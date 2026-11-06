import importlib.util
import io
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
from storage import StorageError
spec = importlib.util.spec_from_file_location('notifier_reliability', Path(__file__).resolve().parents[1] / 'helper/main.py')
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)


def edit_config(directory, key, value):
    h.APP_DIR = Path(directory); h.CONFIG_PATH = h.APP_DIR / 'config.json'
    with h.config_transaction() as config:
        config['accounts'][0][key] = value


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for name, value in {'APP_DIR': self.directory, 'CONFIG_PATH': self.directory/'config.json',
                            'SNAPSHOT_PATH': self.directory/'snapshot.json', 'SNAPSHOT_LOCK_PATH': self.directory/'snapshot.lock',
                            'OAUTH_CLIENT_PATH': self.directory/'oauth-client.json', 'CACHE_DIR': self.directory/'cache'}.items():
            patcher = patch.object(h, name, value); patcher.start(); self.addCleanup(patcher.stop)
        self.account = dict(id='a', email='a@example.invalid', initial='A', generation='test', enabled=True,
                            notifications=True, last_notification_ids=[], notification_baseline_set=True)
        h.save_config(dict(h.DEFAULT_CONFIG, accounts=[self.account]))

    def test_concurrent_config_updates_are_retained(self):
        workers = [multiprocessing.Process(target=edit_config, args=(self.directory, 'initial', 'TR')),
                   multiprocessing.Process(target=edit_config, args=(self.directory, 'notifications', False))]
        for p in workers: p.start()
        for p in workers: p.join(5); self.assertEqual(p.exitcode, 0)
        account = h.load_config()['accounts'][0]
        self.assertEqual(account['initial'], 'TR'); self.assertFalse(account['notifications'])

    def test_corrupt_config_is_preserved_and_cli_returns_json_error(self):
        h.CONFIG_PATH.write_text('{')
        with patch.object(h, 'emit') as emit:
            self.assertEqual(h.main(['state']), 1)
        self.assertFalse(emit.call_args.args[0]['ok']); self.assertEqual(h.CONFIG_PATH.read_text(), '{')

    def test_invalid_account_and_null_headers_are_controlled(self):
        h.CONFIG_PATH.write_text('{"accounts":[null]}')
        with self.assertRaises(StorageError): h.load_config()
        with patch.object(h, 'gmail_request', return_value={'payload': {'headers': None}}):
            with self.assertRaises(h.NotifierError): h.fetch_metadata('fake', ['a'])

    def test_repeated_or_invalid_pagination_is_bounded(self):
        with patch.object(h, 'gmail_request', return_value={'nextPageToken': 'same'}) as request:
            with self.assertRaises(h.NotifierError): h.list_unread_ids('fake')
        self.assertEqual(request.call_count, 2)
        with patch.object(h, 'gmail_request', return_value={'messages': [{'id': {}}]}):
            with self.assertRaises(h.NotifierError): h.list_unread_ids('fake')

    def test_huge_response_and_nonobject_json_are_rejected(self):
        for data in (b'[]', b'x' * (h.MAX_HTTP_RESPONSE_BYTES + 1)):
            with self.assertRaises(h.NotifierError): h.read_json_response(io.BytesIO(data))

    def test_501_messages_load_in_pages_and_reuse_headers(self):
        ids = [str(i) for i in range(501)]
        h.save_runtime_snapshot([dict(self.account, unread_ids=ids, unread_count=501, messages=[], details_ready=False)], 123)
        def metadata(_access, message_ids):
            self.assertLessEqual(len(message_ids), 50)
            return [{'id': i, 'from': 'Alice', 'subject': 'Hi'} for i in message_ids]
        with patch.object(h, 'token_lookup', return_value={}), \
                patch.object(h, 'refresh_access_token', return_value=('fake', {})), \
                patch.object(h, 'fetch_metadata', side_effect=metadata) as fetch, patch.object(h, 'emit'):
            self.assertEqual(h.account_details('a'), 0)
            self.assertEqual(h.load_runtime_snapshot()['accounts'][0]['details_loaded'], 50)
            h.account_details('a')
            self.assertEqual(fetch.call_args.args[1], [])
            h.account_details('a', more=True)
            self.assertEqual(h.load_runtime_snapshot()['accounts'][0]['details_loaded'], 100)
        self.assertEqual(h.load_runtime_snapshot()['accounts'][0]['unread_count'], 501)

    def test_pause_during_poll_prevents_late_alert(self):
        def ids(_):
            with h.config_transaction() as config: config['accounts'][0]['enabled'] = False
            return ['new']
        with patch.object(h, 'token_lookup', return_value={}), \
                patch.object(h, 'refresh_access_token', return_value=('fake', {})), \
                patch.object(h, 'list_unread_ids', side_effect=ids), \
                patch.object(h, 'fetch_metadata', return_value=[]), patch.object(h.desktop, 'notify') as notify:
            state = h.build_snapshot(force=True)
        notify.assert_not_called(); self.assertFalse(state['accounts'][0]['enabled'])

    def test_notification_failure_keeps_polled_count(self):
        with patch.object(h, 'token_lookup', return_value={}), \
                patch.object(h, 'refresh_access_token', return_value=('fake', {})), \
                patch.object(h, 'list_unread_ids', return_value=['new']), \
                patch.object(h, 'fetch_metadata', return_value=[]), \
                patch.object(h.desktop, 'notify', side_effect=RuntimeError('offline')):
            state = h.build_snapshot(force=True)
        self.assertEqual(state['accounts'][0]['unread_count'], 1)
        self.assertIn('notification_error', state['accounts'][0])

    def test_metadata_404_does_not_fail_entire_page(self):
        with patch.object(h, 'gmail_request', side_effect=[h.NotifierError('Gmail API returned HTTP 404.'), {}]):
            self.assertEqual(len(h.fetch_metadata('fake', ['a','b'])), 1)

    def test_retry_after_and_network_budget_are_enforced(self):
        import urllib.error
        from email.message import Message
        headers=Message();headers['Retry-After']='120'
        error=urllib.error.HTTPError('https://gmail.googleapis.com',429,'limit',headers,None)
        with patch.object(h,'safe_open',side_effect=error):
            with self.assertRaises(h.NotifierError) as raised: h.api_json(h.GMAIL_API+'/profile','fake')
        self.assertEqual(raised.exception.retry_after,120)
        with h.network_budget(seconds=-1):
            with self.assertRaises(h.NotifierError):h.request_timeout()

    def test_unexpected_network_endpoint_is_refused_before_connecting(self):
        import urllib.request
        with self.assertRaises(h.NotifierError):
            h.safe_open(urllib.request.Request('https://example.invalid/private'))

    def test_old_refresh_does_not_store_token_for_replaced_account(self):
        h.OAUTH_CLIENT_PATH.write_text('{"installed":{"client_id":"fake"}}')
        with patch.object(h,'token_request',return_value={'access_token':'fake'}), patch.object(h,'token_store') as store:
            with self.assertRaises(h.NotifierError):
                h.refresh_access_token(self.account['email'],{'refresh_token':'fake'},'old-generation')
        store.assert_not_called()

    def test_last_valid_config_backup_is_private(self):
        h.set_initial('a','TR')
        backup=h.APP_DIR/'config.backup.json'
        self.assertEqual(json.loads(backup.read_text())['accounts'][0]['initial'],'A')
        self.assertEqual(backup.stat().st_mode & 0o777,0o600)

    def test_invalid_state_timestamp_does_not_stop_polling(self):
        h.SNAPSHOT_PATH.write_text('{"checked_at":NaN,"accounts":[]}')
        self.assertIsNone(h.load_runtime_snapshot())

    def test_unrelated_oauth_request_does_not_cancel_valid_callback(self):
        import http.server,urllib.request,urllib.error,threading
        h.OAuthCallback.expected_state='expected';h.OAuthCallback.result={}
        server=http.server.HTTPServer(('127.0.0.1',0),h.OAuthCallback)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)+'/'
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(base+'?state=wrong',timeout=2)
            self.assertEqual(h.OAuthCallback.result,{})
            with urllib.request.urlopen(base+'?state=expected&code=fake',timeout=2) as result:
                self.assertEqual(result.status,200)
            self.assertEqual(h.OAuthCallback.result,{'code':'fake'})
        finally:
            server.shutdown();server.server_close();thread.join(2)
