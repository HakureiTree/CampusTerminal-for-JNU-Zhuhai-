# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the release manifest, full payload, and an optional delta from two manifests."""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

PROTECTED_FILES = {"edition.txt", "campusterminal.portable"}
PROTECTED_DIRS = {"state", "logs", "payload", "__pycache__"}


def _rel(path):
    return path.replace("\\", "/").strip("/")


def included(rel):
    rel = _rel(rel)
    if not rel or rel.endswith(".pdb") or rel.endswith(".pyc"):
        return False
    name = rel.split("/")[-1].lower()
    if name in PROTECTED_FILES:
        return False
    return rel.split("/", 1)[0].lower() not in PROTECTED_DIRS


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(source):
    root = Path(source)
    prefix = str(root.resolve())
    found = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        full = str(path.resolve())
        rel = _rel(full[len(prefix):].lstrip("\\/"))
        if not included(rel):
            continue
        found.append({"path": rel, "sha256": _sha256(path), "size": path.stat().st_size, "full": path})
    found.sort(key=lambda item: item["path"])
    return found


def _zip(destination, entries):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in entries:
            archive.write(item["full"], item["path"].replace("\\", "/"))


def _write_json(path, payload):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def payload_name(version):
    return "CampusTerminal-" + version + "-windows-x64-payload.zip"


def delta_name(version, base):
    return "CampusTerminal-" + version + "-delta-from-" + base + ".zip"


def write_release(source, output_dir, version):
    files = iter_files(source)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    name = payload_name(version)
    _zip(output / name, files)
    manifest = {
        "version": version,
        "files": [{"path": item["path"], "sha256": item["sha256"], "size": item["size"]} for item in files],
        "payload": name,
        "deltas": [],
    }
    _write_json(output / "update-manifest.json", manifest)
    return manifest


def write_delta(base_manifest, new_manifest, new_tree, output_dir):
    base = json.loads(Path(base_manifest).read_text(encoding="utf-8-sig"))
    new = json.loads(Path(new_manifest).read_text(encoding="utf-8-sig"))
    base_version = str(base["version"])
    new_version = str(new["version"])
    previous = {item["path"]: item["sha256"].lower() for item in base.get("files") or []}
    tree = {item["path"]: item for item in iter_files(new_tree)}
    changed = []
    for item in new.get("files") or []:
        rel = _rel(item["path"])
        if previous.get(rel) == str(item["sha256"]).lower():
            continue
        if rel not in tree:
            raise SystemExit("delta source missing: " + rel)
        if tree[rel]["sha256"] != str(item["sha256"]).lower():
            raise SystemExit("delta hash mismatch: " + rel)
        changed.append(tree[rel])
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    name = delta_name(new_version, base_version)
    _zip(output / name, changed)
    deltas = [item for item in new.get("deltas") or [] if item.get("from") != base_version]
    deltas.append({"from": base_version, "asset": name, "files": [item["path"] for item in changed]})
    published = {
        "version": new_version,
        "files": [{"path": item["path"], "sha256": item["sha256"], "size": item["size"]} for item in new.get("files") or []],
        "payload": new.get("payload") or payload_name(new_version),
        "deltas": deltas,
    }
    _write_json(output / "update-manifest.json", published)
    return published


def _main(argv):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    release = sub.add_parser("release")
    release.add_argument("--source", required=True)
    release.add_argument("--output", required=True)
    release.add_argument("--version", required=True)
    delta = sub.add_parser("delta")
    delta.add_argument("--base-manifest", required=True)
    delta.add_argument("--new-manifest", required=True)
    delta.add_argument("--new-tree", required=True)
    delta.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "release":
        write_release(args.source, args.output, args.version)
        return 0
    write_delta(args.base_manifest, args.new_manifest, args.new_tree, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
