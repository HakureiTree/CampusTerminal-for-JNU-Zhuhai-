# SPDX-License-Identifier: GPL-3.0-or-later
import ctypes
import json
import os
import sys
import threading
import uuid

from PyQt5.QtCore import QTimer, QUrl, Qt
from PyQt5.QtGui import QDesktopServices, QGuiApplication
from PyQt5.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from gui import theme as T
from gui.bridge import store
from gui.bridge.original import gui_running as original_running, present as original_present
from gui.bridge.paths import diagnose, frozen, install_root
from gui.bridge.client import BackendClient
from gui.bridge.worker import BackendWorker
from gui.bridge.local_net import ConnectionAddressRefresh, TrafficSampler, adapter_ipv4, alternative_path, list_adapters, path_census
from gui.bridge.messages import error_text
from gui.bridge.auto_policy import (
    MAX_AUTO_FAILURES, SILENT_RETRY_SECONDS, apply_connect_outcome, connection_due,
    should_retry_auto_connect, silent_retry_wait, want_auto_connect)

from gui.bridge import trace
from gui.shell.alerts import AlertHost
from gui.shell.notifications import Notice, NotificationPolicy
from gui.shell.tray import AppTray, allow_taskbar_created
from gui.shell.window import MainWindow
from gui.bridge.startup import show_main_on_launch
from gui.shell.instance import SingleInstance, claim_primary, ping


def _choose_adapter(adapters, data):
    chosen = next((a for a in adapters if a["id"] == data.get("adapter_id")), None)
    if not chosen:
        chosen = next((a for a in adapters if a["label"] == data.get("adapter")), None)
    if not chosen and adapters:
        chosen = next((a for a in adapters if a.get("up")), adapters[0])
    return chosen


def _apply_settings(window, data, adapters):
    login = window.home.login
    login.account.setText(data.get("account", "") if data.get("save_account") else "")
    login.save_account.setChecked(bool(data.get("save_account")))
    login.save_password.setChecked(bool(data.get("save_password")))
    if data.get("save_password"):
        login.password.setText(store.load_password())
    labels = [a["label"] for a in adapters]
    chosen = _choose_adapter(adapters, data)
    current = chosen["label"] if chosen else data.get("adapter", "")
    if chosen:
        data["adapter"], data["adapter_id"] = chosen["label"], chosen["id"]
    window.settings.nic.set_adapters(labels, current)
    window.settings.types.set_type("normal")
    window.settings.autos.set_options(data)


def _collect(window, data):
    data["account"] = window.home.login.account.text().strip()
    data["save_account"] = window.home.login.save_account.isChecked()
    data["save_password"] = window.home.login.save_password.isChecked()
    data["adapter"] = window.settings.nic.combo.currentText()
    store.save(data)
    if data["save_password"]:
        password = window.home.login.password.text()
        if password:
            store.save_password(password)
    else:
        store.clear_password()


