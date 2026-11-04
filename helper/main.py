#!/usr/bin/env python3
"""Small local OAuth/Gmail helper for the Omarchy Gmail Notifier widget.

Only Gmail message metadata is requested. The helper never calls an endpoint
that reads message bodies or changes mail state.
"""

from __future__ import annotations

import base64
import copy
import fcntl
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path


APP_DIR = Path.home() / ".config" / "omarchy" / "gmail-notifier"
CONFIG_PATH = APP_DIR / "config.json"
SNAPSHOT_PATH = APP_DIR / "snapshot.json"
SNAPSHOT_LOCK_PATH = APP_DIR / "snapshot.lock"
OAUTH_CLIENT_PATH = APP_DIR / "oauth-client.json"
CACHE_DIR = Path.home() / ".cache" / "omarchy" / "gmail-notifier"
TOKEN_APP = "gmail-notifier"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.metadata"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
DEFAULT_CONFIG = {
    "version": 1,
    "poll_interval_minutes": 2,
    "font_size_offset": 0,
    "panel_width": 376,
    "language": "en",
    "accounts": [],
}


class NotifierError(Exception):
    pass


def load_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("configuration root must be an object")
    except FileNotFoundError:
        data = dict(DEFAULT_CONFIG)
    data.setdefault("version", 1)
    data.setdefault("poll_interval_minutes", 2)
    data.setdefault("flash_duration_seconds", 60)
    data.setdefault("flash_until_clicked", False)
    data.setdefault("font_size_offset", 0)
    data.setdefault("panel_width", 376)
    data.setdefault("language", "en")
    if data["language"] not in {"es", "en"}:
        data["language"] = "en"
    data.setdefault("accounts", [])
    if not isinstance(data["accounts"], list):
        data["accounts"] = []
    try:
        data["poll_interval_minutes"] = max(1, min(60, int(data["poll_interval_minutes"])))
    except (TypeError, ValueError):
        data["poll_interval_minutes"] = 2
    try:
        data["flash_duration_seconds"] = max(5, min(600, int(data.get("flash_duration_seconds", 60))))
    except (TypeError, ValueError):
        data["flash_duration_seconds"] = 60
    data["flash_until_clicked"] = bool(data.get("flash_until_clicked", False))
    try:
        data["font_size_offset"] = max(-2, min(8, int(data["font_size_offset"])))
    except (TypeError, ValueError):
        data["font_size_offset"] = 0
    try:
        data["panel_width"] = max(360, min(720, int(data["panel_width"])))
    except (TypeError, ValueError):
        data["panel_width"] = 376
    return data


def save_config(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(APP_DIR, 0o700)
    fd, tmp_name = tempfile.mkstemp(prefix=".config-", dir=APP_DIR)
    try:
        persisted = copy.deepcopy(data)
        for account in persisted.get("accounts", []):
            for transient in ("messages", "last_error", "details_ready", "unread_count"):
                account.pop(transient, None)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(persisted, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, CONFIG_PATH)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def load_runtime_snapshot() -> dict | None:
    try:
        data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_runtime_snapshot(accounts: list[dict], checked_at: float) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(APP_DIR, 0o700)
    fd, tmp_name = tempfile.mkstemp(prefix=".snapshot-", dir=APP_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"checked_at": checked_at, "accounts": accounts}, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, SNAPSHOT_PATH)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def merge_runtime_accounts(config: dict, snapshot: dict | None) -> list[dict]:
    cached = {a.get("id"): a for a in (snapshot or {}).get("accounts", []) if a.get("id")}
    merged = []
    transient = ("messages", "unread_count", "details_ready", "last_error")
    for configured in config["accounts"]:
        account = copy.deepcopy(configured)
        previous = cached.get(account.get("id"), {})
        for key in transient:
            if key in previous:
                account[key] = previous[key]
        account.setdefault("messages", [])
        account.setdefault("unread_count", 0)
        account.setdefault("details_ready", account["unread_count"] == 0)
        merged.append(account)
    return merged


def snapshot_result(config: dict, snapshot: dict | None) -> dict:
    accounts = merge_runtime_accounts(config, snapshot)
    errors = [f"{a.get('email', 'Account')}: {a['last_error']}" for a in accounts if a.get("last_error")]
    return {
        "ok": True,
        "accounts": accounts,
        "poll_interval_minutes": config["poll_interval_minutes"],
        "flash_duration_seconds": config.get("flash_duration_seconds", 60),
        "flash_until_clicked": config.get("flash_until_clicked", False),
        "font_size_offset": config["font_size_offset"],
        "panel_width": config["panel_width"],
        "language": config["language"],
        "oauth_ready": OAUTH_CLIENT_PATH.is_file(),
        "error": "; ".join(errors),
    }


