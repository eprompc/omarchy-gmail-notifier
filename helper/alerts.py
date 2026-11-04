"""Shared alert generations; never hold this lock during network requests."""

import fcntl
import json
import os
import secrets
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


class AlertStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "alerts.json"

    def read(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @contextmanager
    def transaction(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.directory / "alerts.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            value = self.read()
            yield value
            fd, name = tempfile.mkstemp(prefix=".alerts-", dir=self.directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(value, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, self.path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)

    def observe(self, account_id, unread_ids, until_clicked, duration):
        with self.transaction() as state:
            previous = state.get(account_id)
            ids = list(dict.fromkeys(unread_ids))
            new_ids = set(ids) - set((previous or {}).get("unread_ids", []))
            entry = dict(previous or {})
            entry["unread_ids"] = ids
            # The first successful observation establishes a baseline.
            if previous is not None and new_ids:
                now = int(time.time() * 1000)
                entry.update(event_id=secrets.token_hex(16), started_at=now,
                             expires_at=0 if until_clicked else now + duration * 1000,
                             acknowledged=False)
            if not ids:
                entry["acknowledged"] = True
            state[account_id] = entry

    def acknowledge(self, account_id, event_id):
        with self.transaction() as state:
            entry = state.get(account_id, {})
            # A delayed click must never acknowledge a newer event.
            if event_id and entry.get("event_id") == event_id:
                entry["acknowledged"] = True

    def remove(self, account_id):
        with self.transaction() as state:
            state.pop(account_id, None)

    def visible(self, accounts):
        state = self.read()
        return {a["id"]: state[a["id"]] for a in accounts
                if a.get("enabled") is not False and a.get("id") in state}
