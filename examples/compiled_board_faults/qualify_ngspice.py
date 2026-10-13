"""Compare the owned finite-fault fixture with ngspice; no timing claims.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from examples.compiled_board_faults.build_and_run import load_fixture, native_value
from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.ngspice_plugin import NgspicePlugin
from python.spikes.board_library_client import BoardLibrary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--ngspice", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    here, config, project, faults = load_fixture()
    original = (here / "fault_board.cir").read_text(encoding="utf-8")
    plugin = NgspicePlugin()
    plugin.executable = str(args.ngspice.resolve(strict=True))
    board_library = BoardLibrary(args.manifest.resolve(), engine_library=args.engine.resolve())
    cases = []
    for name, value in (("normal", None), ("gate_source_shunt", .01),
                        ("drain_source_shunt", .01), ("drain_source_shunt", 10.),
                        ("shifted_vto", 6.)):
        lines = [line for line in original.splitlines()
                 if not line.lower().startswith((".tran", ".end"))]
        if name == "shifted_vto":
            lines = [line.replace("VTO=1", f"VTO={value}") for line in lines]
        for binding in faults:
            if binding.positive_node is not None:
                resistance = value if binding.site.name == name else binding.site.healthy_value
                lines.append(f"R{binding.site.element_id} {binding.positive_node} "
                             f"{binding.negative_node} {resistance:.17g}")
        lines.extend([".options reltol=1e-9 abstol=1e-14 vntol=1e-10 gmin=1e-15", ".op", ".end"])
        deck = "\n".join(lines) + "\n"
        result = plugin.run(DesignIR(design_id="fault-reference", name="Owned fault fixture"),
                            AnalysisSpec(analysis_id="reference", mode="spice", solver_id="spike.ngspice",
                                         options={"spice_netlist": deck, "timeout_seconds": 30}))
        if result.status != "completed" or result.summary.get("parse_status") != "complete":
            raise RuntimeError(f"Incomplete ngspice result: {result.summary}; {result.issues}")
        reference = float(result.fields["waveforms"]["v(drain)"][-1])
        native = native_value(args.engine.resolve(), project, faults,
                              None if name == "normal" else name, value)
        with board_library.create() as board:
            if value is not None:
                board.inject_fault(name, value)
            board.step(1e-6)
            compiled = board.read("drain_v")
        if not all(math.isfinite(v) for v in (reference, native, compiled)):
            raise ValueError("Nonfinite comparison")
        tolerance = 1e-6
        error = max(abs(native-reference), abs(compiled-reference), abs(native-compiled))
        cases.append(dict(fault=name, value=value, native_v=native, compiled_v=compiled,
                          ngspice_v=reference, maximum_absolute_error_v=error,
                          absolute_tolerance_v=tolerance, status="passed" if error <= tolerance else "failed",
                          reference_deck=deck, reference_deck_sha256=hashlib.sha256(deck.encode()).hexdigest()))
    report = dict(schema="spikes/fault-reference/v1", scope="Static finite-shunt and Level-1 NMOS fixture only",
                  engine_sha256=hashlib.sha256(args.engine.read_bytes()).hexdigest(),
                  ngspice_sha256=hashlib.sha256(args.ngspice.read_bytes()).hexdigest(), cases=cases,
                  status="passed" if all(c["status"] == "passed" for c in cases) else "failed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: {len(cases)} cases; {args.output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
