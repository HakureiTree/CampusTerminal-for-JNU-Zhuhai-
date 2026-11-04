# SPDX-License-Identifier: GPL-3.0-or-later
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gui.bridge import resources, trace

KEYS = {"gdi", "user", "private_mb", "visible", "tray_flashing"}


class SampleResourcesTests(unittest.TestCase):
    def test_returns_the_full_key_set_with_integers_and_booleans(self):
        sample = resources.sample_resources(True, False)
        self.assertEqual(set(sample), KEYS)
        for key in ("gdi", "user", "private_mb"):
            self.assertIs(type(sample[key]), int)
            self.assertGreaterEqual(sample[key], 0)
        self.assertIs(sample["visible"], True)
        self.assertIs(sample["tray_flashing"], False)

    def test_visibility_flags_are_coerced_to_bool(self):
        sample = resources.sample_resources(1, 0)
        self.assertIs(sample["visible"], True)
        self.assertIs(sample["tray_flashing"], False)
        sample = resources.sample_resources(0, 1)
        self.assertIs(sample["visible"], False)
        self.assertIs(sample["tray_flashing"], True)

    def test_gui_resource_queries_use_the_gdi_and_user_flags(self):
        with patch.object(resources, "_gui_resources", side_effect=[17, 23]) as gui:
            sample = resources.sample_resources(True, False)
        self.assertEqual((sample["gdi"], sample["user"]), (17, 23))
        self.assertEqual([call.args[0] for call in gui.call_args_list],
                         [resources.GDI_RESOURCES, resources.USER_RESOURCES])

    def test_os_and_process_failures_become_zero_instead_of_raising(self):
        with patch.object(resources, "_gui_resources", side_effect=OSError("no user32")), \
                patch.object(resources, "_process", side_effect=RuntimeError("no psutil")):
            sample = resources.sample_resources(True, True)
        self.assertEqual(sample["gdi"], 0)
        self.assertEqual(sample["user"], 0)
        self.assertEqual(sample["private_mb"], 0)
        self.assertIs(sample["visible"], True)
        self.assertIs(sample["tray_flashing"], True)

    def test_missing_win32_handles_become_zero(self):
        with patch.object(resources, "_user32", None):
            self.assertEqual(resources._gui_resources(resources.GDI_RESOURCES), 0)
        with patch.object(resources, "_kernel32", None):
            self.assertEqual(resources._gui_resources(resources.USER_RESOURCES), 0)

    def test_psutil_process_failure_becomes_zero(self):
        with patch.object(resources.psutil, "Process", side_effect=OSError("denied")):
            sample = resources.sample_resources(False, False)
        self.assertEqual(sample["private_mb"], 0)

    def test_private_memory_prefers_private_bytes(self):
        class Info:
            private = 123 * 1024 * 1024
            rss = 999 * 1024 * 1024

        class Process:
            def memory_info(self):
                return Info()

        self.assertEqual(resources.sample_resources(False, False, process=Process())["private_mb"], 123)

    def test_private_memory_falls_back_to_rss(self):
        class Info:
            rss = 300 * 1024 * 1024

        class Process:
            def memory_info(self):
                return Info()

        self.assertEqual(resources.sample_resources(False, False, process=Process())["private_mb"], 300)


class TraceSchemaTests(unittest.TestCase):
    def test_gui_resources_event_keeps_the_sampled_fields(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(trace, "_directory", return_value=Path(directory)):
            trace.emit("gui_resources", reason="periodic", gdi=41, user=52,
                       private_mb=63, visible=True, tray_flashing=False)
            rows = [json.loads(line) for line in
                    (Path(directory) / "gui-events.jsonl").read_text(encoding="utf-8").splitlines()]
        row = rows[-1]
        self.assertEqual(row["stage"], "gui_resources")
        self.assertEqual(row["reason"], "periodic")
        self.assertEqual((row["gdi"], row["user"], row["private_mb"]), (41, 52, 63))
        self.assertIs(row["visible"], True)
        self.assertIs(row["tray_flashing"], False)


if __name__ == "__main__":
    unittest.main()
