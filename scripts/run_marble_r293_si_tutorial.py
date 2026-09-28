"""Reproduce a bounded Marble R293 SI topology study without claiming extraction.

SPDX-License-Identifier: MIT
Copyright (c) 2026 SigHarmonic

The pinned board supplies only the U4/R293/U1 connectivity. Both line halves
and the IBIS endpoints are independently authored teaching models, not Marble
measurements or vendor device models. Generated output is kept under build/.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python.spike_core.service_project import import_design
from python.spike_core.si_ibis import parse_ibis
from python.spike_core.si_network_workflow import cascade_networks, line_network
from python.spike_core.si_workflow import REQUEST, run_si_workflow
from python.spike_core.sparameters import NetworkData, parse_touchstone_text, touchstone_text


BOARD_SHA256 = "3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512"
PHY_NET = "Net-(R293-Pad1)"
FPGA_NET = "/ETH_PHY/RGMII_RXD0"
PADS = {"U4.44": PHY_NET, "R293.1": PHY_NET, "R293.2": FPGA_NET, "U1.J10": FPGA_NET}
ILLUSTRATIVE_IBIS = Path(__file__).resolve().parents[1] / "examples" / "tutorial_pi_si" / "illustrative-rgmii.ibs"


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_board(board: Path, *, design_json: Path | None = None) -> dict:
    actual_sha = _sha(board)
    if actual_sha != BOARD_SHA256:
        raise ValueError(f"Marble board hash mismatch: {actual_sha}; expected {BOARD_SHA256}.")
    design = (json.loads(design_json.read_text(encoding="utf-8")) if design_json
              else import_design(str(board)))
    if design.get("metadata", {}).get("source_sha256") != actual_sha:
        raise ValueError("Normalized board digest does not bind to the pinned source.")
    pads = {}
    for pad in design.get("pads", []):
        key = pad.get("component_pad")
        if key in PADS:
            if key in pads:
                raise ValueError(f"Board pad {key} is ambiguous.")
            pads[key] = pad.get("net_name")
    if pads != PADS:
        raise ValueError(f"Marble U4/R293/U1 pad-net map changed: {pads}.")
    resistor = [item for item in design.get("components", []) if item.get("reference") == "R293"]
    if len(resistor) != 1 or resistor[0].get("pad_count") != 2:
        raise ValueError("R293 must resolve as one two-pad component.")
    track_count = {net: sum(item.get("net_name") == net for item in design["tracks"]) for net in (PHY_NET, FPGA_NET)}
    via_count = {net: sum(item.get("net_name") == net for item in design["vias"]) for net in (PHY_NET, FPGA_NET)}
    if via_count[FPGA_NET] == 0:
        raise ValueError("The expected Marble via-bearing post-resistor path was not retained.")
    return {"source_board_sha256": actual_sha, "source_board_bytes": board.stat().st_size,
            "board": "Berkeley Lab Marble v1.4.4, pinned commit a426777d92c0f22a546d4740b419a3937e0c1f90",
            "path": "U4 pad 44 -> R293 pad 1 -> R293 pad 2 -> U1 pad J10",
            "pads": pads, "track_count_by_net": track_count, "via_count_by_net": via_count,
            "fitted_component": "R293; nominal 22 ohm, 1%, 0402 per pinned KiCad source property",
            "geometry_channel_status": "not_extracted",
            "geometry_reason": "The post-R293 net includes vias and a branched/complex route outside the bounded uniform-path extractor."}


def series_impedance_network(frequencies_hz: np.ndarray, resistance_ohm: float, reference_ohm: float = 50.0) -> NetworkData:
    """Analytic reciprocal two-port for a non-negative ideal series resistance."""
    if not np.isfinite(resistance_ohm) or resistance_ohm < 0 or reference_ohm <= 0:
        raise ValueError("Series resistance must be finite/non-negative and reference positive.")
    transmission = 2 * reference_ohm / (2 * reference_ohm + resistance_ohm)
    reflection = resistance_ohm / (2 * reference_ohm + resistance_ohm)
    s = np.empty((len(frequencies_hz), 2, 2), dtype=complex)
    s[:, 0, 0] = s[:, 1, 1] = reflection
    s[:, 0, 1] = s[:, 1, 0] = transmission
    return NetworkData(frequencies_hz.copy(), s, np.array([reference_ohm] * 2),
                       source="Original analytic ideal series-resistor two-port")


def illustrative_channel(resistance_ohm: float) -> NetworkData:
    """Cascaded placeholders: PHY-side line, R293, FPGA-side line."""
    common = {"kind": "rlgc", "coupled": False, "resistance_ohm_per_m": 5.0,
              "inductance_h_per_m": 250e-9, "capacitance_f_per_m": 100e-12,
              "loss_tangent": 0.015, "frequency_stop_hz": 4e9,
              "frequency_points": 513, "reference_impedance_ohm": 50.0}
    left = line_network({**common, "length_m": 0.01})
    right = line_network({**common, "length_m": 0.03})
    return cascade_networks(cascade_networks(left, series_impedance_network(left.frequencies_hz, resistance_ohm)), right)


def _request(channel_text: str, ibis_text: str) -> dict:
    return {"contract": REQUEST, "channel": {"kind": "touchstone", "name": "illustrative-r293.s2p", "text": channel_text},
            "sources": [{"port": 0, "ibis": {"text": ibis_text, "name": "illustrative-rgmii.ibs", "model": "example_output",
                        "component": "EXAMPLE_PHY", "pin": "44", "corner": "typ", "state": "low", "operating_voltage_v": 0.9}}],
            "receivers": [{"port": 1, "ibis": {"text": ibis_text, "name": "illustrative-rgmii.ibs", "model": "example_input",
                          "component": "EXAMPLE_FPGA", "pin": "J10", "corner": "typ"}}],
            "passives": [], "bit_rate_hz": 250e6, "bit_count": 512, "temperature_c": 25.0,
            "run_time_domain": True, "export_format": "RI"}


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run_case(board: Path, output_dir: Path, *, design_json: Path | None = None) -> dict:
    board_evidence = verify_board(board, design_json=design_json)
    ibis_text = ILLUSTRATIVE_IBIS.read_text(encoding="ascii")
    inventory = parse_ibis(ibis_text, ILLUSTRATIVE_IBIS.name)
    if inventory["unsupported_keywords"]:
        raise ValueError("The illustrative IBIS fixture must not contain unsupported keywords.")
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    networks = {}
    for label, resistance in (("counterfactual-0ohm", 0.0), ("fitted-22ohm", 22.0)):
        network = illustrative_channel(resistance)
        s2p = touchstone_text(network.frequencies_hz, network.s_parameters(), 50.0, data_format="RI",
                              comments=["Original illustrative RLGC halves, not a Marble extraction or measurement.",
                                        f"Pinned Marble topology has R293={resistance:g} ohm in this counterfactual."])
        imported = parse_touchstone_text(s2p, f"{label}.s2p")
        if not np.allclose(imported.s_parameters(), network.s_parameters(), rtol=0, atol=2e-14):
            raise ValueError("Touchstone export/reimport changed the illustrative network.")
        request = _request(s2p, ibis_text)
        result = run_si_workflow(request)
        if (result["status"] != "completed" or result["time_domain"]["status"] != "completed" or
                result["tdr"]["status"] != "completed" or result["touchstone"]["error"] or
                len(result["ibis"]) != 2):
            raise ValueError(f"{label} did not complete all requested stages: {result['status']}.")
        if result["network"]["checks"]["passivity"]["status"] != "pass":
            raise ValueError(f"{label} failed sampled network passivity.")
        (output_dir / f"{label}.s2p").write_text(s2p, encoding="ascii")
        _write_json(output_dir / f"{label}-request.json", request)
        _write_json(output_dir / f"{label}-result.json", result)
        networks[label], results[label] = imported, result

    before, after = results["counterfactual-0ohm"], results["fitted-22ohm"]
    f = networks["fitted-22ohm"].frequencies_hz
    sample_indices = [0, 32, 128, 512]  # 0, 250 MHz, 1 GHz, 4 GHz.
    frequencies = []
    for index in sample_indices:
        b = networks["counterfactual-0ohm"].s_parameters()[index, 1, 0]
        a = networks["fitted-22ohm"].s_parameters()[index, 1, 0]
        frequencies.append({"frequency_hz": float(f[index]), "s21_before_db": float(20 * np.log10(abs(b))),
                            "s21_after_db": float(20 * np.log10(abs(a))),
                            "s21_delta_db": float(20 * np.log10(abs(a / b)))})
    eye_before = before["time_domain"]["receivers"][0]["eye_height_v"]
    eye_after = after["time_domain"]["receivers"][0]["eye_height_v"]
    report = {"contract": "spike/marble-r293-si-tutorial/v1", "status": "completed_experimental",
              "production_qualified": False, "compliance_status": "not_evaluated",
              "board_evidence": board_evidence,
              "illustrative_inputs": {"left_line_m": 0.01, "right_line_m": 0.03, "r_ohm_per_m": 5.0,
                                      "l_h_per_m": 250e-9, "c_f_per_m": 100e-12, "loss_tangent": 0.015,
                                      "ibis_sha256": inventory["sha256"], "ibis_kind": "SPIKE original teaching model, not a vendor IBIS",
                                      "touchstone_kind": "SPIKE original cascaded analytic channel, not Marble extraction or VNA"},
              "touchstone_checks": {key: results[key]["network"]["checks"] for key in results},
              "ibis_reductions": {key: results[key]["ibis"] for key in results},
              "frequency_comparison": frequencies,
              "eye_height_v": {"counterfactual_0ohm": eye_before, "fitted_22ohm": eye_after,
                               "delta_v": eye_after - eye_before},
              "limitations": ["Real Marble connectivity only; line lengths/RLGC and IBIS are illustrative assumptions.",
                              "R293 is represented at its mid-channel location by an analytic series two-port, not by an endpoint passive.",
                              "No qualified arbitrary-board field extraction, actual U4/U1 vendor model, de-embedding, causality or measured correlation.",
                              "IBIS inventory/reduction is one fixed DC I/V slope and ramp, not nonlinear IBIS/AMI execution."]}
    _write_json(output_dir / "impact-report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, required=True, help="Pinned Marble v1.4.4 KiCad board")
    parser.add_argument("--design-json", type=Path, help="Optional previously imported DesignIR v1 JSON bound to that board")
    parser.add_argument("--output-dir", type=Path, default=Path("build/tutorial-pi-si/marble-r293"))
    args = parser.parse_args()
    report = run_case(args.board, args.output_dir, design_json=args.design_json)
    print(json.dumps({"status": report["status"], "board_sha256": report["board_evidence"]["source_board_sha256"],
                      "eye_height_v": report["eye_height_v"], "output_dir": str(args.output_dir)}, indent=2))


if __name__ == "__main__":
    main()
