import importlib.util
import multiprocessing
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HELPER = Path(__file__).resolve().parents[1] / "helper"
sys.path.insert(0, str(HELPER))
from alerts import AlertStore


def acknowledge_in_process(directory, event_id):
    AlertStore(Path(directory)).acknowledge("a", event_id)


class AlertsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = AlertStore(Path(self.temp.name))

    def observe(self, ids, until_clicked=True):
        self.store.observe("a", ids, until_clicked, 60)
        return self.store.read()["a"]

    def event(self):
        self.observe(["old"])
        return self.observe(["old", "new"])

    def test_first_poll_is_baseline(self):
        self.assertNotIn("event_id", self.observe(["old"]))

    def test_replacement_with_same_count_alerts(self):
        self.observe(["old"])
        self.assertIn("event_id", self.observe(["new"]))

    def test_reordering_ids_does_not_alert(self):
        event = self.event()
        self.assertEqual(event["event_id"], self.observe(["new", "old"])["event_id"])

    def test_all_monitors_see_acknowledgement(self):
        event = self.event()
        other = AlertStore(Path(self.temp.name))
        other.acknowledge("a", event["event_id"])
        self.assertTrue(self.store.read()["a"]["acknowledged"])

    def test_delayed_click_cannot_ack_new_mail(self):
        old = self.event()
        new = self.observe(["old", "new", "newer"])
        self.store.acknowledge("a", old["event_id"])
        self.assertEqual(new, self.store.read()["a"])
        self.assertFalse(new["acknowledged"])

    def test_click_before_arrival_does_not_silence_arrival(self):
        event = self.event()
        self.store.acknowledge("a", event["event_id"])
        self.assertFalse(self.observe(["old", "new", "newer"])["acknowledged"])

    def test_timed_deadline_does_not_restart_on_poll(self):
        self.observe([])
        with patch("alerts.time.time", return_value=100):
            event = self.observe(["new"], until_clicked=False)
        self.assertEqual(160000, event["expires_at"])
        self.assertEqual(event, self.observe(["new"], until_clicked=False))

    def test_empty_inbox_clears_alert(self):
        self.event()
        self.assertTrue(self.observe([])["acknowledged"])

    def test_paused_and_removed_accounts_not_visible(self):
        self.event()
        self.assertEqual({}, self.store.visible([{"id": "a", "enabled": False}]))
        self.assertEqual({}, self.store.visible([]))

    def test_removal_resets_baseline(self):
        self.event()
        self.store.remove("a")
        self.assertNotIn("event_id", self.observe(["old"]))

    def test_concurrent_clicks_are_atomic_and_idempotent(self):
        event = self.event()
        workers = [multiprocessing.Process(target=acknowledge_in_process,
                   args=(self.temp.name, event["event_id"])) for _ in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)
            self.assertEqual(0, worker.exitcode)
        self.assertTrue(self.store.read()["a"]["acknowledged"])
        self.assertEqual(0o600, self.store.path.stat().st_mode & 0o777)

    def test_state_and_ack_do_not_wait_for_gmail_lock_or_network(self):
        import fcntl
        spec = importlib.util.spec_from_file_location("notifier", HELPER / "main.py")
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        directory = Path(self.temp.name)
        event = self.event()
        config = dict(helper.DEFAULT_CONFIG, accounts=[{"id": "a", "email": "a@test"}])
        with patch.object(helper, "APP_DIR", directory), patch.object(helper, "CONFIG_PATH", directory / "config.json"), patch.object(helper, "SNAPSHOT_PATH", directory / "snapshot.json"), patch.object(helper, "OAUTH_CLIENT_PATH", directory / "oauth-client.json"), patch.object(helper, "api_json", side_effect=AssertionError("network")), patch.object(helper, "token_lookup", side_effect=AssertionError("secret service")), patch.object(helper, "emit") as emit:
            helper.save_config(config)
            with (directory / "snapshot.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(0, helper.main(["state"]))
                self.assertEqual(0, helper.main(["ack-alert", "a", event["event_id"]]))
            self.assertTrue(emit.call_args.args[0]["alerts"]["a"]["acknowledged"])


if __name__ == "__main__":
    unittest.main()
