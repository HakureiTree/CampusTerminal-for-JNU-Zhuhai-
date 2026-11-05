# SPDX-License-Identifier: GPL-3.0-or-later
"""Release-notes extraction and the tag lookup used by the settings changelog row."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui.bridge import update

NOTES = """# CampusTerminal 1.4.1

## 更新

- 启动时检查新版本。
- 新增「发现新版本后自动更新并重启」。

## 修复

- 修复周期重认证断线。

## 升级

- 从托盘退出后升级。
"""


class UpdateNotesTests(unittest.TestCase):
    def test_update_notes_keep_the_repair_section(self):
        notes = update.update_notes(NOTES)
        self.assertIn("启动时检查新版本", notes)
        self.assertIn("修复周期重认证断线", notes)
        self.assertNotIn("从托盘退出后升级", notes)

    def test_update_notes_empty_without_the_heading(self):
        self.assertEqual(update.update_notes("## 修复\n- 只有修复\n"), "")
        self.assertEqual(update.update_notes(""), "")
        self.assertEqual(update.update_notes(None), "")

    def test_format_and_parse_round_trip(self):
        self.assertEqual(update.format_version(update.parse_version("v1.4.1")), "1.4.1")
        self.assertEqual(update.format_version(None), "")


class TagLookupTests(unittest.TestCase):
    def test_release_notes_read_the_tag_endpoint(self):
        seen = []
        payload = json.dumps({"tag_name": "v1.4.1", "body": NOTES}).encode("utf-8")

        def read(_opener, request, _timeout):
            seen.append(request.full_url)
            return payload

        with patch.object(update, "_read", side_effect=read):
            notes = update.release_notes("1.4.1")
        self.assertEqual(seen, ["https://api.github.com/repos/" + update.REPO + "/releases/tags/v1.4.1"])
        self.assertIn("启动时检查新版本", notes)

    def test_release_notes_prefer_the_readme_asset(self):
        blob = NOTES.encode("utf-8")
        digest = hashlib.sha256(blob).hexdigest()
        asset = {"name": "README.md", "digest": "sha256:" + digest, "size": len(blob),
                 "browser_download_url": "https://github.com/" + update.REPO + "/releases/download/v1.4.1/README.md"}
        payload = json.dumps({"tag_name": "v1.4.1", "body": "## 更新\n- 正文", "assets": [asset]}).encode("utf-8")
        seen = []

        def read(_opener, request, _timeout):
            seen.append(request.full_url)
            return payload if len(seen) == 1 else blob

        with patch.object(update, "_read", side_effect=read):
            notes = update.release_notes("1.4.1")
        self.assertEqual(len(seen), 2)
        self.assertIn("修复周期重认证断线", notes)

    def test_release_notes_mismatched_digest_falls_back_to_the_body(self):
        asset = {"name": "README.md", "digest": "sha256:" + "0" * 64, "size": 4,
                 "browser_download_url": "https://github.com/" + update.REPO + "/releases/download/v1.4.1/README.md"}
        payload = json.dumps({"tag_name": "v1.4.1", "body": NOTES, "assets": [asset]}).encode("utf-8")
        seen = []

        def read(_opener, request, _timeout):
            seen.append(request.full_url)
            return payload if len(seen) == 1 else b"junk"

        with patch.object(update, "_read", side_effect=read):
            notes = update.release_notes("1.4.1")
        self.assertIn("启动时检查新版本", notes)

    def test_release_notes_fail_quietly(self):
        with patch.object(update, "_read", side_effect=OSError("offline")):
            self.assertEqual(update.release_notes("1.4.1"), "")
        self.assertEqual(update.release_notes("not-a-version"), "")

    def test_release_notes_reject_a_mismatched_tag(self):
        payload = json.dumps({"tag_name": "v9.9.9", "body": NOTES}).encode("utf-8")
        with patch.object(update, "_read", return_value=payload):
            self.assertEqual(update.release_notes("1.4.1"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
