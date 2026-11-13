#!/usr/bin/env python3
"""Small local OAuth/Gmail helper for the Omarchy Gmail Notifier widget.

Only Gmail message metadata is requested. The helper never calls an endpoint
that reads message bodies or changes mail state.
"""

from __future__ import annotations

import base64
import copy
from email.utils import parseaddr
import fcntl
import hashlib
import http.server
import json
import math
from html import escape
import os
import secrets
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from alerts import AlertStore
from contextlib import contextmanager
import hmac
import threading
import desktop
from storage import StorageError, locked, read_object, atomic_write, private_directory


APP_DIR = Path.home() / ".config" / "omarchy" / "gmail-notifier"
CONFIG_PATH = APP_DIR / "config.json"
SNAPSHOT_PATH = APP_DIR / "snapshot.json"
SNAPSHOT_LOCK_PATH = APP_DIR / "snapshot.lock"
OAUTH_CLIENT_PATH = APP_DIR / "oauth-client.json"
CACHE_DIR = Path.home() / ".cache" / "omarchy" / "gmail-notifier"
TOKEN_APP = "gmail-notifier"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.metadata"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_HTTP_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_UNREAD_IDS = 10000
MAX_DETAIL_MESSAGES = 50
MAX_ACCOUNTS = 32
NETWORK_CONTEXT = threading.local()
AUTH_CANCELLED = threading.Event()
OUTPUT = threading.local()
MAX_HEADER_CHARS = 4096
DEFAULT_CONFIG = {
    "version": 1,
    "poll_interval_minutes": 2,
    "font_size_offset": 0,
    "panel_width": 376,
    "language": "en",
    "accounts": [],
}


class NotifierError(Exception):
    def __init__(self, message, retry_after=0):
        super().__init__(message)
        self.retry_after = min(3600, max(0, retry_after))


def load_config() -> dict:
    data = read_object(CONFIG_PATH, missing=None, limit=1024 * 1024)
    if data is None:
        data = copy.deepcopy(DEFAULT_CONFIG)
        data['language'] = 'auto'
    if not isinstance(data.get('accounts', []), list):
        raise StorageError('Invalid account list; restore config.json from a valid backup.')
    defaults = {'poll_interval_minutes': (2, 1, 60), 'flash_duration_seconds': (60, 5, 600),
                'font_size_offset': (0, -2, 8), 'panel_width': (376, 360, 720)}
    for name, (default, lower, upper) in defaults.items():
        value = data.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise StorageError('Invalid display settings in config.json.')
        data[name] = max(lower, min(upper, value))
    data.setdefault('version', 1)
    if data['version'] != 1:
        raise StorageError('Unsupported configuration version; keep this file and use a compatible release.')
    data.setdefault('flash_until_clicked', False)
    data.setdefault('language', 'auto')
    if data['language'] not in ('auto', 'es', 'en') or not isinstance(data['flash_until_clicked'], bool):
        raise StorageError('Invalid language or alert settings in config.json.')
    data.setdefault('accounts', [])
    ids = set()
    for account in data['accounts']:
        if not isinstance(account, dict):
            raise StorageError('Invalid account entry in config.json.')
        for field in ('id', 'email'):
            value = account.get(field)
            if not isinstance(value, str) or not value or len(value) > 320 or any(ord(c) < 32 for c in value):
                raise StorageError('Invalid account identity in config.json.')
        if account['id'] in ids:
            raise StorageError('Duplicate account identity in config.json.')
        ids.add(account['id'])
        for field in ('last_notification_ids',):
            items = account.get(field, [])
            if not isinstance(items, list) or len(items) > MAX_UNREAD_IDS or not all(isinstance(i, str) for i in items):
                raise StorageError('Invalid notification history in config.json.')
        account.setdefault('generation', 'legacy')
        if not isinstance(account['generation'], str) or len(account['generation']) > 64:
            raise StorageError('Invalid account generation in config.json.')
        account.setdefault('initial', '?')
        if not isinstance(account['initial'], str) or len(account['initial']) > 64 or any(ord(c) < 32 for c in account['initial']):
            raise StorageError('Invalid account label in config.json.')
        for name in ('enabled', 'notifications'):
            account.setdefault(name, True)
            if not isinstance(account[name], bool):
                raise StorageError('Invalid account switch in config.json.')
    return data


