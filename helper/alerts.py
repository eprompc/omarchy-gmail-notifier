"""Shared alert generations; never hold this lock during network requests."""

import fcntl
import json
import os
import secrets
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from storage import locked, read_object, atomic_write, StorageError


class AlertStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "alerts.json"

    def read(self):
        try:
            state = read_object(self.path) or {}
            return {key: value for key, value in state.items()
                    if isinstance(key, str) and isinstance(value, dict)
                    and isinstance(value.get('unread_ids'), list)
                    and len(value['unread_ids']) <= 10000
                    and all(isinstance(i, str) for i in value['unread_ids'])
                    and isinstance(value.get('started_at', 0), (int, float))
                    and isinstance(value.get('expires_at', 0), (int, float))}
        except StorageError:
            return {}

    @contextmanager
    def transaction(self):
        with locked(self.directory / 'alerts.lock'):
            value = self.read()
            previous = json.dumps(value, sort_keys=True)
            yield value
            if json.dumps(value, sort_keys=True) != previous:
                atomic_write(self.path, value)

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
        return {a["id"]: {key: value for key, value in state[a["id"]].items() if key != "unread_ids"} for a in accounts
                if a.get("enabled") is not False and a.get("id") in state}

