# SPDX-License-Identifier: Apache-2.0
"""Build a local-only real CM4 IO Board plus Sailor Hat acceptance project."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core import __version__
from python.spike_core.harness_authoring import discover_connectors, validate_harness_connections
from python.spike_core.multiboard_circuit import run_multiboard_circuit
from python.spike_core.multiboard_thermal import run_multiboard_thermal
from python.spike_core.multiboard_identity import assembly_physics_digest
from python.spike_core.project_package import _source_member_name, read_project, write_spike_package
from python.spike_core.service_project import import_design
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.spider_v2 import AssemblyIRV1
from scripts.build_arduino_shield_acceptance import _frame, _json, _pin_mapping, _transform_xy

DEFAULT_OUTPUT = ROOT / "build/curated-multiboard-20261005/raspberry-pi"
DEFAULT_SOURCE_DIR = ROOT / "build/rpi-hat-acceptance-20261002/sources/SH-RPi-hardware"
CM4_ARCHIVE_SHA256 = "5ea867e17968cb9c117fbce7a982ea395d66a6ee605253a9a0879483bbfcb0aa"
HAT_COMMIT = "e82e3c9823bbcf94091b22927dd2e0da9cdfac8c"
HAT_BOARD_SHA256 = "d13c9adb68b25b2253ef61015362ed4f836d6d3488cd3e308427c239c1edc0ae"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _through_hole_center(design: dict, reference: str, number: str) -> tuple[float, float]:
    component = next(c for c in design["components"] if c["reference"] == reference)
    pin = next(p for p in design["pins"] if p["component_id"] == component["id"] and p["number"] == number)
    pads = {p["id"]: p for p in design["pads"]}
    candidates = [pads[i] for i in pin["pad_ids"] if pads[i]["pad_kind"] == "thru_hole"]
    if len(candidates) != 1:
        raise ValueError(f"{reference}:{number} needs one through-hole connector anchor.")
    return tuple(candidates[0]["center_mm"])


def _hat_frame() -> list[float]:
    # Proper 180-degree Y rotation aligns the mating faces and reverses the
    # HAT header's X pin ordering without reflection (determinant remains +1).
    return [-1.,0.,0.,200.5, 0.,1.,0.,67.55, 0.,0.,-1.,14., 0.,0.,0.,1.]


def _sources(output: Path, source_dir: Path) -> tuple[Path, Path, dict]:
    cm4_archive = ROOT / "build/arduino-shield-acceptance-20261002/pi-investigation/CM4IO-KiCAD.zip"
    cm4_board = ROOT / "build/arduino-shield-acceptance-20261002/pi-investigation/CM4IO-KiCAD/CM4IOv5.kicad_pcb"
    hat_repo = source_dir
    hat_board = hat_repo / "SH-RPi.kicad_pcb"
    if not cm4_archive.exists() or not cm4_board.exists():
        raise FileNotFoundError("Download the official CM4IO-KiCAD archive locally; see validation documentation.")
    if _sha(cm4_archive) != CM4_ARCHIVE_SHA256:
        raise ValueError("Official CM4IO archive digest differs from the reviewed local input.")
    if not hat_board.exists():
        raise FileNotFoundError("Provide the pinned SH-RPi-hardware checkout with --source-dir.")
    commit = subprocess.run(["git", "-C", str(hat_repo), "rev-parse", "HEAD"], text=True,
        capture_output=True, check=True).stdout.strip()
    if commit != HAT_COMMIT or _sha(hat_board) != HAT_BOARD_SHA256:
        raise ValueError("Sailor Hat revision or board digest differs from the reviewed input.")
    license_text = (hat_repo / "LICENSE.md").read_text(encoding="utf-8")
    if "Creative Commons Attribution 4.0 International" not in license_text:
        raise ValueError("Sailor Hat CC BY 4.0 license was not found.")
    provenance = {"cm4io": {"source": "Raspberry Pi Product Information Portal CM4IO-KiCAD",
        "archive_sha256": CM4_ARCHIVE_SHA256, "pcb_sha256": _sha(cm4_board),
        "redistribution": "local-use-only: archive contains no explicit PCB license grant"},
        "sailor_hat": {"source": "https://github.com/hatlabs/SH-RPi-hardware",
        "commit": commit, "pcb_sha256": HAT_BOARD_SHA256, "license": "CC BY 4.0",
        "creator": "Hat Labs Ltd"}}
    _json(output / "source-provenance.json", provenance)
    return cm4_board, hat_board, provenance


def _circuit(assembly: dict, domain: str) -> dict:
    base, hat = "cm4io", "sailor-hat"
    if domain == "pi":
        models = [{"board_id": base, "elements": [{"id": "source", "type": "voltage_source",
            "positive_node": "J8:2", "negative_node": "J8:6", "dc_value": 5.0},
            {"id": "sda-bias", "type": "resistor", "positive_node": "J8:3", "negative_node": "J8:6", "resistance_ohm": 1e6}]},
            {"board_id": hat, "elements": [{"id": "hat-load", "type": "resistor",
            "positive_node": "J501:2", "negative_node": "J501:6", "resistance_ohm": 12.5},
            {"id": "sda-bias", "type": "resistor", "positive_node": "J501:3", "negative_node": "J501:6", "resistance_ohm": 1e6}]}]
        analysis = {"mode": "operating_point"}
    else:
        models = [{"board_id": base, "elements": [{"id": "sda-drive", "type": "voltage_source",
            "positive_node": "J8:3", "negative_node": "J8:6", "dc_value": 0.0, "ac_magnitude": 1.0},
            {"id": "power-bias", "type": "resistor", "positive_node": "J8:2", "negative_node": "J8:6", "resistance_ohm": 1e6}]},
            {"board_id": hat, "elements": [{"id": "sda-load", "type": "resistor",
            "positive_node": "J501:3", "negative_node": "J501:6", "resistance_ohm": 4700.0},
            {"id": "power-bias", "type": "resistor", "positive_node": "J501:2", "negative_node": "J501:6", "resistance_ohm": 1e6}]}]
        analysis = {"mode": "ac", "start_hz": 1e3, "stop_hz": 10e6, "points": 17, "scale": "log"}
    link = {"link_id": "gpio-header-mate", "kind": "mate", "pins": [
        {"source_pin": pin, "target_pin": pin, "resistance_ohm": .012 if pin in ("2", "6") else .025,
         "inductance_h": 3e-9 if pin in ("2", "6") else 6e-9} for pin in ("2", "3", "6")]}
    return {"contract": "spike/multiboard-circuit-request/v1", "domain": domain,
        "assembly": assembly, "board_models": models, "link_models": [link],
        "ground": {"board_id": base, "node": "J8:6"}, "analysis": analysis}


def _acceptance(results: dict) -> dict:
    pi = results["pi"]
    pi_data = pi["native_result"]["data"]
    load_key = pi["element_map"]["sailor-hat"]["hat-load"]
    actual_power = pi_data["element_power_w"][load_key]
    expected_current = 5.0 / (12.5 + 0.012 + 0.012)
    expected_power = expected_current**2 * 12.5
    pi_relative_error = abs(actual_power - expected_power) / expected_power

    si = results["si"]
    si_data = si["native_result"]["data"]
    frequencies = si_data["frequency_hz"]
    signal_node = si_data["node_voltage_v"][si["node_map"]["sailor-hat"]["J501:3"]]
    return_node = si_data["node_voltage_v"][si["node_map"]["sailor-hat"]["J501:6"]]
    si_errors = []
    for index, frequency in enumerate(frequencies):
        omega = 2.0 * 3.141592653589793 * frequency
        signal_path = complex(0.025, omega * 6e-9)
        ground_path = complex(0.012, omega * 3e-9)
        bias_return = complex(2e6 + 0.012, omega * 3e-9)
        return_path = ground_path * bias_return / (ground_path + bias_return)
        expected = 4700.0 / (4700.0 + signal_path + return_path)
        observed = complex(signal_node["real"][index] - return_node["real"][index],
                           signal_node["imaginary"][index] - return_node["imaginary"][index])
        si_errors.append(abs(observed - expected))

    thermal = results["thermal"]
    thermal_residual = abs(thermal["summary"]["energy_balance_residual_w"])
    evidence = {
        "contract": "spike/curated-multiboard-acceptance/v1",
        "pi": {"oracle": "5 V / (12.5 ohm load + two 0.012 ohm connector returns)",
            "expected_load_power_w": expected_power, "actual_load_power_w": actual_power,
            "relative_error": pi_relative_error, "tolerance": 1e-10, "passed": pi_relative_error <= 1e-10},
        "si": {"oracle": "closed-form 4700 ohm divider through signal link and parallel ground/bias return paths",
            "frequency_points": len(frequencies), "max_complex_voltage_error_v": max(si_errors),
            "tolerance_v": 1e-10, "passed": max(si_errors) <= 1e-10},
        "thermal": {"oracle": "solver-reported steady heat input equals ambient rejection",
            "energy_balance_residual_w": thermal_residual, "tolerance_w": 1e-9,
            "passed": thermal_residual <= 1e-9},
    }
    evidence["passed"] = all(evidence[key]["passed"] for key in ("pi", "si", "thermal"))
    if not evidence["passed"]:
        raise ValueError(f"Curated numerical acceptance failed: {evidence}")
    return evidence


def _verify_packaged_board_sources(project: Path, expected_sources: dict[str, Path]) -> None:
    """Check every board occurrence through the same worker route used by the UI."""

    opened = read_project(project)
    designs = {item["design_id"]: item for item in opened.payload["assembly_designs"]["designs"]}
    manifest_digest = opened.manifest["manifest_payload_sha256"]
    for board in opened.payload["assembly_ir"]["boards"]:
        source_path = expected_sources[board["id"]]
        source_bytes = source_path.read_bytes()
        design_id = board["design_id"]
        if designs[design_id]["source"]["source_digest"] != hashlib.sha256(source_bytes).hexdigest():
            raise ValueError(f"Retained source digest changed for {board['id']}.")
        response = handle_project_request("prepare_assembly_design_visual_bundle", {
            "project_path": str(project), "expected_manifest_payload_sha256": manifest_digest,
            "design_id": design_id, "stage": "source",
        }, request_id=f"rpi-hat-source-{board['id']}", application_version=__version__)
        if not response or not response.get("ok"):
            raise RuntimeError(f"Could not read packaged board source for {board['id']}: {response}")
        result = response["result"]
        if result["design_id"] != design_id or result["source_board"].encode("utf-8") != source_bytes:
            raise ValueError(f"Packaged board source does not match {board['id']}.")


def build(output: Path, source_dir: Path = DEFAULT_SOURCE_DIR) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    cm4_path, hat_path, provenance = _sources(output, source_dir)
    designs = {"cm4io": import_design(str(cm4_path), with_report=True)["design"],
               "hat": import_design(str(hat_path), with_report=True)["design"]}
    counts = {key: {"components": len(d["components"]), "pads": len(d["pads"]), "nets": len(d["nets"])}
              for key, d in designs.items()}
    if counts != {"cm4io": {"components": 151, "pads": 944, "nets": 247},
                  "hat": {"components": 168, "pads": 540, "nets": 118}}:
        raise ValueError(f"Real-board import counts changed: {counts}")
    project = output / "cm4io-sailor-hat.spike"
    base = designs["cm4io"]
    base_digest = base["source"]["source_digest"]
    base["source"]["artifact_path"] = "package:" + _source_member_name(cm4_path.name, base_digest)
    manifest = write_spike_package(project, {"project": {"id": "rpi-hat-acceptance-20261002",
        "name": "Raspberry Pi CM4 IO plus Sailor Hat local acceptance"}, "design_ir": base},
        source_artifacts={cm4_path.name: cm4_path.read_bytes()},
        application_version=__version__)
    response = handle_project_request("import_into_assembly_project", {"project_path": str(project),
        "source_paths": [str(hat_path)], "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"]},
        request_id="rpi-hat-acceptance", application_version=__version__)
    if not response or not response.get("ok"):
        raise RuntimeError(f"Assembly import failed: {response}")
    opened = read_project(project, include_members=True); payload = dict(opened.payload); raw = payload["assembly_ir"]
    ids = ["cm4io", "sailor-hat"]
    for i, board in enumerate(raw["boards"]):
        board["id"] = ids[i]; board["name"] = ("Raspberry Pi CM4 IO Board", "Hat Labs Sailor Hat")[i]
        board["frame"]["frame_id"] = ids[i] + "-frame"; board["frame"]["transform"] = _frame() if i == 0 else _hat_frame()
    assembly = AssemblyIRV1.from_dict(raw); retained = payload["assembly_designs"]["designs"]
    base_d = next(d for d in retained if any(c["reference"] == "J8" for c in d["components"]))
    hat_d = next(d for d in retained if any(c["reference"] == "J501" for c in d["components"]))
    inventory = discover_connectors(assembly, {d["design_id"]: d for d in retained})
    raw["connector_mappings"] = [_pin_mapping(ids[0], "J8", ("2", "3", "6"), inventory, base_d),
        _pin_mapping(ids[1], "J501", ("2", "3", "6"), inventory, hat_d),
        {"id": "gpio-header-mate", "kind": "connector-mate", "name": "physical 40-pin GPIO header subset",
         "data": {"endpoint_a": "cm4io::J8", "endpoint_b": "sailor-hat::J501", "pin_map": {"2": "2", "3": "3", "6": "6"}}}]
    raw["thermal_contacts"] = [{"id": "gpio-standoffs", "name": "assumed header and standoffs",
        "endpoint_a": ids[0], "endpoint_b": ids[1], "contact_type": "mechanical"}]
    assembly = AssemblyIRV1.from_dict(raw); validate_harness_connections(assembly); payload["assembly_ir"] = assembly.to_dict()
    placement = {"contract": "spike/connector-aligned-placement-evidence/v1", "z_gap_mm": 14.0,
        "rotation": "proper 180 degree Y rotation", "matches": []}
    transforms = {b["id"]: b["frame"]["transform"] for b in raw["boards"]}
    for pin in ("2", "3", "6"):
        base_world = _transform_xy(transforms[ids[0]], _through_hole_center(base_d, "J8", pin))
        hat_world = _transform_xy(transforms[ids[1]], _through_hole_center(hat_d, "J501", pin))
        error = ((base_world[0]-hat_world[0])**2 + (base_world[1]-hat_world[1])**2)**.5
        if error > 1e-6 or abs(hat_world[2]-base_world[2]-14.) > 1e-9:
            raise ValueError(f"GPIO connector-aligned placement failed at pin {pin}: {error} mm")
        placement["matches"].append({"pin": pin, "cm4io_world_mm": base_world,
            "hat_world_mm": hat_world, "xy_error_mm": error})
    _json(output/"placement-evidence.json", placement)
    payload["audit"] = [*(payload.get("audit") or []), {"event": "rpi_hat_local_acceptance",
        "cm4io_archive_sha256": CM4_ARCHIVE_SHA256, "hat_commit": HAT_COMMIT,
        "source_provenance": provenance,
        "redistribution": "local build artifact only", "model_status": "experimental"}]
    manifest = write_spike_package(project, payload, preserved_members=opened.members,
        application_version=__version__)
    _verify_packaged_board_sources(project, {ids[0]: cm4_path, ids[1]: hat_path})
    saved = read_project(project, include_members=True); results = {}
    for domain in ("pi", "si"):
        request = _circuit(saved.payload["assembly_ir"], domain); results[domain] = run_multiboard_circuit(request)
        _json(output/f"{domain}-request.json", request); _json(output/f"{domain}-result.json", results[domain])
    power = results["pi"]["native_result"]["data"]["element_power_w"][results["pi"]["element_map"][ids[1]]["hat-load"]]
    areas = {ids[i]: (d["metadata"]["board_bounds_mm"][2]-d["metadata"]["board_bounds_mm"][0]) *
        (d["metadata"]["board_bounds_mm"][3]-d["metadata"]["board_bounds_mm"][1]) for i,d in enumerate(designs.values())}
    f = .25; reciprocal = areas[ids[0]]*f/areas[ids[1]]
    thermal = {"contract": "spike/multiboard-thermal-request/v1", "assembly": saved.payload["assembly_ir"],
        "board_models": [{"board_id": ids[0], "elements": [{"id": "board", "power_w": 2.5,
            "ambient_resistance_c_per_w": 9., "thermal_capacitance_j_per_c": 45.}], "links": []},
            {"board_id": ids[1], "elements": [{"id": "board", "power_w": power,
            "ambient_resistance_c_per_w": 16., "thermal_capacitance_j_per_c": 18.}], "links": []}],
        "contact_models": [{"contact_id": "gpio-standoffs", "from": {"board_id": ids[0], "node": "board"},
            "to": {"board_id": ids[1], "node": "board"}, "conductance_w_per_k": .035}],
        "radiation_surfaces": [{"id": "cm4io-facing", "board_id": ids[0], "node": "board", "area_mm2": areas[ids[0]],
            "emissivity": .85, "view_factors": {"hat-facing": f, "ambient": 1-f}},
            {"id": "hat-facing", "board_id": ids[1], "node": "board", "area_mm2": areas[ids[1]],
            "emissivity": .85, "view_factors": {"cm4io-facing": reciprocal, "ambient": 1-reciprocal}}],
        "ambient_temperature_c": 25., "mode": "steady_state"}
    results["thermal"] = run_multiboard_thermal(thermal); _json(output/"thermal-request.json", thermal); _json(output/"thermal-result.json", results["thermal"])
    acceptance = _acceptance(results); _json(output/"acceptance-evidence.json", acceptance)
    digest = assembly_physics_digest(saved.payload["assembly_ir"])
    current_manifest = manifest
    for domain, request in (("pi", _circuit(saved.payload["assembly_ir"], "pi")),
                            ("si", _circuit(saved.payload["assembly_ir"], "si")),
                            ("thermal", thermal)):
        setup = {key: value for key, value in request.items() if key != "assembly"}
        response = handle_project_request("save_multiboard_study_in_project", {
            "project_path": str(project), "expected_manifest_payload_sha256": current_manifest["manifest_payload_sha256"],
            "domain": domain, "request": setup, "result": results[domain], "assembly_digest": digest,
        }, request_id=f"rpi-hat-{domain}", application_version=__version__)
        if not response or not response.get("ok"):
            raise RuntimeError(f"Could not retain {domain} study: {response}")
        current_manifest = response["result"]["manifest"]
    unsupported = {"full_wave_coupled_em": {"status": "unsupported", "reason": "No qualified general PCB field solve executed."},
        "far_field_radiation": {"status": "unsupported", "reason": "Reduced magnetic loops do not derive radiation from artwork."}}
    _json(output/"unsupported-em-capabilities.json", unsupported)
    summary = {"contract": "spike/rpi-hat-acceptance/v1", "project": project.name, "board_ids": ids,
        "manifest_payload_sha256": current_manifest["manifest_payload_sha256"], "source_provenance": provenance,
        "design_counts": counts, "pre_link_equal_net_name": "GND (design-local until explicit GPIO mate)",
        "placement_evidence": "placement-evidence.json", "acceptance_evidence": "acceptance-evidence.json",
        "results": {k: f"{k}-result.json" for k in results}, "model_status": {k:v["model_status"] for k,v in results.items()},
        "production_qualified": {k:v["production_qualified"] for k,v in results.items()}, "unsupported": unsupported}
    _json(output/"summary.json", summary); return summary


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--output-dir",type=Path,default=DEFAULT_OUTPUT)
    p.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR,
        help="Existing pinned SH-RPi-hardware checkout; it is read in place and is not copied into the output.")
    a=p.parse_args(); print(json.dumps(build(a.output_dir.resolve(), a.source_dir.resolve()),indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
