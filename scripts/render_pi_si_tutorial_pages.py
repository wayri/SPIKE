# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Render offline input/output views from executed PI/SI tutorial artifacts.

The resulting HTML is deliberately not a SPIKE desktop UI simulation. Capture
it in a browser to document exactly which local request and result were used.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "build" / "tutorial-pi-si"
PAGES = RUN / "pages"


def read_json(name: str) -> dict:
    value = json.loads((RUN / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def plot(series: dict[str, list[tuple[float, float]]], x_label: str, y_label: str) -> str:
    values = [(x, y) for rows in series.values() for x, y in rows
              if math.isfinite(x) and math.isfinite(y)]
    if not values:
        raise ValueError("plot has no finite values")
    xs, ys = zip(*values)
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x0 == x1:
        x1 = x0 + 1.0
    if y0 == y1:
        y1 = y0 + 1.0
    inset = (y1 - y0) * 0.08
    y0 -= inset
    y1 += inset
    colors = ("#66e0c2", "#ffd166", "#fb7185", "#93c5fd")
    lines = [
        '<svg viewBox="0 0 620 350" role="img" aria-label="Plot of executed result">'
        '<rect width="620" height="350" fill="#111b2b"/>',
        '<path d="M64 24 V292 H600" stroke="#8aa0b5" fill="none"/>',
    ]
    for i in range(5):
        y = 24 + i * 67
        lines.append(f'<path d="M64 {y} H600" stroke="#2e4259"/>')
    for index, (name, rows) in enumerate(series.items()):
        stride = max(1, math.ceil(len(rows) / 180))
        sampled = rows[::stride]
        if sampled[-1] != rows[-1]:
            sampled.append(rows[-1])
        points = " ".join(
            f"{64 + (x - x0) * 536 / (x1 - x0):.1f},"
            f"{292 - (y - y0) * 268 / (y1 - y0):.1f}"
            for x, y in sampled if math.isfinite(x) and math.isfinite(y)
        )
        color = colors[index % len(colors)]
        lines.append(f'<polyline points="{points}" fill="none" stroke="{color}" '
                     'stroke-width="2" vector-effect="non-scaling-stroke"/>')
        lines.append(f'<text x="{75 + index * 130}" y="325" fill="{color}" '
                     f'font-size="13">{html.escape(name)}</text>')
    lines.extend([
        f'<text x="65" y="18" fill="#dbeafe" font-size="12">{y1:.4g} {html.escape(y_label)}</text>',
        f'<text x="65" y="307" fill="#dbeafe" font-size="12">{y0:.4g}</text>',
        f'<text x="505" y="307" fill="#dbeafe" font-size="12">{x0:.4g} to {x1:.4g} {html.escape(x_label)}</text>',
        "</svg>",
    ])
    return "".join(lines)


def page(name: str, title: str, input_path: Path, command: str,
         input_excerpt: object, output_path: Path, output_excerpt: object,
         graph: str, boundary: str) -> None:
    if not input_path.is_file() or not output_path.is_file():
        raise FileNotFoundError(f"missing executed artifact for {name}")
    left = html.escape(json.dumps(input_excerpt, indent=2, sort_keys=True))
    right = html.escape(json.dumps(output_excerpt, indent=2, sort_keys=True))
    document = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body{{font:15px/1.5 Segoe UI,Arial,sans-serif;background:#0b1220;color:#e5edf7;margin:28px}}
h1{{margin:0;font-size:28px}}p{{margin:6px 0 18px;color:#afc0d4}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
.card{{background:#172337;border:1px solid #35516b;border-radius:10px;padding:18px;min-width:0}}
h2{{font-size:17px;color:#8de8cf;margin:0 0 9px}}code,pre{{font:12px/1.45 Consolas,monospace}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;margin:8px 0 0}}
.path{{color:#bfd1ea}}.note{{background:#533a1c;color:#ffdf9e;padding:12px;margin-top:18px;border-radius:8px}}
.footer{{color:#8da4bc;font:11px Consolas,monospace;margin-top:13px}}
svg{{width:100%;height:300px}}
</style><body>
<h1>{html.escape(title)}</h1>
<p>Executed artifact view, not a SPIKE desktop screenshot or a validation certificate.</p>
<div class="grid">
<section class="card"><h2>Input</h2><div class="path">{html.escape(input_path.relative_to(ROOT).as_posix())}</div>
<pre>{html.escape(command)}</pre><pre>{left}</pre></section>
<section class="card"><h2>Output</h2><div class="path">{html.escape(output_path.relative_to(ROOT).as_posix())}</div>
<pre>{right}</pre></section>
<section class="card" style="grid-column:1 / -1"><h2>Returned result</h2>{graph}</section>
</div><div class="note">{html.escape(boundary)}</div>
<div class="footer">Input SHA-256 prefix {digest(input_path)} | Output SHA-256 prefix {digest(output_path)}
 | Original SPIKE-owned tutorial capture, Apache-2.0, SigHarmonic 2026</div>
</body></html>"""
    PAGES.mkdir(parents=True, exist_ok=True)
    (PAGES / f"{name}.html").write_text(document, encoding="utf-8")


def main() -> None:
    design = ROOT / "examples/tutorial_pi_si/straight_trace.design.json"
    design_value = json.loads(design.read_text(encoding="utf-8"))
    for stem in ("dc", "ac", "transient"):
        if read_json(f"{stem}-request.json")["design"] != design_value:
            raise ValueError(f"{stem} request is stale relative to the checked-in design")
    dc = read_json("dc-result.json")
    drop = dc["summary"]["max_load_voltage_drop_v"]
    assert dc["status"] == "completed" and dc["model_status"] == "approximate"
    assert abs(drop - 10e-3 / (1e-3 * 0.035e-3 * 5.8e7)) < 1e-10
    terminals = dc["networks"]["source_to_load"]["terminal_voltages"]
    page("dc", "DC PI: straight copper trace", design,
         "analyze-dc ... --source 0,0,F.Cu,5 --load 10,0,F.Cu,1",
         {"length_mm": 10, "width_mm": 1, "thickness_mm": 0.035, "load_a": 1},
         RUN / "dc-result.json",
         {"status": dc["status"], "model_status": dc["model_status"],
          "drop_mv": round(drop * 1e3, 6),
          "current_balance_a": dc["networks"]["source_to_load"]["source_current_balance_a"]},
         plot({"terminal voltage": [(i, row["voltage_v"]) for i, row in enumerate(terminals)]},
              "source 0, load 1", "V"),
         "Synthetic one-track analytical check. It does not qualify a routed board or contact model.")

    ac = read_json("ac-result.json")
    network = ac["networks"]["parasitics"][0]
    samples = network["impedance"]
    assert ac["status"] == "completed" and ac["model_status"] == "approximate"
    assert "transmission_line_s_parameters" in network["blocked_uses"]
    page("ac", "PI AC: broadband driving-point response", design,
         "analyze-ac ... --start-hz 1e6 --stop-hz 1e9 --points 5 --capacitance-model none",
         {"source_port": "0,0,F.Cu", "load_port": "10,0,F.Cu", "return": "not defined"},
         RUN / "ac-result.json",
         {"status": ac["status"], "model_status": ac["model_status"],
          "negative_energy_modes": network["quality"]["inductance_passivity"]["negative_eigenmode_count"],
          "impedance_at_1ghz_ohm": {
              "resistance": samples[-1]["resistance_ohm"],
              "reactance": samples[-1]["reactance_ohm"],
          }, "blocked_uses": network["blocked_uses"]},
         plot({"Re(Z)": [(math.log10(v["frequency_hz"]), v["resistance_ohm"]) for v in samples],
               "Im(Z)": [(math.log10(v["frequency_hz"]), v["reactance_ohm"]) for v in samples]},
              "log10(Hz)", "ohm"),
         "One-port approximate R/L response only: no calibrated capacitance, return port, S matrix, or eye.")

    transient = read_json("transient-result.json")
    frames = transient["fields"]["visualization"]["time_series"]["frames"]
    assert transient["status"] == "completed" and transient["model_status"] == "approximate"
    page("transient", "PI transient: stepped load", design,
         "analyze-transient ... --load-waveform step,0,2e-6,1e-6 --time-step-s 2e-7",
         {"source_v": 5, "load_a": 1, "stop_time_s": 8e-6, "capacitance_model": "none"},
         RUN / "transient-result.json",
         {"status": transient["status"], "model_status": transient["model_status"],
          "frames": len(frames), "peak_drop_mv": round(transient["summary"]["max_voltage_drop_v"] * 1e3, 6),
          "final_load_voltage_v": frames[-1]["scalar_values"]["voltage_v"][-1]},
         plot({"load voltage": [(f["time_s"] * 1e6, f["scalar_values"]["voltage_v"][-1])
                               for f in frames]}, "microseconds", "V"),
         "Manual 0.2-us step exceeds the returned 0.008-us recommendation; this is a runnable preview, not time-step convergence.")

    si_input = ROOT / "examples/si/analytical-coupled-rlgc.json"
    si = read_json("si-result.json")
    if si["request"] != json.loads(si_input.read_text(encoding="utf-8")):
        raise ValueError("SI result is stale relative to the checked-in request")
    rx = si["time_domain"]["receivers"][0]
    assert si["status"] == si["time_domain"]["status"] == si["tdr"]["status"] == "completed"
    page("si", "SI: analytical four-port, NEXT/FEXT, TDR and eye", si_input,
         "si-workflow examples/si/analytical-coupled-rlgc.json --touchstone-output ...s4p",
         {"channel": "independently authored coupled RLGC", "ports": 4, "bit_rate_hz": si["request"]["bit_rate_hz"]},
         RUN / "si-result.json",
         {"status": si["status"], "model_status": si["model_status"],
          "port_count": si["network"]["port_count"], "time_domain": si["time_domain"]["status"],
          "tdr": si["tdr"]["status"], "eye_height_v": rx["eye_height_v"],
          "field_maps": si.get("field_maps", {}).get("status", "not_returned"),
          "production_qualified": si["production_qualified"]},
         plot({key: [(row["frequency_hz"] / 1e9,
                      max(-120.0, min(5.0, row["magnitude_db"])))
                      for row in si["network"]["traces"][key]]
               for key in ("S31", "S21", "S41")}, "GHz", "dB"),
         "Analytical channel only. S dB is clipped to [-120, 5] for display. The through/NEXT/FEXT plot, TDR and eye are not PCB extraction or 10GbE compliance.")

    eye = plot({
        f"eye {index + 1}": list(zip(trace["phase_ui"], trace["voltage_v"]))
        for index, trace in enumerate(rx["traces"][:4])
    }, "UI", "V").replace('<svg viewBox=', '<svg style="width:50%" viewBox=', 1)
    tdr = plot({
        "TDR impedance": [(row["time_s"] * 1e9, row["impedance_ohm"])
                          for row in si["tdr"]["tdr"]]
    }, "ns", "ohm").replace('<svg viewBox=', '<svg style="width:50%" viewBox=', 1)
    page("si-time", "SI time result: selected eye traces and TDR", si_input,
         "si-workflow examples/si/analytical-coupled-rlgc.json",
         {"bit_rate_hz": si["request"]["bit_rate_hz"],
          "receiver_port": si["request"]["receivers"][0]["port"]},
         RUN / "si-result.json",
         {"time_domain": si["time_domain"]["status"], "tdr": si["tdr"]["status"],
          "eye_height_v": rx["eye_height_v"],
          "eye_trace_count": len(rx["traces"]),
          "tdr_sample_count": len(si["tdr"]["tdr"])},
         f'<div style="display:flex">{eye}{tdr}</div>',
         "Four of the returned deterministic eye traces are shown beside returned TDR impedance. No jitter/BER or hardware correlation is inferred.")

    touchstone = read_json("touchstone-inspect.json")
    exported = RUN / "si-channel.s4p"
    if exported.read_text(encoding="ascii") != si["touchstone"]["text"]:
        raise ValueError("Touchstone export differs from the executed SI result")
    assert touchstone["status"] == "completed" and touchstone["port_count"] == 4
    page("touchstone", "Touchstone: exported and re-inspected four-port", exported,
         "sparam-inspect build/tutorial-pi-si/si-channel.s4p",
         {"header": exported.read_text(encoding="ascii").splitlines()[:6]},
         RUN / "touchstone-inspect.json",
         {"contract": touchstone["contract"], "status": touchstone["status"],
          "port_count": touchstone["port_count"],
          "quality": touchstone["network_quality_status"],
          "passivity": touchstone["checks"]["passivity"]["status"],
          "reciprocity": touchstone["checks"]["reciprocity"]["status"],
          "causality": touchstone["checks"]["causality"]["status"]},
         plot({"S31": [(row["frequency_hz"] / 1e9, row["magnitude_db"])
                        for row in touchstone["traces"]["S31"]]}, "GHz", "dB"),
         "Round-trip of the unloaded analytical network. Causality is not evaluated. Imported measured files need verified port maps and reference planes.")

    ten_input = ROOT / "examples/si/10g-nrz-cdr.json"
    ten = read_json("10g-reference-result.json")
    ten_request = json.loads(ten_input.read_text(encoding="utf-8"))
    if any(ten["request"].get(key) != value for key, value in ten_request.items()):
        raise ValueError("10G result is stale relative to the checked-in request")
    ten_rx = ten["time_domain"]["receivers"][0]
    assert ten["status"] == "completed" and not ten["production_qualified"]
    page("10g", "10.3125-GBd numerical reference: not 10GbE compliance", ten_input,
         "si-workflow examples/si/10g-nrz-cdr.json",
         {"rate_hz": ten["request"]["bit_rate_hz"], "channel": "ideal matched 1-cm line"},
         RUN / "10g-reference-result.json",
         {"status": ten["status"], "model_status": ten["model_status"],
          "eye_height_v": ten_rx["eye_height_v"],
          "cdr_status": ten_rx["clock_recovery"]["status"],
          "production_qualified": ten["production_qualified"],
          "compliance_status": "not_evaluated"},
         plot({"receiver": [(row["time_s"] * 1e9, row["voltage_v"])
                             for row in ten_rx["waveform"][:300]]}, "ns", "V"),
         "Ideal NRZ/CDR numerical test only. It does not model BASE-T, KR link training, SR/LR optics, or normative limits.")

    marble = ROOT / "build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb"
    audit_path = ROOT / "build/validation/peec-support-gap-refresh-20260928.json"
    count = 7
    if marble.is_file() and audit_path.is_file():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if hashlib.sha256(marble.read_bytes()).hexdigest() != audit["board_sha256"]:
            raise ValueError("Marble board and copper-support audit do not match")
        levels = audit["levels"]
        assert audit["status"] == "diagnostic_unqualified_mesh"
        assert all(not level["support_passed"] for level in levels)
        page("marble-gate", "Marble AC: copper-support gate rejects the mesh", marble,
             "audit_peec_conforming_basis.py --board <pinned Marble PCB> --output <audit.json>",
             {"board_sha256": audit["board_sha256"],
              "mesh_sizes_mm": [level["mesh_size_mm"] for level in levels]},
             audit_path,
             {"status": audit["status"], "inductance_recomputed": audit["inductance_recomputed"],
              "outside_basis_count": [level["outside_basis_count"] for level in levels],
              "outside_area_mm2": [level["sum_outside_area_mm2"] for level in levels],
              "support_passed": [level["support_passed"] for level in levels]},
             plot({"leaking bases": [(level["mesh_size_mm"], level["outside_basis_count"])
                                     for level in levels]}, "target mm", "count"),
             "The retained positive-energy matrix is not an admitted Marble AC result: current bases extend outside copper.")
        count += 1

    print(f"Rendered {count} offline artifact pages under {PAGES}")


if __name__ == "__main__":
    main()
