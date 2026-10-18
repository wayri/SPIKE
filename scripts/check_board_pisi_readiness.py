# SPDX-License-Identifier: Apache-2.0
"""Audit two pinned real boards without promoting diagnostic execution to SI/PI readiness.

Preserves complete imported designs. The 1 V / 1 A terminal excitation is an
assumed conductivity diagnostic, not an operating point or a signoff load.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.spider_v2 import SpiDeRV2

BOARDS = {
    "ebrake": ("app/public/demo/ebrake1.kicad_pcb",
        "d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca"),
    "marble": ("build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb",
        "3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512"),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dc_evidence(result):
    """Check algebraic conservation; explicitly separate it from physical accuracy."""
    if result.get("status") != "completed":
        return {"completed": False}
    s = result["summary"]
    current = s["total_load_current_a"]
    drop = s["max_load_voltage_drop_v"]
    loss = s["total_network_loss_w"]
    residual = s["max_scaled_linear_residual"]
    if not all(math.isfinite(x) for x in (current, drop, loss, residual)):
        raise ValueError("Nonfinite DC diagnostic")
    if current <= 0 or drop <= 0 or residual > 1e-7:
        raise ValueError("DC positivity/residual check failed")
    # One voltage source and one current load: source-minus-load power is I*dV.
    error = abs(loss - current * drop)
    if error > 1e-10 + 1e-7 * abs(loss):
        raise ValueError("Single-load DC power conservation failed")
    return {"completed": True, "resistance_ohm": drop / current,
        "load_drop_v": drop, "loss_w": loss, "power_balance_error_w": error,
        "scaled_residual": residual, "model_status": result.get("model_status")}


def refinement_evidence(rows):
    if len(rows) != 3 or not all(r.get("completed") for r in rows):
        return {"passed": False, "reason": "Three completed levels required"}
    values = [r["resistance_ohm"] for r in rows]
    if not all(math.isfinite(x) and x > 0 for x in values):
        raise ValueError("Finite positive resistance required")
    changes = [abs(a - b) / b for a, b in zip(values, values[1:])]
    return {"passed": max(changes) <= .02 and changes[-1] <= changes[0],
        "relative_changes": changes, "threshold": .02,
        "scope": "mesh sensitivity only; no independent field or measurement correlation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    folder = args.output_dir.resolve()
    if folder.exists():
        parser.error("Fresh output folder required")
    folder.mkdir(parents=True)
    cases = []

    def run(name, arguments):
        output = folder / (name + ".json")
        command = [args.python, "-m", "python.spike_core.cli", "--quiet",
                   "--output", str(output), *map(str, arguments)]
        row = {"name": name, "command": command}
        try:
            process = subprocess.run(command, cwd=ROOT, capture_output=True,
                text=True, timeout=180)
            (folder / (name + ".log")).write_text(process.stdout + process.stderr,
                encoding="utf-8")
            row["exit_code"] = process.returncode
            result = json.loads(output.read_text(encoding="utf-8"))
            row.update(output_sha256=digest(output), status=result.get("status"),
                model_status=result.get("model_status"), error=result.get("error"),
                issues=result.get("issues", []))
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            row["execution_error"] = str(error)
            result = {}
        cases.append(row)
        print(json.dumps({k: row[k] for k in ("name", "exit_code", "status", "error", "execution_error") if k in row}), flush=True)
        return result

    evidence = {}
    for name, (path, expected) in BOARDS.items():
        board = ROOT / path
        if digest(board) != expected:
            raise ValueError(f"Pinned {name} board hash changed")
        imported = run(name + "-import", ["import-design", board, "--report"])
        v2 = imported["design"]
        if v2["source"]["source_digest"] != expected:
            raise ValueError("Import did not retain board digest")
        v1 = SpiDeRV2.from_dict(v2).to_v1().to_dict()
        design_path = folder / (name + "-design-v1.json")
        design_path.write_text(json.dumps(v1), encoding="utf-8")
        v2_path = folder / (name + "-design-v2.json")
        v2_path.write_text(json.dumps(v2), encoding="utf-8")
        evidence[name] = {"board_sha256": expected,
            "counts": {k: len(v2[k]) for k in ("tracks", "arcs", "vias", "pads", "zones")},
            "import_solver_readiness": imported["report"]["solver_readiness"],
            "design_v1_sha256": digest(design_path), "design_v2_sha256": digest(v2_path)}
        pads = {p.get("component_pad"): p for p in v1["pads"]}
        net, source, load = (("Net-(U2-VBUS)", "U2.40", "TP1.1") if name == "ebrake"
                            else ("Net-(C383-Pad1)", "U37.18", "R195.1"))
        def terminal(pad, value):
            p = pads[pad]
            if p.get("net_name", p.get("net")) != net:
                raise ValueError("Pinned terminal net changed")
            return ",".join(map(str, [*p["at"], p["layer"], value]))
        evidence[name]["terminals"] = {p: pads[p] for p in (source, load)}
        common = [design_path, "--net", net, "--max-zone-cells", "1000", "--max-conductors", "2000"]
        rows = []
        for size in ([.5, .25, .125] if name == "ebrake" else [.5]):
            result = run(f"{name}-dc-{size}", ["analyze-dc", *common,
                "--source", terminal(source, 1), "--load", terminal(load, 1),
                "--mesh-size-mm", size])
            row = dc_evidence(result)
            row["mesh_size_mm"] = size
            rows.append(row)
        evidence[name]["dc"] = rows
        evidence[name]["dc_refinement"] = refinement_evidence(rows)
        run(name + "-ac", ["analyze-ac", *common, "--source", terminal(source, source),
            "--load", terminal(load, load), "--mesh-size-mm", ".5", "--start-hz", "1000",
            "--stop-hz", "1000000", "--points", "5", "--capacitance-model", "none"])
        if name == "marble":
            run(name + "-c383-connected-dc", ["analyze-dc", *common,
                "--source", terminal(source, 1), "--load", terminal("C383.1", 1),
                "--mesh-size-mm", ".5"])
        request = {"contract": "spike/si-uniform-channel-request/v1",
            "channel_id": name + "-real-board-probe",
            "signal_net": "Net-(U3-BEMF)" if name == "ebrake" else "/WhiteRabbit/SI570_CLK_N",
            "reference_net": "GND", "reference_layer": "In2.Cu" if name == "ebrake" else "In1.Cu",
            "reference_impedance_ohm": 50, "frequencies_hz": [i * 1e6 for i in range(65)]}
        request_path = folder / (name + "-si.request.json")
        request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
        run(name + "-si", ["si-geometry-channel", v2_path, request_path])

    report = {"contract": "spike/board-pisi-readiness-audit/v1",
        "audit_execution_completed": not any("execution_error" in row for row in cases),
        "full_board_pisi_ready": False, "production_qualified": False,
        "assumptions": ["1 V source / 1 A diagnostic load; nominal operation unknown.",
            "Complete imported designs retained; solver selects named net, no geometry replacement.",
            "DC solves supply conductor only; no physical return loop specified.",
            "AC probe disables capacitance and has no explicit return; not full PDN or SI.",
            "50 ohm / DC-64 MHz SI grid is a diagnostic request, not board requirements."],
        "boards": evidence, "cases": cases,
        "source_sha256": {p: digest(ROOT / p) for p in ("scripts/check_board_pisi_readiness.py",
            "python/spike_core/cli.py", "python/spike_core/si_channel.py", "python/spike_core/dc_solver.py")}}
    from python.spike_core.peec_plugin import native
    report["native_sha256"] = digest(native.__file__) if native else None
    (folder / "readiness.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0 if report["audit_execution_completed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
