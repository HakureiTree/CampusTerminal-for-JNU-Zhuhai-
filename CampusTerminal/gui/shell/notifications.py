# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class Notice:
    title: str
    body: str
    severity: str = "information"
    kind: str = "confirm"
    action: str = ""


def is_confirm(notice):
    return getattr(notice, "kind", "confirm") != "remind"


def remind_ms(notice):
    n = len(notice.title or "") + len(notice.body or "")
    return int(round(min(4.0, max(2.0, 2.0 + n / 40.0)) * 1000))


class NotificationPolicy:
    """Transition policy independent of Qt and Windows notification delivery."""

    def __init__(self, emit, clock=monotonic, cooldown=30):
        self.emit = emit
        self.clock = clock
        self.cooldown = cooldown
        self.phase = "idle"
        self.error = None
        self.link = None
        self.outage = False
        self.sent = {}
        self.exhausted = False

    def send(self, key, notice):
        now = self.clock()
        if now - self.sent.get(key, float("-inf")) < self.cooldown:
            return
        self.sent[key] = now
        self.emit(notice)

    def silence(self, phase, error=None):
        """Remember a state without emitting a toast. Used while auto-retry is still under the cap."""
        self.phase, self.error = phase, error

    def observe(self, phase, error=None):
        previous, old_error = self.phase, self.error
        self.phase, self.error = phase, error
        if phase == previous and error == old_error:
            return
        if phase in ("degraded", "recovering"):
            self.outage = True
            self.send(("outage", error), Notice("校园网连接异常", error or "正在核验网络，请稍候。", "warning", "remind"))
        elif phase in ("error", "fallback_failed"):
            self.outage = self.outage or previous in ("online", "recovering", "verifying", "degraded")
            self.send(("error", error), Notice("校园网终端错误", error or "操作未完成。", "critical", "confirm"))
        elif phase == "connecting":
            self.send("connecting", Notice("正在连接校园网", "请耐心等待。", "information", "remind"))
        elif phase == "online" and previous != "online":
            restored = self.outage
            self.outage = False
            self.send("restored" if restored else "online", Notice(
                "校园网已恢复" if restored else "校园网已连接", "连通性验证已通过。", "information", "remind"))
        elif phase == "fallback":
            self.send("fallback", Notice("正在交还学校官方客户端", "已停止本终端认证，正在启动学校官方客户端。", "warning", "remind"))
        elif phase == "fallback_active":
            self.outage = False
            self.send("fallback_active", Notice("学校官方客户端已接管", "学校官方客户端联网和自动重连已核验。", "information", "remind"))
        elif phase == "idle" and previous == "disconnecting":
            self.outage = False
            self.send("disconnected", Notice("校园网已断连", "已按你的操作停止认证。", "information", "remind"))

    def observe_link(self, up, active):
        previous, self.link = self.link, bool(up)
        if previous is True and not up and active:
            self.outage = True
            self.send("link_down", Notice("有线网络已断开", "请检查网线或网卡。", "warning", "confirm"))

    def observe_recovery(self, exhausted, fallback_enabled):
        previous, self.exhausted = self.exhausted, bool(exhausted)
        if self.exhausted and not previous:
            action = ("正在按兜底设置交还学校官方客户端。" if fallback_enabled
                      else "请恢复学校官方客户端，或检查网线与网卡驱动。")
            self.send("attempts_exhausted", Notice("自动重连已停止", "已达到自动重连上限。" + action, "critical", "confirm"))

    def fallback_option(self, enabled):
        body = ("恢复失败或退出程序时，将停止自身认证并交还学校官方客户端。" if enabled
                else "恢复失败或退出程序时，不会自动启动学校官方客户端。")
        self.send(("fallback_option", enabled), Notice(
            "学校官方客户端兜底已开启" if enabled else "学校官方客户端兜底已关闭", body, "information", "remind"))
