"""One private per-user service; persistent widget clients carry JSON on stdin/socket.

Network work runs on one bounded queue. Local edits and acknowledgement never wait
for Gmail. State is reread after each operation and published in a single ordered
stream with an epoch/revision, rather than applying competing process outputs.
"""
import fcntl
import json
import os
import queue
import select
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from storage import private_directory

MAX_LINE = 8192
MAX_STATE = 16 * 1024 * 1024


def socket_path(helper):
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    base = Path(runtime) / 'omarchy-gmail-notifier' if runtime else helper.APP_DIR / 'runtime'
    private_directory(base)
    return base / 'service-v030.sock'


class Service:
    def __init__(self, helper):
        self.h = helper
        self.clients = {}
        self.lock = threading.RLock()
        self.jobs = queue.Queue(maxsize=32)
        self.epoch = uuid.uuid4().hex
        self.revision = 0
        self.language = 'en'
        self.last_state = None
        self.last_activity = time.monotonic()
        self.stop = threading.Event()
        self.poll_pending = False
        self.config_mtime = None

    def send(self, client, packet):
        try:
            client.sendall((json.dumps(packet, ensure_ascii=False) + '\n').encode())
        except OSError:
            self.clients.pop(client, None)

    def publish(self, force=False):
        with self.lock:
            try:
                state = self.h.snapshot_result(self.h.load_config(), self.h.load_runtime_snapshot())
            except Exception as error:
                state = {'ok': False, 'error': str(error) if isinstance(error, self.h.StorageError)
                         else 'Could not read local Gmail state.'}
            encoded = json.dumps(state, sort_keys=True)
            if encoded == self.last_state and not force:
                return
            self.last_state = encoded
            self.revision += 1
            packet = dict(state, type='state', epoch=self.epoch, revision=self.revision)
            for client in list(self.clients):
                self.send(client, packet)

    def call(self, args):
        result = {}
        self.h.OUTPUT.sink = result.update
        self.h.NETWORK_CONTEXT.language = self.language
        try:
            self.h.main(args)
        except Exception:
            result = {'ok': False, 'error': 'Operation failed; check desktop services and configuration.'}
        finally:
            self.h.OUTPUT.sink = None
        return result

    def execute(self, args, client=None, request_id=None):
        result = self.call(args)
        with self.lock:
            self.publish()
            if client in self.clients:
                self.send(client, {'type': 'result', 'request_id': request_id,
                                   'ok': result.get('ok', False), 'error': result.get('error', '')})

    def worker(self):
        while not self.stop.is_set():
            try:
                args, client, request_id = self.jobs.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self.execute(args, client, request_id)
            finally:
                if args == ['snapshot']:
                    self.poll_pending = False
                self.jobs.task_done()

    def request(self, packet, client):
        request_id = packet.get('request_id')
        if not isinstance(request_id, int) or not 0 <= request_id <= 2147483647:
            raise ValueError('Invalid request identifier')
        args = packet.get('args')
        if not isinstance(args, list) or not args or len(args) > 4 or not all(
                isinstance(x, str) and len(x) <= 1024 and '\0' not in x for x in args):
            raise ValueError('Invalid action')
        allowed = {'ack-alert', 'details', 'more-details', 'update', 'set-enabled', 'set-initial',
                   'set-notifications', 'set-interval', 'set-display', 'move-account', 'remove-account',
                   'add-account', 'cancel-auth', 'language'}
        if args[0] not in allowed:
            raise ValueError('Unsupported action')
        if args[0] == 'language' and len(args) == 2:
            if len(args[1]) <= 16 and args[1].replace('-', '').isalnum():
                self.language = args[1]
            return
        if args[0] == 'cancel-auth':
            self.h.AUTH_CANCELLED.set()
            return
        if args[0] in {'details', 'more-details', 'update', 'add-account'}:
            try:
                self.jobs.put_nowait((args, client, request_id))
            except queue.Full:
                with self.lock:
                    self.send(client, {'type': 'result', 'request_id': request_id,
                                       'ok': False, 'error': 'Too many queued operations; retry shortly.'})
        else:
            self.execute(args, client, request_id)

    def client(self, client):
        client.settimeout(5)
        try:
            peer = client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            if struct.unpack('3i', peer)[1] != os.getuid():
                return
            with self.lock:
                if len(self.clients) >= 32:
                    return
                self.clients[client] = True
                self.publish(force=True)
            client.settimeout(5)
            with client.makefile('rb', buffering=0) as stream:
                while not self.stop.is_set():
                    if not select.select([client], [], [], 1)[0]:
                        continue
                    line = stream.readline(MAX_LINE + 1)
                    if not line:
                        break
                    if len(line) > MAX_LINE:
                        break
                    try:
                        packet = json.loads(line)
                        if not isinstance(packet, dict):
                            raise ValueError()
                        self.request(packet, client)
                    except (ValueError, TypeError):
                        break
        except OSError:
            pass
        finally:
            with self.lock:
                self.clients.pop(client, None)
                self.last_activity = time.monotonic()
            client.close()

    def run(self):
        path = socket_path(self.h)
        with (path.parent / 'service.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            path.unlink(missing_ok=True)
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(path))
            path.chmod(0o600)
            listener.listen(16)
            listener.settimeout(1)
            threading.Thread(target=self.worker, daemon=True).start()
            try:
                while not self.stop.is_set():
                    try:
                        client, _ = listener.accept()
                        threading.Thread(target=self.client, args=(client,), daemon=True).start()
                    except socket.timeout:
                        pass
                    with self.lock:
                        active = bool(self.clients)
                    if active:
                        try:
                            modified = self.h.CONFIG_PATH.stat().st_mtime_ns
                        except OSError:
                            modified = 0
                        if modified != self.config_mtime:
                            self.config_mtime = modified
                            self.publish()
                    if active and not self.poll_pending and self.jobs.empty():
                        try:
                            config = self.h.load_config()
                            snapshot = self.h.load_runtime_snapshot() or {}
                            due = time.time() - snapshot.get('checked_at', 0) >= config['poll_interval_minutes'] * 60
                            if due and any(a['enabled'] for a in config['accounts']):
                                self.poll_pending = True
                                self.jobs.put_nowait((['snapshot'], None, None))
                        except Exception:
                            self.publish()
                    if not active and self.jobs.unfinished_tasks == 0 and time.monotonic() - self.last_activity > 60:
                        break
            finally:
                self.stop.set()
                listener.close()
                path.unlink(missing_ok=True)


