# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gui.bridge.update import (
    choose_package, download_verified, format_version, github_url_allowed, local_version,
    offer_visible, parse_version, plan_files, update_notes)
from gui.shell.window import MainWindow
from gui import theme as T

APP = QApplication.instance() or QApplication([])


def _package():
    path = ROOT / "packaging" / "update_package.py"
    spec = importlib.util.spec_from_file_location("update_package", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class UpdateLogicTests(unittest.TestCase):
    def test_parse_version_accepts_tag_and_assembly_revision(self):
        self.assertEqual(parse_version("v1.4.2"), (1, 4, 2))
        self.assertEqual(parse_version("1.4.2"), (1, 4, 2))
        self.assertEqual(parse_version("1.4.1.0"), (1, 4, 1))
        self.assertLess(parse_version("1.3.20"), parse_version("1.4.1"))
        self.assertLess(parse_version("1.4.1"), parse_version("v1.4.2"))
        self.assertIsNone(parse_version("1.4.1.1"))
        self.assertIsNone(parse_version("beta"))
        self.assertIsNone(parse_version(""))

    def test_local_version_reads_marker_only_when_frozen(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "version.txt").write_text("v1.4.2\n", encoding="utf-8")
            (root / "release").mkdir()
            (root / "release" / "version.txt").write_text("9.9.9\n", encoding="utf-8")
            self.assertEqual(local_version(root, True, "1.0.0"), (1, 4, 2))
            self.assertEqual(local_version(root, False, "1.4.1"), (1, 4, 1))
            (root / "version.txt").write_text("not-a-version", encoding="utf-8")
            self.assertEqual(local_version(root, True, "1.4.1"), (1, 4, 1))

    def test_update_notes_stop_at_the_next_heading(self):
        text = "# Title\n\n##更新\n\n- 第一行\n\n## 下载\n- 忽略\n"
        self.assertEqual(update_notes(text), "- 第一行")
        spaced = "## 更新\n说明\n##验证\n"
        self.assertEqual(update_notes(spaced), "说明")
        self.assertEqual(update_notes("# 无更新段\n"), "")
        self.assertEqual(update_notes(""), "")

    def test_ignore_hides_that_version_but_not_a_higher_one(self):
        local, ignored = (1, 4, 1), (1, 4, 2)
        self.assertFalse(offer_visible(local, (1, 4, 2), ignored))
        self.assertFalse(offer_visible(local, (1, 4, 1), ignored))
        self.assertTrue(offer_visible(local, (1, 4, 3), ignored))
        self.assertFalse(offer_visible(None, (1, 4, 3), None))

    def test_update_notes_keep_the_following_fixes_section(self):
        text = "# 1.4.1\n\n## 更新\n- 新功能\n\n### 细节\n功能说明\n\n## 修复\n- 稳定性修复\n\n## 升级\n升级说明\n"
        expected = "- 新功能\n\n### 细节\n功能说明\n\n## 修复\n- 稳定性修复"
        self.assertEqual(update_notes(text), expected)
        self.assertEqual(update_notes(text.replace("\n", "\r\n")), expected)

    def test_delta_must_cover_every_changed_file(self):
        manifest = {
            "payload": "CampusTerminal-1.4.2-windows-x64-payload.zip",
            "deltas": [{
                "from": "1.4.1",
                "asset": "CampusTerminal-1.4.2-delta-from-1.4.1.zip",
                "files": ["a.txt", "b.txt"],
            }],
        }
        delta = choose_package((1, 4, 1), manifest, ["a.txt"])
        full = choose_package((1, 4, 1), manifest, ["a.txt", "c.txt"])
        other = choose_package((1, 4, 0), manifest, ["a.txt"])
        self.assertEqual(delta["kind"], "delta")
        self.assertEqual(delta["asset"], "CampusTerminal-1.4.2-delta-from-1.4.1.zip")
        self.assertEqual(full["kind"], "full")
        self.assertEqual(full["asset"], "CampusTerminal-1.4.2-windows-x64-payload.zip")
        self.assertEqual(other["kind"], "full")

    def test_plan_skips_unchanged_and_rejects_unsafe_paths(self):
        digest = _sha("new")
        with tempfile.TemporaryDirectory() as temp:
            root, staged = Path(temp) / "app", Path(temp) / "stage"
            root.mkdir()
            staged.mkdir()
            (staged / "ok.txt").write_text("new", encoding="utf-8")
            manifest = {"files": [{"path": "ok.txt", "sha256": digest, "size": 3}]}
            self.assertEqual([item["path"] for item in plan_files(root, staged, manifest, {})], ["ok.txt"])
            self.assertEqual(plan_files(root, staged, manifest, {"ok.txt": digest}), [])
            for path in ("..\\edition.txt", "state\\ui-settings.dpapi", "../outside.txt"):
                bad = {"files": [{"path": path, "sha256": digest, "size": 3}]}
                with self.assertRaises(ValueError):
                    plan_files(root, staged, bad, {})

    def test_download_rejects_foreign_host_and_hash_mismatch(self):
        class Opener:
            def open(self, request, timeout=None):
                raise AssertionError("opener should not run")

        foreign = {"browser_download_url": "https://evil.example/a", "digest": "sha256:" + ("a" * 64), "size": 1}
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "a.bin"
            with self.assertRaises(ValueError):
                download_verified(foreign, dest, Opener(), 5, "test")
            self.assertFalse(dest.exists())

            class Body:
                def __init__(self, payload):
                    self.payload = payload

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def read(self):
                    return self.payload

            body = b"hello"
            asset = {
                "browser_download_url": "https://github.com/HakureiTree/repo/releases/download/v1/a.bin",
                "digest": "sha256:" + _sha("nope"),
                "size": len(body),
            }
            with self.assertRaises(ValueError):
                download_verified(asset, dest, type("O", (), {"open": lambda *_a, **_k: Body(body)})(), 5, "test")
            self.assertFalse(dest.exists())
        self.assertFalse(github_url_allowed("http://github.com/a"))
        self.assertTrue(github_url_allowed("https://objects.githubusercontent.com/a"))

    def test_release_package_omits_user_and_edition_files(self):
        module = _package()
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / "src", Path(temp) / "out"
            (source / "state").mkdir(parents=True)
            (source / "a.txt").write_text("keep", encoding="utf-8")
            (source / "edition.txt").write_text("portable", encoding="utf-8")
            (source / "state" / "secret.txt").write_text("no", encoding="utf-8")
            manifest = module.write_release(source, output, "1.4.1")
            self.assertEqual([item["path"] for item in manifest["files"]], ["a.txt"])
            self.assertEqual(manifest["version"], "1.4.1")
            self.assertEqual(manifest["payload"], "CampusTerminal-1.4.1-windows-x64-payload.zip")
            with __import__("zipfile").ZipFile(output / manifest["payload"]) as archive:
                self.assertEqual(archive.namelist(), ["a.txt"])

    def test_delta_reads_versions_from_manifests(self):
        module = _package()
        with tempfile.TemporaryDirectory() as temp:
            base, new, tree, output = [Path(temp) / name for name in ("base.json", "new.json", "tree", "out")]
            tree.mkdir()
            (tree / "a.txt").write_text("new", encoding="utf-8")
            (tree / "b.txt").write_text("added", encoding="utf-8")
            old_hash, new_hash, added_hash = _sha("old"), _sha("new"), _sha("added")
            base.write_text(json.dumps({
                "version": "1.4.1",
                "files": [{"path": "a.txt", "sha256": old_hash, "size": 3}],
                "payload": "CampusTerminal-1.4.1-windows-x64-payload.zip",
                "deltas": [],
            }), encoding="utf-8")
            new.write_text(json.dumps({
                "version": "1.4.2",
                "files": [
                    {"path": "a.txt", "sha256": new_hash, "size": 3},
                    {"path": "b.txt", "sha256": added_hash, "size": 5},
                ],
                "payload": "CampusTerminal-1.4.2-windows-x64-payload.zip",
                "deltas": [],
            }), encoding="utf-8")
            published = module.write_delta(base, new, tree, output)
            self.assertEqual(published["deltas"][0]["from"], "1.4.1")
            self.assertEqual(published["deltas"][0]["files"], ["a.txt", "b.txt"])
            self.assertEqual(published["deltas"][0]["asset"], "CampusTerminal-1.4.2-delta-from-1.4.1.zip")


class ApplyScriptTests(unittest.TestCase):
    def _run(self, transaction):
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        script = ROOT / "packaging" / "Apply-Update.ps1"
        return subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(script), "-Transaction", str(transaction)],
            capture_output=True, text=True, timeout=40)

    def _transaction(self, install, staging, files, result):
        payload = {
            "install_root": str(install),
            "staging_root": str(staging),
            "files": files,
            "relaunch": "",
            "relaunch_args": [],
            "wait_pids": [],
            "wait_names": [],
            "result_path": str(result),
            "backup_root": str(install.parent / "backup"),
        }
        path = install.parent / "transaction.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_apply_replaces_only_planned_files_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install, staging = root / "app", root / "stage"
            (install / "state").mkdir(parents=True)
            staging.mkdir()
            (install / "a.txt").write_text("old", encoding="utf-8")
            (install / "edition.txt").write_text("installed", encoding="utf-8")
            (install / "state" / "keep.txt").write_text("user", encoding="utf-8")
            (staging / "a.txt").write_text("new", encoding="utf-8")
            result = root / "update-result.json"
            transaction = self._transaction(install, staging, [{
                "src": str(staging / "a.txt"), "dest": str(install / "a.txt"), "sha256": _sha("new"),
            }], result)
            done = self._run(transaction)
            detail = result.read_text(encoding="utf-8-sig") if result.exists() else done.stdout
            self.assertEqual(done.returncode, 0, done.stderr or detail)
            self.assertEqual((install / "a.txt").read_text(encoding="utf-8"), "new")
            self.assertEqual((install / "edition.txt").read_text(encoding="utf-8"), "installed")
            self.assertEqual((install / "state" / "keep.txt").read_text(encoding="utf-8"), "user")
            self.assertTrue(json.loads(result.read_text(encoding="utf-8"))["ok"])

            (staging / "a.txt").write_text("bad", encoding="utf-8")
            (staging / "c.txt").write_text("extra", encoding="utf-8")
            transaction = self._transaction(install, staging, [
                {"src": str(staging / "a.txt"), "dest": str(install / "a.txt"), "sha256": _sha("bad")},
                {"src": str(staging / "c.txt"), "dest": str(install / "c.txt"), "sha256": "0" * 64},
            ], result)
            failed = self._run(transaction)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual((install / "a.txt").read_text(encoding="utf-8"), "new")
            self.assertFalse((install / "c.txt").exists())
            self.assertFalse(json.loads(result.read_text(encoding="utf-8"))["ok"])

            transaction = self._transaction(install, staging, [{
                "src": str(staging / "a.txt"), "dest": str(install / "edition.txt"), "sha256": _sha("bad"),
            }], result)
            blocked = self._run(transaction)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertEqual((install / "edition.txt").read_text(encoding="utf-8"), "installed")
            self.assertEqual((install / "a.txt").read_text(encoding="utf-8"), "new")


