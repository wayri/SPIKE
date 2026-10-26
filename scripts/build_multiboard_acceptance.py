# SPDX-License-Identifier: Apache-2.0
"""Build and execute a three-occurrence native SPIKE multiboard acceptance case."""
from __future__ import annotations

import argparse
import copy
import hashlib
import heapq
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core import __version__
from python.spike_core.assembly_frames import IDENTITY
from python.spike_core.harness_authoring import discover_connectors, validate_harness_connections
from python.spike_core.solvers.circuits.models.multiboard_circuit import run_multiboard_circuit
from python.spike_core.solvers.thermal_fluid.heat.multiboard_thermal import run_multiboard_thermal
from python.spike_core.project_package import _source_member_name, read_project, write_spike_package
from python.spike_core.service_project import import_design
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.spider_v2 import AssemblyIRV1
from python.spike_core.spider_v2_schema import content_digest
from python.spike_core.solvers.geometry_meshing.preparation.geometry import extract_net_geometry
from python.spike_core.contracts import AnalysisSpec, SpiDeR
from python.spike_core.solvers.geometry_meshing.preparation.hybrid_mesh import build_hybrid_mesh, nearest_mesh_node

SOURCE = ROOT / "app/public/demo/ebrake1.kicad_pcb"
DEFAULT_OUTPUT = ROOT / "build/multiboard-acceptance-20261001"
PINS = ("2", "4")


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8")


def _frame(x: float, z: float) -> list[float]:
    matrix = list(IDENTITY)
    matrix[3], matrix[11] = x, z
    return matrix


def _pin_owners(design: dict, reference: str) -> dict:
    component = next(item for item in design["components"] if item["reference"] == reference)
    nets = {item["id"]: item["name"] for item in design["nets"]}
    pads = {item["id"]: item for item in design["pads"]}
    owners = {}
    for pin in design["pins"]:
        if pin["component_id"] != component["id"] or pin["number"] not in PINS:
            continue
        owners[pin["number"]] = {"pin_id": pin["id"], "pad_ids": pin["pad_ids"],
            "net_id": pin["net_id"], "net_name": nets[pin["net_id"]],
            "pad_centers_mm": [pads[pad_id]["center_mm"] for pad_id in pin["pad_ids"]]}
    if set(owners) != set(PINS) or owners["2"]["net_name"] != "3Vin" or owners["4"]["net_name"] != "GND":
        raise ValueError(f"{reference} physical 3Vin/GND pin ownership changed.")
    return owners


def _mapping(board_id: str, reference: str, connectors: dict, design: dict) -> dict:
    key = f"{board_id}::{reference}"
    discovered = connectors[key]
    return {"id": f"map-{board_id}-{reference}", "kind": "connector-pin-map",
        "name": key, "data": {"board_id": board_id, "connector_id": reference,
            "position_mm": discovered["position_mm"], "pins": {pin: discovered["pins"][pin] for pin in PINS},
            "pin_ownership": _pin_owners(design, reference)}}


def _circuit(assembly: dict, ids: list[str], *, domain: str) -> dict:
    a, b, c = ids
    ac = domain == "si"
    # Every resistance, inductance, and load here is an assumed model input.
    board_models = [
        {"board_id": a, "elements": [{"id": "supply", "type": "voltage_source",
            "positive_node": "J7:2", "negative_node": "J7:4", "dc_value": 3.3,
            "ac_magnitude": 1.0}]},
        {"board_id": b, "elements": [
            {"id": "power-path", "type": "resistor", "positive_node": "J7:2", "negative_node": "J5:2", "resistance_ohm": .02},
            {"id": "return-path", "type": "resistor", "positive_node": "J7:4", "negative_node": "J5:4", "resistance_ohm": .02},
            {"id": "operating-load", "type": "resistor", "positive_node": "J5:2", "negative_node": "J5:4", "resistance_ohm": 10.0}]},
        {"board_id": c, "elements": [{"id": "operating-load", "type": "resistor",
            "positive_node": "J5:2", "negative_node": "J5:4", "resistance_ohm": 15.0}]},
    ]
    links = [
        {"link_id": "stacked-mate", "kind": "mate", "pins": [
            {"source_pin": pin, "target_pin": pin, "resistance_ohm": .005, "inductance_h": 1e-9}
            for pin in PINS]},
        {"link_id": "side-harness", "kind": "harness", "pins": [
            {"source_pin": pin, "target_pin": pin, "resistance_ohm": .08, "inductance_h": 100e-9}
            for pin in PINS]},
    ]
    return {"contract": "spike/multiboard-circuit-request/v1", "domain": domain,
        "assembly": assembly, "board_models": board_models, "link_models": links,
        "ground": {"board_id": a, "node": "J7:4"},
        "analysis": {"mode": "ac", "start_hz": 1e3, "stop_hz": 1e6, "points": 9, "scale": "log"}
        if ac else {"mode": "operating_point"}}


