# SPDX-License-Identifier: Apache-2.0
"""Execute existing bounded four-excitation box benchmark with extension source.

This is runtime/cross-board field evidence, not imported complete PCB geometry.
Snapshots the actual extension implementation rather than the compatibility
shim, which cannot import extensions inside the isolated stdin runtime.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_crossboard_openems import WORKER, fixture
from python.spike_core.solvers.external_engines.openems.openems_assembly_geometry import compile_assembly_geometry
from python.spike_core.external_engines import _run_isolated_python
from python.spike_core.runtime_locations import openems_python, openems_install_root
from python.spike_core.solvers.electromagnetics.fields.crossboard_field_screen import screen_case


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    if not 10 <= args.timeout <= 600:
        parser.error("timeout must be 10..600 seconds")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    paths = [ROOT / "extensions/openems_suite/openems_assembly_geometry.py",
             ROOT / "python/spike_core/solvers/electromagnetics/fields/multi_excitation_network.py",
             ROOT / "python/spike_core/solvers/geometry_meshing/preparation/crossboard_mesh.py"]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    sources = {str(path.relative_to(ROOT)): digest(path) for path in [*paths, ROOT / "scripts/run_crossboard_openems.py", Path(__file__)]}
    raw = fixture(4)
    compiled = compile_assembly_geometry(raw)
    payload = (source + "\nOUTPUT=" + repr(str(output)) + "\nRAW=" + repr(raw) +
               "\nGAP=4.\nMESH=2.\nMESH_LEVEL=0\nEND_CRITERIA=1e-7\nMAX_STEPS=120000\n" + WORKER).encode()
    for name, value in (("geometry.json", raw), ("compiled.json", compiled)):
        (output / name).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "USERPROFILE", "LD_LIBRARY_PATH") if key in os.environ}
    environment.update(OPENEMS_INSTALL_PATH=openems_install_root(), TEMP=str(output), TMP=str(output))
    begin = time.perf_counter()
    execution = _run_isolated_python(openems_python(), payload, [], cwd=output, environment=environment,
                                    log_path=output / "solver.log", output_root=output,
                                    timeout_seconds=args.timeout, output_limit_bytes=512 * 1024 ** 2)
    unchanged = all(digest(ROOT / path) == sha for path, sha in sources.items())
    report = {"contract": "spike/multiboard-em-acceptance/v1", "status": "executed" if execution["returncode"] == 0 and unchanged else "failed",
              "execution": execution, "elapsed_s": time.perf_counter() - begin, "machine": platform.platform(),
              "source_sha256": sources, "sources_unchanged": unchanged,
              "worker_sha256": hashlib.sha256(payload).hexdigest(), "production_qualified": False,
              "runtime_python": openems_python(), "runtime_root": openems_install_root(),
              "scope": "Two retained substrate boxes with traces/returns, four actual independent field excitations; not imported complete board geometry.",
              "artifact_sha256": {path.name: digest(path) for path in output.glob("*.json")}}
    (output / "execution.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    if report["status"] == "executed":
        try:
            screen = screen_case(output)
        except (ValueError, OSError, KeyError) as error:
            screen = {"status": "screen_failed", "error": str(error), "production_qualified": False}
        (output / "screening.json").write_text(json.dumps(screen, indent=2, allow_nan=False), encoding="utf-8")
        report["screening"] = screen
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["status"] == "executed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
