"""Create paired ODB++ exports with the installed KiCad CLI, preserving inputs."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "build/public-board-corpus"
CLI = Path("C:/Program Files/KiCad/10.0/bin/kicad-cli.exe")
manifest_path = BASE / "manifest.json"
data = json.loads(manifest_path.read_text(encoding="utf-8"))
results = []
(BASE / "generated").mkdir(exist_ok=True)
for ident in ["constraints", "ecc83", "stickhub", "cm5-minima", "video", "olimex-a64"]:
    case = next(c for c in data["cases"] if c["id"] == ident)
    target = BASE / "generated" / (ident + ".zip")
    command = [str(CLI), "pcb", "export", "odb", "--compression", "zip", "--precision", "6", "--output", str(target), str(ROOT / case["local_path"])]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
    log = {"id": ident, "command": command, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    if result.returncode == 0 and target.is_file():
        generated = {"id": ident + "-odb", "format": "odb++", "local_path": target.relative_to(ROOT).as_posix(),
                     "derived_from": ident, "exporter": "KiCad CLI 10.0.5", "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        data["cases"] = [c for c in data["cases"] if c["id"] != generated["id"]] + [generated]
    results.append(log)
    print(ident, result.returncode, flush=True)
manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
(BASE / "generated/export-log.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
