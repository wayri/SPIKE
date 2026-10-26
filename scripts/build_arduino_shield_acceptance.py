# SPDX-License-Identifier: Apache-2.0
"""Fetch, convert, package, and solve a real Arduino UNO R4/shield assembly.

Third-party CAD is retained under ``build/`` only.  The pinned archive hashes
make a changed upstream download fail closed instead of silently changing the
acceptance input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core import __version__
from python.spike_core.assembly_frames import IDENTITY
from python.spike_core.harness_authoring import discover_connectors, validate_harness_connections
from python.spike_core.solvers.circuits.models.multiboard_circuit import run_multiboard_circuit
from python.spike_core.solvers.electromagnetics.fields.multiboard_em import run_multiboard_em
from python.spike_core.solvers.thermal_fluid.heat.multiboard_thermal import run_multiboard_thermal
from python.spike_core.project_package import _source_member_name, read_project, write_spike_package
from python.spike_core.project_state_artifacts import hydrate_result_state
from python.spike_core.multiboard_study import validate_study_result
from python.spike_core.service_project import import_design
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.spider_v2 import AssemblyIRV1

DEFAULT_OUTPUT = ROOT / "build/arduino-shield-acceptance-20261002"
DEFAULT_SOURCE_CACHE = ROOT / "build/arduino-shield-acceptance-20261002/sources"
SOURCES = {
    "uno": {
        "product": "Arduino UNO R4 Minima ABX00080",
        "url": "https://docs.arduino.cc/static/ae97aad5c05de6a565c7f93a28c04717/ABX00080-cad-files.zip",
        "sha256": "37d7bcab7a6048619abdecee6d41582b825c3a1d045bb26821c1e36dcbd9ce26",
        "member": "ABX00080-cad-files/Altium files/PCB.PcbDoc",
        "format": "altium",
        "license_member": "ABX00080-cad-files/License.txt",
    },
    "shield": {
        "product": "Arduino 4 Relays Shield A000110",
        "url": "https://docs.arduino.cc/static/c919f2fcead5d5e20cd8957999d0297f/A000110-cad-files.zip",
        "sha256": "825d46d3f223a8be0a575cc6cf30979ef58b16b2f571032a2942d4ce0aab90a8",
        "member": "A000110-cad-files/4RelaysShieldV2.0.brd",
        "format": "eagle",
        "license_member": "A000110-cad-files/License.txt",
    },
}
EXPECTED_IMPORT_COUNTS = {
    "uno": {"components": 85, "pads": 304, "nets": 64},
    "shield": {"components": 47, "pads": 167, "nets": 35},
}


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _kicad_cli() -> Path:
    found = shutil.which("kicad-cli")
    candidates = [Path(found)] if found else []
    candidates += sorted(Path("C:/Program Files/KiCad").glob("*/bin/kicad-cli.exe"), reverse=True)
    if not candidates:
        raise RuntimeError("KiCad CLI was not found; KiCad 10 or newer is required for reproducible CAD import.")
    return candidates[0]


def prepare_sources(output: Path, *, offline: bool = False,
                    source_cache: Path | None = None) -> tuple[dict, dict[str, Path]]:
    source_dir = output / "sources"
    converted_dir = output / "converted"
    source_dir.mkdir(parents=True, exist_ok=True)
    converted_dir.mkdir(parents=True, exist_ok=True)
    cli = _kicad_cli()
    provenance, converted = {}, {}
    for key, spec in SOURCES.items():
        archive = source_dir / (Path(spec["url"]).name)
        if not archive.exists():
            cached = source_cache / archive.name if source_cache else None
            if cached and cached.is_file():
                shutil.copy2(cached, archive)
            elif offline:
                raise FileNotFoundError(f"Offline source archive is missing: {archive}")
            else:
                urllib.request.urlretrieve(spec["url"], archive)
        observed = _sha(archive)
        if observed != spec["sha256"]:
            raise ValueError(f"Pinned {key} archive digest changed: {observed}")
        extracted = source_dir / key
        if not extracted.exists():
            with zipfile.ZipFile(archive) as package:
                package.extractall(extracted)
        source = extracted / spec["member"]
        license_path = extracted / spec["license_member"]
        license_text = license_path.read_text(encoding="utf-8").strip()
        if "Creative Commons Attribution-ShareAlike 4.0" not in license_text:
            raise ValueError(f"Expected CC BY-SA 4.0 license is absent from {key} archive.")
        board = converted_dir / f"{key}.kicad_pcb"
        report = converted_dir / f"{key}-import-report.json"
        board.unlink(missing_ok=True)
        report.unlink(missing_ok=True)
        command = [str(cli), "pcb", "import", "--format", spec["format"],
                   "--report-format", "json", "--report-file", str(report),
                   "--output", str(board), str(source)]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        if completed.returncode:
            raise RuntimeError(f"KiCad import failed for {key}:\n{completed.stdout}\n{completed.stderr}")
        converted[key] = board
        provenance[key] = {**spec, "archive_sha256": observed, "source_member_sha256": _sha(source),
            "converted_sha256": _sha(board), "license": license_text,
            "kicad_import_report": report.name, "kicad_stdout": completed.stdout.strip(),
            "kicad_stderr": completed.stderr.strip()}
    provenance["kicad_cli"] = subprocess.run([str(cli), "version"], text=True,
        capture_output=True).stdout.strip()
    _json(output / "source-provenance.json", provenance)
    return provenance, converted


def _frame(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> list[float]:
    result = list(IDENTITY)
    result[3], result[7], result[11] = x, y, z
    return result


def _pin_center(design: dict, reference: str, number: str) -> tuple[float, float]:
    component = next(c for c in design["components"] if c["reference"] == reference)
    pin = next(p for p in design["pins"] if p["component_id"] == component["id"] and p["number"] == number)
    pads = {p["id"]: p for p in design["pads"]}
    centers = [pads[identifier]["center_mm"] for identifier in pin["pad_ids"]]
    if len(centers) != 1:
        raise ValueError(f"{reference}:{number} needs one unambiguous pad center, found {centers}")
    return tuple(centers[0])


def _transform_xy(matrix: list[float], point: tuple[float, float]) -> tuple[float, float, float]:
    return (matrix[0]*point[0] + matrix[1]*point[1] + matrix[3],
            matrix[4]*point[0] + matrix[5]*point[1] + matrix[7], matrix[11])


def _pin_mapping(board_id: str, connector: str, pins: tuple[str, ...], inventory: dict, design: dict) -> dict:
    component = next(item for item in design["components"] if item["reference"] == connector)
    components = {item["reference"]: item["id"] for item in design["components"]}
    nets = {item["id"]: item["name"] for item in design["nets"]}
    owners = {pin["number"]: {"pin_id": pin["id"], "net_id": pin["net_id"],
        "net_name": nets[pin["net_id"]], "pad_ids": pin["pad_ids"]}
        for pin in design["pins"] if pin["component_id"] == components[connector] and pin["number"] in pins}
    if set(owners) != set(pins):
        raise ValueError(f"Missing physical pins on {board_id}::{connector}: {pins}")
    found = inventory.get(f"{board_id}::{connector}", {"position_mm": [*component["position_mm"], 0.0],
        "pins": {pin: owners[pin]["net_name"] for pin in pins}})
    return {"id": f"map-{board_id}-{connector}", "kind": "connector-pin-map",
        "name": f"{board_id}::{connector}", "data": {"board_id": board_id,
        "connector_id": connector, "position_mm": found["position_mm"],
        "pins": {pin: found["pins"][pin] for pin in pins}, "pin_ownership": owners}}


def _circuit(assembly: dict, domain: str) -> dict:
    base, shield = "uno-r4-minima", "relay-shield"
    if domain == "pi":
        models = [
            {"board_id": base, "elements": [{"id": "supply", "type": "voltage_source",
                "positive_node": "JANALOG:5", "negative_node": "JANALOG:6", "dc_value": 5.0},
                {"id": "gpio-bias", "type": "resistor", "positive_node": "JDIGITAL:6",
                 "negative_node": "JANALOG:6", "resistance_ohm": 1_000_000.0}]},
            {"board_id": shield, "elements": [{"id": "relay-bank-load", "type": "resistor",
                "positive_node": "POWER0:5", "negative_node": "POWER0:6", "resistance_ohm": 25.0},
                {"id": "input-bias", "type": "resistor", "positive_node": "JLOW0:6",
                 "negative_node": "POWER0:6", "resistance_ohm": 1_000_000.0}]},
        ]
        links = [{"link_id": "power-header-mate", "kind": "mate", "pins": [
            {"source_pin": pin, "target_pin": pin, "resistance_ohm": 0.01, "inductance_h": 2e-9}
            for pin in ("5", "6")]},
            {"link_id": "digital-header-mate", "kind": "mate", "pins": [
                {"source_pin": "6", "target_pin": "6", "resistance_ohm": 0.02, "inductance_h": 5e-9}]}]
        analysis = {"mode": "operating_point"}
        ground = {"board_id": base, "node": "JANALOG:6"}
    else:
        models = [
            {"board_id": base, "elements": [{"id": "gpio-drive", "type": "voltage_source",
                "positive_node": "JDIGITAL:6", "negative_node": "JANALOG:6", "dc_value": 0.0,
                "ac_magnitude": 1.0}, {"id": "power-bias", "type": "resistor",
                "positive_node": "JANALOG:5", "negative_node": "JANALOG:6", "resistance_ohm": 1_000_000.0}]},
            {"board_id": shield, "elements": [{"id": "input-load", "type": "resistor",
                "positive_node": "JLOW0:6", "negative_node": "POWER0:6", "resistance_ohm": 10_000.0},
                {"id": "power-bias", "type": "resistor", "positive_node": "POWER0:5",
                 "negative_node": "POWER0:6", "resistance_ohm": 1_000_000.0}]},
        ]
        links = [
            {"link_id": "power-header-mate", "kind": "mate", "pins": [
                {"source_pin": pin, "target_pin": pin, "resistance_ohm": 0.01, "inductance_h": 2e-9}
                for pin in ("5", "6")]},
            {"link_id": "digital-header-mate", "kind": "mate", "pins": [
                {"source_pin": "6", "target_pin": "6", "resistance_ohm": 0.02, "inductance_h": 5e-9}]},
        ]
        analysis = {"mode": "ac", "start_hz": 1e3, "stop_hz": 10e6, "points": 17, "scale": "log"}
        ground = {"board_id": base, "node": "JANALOG:6"}
    return {"contract": "spike/multiboard-circuit-request/v1", "domain": domain,
        "assembly": assembly, "board_models": models, "link_models": links,
        "ground": ground, "analysis": analysis}


def _persist_study(project: Path, domain: str, request: dict, result: dict) -> dict:
    opened = read_project(project)
    setup = {key: value for key, value in request.items() if key != "assembly"}
    response = handle_project_request("save_multiboard_study_in_project", {
        "project_path": str(project),
        "expected_manifest_payload_sha256": opened.manifest["manifest_payload_sha256"],
        "domain": domain,
        "request": setup,
        "result": result,
        "assembly_digest": result["assembly_digest"],
    }, request_id=f"arduino-{domain}-study", application_version=__version__)
    if not response or not response.get("ok"):
        raise RuntimeError(f"{domain.upper()} study persistence failed: {response}")
    return response["result"]["manifest"]


def build(output: Path, *, offline: bool = False, source_cache: Path | None = None) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    provenance, boards = prepare_sources(output, offline=offline, source_cache=source_cache)
    designs = {key: import_design(str(path), with_report=True)["design"] for key, path in boards.items()}
    for key, expected in EXPECTED_IMPORT_COUNTS.items():
        observed = {"components": len(designs[key]["components"]), "pads": len(designs[key]["pads"]),
                    "nets": len(designs[key]["nets"])}
        if observed != expected:
            raise ValueError(f"{key} import count regression: expected {expected}, observed {observed}")
    project = output / "arduino-r4-relay-shield.spike"
    uno_bytes = boards["uno"].read_bytes()
    uno = designs["uno"]
    uno["source"]["artifact_path"] = "package:" + _source_member_name(boards["uno"].name, _sha(boards["uno"]))
    manifest = write_spike_package(project, {"project": {"id": "arduino-shield-acceptance-20261002",
        "name": "Arduino UNO R4 Minima plus 4 Relays Shield"}, "design_ir": uno},
        source_artifacts={boards["uno"].name: uno_bytes}, application_version=__version__)
    response = handle_project_request("import_into_assembly_project", {"project_path": str(project),
        "source_paths": [str(boards["shield"])],
        "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"]},
        request_id="arduino-shield-acceptance", application_version=__version__)
    if not response or not response.get("ok"):
        raise RuntimeError(f"Assembly import failed: {response}")
    opened = read_project(project, include_members=True)
    payload, raw = dict(opened.payload), opened.payload["assembly_ir"]
    if len(raw["boards"]) != 2 or len({b["design_id"] for b in raw["boards"]}) != 2:
        raise ValueError("Expected two distinct imported board designs.")
    ids = ["uno-r4-minima", "relay-shield"]
    for index, board in enumerate(raw["boards"]):
        board["id"], board["name"] = ids[index], ("Arduino UNO R4 Minima", "Arduino 4 Relays Shield")[index]
        board["frame"]["frame_id"] = ids[index] + "-frame"
        board["frame"]["transform"] = _frame() if index == 0 else _frame(114.2111, 131.6736, 11.0)
    assembly = AssemblyIRV1.from_dict(raw)
    retained = payload["assembly_designs"]["designs"]
    retained_uno = next(d for d in retained if any(c["reference"] == "JANALOG" for c in d["components"]))
    retained_shield = next(d for d in retained if any(c["reference"] == "POWER0" for c in d["components"]))
    design_by_id = {d["design_id"]: d for d in retained}
    inventory = discover_connectors(assembly, design_by_id)
    raw["connector_mappings"] = [
        _pin_mapping(ids[0], "JANALOG", ("5", "6"), inventory, retained_uno),
        _pin_mapping(ids[1], "POWER0", ("5", "6"), inventory, retained_shield),
        _pin_mapping(ids[0], "JDIGITAL", ("6",), inventory, retained_uno),
        _pin_mapping(ids[1], "JLOW0", ("6",), inventory, retained_shield),
        {"id": "power-header-mate", "kind": "connector-mate", "name": "physical UNO power header",
         "data": {"endpoint_a": f"{ids[0]}::JANALOG", "endpoint_b": f"{ids[1]}::POWER0",
                  "pin_map": {"5": "5", "6": "6"}}},
        {"id": "digital-header-mate", "kind": "connector-mate", "name": "physical UNO D5 header position",
         "data": {"endpoint_a": f"{ids[0]}::JDIGITAL", "endpoint_b": f"{ids[1]}::JLOW0",
                  "pin_map": {"6": "6"}}},
    ]
    raw["thermal_contacts"] = [{"id": "stacked-headers", "name": "assumed header/standoff path",
        "endpoint_a": ids[0], "endpoint_b": ids[1], "contact_type": "mechanical"}]
    assembly = AssemblyIRV1.from_dict(raw)
    validate_harness_connections(assembly)
    placement = {"contract": "spike/connector-aligned-placement-evidence/v1", "z_gap_mm": 11.0,
        "matches": []}
    transforms = {b["id"]: b["frame"]["transform"] for b in raw["boards"]}
    for pin in ("5", "6"):
        base_world = _transform_xy(transforms[ids[0]], _pin_center(retained_uno, "JANALOG", pin))
        shield_world = _transform_xy(transforms[ids[1]], _pin_center(retained_shield, "POWER0", pin))
        error = ((base_world[0]-shield_world[0])**2 + (base_world[1]-shield_world[1])**2)**0.5
        if error > 1e-6 or abs(shield_world[2]-base_world[2]-11.0) > 1e-9:
            raise ValueError(f"Connector-aligned placement failed at power pin {pin}: {error} mm")
        placement["matches"].append({"pin": pin, "base_world_mm": base_world,
            "shield_world_mm": shield_world, "xy_error_mm": error})
    _json(output / "placement-evidence.json", placement)
    payload["assembly_ir"] = assembly.to_dict()
    payload["audit"] = [*(payload.get("audit") or []), {"event": "arduino_shield_acceptance_setup",
        "source_archive_sha256": {k: provenance[k]["archive_sha256"] for k in ("uno", "shield")},
        "model_status": "experimental", "cad_license": "CC BY-SA 4.0"}]
    manifest = write_spike_package(project, payload, preserved_members=opened.members,
        source_artifacts={boards["shield"].name: boards["shield"].read_bytes()}, application_version=__version__)
    saved = read_project(project, include_members=True)
    results = {}
    for domain in ("pi", "si"):
        request = _circuit(saved.payload["assembly_ir"], domain)
        results[domain] = run_multiboard_circuit(request)
        _json(output / f"{domain}-request.json", request)
        _json(output / f"{domain}-result.json", results[domain])
        if results[domain]["status"] != "completed":
            raise RuntimeError(f"{domain.upper()} reduced solve failed.")
    pi_power = results["pi"]["native_result"]["data"]["element_power_w"]
    shield_power = pi_power[results["pi"]["element_map"][ids[1]]["relay-bank-load"]]
    areas = {}
    for key, identifier in (("uno", ids[0]), ("shield", ids[1])):
        b = designs[key]["metadata"]["board_bounds_mm"]
        areas[identifier] = (b[2] - b[0]) * (b[3] - b[1])
    f_us = 0.55
    f_su = areas[ids[0]] * f_us / areas[ids[1]]
    thermal_request = {"contract": "spike/multiboard-thermal-request/v1", "assembly": saved.payload["assembly_ir"],
        "board_models": [
            {"board_id": ids[0], "elements": [{"id": "board", "power_w": 0.35,
                "ambient_resistance_c_per_w": 18.0, "thermal_capacitance_j_per_c": 18.0}], "links": []},
            {"board_id": ids[1], "elements": [{"id": "board", "power_w": shield_power,
                "ambient_resistance_c_per_w": 22.0, "thermal_capacitance_j_per_c": 12.0}], "links": []}],
        "contact_models": [{"contact_id": "stacked-headers", "from": {"board_id": ids[0], "node": "board"},
            "to": {"board_id": ids[1], "node": "board"}, "conductance_w_per_k": 0.025}],
        "radiation_surfaces": [
            {"id": "uno-facing", "board_id": ids[0], "node": "board", "area_mm2": areas[ids[0]],
             "emissivity": 0.85, "view_factors": {"shield-facing": f_us, "ambient": 1-f_us}},
            {"id": "shield-facing", "board_id": ids[1], "node": "board", "area_mm2": areas[ids[1]],
             "emissivity": 0.85, "view_factors": {"uno-facing": f_su, "ambient": 1-f_su}}],
        "ambient_temperature_c": 25.0, "mode": "steady_state"}
    results["thermal"] = run_multiboard_thermal(thermal_request)
    _json(output / "thermal-request.json", thermal_request); _json(output / "thermal-result.json", results["thermal"])
    if results["thermal"]["status"] != "completed":
        raise RuntimeError("THERMAL reduced solve failed.")
    requests = {"pi": _circuit(saved.payload["assembly_ir"], "pi"),
                "si": _circuit(saved.payload["assembly_ir"], "si"),
                "thermal": thermal_request}
    for domain in ("pi", "si", "thermal"):
        manifest = _persist_study(project, domain, requests[domain], results[domain])
    reopened = read_project(project)
    hydrated = hydrate_result_state(reopened.payload, project,
                                    reopened.manifest["manifest_payload_sha256"])
    saved_studies = hydrated["assembly_ir"]["extensions"]["spike.multiboard-studies"]
    for domain in ("pi", "si", "thermal"):
        study = saved_studies[domain]
        validate_study_result(hydrated["assembly_ir"], domain, study["request"], study["result"])
        if study["result"] != results[domain]:
            raise RuntimeError(f"{domain.upper()} result changed during project persistence.")
    em_request = {"contract": "spike/multiboard-em-request/v1", "assembly": saved.payload["assembly_ir"],
        "loops": [
            {"loop_id": "uno-supply-loop", "board_id": ids[0], "resistance_ohm": 0.5,
             "self_inductance_h": 1e-6, "voltage_real_v": 1.0, "voltage_imag_v": 0.0},
            {"loop_id": "shield-relay-loop", "board_id": ids[1], "resistance_ohm": 2.0,
             "self_inductance_h": 1.2e-6, "voltage_real_v": 0.0, "voltage_imag_v": 0.0}],
        "mutual_inductances": [{"loop_a": "uno-supply-loop", "loop_b": "shield-relay-loop",
            "mutual_inductance_h": 0.15e-6}], "frequency_hz": [1e3, 1e4, 1e5, 1e6], "connector_models": []}
    results["em"] = run_multiboard_em(em_request)
    _json(output / "em-request.json", em_request); _json(output / "em-result.json", results["em"])
    unsupported = {"far_field_radiation": {"status": "unsupported",
        "reason": "The executable multiboard EM path is a supplied lumped reciprocal magnetic-loop model; it does not derive fields or radiation from these PCB artworks."},
        "full_wave_coupled_em": {"status": "unsupported",
        "reason": "No qualified general coupled PCB field solver is registered for this assembly."}}
    _json(output / "unsupported-em-capabilities.json", unsupported)
    summary = {"contract": "spike/arduino-shield-acceptance/v1", "project": project.name,
        "board_ids": ids, "distinct_design_count": 2, "source_provenance": "source-provenance.json",
        "manifest_payload_sha256": manifest["manifest_payload_sha256"],
        "design_counts": {key: {"components": len(designs[key]["components"]), "pads": len(designs[key]["pads"]),
            "nets": len(designs[key]["nets"])} for key in ("uno", "shield")},
        "retained_field_shape": {key: {"board_bounds_mm": designs[key]["metadata"]["board_bounds_mm"],
            "outline_primitive_count": len(designs[key]["metadata"]["board_outline_drawings"]),
            "copper_layer_count": designs[key]["metadata"]["copper_layer_count"],
            "stackup_row_count": len(designs[key]["metadata"]["spike.v1.stackup"]),
            "stackup_missing_copper_layers": designs[key]["metadata"]["stackup_missing_copper_layers"],
            "import_status": designs[key]["metadata"]["import_report"]["status"]}
            for key in ("uno", "shield")},
        "pre_link_equal_net_name": "GND (distinct design-local net IDs until explicit connector mate)",
        "placement_evidence": "placement-evidence.json",
        "results": {key: f"{key}-result.json" for key in ("pi", "si", "thermal", "em")},
        "saved_coupled_studies": ["pi", "si", "thermal"],
        "model_status": {key: results[key]["model_status"] for key in results},
        "production_qualified": {key: results[key]["production_qualified"] for key in results},
        "unsupported": unsupported}
    _json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--offline", action="store_true", help="Use only already downloaded, digest-matched archives.")
    parser.add_argument("--source-cache", type=Path, default=DEFAULT_SOURCE_CACHE,
                        help="Directory containing pinned source archives to copy before any download.")
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir.resolve(), offline=args.offline,
                           source_cache=args.source_cache.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
