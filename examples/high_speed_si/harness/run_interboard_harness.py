# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Yawar B and SPIKE contributors.
"""Run an original synthetic interboard harness PI and coupled SI reference.

Run from the checkout with a fresh output directory:
  python examples/high_speed_si/harness/run_interboard_harness.py --output-dir build/interboard-harness-reference
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from python.spike_core.harness_authoring import validate_harness_connections
from python.spike_core.harness_mtl import run_harness_mtl
from python.spike_core.harness_pi import run_harness_pi
from python.spike_core.harness_rlgc_geometry import extract_parallel_round_rlgc
from python.spike_core.harness_signal import run_harness_si
from python.spike_core.spider_v2 import AssemblyIRV1

BOARD_A, BOARD_B = "harness-board-A", "harness-board-B"
CONNECTOR_A, CONNECTOR_B = f"{BOARD_A}::JH1", f"{BOARD_B}::JH1"
LENGTH_M, LOAD_CURRENT_A, SOURCE_VOLTAGE_V = 0.6, 4.0, 12.0
COPPER_CONDUCTIVITY_S_M, POWER_AREA_M2 = 5.8e7, 0.5e-6
POWER_RESISTANCE_OHM = LENGTH_M / (COPPER_CONDUCTIVITY_S_M * POWER_AREA_M2)
SIGNAL_IDS = ["agg-p", "agg-n", "vic-p", "vic-n"]
PIN_IDS = ["PWR", "RET", "AGG_P", "AGG_N", "VIC_P", "VIC_N"]
FREQUENCY_HZ = np.linspace(0.0, 250e6, 33).tolist()


def endpoint(connector: str, pin: str) -> dict:
    return {"connector": connector, "pin": pin}


def _signal_resistance() -> float:
    return LENGTH_M / (COPPER_CONDUCTIVITY_S_M * math.pi * (0.15e-3) ** 2)


def harness_document() -> dict:
    """One explicit six-conductor pin map shared by visual and PI artifacts."""
    pins = [{"id": pin, "net": f"SYNTH_{pin}"} for pin in PIN_IDS]
    power_radius_mm = math.sqrt(POWER_AREA_M2 / math.pi) * 1e3
    common_material = {"name": "assumed copper", "resistivity_ohm_m": 1 / COPPER_CONDUCTIVITY_S_M,
                       "reference_temperature_c": 20.0}
    wires = [
        {"id": "pwr", "from": endpoint(CONNECTOR_A, "PWR"), "to": endpoint(CONNECTOR_B, "PWR"),
         "role": "power", "return_wire_id": "return", "length_mm": 600.0, "area_mm2": 0.5,
         "route_id": "interboard-route", "color": "#e36f4f", "material": copy.deepcopy(common_material),
         "electrical": {"resistance_ohm": POWER_RESISTANCE_OHM,
                        "provenance": {"source": "R=L/(sigma*A) from explicit synthetic inputs"}},
         "properties": {"cross_section_position_mm": [-12.0, 8.0], "radius_mm": power_radius_mm}},
        {"id": "return", "from": endpoint(CONNECTOR_B, "RET"), "to": endpoint(CONNECTOR_A, "RET"),
         "role": "return", "length_mm": 600.0, "area_mm2": 0.5,
         "route_id": "interboard-route", "color": "#8090aa", "material": copy.deepcopy(common_material),
         "electrical": {"resistance_ohm": POWER_RESISTANCE_OHM,
                        "provenance": {"source": "R=L/(sigma*A) from explicit synthetic inputs"}},
         "properties": {"cross_section_position_mm": [12.0, 8.0], "radius_mm": power_radius_mm}},
    ]
    positions = {"agg-p": -7.0, "agg-n": -3.0, "vic-p": 3.0, "vic-n": 7.0}
    pin_by_wire = {"agg-p": "AGG_P", "agg-n": "AGG_N", "vic-p": "VIC_P", "vic-n": "VIC_N"}
    for wire_id in SIGNAL_IDS:
        wires.append({"id": wire_id, "from": endpoint(CONNECTOR_A, pin_by_wire[wire_id]),
            "to": endpoint(CONNECTOR_B, pin_by_wire[wire_id]), "role": "signal",
            "length_mm": 600.0, "area_mm2": math.pi * 0.15**2, "route_id": "interboard-route",
            "color": "#55c7dc", "material": copy.deepcopy(common_material),
            "electrical": {"resistance_ohm": _signal_resistance(),
                           "provenance": {"source": "DC metadata from the same solid round-wire geometry"}},
            "properties": {"cross_section_position_mm": [positions[wire_id], 8.0], "radius_mm": 0.15}})
    pi_setup = {"wire_ids": ["pwr", "return"], "ground": endpoint(CONNECTOR_A, "RET"), "contacts": [],
        "terminals": [
            {"id": "board-A-source", "type": "voltage_source", "positive": endpoint(CONNECTOR_A, "PWR"),
             "negative": endpoint(CONNECTOR_A, "RET"), "value": SOURCE_VOLTAGE_V},
            {"id": "board-B-load", "type": "current_load", "positive": endpoint(CONNECTOR_B, "PWR"),
             "negative": endpoint(CONNECTOR_B, "RET"), "value": LOAD_CURRENT_A}]}
    si_setup = {"selection": {"pair_id": "aggressor-pair"},
                "source": "Differential scalar modal model derived from the checked geometry RLGC artifact",
                "model_input": {}}
    return {"contract": "spike/harness/v1", "id": "synthetic-interboard-harness",
        "name": "Synthetic board A to board B power and coupled signal harness",
        "connectors": [
            {"id": CONNECTOR_A, "name": "Board A reviewed harness connector",
             "board_binding": {"board_id": BOARD_A, "connector_id": "JH1"}, "pins": copy.deepcopy(pins)},
            {"id": CONNECTOR_B, "name": "Board B reviewed harness connector",
             "board_binding": {"board_id": BOARD_B, "connector_id": "JH1"}, "pins": copy.deepcopy(pins)}],
        "wires": wires,
        "pairs": [{"id": "aggressor-pair", "wire_ids": ["agg-p", "agg-n"], "kind": "differential", "twisted": False},
                  {"id": "victim-pair", "wire_ids": ["vic-p", "vic-n"], "kind": "differential", "twisted": False}],
        "cables": [{"id": "six-conductor-bundle", "wire_ids": ["pwr", "return", *SIGNAL_IDS], "twisted": False}],
        "routes": [{"id": "interboard-route", "frame_id": "assembly", "points_mm": [[0, 0, 0], [600, 0, 0]]}],
        "extensions": {"spike.harness-pi": copy.deepcopy(pi_setup), "spike.harness-si": si_setup,
                       "spike.harness-mtl-evidence": {"status": "external-example-artifact",
                                                      "request": "mtl-request.json", "result": "mtl-result.json"}},
        "provenance": {"source": "Original synthetic SPIKE interboard harness; no imported board pinout or measured cable data"}}


def pi_request(document: dict) -> dict:
    return {"contract": "spike/harness-pi-request/v1", "harness": copy.deepcopy(document),
            **copy.deepcopy(document["extensions"]["spike.harness-pi"])}


def geometry_request() -> dict:
    positions = {"agg-p": -7e-3, "agg-n": -3e-3, "vic-p": 3e-3, "vic-n": 7e-3}
    return {"contract": "spike/harness-round-wire-rlgc/v1", "harness_id": "synthetic-interboard-harness",
        "occurrence_id": "synthetic-interboard-harness-assembly/harness-1",
        "reference_plane": {"kind": "ideal_infinite_ground_plane"},
        "wires": [{"wire_id": wire_id, "x_m": positions[wire_id], "height_m": 8e-3,
                   "radius_m": 0.15e-3, "conductivity_s_m": COPPER_CONDUCTIVITY_S_M,
                   "relative_permeability": 1.0, "role": "signal",
                   "occurrence_id": "synthetic-interboard-harness-assembly/harness-1"}
                  for wire_id in SIGNAL_IDS],
        "dielectric": {"relative_permittivity": 2.4, "loss_tangent": 0.008}, "frequency_hz": FREQUENCY_HZ,
        "provenance": {"source": "Original assumed straight solid round-wire cross-section; coordinates and constant material values are explicit",
                       "board_occurrences": [BOARD_A, BOARD_B], "not_measured": True}}


def mtl_request(model: dict) -> dict:
    nodes, ports = [], []
    for end, occurrence in (("A", BOARD_A), ("B", BOARD_B)):
        for wire_id in SIGNAL_IDS:
            node_id = f"{end}:{wire_id}"
            nodes.append({"id": node_id, "wire_id": wire_id, "occurrence_id": occurrence})
            ports.append({"id": node_id, "positive_node": node_id, "negative_node": "ideal-reference-plane",
                          "reference_impedance_ohm": 50.0, "occurrence_id": occurrence, "wire_id": wire_id})
    return {"contract": "spike/harness-mtl-request/v1", "reference_node": "ideal-reference-plane",
        "frequency_hz": FREQUENCY_HZ, "nodes": nodes,
        "segments": [{"id": "straight-six-hundred-mm-signal-bundle", "wire_ids": SIGNAL_IDS,
                      "from_nodes": [f"A:{wire_id}" for wire_id in SIGNAL_IDS],
                      "to_nodes": [f"B:{wire_id}" for wire_id in SIGNAL_IDS],
                      "length_m": LENGTH_M, "model": copy.deepcopy(model)}],
        "contacts": [], "terminations": [], "ports": ports,
        "mixed_mode_pairs": [["A:agg-p", "A:agg-n"], ["A:vic-p", "A:vic-n"],
                             ["B:agg-p", "B:agg-n"], ["B:vic-p", "B:vic-n"]],
        "provenance": {"source": "Original synthetic interboard harness using SPIKE geometry-derived sampled RLGC",
                       "board_occurrences": [BOARD_A, BOARD_B],
                       "port_loading": "Each single-ended port explicitly uses a real 50 ohm reference; non-excited ports receive that matched load"}}


def uniform_si_request(document: dict, sampled_model: dict) -> dict:
    """Build the GUI-supported bounded differential mode from the same RLGC.

    For d=[1,-1], Vd=Vp-Vn and conductor currents [I,-I], the scalar
    telegrapher terms are d.T Z d and d.T Y d / 4.
    """
    d = np.asarray([1.0, -1.0])
    selected = np.ix_([0, 1], [0, 1])
    r = np.asarray(sampled_model["r_ohm_per_m"][0])[selected]
    l = np.asarray(sampled_model["l_h_per_m"][0])[selected]
    c = np.asarray(sampled_model["c_f_per_m"][0])[selected]
    r_loop = float(d @ r @ d)
    l_loop = float(d @ l @ d)
    c_loop = float(d @ c @ d / 4)
    z0 = math.sqrt(l_loop / c_loop)
    harness = copy.deepcopy(document)
    harness["extensions"].pop("spike.harness-si", None)  # same freeze boundary as harnessSignalRequest()
    model = {"kind": "rlgc", "coupled": False, "length_m": LENGTH_M,
             "resistance_ohm_per_m": r_loop, "inductance_h_per_m": l_loop,
             "capacitance_f_per_m": c_loop, "loss_tangent": 0.008,
             "inductive_coupling": 0.0, "capacitive_coupling": 0.0,
             "reference_impedance_ohm": z0, "frequency_stop_hz": FREQUENCY_HZ[-1],
             "frequency_points": len(FREQUENCY_HZ)}
    document["extensions"]["spike.harness-si"]["model_input"] = {
        key: value for key, value in model.items() if key not in ("kind", "coupled", "inductive_coupling", "capacitive_coupling")}
    return {"contract": "spike/harness-si-request/v1", "harness": harness,
            "selection": {"pair_id": "aggressor-pair"}, "model": model,
            "provenance": {"source": "Scalar aggressor differential mode derived from the DC L/R and static C of rlgc-result.json; no victim/crosstalk or common-mode content"}}


def _assembly_conductor_metadata(document: dict) -> dict:
    wire_by_pin = {wire["from"]["pin"]: wire for wire in document["wires"]}
    retained = []
    keys = ("id", "role", "return_wire_id", "length_mm", "area_mm2", "net", "color", "part_number",
            "material", "electrical", "properties", "extensions")
    for pin in PIN_IDS:
        wire = wire_by_pin[pin]
        retained.append({"from_pin": pin, "to_pin": wire["to"]["pin"],
                         **{key: copy.deepcopy(wire[key]) for key in keys if key in wire}})
    return {"contract": "spike/assembly-harness-conductors/v1", "wires": retained,
            "pairs": copy.deepcopy(document["pairs"]), "cables": copy.deepcopy(document["cables"]),
            "connectors": copy.deepcopy(document["connectors"]),
            "analysis_extensions": copy.deepcopy(document["extensions"])}


def assembly_view(document: dict) -> dict:
    raw = {"assembly_id": "synthetic-interboard-harness-assembly", "name": "Synthetic interboard harness assembly",
        "boards": [
            {"id": BOARD_A, "design_id": "synthetic-harness-terminal-board-A",
             "frame": {"frame_id": "harness-board-A-frame", "parent_frame_id": "assembly"}},
            {"id": BOARD_B, "design_id": "synthetic-harness-terminal-board-B",
             "frame": {"frame_id": "harness-board-B-frame", "parent_frame_id": "assembly",
                       "transform": [1, 0, 0, 600, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}}],
        "connector_mappings": [
            {"id": "board-A-JH1-position", "kind": "connector-position",
             "data": {"board_id": BOARD_A, "connector_id": "JH1", "position_mm": [0, 0, 0]}},
            {"id": "board-B-JH1-position", "kind": "connector-position",
             "data": {"board_id": BOARD_B, "connector_id": "JH1", "position_mm": [0, 0, 0]}}],
        "harnesses": [{"id": document["id"], "name": document["name"], "endpoint_a": CONNECTOR_A,
                       "endpoint_b": CONNECTOR_B, "length_mm": 600.0, "pin_map": {pin: pin for pin in PIN_IDS},
                       "extensions": {"spike.harness-routing": {"route_mm": [[0, 0, 0], [600, 0, 0]]},
                                      "spike.harness-conductors": _assembly_conductor_metadata(document)}}]}
    assembly = AssemblyIRV1.from_dict(raw)
    validate_harness_connections(assembly)
    return assembly.to_dict()


def _complex_mixed(result: dict) -> np.ndarray:
    return np.asarray(result["mixed_mode"]["s_real"]) + 1j * np.asarray(result["mixed_mode"]["s_imag"])


def _diagonal_control(request: dict) -> dict:
    control = copy.deepcopy(request)
    model = control["segments"][0]["model"]
    for key in ("r_ohm_per_m", "l_h_per_m", "g_s_per_m", "c_f_per_m"):
        model[key] = [np.diag(np.diag(np.asarray(matrix, dtype=float))).tolist() for matrix in model[key]]
    model["provenance"] = {"source": "Synthetic no-mutual-coupling control retaining only supplied RLGC diagonals",
                           "parent": request["segments"][0]["model"]["provenance"]}
    control["provenance"] = {**control["provenance"], "control": "all interconductor RLGC entries set to zero"}
    return run_harness_mtl(control)


def _db(value: float) -> float:
    return 20 * math.log10(max(value, 1e-300))


def validate_and_summarize(pi: dict, geometry: dict, uniform_si: dict, mtl: dict, control: dict) -> dict:
    expected_load_v = SOURCE_VOLTAGE_V - LOAD_CURRENT_A * 2 * POWER_RESISTANCE_OHM
    expected_wire_loss_w = LOAD_CURRENT_A**2 * 2 * POWER_RESISTANCE_OHM
    connection = {row["id"]: row for row in pi["connections"]}
    power_sum_w = sum(pi["native_result"]["data"]["element_power_w"].values())
    pi_checks = {"load_voltage_v": connection["board-B-load"]["voltage_v"],
        "analytical_load_voltage_v": expected_load_v,
        "load_voltage_abs_error_v": abs(connection["board-B-load"]["voltage_v"] - expected_load_v),
        "wire_loss_w": pi["total_wire_loss_w"], "analytical_wire_loss_w": expected_wire_loss_w,
        "wire_loss_abs_error_w": abs(pi["total_wire_loss_w"] - expected_wire_loss_w),
        "native_element_power_sum_w": power_sum_w,
        "all_selected_wire_currents_abs_a": [abs(row["current_a"]) for row in pi["wires"]]}
    assert pi["status"] == "completed"
    assert pi_checks["load_voltage_abs_error_v"] <= 1e-10 and pi_checks["wire_loss_abs_error_w"] <= 1e-10
    assert abs(power_sum_w) <= 1e-10
    assert all(abs(value - LOAD_CURRENT_A) <= 1e-10 for value in pi_checks["all_selected_wire_currents_abs_a"])

    mixed, control_mixed = _complex_mixed(mtl), _complex_mixed(control)
    next_values, fext_values, through_values = np.abs(mixed[:, 1, 0]), np.abs(mixed[:, 3, 0]), np.abs(mixed[:, 2, 0])
    control_values = np.maximum(np.abs(control_mixed[:, 1, 0]), np.abs(control_mixed[:, 3, 0]))
    peak_next, peak_fext = int(np.argmax(next_values)), int(np.argmax(fext_values))
    si_checks = {"mixed_mode_order": mtl["mixed_mode"]["ordering"],
        "differential_pair_order": ["A aggressor", "A victim", "B aggressor", "B victim"],
        "maximum_relative_residual": max(mtl["quality"]["relative_residual"]),
        "maximum_condition_number": max(mtl["quality"]["condition_number"]),
        "maximum_sampled_singular_value": max(mtl["quality"]["maximum_singular_value"]),
        "reciprocity_max_abs": mtl["quality"]["reciprocity_max_abs"],
        "peak_differential_next": {"frequency_hz": FREQUENCY_HZ[peak_next],
            "magnitude_v_per_v": float(next_values[peak_next]), "transfer_db": _db(float(next_values[peak_next]))},
        "peak_differential_fext": {"frequency_hz": FREQUENCY_HZ[peak_fext],
            "magnitude_v_per_v": float(fext_values[peak_fext]), "transfer_db": _db(float(fext_values[peak_fext]))},
        "minimum_differential_aggressor_through_magnitude": float(np.min(through_values)),
        "diagonal_control_maximum_victim_transfer": float(np.max(control_values)),
        "frequency_response": [{"frequency_hz": frequency,
            "aggressor_through_magnitude": float(through_values[index]),
            "differential_next_magnitude": float(next_values[index]), "differential_next_db": _db(float(next_values[index])),
            "differential_fext_magnitude": float(fext_values[index]), "differential_fext_db": _db(float(fext_values[index]))}
            for index, frequency in enumerate(FREQUENCY_HZ)]}
    assert geometry["status"] == "completed" and geometry["geometry_rlgc_executed"] and mtl["status"] == "completed"
    uniform_s = np.asarray(uniform_si["s_real"]) + 1j * np.asarray(uniform_si["s_imag"])
    assert uniform_si["status"] == "completed" and uniform_si["mode"] == "differential"
    assert uniform_si["wire_ids"] == ["agg-p", "agg-n"] and np.all(np.isfinite(uniform_s))
    assert np.max(np.abs(uniform_s - uniform_s.transpose(0, 2, 1))) <= 1e-12
    assert si_checks["maximum_relative_residual"] <= 1e-10
    assert si_checks["maximum_sampled_singular_value"] <= 1 + 1e-8 and si_checks["reciprocity_max_abs"] <= 1e-8
    assert max(float(np.max(next_values)), float(np.max(fext_values))) > 1e-6
    assert si_checks["diagonal_control_maximum_victim_transfer"] <= 1e-12
    uniform_checks = {"status": uniform_si["status"], "mode": uniform_si["mode"],
        "frequency_points": len(uniform_si["frequency_hz"]),
        "reference_impedance_ohm": uniform_si["reference_impedance_ohm"][0],
        "maximum_reciprocity_error": float(np.max(np.abs(uniform_s - uniform_s.transpose(0, 2, 1)))),
        "minimum_through_magnitude": float(np.min(np.abs(uniform_s[:, 1, 0]))),
        "maximum_input_reflection_magnitude": float(np.max(np.abs(uniform_s[:, 0, 0])))}
    return {"status": "passed", "pi": pi_checks, "uniform_gui_si": uniform_checks, "si": si_checks,
            "assertions": ["DC load voltage agrees with explicit two-wire KVL within 1e-10 V.",
                "DC wire loss agrees with I^2R within 1e-10 W and native power closes within 1e-10 W.",
                "Coupled MTL residual, sampled passivity and reciprocity meet solver admission thresholds.",
                "Public GUI uniform differential harness SI completes with finite reciprocal two-port output.",
                "Differential victim transfer is nonzero with mutual RLGC and <=1e-12 when mutual terms are removed."]}


def _line_number(relative: str, needle: str) -> int:
    for number, line in enumerate((ROOT / relative).read_text(encoding="utf-8").splitlines(), 1):
        if needle in line:
            return number
    raise ValueError(f"Missing integration anchor {needle!r} in {relative}")


def integration_map() -> dict:
    entries = [
        ("Harness PI desktop panel submits saved document/setup", "app/src/HarnessPiPanel.tsx", "contract: \"spike/harness-pi-request/v1\""),
        ("Desktop worker bridge admits PI", "app/src/workerBridge.ts", "\"run_harness_pi\""),
        ("Desktop worker bridge admits coupled MTL", "app/src/workerBridge.ts", "\"run_harness_mtl\""),
        ("Harness signal panel submits public uniform SI", "app/src/HarnessSignalPanel.tsx", "run_harness_si"),
        ("3D view resolves board and connector identities", "app/src/harnessVisualization.ts", "Endpoint strings use `board-instance-id::connector-id`"),
        ("3D view consumes serialized route", "app/src/harnessVisualization.ts", "Array.isArray(routing.route_mm)"),
        ("CLI exposes harness PI", "python/spike_core/cli.py", "harness-pi\", help=")]
    return {"schemas": ["schemas/harness-v1.schema.json", "schemas/harness-pi-request-v1.schema.json",
            "schemas/harness-pi-result-v1.schema.json", "schemas/harness-si-request-v1.schema.json",
            "schemas/harness-si-result-v1.schema.json", "schemas/harness-round-wire-rlgc-request-v1.schema.json",
            "schemas/harness-mtl-request-v1.schema.json"],
        "source_coordinates": [{"purpose": purpose, "path": path, "line": _line_number(path, needle), "anchor": needle}
                               for purpose, path, needle in entries],
        "gui_scope": "PI authoring/result and 3D conductor picking are integrated; coupled MTL is callable through the registered worker bridge but has no dedicated MTL report panel."}


def _sha256_json(value: object) -> str:
    # Match the exact UTF-8 bytes written by main(), including indentation and LF.
    return hashlib.sha256((json.dumps(value, indent=2, allow_nan=False) + "\n").encode()).hexdigest()


def run_case() -> dict[str, object]:
    document = harness_document()
    pi_input = pi_request(document)
    pi_result = run_harness_pi(pi_input)
    geometry_input = geometry_request()
    geometry_result = extract_parallel_round_rlgc(geometry_input)
    if geometry_result["status"] != "completed":
        raise ValueError(f"Geometry extraction was not admitted: {geometry_result['issues']}")
    mtl_input = mtl_request(geometry_result["model"])
    uniform_input = uniform_si_request(document, geometry_result["model"])
    uniform_result = run_harness_si(uniform_input)
    assembly = assembly_view(document)
    mtl_result = run_harness_mtl(mtl_input)
    control_result = _diagonal_control(mtl_input)
    validation = validate_and_summarize(pi_result, geometry_result, uniform_result, mtl_result, control_result)
    integration = integration_map()
    report = {"contract": "spike/example-interboard-harness-report/v1", "status": "completed",
        "title": "Synthetic interboard harness PI and coupled SI report", "assembly_id": assembly["assembly_id"],
        "board_occurrences": [BOARD_A, BOARD_B],
        "model_scope": {"pi": "Actual SPIKE lumped linear DC operating point on explicit power and return conductors.",
                        "si": "Actual SPIKE sampled four-conductor MTL using geometry-derived approximate RLGC above an ideal plane.",
                        "loads": "12 V source and 4 A board-B DC load; SI ports are explicit 50 ohm single-ended references (100 ohm differential normalization)."},
        "result_summary": {"pi": validation["pi"], "uniform_gui_si": validation["uniform_gui_si"],
                           "si": {key: value for key, value in validation["si"].items() if key != "frequency_response"}},
        "limitations": ["Original synthetic connector/pin identities; no actual board pinout was supplied or inferred.",
            "DC excludes board copper, connector/contact resistance and temperature feedback.",
            "Signal reference is an ideal infinite ground plane; power/return wires are not silently used as that reference.",
            "Thin straight round-wire quasi-TEM approximation only; no launch, bend, shield, radiation, full-wave, BER or compliance claim.",
            "Sampled passivity and reciprocity are checked; broadband causality and measured correlation remain unqualified."],
        "integration": integration,
        "artifacts": ["assembly-view.json", "harness-document.json", "pi-request.json", "pi-result.json",
            "harness-si-request.json", "harness-si-result.json",
            "rlgc-request.json", "rlgc-result.json", "mtl-request.json", "mtl-result.json",
            "mtl-diagonal-control-result.json", "validation.json", "integration.json", "evidence.json"]}
    artifacts = {"assembly-view.json": assembly, "harness-document.json": document,
        "pi-request.json": pi_input, "pi-result.json": pi_result,
        "harness-si-request.json": uniform_input, "harness-si-result.json": uniform_result,
        "rlgc-request.json": geometry_input,
        "rlgc-result.json": geometry_result, "mtl-request.json": mtl_input, "mtl-result.json": mtl_result,
        "mtl-diagonal-control-result.json": control_result, "validation.json": validation,
        "integration.json": integration, "report.json": report}
    source_paths = ["examples/high_speed_si/harness/run_interboard_harness.py", "python/spike_core/harness_pi.py",
                    "python/spike_core/harness_rlgc_geometry.py", "python/spike_core/harness_mtl.py"]
    artifacts["evidence.json"] = {"status": "passed", "production_qualified": False,
        "artifact_sha256": {name: _sha256_json(value) for name, value in artifacts.items()},
        "source_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in source_paths},
        "runtime": {"python": platform.python_version(), "platform": platform.platform(),
                    "numpy": np.__version__, "scipy": scipy.__version__}}
    return artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path, help="Fresh directory for JSON evidence artifacts")
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError(f"Use a fresh output directory; refusing to overwrite {args.output_dir}")
    artifacts = run_case()
    args.output_dir.mkdir(parents=True)
    for name, value in artifacts.items():
        (args.output_dir / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "passed", "output_dir": str(args.output_dir),
        "peak_next": artifacts["validation.json"]["si"]["peak_differential_next"],
        "peak_fext": artifacts["validation.json"]["si"]["peak_differential_fext"],
        "pi_load_voltage_v": artifacts["validation.json"]["pi"]["load_voltage_v"]}, indent=2))


if __name__ == "__main__":
    main()
