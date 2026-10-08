# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui.shell.notifications import NotificationPolicy


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.notices = []
        self.now = 0
        self.policy = NotificationPolicy(self.notices.append, lambda: self.now)

    def test_silent_retry_does_not_emit(self):
        self.policy.silence("error", "校园网拒绝了本次认证")
        self.policy.observe("error", "校园网拒绝了本次认证")
        self.assertEqual(self.notices, [])

    def test_unchanged_error_never_repeats(self):
        self.policy.observe("error", "后台不可用")
        for _ in range(100):
            self.now += 60
            self.policy.observe("error", "后台不可用")
        self.assertEqual(len(self.notices), 1)
        self.policy.observe("error", "认证失败")
        self.assertEqual(len(self.notices), 2)

    def test_outage_and_verified_restoration(self):
        self.policy.observe("online")
        self.now = 40
        self.policy.observe("degraded")
        self.policy.observe("recovering")
        self.policy.observe("verifying")
        self.policy.observe("online")
        self.assertEqual([n.title for n in self.notices], ["校园网已连接", "校园网连接异常", "校园网已恢复"])

    def test_no_startup_link_warning_or_manual_disconnect_error(self):
        self.policy.observe_link(False, True)
        self.policy.observe("idle")
        self.assertEqual(self.notices, [])
        self.policy.observe_link(True, True)
        self.policy.observe_link(False, True)
        self.policy.observe_link(False, True)
        self.assertEqual(len(self.notices), 1)
        self.policy.observe("disconnecting")
        self.policy.observe("idle")
        self.assertEqual(self.notices[-1].title, "校园网已断连")

    def test_flapping_is_rate_limited(self):
        for _ in range(5):
            self.policy.observe("error", "后台不可用")
            self.policy.observe("idle")
        self.assertEqual(len(self.notices), 1)
        self.now = 31
        self.policy.observe("error", "后台不可用")
        self.assertEqual(len(self.notices), 2)

    def test_connecting_is_a_remind_notice(self):
        self.policy.observe("connecting")
        self.assertEqual(self.notices[-1].title, "正在连接校园网")
        self.assertEqual(self.notices[-1].kind, "remind")
        self.policy.observe("connecting")
        self.assertEqual(len(self.notices), 1)

    def test_fallback_and_option_changes(self):
        self.policy.fallback_option(True)
        self.policy.observe("fallback")
        self.policy.observe("fallback_active")
        self.policy.fallback_option(False)
        self.assertEqual(len(self.notices), 4)

    def test_dns_diagnostic_change_is_actionable_but_deduplicated(self):
        self.policy.observe("degraded")
        self.policy.observe("degraded", "DNS 解析失败")
        self.policy.observe("degraded", "DNS 解析失败")
        self.assertEqual(len(self.notices), 2)
        self.assertEqual(self.notices[-1].body, "DNS 解析失败")

    def test_exhaustion_survives_fast_fallback_phase_and_is_not_repeated(self):
        self.policy.observe_recovery(True, True)
        self.policy.observe("fallback")
        for _ in range(50):
            self.now += 60
            self.policy.observe_recovery(True, True)
        failures = [n for n in self.notices if n.title == "自动重连已停止"]
        self.assertEqual(len(failures), 1)
        self.assertIn("交还", failures[0].body)
        self.policy.observe_recovery(False, False)
        self.policy.observe_recovery(True, False)
        self.assertIn("网线", self.notices[-1].body)
        self.assertIn("驱动", self.notices[-1].body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
