import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
spec = importlib.util.spec_from_file_location('notifier_notifications', Path(__file__).resolve().parents[1] / 'helper/main.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class NotificationPrivacyTests(unittest.TestCase):
    def account(self):
        return dict(email='private@example.invalid', initial='TR', last_notification_ids=[], notification_baseline_set=True)

    def test_private_text_is_delivered_in_process(self):
        account = self.account()
        with patch.object(helper, 'fetch_metadata', return_value=[
                {'from': 'Alice <alice@example.invalid>', 'subject': 'Private subject'}]), \
                patch.object(helper.desktop, 'notify', return_value=42) as notify, \
                patch('subprocess.run', side_effect=AssertionError('No child process')):
            helper.notify_new(account, ['m1'], 'fake', 'es')
        notify.assert_called_once_with('Nuevo email en la cuenta (TR)', '<b>Alice</b>\nPrivate subject')
        self.assertNotIn('private@example.invalid', str(notify.call_args))
        self.assertNotIn('alice@example.invalid', str(notify.call_args))

    def test_sender_and_subject_markup_are_escaped(self):
        with patch.object(helper, 'fetch_metadata', return_value=[
                {'from': '"<img>" <alice@example.invalid>', 'subject': '<a href="https://example.invalid">secret</a>'}]), \
                patch.object(helper.desktop, 'notify') as notify:
            helper.notify_new(self.account(), ['m1'], 'fake')
        body = notify.call_args.args[1]
        self.assertNotIn('<img>', body)
        self.assertNotIn('<a ', body)
        self.assertIn('&lt;img&gt;', body)

    def test_disabled_alerts_do_not_read_headers_or_notify(self):
        account = self.account(); account['notifications'] = False
        with patch.object(helper, 'fetch_metadata') as metadata, patch.object(helper.desktop, 'notify') as notify:
            helper.notify_new(account, ['m1'], 'fake')
        metadata.assert_not_called(); notify.assert_not_called()

    def test_delivery_failure_does_not_discard_new_count_or_repeat_event(self):
        account = self.account()
        with patch.object(helper.desktop, 'notify', side_effect=RuntimeError('no bus')):
            helper.deliver_notification(account, ['m1'], [], 'en')
        self.assertIn('notification_error', account)
        self.assertEqual(account['last_notification_ids'], ['m1'])
        with patch.object(helper.desktop, 'notify') as notify:
            helper.deliver_notification(account, ['m1'], [], 'en')
        notify.assert_not_called()
