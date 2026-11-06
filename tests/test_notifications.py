import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "helper"))
spec = importlib.util.spec_from_file_location("gmail_helper", ROOT / "helper" / "main.py")
helper = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(helper)


class NotificationPrivacyTests(unittest.TestCase):
    def test_notification_shows_sender_and_subject_without_mailbox(self):
        account = {
            "email": "private-account@example.com",
            "initial": "TR",
            "last_notification_ids": [],
            "notification_baseline_set": True,
        }
        calls = []

        def fake_run(command, **_kwargs):
            calls.append(command)

        with patch.object(helper, "fetch_metadata", return_value=[{
            "from": "Alice Example <alice@example.com>",
            "subject": "Confidential project details",
        }]), patch.object(helper.subprocess, "run", side_effect=fake_run):
            helper.notify_new(account, ["message-1"], "token", "es")

        self.assertEqual(calls[0][0], "omarchy-notification-send")
        self.assertIn("--transient", calls[0])
        self.assertEqual(calls[0][-2:], [
            "Nuevo email en la cuenta (TR)",
            "<b>Alice Example</b>\nConfidential project details",
        ])
        self.assertNotIn("private-account@example.com", calls[0])
        self.assertNotIn("alice@example.com", calls[0])
        self.assertNotIn("notify-send", calls[0])

    def test_sender_markup_is_escaped(self):
        account = {
            "email": "private-account@example.com",
            "initial": "TR",
            "last_notification_ids": [],
            "notification_baseline_set": True,
        }
        calls = []

        with patch.object(helper, "fetch_metadata", return_value=[{
            "from": '"<img src=\'https://example.invalid/tracker\'>" <sender@example.com>',
            "subject": "Secret",
        }]), patch.object(helper.subprocess, "run", side_effect=lambda command, **_kwargs: calls.append(command)):
            helper.notify_new(account, ["message-1"], "token", "es")

        body = calls[0][-1]
        self.assertNotIn("<img", body)
        self.assertIn("&lt;img", body)


if __name__ == "__main__":
    unittest.main()
