# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SCRIPT = ROOT / "core/handoff/Invoke-OriginalHandoffStage.ps1"
POWERSHELL = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="CampusTerminal-executor-test-")
        self.root = Path(self.temp.name)
        for folder in ("src", "replacement", "logs", "report"):
            (self.root / folder).mkdir()
        fixture = ROOT / "tests/handoff/FakePlatform.psm1"
        shutil.copyfile(fixture, self.root / "src/INodeController.psm1")
        shutil.copyfile(fixture, self.root / "replacement/OriginalService.psm1")
        shutil.copyfile(REPO / "src/Runtime.psm1", self.root / "src/Runtime.psm1")
        shutil.copyfile(REPO / "replacement/TrialWorkflow.psm1", self.root / "replacement/TrialWorkflow.psm1")
        self.fixture = {"Adapter": str(uuid.uuid4()), "Mac": "020000000001", "RunId": uuid.uuid4().hex,
                        "Failure": "", "Client": False, "StartedUtc": "2026-09-17T00:00:00Z"}
        self.write("fixture.json", self.fixture)
        self.write("config.json", {"AdapterGuid": self.fixture["Adapter"], "Recovery": {"Enabled": True, "Mode": "GuiRestart"}})
        self.write("logs/control.json", {"TaskName": "ReInode-Observer", "RunId": self.fixture["RunId"]})
        self.write("report/context.json", {"Root": str(self.root), "Adapter": self.fixture["Adapter"],
                                          "Mac": self.fixture["Mac"], "Marker": "owned-test-marker"})
        self.pause = self.root / "logs/pause-recovery.signal"
        self.pause.write_text("owned-test-marker", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, value):
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")

    def stage(self, name, ok=True):
        process = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
                                  "-Stage", name, "-ContextPath", str(self.root / "report/context.json")],
                                 capture_output=True, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
        report_path = self.root / "report" / (name + ".json")
        self.assertTrue(report_path.exists(), process.stderr.decode("utf-8", "replace"))
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        self.assertEqual(report["Ok"], ok, (report, process.stderr.decode("utf-8", "replace")))
        self.assertEqual(process.returncode, 0 if ok else 1)
        return report

    def prepare_client(self):
        self.stage("Preflight")
        self.stage("RestoreService")
        self.assertFalse(self.stage("ClientExists")["Value"])
        self.stage("StartClient")
        self.assertTrue(self.stage("WaitClient")["Value"])

    def test_production_executor_success_with_isolated_platform(self):
        self.prepare_client()
        self.stage("Authentication")
        self.stage("Network")
        evidence = json.loads((self.root / "report/network-evidence.json").read_text(encoding="utf-8-sig"))
        self.assertTrue(evidence["Verified"])
        self.assertEqual(len(evidence["Rounds"]), 2)
        self.stage("ResumeMonitor")
        self.assertFalse(self.pause.exists())
        actions = (self.root / "actions.log").read_text().splitlines()
        self.assertEqual(actions, ["service", "start", "authentication", "network", "resume"])

    def test_failed_verification_or_monitor_preserves_pause(self):
        self.prepare_client()
        for failure, stage in (("authentication", "Authentication"), ("network", "Network"), ("monitor", "ResumeMonitor")):
            with self.subTest(stage=stage):
                saved = json.loads((self.root / "fixture.json").read_text(encoding="utf-8-sig"))
                saved["Failure"] = failure
                self.write("fixture.json", saved)
                self.stage(stage, ok=False)
                self.assertEqual(self.pause.read_text(encoding="utf-8"), "owned-test-marker")

    def test_foreign_pause_blocks_before_platform_action(self):
        self.pause.write_text("foreign-owner", encoding="utf-8")
        report = self.stage("RestoreService", ok=False)
        self.assertEqual(report["Error"], "MaintenanceOwnershipLost")
        self.assertFalse((self.root / "actions.log").exists())
        self.assertEqual(self.pause.read_text(), "foreign-owner")

    def test_takeover_stops_service_normally_before_authentication(self):
        self.prepare_client()
        self.stage("StopOriginal")
        self.assertFalse(self.stage("ClientExists")["Value"])
        self.assertTrue(self.pause.exists())
        self.assertEqual((self.root / "actions.log").read_text().splitlines(), ["service", "start", "normal-exit", "service"])

    def test_takeover_uses_real_exit_interface_when_service_leaves_gui(self):
        self.prepare_client()
        saved = json.loads((self.root / "fixture.json").read_text(encoding="utf-8-sig"))
        saved["KeepClientOnStop"] = True
        self.write("fixture.json", saved)
        self.stage("StopOriginal")
        self.assertFalse(self.stage("ClientExists")["Value"])
        self.assertEqual((self.root / "actions.log").read_text().splitlines(), ["service", "start", "normal-exit", "service"])

    def test_stop_original_service_allows_leftover_gui(self):
        self.prepare_client()
        saved = json.loads((self.root / "fixture.json").read_text(encoding="utf-8-sig"))
        saved["KeepClientOnStop"] = True
        self.write("fixture.json", saved)
        self.stage("StopOriginalService")
        self.assertIn("close-gui", (self.root / "actions.log").read_text().splitlines())

    def test_menu_failure_does_not_stop_the_working_original_service(self):
        self.prepare_client()
        saved = json.loads((self.root / "fixture.json").read_text(encoding="utf-8-sig"))
        saved["Failure"] = "normal-exit"
        self.write("fixture.json", saved)
        result = self.stage("StopOriginal", ok=False)
        self.assertEqual(result["Error"], "PopupChanged")
        self.assertEqual((self.root / "actions.log").read_text().splitlines(), ["service", "start", "normal-exit"])
        self.assertTrue(self.pause.exists())

    def test_service_authentication_can_precede_gui_start(self):
        self.prepare_client()
        saved = json.loads((self.root / "fixture.json").read_text(encoding="utf-8-sig"))
        online = datetime.now(timezone.utc)
        saved["OnlineUtc"] = online.isoformat()
        saved["StartedUtc"] = (online + timedelta(seconds=7)).isoformat()
        self.write("fixture.json", saved)
        self.stage("ClientExists")
        self.stage("Authentication")
        evidence = json.loads((self.root / "report/authentication-evidence.json").read_text(encoding="utf-8-sig"))
        self.assertTrue(evidence["Verified"])
        self.assertIn("Since", evidence)
        stage = json.loads((self.root / "report/Authentication.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(stage["Stage"], "Authentication")

    def test_existing_instance_reuses_only_matching_verified_authentication(self):
        self.prepare_client()
        online = datetime.now(timezone.utc) - timedelta(minutes=5)
        saved = json.loads((self.root / "fixture.json").read_text(encoding="utf-8-sig"))
        saved.update(OnlineUtc=online.isoformat(), StartedUtc=(online + timedelta(seconds=7)).isoformat())
        self.write("fixture.json", saved)
        self.stage("ClientExists")
        state = json.loads((self.root / "report/original-state.json").read_text(encoding="utf-8-sig"))
        history = self.root / "logs/campus-terminal/prior-success"
        history.mkdir(parents=True)
        context = json.loads((self.root / "report/context.json").read_text())
        previous = {**state, "AuthenticationSinceUtc": (online - timedelta(seconds=2)).isoformat()}
        proof = {"Verified": True, "IdentityVerified": True, "ObservedProcessId": 1234, "OnlineTime": online.isoformat()}
        for name, value in (("result.json", {"Succeeded": True, "Stage": "Complete"}),
                            ("context.json", context), ("authentication-evidence.json", proof)):
            self.write("logs/campus-terminal/prior-success/" + name, value)
        self.write("logs/campus-terminal/prior-success/original-state.json", {**previous, "ClientStartedUtc": "wrong-instance"})
        self.stage("Authentication", ok=False)
        self.write("logs/campus-terminal/prior-success/original-state.json", previous)
        self.stage("Authentication")
        updated = json.loads((self.root / "report/original-state.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(updated["BaselineSource"], str(history))
        self.assertEqual(updated["AuthenticationSinceUtc"], previous["AuthenticationSinceUtc"])

    def test_service_replaced_gui_must_stabilize_before_identity_is_saved(self):
        self.prepare_client()
        saved = json.loads((self.root / "fixture.json").read_text(encoding="utf-8-sig"))
        saved.update(ClientReads=0, ReplaceAfterReads=5, ReplacementStartedUtc="2026-09-17T00:00:07Z")
        self.write("fixture.json", saved)
        self.assertTrue(self.stage("WaitClient")["Value"])
        state = json.loads((self.root / "report/original-state.json").read_text(encoding="utf-8-sig"))
        saved = json.loads((self.root / "fixture.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(state["ClientId"], 5678)
        self.assertEqual(state["ClientStartedUtc"], saved["ReplacementStartedUtc"])
        self.assertGreaterEqual(saved["ClientReads"], 25)
        self.assertEqual((self.root / "actions.log").read_text().splitlines(), ["service", "start"])

    def test_orphaned_helper_publishes_identity_but_never_touches_platform(self):
        process = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(SCRIPT), "-Stage", "RestoreService", "-ContextPath", str(self.root / "report/context.json"),
            "-CallerProcessId", str(os.getpid()), "-CallerStartedUtc", "2000-01-01T00:00:00Z"],
            capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertNotEqual(process.returncode, 0)
        records = list((self.root / "report").glob("helper-*.json"))
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_text(encoding="utf-8-sig"))
        self.assertEqual(record["Stage"], "RestoreService")
        self.assertFalse((self.root / "actions.log").exists())
        self.assertEqual(self.pause.read_text(), "owned-test-marker")

    def test_occlusion_uses_log_and_address_evidence(self):
        self.prepare_client()
        saved = json.loads((self.root / "fixture.json").read_text(encoding="utf-8-sig"))
        saved["Failure"] = "occlusion"
        self.write("fixture.json", saved)
        self.stage("Authentication")
        evidence = json.loads((self.root / "report/authentication-evidence.json").read_text(encoding="utf-8-sig"))
        self.assertTrue(evidence["Verified"])
        self.assertEqual(evidence["Method"], "LogAndAddress")
        self.assertIn("log-evidence", (self.root / "actions.log").read_text().splitlines())


if __name__ == "__main__":
    unittest.main(verbosity=2)
