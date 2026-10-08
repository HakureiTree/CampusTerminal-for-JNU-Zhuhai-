# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gui.bridge.client import BackendClient


class ShutdownAdmissionTests(unittest.TestCase):
    def test_unavailable_or_unresponsive_backend_is_not_restarted_on_exit(self):
        for error in ("BackendUnavailable", "BackendTimeout", "BackendProtocolError"):
            with self.subTest(error=error):
                client = BackendClient(ROOT)
                failure = {"ok": False, "error": error}
                with patch.object(client, "status", return_value=failure), \
                        patch.object(client, "ensure_started") as start, \
                        patch.object(client, "_talk_py") as talk:
                    self.assertEqual(client.shutdown(True, "test-adapter"), failure)
                    start.assert_not_called()
                    talk.assert_not_called()

    def test_existing_backend_still_receives_handoff(self):
        client = BackendClient(ROOT)
        with patch.object(client, "status", return_value={"ok": True}), \
                patch.object(client, "ensure_started", return_value={"ok": True}), \
                patch.object(client, "_talk_py", return_value={"ok": True, "pending": True}) as talk:
            self.assertTrue(client.shutdown(True, "test-adapter")["pending"])
            self.assertEqual(talk.call_args.args[0], {
                "id": 4, "method": "shutdown", "handoff": True, "adapter": "test-adapter"})

    def test_exit_without_handoff_never_starts_backend(self):
        client = BackendClient(ROOT)
        with patch.object(client, "ensure_started") as start, \
                patch.object(client, "_talk_py", return_value={"ok": True}), \
                patch.object(client, "wait_until_stopped", return_value=True) as wait:
            self.assertTrue(client.shutdown()["ok"])
            start.assert_not_called()
            wait.assert_called()

    def test_wait_until_stopped_without_known_pid_does_not_block(self):
        client = BackendClient(ROOT)
        self.assertTrue(client.wait_until_stopped())


if __name__ == "__main__":
    unittest.main(verbosity=2)