def watch(helper):
    path = socket_path(helper)
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    for attempt in range(30):
        try:
            connection.connect(str(path))
            break
        except OSError:
            if attempt == 0:
                subprocess.Popen([sys.executable, str(Path(helper.__file__).resolve()), 'serve'],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
            time.sleep(0.1)
    else:
        raise RuntimeError('Shared Gmail service could not start.')
    incoming = bytearray()
    outgoing = bytearray()
    with connection:
        while True:
            ready, _, _ = select.select([connection, sys.stdin.buffer], [], [])
            if connection in ready:
                data = connection.recv(65536)
                if not data:
                    return
                incoming.extend(data)
                if len(incoming) > MAX_STATE:
                    return
                while b'\n' in incoming:
                    line, _, rest = incoming.partition(b'\n')
                    incoming = bytearray(rest)
                    sys.stdout.buffer.write(line + b'\n')
                    sys.stdout.buffer.flush()
            if sys.stdin.buffer in ready:
                chunk = os.read(sys.stdin.fileno(), MAX_LINE)
                if not chunk:
                    return
                outgoing.extend(chunk)
                if len(outgoing) > MAX_LINE:
                    return
                while b'\n' in outgoing:
                    line, _, rest = outgoing.partition(b'\n')
                    outgoing = bytearray(rest)
                    connection.sendall(line + b'\n')
