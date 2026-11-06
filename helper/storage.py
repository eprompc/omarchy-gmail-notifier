"""Small owner-only atomic stores. Lock order: config -> alerts; never network."""
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


class StorageError(Exception):
    pass


def private_directory(path):
    path = Path(path)
    if path.is_symlink():
        raise StorageError("State directory must not be a symbolic link.")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.getuid():
        raise StorageError("State directory belongs to another user.")
    path.chmod(0o700)


@contextmanager
def locked(path):
    private_directory(path.parent)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as stream:
        os.chmod(path, 0o600)
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def read_object(path, missing=None, limit=16 * 1024 * 1024):
    try:
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("file too large")
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("expected an object")
        return value
    except FileNotFoundError:
        return missing
    except (ValueError, UnicodeError) as error:
        raise StorageError(f"Invalid {path.name}; preserve this file and restore a valid backup.") from error


def atomic_write(path, value):
    private_directory(path.parent)
    fd, name = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