def emit(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def api_json(url: str, access_token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise NotifierError("Google authorization expired; reconnect this account.") from None
        if error.code == 403:
            raise NotifierError("Gmail denied metadata access; check the OAuth consent and Gmail API.") from None
        raise NotifierError(f"Gmail API returned HTTP {error.code}.") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise NotifierError("Could not reach Gmail. The last saved count is kept.") from None


def token_lookup(email: str) -> dict:
    result = subprocess.run(
        ["secret-tool", "lookup", "application", TOKEN_APP, "account", email],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise NotifierError("No saved Google authorization for this account.")
    try:
        token = json.loads(result.stdout)
        if not isinstance(token, dict) or not token.get("refresh_token"):
            raise ValueError
        return token
    except (json.JSONDecodeError, ValueError):
        raise NotifierError("Saved authorization is invalid; reconnect this account.") from None


def token_store(email: str, token: dict) -> None:
    result = subprocess.run(
        ["secret-tool", "store", "--label=Gmail Notifier account token", "application", TOKEN_APP, "account", email],
        input=json.dumps(token),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise NotifierError("Secret Service could not store the Google authorization.")


def token_clear(email: str) -> None:
    subprocess.run(
        ["secret-tool", "clear", "application", TOKEN_APP, "account", email],
        capture_output=True,
        text=True,
        check=False,
    )


def token_request(form: dict) -> dict:
    data = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise NotifierError(f"Google OAuth returned HTTP {error.code}.") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise NotifierError("Could not reach Google OAuth.") from None


def refresh_access_token(email: str, token: dict) -> tuple[str, dict]:
    if float(token.get("expires_at", 0)) > time.time() + 60 and token.get("access_token"):
        return str(token["access_token"]), token
    client = read_oauth_client()
    form = {
        "client_id": client["client_id"],
        "refresh_token": token["refresh_token"],
        "grant_type": "refresh_token",
    }
    if client.get("client_secret"):
        form["client_secret"] = client["client_secret"]
    refreshed = token_request(form)
    token["access_token"] = refreshed["access_token"]
    token["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600))
    token_store(email, token)
    return str(token["access_token"]), token


def read_oauth_client() -> dict:
    try:
        data = json.loads(OAUTH_CLIENT_PATH.read_text(encoding="utf-8"))
        installed = data.get("installed", {})
        client_id = installed.get("client_id")
        client_secret = installed.get("client_secret", "")
        if not client_id:
            raise ValueError
        return {"client_id": client_id, "client_secret": client_secret}
    except FileNotFoundError:
        raise NotifierError(
            "Set up a Google Desktop OAuth client at ~/.config/omarchy/gmail-notifier/oauth-client.json first."
        ) from None
    except (json.JSONDecodeError, AttributeError, ValueError):
        raise NotifierError("The OAuth client file is invalid; use a Google Desktop app JSON.") from None


class OAuthCallback(http.server.BaseHTTPRequestHandler):
    expected_state = ""
    result: dict = {}

    def do_GET(self) -> None:  # noqa: N802
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if query.get("state", [""])[0] != self.expected_state:
            type(self).result = {"error": "state_mismatch"}
            body = b"Authorization state did not match. You can close this tab."
        elif query.get("error"):
            type(self).result = {"error": query["error"][0]}
            body = b"Google authorization was not completed. You can close this tab."
        else:
            type(self).result = {"code": query.get("code", [""])[0]}
            body = b"Google authorization was received. Return to Omarchy to confirm Gmail access and finish connecting the account."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def authorize_account() -> int:
    client = read_oauth_client()
    APP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(APP_DIR, 0o700)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    state = secrets.token_urlsafe(32)
    OAuthCallback.expected_state = state
    OAuthCallback.result = {}
    server = http.server.HTTPServer(("127.0.0.1", 0), OAuthCallback)
    server.timeout = 1
    redirect_uri = f"http://127.0.0.1:{server.server_port}/"
    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPE,
        "access_type": "offline",
        "prompt": "consent select_account",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    if not webbrowser.open(auth_url):
        server.server_close()
        raise NotifierError("Could not open the default browser for Google authorization.")
    deadline = time.monotonic() + 300
    try:
        while not OAuthCallback.result and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    callback = OAuthCallback.result
    if callback.get("error"):
        raise NotifierError("Google authorization was cancelled or rejected.")
    if not callback.get("code"):
        raise NotifierError("Google authorization timed out; try again.")
    form = {
        "client_id": client["client_id"],
        "code": callback["code"],
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    if client.get("client_secret"):
        form["client_secret"] = client["client_secret"]
    token = token_request(form)
    if not token.get("refresh_token"):
        raise NotifierError("Google did not return a refresh token; revoke the app grant and authorize again.")
    profile = api_json(f"{GMAIL_API}/profile", token["access_token"])
    email = str(profile.get("emailAddress", "")).strip().lower()
    if not email:
        raise NotifierError("Google did not return the Gmail account address.")
    token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
    token_store(email, token)
    config = load_config()
    existing = next((a for a in config["accounts"] if a.get("email", "").lower() == email), None)
    if not existing:
        config["accounts"].append({
            "id": email,
            "email": email,
            "initial": email[:1].upper(),
            "enabled": True,
            "notifications": True,
            "last_notification_ids": [],
            "messages": [],
            "unread_count": 0,
        })
    save_config(config)
    return 0


def gmail_request(url: str, access_token: str) -> dict:
    return api_json(url, access_token)


def message_url(message_id: str) -> str:
    return f"{GMAIL_API}/messages/{urllib.parse.quote(message_id, safe='')}"


def list_unread_ids(access_token: str) -> list[str]:
    """List unread inbox message IDs only; this is the periodic low-cost poll."""
    unread_ids: list[str] = []
    page_token = ""
    while True:
        params = [("labelIds", "INBOX"), ("labelIds", "UNREAD"), ("maxResults", "500")]
        if page_token:
            params.append(("pageToken", page_token))
        url = f"{GMAIL_API}/messages?{urllib.parse.urlencode(params)}"
        page = gmail_request(url, access_token)
        unread_ids.extend(item["id"] for item in page.get("messages", []) if item.get("id"))
        page_token = str(page.get("nextPageToken", ""))
        if not page_token:
            break
    return unread_ids


def fetch_metadata(access_token: str, message_ids: list[str]) -> list[dict]:
    summaries: list[dict] = []
    for message_id in message_ids:
        params = urllib.parse.urlencode([
            ("format", "metadata"),
            ("metadataHeaders", "From"),
            ("metadataHeaders", "Subject"),
        ])
        message = gmail_request(f"{message_url(message_id)}?{params}", access_token)
        headers = {
            str(header.get("name", "")).lower(): str(header.get("value", ""))
            for header in message.get("payload", {}).get("headers", [])
        }
        summaries.append({
            "id": message_id,
            "from": headers.get("from", "Unknown sender"),
            "subject": headers.get("subject", "(no subject)"),
        })
    return summaries


def account_cache_path(email: str) -> Path:
    digest = hashlib.sha256(email.lower().encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def read_details_cache(email: str, unread_ids: list[str]) -> tuple[list[dict], bool]:
    try:
        cached = json.loads(account_cache_path(email).read_text(encoding="utf-8"))
        if cached.get("unread_ids") == unread_ids:
            return cached.get("messages", []), True
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        pass
    return [], False


def write_details_cache(email: str, unread_ids: list[str], messages: list[dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(CACHE_DIR, 0o700)
    path = account_cache_path(email)
    fd, tmp_name = tempfile.mkstemp(prefix=".details-", dir=CACHE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"unread_ids": unread_ids, "messages": messages}, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def notify_new(account: dict, unread_ids: list[str], access_token: str) -> None:
    if account.get("notifications") is False:
        account["last_notification_ids"] = unread_ids
        account["notification_baseline_set"] = True
        return
    previous = set(account.get("last_notification_ids", []))
    if "notification_baseline_set" not in account:
        account["notification_baseline_set"] = True
        account["last_notification_ids"] = unread_ids
        return
    new_ids = [message_id for message_id in unread_ids if message_id not in previous]
    if new_ids:
        try:
            newest = fetch_metadata(access_token, new_ids[:1])[0]
            subject = newest.get("subject") or "New unread email"
        except (NotifierError, IndexError):
            subject = f"{len(new_ids)} new unread message(s)"
        subprocess.run(
            [
                "notify-send",
                "--icon=mail-unread",
                "--app-name=Gmail Notifier",
                "--",
                "Gmail · " + account["email"],
                str(subject),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    account["last_notification_ids"] = unread_ids


def build_snapshot(force: bool = False) -> dict:
    APP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with SNAPSHOT_LOCK_PATH.open("a", encoding="utf-8") as lock_stream:
        fcntl.flock(lock_stream, fcntl.LOCK_EX)
        config = load_config()
        previous = load_runtime_snapshot()
        now = time.time()
        checked_at = float((previous or {}).get("checked_at", 0))
        if not force and previous and now - checked_at < config["poll_interval_minutes"] * 60:
            return snapshot_result(config, previous)

        cached_accounts = {a.get("id"): a for a in (previous or {}).get("accounts", []) if a.get("id")}
        polled_accounts = []
        for configured in config["accounts"]:
            account = copy.deepcopy(configured)
            prior = cached_accounts.get(account.get("id"), {})
            for key in ("messages", "unread_count", "details_ready", "last_error"):
                if key in prior:
                    account[key] = prior[key]
            account.setdefault("messages", [])
            account.setdefault("unread_count", 0)
            if account.get("enabled") is False:
                polled_accounts.append(account)
                continue
            try:
                token = token_lookup(account["email"])
                access_token, _token = refresh_access_token(account["email"], token)
                unread_ids = list_unread_ids(access_token)
                notify_new(account, unread_ids, access_token)
                messages, details_ready = read_details_cache(account["email"], unread_ids)
                account["messages"] = messages
                account["unread_count"] = len(unread_ids)
                account["details_ready"] = details_ready or not unread_ids
                account.pop("last_error", None)
            except (NotifierError, KeyError, OSError) as error:
                account["last_error"] = str(error)
            polled_accounts.append(account)

        # Preserve settings changed while the Gmail requests were in flight.
        latest_config = load_config()
        polled_by_id = {a.get("id"): a for a in polled_accounts}
        for account in latest_config["accounts"]:
            polled = polled_by_id.get(account.get("id"))
            if not polled:
                continue
            for key in ("last_notification_ids", "notification_baseline_set"):
                if key in polled:
                    account[key] = polled[key]
        save_config(latest_config)
        save_runtime_snapshot(merge_runtime_accounts(latest_config, {"accounts": polled_accounts}), time.time())
        return snapshot_result(latest_config, load_runtime_snapshot())


def account_details(account_id: str) -> int:
    APP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with SNAPSHOT_LOCK_PATH.open("a", encoding="utf-8") as lock_stream:
        fcntl.flock(lock_stream, fcntl.LOCK_EX)
        config = load_config()
        account = find_account(config, account_id)
        if account is None:
            emit({"ok": False, "error": "Account not found"})
            return 1
        if account.get("enabled") is False:
            emit({"ok": False, "error": "This account is paused"})
            return 1
        try:
            token = token_lookup(account["email"])
            access_token, _token = refresh_access_token(account["email"], token)
            unread_ids = list_unread_ids(access_token)
            messages = fetch_metadata(access_token, unread_ids)
            write_details_cache(account["email"], unread_ids, messages)
            account["messages"] = messages
            account["unread_count"] = len(unread_ids)
            account["details_ready"] = True
            account.pop("last_error", None)
            previous = load_runtime_snapshot() or {}
            runtime_accounts = merge_runtime_accounts(config, previous)
            for index, current in enumerate(runtime_accounts):
                if current.get("id") == account_id:
                    runtime_accounts[index] = copy.deepcopy(account)
                    break
            save_runtime_snapshot(runtime_accounts, float(previous.get("checked_at", 0)))
            emit(snapshot_result(config, load_runtime_snapshot()))
            return 0
        except (NotifierError, KeyError, OSError) as error:
            emit({"ok": False, "error": f"{account.get('email', 'Account')}: {error}"})
            return 1


def find_account(config: dict, account_id: str) -> dict | None:
    return next((a for a in config["accounts"] if a.get("id") == account_id), None)


def set_enabled(account_id: str, value: str) -> int:
    config = load_config()
    account = find_account(config, account_id)
    if account is None:
        emit({"ok": False, "error": "Account not found"})
        return 1
    account["enabled"] = value.lower() in {"true", "1", "yes"}
    save_config(config)
    emit(build_snapshot(force=account["enabled"]))
    return 0


def set_initial(account_id: str, value: str) -> int:
    config = load_config()
    account = find_account(config, account_id)
    initial = value.strip()
    if account is None:
        emit({"ok": False, "error": "Account not found"})
        return 1
    if not initial or len(initial) > 7:
        emit({"ok": False, "error": "Choose a letter or symbol (up to seven characters)"})
        return 1
    account["initial"] = initial.upper()
    save_config(config)
    emit(build_snapshot())
    return 0


def set_notifications(account_id: str, value: str) -> int:
    config = load_config()
    account = find_account(config, account_id)
    if account is None:
        emit({"ok": False, "error": "Account not found"})
        return 1
    account["notifications"] = value.lower() in {"true", "1", "yes"}
    save_config(config)
    emit(build_snapshot())
    return 0


def set_interval(value: str) -> int:
    try:
        interval = max(1, min(60, int(value)))
    except ValueError:
        emit({"ok": False, "error": "Check interval must be between 1 and 60 minutes"})
        return 1
    config = load_config()
    config["poll_interval_minutes"] = interval
    save_config(config)
    emit(build_snapshot())
    return 0


def set_display_setting(name: str, value: str) -> int:
    config = load_config()
    if name == "language":
        language = value.lower()
        if language not in {"es", "en"}:
            emit({"ok": False, "error": "Language must be es or en"})
            return 1
        config["language"] = language
        save_config(config)
        emit(build_snapshot())
        return 0
    if name == "flash-until-clicked":
        config["flash_until_clicked"] = value.lower() in {"true", "1", "yes"}
        save_config(config)
        emit(build_snapshot())
        return 0
    try:
        number = int(value)
    except ValueError:
        emit({"ok": False, "error": "Display setting must be a whole number"})
        return 1
    if name == "font-size-offset":
        config["font_size_offset"] = max(-2, min(8, number))
    elif name == "panel-width":
        config["panel_width"] = max(360, min(720, number))
    elif name == "flash-duration-seconds":
        config["flash_duration_seconds"] = max(5, min(600, number))
    else:
        emit({"ok": False, "error": "Unknown display setting"})
        return 1
    save_config(config)
    emit(build_snapshot())
    return 0


def reorder_account(account_id: str, direction: str) -> int:
    config = load_config()
    index = next((i for i, item in enumerate(config["accounts"]) if item.get("id") == account_id), -1)
    if index < 0:
        emit({"ok": False, "error": "Account not found"})
        return 1
    target = index - 1 if direction == "up" else index + 1 if direction == "down" else index
    if direction not in {"up", "down"}:
        emit({"ok": False, "error": "Direction must be up or down"})
        return 1
    if 0 <= target < len(config["accounts"]):
        config["accounts"][index], config["accounts"][target] = config["accounts"][target], config["accounts"][index]
    save_config(config)
    emit(build_snapshot())
    return 0


def remove_account(account_id: str) -> int:
    config = load_config()
    account = find_account(config, account_id)
    if account is None:
        emit({"ok": False, "error": "Account not found"})
        return 1
    token_clear(account["email"])
    try:
        account_cache_path(account["email"]).unlink()
    except FileNotFoundError:
        pass
    config["accounts"] = [a for a in config["accounts"] if a.get("id") != account_id]
    save_config(config)
    emit(build_snapshot())
    return 0


def main(argv: list[str]) -> int:
    try:
        if not argv or argv[0] == "snapshot":
            emit(build_snapshot())
            return 0
        command, *args = argv
        if command in ("update", "refresh"):
            emit(build_snapshot(force=True))
            return 0
        if command == "set-enabled" and len(args) == 2:
            return set_enabled(args[0], args[1])
        if command == "set-initial" and len(args) == 2:
            return set_initial(args[0], args[1])
        if command == "set-notifications" and len(args) == 2:
            return set_notifications(args[0], args[1])
        if command == "set-interval" and len(args) == 1:
            return set_interval(args[0])
        if command == "set-display" and len(args) == 2:
            return set_display_setting(args[0], args[1])
        if command == "move-account" and len(args) == 2:
            return reorder_account(args[0], args[1])
        if command == "details" and len(args) == 1:
            return account_details(args[0])
        if command == "remove-account" and len(args) == 1:
            return remove_account(args[0])
        if command == "add-account" and not args:
            authorize_account()
            emit(build_snapshot(force=True))
            return 0
        emit({"ok": False, "error": "Unknown command"})
        return 2
    except NotifierError as error:
        emit({"ok": False, "error": str(error)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
