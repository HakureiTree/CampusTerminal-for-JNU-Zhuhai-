# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui.bridge.auto_policy import (
    MAX_AUTO_FAILURES, SILENT_RETRY_SECONDS, adapter_identity_changed, adapter_key, apply_connect_outcome,
    connection_due, counts_as_auto_failure, may_resume_owned_session, resume_block_reason, same_adapter,
    should_retry_auto_connect, should_stop_auto_connect, silent_retry_wait, want_auto_connect)


class AutoPolicyTests(unittest.TestCase):
    def test_policy_has_no_calendar_cutoff(self):
        import inspect
        self.assertEqual(list(inspect.signature(connection_due).parameters),
                         ["previous_up", "current_up", "enabled", "manual_stop"])

    def test_login_link_restore_and_manual_stop(self):
        self.assertTrue(connection_due(False, True, True, False))
        self.assertFalse(connection_due(True, True, True, False))
        self.assertFalse(connection_due(False, True, True, True))
        self.assertFalse(connection_due(False, True, False, False))
        self.assertFalse(connection_due(True, False, True, False))

    def test_retry_missing_backend_and_bounded_auth_reject(self):
        self.assertTrue(should_retry_auto_connect("BackendMissing", True, False, False))
        self.assertTrue(should_retry_auto_connect("LinkUnavailable", True, False, False))
        self.assertTrue(should_retry_auto_connect("AuthenticationRejected", True, False, False, 0))
        self.assertTrue(should_retry_auto_connect("AuthenticationRejected", True, False, False, 4))
        self.assertFalse(should_retry_auto_connect("AuthenticationRejected", True, False, False, 5))
        self.assertFalse(should_retry_auto_connect("ElevationCancelled", True, False, False))
        self.assertFalse(should_retry_auto_connect("BackendMissing", True, True, False))
        self.assertFalse(should_retry_auto_connect("BackendMissing", False, False, False))
        self.assertFalse(should_retry_auto_connect("BackendMissing", True, False, True))
        self.assertTrue(should_retry_auto_connect("BackendStartTimeout", True, False, False))
        self.assertFalse(should_retry_auto_connect("AuthenticationRejected", True, False, False, 0, True))
        self.assertFalse(should_retry_auto_connect("AlternativeNetworkPath", True, False, False))
        self.assertFalse(should_retry_auto_connect("ReconnectAttemptsExhausted", True, False, False, 0))

    def test_five_auth_failures_then_manual_only_until_success(self):
        self.assertEqual(MAX_AUTO_FAILURES, 5)
        count, stopped, yielded, notice, suppress = 0, False, False, None, False
        for step in range(4):
            count, stopped, yielded, notice, suppress = apply_connect_outcome(
                "AuthenticationRejected", "error", count, False, False)
            self.assertEqual(count, step + 1)
            self.assertFalse(stopped)
            self.assertTrue(suppress)
            self.assertEqual(notice, "AuthenticationRejected")
        count, stopped, yielded, notice, suppress = apply_connect_outcome(
            "AuthenticationRejected", "error", count, False, False)
        self.assertEqual(count, 5)
        self.assertTrue(stopped)
        self.assertFalse(suppress)
        self.assertEqual(notice, "AutoReconnectLimit")
        count, stopped, yielded, notice, suppress = apply_connect_outcome(
            "online", "online", count, False, False)
        self.assertEqual((count, stopped, yielded, notice), (0, False, False, None))

    def test_usb_share_yields_without_consuming_failure_budget(self):
        count, stopped, yielded, notice, suppress = apply_connect_outcome(
            "AuthenticationRejected", "error", 2, False, True)
        self.assertEqual(count, 2)
        self.assertTrue(stopped and yielded)
        self.assertEqual(notice, "AlternativeNetworkPath")
        self.assertFalse(suppress)
        self.assertTrue(should_stop_auto_connect("AlternativeNetworkPath", 2, True))
        self.assertTrue(counts_as_auto_failure("ProtocolFailed"))
        self.assertFalse(counts_as_auto_failure("AlternativeNetworkPath"))
        count, stopped, yielded, notice, suppress = apply_connect_outcome(
            None, "online", 2, False, True)
        self.assertEqual(count, 2)
        self.assertTrue(stopped and yielded)
        self.assertEqual(notice, "AlternativeNetworkPath")
        self.assertFalse(suppress)

    def test_capped_retry_waits_ten_minutes_unless_usb_is_up(self):
        self.assertEqual(SILENT_RETRY_SECONDS, 600)
        due, left = silent_retry_wait(600, True, False, True, False, False)
        self.assertFalse(due)
        self.assertEqual(left, 599)
        due, left = silent_retry_wait(1, True, False, True, False, False)
        self.assertTrue(due)
        self.assertEqual(left, 600)
        due, left = silent_retry_wait(30, True, True, True, False, False)
        self.assertFalse(due)
        self.assertEqual(left, 30)
        due, left = silent_retry_wait(1, True, False, True, True, False)
        self.assertFalse(due)

    def test_only_a_slow_retry_on_the_owned_adapter_may_resume(self):
        low = "325b38cc-bfd3-4628-beac-acbc8f520ed4"
        upper = low.upper()
        other = "325b38cc-bfd3-4628-beac-acbc8f520ed5"
        self.assertTrue(may_resume_owned_session(True, True, low, upper, True, True, False))
        self.assertFalse(may_resume_owned_session(False, True, low, upper, True, True, False))
        self.assertFalse(may_resume_owned_session(True, False, low, upper, True, True, False))
        self.assertFalse(may_resume_owned_session(True, True, low, other, True, True, False))
        self.assertFalse(may_resume_owned_session(True, True, "", upper, True, True, False))
        self.assertFalse(may_resume_owned_session(True, True, low, upper, False, True, False))
        self.assertFalse(may_resume_owned_session(True, True, low, upper, True, False, False))
        self.assertFalse(may_resume_owned_session(True, True, low, upper, True, True, True))

    def test_adapter_identity_is_compared_as_a_uuid_value(self):
        low = "325b38cc-bfd3-4628-beac-acbc8f520ed4"
        upper = low.upper()
        other = "325b38cc-bfd3-4628-beac-acbc8f520ed5"
        self.assertTrue(same_adapter(low, upper))
        self.assertTrue(same_adapter("{" + upper + "}", low))
        self.assertFalse(same_adapter(low, other))
        self.assertFalse(same_adapter(low, ""))
        self.assertFalse(same_adapter("", low))
        self.assertFalse(same_adapter(None, low))
        self.assertFalse(same_adapter("not-a-guid", "not-a-guid"))
        self.assertEqual(adapter_key("{" + upper + "}"), low)
        self.assertFalse(adapter_identity_changed(low, upper))
        self.assertTrue(adapter_identity_changed(low, ""))
        self.assertTrue(adapter_identity_changed("", low))
        self.assertFalse(adapter_identity_changed("", ""))
        self.assertFalse(adapter_identity_changed(None, None))

    def test_resume_gate_reports_the_blocking_condition(self):
        low = "325b38cc-bfd3-4628-beac-acbc8f520ed4"
        upper = low.upper()
        other = "325b38cc-bfd3-4628-beac-acbc8f520ed5"
        self.assertTrue(may_resume_owned_session(True, True, low, upper, True, True, False))
        self.assertEqual(resume_block_reason(True, low, upper, True, True, False), "ok")
        self.assertEqual(resume_block_reason(False, low, upper, True, True, False), "not_owned")
        self.assertEqual(resume_block_reason(True, low, other, True, True, False), "adapter_mismatch")
        self.assertEqual(resume_block_reason(True, low, upper, False, True, False), "auto_connect_off")
        self.assertEqual(resume_block_reason(True, low, upper, True, False, False), "auto_reconnect_off")
        self.assertEqual(resume_block_reason(True, low, upper, True, True, True), "other_network")

    def test_authoritative_core_failure_count_is_not_incremented_again(self):
        count, stopped, yielded, notice, suppress = apply_connect_outcome(
            "AuthenticationRejected", "error", 5, False, False, counted=False)
        self.assertEqual(count, 5)
        self.assertTrue(stopped)
        self.assertEqual(notice, "AutoReconnectLimit")
        count, stopped, yielded, notice, suppress = apply_connect_outcome(
            "AuthenticationRejected", "error", 5, False, False, counted=True)
        self.assertEqual(count, 6)
        count, stopped, yielded, notice, suppress = apply_connect_outcome(
            "AuthenticationRejected", "error", 4, False, False, counted=False)
        self.assertEqual(count, 4)
        self.assertFalse(stopped)
        self.assertTrue(suppress)
        count, stopped, yielded, notice, suppress = apply_connect_outcome(
            None, "online", 5, False, False, counted=False)
        self.assertEqual((count, stopped, yielded, notice), (0, False, False, None))

    def test_auto_connect_does_not_wait_for_windows_link_up(self):
        self.assertTrue(want_auto_connect(True, False, False, True, True))
        self.assertFalse(want_auto_connect(True, False, False, False, True))
        self.assertFalse(want_auto_connect(True, True, False, True, True))
        self.assertFalse(want_auto_connect(False, False, False, True, True))
        self.assertFalse(want_auto_connect(True, False, True, True, True))
        self.assertFalse(want_auto_connect(True, False, False, True, False))


if __name__ == "__main__":
    unittest.main()
