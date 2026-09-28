# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Real polyMesh synthetic heated-duct fixture; preparation is not CFD evidence."""
from pathlib import Path

from .openfoam_multiregion import REQUEST_CONTRACT, prepare_runnable_multiregion_case
from .openfoam_multiregion_fixture import _structured_hex_mesh, _digest
from .openfoam_polymesh import write_polymesh


def build_fan_heated_fixture(output_root, *, divisions=4, board_count=1,
                             delta_t_s=.001, end_time_s=10, write_interval_steps=1000):
    """One/two 10mm square boards bounding an 8.4mm air duct; 0.1W each.

    The optional upper board spans z=10..11.6mm; both boards have separate
    source zones and mapped interfaces. This is synthetic slab geometry.
    """
    if isinstance(divisions, bool) or not isinstance(divisions, int) or not 1 <= divisions <= 32:
        raise ValueError("divisions must be an integer from 1 to 32")
    if isinstance(board_count, bool) or not isinstance(board_count, int) or board_count not in (1, 2):
        raise ValueError("board_count must be 1 or 2")
    for value in (delta_t_s, end_time_s):
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 < value < float("inf"):
            raise ValueError("Time controls must be positive finite numbers")
    if delta_t_s > end_time_s or end_time_s / delta_t_s > 10_000_000:
        raise ValueError("Time controls exceed fixture limits")
    if isinstance(write_interval_steps, bool) or not isinstance(write_interval_steps, int) or not 1 <= write_interval_steps <= 1_000_000:
        raise ValueError("write_interval_steps must be an integer from 1 to 1000000")
    root = Path(output_root).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Fixture output root must be empty")
    mesh_root = root / "meshes"
    board = _structured_hex_mesh(region_id="board", z0_mm=0, z1_mm=1.6, divisions=divisions,
        lower_patch="bottom", upper_patch="board_air", lower_mapped=None,
        upper_mapped={"neighbour_region": "air", "neighbour_patch": "air_board", "interface_id": "board_air"})
    air = _structured_hex_mesh(region_id="air", z0_mm=1.6, z1_mm=10, divisions=divisions,
        lower_patch="air_board", upper_patch="air_board2" if board_count == 2 else "top",
        upper_mapped={"neighbour_region": "board2", "neighbour_patch": "board2_air", "interface_id": "board2_air"} if board_count == 2 else None,
        lower_mapped={"neighbour_region": "board", "neighbour_patch": "board_air", "interface_id": "board_air"})
    external = next(patch for patch in air["boundary_patches"] if patch["name"] == "air_external")
    inlet, outlet, walls = [], [], []
    for face in external["faces"]:
        x = [air["mesh"]["vertices"][index][0] for index in face]
        (inlet if all(value == 0 for value in x) else outlet if all(value == 10 for value in x) else walls).append(face)
    external["faces"] = walls
    air["boundary_patches"].extend([
        {"name": "fan_in", "type": "patch", "faces": inlet},
        {"name": "exhaust", "type": "patch", "faces": outlet}])
    neutral_meshes = {"board": board, "air": air}
    if board_count == 2:
        upper = _structured_hex_mesh(region_id="board2", z0_mm=10, z1_mm=11.6, divisions=divisions,
            lower_patch="board2_air", upper_patch="top", upper_mapped=None, source_zone_name="board2_source",
            lower_mapped={"neighbour_region": "air", "neighbour_patch": "air_board2", "interface_id": "board2_air"})
        for cell in upper["mesh"]["cells"]:
            cell["material_id"] = "fr4"
        upper["mesh_evidence"]["sha256"] = _digest(upper["mesh"])
        neutral_meshes["board2"] = upper
    meshes = {name: write_polymesh(mesh, mesh_root / name / "polyMesh") for name, mesh in neutral_meshes.items()}
    def evidence(name, contract, value):
        return {"id": f"synthetic-fixture:{name}", "contract": contract, "sha256": _digest(value), "qualified": True}
    request = {
        "contract": REQUEST_CONTRACT,
        "mesh_evidence": evidence("assembly", "spike/openfoam-multiregion-mesh-set/v1", {name: mesh["poly_mesh_digest"] for name, mesh in meshes.items()}),
        "materials": [
            {"id": "fr4", "phase": "solid", "conductivity_w_mk": .35, "density_kg_m3": 1850, "specific_heat_j_kgk": 900},
            {"id": "airmat", "phase": "fluid", "conductivity_w_mk": .026, "density_kg_m3": 1.2, "specific_heat_j_kgk": 1006, "dynamic_viscosity_pa_s": 1.8e-5}],
        "regions": [
            {"id": "board", "kind": "solid", "role": "board", "material_id": "fr4", "mesh_evidence": meshes["board"]["poly_mesh_evidence"], "boundary_ownership": {"board_external": "external:adiabatic", "board_air": "interface:board_air"}},
            {"id": "air", "kind": "fluid", "role": "air", "material_id": "airmat", "mesh_evidence": meshes["air"]["poly_mesh_evidence"], "boundary_ownership": {"air_external": "external:adiabatic", "air_board": "interface:board_air", "fan_in": "fan:intake", "exhaust": "external:pressure_outlet"}}],
        "interfaces": [{"id": "board_air", "region_a": "board", "region_b": "air", "patch_a": "board_air", "patch_b": "air_board", "kind": "conjugate", "evidence": evidence("interface", "spike/qualified-contact/v1", {"face_a": board["boundary_patches"][1], "face_b": air["boundary_patches"][1]})}],
        "heat_sources": [{"id": "load", "solid_region_id": "board", "power_w": .1, "evidence": evidence("load", "spike/component-power-table/v1", {"power_w": .1}), "fv_option": {"cell_zone": "board_source", "volumetric_power_w_m3": 625000}}],
        "environment": {"enclosure": "open", "radiation": False, "vacuum": False, "gravity_m_s2": [0, 0, 0], "ambient_temperature_k": 298.15,
            "pressure_outlets": [{"fluid_region_id": "air", "boundary_patch": "exhaust", "static_pressure_pa": 101325, "backflow_temperature_k": 298.15}]},
        "fans": [{"id": "intake", "fluid_region_id": "air", "boundary_patch": "fan_in", "flow_rate_m3_s": 1e-5, "inlet_temperature_k": 298.15,
            "boundary_evidence": {"id": "synthetic-fixture:intake", "contract": "spike/qualified-boundary/v1", "qualified": True, "sha256": meshes["air"]["poly_mesh_digest"]}}],
        "heatsinks": [], "numerics": {"end_time_s": end_time_s, "delta_t_s": delta_t_s, "write_interval_steps": write_interval_steps, "validation_interval_steps": min(100, write_interval_steps), "outer_correctors": 5}}
    if board_count == 2:
        request["regions"][1]["boundary_ownership"]["air_board2"] = "interface:board2_air"
        request["regions"].append({"id": "board2", "kind": "solid", "role": "board", "material_id": "fr4", "mesh_evidence": meshes["board2"]["poly_mesh_evidence"], "boundary_ownership": {"board2_external": "external:adiabatic", "board2_air": "interface:board2_air"}})
        request["interfaces"].append({"id": "board2_air", "region_a": "board2", "region_b": "air", "patch_a": "board2_air", "patch_b": "air_board2", "kind": "conjugate", "evidence": evidence("upper-interface", "spike/qualified-contact/v1", {"upper": upper["mesh_evidence"], "air": air["mesh_evidence"]})})
        request["heat_sources"].append({"id": "load2", "solid_region_id": "board2", "power_w": .1, "evidence": evidence("load2", "spike/component-power-table/v1", {"power_w": .1}), "fv_option": {"cell_zone": "board2_source", "volumetric_power_w_m3": 625000}})
    prepared = prepare_runnable_multiregion_case(request, root / "case", mesh_root)
    return {"contract": "spike/openfoam-fan-heated-fixture/v1", "board_count": board_count, "request": request, "meshes": meshes, "prepared": prepared,
            "qualification": {"synthetic_geometry_only": True, "executed_cfd": False, "production_qualified": False}}
