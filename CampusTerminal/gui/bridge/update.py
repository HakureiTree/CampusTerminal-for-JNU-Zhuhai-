# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the public GitHub release and plan an incremental file replace."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

REPO = "HakureiTree/CampusTerminal-for-JNU-Zhuhai-"
LATEST_URL = "https://api.github.com/repos/" + REPO + "/releases/latest"
ALLOWED_HOSTS = frozenset({
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
    "api.github.com",
})
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:\.0+)?$")
_NOTES = re.compile(r"(?m)^##\s*更新\s*$")
_NEXT = re.compile(r"(?m)^##(?!#)[ \t]*\S")
_FIXES = re.compile(r"(?m)^##[ \t]*修复[ \t]*$")
_HEX = re.compile(r"^[0-9a-f]{64}$")
PROTECTED_FILES = frozenset({"edition.txt", "campusterminal.portable"})
PROTECTED_DIRS = frozenset({"state", "logs", "payload"})
EMPTY_NOTES = "该版本未提供更新说明。"


def parse_version(text):
    if text is None:
        return None
    match = _VERSION.fullmatch(str(text).strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def format_version(version):
    if not version:
        return ""
    return str(version[0]) + "." + str(version[1]) + "." + str(version[2])


def local_version(install_root, frozen, fallback):
    root = Path(install_root)
    if frozen:
        marker = root / "version.txt"
        if marker.is_file():
            parsed = parse_version(marker.read_text(encoding="utf-8-sig"))
            if parsed:
                return parsed
    return parse_version(fallback)


def display_version():
    from gui import theme as T
    from gui.bridge.paths import frozen, install_root
    parsed = local_version(install_root(), frozen(), T.APP_VERSION)
    return format_version(parsed) if parsed else str(T.APP_VERSION)


def update_notes(markdown):
    if not markdown:
        return ""
    text = str(markdown).replace("\r\n", "\n").replace("\r", "\n")
    match = _NOTES.search(text)
    if not match:
        return ""
    rest = text[match.end():]
    if rest.startswith("\n"):
        rest = rest[1:]
    nxt = _NEXT.search(rest)
    if nxt:
        fixes = _FIXES.match(rest, nxt.start())
        if fixes:
            nxt = _NEXT.search(rest, fixes.end())
    body = rest[:nxt.start()] if nxt else rest
    return body.strip()


def notes_or_fallback(markdown):
    body = update_notes(markdown)
    return body if body else EMPTY_NOTES


def offer_visible(local, remote, ignored):
    if local is None or remote is None or remote <= local:
        return False
    if ignored is not None and remote <= ignored:
        return False
    return True


def github_url_allowed(url):
    try:
        parts = urlsplit(str(url))
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and host in ALLOWED_HOSTS


def normalize_rel(path):
    text = str(path or "").replace("\\", "/").strip()
    if not text or text.startswith("/") or ":" in text.split("/", 1)[0]:
        return None
    parts = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)
    if not parts:
        return None
    return "/".join(parts)


def protected_rel(path):
    rel = normalize_rel(path)
    if rel is None:
        return True
    lowered = rel.lower()
    if lowered in PROTECTED_FILES:
        return True
    return lowered.split("/", 1)[0] in PROTECTED_DIRS


def _digest(value):
    text = str(value or "").strip().lower()
    if text.startswith("sha256:"):
        text = text.split(":", 1)[1]
    return text if _HEX.fullmatch(text) else None


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_index(manifest):
    found = {}
    for item in (manifest or {}).get("files") or []:
        if not isinstance(item, dict):
            raise ValueError("manifest file")
        rel = normalize_rel(item.get("path"))
        if rel is None or protected_rel(rel):
            raise ValueError("manifest path")
        digest = _digest(item.get("sha256"))
        if not digest:
            raise ValueError("manifest hash")
        size = item.get("size")
        found[rel] = (digest, None if size is None else int(size))
    return found


def changed_paths(install_root, manifest):
    root = Path(install_root)
    expected = manifest_index(manifest)
    changed, hashes = [], {}
    for rel, (digest, _size) in expected.items():
        dest = root / rel
        if dest.is_file():
            current = sha256_file(dest)
            hashes[rel] = current
            if current != digest:
                changed.append(rel)
        else:
            changed.append(rel)
    return changed, hashes


def choose_package(local, manifest, changed):
    if not isinstance(manifest, dict) or local is None:
        return None
    needed = set()
    for path in changed or []:
        rel = normalize_rel(path)
        if rel is None:
            return None
        needed.add(rel)
    local_text = format_version(local)
    for delta in manifest.get("deltas") or []:
        if not isinstance(delta, dict) or delta.get("from") != local_text or not delta.get("asset"):
            continue
        listed = delta.get("files")
        if not isinstance(listed, list):
            continue
        names = {normalize_rel(path) for path in listed}
        if None not in names and needed <= names:
            return {"kind": "delta", "asset": str(delta["asset"])}
    payload = manifest.get("payload")
    if payload:
        return {"kind": "full", "asset": str(payload)}
    return None