def _thermal(assembly: dict, ids: list[str], design: dict, pi: dict) -> dict:
    bounds = design["metadata"]["board_bounds_mm"]
    area_mm2 = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
    power = pi["native_result"]["data"]["element_power_w"]
    loads = [0.2, *[
        power[pi["element_map"][board]["operating-load"]] for board in ids[1:]
    ]]
    surfaces = [
        {"id": f"board-{index}-facing", "board_id": board, "node": "board",
         "area_mm2": area_mm2, "emissivity": 0.85,
         "view_factors": {f"board-{1-index}-facing": 0.35, "ambient": 0.65}
         if index < 2 else {"ambient": 1.0}}
        for index, board in enumerate(ids)
    ]
    return {"contract": "spike/multiboard-thermal-request/v1", "assembly": assembly,
        "board_models": [{"board_id": board, "elements": [
            {"id": "board", "power_w": loads[index], "ambient_resistance_c_per_w": 25.0,
             "thermal_capacitance_j_per_c": 15.0}], "links": []}
            for index, board in enumerate(ids)],
        "contact_models": [{"contact_id": "stacked-standoff",
            "from": {"board_id": ids[0], "node": "board"},
            "to": {"board_id": ids[1], "node": "board"},
            "conductance_w_per_k": 0.01}],
        "radiation_surfaces": surfaces, "ambient_temperature_c": 25.0, "mode": "steady_state"}


def _routed_resistance(design: SpiDeR) -> dict:
    """Extract a minimum series-R copper path; parallel equivalent R is separate."""
    mesh = build_hybrid_mesh(design, AnalysisSpec(mode="dc", net_names=["3Vin"], mesh={"target_size_mm": 3.0}))
    pads = {pad["component_pad"]: pad for pad in design.pads}
    terminals = ("J7.2", "J11.1")
    node_ids = [nearest_mesh_node(mesh, {"position_mm": pads[name]["at"],
        "geometry_anchor": {"id": pads[name]["id"], "type": "pad"}}, "3Vin") for name in terminals]
    if mesh.truncated or any(node is None for node in node_ids):
        raise ValueError("The 3Vin mesh could not bind both physical connector pad terminals.")
    adjacency = {node.id: [] for node in mesh.nodes}
    for index, branch in enumerate(mesh.branches):
        if branch.net != "3Vin":
            continue
        resistance = branch.resistance_ohm
        adjacency[branch.node_p].append((branch.node_n, resistance, index))
        adjacency[branch.node_n].append((branch.node_p, resistance, index))
    start, end = node_ids
    distances, parent, queue = {start: 0.0}, {}, [(0.0, start)]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances.get(node):
            continue
        if node == end:
            break
        for adjacent, resistance, index in adjacency[node]:
            candidate = distance + resistance
            if candidate < distances.get(adjacent, float("inf")):
                distances[adjacent] = candidate
                parent[adjacent] = (node, index)
                heapq.heappush(queue, (candidate, adjacent))
    if end not in distances:
        samples = [branch for branch in mesh.branches if branch.kind == "track" and branch.net == "3Vin"]
        if not samples:
            raise ValueError("The 3Vin mesh has no extracted track resistance.")
        sample = max(samples, key=lambda branch: branch.length_mm)
        return {"contract": "spike/multiboard-routed-resistance-evidence/v1",
            "source_net": "3Vin", "terminals": list(terminals), "terminal_node_ids": node_ids,
            "connector_path_status": "disconnected_in_extracted_mesh",
            "sample_track_source_id": sample.source_id, "sample_track_length_mm": sample.length_mm,
            "sample_track_resistance_ohm": sample.resistance_ohm,
            "mesh_node_count": len(mesh.nodes), "mesh_branch_count": len(mesh.branches),
            "mesh_issues": [{"code": issue.code, "severity": issue.severity, "message": issue.message}
                for issue in mesh.issues],
            "model_status": "approximate", "equivalent_port_resistance": False}
    branch_ids = []
    cursor = end
    while cursor != start:
        cursor, index = parent[cursor]
        branch_ids.append(index)
    branch_ids.reverse()
    return {"contract": "spike/multiboard-routed-resistance-evidence/v1",
        "source_net": "3Vin", "terminals": list(terminals), "terminal_node_ids": node_ids,
        "connector_path_status": "connected", "minimum_series_path_resistance_ohm": distances[end],
        "path_branch_count": len(branch_ids),
        "path_length_mm": sum(mesh.branches[index].length_mm for index in branch_ids),
        "branch_kinds": {kind: sum(mesh.branches[index].kind == kind for index in branch_ids)
            for kind in sorted({mesh.branches[index].kind for index in branch_ids})},
        "mesh_node_count": len(mesh.nodes), "mesh_branch_count": len(mesh.branches),
        "mesh_issues": [{"code": issue.code, "severity": issue.severity, "message": issue.message}
            for issue in mesh.issues],
        "method": "Dijkstra minimum sum of extracted hybrid conductor branch DC resistance; no parallel current redistribution",
        "model_status": "approximate", "equivalent_port_resistance": False}


