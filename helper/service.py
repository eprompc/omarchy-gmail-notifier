"""One private per-user service; persistent widget clients carry JSON on stdin/socket.

Network work runs on one bounded queue. Local edits and acknowledgement never wait
for Gmail. State is reread after each operation and published in a single ordered
stream with an epoch/revision, rather than applying competing process outputs.
"""
import fcntl
import hashlib
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
from jobs import run_job

MAX_LINE = 8192
MAX_STATE = 16 * 1024 * 1024


def socket_path(helper):
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    base = Path(runtime) / 'omarchy-gmail-notifier' if runtime else helper.APP_DIR / 'runtime'
    private_directory(base)
    # A source update must start the matching backend immediately, even if the
    # old daemon is still inside its idle grace period. Personal state stays put.
    source = Path(helper.__file__).resolve().parent
    digest = hashlib.sha256()
    for file in sorted(source.glob('*.py')):
        digest.update(file.name.encode('utf-8'))
        digest.update(file.read_bytes())
    return base / ('service-' + digest.hexdigest()[:16] + '.sock')


class Peer:
    """A slow/dead monitor must never hold the shared state/network lock."""
    def __init__(self, connection):
        self.connection = connection
        self.outgoing = queue.Queue(maxsize=4)
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self.write, daemon=True)
        self.thread.start()

    def send(self, data):
        if self.closed.is_set():
            return False
        try:
            self.outgoing.put_nowait(data)
            return True
        except queue.Full:
            self.close()
            return False

    def write(self):
        try:
            while not self.closed.is_set():
                try:
                    data = self.outgoing.get(timeout=0.25)
                except queue.Empty:
                    continue
                self.connection.sendall(data)
        except OSError:
            pass
        finally:
            self.close()

    def close(self):
        if not self.closed.is_set():
            self.closed.set()
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class Service:
    def __init__(self, helper):
        self.h = helper
        self.clients = {}
        self.lock = threading.RLock()
        self.jobs = queue.Queue(maxsize=1)
        self.epoch = uuid.uuid4().hex
        self.revision = 0
        self.language = 'en'
        self.last_state = None
        self.last_activity = time.monotonic()
        self.stop = threading.Event()
        self.network_busy = False
        self.network_operation = ''
        self.network_error = ''
        self.cancel_network = threading.Event()
        self.last_poll = None
        self.retry_poll_at = 0
        self.config_mtime = None

    def send(self, client, packet):
        try:
            data = (json.dumps(packet, ensure_ascii=False) + '\n').encode('utf-8', 'backslashreplace')
            peer = self.clients.get(client)
            if isinstance(peer, Peer):
                if not peer.send(data):
                    self.clients.pop(client, None)
            else:
                client.sendall(data)
        except OSError:
            self.clients.pop(client, None)

    def publish(self, force=False):
        with self.lock:
            try:
                state = self.h.snapshot_result(self.h.load_config(), self.h.load_runtime_snapshot())
            except Exception as error:
                state = {'ok': False, 'error': str(error) if isinstance(error, self.h.StorageError)
                         else 'Could not read local Gmail state.'}
            state.update(network_busy=self.network_busy, network_operation=self.network_operation,
                         network_error=self.network_error)
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

    def run_network(self, args):
        if args[0] not in ('update', 'snapshot'):
            return run_job(self.h.__file__, args, 400 if args[0] == 'add-account' else 70,
                           progress=self.publish, cancelled=self.cancel_network, language=self.language)
        accounts = self.h.load_config()['accounts']
        failed = False
        for account in accounts:
            if not account['enabled']:
                continue
            if self.cancel_network.is_set():
                return {'ok': False, 'error': 'Mail operation was cancelled.'}
            # A separate killable process per account prevents a blocked socket,
            # keyring or notification from freezing all accounts behind it.
            result = run_job(self.h.__file__, ['poll-one', account['id'], 'true' if args[0] == 'update' else 'false'],
                             70, cancelled=self.cancel_network, language=self.language)
            if self.cancel_network.is_set():
                return {'ok': False, 'error': 'Mail operation was cancelled.'}
            if not result.get('ok'):
                failed = True
                # A normal account failure already persisted its exponential
                # backoff. Only supervisor/transport failures need recording.
                if 'accounts' not in result:
                    self.h.record_poll_failure(account['id'], result.get('error', 'Mail query failed.'))
            self.publish()
        self.h.finish_poll()
        return {'ok': not failed, 'poll_completed': True, 'error': 'Some accounts could not be updated; polling will retry.' if failed else ''}

    def execute(self, args, client=None, request_id=None):
        network = args[0] in {'snapshot', 'update', 'details', 'more-details', 'add-account'}
        result = self.run_network(args) if network else self.call(args)
        with self.lock:
            if network:
                self.network_busy = False
                self.network_operation = ''
                self.network_error = '' if result.get('ok') else result.get('error', 'Mail query failed.')
                if args[0] in ('snapshot', 'update'):
                    if result.get('poll_completed'):
                        self.last_poll = time.monotonic()
                        self.retry_poll_at = 0
                    else:
                        self.retry_poll_at = time.monotonic() + 30
            self.publish()
            if client in self.clients:
                self.send(client, {'type': 'result', 'request_id': request_id,
                                   'ok': result.get('ok', False), 'error': result.get('error', '')})

    def poll_due(self):
        config = self.h.load_config()
        if not any(a['enabled'] for a in config['accounts']):
            return False
        now = time.monotonic()
        if self.last_poll is None:
            snapshot = self.h.load_runtime_snapshot() or {}
            age = max(0, min(config['poll_interval_minutes'] * 60,
                             time.time() - snapshot.get('checked_at', 0)))
            self.last_poll = now - age
        return now >= self.retry_poll_at and now - self.last_poll >= config['poll_interval_minutes'] * 60

    def submit_network(self, args, client=None, request_id=None):
        with self.lock:
            if self.network_busy:
                if client in self.clients:
                    self.send(client, {'type': 'result', 'request_id': request_id,
                                       'ok': False, 'code': 'busy', 'error': 'A mail query is already running.'})
                return False
            self.cancel_network.clear()
            self.network_busy = True
            self.network_operation = args[0]
            try:
                self.jobs.put_nowait((args, client, request_id))
            except queue.Full:
                self.network_busy = True
                if client in self.clients:
                    self.send(client, {'type': 'result', 'request_id': request_id,
                                       'ok': False, 'code': 'busy', 'error': 'A mail query is already queued.'})
                return False
            self.publish()
            return True

    def schedule_poll(self):
        with self.lock:
            if self.network_busy:
                return False
            try:
                due = self.poll_due()
            except Exception:
                self.publish()
                return False
            return self.submit_network(['snapshot']) if due else False

    def worker(self):
        while not self.stop.is_set():
            try:
                args, client, request_id = self.jobs.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self.execute(args, client, request_id)
            except Exception:
                # A failed query or publication must not kill the sole worker.
                with self.lock:
                    # execute() may have published idle before failing. A new
                    # client request can already have reserved the next job.
                    self.network_busy = not self.jobs.empty()
                    if not self.network_busy:
                        self.network_operation = ''
                    self.network_error = 'Mail operation failed; automatic polling will retry.'
                    self.retry_poll_at = time.monotonic() + 30
                    try:
                        self.publish()
                        if client in self.clients:
                            self.send(client, {'type': 'result', 'request_id': request_id,
                                               'ok': False, 'error': self.network_error})
                    except Exception:
                        pass
            finally:
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
                   'add-account', 'cancel-auth', 'language', 'check-setup'}
        if args[0] not in allowed:
            raise ValueError('Unsupported action')
        if args[0] == 'language' and len(args) == 2:
            if len(args[1]) <= 16 and args[1].replace('-', '').isalnum():
                self.language = args[1]
            return
        if args[0] == 'cancel-auth':
            if self.network_operation == 'add-account':
                self.cancel_network.set()
            return
        if args[0] in {'details', 'more-details', 'update', 'add-account'}:
            # An overdue poll has priority over repeated panel/detail requests.
            if args[0] in ('details', 'more-details'):
                self.schedule_poll()
            self.submit_network(args, client, request_id)
        else:
            self.execute(args, client, request_id)

    def client(self, client):
        client.settimeout(5)
        channel = None
        try:
            peer = client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            if struct.unpack('3i', peer)[1] != os.getuid():
                return
            with self.lock:
                if len(self.clients) >= 32:
                    return
                channel = Peer(client)
                self.clients[client] = channel
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
            if channel is not None:
                channel.close()
            client.close()

    def run(self):
        path = socket_path(self.h)
        with path.with_suffix('.lock').open('a') as lock:
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
                        modified = []
                        for file in (self.h.CONFIG_PATH, self.h.OAUTH_CLIENT_PATH):
                            try:
                                stat = file.stat()
                                modified.append((stat.st_mtime_ns, stat.st_size, stat.st_ino, stat.st_mode))
                            except OSError:
                                modified.append(None)
                        if modified != self.config_mtime:
                            self.config_mtime = modified
                            self.publish()
                    if active:
                        self.schedule_poll()
                    if not active:
                        self.cancel_network.set()
                    if not active and self.jobs.unfinished_tasks == 0 and time.monotonic() - self.last_activity > 60:
                        break
            finally:
                self.stop.set()
                self.cancel_network.set()
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