class UpdateWindowTests(unittest.TestCase):
    def test_markdown_notes_render_headings_lists_and_emphasis(self):
        window = MainWindow(480 / T.WIN_W, T.load_design_font())
        window.show()
        APP.processEvents()
        try:
            dialog = window.update_choice
            notes = "- **自动更新**，保留 `state/`。\r\n\r\n##修复\r\n- 保持在线。"
            dialog.show_offer("1.4.1", notes)
            APP.processEvents()
            self.assertEqual(dialog.body.text(), "更新\n自动更新，保留 state/。\n修复\n保持在线。")
            headings, lists, bold = [], [], []
            block = dialog.body.document.begin()
            while block.isValid():
                if block.blockFormat().headingLevel():
                    headings.append((block.text(), block.begin().fragment().charFormat().font().pixelSize()))
                elif block.textList():
                    lists.append(block.text())
                    iterator = block.begin()
                    while not iterator.atEnd():
                        fragment = iterator.fragment()
                        if fragment.charFormat().font().bold():
                            bold.append(fragment.text())
                        iterator += 1
                block = block.next()
            self.assertEqual([text for text, _size in headings], ["更新", "修复"])
            self.assertEqual(len(lists), 2)
            self.assertIn("自动更新", bold)
            for _text, size in headings:
                self.assertGreater(size, dialog.body.font().pixelSize())
                self.assertLess(size, dialog.title.font().pixelSize())
            self.assertEqual(dialog.scroll.verticalScrollBar().maximum(), 0)
            dialog.show_offer("1.4.1", "## 更新\n- 改善连接。\n\n## 修复\n- 保持在线。")
            APP.processEvents()
            self.assertEqual(dialog.body.text().count("更新"), 1)
        finally:
            window.quit_app()

    def test_offer_adapts_to_the_release_notes_and_shrinks_again(self):
        notes = "更新\n- 启动时检查新版，可查看更新说明、立即更新或忽略该版本。\n- 按文件替换变化内容，保留设置、日志和安装类型。\n\n修复\n" + \
                "- 修复周期重认证与界面稳定性问题，继续保持连接并正常显示状态。\n" * 7
        window = MainWindow(480 / T.WIN_W, T.load_design_font())
        window.show()
        APP.processEvents()
        try:
            dialog = window.update_choice
            dialog.show_offer("1.4.1", "- 改善连接。")
            APP.processEvents()
            short = dialog._box.size()
            dialog.show_offer("1.4.1", notes)
            APP.processEvents()
            self.assertGreater(dialog._box.width(), short.width())
            self.assertGreater(dialog._box.height(), short.height())
            self.assertTrue(window.rect().contains(dialog._box.toAlignedRect()))
            self.assertEqual(dialog.scroll.verticalScrollBar().maximum(), 0)
            for button in (dialog.cancel_btn, dialog.ignore_btn, dialog.update_btn):
                self.assertTrue(dialog._box.toAlignedRect().contains(button.geometry()))
                self.assertGreater(button.y(), dialog.scroll.geometry().bottom())
            dialog.show_offer("1.4.1", "- 改善连接。")
            APP.processEvents()
            self.assertEqual(dialog._box.size(), short)
            dialog.show_offer("1.4.1", notes * 20)
            APP.processEvents()
            self.assertGreater(dialog.scroll.verticalScrollBar().maximum(), 0)
            window.resize(700, 850)
            APP.processEvents()
            dialog.show_offer("1.4.1", notes)
            APP.processEvents()
            self.assertEqual(dialog.scroll.verticalScrollBar().maximum(), 0)
            self.assertLessEqual(dialog.body.document.size().height(), dialog.scroll.viewport().height())
        finally:
            window.quit_app()

    def test_very_long_notes_scroll_and_keep_buttons_visible_on_small_windows(self):
        window = MainWindow(240 / T.WIN_W, T.load_design_font())
        window.show()
        APP.processEvents()
        try:
            dialog = window.update_choice
            dialog.show_offer("1.4.1", "更新说明\n" + "- 连接与界面改进的详细说明。\n" * 180)
            for size in ((240, 356), (480, 713), (700, 850)):
                window.resize(*size)
                APP.processEvents()
                box = dialog._box.toAlignedRect()
                self.assertTrue(window.rect().contains(box))
                self.assertGreater(dialog.scroll.verticalScrollBar().maximum(), 0)
                self.assertEqual(dialog.scroll.horizontalScrollBar().maximum(), 0)
                buttons = (dialog.cancel_btn, dialog.ignore_btn, dialog.update_btn)
                for button in buttons:
                    self.assertTrue(box.contains(button.geometry()))
                    self.assertGreater(button.y(), dialog.scroll.geometry().bottom())
                for left, right in zip(buttons, buttons[1:]):
                    self.assertFalse(left.geometry().intersects(right.geometry()))
        finally:
            window.quit_app()

    def test_chip_dialog_and_ignore(self):
        window = MainWindow(480 / T.WIN_W, T.load_design_font())
        window.show()
        APP.processEvents()
        try:
            window.update_chip.set_version("9.9.9")
            APP.processEvents()
            self.assertEqual(window.update_chip.label(), "有新版本可用：V9.9.9")
            self.assertTrue(window.update_chip.isVisible())
            self.assertIn("auto_update", window.settings.autos.toggles)
            self.assertTrue(window.settings.autos.rect().contains(
                window.settings.autos.toggles["auto_update"].geometry()))
            window.update_choice.show_offer("9.9.9", "- 修复连接\n")
            APP.processEvents()
            self.assertIn("修复连接", window.update_choice.body.text())
            window.resize(700, 850)
            APP.processEvents()
            self.assertEqual(window.update_choice.geometry(), window.rect())
            data = {}
            window.update_choice.ignore_requested.connect(window.update_confirm.ask)
            window.update_confirm.confirmed.connect(lambda: data.update(ignored_version="9.9.9") or window.update_chip.set_version(""))
            QTest.mouseClick(window.update_choice.ignore_btn, Qt.LeftButton)
            APP.processEvents()
            self.assertTrue(window.update_confirm.isVisible())
            self.assertEqual(window.update_confirm.body.text(), "确认忽略该版本更新？")
            window.resize(760, 900)
            APP.processEvents()
            self.assertEqual(window.update_confirm.geometry(), window.rect())
            QTest.mouseClick(window.update_confirm.confirm_btn, Qt.LeftButton)
            APP.processEvents()
            self.assertEqual(data["ignored_version"], "9.9.9")
            self.assertFalse(window.update_chip.isVisible())
        finally:
            window.quit_app()

    def test_version_sources_agree_and_hosts_have_no_literal(self):
        app = re.search(r'APP_VERSION = "(\d+\.\d+\.\d+)"',
                        (ROOT / "gui" / "theme.py").read_text(encoding="utf-8")).group(1)
        core = re.search(r"<Version>([^<]+)</Version>",
                         (ROOT / "core" / "CampusTerminal.Core.csproj").read_text(encoding="utf-8")).group(1)
        launch = re.search(r"<Version>([^<]+)</Version>",
                           (ROOT / "packaging" / "Launch" / "Launch.csproj").read_text(encoding="utf-8")).group(1)
        self.assertEqual(app, core)
        self.assertEqual(app, launch)
        self.assertEqual(format_version(parse_version(app)), app)
        host = (ROOT / "core" / "host" / "GuiHost.cs").read_text(encoding="utf-8")
        platform = (ROOT / "packaging" / "Launch" / "WindowsNpcapPlatform.cs").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"CampusTerminal-\d+\.\d+", host))
        self.assertIsNone(re.search(r"CampusTerminal/\d+\.\d+", platform))


if __name__ == "__main__":
    unittest.main()
