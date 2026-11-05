# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise production PowerShell discovery and handoff guards without touching iNode."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"


class OriginalInstallationTests(unittest.TestCase):
    def run_suite(self, suite):
        with tempfile.TemporaryDirectory(prefix="CampusTerminal-installation-") as folder:
            process = subprocess.run(
                [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(ROOT / "tests/handoff/InstallationChecks.ps1"),
                 "-RepoRoot", str(ROOT.parent), "-FixtureRoot", folder, "-Suite", suite],
                capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(process.returncode, 0,
                             (process.stdout + process.stderr).decode("utf-8", "replace"))
            self.assertIn(f"PASS {suite}:".encode(), process.stdout)

    def test_command_parsing_and_rejection(self):
        self.run_suite("Parsing")

    def test_discovery_versions_files_and_running_image(self):
        self.run_suite("Discovery")

    def test_service_transition_identity_and_safety(self):
        self.run_suite("Transitions")

    def test_client_identity_and_launch_without_shortcuts(self):
        self.run_suite("Client")


if __name__ == "__main__":
    unittest.main(verbosity=2)