def save_config(data: dict) -> None:
    persisted = copy.deepcopy(data)
    for account in persisted.get('accounts', []):
        for key in ('messages', 'last_error', 'notification_error', 'details_ready', 'unread_count',
                    'unread_ids', 'details_more', 'details_loaded', 'details_error', 'retry_at', 'failures'):
            account.pop(key, None)
    previous = read_object(CONFIG_PATH)
    if previous == persisted:
        return
    if previous is not None:
        atomic_write(APP_DIR / 'config.backup.json', previous)
    atomic_write(CONFIG_PATH, persisted)


@contextmanager
def config_transaction():
    with locked(APP_DIR / 'config.lock'):
        config = load_config()
        yield config
        save_config(config)


@contextmanager
def network_budget(seconds=60):
    previous = getattr(NETWORK_CONTEXT, 'deadline', None)
    NETWORK_CONTEXT.deadline = time.monotonic() + seconds
    try:
        yield
    finally:
        NETWORK_CONTEXT.deadline = previous


def request_timeout():
    deadline = getattr(NETWORK_CONTEXT, 'deadline', None)
    remaining = deadline - time.monotonic() if deadline else 20
    if remaining <= 0:
        raise NotifierError('Google operation timed out; retry when ready.')
    return min(20, remaining)


def valid_runtime_account(account):
    count = account.get('unread_count', 0)
    if not isinstance(count, int) or not 0 <= count <= MAX_UNREAD_IDS:
        return False
    ids = account.get('unread_ids', [])
    if not isinstance(ids, list) or len(ids) > MAX_UNREAD_IDS or not all(isinstance(i, str) for i in ids):
        return False
    messages = account.get('messages', [])
    if not isinstance(messages, list) or len(messages) > MAX_UNREAD_IDS:
        return False
    for message in messages:
        if not isinstance(message, dict) or not all(isinstance(message.get(k), str) for k in ('id', 'from', 'subject')):
            return False
    for key in ('retry_at', 'failures'):
        value = account.get(key, 0)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            return False
    return True


def load_runtime_snapshot() -> dict | None:
    try:
        value = read_object(SNAPSHOT_PATH)
        if value is not None and (not isinstance(value.get('accounts'), list)
                                  or not all(isinstance(a, dict) for a in value.get('accounts', []))
                                  or not isinstance(value.get('checked_at'), (int, float))
                                  or not math.isfinite(value['checked_at'])
                                  or not 0 <= value['checked_at'] <= time.time() + 60
                                  or not all(valid_runtime_account(a) for a in value.get('accounts', []))):
            return None
        return value
    except StorageError:
        return None


def save_runtime_snapshot(accounts: list[dict], checked_at: float) -> None:
    accounts = copy.deepcopy(accounts)
    value = {'checked_at': checked_at, 'accounts': accounts}
    while len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > 8 * 1024 * 1024:
        largest = max(accounts, key=lambda a: len(a.get('messages', [])), default={})
        messages = largest.get('messages', [])
        if not messages:
            raise NotifierError('Shared state limit reached; reduce the unread inbox.')
        largest['messages'] = messages[:len(messages) // 2]
        largest['details_loaded'] = len(largest['messages'])
        largest['details_more'] = True
    atomic_write(SNAPSHOT_PATH, value)


def merge_runtime_accounts(config: dict, snapshot: dict | None) -> list[dict]:
    cached = {a.get("id"): a for a in (snapshot or {}).get("accounts", []) if a.get("id")}
    merged = []
    transient = ("messages", "unread_count", "details_ready", "last_error", "notification_error",
                 "unread_ids", "details_more", "details_loaded", "details_error", "retry_at", "failures")
    for configured in config["accounts"]:
        account = copy.deepcopy(configured)
        previous = cached.get(account.get("id"), {})
        if previous.get("generation", "legacy") != account.get("generation", "legacy"):
            previous = {}
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
    for account in accounts:
        for key in ("unread_ids", "last_notification_ids", "notification_baseline_set", "generation"):
            account.pop(key, None)
    errors = [f"{a.get('initial', 'Account')}: {a.get('last_error') or a.get('notification_error') or a.get('details_error')}"
              for a in accounts if a.get("last_error") or a.get("notification_error") or a.get("details_error")]
    return {
        "ok": True,
        "alerts": AlertStore(APP_DIR).visible(accounts),
        "accounts": accounts,
        "poll_interval_minutes": config["poll_interval_minutes"],
        "flash_duration_seconds": config.get("flash_duration_seconds", 60),
        "flash_until_clicked": config.get("flash_until_clicked", False),
        "font_size_offset": config["font_size_offset"],
        "panel_width": config["panel_width"],
        "language": config["language"],
        "effective_language": effective_language(config["language"]),
        "oauth_ready": OAUTH_CLIENT_PATH.is_file(),
        "error": "; ".join(errors),
    }


def emit(data: dict) -> None:
    sink = getattr(OUTPUT, "sink", None)
    if sink:
        sink(data)
    else:
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")), flush=True)


def read_json_response(response) -> dict:
    payload = response.read(MAX_HTTP_RESPONSE_BYTES + 1)
    if len(payload) > MAX_HTTP_RESPONSE_BYTES:
        raise NotifierError("Google response was too large; the previous state is kept.")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise NotifierError("Google returned an invalid JSON response.") from None
    if not isinstance(value, dict):
        raise NotifierError("Google returned an unexpected response.")
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, url):
        return None


