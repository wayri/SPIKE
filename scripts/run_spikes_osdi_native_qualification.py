#!/usr/bin/env python3
"""Generate reproducible evidence for SPIKES' native OSDI callback boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spikes.hdl_frontend import OsdiModuleManifest  # noqa: E402
from python.spikes.osdi_runtime import (  # noqa: E402
    NativeOsdiCallbackRuntime, OsdiExecutionError,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qualify(root: Path) -> dict[str, object]:
    artifact = root / "artifacts" / "hdl-qualification-wave4-current" / "spikes_linear_resistor.osdi"
    source = root / "benchmarks" / "hdl" / "spikes_linear_resistor.va"
    compiler = root / "tools" / "hdl" / "openvaf" / "openvaf.exe"
    module = OsdiModuleManifest.create(
        module_id="qualification.linear_resistor",
        module_name="spikes_linear_resistor", artifact=artifact,
        source_sha256=sha256(source), compiler_sha256=sha256(compiler),
        osdi_abi_major=0, osdi_abi_minor=3,
        callbacks=("setup", "load", "noise", "trunc", "accept", "destroy"),
    )
    runtime = NativeOsdiCallbackRuntime()
    result = runtime.evaluate_dc(module, artifact, [1.0, 0.0])
    osdi = result["osdi_result"]
    expected = {
        (0, 0): 0.001, (0, 1): -0.001,
        (1, 0): -0.001, (1, 1): 0.001,
    }
    stamps = {
        (item["row"], item["column"]): item["value"]
        for item in osdi["jacobian"]
    }
    numeric_pass = (
        len(stamps) == len(expected)
        and all(abs(stamps.get(key, float("inf")) - value) <= 1e-12 for key, value in expected.items())
        and all(abs(actual - target) <= 1e-12 for actual, target in zip(osdi["residual"], [0.001, -0.001]))
    )
    hostile_fail_closed = False
    try:
        runtime.evaluate_dc(module, artifact.with_name("absent.osdi"), [1.0, 0.0], hostile_code=True)
    except OsdiExecutionError as exc:
        hostile_fail_closed = "hostile OSDI execution is unavailable" in str(exc)
    return {
        "contract": "spikes/osdi-native-qualification/v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "host": {"system": platform.system(), "machine": platform.machine()},
        "status": "passed" if numeric_pass and hostile_fail_closed else "failed",
        "native_callback_execution": True,
        "ngspice_in_callback_path": False,
        "osdi_abi": "0.3",
        "fixture": {
            "source": str(source), "source_sha256": sha256(source),
            "artifact": str(artifact), "artifact_sha256": sha256(artifact),
            "compiler": str(compiler), "compiler_sha256": sha256(compiler),
            "module_manifest_sha256": module.manifest_sha256,
        },
        "dc_callback_case": {
            "terminal_voltages": [1.0, 0.0], "residual": osdi["residual"],
            "jacobian": osdi["jacobian"], "numeric_tolerance": 1e-12,
            "passed": numeric_pass,
        },
        "containment": result["containment"],
        "hostile_code_request_fails_closed_before_artifact_lookup": hostile_fail_closed,
        "production_claim_eligible": False,
        "limitations": result["limitations"] + [
            "Native stamps are returned to the SPIKES boundary but are not yet registered as a netlist device in the C++ MNA engine.",
            "The current boundary is a trusted-code containment profile, not a hostile-code sandbox.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "artifacts" / "spikes-osdi-native-qualification-2026-08-30.json",
    )
    args = parser.parse_args()
    evidence = qualify(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "output": str(args.output.resolve())}, sort_keys=True))
    return 0 if evidence["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