def build(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    project = output / "three-ebrake-assembly.spike"
    source_bytes = SOURCE.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    design = import_design(str(SOURCE), with_report=True)["design"]
    if design["source"]["source_digest"] != source_sha:
        raise ValueError("Imported design does not match the source bytes.")
    design["source"]["artifact_path"] = "package:" + _source_member_name(SOURCE.name, source_sha)
    manifest = write_spike_package(project, {"project": {"id": "multiboard-acceptance-20261001",
        "name": "Three eBrake board acceptance"}, "design_ir": design},
        source_artifacts={SOURCE.name: source_bytes}, application_version=__version__)
    response = handle_project_request("import_into_assembly_project", {
        "project_path": str(project), "source_paths": [str(SOURCE), str(SOURCE)],
        "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
    }, request_id="multiboard-acceptance", application_version=__version__)
    if not response or not response.get("ok"):
        raise RuntimeError(f"Batch board import failed: {response}")
    imported = response["result"]
    opened = read_project(project, include_members=True)
    payload = dict(opened.payload)
    raw = payload["assembly_ir"]
    if len(raw["boards"]) != 3 or len(set(board["design_id"] for board in raw["boards"])) != 1:
        raise ValueError("Batch import did not retain three occurrences of one board design.")
    ids = ["ebrake-source", "ebrake-stacked", "ebrake-side"]
    for index, board in enumerate(raw["boards"]):
        board["id"] = ids[index]
        board["name"] = ("eBrake source", "eBrake stacked load", "eBrake side load")[index]
        board["frame"]["frame_id"] = ids[index] + "-frame"
        board["frame"]["transform"] = _frame((0, 0, 180)[index], (0, 8, 0)[index])
    assembly = AssemblyIRV1.from_dict(raw)
    connectors = discover_connectors(assembly, {design["design_id"]: design})
    raw["connector_mappings"] = [
        _mapping(ids[0], "J7", connectors, design),
        _mapping(ids[1], "J7", connectors, design),
        _mapping(ids[1], "J5", connectors, design),
        _mapping(ids[2], "J5", connectors, design),
        {"id": "stacked-mate", "kind": "connector-mate", "name": "stacked direct mate",
            "data": {"endpoint_a": f"{ids[0]}::J7", "endpoint_b": f"{ids[1]}::J7",
                "pin_map": {"2": "2", "4": "4"}}},
    ]
    raw["harnesses"] = [{"id": "side-harness", "name": "side virtual harness",
        "endpoint_a": f"{ids[1]}::J5", "endpoint_b": f"{ids[2]}::J5",
        "length_mm": 230.0, "pin_map": {"2": "2", "4": "4"}}]
    raw["thermal_contacts"] = [{"id": "stacked-standoff", "name": "assumed standoff path",
        "endpoint_a": ids[0], "endpoint_b": ids[1], "contact_type": "mechanical"}]
    assembly = AssemblyIRV1.from_dict(raw)
    validate_harness_connections(assembly)
    payload["assembly_ir"] = assembly.to_dict()
    payload["audit"] = [*(payload.get("audit") or []), {"event": "multiboard_acceptance_setup",
        "source_sha256": source_sha, "board_ids": ids, "model_status": "experimental"}]
    manifest = write_spike_package(project, payload, preserved_members=opened.members,
        application_version=__version__)
    verified = read_project(project, include_members=True)
    if verified.manifest["manifest_payload_sha256"] != manifest["manifest_payload_sha256"]:
        raise ValueError("Saved native project did not verify.")
    solved = {}
    for domain in ("pi", "si"):
        request = _circuit(verified.payload["assembly_ir"], ids, domain=domain)
        result = run_multiboard_circuit(request)
        solved[domain] = result
        _json(output / f"{domain}-request.json", request)
        _json(output / f"{domain}-result.json", result)
        if result["status"] != "completed":
            raise RuntimeError(f"Reduced {domain.upper()} solve failed: {result['native_result'].get('diagnostics')}")
    thermal_request = _thermal(verified.payload["assembly_ir"], ids, design, solved["pi"])
    thermal_result = run_multiboard_thermal(thermal_request)
    _json(output / "thermal-request.json", thermal_request)
    _json(output / "thermal-result.json", thermal_result)
    if thermal_result["status"] != "completed":
        raise RuntimeError("Coupled thermal radiation solve did not complete.")
    disabled_request = copy.deepcopy(thermal_request)
    disabled_request["board_models"][1]["elements"][0]["power_w"] = 0.0
    disabled_result = run_multiboard_thermal(disabled_request)
    if disabled_result["status"] != "completed":
        raise RuntimeError("Stacked-power-disabled thermal sensitivity did not complete.")
    _json(output / "thermal-stacked-disabled-request.json", disabled_request)
    _json(output / "thermal-stacked-disabled-result.json", disabled_result)
    source_id = ids[0]
    baseline_source_c = thermal_result["board_temperatures_c"][source_id]["board"]
    disabled_source_c = disabled_result["board_temperatures_c"][source_id]["board"]
    sensitivity = {"contract": "spike/multiboard-powered-board-sensitivity/v1",
        "changed_board_id": ids[1], "observed_board_id": source_id,
        "baseline_stacked_power_w": thermal_request["board_models"][1]["elements"][0]["power_w"],
        "disabled_stacked_power_w": 0.0,
        "source_power_w": thermal_request["board_models"][0]["elements"][0]["power_w"],
        "side_power_w": thermal_request["board_models"][2]["elements"][0]["power_w"],
        "source_baseline_temperature_c": baseline_source_c,
        "source_stacked_disabled_temperature_c": disabled_source_c,
        "source_temperature_change_c": baseline_source_c - disabled_source_c,
        "method": "two completed explicit radiosity/RC solves with only stacked board power changed"}
    _json(output / "thermal-powered-board-sensitivity.json", sensitivity)
    legacy = SpiDeR(**import_design(str(SOURCE)))
    geometry = {net: extract_net_geometry(legacy, net) for net in ("3Vin", "GND")}
    _json(output / "extracted-net-geometry.json", geometry)
    routed = _routed_resistance(legacy)
    _json(output / "routed-resistance.json", routed)
    summary = {"contract": "spike/multiboard-acceptance/v1", "project": project.name,
        "source": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "source_sha256": source_sha,
        "manifest_payload_sha256": manifest["manifest_payload_sha256"], "board_ids": ids,
        "design_id": design["design_id"], "batch_source_counts": [
            {"source_name": item["source_name"], "board_count": item["board_count"],
             "part_count": item["part_count"]} for item in imported["sources"]],
        "connector_endpoints": [f"{ids[0]}::J7", f"{ids[1]}::J7", f"{ids[1]}::J5", f"{ids[2]}::J5"],
        "geometry_counts": {net: item["counts"] for net, item in geometry.items()},
        "routed_resistance_ohm": routed.get("minimum_series_path_resistance_ohm"),
        "connector_copper_path_status": routed["connector_path_status"],
        "results": {"pi": "pi-result.json", "si": "si-result.json", "thermal": "thermal-result.json",
                    "thermal_sensitivity": "thermal-powered-board-sensitivity.json"},
        "source_license": "Repository bundled demo board; source file has no embedded license declaration. Consult repository provenance before redistribution.",
        "qualification": "experimental reduced models; geometry extracted separately; no field-derived circuit values or view factors"}
    summary["artifact_sha256"] = {
        name: hashlib.sha256((output / name).read_bytes()).hexdigest()
        for name in ("pi-request.json", "pi-result.json", "si-request.json", "si-result.json",
                     "thermal-request.json", "thermal-result.json",
                     "thermal-stacked-disabled-request.json", "thermal-stacked-disabled-result.json",
                     "thermal-powered-board-sensitivity.json", "extracted-net-geometry.json", "routed-resistance.json")
    }
    _json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