def _main_impl(cleanup):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ReveriX.CampusTerminal")
    except (AttributeError, OSError):
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("开源暨珠有线网络终端")
    app.setWindowIcon(T.app_icon())
    app.setQuitOnLastWindowClosed(False)
    preview = "--preview" in sys.argv
    silent_launch = "--silent" in sys.argv
    if not preview and os.environ.get("QT_QPA_PLATFORM") != "offscreen" and not claim_primary():
        # A second autostart must not raise the panel or pop a "already running" dialog.
        ping(not silent_launch)
        return 0
    window = MainWindow(T.window_scale(QGuiApplication.primaryScreen()), T.load_design_font())
    instance = SingleInstance(window.present, window) if not preview else None
    if instance and not instance.acquire():
        ping(not silent_launch)
        return 0
    if not preview:
        trace.begin_session()
    try:
        data = dict(store.DEFAULTS) if preview else store.load()
    except OSError:
        QMessageBox.critical(window, "设置", "无法读取当前 Windows 用户的加密设置。原文件已保留，未启动认证。")
        return 1
    if not preview:
        if frozen() and data.get("auto_start") and not store.startup_enabled():
            try:
                store.set_startup(True, bool(data.get("silent_start")))
            except OSError:
                pass
        try:
            store.sync_silent_startup(bool(data.get("silent_start")))
        except OSError:
            pass
        data["auto_start"] = store.startup_enabled()
    adapters = list_adapters()
    filled_adapter = not data.get("adapter_id")
    _apply_settings(window, data, adapters)
    if not preview and filled_adapter and data.get("adapter_id"):
        try:
            store.save(data)
        except OSError:
            pass
    root = install_root()
    try:
        (store.APP_DIR / "backend-probe.json").write_text(
            json.dumps(diagnose(root), ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    backend = BackendWorker(BackendClient(root), window)
    cleanup.append(backend.close)
    sampler = TrafficSampler()
    address_refresh = ConnectionAddressRefresh()
    tray = None
    alerts = AlertHost(window, None)
    notifications = NotificationPolicy(alerts.deliver if not preview else lambda _notice: None)
    window.tray_available = False
    runtime = {"phase": "idle", "active": False, "last_up": False, "auto_due": False,
               "quit": False, "disconnect": False, "configure": False, "ticks": 0,
               "quit_pending": False, "handed_back": False, "retry_stopped": False,
               "manual_stop": False, "closing": False, "retry_wait": 0, "typed_login": False,
               "core_alternative": False, "other_noted": False, "path_fp": "",
               "notified_fallback": bool(data.get("inode_fallback")), "inode_offered": False,
               "failure_count": 0, "yielded_network": False, "accounted": False,
               "cap_noted": False, "silent_wait": SILENT_RETRY_SECONDS, "released_for_other": False,
               "campaign_id": "", "campaign_eligible": False, "log_alerted": False}
    runtime["last_logged_status_phase"] = None

    def apply_original_features():
        on = original_present()
        toggle = window.settings.autos.toggles.get("inode_fallback")
        if toggle:
            toggle.setEnabled(on)
            if not on:
                toggle.blockSignals(True)
                toggle.setChecked(False)
                toggle.blockSignals(False)
                data["inode_fallback"] = False

    def offer_inode():
        if preview or original_present() or runtime["inode_offered"]:
            return
        if not (root / "payload" / "iNodeSetup.exe").is_file():
            return
        runtime["inode_offered"] = True
        alerts.deliver(Notice("本终端暂时无法联网",
                              "可以安装学校官方客户端作为应急，也可以拒绝、稍后再试。",
                              "warning", "confirm", "install-inode"))

    def on_notice_action(act):
        if act == "install-inode":
            setup = root / "payload" / "iNodeSetup.exe"
            if setup.is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(setup)))

    def selected():
        return next((a for a in adapters if a["label"] == window.settings.nic.combo.currentText()), None)

    def refresh_ipv4():
        nic = selected()
        try:
            addresses = adapter_ipv4(nic)
            text = " / ".join(addresses) if addresses else "尚未分配 IPv4" if nic else "未选择网卡"
        except OSError:
            text = "IPv4 读取失败"
        window.settings.ip.set_address(text)

    def sync_phase(phase, rows=None, error=None, recovery_enabled=None, quiet=False):
        runtime["phase"] = phase
        actions = window.home.actions
        actions.set_phase(phase)
        actions.login.setEnabled(not backend.busy and not runtime["active"] and not preview)
        actions.logout.setEnabled(runtime["active"] and phase not in ("disconnecting", "fallback"))
        window.settings.nic.setEnabled(not runtime["active"] and not backend.busy)
        rec = "ok" if phase in ("online", "fallback_active") else "wait" if phase in ("connecting", "verifying", "recovering", "disconnecting", "fallback") else "error" if error else "idle"
        if recovery_enabled is False and rec == "ok":
            rec = "idle"
        detail = error_text(error) if error else None
        if quiet:
            notifications.silence(phase, detail)
        else:
            notifications.observe(phase, detail)
        window.home.recovery.set_state(rec, rows or [], detail)
        window.home.actions.led.setToolTip(detail or {"online": "校园网验证通过", "verifying": "正在验证校园网连通性", "fallback": "正在交还学校官方客户端", "fallback_active": "学校官方客户端已接管", "fallback_failed": "交还学校官方客户端失败"}.get(phase, phase))
        if tray:
            tray.set_phase(phase)

    def options(takeover=False, manual=False, silent_retry=False, campaign=False):
        result = {"autoReconnect": bool(data.get("auto_reconnect")), "inodeFallback": bool(data.get("inode_fallback")),
                "connectionType": "normal", "takeOverOriginal": bool(takeover), "manual": bool(manual),
                "silentRetry": bool(silent_retry)}
        if campaign:
            result.update(autoReconnectCampaign=True, campaignId=ensure_campaign_id())
        return result

    def ensure_campaign_id():
        if not runtime["campaign_id"]:
            runtime["campaign_id"] = uuid.uuid4().hex
        return runtime["campaign_id"]

    def set_retry_wait(seconds, reason="failure"):
        previous = runtime["retry_wait"]
        runtime["retry_wait"] = max(previous, seconds)
        if seconds and not previous:
            trace.emit("auto_retry_wait", count=runtime["failure_count"], duration_ms=seconds * 1000,
                       campaign_id=runtime["campaign_id"] or None, outcome="entered", reason=reason)

    def completed(method, result):
        if method == "shutdown" and result.get("error") in ("BackendUnavailable", "BackendStopTimeout") and not data.get("inode_fallback"):
            result = {"ok": True, "pending": False}
        if result.get("ok"):
            logging = result.get("logging") or {}
            log_error = logging.get("error") or logging.get("recoveryError") if isinstance(logging, dict) else None
            if log_error and not runtime.get("backend_log_alerted"):
                runtime["backend_log_alerted"] = True
                trace.emit("backend_log_write_error", error=trace.safe_error(log_error))
                alerts.warn("诊断记录", "后台日志暂时无法完整保存，请检查日志目录的写入权限。", "warning", kind="remind")
            elif not log_error and runtime.pop("backend_log_alerted", False):
                trace.emit("backend_log_write_recovered")
            if method == "status":
                runtime.pop("status_alert_error", None)
                phase_now = result.get("phase", "idle")
                if phase_now != runtime["last_logged_status_phase"]:
                    runtime["last_logged_status_phase"] = phase_now
                    trace.emit("status_phase", phase=phase_now, active=bool(result.get("active")))
            if method == "status" and result.get("phase") in ("online", "fallback_active"):
                runtime["campaign_eligible"] = False
                runtime["campaign_id"] = ""
            if method == "shutdown" and result.get("pending") and data.get("inode_fallback"):
                runtime["quit_pending"] = True
            elif method == "shutdown":
                stop_ui_callbacks()
                if tray:
                    tray.hide()
                backend.close()
                window.quit_app()
                app.quit()
                return
            if method == "configure" and "inodeFallback" in (result.get("options") or {}):
                confirmed = bool(result["options"]["inodeFallback"])
                if confirmed != runtime["notified_fallback"]:
                    notifications.fallback_option(confirmed)
                    runtime["notified_fallback"] = confirmed
            runtime["active"] = bool(result.get("active", method == "connect"))
            rec = result.get("recovery") or {}
            remote_failures = int(rec.get("autoFailures") or 0)
            if remote_failures:
                runtime["failure_count"] = max(runtime["failure_count"], remote_failures)
            if rec.get("exhausted") and runtime["failure_count"] >= MAX_AUTO_FAILURES:
                runtime["retry_stopped"] = True
                runtime["auto_due"] = False
            if "exhausted" in rec:
                notifications.observe_recovery(rec["exhausted"], bool(data.get("inode_fallback")))
                if rec["exhausted"]:
                    runtime["retry_stopped"] = True
                    runtime["auto_due"] = False
                    offer_inode()
            err = result.get("firstError") or result.get("error")
            phase = result.get("phase", "idle")
            if method == "release_campus" and not result.get("yielded"):
                runtime["released_for_other"] = False
            if "alternative" in result:
                runtime["core_alternative"] = bool(result.get("alternative"))
            nic = selected()
            try:
                other = bool(alternative_path(nic["id"] if nic else "")) or runtime["core_alternative"]
            except OSError:
                other = runtime["core_alternative"]
            yield_now = other and phase not in ("disconnecting", "fallback")
            identity = (nic["id"] if nic else "", result.get("processId"), result.get("generation"))
            if address_refresh.observe("idle" if yield_now else phase, identity):
                refresh_ipv4()
            notice, suppress = err, False
            if phase in ("online", "degraded") or (phase == "error" and not runtime["accounted"]) or yield_now:
                if phase in ("online", "degraded") and not yield_now:
                    runtime["accounted"] = False
                    runtime["cap_noted"] = False
                    runtime["silent_wait"] = SILENT_RETRY_SECONDS
                    runtime["released_for_other"] = False
                count, stopped, yielded, notice, suppress = apply_connect_outcome(
                    err, phase, runtime["failure_count"], runtime["yielded_network"], yield_now)
                runtime["failure_count"], runtime["retry_stopped"], runtime["yielded_network"] = count, stopped, yielded
                if phase == "error" or notice == "AlternativeNetworkPath":
                    runtime["accounted"] = True
                    runtime["campaign_eligible"] = True
                if stopped:
                    runtime["auto_due"] = False
            rows = []
            for e in rec.get("events", []):
                event_result = str(e.get("result") or "")
                if not event_result and e.get("stage") == "TwoCampusRoundsPassed":
                    event_result = "成功"
                rows.append((str(e.get("at", "")), str(e.get("time", "")), event_result))
            if runtime["failure_count"] >= MAX_AUTO_FAILURES and not runtime["active"]:
                runtime["retry_stopped"] = True
                runtime["auto_due"] = False
                if not runtime["cap_noted"]:
                    runtime["cap_noted"] = True
                    runtime["silent_wait"] = SILENT_RETRY_SECONDS
                    trace.emit("auto_retry_cap_reached", count=runtime["failure_count"],
                               campaign_id=ensure_campaign_id())
                    trace.emit("auto_retry_wait", count=runtime["failure_count"],
                               duration_ms=SILENT_RETRY_SECONDS * 1000,
                               campaign_id=runtime["campaign_id"], outcome="entered", reason="failure_cap")
                    notice, suppress = "AutoReconnectLimit", False
                else:
                    notice, suppress = None, True
            if notice == "AlternativeNetworkPath" or yield_now:
                runtime["auto_due"] = False
                runtime["yielded_network"] = True
                runtime["retry_stopped"] = True
                if runtime["active"]:
                    runtime["disconnect"] = True
                note_other_network()
                sync_phase("idle", rows, None, rec.get("enabled"), quiet=True)
            elif suppress and phase == "error":
                if not runtime["cap_noted"]:
                    runtime["auto_due"] = True
                    set_retry_wait(2, "retryable_status_error")
                sync_phase("error", rows, notice, rec.get("enabled"), quiet=True)
            else:
                shown = "error" if notice == "AutoReconnectLimit" else phase
                sync_phase(shown, rows, notice, rec.get("enabled"))
            if result.get("phase") in ("fallback", "fallback_active", "fallback_failed"):
                runtime["handed_back"] = True
                runtime["auto_due"] = False
            if method == "status" and runtime["quit_pending"] and not runtime["active"]:
                runtime["quit_pending"] = False
                pump()
                return
        else:
            address_refresh.observe("error", None)
            lost = result.get("error") == "BackendUnavailable" and runtime["active"]
            err = result.get("firstError") or result.get("error")
            if result.get("alternative") or err == "AlternativeNetworkPath":
                runtime["core_alternative"] = True
                runtime["yielded_network"] = True
                runtime["retry_stopped"] = True
                runtime["auto_due"] = False
                note_other_network()
                sync_phase("idle", quiet=True)
                pump()
                return
            blocking = err in ("OriginalManualExitRequired", "MaintenanceAlreadyOwned")
            if lost:
                runtime["active"] = False
                runtime["auto_due"] = bool(data.get("auto_connect")) and not runtime["manual_stop"] and not runtime["handed_back"]
            if blocking:
                runtime["retry_stopped"] = True
                runtime["auto_due"] = False
            idle_status = method == "status" and not runtime["active"] and err == "BackendUnavailable"
            if not idle_status:
                sync_phase("error", error=err)
            if method == "status" and err:
                if runtime.get("status_alert_error") != err:
                    runtime["status_alert_error"] = err
                    alerts.warn("连接状态", "连接后台状态读取失败，正在继续监测。", "warning", kind="remind")
            if err in ("BackendMissing", "BackendLaunchFailed", "ElevationCancelled", "AdapterNotFound",
                       "LinkUnavailable", "ReconnectAttemptsExhausted", "AutoReconnectLimit"):
                offer_inode()
            if method in ("connect", "ensure_started") and should_retry_auto_connect(
                    err, data.get("auto_connect"), runtime["manual_stop"], runtime["handed_back"],
                    runtime["failure_count"], runtime["yielded_network"]):
                runtime["auto_due"] = True
                set_retry_wait(8 if err == "BackendStartTimeout" else 3, "backend_error")
            elif method in ("connect", "ensure_started") and err:
                runtime["retry_stopped"] = True
                runtime["auto_due"] = False
            if method in ("connect", "ensure_started"):
                runtime["campaign_eligible"] = True
            if method in ("connect", "disconnect", "shutdown"):
                if method == "shutdown":
                    runtime["quit"] = False
                    runtime["quit_pending"] = False
        pump()

    def pump():
        if runtime["closing"] or backend.busy or preview:
            return
        if runtime["quit"]:
            if not runtime["quit_pending"]:
                nic = selected()
                backend.submit("shutdown", bool(data.get("inode_fallback")), nic["id"] if nic else "")
        elif runtime["disconnect"]:
            runtime["disconnect"] = False
            backend.submit("disconnect")
        elif runtime["configure"]:
            runtime["configure"] = False
            backend.submit("configure", options())

    def on_option(key, value):
        if preview:
            return
        old = data.get(key)
        data[key] = value
        try:
            if key in ("save_account", "save_password"):
                _collect(window, data)
            else:
                store.save(data)
        except OSError as exc:
            data[key] = old
            window.settings.autos.set_options(data)
            alerts.warn("设置", "保存失败：" + str(exc))
            return
        if key in ("auto_start", "silent_start"):
            try:
                store.set_startup(bool(data.get("auto_start")), bool(data.get("silent_start")))
            except OSError:
                alerts.warn("开机启动", "选项已保存，但开机项未能登记。可稍后再试。", "warning", kind="remind")
                return
        if key == "inode_fallback" and value and not original_present():
            data[key] = False
            window.settings.autos.set_options(data)
            return
        if key in ("auto_reconnect", "inode_fallback"):
            runtime["configure"] = True
            pump()
        if key == "auto_connect" and value:
            runtime["last_up"] = False
            runtime["manual_stop"] = False
            runtime["auto_due"] = True
            runtime["retry_wait"] = 0

    def on_adapter(label):
        match = next((a for a in adapters if a["label"] == label), None)
        sampler.set_adapter(match["name"] if match else None)
        refresh_ipv4()
        runtime["last_up"] = False
        if not preview:
            data["adapter"], data["adapter_id"] = label, match["id"] if match else ""
            store.save(data)

    def saved_login():
        user = (data.get("account") or "").strip() if data.get("save_account") else ""
        password = store.load_password() if data.get("save_password") else ""
        return user, password

    def connect(silent=False, periodic=False):
        if preview or backend.busy or runtime["active"]:
            return False
        if silent and runtime["retry_stopped"] and not periodic:
            return False
        if silent:
            if runtime["yielded_network"] or runtime["core_alternative"]:
                trace.emit("auto_skip", reason="OtherNetwork")
                return False
            if runtime["typed_login"]:
                trace.emit("auto_skip", reason="WaitingManualLogin")
                return False
            user, password = saved_login()
            if not user or not password:
                trace.emit("auto_skip", reason="NoSavedCredentials")
                return False
        else:
            user = window.home.login.account.text().strip()
            password = window.home.login.password.text()
            if not user or not password:
                trace.emit("connect_skip", reason="NoCredentials")
                alerts.warn("网络登入", "请先输入学号和密码。", "information", kind="remind")
                return False
        nic = selected()
        if not nic:
            trace.emit("auto_skip" if silent else "connect_skip", reason="AdapterNotFound")
            if not silent:
                sync_phase("error", error="AdapterNotFound")
            return False
        try:
            _collect(window, data)
        except OSError:
            alerts.warn("网络登入", "凭据设置保存失败，尚未发起连接。")
            return False
        takeover = original_running() and not periodic
        trace.emit("connect_submit", silent=silent, adapter=nic["id"], takeover=takeover,
                   up=bool(nic.get("up")))
        campaign = bool(silent and runtime["campaign_eligible"])
        backend.submit("connect", user, password, nic["id"],
                       options(takeover=takeover, manual=not silent, silent_retry=periodic, campaign=campaign))
        runtime["accounted"] = False
        if not silent:
            runtime["campaign_eligible"] = False
            runtime["campaign_id"] = ""
        if not silent and runtime["failure_count"] < MAX_AUTO_FAILURES:
            runtime["retry_stopped"] = False
        runtime["manual_stop"] = False
        runtime["handed_back"] = False
        if not silent:
            runtime["typed_login"] = False
        sync_phase("connecting")
        return True

    def note_other_network():
        if runtime["other_noted"]:
            return
        runtime["other_noted"] = True
        trace.emit("yield_other")
        alerts.warn("已让出网络",
                    "检测到手机共享或其它上网方式，已停止校园网认证和重连，避免抢走默认路由。其它网络断开后会再自动连接。",
                    "information", kind="remind")

    def record_paths(campus_id, other):
        try:
            rows = path_census(campus_id)
        except OSError:
            return
        fingerprint = json.dumps(rows, ensure_ascii=False, sort_keys=True)
        if fingerprint == runtime["path_fp"] and runtime["ticks"] % 60 != 0:
            return
        runtime["path_fp"] = fingerprint
        trace.emit("path_census", other=bool(other), rows=rows)

    def disconnect():
        runtime["manual_stop"] = True
        runtime["auto_due"] = False
        runtime["campaign_eligible"] = False
        runtime["campaign_id"] = ""
        runtime["disconnect"] = True
        sync_phase("disconnecting")
        pump()

    def tick():
        if runtime["closing"] or preview:
            return
        if not runtime["log_alerted"] and (store.APP_DIR / "gui-events.write-status.json").exists():
            runtime["log_alerted"] = True
            alerts.warn("诊断记录", "诊断日志暂时无法写入；应用仍在运行。请检查应用状态目录的写入权限。",
                        "warning", kind="remind")
        elif runtime["log_alerted"] and not (store.APP_DIR / "gui-events.write-status.json").exists():
            runtime["log_alerted"] = False
        runtime["ticks"] += 1
        if runtime["ticks"] % 60 == 0:
            trace.session_heartbeat()
        if runtime["ticks"] % 2 == 0:
            fresh = list_adapters()
            current = window.settings.nic.combo.currentText()
            if [(a["id"], a["label"]) for a in fresh] != [(a["id"], a["label"]) for a in adapters]:
                adapters[:] = fresh
                window.settings.nic.set_adapters([a["label"] for a in fresh], current)
                on_adapter(window.settings.nic.combo.currentText())
            else:
                adapters[:] = fresh
        up, down, samples = sampler.tick()
        window.home.speed.set_rates(up, down, samples)
        nic = selected()
        has_nic = nic is not None
        saved_user, saved_password = saved_login()
        has_creds = bool(saved_user and saved_password) and not runtime["typed_login"]
        link_up = bool(nic and nic["up"])
        try:
            local_other = bool(alternative_path(nic["id"] if nic else ""))
        except OSError:
            local_other = False
        other = local_other or runtime["core_alternative"]
        notifications.observe_link(link_up, runtime["active"] and not other)
        if runtime["ticks"] % 30 == 0 or runtime["ticks"] == 1:
            record_paths(nic["id"] if nic else "", other)
        if other:
            runtime["auto_due"] = False
            runtime["yielded_network"] = True
            runtime["retry_stopped"] = True
            note_other_network()
            if nic and not runtime["released_for_other"] and not backend.busy:
                if backend.submit("release_campus", nic["id"]):
                    runtime["released_for_other"] = True
            elif runtime["active"] and runtime["phase"] not in ("disconnecting", "fallback"):
                runtime["disconnect"] = True
            elif runtime["phase"] == "error":
                sync_phase("idle", quiet=True)
        elif want_auto_connect(data.get("auto_connect"), runtime["manual_stop"], runtime["handed_back"], has_nic, has_creds):
            runtime["released_for_other"] = False
            runtime["other_noted"] = False
            runtime["core_alternative"] = False
            if runtime["yielded_network"]:
                runtime["yielded_network"] = False
                if runtime["failure_count"] < MAX_AUTO_FAILURES:
                    runtime["retry_stopped"] = False
            if connection_due(runtime["last_up"], link_up, True, False) and runtime["failure_count"] < MAX_AUTO_FAILURES:
                runtime["retry_wait"] = 0
                runtime["retry_stopped"] = False
            runtime["auto_due"] = not runtime["retry_stopped"]
        else:
            runtime["auto_due"] = False
        runtime["last_up"] = link_up
        if tray and runtime["ticks"] % 15 == 0:
            tray.keep()
        if backend.busy or preview:
            return
        pump()
        if runtime["quit"]:
            if not backend.busy and runtime["quit_pending"]:
                backend.submit("status")
            return
        if backend.busy:
            return
        if (runtime["cap_noted"] and not runtime["active"] and not runtime["handed_back"] and not runtime["quit"]
                and not runtime["manual_stop"]):
            due, runtime["silent_wait"] = silent_retry_wait(
                runtime["silent_wait"], True, other, bool(data.get("auto_connect")),
                runtime["manual_stop"], runtime["handed_back"])
            if due:
                trace.emit("auto_retry_wait", count=runtime["failure_count"],
                           duration_ms=SILENT_RETRY_SECONDS * 1000,
                           campaign_id=ensure_campaign_id(), outcome="resumed", reason="failure_cap")
                connect(silent=True, periodic=True)
        if runtime["auto_due"] and not runtime["active"] and not runtime["handed_back"] and not runtime["quit"]:
            if runtime["retry_wait"] > 0:
                runtime["retry_wait"] -= 1
                if runtime["retry_wait"] == 0:
                    trace.emit("auto_retry_wait", count=runtime["failure_count"], duration_ms=0,
                               campaign_id=runtime["campaign_id"] or None,
                               outcome="resumed", reason="backend_error")
            elif connect(silent=True):
                runtime["auto_due"] = False
            else:
                runtime["retry_wait"] = 2
        if not backend.busy:
            backend.submit("status")

    def quit_app():
        if preview:
            stop_ui_callbacks()
            backend.close()
            window.quit_app()
            app.quit()
            return
        if tray and QMessageBox.question(window, "开源暨珠有线网络终端",
                                         "退出后将停止校园网认证。确定退出？",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            _collect(window, data)
        except OSError:
            alerts.warn("设置", "设置保存失败。")
        runtime["quit"] = True
        runtime["auto_due"] = False
        if tray:
            tray.hide()
        pump()

    apply_original_features()
    window.notice.action_requested.connect(on_notice_action)
    backend.completed.connect(completed)
    window.home.connect_requested.connect(lambda: connect(False))
    window.home.disconnect_requested.connect(disconnect)
    window.home.open_ad.connect(lambda: QDesktopServices.openUrl(QUrl("https://tree.reverix.ai")))
    window.settings.option_changed.connect(on_option)
    window.settings.adapter_changed.connect(on_adapter)
    window.home.login.save_account_changed.connect(lambda on: on_option("save_account", on))
    window.home.login.save_password_changed.connect(lambda on: on_option("save_password", on))
    window.home.login.password.returnPressed.connect(lambda: connect(False))
    window.home.login.account.returnPressed.connect(window.home.login.password.setFocus)
    def persist_login():
        if preview or runtime["closing"] or runtime["quit"]:
            return
        try:
            _collect(window, data)
        except OSError:
            alerts.warn("设置", "凭据保存失败，未写入明文。")
    def mark_login_edit():
        if runtime["closing"] or runtime["quit"]:
            return
        runtime["typed_login"] = True
        runtime["auto_due"] = False
    window.home.login.account.textChanged.connect(mark_login_edit)
    window.home.login.password.textChanged.connect(mark_login_edit)
    window.home.login.account.editingFinished.connect(persist_login)
    window.home.login.password.editingFinished.connect(persist_login)
    window.exit_requested.connect(quit_app)
    def attach_tray():
        nonlocal tray
        if tray is not None or not QSystemTrayIcon.isSystemTrayAvailable():
            return tray is not None
        tray = AppTray(window)
        window.tray_available = True
        alerts.tray = tray
        tray.show_main.connect(window.present)
        tray.connect_requested.connect(lambda: connect(False))
        tray.disconnect_requested.connect(disconnect)
        tray.quit_requested.connect(quit_app)
        window.taskbar_created.connect(tray.restore)
        tray.show()
        try:
            allow_taskbar_created(int(window.winId()))
        except (TypeError, ValueError, OSError):
            pass
        return True

    attach_tray()
    match = selected()
    sampler.set_adapter(match["name"] if match else None)
    refresh_ipv4()
    if not preview:
        if data.get("auto_connect"):
            saved_user, saved_password = saved_login()
            runtime["auto_due"] = bool(saved_user and saved_password)
            trace.emit("auto_armed", adapter=data.get("adapter_id"),
                       has_password=bool(saved_password),
                       auto_due=runtime["auto_due"],
                       adapter_up=bool(match and match.get("up")))
        else:
            backend.submit("ensure_started")
    sync_phase("idle")
    timer = QTimer(window)
    timer.setInterval(1000)
    timer.timeout.connect(tick)
    watchdog = trace.MainLoopWatchdog()
    cleanup.append(watchdog.close)
    pulse = QTimer(window)
    pulse.setInterval(250)
    pulse.timeout.connect(watchdog.pulse)
    pulse.start()
    def stop_ui_callbacks():
        if runtime["closing"]:
            return
        runtime["closing"] = True
        timer.stop()
        pulse.stop()
        watchdog.close()
        # Focus loss during widget destruction must not save or open a dialog.
        window.home.login.account.textChanged.disconnect(mark_login_edit)
        window.home.login.password.textChanged.disconnect(mark_login_edit)
        window.home.login.account.editingFinished.disconnect(persist_login)
        window.home.login.password.editingFinished.disconnect(persist_login)
    app.aboutToQuit.connect(stop_ui_callbacks)
    timer.start()
    if not preview and runtime["auto_due"]:
        QTimer.singleShot(0, tick)
    if show_main_on_launch(silent_launch, tray is not None, False):
        window.present()
    elif silent_launch and tray is None:
        # Explorer's tray is often missing for the first seconds after logon.
        hold = {"left": 20}

        def retry_tray():
            if runtime["closing"]:
                return
            if attach_tray() or hold["left"] <= 0:
                if show_main_on_launch(True, tray is not None, hold["left"] <= 0):
                    window.present()
                return
            hold["left"] -= 1
            QTimer.singleShot(500, retry_tray)

        QTimer.singleShot(500, retry_tray)
    if preview and "--smoke" in sys.argv:
        QTimer.singleShot(800, quit_app)
    code = app.exec_()
    stop_ui_callbacks()
    backend.close()
    return code


def main():
    old_sys_hook, old_thread_hook = sys.excepthook, threading.excepthook
    crash = {"exception": None}
    cleanup = []
    def _sys_hook(exc_type, _exc, tb):
        trace.safe_exception("unhandled_exception", exc_type, tb)
    def _thread_hook(args):
        trace.safe_exception("unhandled_thread_exception", args.exc_type, args.exc_traceback)
    sys.excepthook, threading.excepthook = _sys_hook, _thread_hook
    try:
        return _main_impl(cleanup)
    except BaseException as exc:
        crash["exception"] = exc
        trace.safe_exception("gui_startup_exception", type(exc), exc.__traceback__)
        return 1
    finally:
        for close in reversed(cleanup):
            try:
                close()
            except Exception as exc:
                trace.safe_exception("gui_cleanup_exception", type(exc), exc.__traceback__)
        exc = crash["exception"]
        trace.end_session(bool(exc), type(exc) if exc else None, exc.__traceback__ if exc else None)
        sys.excepthook, threading.excepthook = old_sys_hook, old_thread_hook
