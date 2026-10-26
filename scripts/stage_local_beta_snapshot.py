# SPDX-License-Identifier: Apache-2.0
"""Stage a fresh, bounded local engineering-preview checkout without cleanup."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = {"python", "src", "scripts", "tests", "schemas", "examples", "extensions", "extension_sdk", "solver_sdk", "config", "licenses", "docs", "integrations", "cmake"}
APP_ROOTS = ("app/src/", "app/public/", "app/scripts/", "app/src-tauri/src/", "app/src-tauri/icons/", "app/src-tauri/capabilities/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--version", default="0.4.2-beta")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    target = args.destination.resolve()
    if target.exists() or target == ROOT or ROOT in target.parents:
        raise ValueError("Choose a fresh destination outside the live checkout; existing paths are never replaced.")
    inventory = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    paths = set()
    for name in inventory:
        p = Path(name)
        if not name or not (ROOT / p).is_file() or "__pycache__" in p.parts:
            continue
        if p.parts[0] in SOURCE_ROOTS or name.startswith(APP_ROOTS) or name.startswith("data/materials/") or p.parent.as_posix() in {".", "app", "app/src-tauri"}:
            if p.suffix not in {".pyc", ".pyo"}:
                paths.add(p)
    sys.path.insert(0, str(ROOT))
    from scripts.check_private_research import private_paths
    blocked = private_paths([p.as_posix() for p in paths])
    if blocked:
        raise ValueError(f"Private research cannot be staged: {blocked}")
    from python.spike_core.spikes_runtime import owned_library_path
    paths.add(owned_library_path().relative_to(ROOT))
    paths.update(p.relative_to(ROOT) for p in (ROOT / "python").glob("*.pyd"))
    paths.add(Path("app/src-tauri/resources/README.md"))
    native_root = ROOT / "build/ac-cht-alpha2-native-cht-current-20261024/Release"
    for name in ("spike_native_airflow.exe", "spike_native_cht.exe"):
        paths.add((native_root / name).relative_to(ROOT))
    bytes_total = sum((ROOT / p).stat().st_size for p in paths)
    print(json.dumps({"source_files": len(paths), "source_bytes": bytes_total, "destination": str(target), "version": args.version, "execute": args.execute}))
    if not args.execute:
        return
    if shutil.disk_usage(target.parent).free < bytes_total + 10 * 1024**3:
        raise ValueError("Destination requires source bytes plus 10 GiB build headroom.")
    target.mkdir()
    records = []
    for p in sorted(paths):
        destination = target / p
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / p, destination)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        if digest != hashlib.sha256((ROOT / p).read_bytes()).hexdigest():
            raise ValueError(f"Source changed during capture: {p}")
        records.append({"path": p.as_posix(), "sha256": digest})
    # Derive the admitted baseline; old candidate receipts remain unchanged.
    from scripts.release_automation import version
    source_version = version(ROOT)
    native_version = source_version.split("-")[0]
    target_native_version = args.version.split("-")[0]
    # Only the dedicated beta snapshot is versioned; ongoing source work is untouched.
    for name in ("app/package.json", "app/package-lock.json", "app/src-tauri/tauri.conf.json"):
        path = target / name
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
        obj["version"] = args.version
        if name.endswith("package-lock.json"): obj["packages"][""]["version"] = args.version
        path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    replacements = {
        "app/src/appVersion.ts": [(f'APP_VERSION = "{source_version}"', f'APP_VERSION = "{args.version}"')],
        "app/src-tauri/Cargo.toml": [(f'version = "{source_version}"', f'version = "{args.version}"')],
        "app/src-tauri/Cargo.lock": [(f'name = "spike-desktop"\nversion = "{source_version}"', f'name = "spike-desktop"\nversion = "{args.version}"')],
        "python/spike_core/__init__.py": [(f'__version__ = "{source_version}"', f'__version__ = "{args.version}"')],
        "CMakeLists.txt": [(f'project(SPIKE VERSION {native_version} ', f'project(SPIKE VERSION {target_native_version} ')],
    }
    for name, items in replacements.items():
        path = target / name
        text = path.read_text(encoding="utf-8")
        for old, new in items:
            if old not in text: raise ValueError(f"Version baseline changed: {name}")
            text = text.replace(old, new, 1)
        path.write_text(text, encoding="utf-8")
    (target / "RELEASE_SOURCE_MANIFEST.json").write_text(json.dumps({"source_root": str(ROOT), "files": records, "snapshot_version": args.version}, indent=2), encoding="utf-8")
    shutil.copytree(ROOT / "app/node_modules", target / "app/node_modules")
    # Retain the separate circuit worker until it is rebuilt and verified in this snapshot.
    (target / "app/src-tauri/resources/worker").mkdir(parents=True, exist_ok=True)
    (target / "build").mkdir(exist_ok=True)
    (target / "build/temp").mkdir()
    print("Snapshot staged; build and verification have not yet run.")


if __name__ == "__main__": main()