def _inside(path, root):
    resolved = Path(path).resolve()
    base = Path(root).resolve()
    return resolved == base or base in resolved.parents


def plan_files(install_root, staged_root, manifest, local_hashes):
    root = Path(install_root).resolve()
    staged = Path(staged_root).resolve()
    expected = manifest_index(manifest)
    planned = []
    for rel, (digest, _size) in expected.items():
        current = str((local_hashes or {}).get(rel, "")).lower()
        if current == digest:
            continue
        src = (staged / rel).resolve()
        dest = (root / rel).resolve()
        if not _inside(src, staged) or not _inside(dest, root):
            raise ValueError("path escape")
        if not src.is_file():
            raise ValueError("missing staged file")
        planned.append({"src": str(src), "dest": str(dest), "sha256": digest, "path": rel})
    return planned


def payload_name(version_text):
    return "CampusTerminal-" + version_text + "-windows-x64-payload.zip"


def delta_name(version_text, base_text):
    return "CampusTerminal-" + version_text + "-delta-from-" + base_text + ".zip"


class _RedirectGuard(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not github_url_allowed(newurl):
            raise ValueError("redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener():
    return urllib.request.build_opener(_RedirectGuard)


def _request(url, user_agent, accept):
    if not github_url_allowed(url):
        raise ValueError("url")
    return urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": accept})


def _read(opener, request, timeout):
    with opener.open(request, timeout=timeout) as response:
        return response.read()


def download_verified(asset, dest, opener, timeout, user_agent):
    if not isinstance(asset, dict):
        raise ValueError("asset")
    digest = _digest(asset.get("digest"))
    if not digest:
        raise ValueError("digest")
    size = asset.get("size")
    if size is None:
        raise ValueError("size")
    url = asset.get("browser_download_url") or ""
    data = _read(opener, _request(url, user_agent, "application/octet-stream"), timeout)
    if len(data) != int(size) or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("asset mismatch")
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def extract_package(zip_path, dest, manifest, required):
    expected = manifest_index(manifest)
    required_set = set()
    for path in required:
        rel = normalize_rel(path)
        if rel is None or rel not in expected:
            raise ValueError("required path")
        required_set.add(rel)
    target = Path(dest)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    found = set()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            rel = normalize_rel(info.filename)
            if rel is None or protected_rel(rel) or rel not in expected:
                raise ValueError("zip path")
            digest, size = expected[rel]
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            if (size is not None and out.stat().st_size != size) or sha256_file(out) != digest:
                raise ValueError("zip file")
            found.add(rel)
    if not required_set <= found:
        raise ValueError("incomplete package")
    return found


def _asset_map(assets):
    found = {}
    for asset in assets or []:
        if isinstance(asset, dict) and asset.get("name"):
            found[str(asset["name"])] = asset
    return found


def fetch_offer(user_agent, opener=None, timeout=20):
    opener = opener or build_opener()
    raw = _read(opener, _request(LATEST_URL, user_agent, "application/vnd.github+json"), timeout)
    release = json.loads(raw.decode("utf-8"))
    remote = parse_version(release.get("tag_name"))
    if not isinstance(release, dict) or remote is None:
        return None
    assets = release.get("assets") if isinstance(release.get("assets"), list) else []
    notes = ""
    readme = _asset_map(assets).get("README.md")
    if readme:
        try:
            blob = _read(opener, _request(readme.get("browser_download_url"), user_agent, "application/octet-stream"), timeout)
            digest = _digest(readme.get("digest"))
            size = readme.get("size")
            if not digest or size is None or len(blob) != int(size) or hashlib.sha256(blob).hexdigest() != digest:
                raise ValueError("readme")
            notes = update_notes(blob.decode("utf-8"))
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
            notes = ""
    if not notes:
        notes = update_notes(release.get("body") or "")
    return {
        "version": format_version(remote),
        "notes": notes,
        "assets": [
            {"name": item.get("name"), "browser_download_url": item.get("browser_download_url"),
             "digest": item.get("digest"), "size": item.get("size")}
            for item in assets if isinstance(item, dict)
        ],
    }


def release_notes(version):
    """Return a released version's notes through the tag API, or '' when unavailable."""
    parsed = parse_version(version)
    if parsed is None:
        return ""
    text = format_version(parsed)
    tag = "v" + text
    url = "https://api.github.com/repos/" + REPO + "/releases/tags/" + tag
    user_agent = "CampusTerminal/" + text
    opener = build_opener()
    try:
        payload = json.loads(_read(opener, _request(url, user_agent, "application/vnd.github+json"), 20).decode("utf-8"))
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict) or payload.get("tag_name") not in (tag, text):
        return ""
    notes = ""
    readme = _asset_map(payload.get("assets")).get("README.md")
    if readme:
        try:
            blob = _read(opener, _request(readme.get("browser_download_url"), user_agent,
                                          "application/octet-stream"), 20)
            digest = _digest(readme.get("digest"))
            size = readme.get("size")
            if not digest or size is None or len(blob) != int(size) or hashlib.sha256(blob).hexdigest() != digest:
                raise ValueError("readme")
            notes = update_notes(blob.decode("utf-8"))
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
            notes = ""
    if not notes:
        notes = update_notes(payload.get("body") or "")
    return notes


def updates_root():
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise OSError("LOCALAPPDATA")
    return Path(local) / "CampusTerminal" / "updates"


def result_path():
    return updates_root() / "update-result.json"


def consume_result():
    path = result_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError):
        payload = {"ok": False, "error": "更新结果无法读取"}
    try:
        path.unlink()
    except OSError:
        pass
    return payload if isinstance(payload, dict) else {"ok": False, "error": "更新结果无法读取"}


