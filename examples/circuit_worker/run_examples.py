# SPDX-License-Identifier: Apache-2.0
"""Run bounded owned-SPICE and fail-closed IBIS process examples.

This is qualification-oriented example glue, not a general SPICE/IBIS API.
It never accepts raw SPICE text or executable IBIS/AMI models.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any


EXAMPLE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from python.spike_core.circuit_worker_supervisor import (  # noqa: E402
    run_circuit_worker,
    sha256_file,
    supervise_process,
)


def owned_spice_job() -> dict[str, Any]:
    return {
        "contract": "spike/owned-spice-process-job/v1",
        "design": {
            "contract": "spike/v1", "design_id": "example-divider",
            "name": "Structured divider example", "source_format": "generated",
            "source_path": "", "units": "mm", "layers": [], "nets": [],
            "tracks": [], "vias": [], "zones": [], "component_bonds": [],
            "connectors": [], "stackup": [], "technology": "rigid",
            "regions": [], "bends": [], "issues": [], "metadata": {},
            "pads": [
                {"id": "v-p", "ref": "V1", "name": "1", "net_name": "VIN"},
                {"id": "v-n", "ref": "V1", "name": "2", "net_name": "GND"},
                {"id": "r-p", "ref": "R1", "name": "1", "net_name": "VIN"},
                {"id": "r-n", "ref": "R1", "name": "2", "net_name": "GND"},
            ],
            "components": [
                {"id": "source", "reference": "V1"},
                {"id": "load", "reference": "R1"},
            ],
        },
        "circuit_request": {
            "contract": "spike/owned-spice-workspace-request/v1",
            "request_id": "example-divider-op",
            "workspace": {
                "contract": "spike/spice-workspace/v1", "name": "Example divider",
                "domain": "pi", "ground_node": "GND",
                "models": [
                    {"id": "supply", "kind": "primitive", "primitive": "voltage_source",
                     "pins": ["p", "n"], "value": "1.2", "origin": "built_in",
                     "parameters": {"dc_value": 1.2}},
                    {"id": "load", "kind": "primitive", "primitive": "resistor",
                     "pins": ["p", "n"], "value": "120", "origin": "built_in",
                     "parameters": {"resistance_ohm": 120.0}},
                ],
                "assignments": [
                    {"id": "supply-map", "component_ref": "V1", "model_id": "supply",
                     "enabled": True, "pin_bindings": [
                         {"model_pin": "p", "pad_id": "v-p", "circuit_node": "VIN"},
                         {"model_pin": "n", "pad_id": "v-n", "circuit_node": "GND"},
                     ]},
                    {"id": "load-map", "component_ref": "R1", "model_id": "load",
                     "enabled": True, "pin_bindings": [
                         {"model_pin": "p", "pad_id": "r-p", "circuit_node": "VIN"},
                         {"model_pin": "n", "pad_id": "r-n", "circuit_node": "GND"},
                     ]},
                ],
                "parasitics": [], "analysis": {"mode": "operating_point"},
            },
            "probes": ["V(VIN)", "I(V1)", "P(R1)"],
            "resource_limits": {
                "maximum_netlist_bytes": 2 * 1024 * 1024,
                "maximum_result_bytes": 4 * 1024 * 1024,
                "maximum_probes": 8,
            },
        },
    }


def package_paths() -> tuple[Path, Path, dict[str, Any]]:
    package_root = REPO_ROOT / "app" / "src-tauri" / "resources" / "worker"
    manifest_path = package_root / "spike-circuit-worker.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = package_root / "spike-circuit-worker"
    worker = artifact / ("spike-circuit-worker.exe" if sys.platform == "win32" else "spike-circuit-worker")
    library = artifact / "_internal" / "spikes" / (
        "spikes_c_api.dll" if sys.platform == "win32" else "libspikes_c_api.so"
    )
    for item in manifest["files"]:
        path = artifact / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"package manifest admission failed for {item['path']}")
    return worker.resolve(strict=True), library.resolve(strict=True), manifest


def run_spice_examples() -> list[dict[str, Any]]:
    worker, library, manifest = package_paths()
    worker_sha = sha256_file(worker)
    library_sha = sha256_file(library)
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="spike-owned-spice-example-") as directory:
        root = Path(directory).resolve(strict=True)
        job = root / "job"
        job.mkdir()
        (job / "request.json").write_text(
            json.dumps(owned_spice_job(), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        outcome = run_circuit_worker(
            worker_executable=worker, worker_sha256=worker_sha,
            library_path=library, library_sha256=library_sha,
            job_root=root, request="job/request.json", result="job/result.json",
            timeout_seconds=30, memory_limit_mib=256,
        )
        result = json.loads((job / "result.json").read_text(encoding="utf-8"))
        if outcome.returncode != 0 or result.get("status") != "completed":
            raise RuntimeError("packaged structured owned-SPICE solve did not complete")
        probes = result["circuit"]["circuit_result"]["probes"]
        voltage_v = probes["V(VIN)"]["value"]
        source_current_a = probes["I(V1)"]["value"]
        load_power_w = probes["P(R1)"]["value"]
        if not (
            abs(voltage_v - 1.2) <= 1e-12
            and abs(source_current_a + 0.01) <= 1e-12
            and abs(load_power_w - 0.012) <= 1e-12
        ):
            raise RuntimeError("packaged structured solve returned unexpected probe values")
        records.append({
            "example": "owned_spice_structured_operating_point", "status": "passed",
            "os_enforcement": outcome.os_enforcement,
            "worker_sha256": worker_sha,
            "owned_library_sha256": library_sha,
            "package_file_count": len(manifest["files"]),
            "vin_v": voltage_v,
            "source_current_a": source_current_a,
            "load_power_w": load_power_w,
        })

        if "ibis" in json.dumps(manifest["capability"]).lower():
            raise RuntimeError("example assumptions are stale: an IBIS process capability now exists")
        records.append({
            "example": "ibis_process_capability_absent", "status": "passed",
            "expected_state": "not_advertised_by_packaged_worker",
        })

        attempted_ibis = owned_spice_job()
        attempted_ibis["circuit_request"]["ibis_payload"] = (
            "[IBIS Ver] 8.0\n[Component] MUST_NOT_BE_READ\n[End]\n"
        )
        (job / "request.json").write_text(
            json.dumps(attempted_ibis, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        ibis_outcome = run_circuit_worker(
            worker_executable=worker, worker_sha256=worker_sha,
            library_path=library, library_sha256=library_sha,
            job_root=root, request="job/request.json", result="job/result.json",
            timeout_seconds=30, memory_limit_mib=256,
        )
        ibis_result = json.loads((job / "result.json").read_text(encoding="utf-8"))
        if ibis_outcome.returncode != 2 or ibis_result.get("status") == "completed":
            raise RuntimeError(
                "unadvertised IBIS payload was not rejected by the process boundary: "
                f"returncode={ibis_outcome.returncode} result_status={ibis_result.get('status')}"
            )
        ibis_issues = ibis_result.get("issues") or ibis_result.get("circuit", {}).get("issues", [])
        records.append({
            "example": "unadvertised_ibis_payload_rejection", "status": "passed",
            "worker_returncode": ibis_outcome.returncode,
            "result_status": ibis_result.get("status"),
            "issue_code": ibis_issues[0]["code"] if ibis_issues else "not_reported",
        })

        (job / "request.json").write_text(
            json.dumps(owned_spice_job(), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

        try:
            run_circuit_worker(
                worker_executable=worker, worker_sha256="0" * 64,
                library_path=library, library_sha256=library_sha,
                job_root=root, request="job/request.json", result="job/result.json",
            )
            raise RuntimeError("tampered worker identity was accepted")
        except ValueError as error:
            if "SHA-256 admission failed" not in str(error):
                raise
            records.append({"example": "worker_hash_rejection", "status": "passed"})

        try:
            run_circuit_worker(
                worker_executable=worker, worker_sha256=worker_sha,
                library_path=library, library_sha256=library_sha,
                job_root=root, request="job/../job/request.json", result="job/result.json",
            )
            raise RuntimeError("path traversal was accepted")
        except ValueError as error:
            if "normalized and job-relative" not in str(error):
                raise
            records.append({"example": "control_path_rejection", "status": "passed"})

    timed = supervise_process(
        Path(sys.executable).resolve(strict=True),
        ["-c", "import time; time.sleep(30)"], cwd=EXAMPLE_ROOT,
        timeout_seconds=0.15, memory_limit_mib=256,
    )
    if timed.status != "timeout":
        raise RuntimeError("supervisor timeout example did not terminate the child")
    records.append({
        "example": "supervisor_timeout", "status": "passed",
        "os_enforcement": timed.os_enforcement,
    })
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    records = run_spice_examples()
    for record in records:
        print(json.dumps(record, sort_keys=True, separators=(",", ":")))
    print(json.dumps({
        "contract": "spike/circuit-worker-example-report/v1",
        "status": "passed", "validation_state": "example_only",
        "passed": len(records), "failed": 0,
        "scope": "structured-owned-spice;ibis-process-unavailable-and-rejected",
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
