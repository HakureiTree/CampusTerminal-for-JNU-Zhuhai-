# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gui.bridge import store


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.patches = [patch.object(store, "APP_DIR", self.directory),
                        patch.object(store, "SETTINGS_PATH", self.directory / "ui-settings.dpapi"),
                        patch.object(store, "SECRET_PATH", self.directory / "password.dpapi")]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def test_round_trip_across_process_without_plaintext(self):
        store.save({"account": "fake-student-123", "save_password": True,
                    "adapter_id": "fake-guid", "auto_connect": True})
        store.save_password("fake-password-456")
        for path in self.directory.iterdir():
            content = path.read_bytes()
            self.assertNotIn(b"fake-student-123", content)
            self.assertNotIn(b"fake-password-456", content)
        code = ("from gui.bridge import store; "
                "assert store.load()['account']=='fake-student-123'; "
                "assert store.load_password()=='fake-password-456'")
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                env={**os.environ, "CAMPUS_TERMINAL_STATE": str(self.directory)},
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_settings_migrated_after_encrypted_commit(self):
        legacy = self.directory / "ui-settings.json"
        legacy.write_text(json.dumps({"account": "legacy-test", "save_account": True}), encoding="utf-8-sig")
        self.assertEqual(store.load()["account"], "legacy-test")
        self.assertFalse(legacy.exists())
        self.assertTrue(store.SETTINGS_PATH.exists())

    def test_failed_commit_preserves_previous_state(self):
        store.save({"account": "before"})
        before = store.SETTINGS_PATH.read_bytes()
        with patch.object(Path, "replace", side_effect=OSError("test write failure")):
            with self.assertRaises(OSError):
                store.save({"account": "after"})
        self.assertEqual(store.SETTINGS_PATH.read_bytes(), before)
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_corruption_is_visible_and_never_overwritten_on_load(self):
        store.SETTINGS_PATH.write_bytes(b"invalid ciphertext")
        with self.assertRaises(OSError):
            store.load()
        self.assertEqual(store.SETTINGS_PATH.read_bytes(), b"invalid ciphertext")

    def test_clear_saved_password_and_unsaved_account(self):
        store.save_password("test-secret")
        store.clear_password()
        self.assertEqual(store.load_password(), "")
        store.save({"account": "unsaved", "save_account": False, "password": "must-not-save"})
        self.assertEqual(store.load()["account"], "")
        self.assertNotIn("password", store.load())

    def test_blank_password_does_not_erase_existing_secret(self):
        store.save_password("keep-this-secret")
        store.save_password("")
        self.assertEqual(store.load_password(), "keep-this-secret")


if __name__ == "__main__":
    unittest.main()
