"""Capture/verify source identities to detect concurrent edits during packaging."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ("python", "app/src", "app/public", "app/src-tauri/src", "schemas", "extensions", "tests/python", "app/scripts")
FILES = ("app/package.json", "app/package-lock.json", "app/src-tauri/Cargo.toml",
         "app/src-tauri/Cargo.lock", "app/src-tauri/tauri.conf.json",
         "scripts/build_packaged_worker.py", "scripts/build_windows_installer.ps1",
         "build-spikes-hybrid/spikes_c_api.dll")
SUFFIXES = {".py", ".pyi", ".pyd", ".dll", ".rs", ".ts", ".tsx", ".css", ".json", ".mjs", ".html", ".svg", ".png"}


def snapshot():
    paths = {ROOT / name for name in FILES}
    for name in DIRECTORIES:
        paths.update(path for path in (ROOT / name).rglob("*")
                     if path.is_file() and path.suffix in SUFFIXES
                     and "__pycache__" not in path.parts
                     # Some numerical tests emit disposable fixtures under
                     # python/build; these are not packaged source inputs.
                     and not path.is_relative_to(ROOT / "python/build"))
    result = {}
    for path in sorted(paths):
        with path.open("rb") as stream:
            result[path.relative_to(ROOT).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    current = snapshot()
    if args.verify:
        expected = json.loads(args.output.read_text(encoding="utf-8"))
        changed = sorted(key for key in expected.keys() | current.keys()
                         if expected.get(key) != current.get(key))
        print(json.dumps({"status": "changed" if changed else "unchanged", "files": len(current), "changed": changed}))
        return int(bool(changed))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(current)} source identities: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
