"""Compile first-party fixtures with exact reviewed vendored HDL toolchains."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spikes.hdl_frontend import (
    CompilerTool, HdlCompileError, HdlCompilePlan, compile_hdl,
    discover_hdl_toolchains,
)


PATHS = {
    "openvaf": ROOT / "tools" / "hdl" / "openvaf" / "openvaf.exe",
    "ghdl": ROOT / "tools" / "hdl" / "ghdl" / "installed" / "ucrt64" / "bin" / "ghdl.exe",
    "iverilog": ROOT / "tools" / "hdl" / "iverilog-standalone" / "bin" / "iverilog.exe",
    "verilator": ROOT / "tools" / "hdl" / "oss-cad-suite" / "oss-cad-suite" / "bin" / "verilator_bin.exe",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    inventory = discover_hdl_toolchains(PATHS)
    raw = {item["compiler_id"]: item for item in inventory["tools"]}
    tools = {
        name: CompilerTool(**{
            key: value for key, value in raw[name].items()
            if key in CompilerTool.__dataclass_fields__
        }) for name in PATHS
    }
    arguments.artifacts.mkdir(parents=True, exist_ok=True)
    cases = (
        ("openvaf", ROOT / "benchmarks" / "hdl" / "spikes_linear_resistor.va", ""),
        ("ghdl", ROOT / "benchmarks" / "hdl" / "spikes_inverter.vhd", "spikes_inverter"),
        ("iverilog", ROOT / "benchmarks" / "hdl" / "spikes_tristate.v", "spikes_tristate"),
        ("verilator", ROOT / "benchmarks" / "hdl" / "spikes_tristate.v", "spikes_tristate"),
    )
    results = []
    for compiler_id, source, top in cases:
        plan = HdlCompilePlan.create(
            compilation_id=f"qualification.{compiler_id}", compiler=tools[compiler_id],
            source=source, top_module=top,
        )
        try:
            result = compile_hdl(plan, source, arguments.artifacts)
            results.append({"compiler_id": compiler_id, "status": "passed", "result": result})
        except HdlCompileError as exc:
            results.append({
                "compiler_id": compiler_id, "status": "failed",
                "error_code": exc.code, "detail": exc.detail,
            })
    passed = sum(item["status"] == "passed" for item in results)
    report = {
        "contract": "spikes/hdl-toolchain-qualification/v1",
        "status": "passed" if passed == len(results) else ("partial" if passed else "failed"),
        "summary": {"total": len(results), "passed": passed, "failed": len(results) - passed},
        "inventory": inventory, "cases": results,
        "osdi_native_mna_load_qualified": False,
        "production_claim_eligible": False,
        "limitations": [
            "Compiler acceptance is syntax/tool execution evidence, not model numerical qualification.",
            "HDL compiler acceptance does not qualify mixed-signal co-simulation semantics.",
            "OSDI callbacks are not loaded into the SPIKES native MNA solver.",
        ],
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"HDL qualification: {passed}/{len(results)}")
    return 0 if passed >= 3 else 2


if __name__ == "__main__":
    raise SystemExit(main())
