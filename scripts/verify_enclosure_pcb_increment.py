# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Local, hashed numerical/adapter evidence; not production qualification."""
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.enclosure_stokes import solve_enclosure_stokes


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    modules = ["enclosure_stokes", "pcb_entity_ports", "openems_geometry_admission",
               "openems_pad_geometry", "openems_far_field", "openems_far_field_normalization",
               "laminar_channel_cht", "huygens_far_field"]
    sources = [ROOT / "python/spike_core" / (name + ".py") for name in
        ("enclosure_stokes", "pcb_entity_ports", "openems_geometry_admission", "openems_adapter_source",
         "external_engines", "openems_validation", "laminar_channel_cht", "huygens_far_field")]
    sources += [ROOT / "tests/python" / ("test_" + name + ".py") for name in modules]
    sources += [Path(__file__), ROOT / "examples/thermal/enclosure_stokes_request.json",
                ROOT / "scripts/run_structured_solid_thermal.py", ROOT / "examples/em/run_entity_port_patch.py"]
    before = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    output = ROOT / "build" / ("enclosure-pcb-evidence-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"))
    output.mkdir()
    tests = subprocess.run([sys.executable, "-W", "error", "-m", "unittest",
        *("tests.python.test_" + name for name in modules), "-q"], cwd=ROOT,
        text=True, capture_output=True, timeout=120)
    (output / "tests.log").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    request = json.loads((ROOT / "examples/thermal/enclosure_stokes_request.json").read_text())
    samples, checks, result = [], [], {}
    for index in range(6):
        start = time.perf_counter()
        result = solve_enclosure_stokes(request)
        elapsed = time.perf_counter() - start
        if index:
            samples.append(elapsed)
        checks.append(result.get("status") == "completed")
    (output / "flow-result.json").write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    after = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    report = {"contract": "spike/local-enclosure-pcb-evidence/v1", "production_qualified": False,
        "status": "passed" if tests.returncode == 0 and all(checks) and before == after else "failed",
        "machine": {"platform": platform.platform(), "python": sys.version},
        "source_sha256": before, "source_unchanged": before == after,
        "test_exit_code": tests.returncode, "timing_method": "one warmup, five measured runs",
        "samples_s": samples, "median_s": statistics.median(samples),
        "flow_diagnostics": result.get("diagnostics"),
        "limits": ["Local reference, no production qualification",
            "Closed creeping-flow voxels, not full enclosure thermal/airflow",
            "Adapter unit tests are not actual FDTD; real cases are separately retained"]}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    (output / "SHA256.json").write_text(json.dumps({p.name: sha(p) for p in output.iterdir()
        if p.is_file()}, indent=2), encoding="utf-8")
    print(report["status"], output)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