def safe_open(request):
    parsed = urllib.parse.urlparse(request.full_url)
    if parsed.scheme != 'https' or parsed.hostname not in ('gmail.googleapis.com', 'oauth2.googleapis.com'):
        raise NotifierError('Refused unexpected Google endpoint.')
    return urllib.request.build_opener(NoRedirect()).open(request, timeout=request_timeout())


def api_json(url: str, access_token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    try:
        with safe_open(request) as response:
            return read_json_response(response)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise NotifierError("Google authorization expired; reconnect this account.") from None
        if error.code == 403:
            raise NotifierError("Gmail denied metadata access; check the OAuth consent and Gmail API.") from None
        retry_after = error.headers.get('Retry-After', '60')
        try:
            retry_after = int(retry_after)
        except (TypeError, ValueError):
            retry_after = 60
        raise NotifierError(f"Gmail API returned HTTP {error.code}.", retry_after if error.code in (429, 503) else 0) from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        raise NotifierError("Could not reach Gmail. The last saved count is kept.") from None


def token_lookup(email: str, generation=None) -> dict:
    try:
        # Migration must share the removal lock so it cannot recreate a cleared secret.
        with config_transaction() as config:
            account = next((a for a in config['accounts'] if a['email'] == email and a['enabled']), None)
            if account is None or (generation is not None and account.get('generation') != generation):
                raise NotifierError('Account was removed, paused or replaced.')
            token = desktop.lookup(email, preserve_legacy=True)
        if not isinstance(token, dict) or not isinstance(token.get('refresh_token'), str) or not token['refresh_token']:
            raise NotifierError('No valid saved Google authorization; reconnect this account.')
        if not isinstance(token.get('expires_at', 0), (int, float)) or not 0 <= token.get('expires_at', 0) < 1e12:
            raise NotifierError('No valid saved Google authorization; reconnect this account.')
        return token
    except NotifierError:
        raise
    except RuntimeError as error:
        raise NotifierError(str(error)) from error
    except Exception as error:
        raise NotifierError('Secret Service is unavailable or locked; unlock it and retry.') from error


def token_store(email: str, token: dict) -> None:
    try:
        desktop.store(email, token, preserve_legacy=True)
    except Exception as error:
        raise NotifierError('Secret Service could not store authorization.') from error


def token_clear(email: str) -> None:
    try:
        desktop.clear(email)
    except Exception as error:
        raise NotifierError('Secret Service could not remove authorization; account was retained.') from error


def token_request(form: dict) -> dict:
    data = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with safe_open(request) as response:
            token = read_json_response(response)
            access = token.get('access_token')
            lifetime = token.get('expires_in', 3600)
            if not isinstance(access, str) or not access or len(access) > 16384 or isinstance(lifetime, bool) or not isinstance(lifetime, int) or not 1 <= lifetime <= 86400:
                raise NotifierError('Google returned an invalid access token response.')
            return token
    except urllib.error.HTTPError as error:
        raise NotifierError(f"Google OAuth returned HTTP {error.code}.") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        raise NotifierError("Could not reach Google OAuth.") from None


def refresh_access_token(email: str, token: dict, generation=None) -> tuple[str, dict]:
    if float(token.get("expires_at", 0)) > time.time() + 60 and isinstance(token.get("access_token"), str):
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
    if not isinstance(refreshed.get('access_token'), str) or not refreshed['access_token']:
        raise NotifierError('Google did not return a valid access token.')
    if 'refresh_token' in refreshed:
        if not isinstance(refreshed['refresh_token'], str) or not refreshed['refresh_token']:
            raise NotifierError('Google returned an invalid refresh token; saved authorization was retained.')
        token['refresh_token'] = refreshed['refresh_token']
    token["access_token"] = refreshed["access_token"]
    token["expires_at"] = time.time() + max(60, min(86400, int(refreshed.get("expires_in", 3600))))
    with config_transaction() as config:
        account = next((a for a in config['accounts'] if a['email'] == email and a['enabled']), None)
        if account is None or (generation is not None and account.get('generation') != generation):
            raise NotifierError('Account was removed, paused or replaced during authorization refresh.')
        token_store(email, token)
    return str(token["access_token"]), token


def read_oauth_client() -> dict:
    try:
        data = json.loads(OAUTH_CLIENT_PATH.read_text(encoding="utf-8"))
        installed = data.get("installed", {})
        client_id = installed.get("client_id")
        client_secret = installed.get("client_secret", "")
        if not isinstance(client_id, str) or not client_id or len(client_id) > 1024 or not isinstance(client_secret, str):
            raise ValueError
        return {"client_id": client_id, "client_secret": client_secret}
    except FileNotFoundError:
        raise NotifierError(
            "Set up a Google Desktop OAuth client at ~/.config/omarchy/gmail-notifier/oauth-client.json first."
        ) from None
    except (json.JSONDecodeError, AttributeError, ValueError, TypeError):
        raise NotifierError("The OAuth client file is invalid; use a Google Desktop app JSON.") from None


class OAuthCallback(http.server.BaseHTTPRequestHandler):
    expected_state = ""
    result: dict = {}

    def do_GET(self) -> None:  # noqa: N802
        url = urllib.parse.urlparse(self.path)
        try:
            query = urllib.parse.parse_qs(url.query, max_num_fields=10)
        except ValueError:
            self.send_error(400, 'Invalid authorization request')
            return
        if url.path != '/' or not hmac.compare_digest(query.get('state', [''])[0].encode('utf-8'), self.expected_state.encode('utf-8')):
            self.send_error(400, 'Unrelated authorization request')
            return
        elif query.get("error"):
            type(self).result = {"error": query["error"][0]}
            body = b"Google authorization was not completed. You can close this tab."
        else:
            code = query.get('code', [''])[0]
            if not code or len(code) > 8192:
                self.send_error(400, 'Invalid authorization code')
                return
            type(self).result = {"code": code}
            body = b"Google authorization was received. Return to Omarchy to confirm Gmail access and finish connecting the account."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def authorize_account() -> int:
    AUTH_CANCELLED.clear()
    try:
        with desktop.secret_api():
            pass
    except (RuntimeError, ImportError, ValueError) as error:
        raise NotifierError(str(error)) from error
    client = read_oauth_client()
    APP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(APP_DIR, 0o700)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    state = secrets.token_urlsafe(32)
    OAuthCallback.expected_state = state
    OAuthCallback.result = {}
    class CallbackServer(http.server.HTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(2)
            return connection, address
    server = CallbackServer(("127.0.0.1", 0), OAuthCallback)
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
        while not OAuthCallback.result and time.monotonic() < deadline and not AUTH_CANCELLED.is_set():
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
    if not isinstance(token.get("refresh_token"), str) or not isinstance(token.get("access_token"), str):
        raise NotifierError("Google did not return a refresh token; revoke the app grant and authorize again.")
    profile = api_json(f"{GMAIL_API}/profile", token["access_token"])
    email = str(profile.get("emailAddress", "")).strip().lower()
    if not email:
        raise NotifierError("Google did not return the Gmail account address.")
    token["expires_at"] = time.time() + max(60, min(86400, int(token.get("expires_in", 3600))))
    with config_transaction() as config:
        existing = next((a for a in config['accounts'] if a['email'].lower() == email), None)
        if existing is None and len(config['accounts']) >= MAX_ACCOUNTS:
            raise NotifierError('Maximum configured account count reached.')
        token_store(email, token)
        if existing is None:
            config['accounts'].append({
                'id': secrets.token_hex(16), 'email': email, 'generation': secrets.token_hex(16),
                'initial': email[:1].upper(), 'enabled': True, 'notifications': True,
                'last_notification_ids': [],
            })
    return 0


def gmail_request(url: str, access_token: str) -> dict:
    return api_json(url, access_token)


def message_url(message_id: str) -> str:
    return f"{GMAIL_API}/messages/{urllib.parse.quote(message_id, safe='')}"


def list_unread_ids(access_token: str) -> list[str]:
    unread_ids, seen_ids, seen_pages = [], set(), set()
    page_token = ''
    for _ in range(25):
        params = [('labelIds', 'INBOX'), ('labelIds', 'UNREAD'), ('maxResults', '500')]
        if page_token:
            params.append(('pageToken', page_token))
        page = gmail_request(f'{GMAIL_API}/messages?{urllib.parse.urlencode(params)}', access_token)
        items = page.get('messages', [])
        if not isinstance(items, list) or len(items) > 500:
            raise NotifierError('Google returned an invalid message list.')
        for item in items:
            message_id = item.get('id') if isinstance(item, dict) else None
            if not isinstance(message_id, str) or not message_id or len(message_id) > 128 or not message_id.isalnum():
                raise NotifierError('Google returned an invalid message identifier.')
            if message_id not in seen_ids:
                unread_ids.append(message_id)
                seen_ids.add(message_id)
        if len(unread_ids) > MAX_UNREAD_IDS:
            raise NotifierError('Unread inbox exceeds the supported limit of 10000 messages.')
        page_token = page.get('nextPageToken', '')
        if not page_token:
            return unread_ids
        if not isinstance(page_token, str) or len(page_token) > 512 or page_token in seen_pages:
            raise NotifierError('Google returned invalid pagination.')
        seen_pages.add(page_token)
    raise NotifierError('Google pagination exceeded the operation limit.')


def fetch_metadata(access_token: str, message_ids: list[str]) -> list[dict]:
    if len(message_ids) > MAX_DETAIL_MESSAGES:
        raise NotifierError("Too many unread messages to load safely; narrow the inbox and try again.")
    summaries: list[dict] = []
    for message_id in message_ids:
        params = urllib.parse.urlencode([
            ("format", "metadata"),
            ("metadataHeaders", "From"),
            ("metadataHeaders", "Subject"),
        ])
        try:
            message = gmail_request(f"{message_url(message_id)}?{params}", access_token)
        except NotifierError as error:
            if 'HTTP 404' in str(error):
                continue
            raise
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
        raw_headers = payload.get("headers", [])
        if not isinstance(raw_headers, list) or len(raw_headers) > 100:
            raise NotifierError('Google returned invalid message headers.')
        headers = {
            str(header.get("name", "")).lower(): str(header.get("value", ""))[:MAX_HEADER_CHARS]
            for header in raw_headers
            if isinstance(header, dict)
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
        cached = read_object(account_cache_path(email)) or {}
        messages = cached.get('messages', [])
        if not isinstance(messages, list) or not all(isinstance(m, dict) and isinstance(m.get('id'), str)
                and isinstance(m.get('from'), str) and isinstance(m.get('subject'), str) for m in messages):
            return [], False
        by_id = {m['id']: m for m in messages}
        current = [by_id[i] for i in unread_ids if i in by_id]
        return current, len(current) == len(unread_ids)
    except StorageError:
        return [], False


def write_details_cache(email: str, unread_ids: list[str], messages: list[dict]) -> None:
    value = {'unread_ids': unread_ids, 'messages': messages}
    if len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > 4 * 1024 * 1024:
        raise NotifierError('Header cache limit reached; reduce the unread inbox before loading more.')
    atomic_write(account_cache_path(email), value)


def notify_new(account: dict, unread_ids: list[str], access_token: str, language='auto') -> None:
    previous = set(account.get('last_notification_ids', []))
    new_ids = [i for i in unread_ids if i not in previous]
    metadata = []
    if account.get('notifications', True) and account.get('notification_baseline_set') and new_ids:
        try:
            metadata = fetch_metadata(access_token, new_ids[:1])
        except NotifierError:
            pass
    deliver_notification(account, unread_ids, metadata, language)


def deliver_notification(account, unread_ids, metadata, language):
    previous = set(account.get('last_notification_ids', []))
    baseline = account.get('notification_baseline_set', False)
    account['last_notification_ids'] = unread_ids
    account['notification_baseline_set'] = True
    account.pop('notification_error', None)
    new_ids = [i for i in unread_ids if i not in previous]
    if not baseline or not account.get('notifications', True) or not new_ids:
        return
    sender, subject = '', ''
    try:
        newest = metadata[0]
        sender, _ = parseaddr(newest.get('from', ''))
        sender = sender.strip()[:160]
        subject = newest.get('subject', '')[:240]
    except (NotifierError, IndexError):
        pass
    spanish = effective_language(language).startswith('es')
    heading = 'Nuevo email en la cuenta' if spanish else 'New email in account'
    subject = subject or ('Nuevo correo sin leer' if spanish else 'New unread mail')
    # Headline is plain text in Omarchy. Body supports only a safe markup subset.
    label = account.get('initial', '?')[:7]
    body = (f'<b>{escape(sender, quote=False)}</b>\n' if sender else '') + escape(subject, quote=False)
    try:
        desktop.notify(f'{heading} ({label})', body)
    except Exception:
        account['notification_error'] = 'Desktop notification delivery failed; Gmail count is still current.'


def effective_language(language):
    if language != 'auto':
        return language
    # QML passes the live shell language on the private service channel.
    return getattr(NETWORK_CONTEXT, 'language', None) or os.environ.get('LANG', 'en').split('.')[0].replace('_', '-')


def poll_account(config, account, force=False):
    if not account['enabled'] or (not force and account.get('retry_at', 0) > time.time()):
        return
    # A slow account gets its own budget; it cannot consume every other
    # account's allowance and permanently starve accounts later in the list.
    try:
        with network_budget():
            request_timeout()
            token = token_lookup(account['email'], account['generation'])
            access, _ = refresh_access_token(account['email'], token, account['generation'])
            ids = list_unread_ids(access)
            request_timeout()
            new_ids = [i for i in ids if i not in account.get('last_notification_ids', [])]
            newest = []
            if account.get('notifications') and account.get('notification_baseline_set') and new_ids:
                try:
                    newest = fetch_metadata(access, new_ids[:1])
                except NotifierError:
                    pass
            request_timeout()
            with config_transaction() as latest:
                current = find_account(latest, account['id'])
                if not current or not current['enabled'] or current.get('generation') != account.get('generation'):
                    return
                account.update({k: current[k] for k in ('initial', 'notifications')})
                AlertStore(APP_DIR).observe(account['id'], ids, latest['flash_until_clicked'], latest['flash_duration_seconds'])
                account['unread_ids'] = ids
                messages, ready = read_details_cache(account['email'], ids)
                account.update(messages=messages, unread_count=len(ids), details_ready=ready or not ids,
                               details_loaded=len(messages), details_more=len(messages) < len(ids), failures=0, retry_at=0)
                account.pop('last_error', None)
                account.pop('details_error', None)
                deliver_notification(account, ids, newest, latest['language'])
                current['last_notification_ids'] = ids
                current['notification_baseline_set'] = True
    except (NotifierError, StorageError, OSError, ValueError, TypeError, KeyError) as error:
        failures = min(6, int(account.get('failures', 0)) + 1)
        message = str(error) if isinstance(error, (NotifierError, StorageError)) else 'Could not update this account; polling will retry.'
        account.update(last_error=message, failures=failures,
                       retry_at=time.time() + max(getattr(error, 'retry_after', 0), min(900, 30 * 2 ** (failures - 1))))


def poll_one(account_id, force=False):
    with locked(SNAPSHOT_LOCK_PATH):
        config = load_config()
        previous = load_runtime_snapshot() or {'checked_at': 0, 'accounts': []}
        accounts = merge_runtime_accounts(config, previous)
        account = next((a for a in accounts if a['id'] == account_id), None)
        if account is not None:
            poll_account(config, account, force)
        latest = load_config()
        save_runtime_snapshot(merge_runtime_accounts(latest, {'accounts': accounts}), previous['checked_at'])
        state = snapshot_result(latest, load_runtime_snapshot())
        error = account.get('last_error', '') if account else ''
        state['ok'] = not bool(error)
        if error:
            state['error'] = 'One account could not be updated; automatic polling will retry.'
        emit(state)
        return 0 if state['ok'] else 1


def record_poll_failure(account_id, message):
    with locked(SNAPSHOT_LOCK_PATH, timeout=1):
        config = load_config()
        previous = load_runtime_snapshot() or {'checked_at': 0, 'accounts': []}
        accounts = merge_runtime_accounts(config, previous)
        for account in accounts:
            if account['id'] == account_id and account['enabled']:
                account.update(last_error=message, retry_at=time.time() + 30)
        save_runtime_snapshot(accounts, previous['checked_at'])


def finish_poll():
    with locked(SNAPSHOT_LOCK_PATH, timeout=1):
        config = load_config()
        save_runtime_snapshot(merge_runtime_accounts(config, load_runtime_snapshot()), time.time())


def build_snapshot(force: bool = False) -> dict:
    with locked(SNAPSHOT_LOCK_PATH):
        config = load_config()
        previous = load_runtime_snapshot()
        checked_at = float((previous or {}).get('checked_at', 0))
        if not force and previous and time.time() - checked_at < config['poll_interval_minutes'] * 60:
            return snapshot_result(config, previous)
        polled_accounts = merge_runtime_accounts(config, previous)
        for account in polled_accounts:
            poll_account(config, account, force)
            # Publish completed accounts incrementally without marking the whole
            # poll as finished or resetting another account's saved settings.
            latest = load_config()
            merged = merge_runtime_accounts(latest, {'accounts': polled_accounts})
            save_runtime_snapshot(merged, checked_at)
            progress = getattr(OUTPUT, 'progress', None)
            if progress is not None:
                progress()
        latest = load_config()
        merged = merge_runtime_accounts(latest, {'accounts': polled_accounts})
        save_runtime_snapshot(merged, time.time())
        return snapshot_result(latest, load_runtime_snapshot())


def account_details(account_id: str, more=False) -> int:
    with network_budget():
        config = load_config()
        account = find_account(config, account_id)
        if account is None or not account['enabled']:
            raise NotifierError('Account is missing or paused.')
        generation = account['generation']
        previous = load_runtime_snapshot() or {'accounts': [], 'checked_at': 0}
        runtime = merge_runtime_accounts(config, previous)
        current = next(a for a in runtime if a['id'] == account_id)
        try:
            token = token_lookup(account['email'], account['generation'])
            access, _ = refresh_access_token(account['email'], token, account['generation'])
            ids = current.get('unread_ids')
            if not isinstance(ids, list):
                ids = list_unread_ids(access)
            cached, _ = read_details_cache(account['email'], ids)
            cached_ids = {m['id'] for m in cached}
            pending = [i for i in ids if i not in cached_ids][:MAX_DETAIL_MESSAGES] if more or not cached else []
            messages = cached + fetch_metadata(access, pending)
            by_id = {m['id']: m for m in messages}
            messages = [by_id[i] for i in ids if i in by_id]
            with config_transaction() as latest:
                configured = find_account(latest, account_id)
                if not configured or not configured['enabled'] or configured['generation'] != generation:
                    raise NotifierError('Account changed while details were loading.')
                write_details_cache(account['email'], ids, messages)
                # Reread the latest shared snapshot before replacing only this account.
                recent = load_runtime_snapshot() or previous
                runtime = merge_runtime_accounts(latest, recent)
                for item in runtime:
                    if item['id'] == account_id:
                        item.update(messages=messages, unread_ids=ids, unread_count=len(ids), details_ready=True,
                                    details_loaded=len(messages), details_more=len(cached) + len(pending) < len(ids))
                        item.pop('details_error', None)
                save_runtime_snapshot(runtime, recent['checked_at'])
            emit(snapshot_result(latest, load_runtime_snapshot()))
            return 0
        except NotifierError as error:
            raise NotifierError(str(error)) from error


def find_account(config: dict, account_id: str) -> dict | None:
    return next((a for a in config["accounts"] if a.get("id") == account_id), None)


def set_enabled(account_id: str, value: str) -> int:
    with config_transaction() as config:
        account = find_account(config, account_id)
        if account is None:
            emit({"ok": False, "error": "Account not found"})
            return 1
        account["enabled"] = value.lower() in {"true", "1", "yes"}
        emit(snapshot_result(config, load_runtime_snapshot()))
        return 0


def set_initial(account_id: str, value: str) -> int:
    with config_transaction() as config:
        account = find_account(config, account_id)
        initial = value.strip()
        if account is None:
            emit({"ok": False, "error": "Account not found"})
            return 1
        if not initial or len(initial.upper()) > 7 or any(ord(c) < 32 for c in initial):
            emit({"ok": False, "error": "Choose a letter or symbol (up to seven characters)"})
            return 1
        account["initial"] = initial.upper()
        emit(snapshot_result(config, load_runtime_snapshot()))
        return 0


def set_notifications(account_id: str, value: str) -> int:
    with config_transaction() as config:
        account = find_account(config, account_id)
        if account is None:
            emit({"ok": False, "error": "Account not found"})
            return 1
        account["notifications"] = value.lower() in {"true", "1", "yes"}
        emit(snapshot_result(config, load_runtime_snapshot()))
        return 0


def set_interval(value: str) -> int:
    try:
        interval = max(1, min(60, int(value)))
    except ValueError:
        emit({"ok": False, "error": "Check interval must be between 1 and 60 minutes"})
        return 1
    with config_transaction() as config:
        config["poll_interval_minutes"] = interval
        emit(snapshot_result(config, load_runtime_snapshot()))
        return 0


def set_display_setting(name: str, value: str) -> int:
    with config_transaction() as config:
        if name == "language":
            language = value.lower()
            if language not in {"auto", "es", "en"}:
                emit({"ok": False, "error": "Language must be auto, es or en"})
                return 1
            config["language"] = language
            emit(snapshot_result(config, load_runtime_snapshot()))
            return 0
        if name == "flash-until-clicked":
            config["flash_until_clicked"] = value.lower() in {"true", "1", "yes"}
            emit(snapshot_result(config, load_runtime_snapshot()))
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
        emit(snapshot_result(config, load_runtime_snapshot()))
        return 0


def reorder_account(account_id: str, direction: str) -> int:
    with config_transaction() as config:
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
        emit(snapshot_result(config, load_runtime_snapshot()))
        return 0


def remove_account(account_id: str) -> int:
    with config_transaction() as config:
        account = find_account(config, account_id)
        if account is None:
            emit({"ok": False, "error": "Account not found"})
            return 1
        AlertStore(APP_DIR).remove(account_id)
        token_clear(account["email"])
        try:
            account_cache_path(account["email"]).unlink()
        except FileNotFoundError:
            pass
        config["accounts"] = [a for a in config["accounts"] if a.get("id") != account_id]
        emit(snapshot_result(config, load_runtime_snapshot()))
        return 0


def main(argv: list[str]) -> int:
    try:
        if argv == ['job']:
            line = sys.stdin.buffer.readline(8193)
            if len(line) > 8192:
                raise NotifierError('Invalid mail job request.')
            packet = json.loads(line)
            args = packet.get('args') if isinstance(packet, dict) else None
            if not isinstance(args, list) or not args or args[0] not in ('snapshot', 'update', 'poll-one', 'details', 'more-details', 'add-account') or len(args) > 3 or not all(isinstance(x, str) and len(x) <= 1024 and '\0' not in x for x in args):
                raise NotifierError('Invalid mail job request.')
            language = packet.get('language', 'en')
            if isinstance(language, str) and len(language) <= 16:
                NETWORK_CONTEXT.language = language
            OUTPUT.progress = lambda: emit({'type': 'progress'})
            return main(args)
        if argv == ["serve"]:
            from service import Service
            Service(sys.modules[__name__]).run()
            return 0
        if argv == ["watch"]:
            from service import watch
            watch(sys.modules[__name__])
            return 0
        if not argv or argv[0] == "snapshot":
            emit(build_snapshot())
            return 0
        command, *args = argv
        if command == 'poll-one' and len(args) == 2:
            return poll_one(args[0], args[1] == 'true')
        if command == "state" and not args:
            emit(snapshot_result(load_config(), load_runtime_snapshot()))
            return 0
        if command == "ack-alert" and len(args) == 2:
            AlertStore(APP_DIR).acknowledge(args[0], args[1])
            emit(snapshot_result(load_config(), load_runtime_snapshot()))
            return 0
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
        if command in ("details", "more-details") and len(args) == 1:
            return account_details(args[0], command == "more-details")
        if command == "remove-account" and len(args) == 1:
            return remove_account(args[0])
        if command == "add-account" and not args:
            authorize_account()
            emit(snapshot_result(load_config(), load_runtime_snapshot()))
            return 0
        emit({"ok": False, "error": "Unknown command"})
        return 2
    except (NotifierError, StorageError, OSError, ValueError, TypeError, KeyError) as error:
        emit({"ok": False, "error": str(error) if isinstance(error, (NotifierError, StorageError)) else "Operation failed; check configuration and desktop services."})
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


