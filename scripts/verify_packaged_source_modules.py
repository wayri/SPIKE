"""Compare frozen Python code with current source without executing either.

Use the build's exact Python interpreter. File names are normalized because
PyInstaller relocates them; instructions, constants and line tables must match.
Native libraries/data are covered separately by the packaged worker manifest.
"""
import argparse
import json
from pathlib import Path
import types

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]


def normalized(code):
    return code.replace(co_filename="", co_consts=tuple(
        normalized(value) if isinstance(value, types.CodeType) else value
        for value in code.co_consts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    archive = CArchiveReader(str(args.executable)).open_embedded_archive("PYZ.pyz")
    checked, changed, missing = [], [], []
    for name in sorted(archive.toc):
        if name != "python" and not name.startswith("python."):
            continue
        base = ROOT.joinpath(*name.split("."))
        source = base.with_suffix(".py")
        if not source.is_file():
            source = base / "__init__.py"
        if not source.is_file():
            missing.append(name)
            continue
        frozen = archive.extract(name)
        current = compile(source.read_bytes(), str(source), "exec", optimize=0)
        checked.append(name)
        # Code equality compares constants semantically. Marshaled byte streams
        # can differ only in frozenset ordering under different hash seeds.
        if normalized(frozen) != normalized(current):
            changed.append(name)
    report = {"status": "passed" if checked and not changed and not missing else "failed",
              "checked_modules": len(checked), "changed": changed, "missing": missing}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
