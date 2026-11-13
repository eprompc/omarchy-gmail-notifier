"""Regressions for cross-monitor bursts, account deadlines and periodic recovery."""
import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch
import test_service
from jobs import run_job
from service import Peer

h = test_service.h


class RefreshSchedulingTests(unittest.TestCase):
    def setUp(self):
        test_service.ServiceTests.setUp(self)
        for name, value in {'SNAPSHOT_LOCK_PATH': self.directory/'snapshot.lock',
                            'CACHE_DIR': self.directory/'cache'}.items():
            p = patch.object(h, name, value)
            p.start()
            self.addCleanup(p.stop)

    def enabled_accounts(self):
        config = h.load_config()
        config['accounts'] = [dict(id=k, email=k+'@example.invalid', initial=k.upper(),
                                   enabled=True, notifications=False) for k in ('a', 'b')]
        h.save_config(config)
        return h.load_config()['accounts']

    def test_second_refresh_from_another_monitor_does_not_queue(self):
        clients = [test_service.FakeClient(), test_service.FakeClient()]
        self.service.clients = {c: True for c in clients}
        for i in range(100):
            self.service.request({'args': ['update'], 'request_id': i}, clients[i % 2])
        self.assertEqual(self.service.jobs.qsize(), 1)
        rejected = [m for c in clients for m in c.messages if m.get('code') == 'busy']
        self.assertEqual(len(rejected), 99)

    def test_busy_state_is_shared_before_the_network_request_runs(self):
        clients = [test_service.FakeClient(), test_service.FakeClient()]
        self.service.clients = {c: True for c in clients}
        self.service.request({'args': ['update'], 'request_id': 1}, clients[0])
        for client in clients:
            states = [m for m in client.messages if m.get('type') == 'state']
            self.assertTrue(states[-1]['network_busy'])
        self.assertEqual(clients[0].messages, clients[1].messages)

    def test_busy_state_clears_and_counts_publish_after_completed_update(self):
        accounts = self.enabled_accounts()
        clients = [test_service.FakeClient(), test_service.FakeClient()]
        self.service.clients = {c: True for c in clients}
        self.service.submit_network(['update'], clients[0], 1)
        def query(_script, args, *_pos, **_kw):
            previous = h.load_runtime_snapshot()
            runtime = h.merge_runtime_accounts(h.load_config(), previous)
            for account in runtime:
                if account['id'] == args[1]:
                    account.update(unread_count=0, unread_ids=[], messages=[])
            h.save_runtime_snapshot(runtime, 0)
            return {'ok': True}
        h.save_runtime_snapshot([dict(a, unread_count=3, unread_ids=['x','y','z']) for a in accounts], 0)
        with patch('service.run_job', side_effect=query):
            self.service.execute(['update'], clients[0], 1)
        for client in clients:
            states = [m for m in client.messages if m.get('type') == 'state']
            self.assertFalse(states[-1]['network_busy'])
            self.assertEqual([a['unread_count'] for a in states[-1]['accounts']], [0, 0])
        self.assertTrue(clients[0].messages[-1]['ok'])

    def test_worker_exception_does_not_disable_all_future_polls(self):
        completed = threading.Event()
        count = []
        def execute(*args):
            count.append(1)
            if len(count) == 1:
                raise RuntimeError('synthetic broadcast failure')
            completed.set()
        self.service.execute = execute
        thread = threading.Thread(target=self.service.worker, daemon=True)
        thread.start()
        try:
            self.service.jobs.put((['update'], None, None))
            self.service.jobs.put((['snapshot'], None, None))
            self.assertTrue(completed.wait(1))
        finally:
            self.service.stop.set()
            thread.join(2)

    def test_timeout_of_first_account_preserves_count_and_still_queries_second(self):
        accounts = self.enabled_accounts()
        h.save_runtime_snapshot([dict(a, unread_count=2, unread_ids=['x','y']) for a in accounts], 0)
        with patch('service.run_job', side_effect=[{'ok': False, 'error': 'Mail operation timed out.'}, {'ok': True}]) as job:
            result = self.service.run_network(['update'])
        self.assertFalse(result['ok'])
        self.assertTrue(result['poll_completed'])
        self.assertEqual([c.args[1] for c in job.call_args_list], [['poll-one','a','true'], ['poll-one','b','true']])
        snapshot = h.load_runtime_snapshot()
        self.assertEqual(snapshot['accounts'][0]['unread_count'], 2)
        self.assertIn('timed out', snapshot['accounts'][0]['last_error'])
        self.assertNotIn('last_error', snapshot['accounts'][1])
        self.assertGreater(snapshot['checked_at'], 0)

    def test_account_rate_limit_backoff_is_not_replaced_by_supervisor(self):
        self.enabled_accounts()
        with patch('service.run_job', return_value={'ok': False, 'accounts': [], 'error': 'retry'}), \
                patch.object(h, 'record_poll_failure') as record:
            self.service.run_network(['snapshot'])
        record.assert_not_called()

    def test_disabling_all_monitors_cancels_sweep_without_marking_accounts_failed(self):
        self.enabled_accounts()
        def cancel(*_args, **_kwargs):
            self.service.cancel_network.set()
            return {'ok': False, 'error': 'cancelled'}
        with patch('service.run_job', side_effect=cancel) as job, \
                patch.object(h, 'record_poll_failure') as record:
            result = self.service.run_network(['update'])
        self.assertFalse(result['ok'])
        self.assertEqual(job.call_count, 1)
        record.assert_not_called()

    def test_periodic_poll_resumes_after_manual_update_and_waits_full_interval(self):
        self.enabled_accounts()
        with patch('service.time.monotonic', return_value=100), \
                patch.object(self.service, 'run_network', return_value={'ok': True, 'poll_completed': True}):
            self.service.execute(['update'])
        with patch('service.time.monotonic', return_value=219):
            self.assertFalse(self.service.schedule_poll())
        with patch('service.time.monotonic', return_value=221):
            self.assertTrue(self.service.schedule_poll())
        self.assertEqual(self.service.jobs.get_nowait()[0], ['snapshot'])

    def test_failed_poll_is_retried_after_backoff_without_manual_restart(self):
        self.enabled_accounts()
        self.service.last_poll = 0
        with patch('service.time.monotonic', return_value=200), \
                patch.object(self.service, 'run_network', return_value={'ok': False, 'error': 'temporary failure'}):
            self.service.execute(['snapshot'])
        self.assertFalse(self.service.network_busy)
        with patch('service.time.monotonic', return_value=229):
            self.assertFalse(self.service.schedule_poll())
        with patch('service.time.monotonic', return_value=231):
            self.assertTrue(self.service.schedule_poll())

    def test_repeated_detail_requests_cannot_starve_overdue_poll(self):
        self.enabled_accounts()
        self.service.last_poll = 0
        with patch('service.time.monotonic', return_value=200):
            self.service.request({'args': ['details', 'a'], 'request_id': 1}, None)
        self.assertEqual(self.service.jobs.get_nowait()[0], ['snapshot'])
        self.assertTrue(self.service.network_busy)

    def test_local_settings_and_acknowledgement_remain_usable_while_polling(self):
        self.service.submit_network(['update'])
        self.service.request({'args': ['set-initial','a','TR'], 'request_id': 1}, None)
        self.assertEqual(h.load_config()['accounts'][0]['initial'], 'TR')
        self.assertTrue(self.service.network_busy)

    def test_pause_or_remove_during_sweep_does_not_restore_old_configuration(self):
        self.enabled_accounts()
        def query(_script, args, *_pos, **_kw):
            if args[1] == 'a':
                with h.config_transaction() as config:
                    config['accounts'][1]['enabled'] = False
                    config['accounts'][1]['initial'] = 'NEW'
            # poll-one always rereads current configuration, even if the service
            # took the original list before a pause/removal.
            with patch.object(h, 'token_lookup', side_effect=h.NotifierError('offline')), patch.object(h, 'emit'):
                h.poll_one(args[1], True)
            return {'ok': True}
        with patch('service.run_job', side_effect=query):
            self.service.run_network(['update'])
        config = h.load_config()
        self.assertFalse(config['accounts'][1]['enabled'])
        self.assertEqual(config['accounts'][1]['initial'], 'NEW')
        self.assertFalse(h.load_runtime_snapshot()['accounts'][1]['enabled'])

    def test_poll_failure_keeps_settings_and_oauth_client_unchanged(self):
        self.enabled_accounts()
        h.OAUTH_CLIENT_PATH.write_text('{"installed":{"client_id":"synthetic"}}')
        config = h.CONFIG_PATH.read_bytes()
        oauth = h.OAUTH_CLIENT_PATH.read_bytes()
        with patch('service.run_job', return_value={'ok': False, 'error': 'timeout'}), \
                patch.object(h, 'token_clear') as clear:
            self.service.run_network(['update'])
        self.assertEqual(h.CONFIG_PATH.read_bytes(), config)
        self.assertEqual(h.OAUTH_CLIENT_PATH.read_bytes(), oauth)
        clear.assert_not_called()

    def test_external_snapshot_lock_cannot_freeze_supervisor_bookkeeping(self):
        from storage import locked, StorageError
        with locked(h.SNAPSHOT_LOCK_PATH):
            start = time.monotonic()
            with self.assertRaises(StorageError):
                h.finish_poll()
            self.assertLess(time.monotonic()-start, 2)
        # Releasing an external CLI's lock leaves the service usable.
        h.finish_poll()
        self.assertGreater(h.load_runtime_snapshot()['checked_at'], 0)

    def test_slow_monitor_does_not_block_other_monitor_or_shared_lock(self):
        server, remote = socket.socketpair()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
        peer = Peer(server)
        healthy = test_service.FakeClient()
        self.service.clients = {server: peer, healthy: True}
        try:
            peer.send(b'x' * (1024 * 1024))
            for _ in range(5):
                peer.send(b'x' * 1024)
            done = threading.Event()
            thread = threading.Thread(target=lambda: (self.service.publish(), done.set()), daemon=True)
            thread.start()
            self.assertTrue(done.wait(1), 'a blocked receiver held the shared lock')
            thread.join(1)
            self.assertTrue(healthy.messages)
        finally:
            peer.close()
            server.close()
            remote.close()
            peer.thread.join(1)

    def test_real_monitor_connections_share_busy_then_idle_after_one_query(self):
        entered = threading.Event()
        release = threading.Event()
        def query(_args):
            entered.set()
            release.wait(3)
            return {'ok': True, 'poll_completed': True}
        self.service.run_network = query
        worker = threading.Thread(target=self.service.worker, daemon=True)
        worker.start()
        connections = []
        def read_until(stream, predicate):
            for _ in range(10):
                packet = json.loads(stream.readline())
                if predicate(packet):
                    return packet
            self.fail('expected shared state was not received')
        try:
            for _ in range(2):
                server, client = socket.socketpair()
                client.settimeout(3)
                thread = threading.Thread(target=self.service.client, args=(server,), daemon=True)
                stream = client.makefile('rb')
                connections.append((client, stream, thread))
                thread.start()
                read_until(stream, lambda p: p['type'] == 'state')
            connections[0][0].sendall(b'{"args":["update"],"request_id":1}\n')
            self.assertTrue(entered.wait(1))
            for _client, stream, _thread in connections:
                read_until(stream, lambda p: p.get('network_busy') is True)
            connections[1][0].sendall(b'{"args":["update"],"request_id":1}\n')
            rejected = read_until(connections[1][1], lambda p: p['type'] == 'result')
            self.assertEqual(rejected['code'], 'busy')
            self.assertEqual(self.service.jobs.qsize(), 0)
            release.set()
            for _client, stream, _thread in connections:
                read_until(stream, lambda p: p['type'] == 'state' and p.get('network_busy') is False)
        finally:
            release.set()
            self.service.stop.set()
            for client, stream, thread in connections:
                stream.close()
                client.close()
                thread.join(2)
            worker.join(2)


class JobSupervisorTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.script = Path(self.temp.name)/'synthetic_worker.py'
        self.script.write_text('''import json,signal,sys,time
packet=json.loads(sys.stdin.readline())
command=packet['args'][0]
if command=='hang':
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    time.sleep(30)
if command=='bad':
    print('not json',flush=True)
elif command=='crash':
    sys.exit(1)
else:
    print(json.dumps({'ok':True,'argv':sys.argv[1:],'echo':packet['args'],'language':packet['language']}),flush=True)
''')

    def test_hung_process_is_killed_and_next_job_succeeds(self):
        start = time.monotonic()
        result = run_job(self.script, ['hang'], 0.2)
        self.assertLess(time.monotonic()-start, 2.5)
        self.assertFalse(result['ok'])
        self.assertIn('timed out', result['error'])
        self.assertTrue(run_job(self.script, ['fine'], 10)['ok'])

    def test_private_request_and_live_language_travel_in_pipe_only(self):
        result = run_job(self.script, ['synthetic@example.invalid','PRIVATE SUBJECT'], 10, language='es')
        self.assertEqual(result['argv'], ['job'])
        self.assertEqual(result['echo'], ['synthetic@example.invalid','PRIVATE SUBJECT'])
        self.assertEqual(result['language'], 'es')

    def test_invalid_or_incomplete_child_response_is_recoverable(self):
        for command in ('bad', 'crash'):
            self.assertFalse(run_job(self.script, [command], 10)['ok'])
        self.assertTrue(run_job(self.script, ['fine'], 10)['ok'])

    def test_cancelled_auth_or_query_terminates_child(self):
        cancelled = threading.Event()
        cancelled.set()
        result = run_job(self.script, ['hang'], 2, cancelled=cancelled)
        self.assertFalse(result['ok'])
        self.assertIn('cancelled', result['error'])

    def test_real_job_entry_accepts_private_protocol_without_new_authorization(self):
        # No accounts, no Google/keyring access. Exercise the production entry
        # point in an isolated home without reading personal configuration.
        import subprocess
        with patch.dict('os.environ', {'HOME': self.temp.name}):
            p = subprocess.run([sys.executable, str(Path(h.__file__)), 'job'],
                               input=json.dumps({'args':['update'],'language':'es'}), text=True,
                               capture_output=True, timeout=10)
        self.assertEqual(p.returncode, 0)
        self.assertTrue(json.loads(p.stdout.splitlines()[-1])['ok'])
        self.assertEqual(p.stderr, '')
