# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui.bridge import startup
from gui.bridge.startup import has_silent, show_main_on_launch


class StartupTests(unittest.TestCase):
    def xml(self):
        return ('<?xml version="1.0" encoding="UTF-16"?>'
                '<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
                '<Principals><Principal><RunLevel>HighestAvailable</RunLevel></Principal></Principals>'
                f'<Actions><Exec><Command>{startup.pythonw()}</Command>'
                f'<Arguments>"{startup.ROOT / "run.py"}" --silent</Arguments></Exec></Actions></Task>')

    def test_oem_stdout_with_utf16_declaration_and_real_utf16(self):
        for encoding in ("oem", "utf-16"):
            result = SimpleNamespace(returncode=0, stdout=self.xml().encode(encoding))
            with patch.object(startup.subprocess, "run", return_value=result):
                self.assertTrue(startup.enabled())

    def test_silent_autostart_does_not_reveal_or_fallback_early(self):
        self.assertTrue(has_silent(r'"C:\客户端\开源暨珠有线网络终端.exe" --silent'))
        self.assertFalse(has_silent(r'"C:\客户端\开源暨珠有线网络终端.exe"'))
        self.assertFalse(show_main_on_launch(True, True, False))
        self.assertFalse(show_main_on_launch(True, False, False))
        self.assertTrue(show_main_on_launch(True, False, True))
        self.assertTrue(show_main_on_launch(False, True, False))

    def test_wrong_command_or_disabled_task_rejected(self):
        for xml in (self.xml().replace("run.py", "unrelated.py"),
                    self.xml().replace("</Task>", "<Settings><Enabled>false</Enabled></Settings></Task>")):
            with patch.object(startup.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=xml.encode("oem"))):
                self.assertFalse(startup.enabled())


if __name__ == "__main__":
    unittest.main()