def _stage_package(kind, asset_name, assets, manifest, changed, staging, opener, timeout, user_agent):
    asset = assets.get(asset_name)
    if not asset:
        raise ValueError("missing asset")
    archive = staging / (kind + ".zip")
    download_verified(asset, archive, opener, timeout, user_agent)
    extract_package(archive, staging / "files", manifest, changed)
    return staging / "files"


def prepare_transaction(install_root, offer, silent, pid, script_source, opener=None, timeout=60):
    opener = opener or build_opener()
    remote = parse_version((offer or {}).get("version"))
    if remote is None:
        raise ValueError("version")
    version_text = format_version(remote)
    from gui import theme as T
    local = local_version(install_root, True, T.APP_VERSION)
    user_agent = "CampusTerminal/" + (format_version(local) or T.APP_VERSION)
    assets = _asset_map(offer.get("assets"))
    manifest_asset = assets.get("update-manifest.json")
    if not manifest_asset:
        raise ValueError("manifest")
    root = updates_root() / version_text
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    manifest_path = download_verified(manifest_asset, root / "update-manifest.json", opener, timeout, user_agent)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if parse_version(manifest.get("version")) != remote:
        raise ValueError("manifest version")
    changed, hashes = changed_paths(install_root, manifest)
    if not changed:
        return None
    choice = choose_package(local, manifest, changed)
    if not choice:
        raise ValueError("package")
    files_root = None
    if choice["kind"] == "delta":
        try:
            files_root = _stage_package("delta", choice["asset"], assets, manifest, changed, root / "delta", opener, timeout, user_agent)
        except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
            files_root = None
    if files_root is None:
        payload = manifest.get("payload")
        if not payload:
            raise ValueError("payload")
        files_root = _stage_package("full", str(payload), assets, manifest, changed, root / "full", opener, timeout, user_agent)
    planned = plan_files(install_root, files_root, {"files": [
        item for item in manifest.get("files") or [] if normalize_rel(item.get("path")) in set(changed)
    ]}, hashes)
    if not planned:
        return None
    source = Path(script_source)
    if not source.is_file():
        raise ValueError("updater missing")
    script = root / "Apply-Update.ps1"
    shutil.copyfile(source, script)
    install = Path(install_root)
    launcher = install / "开源暨珠有线网络终端.exe"
    if not launcher.is_file():
        launcher = install / "CampusTerminal.exe"
    transaction = {
        "install_root": str(install.resolve()),
        "staging_root": str(files_root.resolve()),
        "files": [{"src": item["src"], "dest": item["dest"], "sha256": item["sha256"]} for item in planned],
        "relaunch": str(launcher),
        "relaunch_args": ["--silent"] if silent else [],
        "wait_pids": [int(pid)],
        "wait_names": ["CampusTerminal", "CampusTerminal.Core"],
        "result_path": str(result_path()),
        "backup_root": str((root / "backup").resolve()),
    }
    path = root / "transaction.json"
    path.write_text(json.dumps(transaction), encoding="utf-8")
    return {"transaction": str(path), "script": str(script)}


def spawn_apply(script, transaction):
    system = os.environ.get("SystemRoot")
    if not system:
        raise OSError("SystemRoot")
    powershell = Path(system) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    flags = 0x00000008 | 0x00000200 | 0x08000000
    return subprocess.Popen(
        [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script), "-Transaction", str(transaction)],
        creationflags=flags, close_fds=True)


def apply_script_path(install_root, frozen):
    root = Path(install_root)
    if frozen:
        return root / "Apply-Update.ps1"
    return Path(__file__).resolve().parents[2] / "packaging" / "Apply-Update.ps1"
