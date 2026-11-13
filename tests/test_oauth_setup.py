"""Setup guidance must not reset existing accounts or launch OAuth on an update."""
import copy
import json
import os
import socket
import threading
import time
import unittest
from unittest.mock import patch
import test_upgrade
from service import Service, socket_path

h = test_upgrade.h


class OAuthSetupTests(unittest.TestCase):
    def setUp(self):
        test_upgrade.UpgradeTests.setUp(self)

    def assert_check_is_read_only(self, expected):
        config = h.CONFIG_PATH.read_bytes()
        client = h.OAUTH_CLIENT_PATH.read_bytes() if h.OAUTH_CLIENT_PATH.is_file() else None
        secrets = copy.deepcopy(self.secrets.values)
        with patch.object(h, 'authorize_account', side_effect=AssertionError('No automatic OAuth')), \
                patch.object(h.webbrowser, 'open', side_effect=AssertionError('No browser for check')), \
                patch.object(h, 'token_lookup', side_effect=AssertionError('Check must not read tokens')), \
                patch.object(h, 'token_clear', side_effect=AssertionError('No credential deletion')), \
                patch.object(h, 'emit') as emit:
            for _ in range(3):
                self.assertEqual(h.main(['check-setup']), 0)
                state = emit.call_args.args[0]
                self.assertEqual(state['oauth_status'], expected)
                self.assertEqual(state['oauth_ready'], expected == 'ready')
                self.assertEqual([a['id'] for a in state['accounts']], [a['id'] for a in self.config['accounts']])
                self.assertNotIn('client_secret', json.dumps(state))
        self.assertEqual(h.CONFIG_PATH.read_bytes(), config)
        self.assertEqual(self.secrets.values, secrets)
        self.assertEqual(self.secrets.clear_calls, [])
        if client is not None:
            self.assertEqual(h.OAUTH_CLIENT_PATH.read_bytes(), client)
        else:
            self.assertFalse(h.OAUTH_CLIENT_PATH.exists())

    def test_missing_client_keeps_all_existing_accounts_and_tokens(self):
        h.OAUTH_CLIENT_PATH.unlink()
        self.assert_check_is_read_only('missing')

    def test_valid_existing_client_is_reused_without_authorization_or_rewrite(self):
        self.assert_check_is_read_only('ready')

    def test_invalid_client_remains_intact_and_gets_help_status(self):
        for contents in ('{', '[]', '{"web":{"client_id":"synthetic"}}', '{"installed":{"client_id":7}}'):
            h.OAUTH_CLIENT_PATH.write_text(contents)
            self.assert_check_is_read_only('invalid')

    def test_client_read_error_is_generic_without_credential_disclosure(self):
        with patch.object(h, 'read_oauth_client', side_effect=PermissionError('PRIVATE CLIENT CONTENT')):
            self.assert_check_is_read_only('unreadable')

    def test_nonregular_or_huge_client_cannot_block_setup_status(self):
        h.OAUTH_CLIENT_PATH.unlink()
        os.mkfifo(h.OAUTH_CLIENT_PATH, mode=0o600)
        self.assertEqual(h.oauth_client_status(), 'invalid')
        h.OAUTH_CLIENT_PATH.unlink()
        h.OAUTH_CLIENT_PATH.write_bytes(b'x'*(1024*1024+1))
        self.assertEqual(h.oauth_client_status(), 'invalid')

    def test_restoring_original_client_refreshes_existing_grant_without_new_oauth(self):
        old = dict(self.token, expires_at=0)
        self.secrets.values[self.address] = json.dumps(old)
        h.OAUTH_CLIENT_PATH.unlink()
        self.assert_check_is_read_only('missing')
        h.OAUTH_CLIENT_PATH.write_text(self.oauth)
        with patch.object(h, 'authorize_account', side_effect=AssertionError('Restore must reuse grant')), \
                patch.object(h.webbrowser, 'open', side_effect=AssertionError('No new consent')), \
                patch.object(h, 'token_request', return_value={'access_token':'renewed', 'expires_in':3600}) as request:
            access, _token = h.refresh_access_token(self.address, h.token_lookup(self.address), 'legacy')
        self.assertEqual(access, 'renewed')
        self.assertEqual(request.call_args.args[0]['client_id'], 'synthetic-client')
        self.assertEqual(request.call_args.args[0]['grant_type'], 'refresh_token')
        self.assertEqual(h.OAUTH_CLIENT_PATH.read_text(), self.oauth)
        self.assertEqual(self.secrets.clear_calls, [])

    def test_missing_client_hint_does_not_block_usable_existing_access_token(self):
        h.OAUTH_CLIENT_PATH.unlink()
        with patch.object(h, 'authorize_account', side_effect=AssertionError('No automatic OAuth')), \
                patch.object(h, 'token_request', side_effect=AssertionError('Fresh token remains usable')), \
                patch.object(h, 'list_unread_ids', return_value=['synthetic-message']):
            state = h.build_snapshot(force=True)
        self.assertTrue(state['ok'])
        self.assertEqual(state['oauth_status'], 'missing')
        self.assertEqual(state['accounts'][0]['unread_count'], 1)
        self.assertEqual(self.secrets.clear_calls, [])

    def test_service_check_is_local_even_when_network_queue_is_busy(self):
        service = Service(h)
        service.jobs.put((['update'], None, None))
        with patch.object(h, 'authorize_account', side_effect=AssertionError('No OAuth')), \
                patch.object(h, 'build_snapshot', side_effect=AssertionError('No network poll')):
            service.request({'args':['check-setup'], 'request_id':1}, None)
        self.assertEqual(service.jobs.qsize(), 1)
        self.assertEqual(h.OAUTH_CLIENT_PATH.read_text(), self.oauth)

    def test_running_service_detects_saved_client_without_restart_or_new_consent(self):
        h.OAUTH_CLIENT_PATH.unlink()
        config = h.load_config()
        for account in config['accounts']:
            account['enabled'] = False
        h.save_config(config)
        service = Service(h)
        with patch.dict(os.environ, {'XDG_RUNTIME_DIR':str(self.directory)}), \
                patch.object(h, 'authorize_account', side_effect=AssertionError('No automatic OAuth')):
            thread = threading.Thread(target=service.run, daemon=True)
            thread.start()
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(4)
            try:
                path = socket_path(h)
                deadline = time.monotonic()+3
                while not path.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                client.connect(str(path))
                with client.makefile('rb') as stream:
                    self.assertEqual(json.loads(stream.readline())['oauth_status'], 'missing')
                    # A file manager/editor may expose an incomplete JSON before
                    # finishing its copy. It must recover on the next file change.
                    h.OAUTH_CLIENT_PATH.write_text('{')
                    self.assertEqual(json.loads(stream.readline())['oauth_status'], 'invalid')
                    h.OAUTH_CLIENT_PATH.write_text(self.oauth)
                    deadline = time.monotonic()+5
                    while True:
                        client.settimeout(max(0.1, deadline-time.monotonic()))
                        packet = json.loads(stream.readline())
                        if packet['oauth_status'] == 'ready':
                            break
                        self.assertLess(time.monotonic(), deadline)
            finally:
                client.close()
                service.stop.set()
                thread.join(3)
        self.assertEqual(self.secrets.clear_calls, [])
