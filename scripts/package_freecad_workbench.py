"""Build a clean, installable companion ZIP from checked-in source files."""
import argparse
import hashlib
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
args = parser.parse_args()
target = Path(args.output).resolve()
source = root / "integrations/freecad/SPIKEWorkbench"
if target.exists(): raise SystemExit("Output already exists; select a new ZIP path.")
if (root / "python/spike_core/mcad_session_contract.py").read_bytes() != (source / "spike_freecad/session_contract.py").read_bytes():
    raise SystemExit("Run scripts/sync_freecad_contract.py before packaging.")
target.parent.mkdir(parents=True, exist_ok=True)
files = sorted(p for p in source.rglob("*") if p.is_file() and not p.is_symlink()
               and "__pycache__" not in p.parts and (p.suffix in {".py", ".json", ".svg", ".xml", ".md", ".jpg", ".png"} or p.name == "LICENSE"))
with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in files: archive.write(path, "SPIKEWorkbench/" + path.relative_to(source).as_posix())
with zipfile.ZipFile(target) as archive:
    if archive.testzip() is not None: raise RuntimeError("Workbench archive verification failed.")
print(f"{target}\n{len(files)} files; SHA-256 {hashlib.sha256(target.read_bytes()).hexdigest()}")
