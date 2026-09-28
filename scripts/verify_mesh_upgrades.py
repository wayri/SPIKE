# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Local source-stable mesh/basis regression and timing evidence."""
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    modules = ["local_mesh_controls", "tetra_mesh_refinement", "tetra_mesh_optimization",
               "mom_surface_basis", "openfoam_polymesh", "hybrid_mesh_containment"]
    paths = [ROOT / "tests/python" / ("test_" + name + ".py") for name in modules]
    paths += [ROOT / "python/spike_core" / (name + ".py") for name in modules[:-1] + ["hybrid_mesh"]]
    paths += [Path(__file__), ROOT / "examples/mesh/run_mesh_upgrades.py", ROOT / "schemas/solver-mesh-v1.schema.json"]
    before = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    output = ROOT / "build" / ("mesh-evidence-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"))
    output.mkdir()
    tests = subprocess.run([sys.executable, "-W", "error", "-m", "unittest",
        *("tests.python.test_" + name for name in modules), "-q"], cwd=ROOT,
        text=True, capture_output=True, timeout=120)
    (output / "tests.log").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    samples, runs = [], []
    for index in range(6):
        start = time.perf_counter()
        run = subprocess.run([sys.executable, "-W", "error", str(ROOT / "examples/mesh/run_mesh_upgrades.py"),
            "--output", str(output / f"example-{index}")], cwd=ROOT, text=True, capture_output=True, timeout=60)
        elapsed = time.perf_counter()-start
        (output / f"example-{index}.log").write_text(run.stdout+run.stderr, encoding="utf-8")
        runs.append(run.returncode)
        if index:
            samples.append(elapsed)
    stable = before == {str(p.relative_to(ROOT)): sha(p) for p in paths}
    report = {"contract": "spike/local-mesh-evidence/v1", "production_qualified": False,
        "status": "passed" if tests.returncode == 0 and all(v == 0 for v in runs) and stable else "failed",
        "machine": {"platform": platform.platform(), "python": sys.version},
        "source_sha256": before, "source_unchanged": stable, "test_exit_code": tests.returncode,
        "example_exit_codes": runs, "samples_s": samples, "median_s": statistics.median(samples),
        "timing_method": "One warmup plus five measured full example subprocesses including startup and artifact I/O; no performance acceptance baseline",
        "scope": "Mesh/basis operation, not field-solver accuracy or production qualification"}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    (output / "SHA256.json").write_text(json.dumps({str(p.relative_to(output)): sha(p)
        for p in output.rglob("*") if p.is_file()}, indent=2), encoding="utf-8")
    print(report["status"], output)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
