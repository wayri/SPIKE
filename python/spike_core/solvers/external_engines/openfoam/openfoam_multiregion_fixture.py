"""Deterministic two-region slab fixture for OpenFOAM adapter qualification.

The fixture is intentionally small and synthetic.  It validates translation,
mesh topology, interface coupling and zero-load equilibrium; it is not PCB or
measured correlation evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from .openfoam_multiregion import REQUEST_CONTRACT, prepare_runnable_multiregion_case
from .openfoam_polymesh import REQUEST_CONTRACT as POLYMESH_REQUEST_CONTRACT, write_polymesh


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()


def _structured_hex_mesh(*, region_id: str, z0_mm: float, z1_mm: float, divisions: int, lower_patch: str, upper_patch: str, lower_mapped: Dict[str, str] | None, upper_mapped: Dict[str, str] | None, external_groups: list[str] | None = None, source_zone_name: str | None = None) -> Dict[str, Any]:
    if not 1 <= divisions <= 32:
        raise ValueError("Fixture divisions must be between 1 and 32.")
    nx = ny = nz = divisions
    vertices = []
    index = {}
    for k in range(nz + 1):
        z = z0_mm + (z1_mm - z0_mm) * k / nz
        for j in range(ny + 1):
            for i in range(nx + 1):
                index[(i, j, k)] = len(vertices)
                vertices.append([10.0 * i / nx, 10.0 * j / ny, z])
    cells = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                corners = [index[(i, j, k)], index[(i + 1, j, k)], index[(i + 1, j + 1, k)], index[(i, j + 1, k)], index[(i, j, k + 1)], index[(i + 1, j, k + 1)], index[(i + 1, j + 1, k + 1)], index[(i, j + 1, k + 1)]]
                cells.append({"id": f"{region_id}_{i}_{j}_{k}", "kind": "hexahedron", "vertices": corners, "source_object_ids": [f"region:{region_id}"], "material_id": "fr4" if region_id == "board" else "air"})
    lower_faces = [[index[(i, j, 0)], index[(i, j + 1, 0)], index[(i + 1, j + 1, 0)], index[(i + 1, j, 0)]] for j in range(ny) for i in range(nx)]
    upper_faces = [[index[(i, j, nz)], index[(i + 1, j, nz)], index[(i + 1, j + 1, nz)], index[(i, j + 1, nz)]] for j in range(ny) for i in range(nx)]
    side_faces = []
    for k in range(nz):
        for j in range(ny):
            side_faces.extend([
                [index[(0, j, k)], index[(0, j, k + 1)], index[(0, j + 1, k + 1)], index[(0, j + 1, k)]],
                [index[(nx, j, k)], index[(nx, j + 1, k)], index[(nx, j + 1, k + 1)], index[(nx, j, k + 1)]],
            ])
        for i in range(nx):
            side_faces.extend([
                [index[(i, 0, k)], index[(i + 1, 0, k)], index[(i + 1, 0, k + 1)], index[(i, 0, k + 1)]],
                [index[(i, ny, k)], index[(i, ny, k + 1)], index[(i + 1, ny, k + 1)], index[(i + 1, ny, k)]],
            ])
    mesh = {"contract": "spike/solver-mesh/v1", "units": "mm", "coordinate_system": "right_handed_xyz", "vertices": vertices, "cells": cells, "object_map": {f"region:{region_id}": {"kind": "thermal_region"}}, "counts": {"vertices": len(vertices), "cells": len(cells)}}
    evidence = {"id": f"neutral:{region_id}", "contract": "spike/solver-mesh/v1", "sha256": _digest(mesh), "qualified": True}
    external_patch: Dict[str, Any] = {"name": f"{region_id}_external", "type": "wall", "faces": side_faces}
    if external_groups:
        external_patch["groups"] = list(external_groups)
    patches = [external_patch]
    for name, faces, mapped in ((lower_patch, lower_faces, lower_mapped), (upper_patch, upper_faces, upper_mapped)):
        patch: Dict[str, Any] = {"name": name, "type": "mappedWall" if mapped else "wall", "faces": faces}
        if mapped:
            patch.update(mapped)
        else:
            patches[0]["faces"].extend(faces)
            continue
        patches.append(patch)
    result = {"contract": POLYMESH_REQUEST_CONTRACT, "region_id": region_id, "mesh": mesh, "mesh_evidence": evidence, "boundary_patches": patches}
    zone_name = source_zone_name or ("board_source" if region_id == "board" else None)
    if zone_name is not None:
        result["cell_zones"] = [{"name": zone_name, "cell_ids": [cell["id"] for cell in cells]}]
    return result


def build_two_region_slab_fixture(output_root: str | Path, *, divisions: int = 1, end_time_s: float = 100.0, delta_t_s: float = 1.0) -> Dict[str, Any]:
    root = Path(output_root).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Fixture output root must be empty.")
    root.mkdir(parents=True, exist_ok=True)
    mesh_root = root / "meshes"
    board_mesh = _structured_hex_mesh(region_id="board", z0_mm=0.0, z1_mm=1.6, divisions=divisions, lower_patch="board_bottom", upper_patch="board_air", lower_mapped=None, upper_mapped={"neighbour_region": "air", "neighbour_patch": "air_board", "interface_id": "board_air"})
    air_mesh = _structured_hex_mesh(region_id="air", z0_mm=1.6, z1_mm=10.0, divisions=divisions, lower_patch="air_board", upper_patch="air_top", lower_mapped={"neighbour_region": "board", "neighbour_patch": "board_air", "interface_id": "board_air"}, upper_mapped=None)
    board_result = write_polymesh(board_mesh, mesh_root / "board" / "polyMesh")
    air_result = write_polymesh(air_mesh, mesh_root / "air" / "polyMesh")
    interface_digest = hashlib.sha256(f"board-air-{divisions}".encode("utf-8")).hexdigest()
    assembly_digest = _digest({"board": board_result["poly_mesh_digest"], "air": air_result["poly_mesh_digest"]})
    request = {
        "contract": REQUEST_CONTRACT, "job_id": f"slab-{divisions}",
        "mesh_evidence": {"id": "slab-assembly", "sha256": assembly_digest, "contract": "spike/openfoam-multiregion-mesh-set/v1", "qualified": True},
        "materials": [
            {"id": "fr4", "phase": "solid", "conductivity_w_mk": 0.35, "density_kg_m3": 1850.0, "specific_heat_j_kgk": 900.0},
            {"id": "airmat", "phase": "fluid", "conductivity_w_mk": 0.026, "density_kg_m3": 1.2, "specific_heat_j_kgk": 1006.0, "dynamic_viscosity_pa_s": 1.8e-5},
        ],
        "regions": [
            {"id": "board", "kind": "solid", "role": "board", "material_id": "fr4", "mesh_evidence": board_result["poly_mesh_evidence"], "boundary_ownership": {"board_external": "external:adiabatic", "board_air": "interface:board_air"}},
            {"id": "air", "kind": "fluid", "role": "air", "material_id": "airmat", "mesh_evidence": air_result["poly_mesh_evidence"], "boundary_ownership": {"air_external": "external:fixed_temperature", "air_board": "interface:board_air"}},
        ],
        "interfaces": [{"id": "board_air", "region_a": "board", "region_b": "air", "patch_a": "board_air", "patch_b": "air_board", "kind": "conjugate", "evidence": {"id": "interface:board_air", "sha256": interface_digest, "contract": "spike/qualified-contact/v1", "qualified": True}}],
        "heat_sources": [{"id": "board_load", "solid_region_id": "board", "power_w": 0.1, "evidence": {"id": "fixture:board-load", "sha256": hashlib.sha256(b"fixture-board-load-0.1W").hexdigest(), "contract": "spike/component-power-table/v1", "qualified": True}, "fv_option": {"cell_zone": "board_source", "volumetric_power_w_m3": 625000.0}}], "environment": {"enclosure": "open", "radiation": False, "vacuum": False, "medium": "air", "ambient_temperature_k": 298.15}, "fans": [], "heatsinks": [],
        "numerics": {"end_time_s": end_time_s, "delta_t_s": delta_t_s, "write_interval_steps": max(1, int(round(end_time_s / delta_t_s))), "validation_interval_steps": 1},
    }
    prepared = prepare_runnable_multiregion_case(request, root / "case", mesh_root)
    return {"contract": "spike/openfoam-multiregion-slab-fixture/v1", "divisions": divisions, "request": request, "meshes": {"board": board_result, "air": air_result}, "prepared": prepared}


def build_solid_vacuum_fixture(output_root: str | Path, *, divisions: int = 2, end_time_s: float = 2.0, delta_t_s: float = 0.25, background_temperature_k: float = 3.0) -> Dict[str, Any]:
    """Build a bounded solid-only exterior-radiation runtime fixture.

    This verifies OpenFOAM's no-fluid region topology and the explicit
    ``externalWallHeatFluxTemperature`` vacuum boundary. It is deliberately a
    synthetic numerical fixture, not spacecraft or PCB correlation evidence.
    """
    root = Path(output_root).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Fixture output root must be empty.")
    root.mkdir(parents=True, exist_ok=True)
    mesh_root = root / "meshes"
    board_mesh = _structured_hex_mesh(
        region_id="board", z0_mm=0.0, z1_mm=1.6, divisions=divisions,
        lower_patch="board_bottom", upper_patch="board_top",
        lower_mapped=None, upper_mapped=None,
    )
    board_result = write_polymesh(board_mesh, mesh_root / "board" / "polyMesh")
    assembly_digest = _digest({"board": board_result["poly_mesh_digest"]})
    request = {
        "contract": REQUEST_CONTRACT,
        "job_id": f"vacuum-slab-{divisions}",
        "mesh_evidence": {"id": "vacuum-slab-assembly", "sha256": assembly_digest, "contract": "spike/openfoam-multiregion-mesh-set/v1", "qualified": True},
        "materials": [
            {"id": "fr4", "phase": "solid", "conductivity_w_mk": 0.35, "density_kg_m3": 1850.0, "specific_heat_j_kgk": 900.0, "emissivity": 0.85},
        ],
        "regions": [
            {"id": "board", "kind": "solid", "role": "board", "material_id": "fr4", "mesh_evidence": board_result["poly_mesh_evidence"], "boundary_ownership": {"board_external": "external:radiation"}},
        ],
        "interfaces": [],
        "heat_sources": [
            {"id": "board_load", "solid_region_id": "board", "power_w": 0.1, "evidence": {"id": "fixture:vacuum-board-load", "sha256": hashlib.sha256(b"fixture-vacuum-board-load-0.1W").hexdigest(), "contract": "spike/component-power-table/v1", "qualified": True}, "fv_option": {"cell_zone": "board_source", "volumetric_power_w_m3": 625000.0}},
        ],
        "environment": {
            "enclosure": "open", "radiation": True, "vacuum": True, "medium": "vacuum",
            "ambient_temperature_k": 298.15,
            "radiation_model": {
                "model": "externalAmbient", "background_temperature_k": background_temperature_k,
                "boundaries": [{
                    "region_id": "board", "patch": "board_external", "material_id": "fr4", "emissivity": 0.85,
                    "external_radiative_flux_w_m2": 0.0,
                    "emissivity_evidence": {"id": "fixture:fr4-emissivity", "sha256": hashlib.sha256(b"fixture-fr4-emissivity-0.85").hexdigest(), "contract": "spike/qualified-emissivity/v1", "qualified": True},
                    "boundary_evidence": {"id": "fixture:vacuum-board-boundary", "sha256": board_result["poly_mesh_digest"], "contract": "spike/qualified-radiation-boundary/v1", "qualified": True},
                }],
            },
        },
        "fans": [], "heatsinks": [],
        "numerics": {"end_time_s": end_time_s, "delta_t_s": delta_t_s, "write_interval_steps": max(1, int(round(end_time_s / delta_t_s))), "validation_interval_steps": 1},
    }
    prepared = prepare_runnable_multiregion_case(request, root / "case", mesh_root)
    return {"contract": "spike/openfoam-solid-vacuum-fixture/v1", "divisions": divisions, "request": request, "meshes": {"board": board_result}, "prepared": prepared}


def build_board_package_air_contact_fixture(output_root: str | Path, *, divisions: int = 1, end_time_s: float = 10.0, delta_t_s: float = 0.5) -> Dict[str, Any]:
    """Build a bounded PCB/package/contact/air CHT translation fixture.

    The 10 mm x 10 mm stack has a FR-4 board, a silicon package and an air
    region.  The board/package interface has an explicit 0.2 K/W TIM contact
    over 100 mm2; the package/air interface is conjugate.  This is deliberately
    synthetic and is not a calibrated package, PCB or measured fixture.
    """
    root = Path(output_root).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Fixture output root must be empty.")
    root.mkdir(parents=True, exist_ok=True)
    mesh_root = root / "meshes"
    board_mesh = _structured_hex_mesh(
        region_id="board", z0_mm=0.0, z1_mm=1.6, divisions=divisions,
        lower_patch="board_bottom", upper_patch="board_package", lower_mapped=None,
        upper_mapped={"neighbour_region": "package", "neighbour_patch": "package_board", "interface_id": "board_package"},
    )
    package_mesh = _structured_hex_mesh(
        region_id="package", z0_mm=1.6, z1_mm=2.6, divisions=divisions,
        lower_patch="package_board", upper_patch="package_air",
        lower_mapped={"neighbour_region": "board", "neighbour_patch": "board_package", "interface_id": "board_package"},
        upper_mapped={"neighbour_region": "air", "neighbour_patch": "air_package", "interface_id": "package_air"},
        source_zone_name="package_source",
    )
    air_mesh = _structured_hex_mesh(
        region_id="air", z0_mm=2.6, z1_mm=12.6, divisions=divisions,
        lower_patch="air_package", upper_patch="air_top",
        lower_mapped={"neighbour_region": "package", "neighbour_patch": "package_air", "interface_id": "package_air"},
        upper_mapped=None,
    )
    board_result = write_polymesh(board_mesh, mesh_root / "board" / "polyMesh")
    package_result = write_polymesh(package_mesh, mesh_root / "package" / "polyMesh")
    air_result = write_polymesh(air_mesh, mesh_root / "air" / "polyMesh")
    assembly_digest = _digest({"board": board_result["poly_mesh_digest"], "package": package_result["poly_mesh_digest"], "air": air_result["poly_mesh_digest"]})
    contact_digest = hashlib.sha256(f"board-package-contact-{divisions}".encode("utf-8")).hexdigest()
    air_digest = hashlib.sha256(f"package-air-interface-{divisions}".encode("utf-8")).hexdigest()
    request = {
        "contract": REQUEST_CONTRACT, "job_id": f"board-package-air-{divisions}",
        "mesh_evidence": {"id": "board-package-air-assembly", "sha256": assembly_digest, "contract": "spike/openfoam-multiregion-mesh-set/v1", "qualified": True},
        "materials": [
            {"id": "fr4", "phase": "solid", "conductivity_w_mk": 0.35, "density_kg_m3": 1850.0, "specific_heat_j_kgk": 900.0},
            {"id": "silicon", "phase": "solid", "conductivity_w_mk": 130.0, "density_kg_m3": 2330.0, "specific_heat_j_kgk": 700.0},
            {"id": "airmat", "phase": "fluid", "conductivity_w_mk": 0.026, "density_kg_m3": 1.2, "specific_heat_j_kgk": 1006.0, "dynamic_viscosity_pa_s": 1.8e-5},
        ],
        "regions": [
            {"id": "board", "kind": "solid", "role": "board", "material_id": "fr4", "mesh_evidence": board_result["poly_mesh_evidence"], "boundary_ownership": {"board_external": "external:adiabatic", "board_package": "interface:board_package"}},
            {"id": "package", "kind": "solid", "role": "package", "material_id": "silicon", "mesh_evidence": package_result["poly_mesh_evidence"], "boundary_ownership": {"package_external": "external:adiabatic", "package_board": "interface:board_package", "package_air": "interface:package_air"}},
            {"id": "air", "kind": "fluid", "role": "air", "material_id": "airmat", "mesh_evidence": air_result["poly_mesh_evidence"], "boundary_ownership": {"air_external": "external:fixed_temperature", "air_package": "interface:package_air"}},
        ],
        "interfaces": [
            {"id": "board_package", "region_a": "board", "region_b": "package", "patch_a": "board_package", "patch_b": "package_board", "kind": "thermal_contact", "thermal_resistance_k_per_w": 0.2, "contact_area_mm2": 100.0, "openfoam_baffle": {"thickness_m": 2.0e-5, "conductivity_w_mk": 1.0}, "evidence": {"id": "fixture:board-package-contact", "sha256": contact_digest, "contract": "spike/qualified-contact/v1", "qualified": True}},
            {"id": "package_air", "region_a": "package", "region_b": "air", "patch_a": "package_air", "patch_b": "air_package", "kind": "conjugate", "evidence": {"id": "fixture:package-air-interface", "sha256": air_digest, "contract": "spike/qualified-contact/v1", "qualified": True}},
        ],
        "heat_sources": [{"id": "u1_die", "solid_region_id": "package", "power_w": 0.1, "evidence": {"id": "fixture:u1-die-power", "sha256": hashlib.sha256(b"fixture-u1-die-power-0.1W").hexdigest(), "contract": "spike/component-power-table/v1", "qualified": True}, "fv_option": {"cell_zone": "package_source", "volumetric_power_w_m3": 1.0e6}}],
        "environment": {"enclosure": "open", "radiation": False, "vacuum": False, "medium": "air", "ambient_temperature_k": 298.15},
        "fans": [], "heatsinks": [],
        "numerics": {"end_time_s": end_time_s, "delta_t_s": delta_t_s, "write_interval_steps": max(1, int(round(end_time_s / delta_t_s))), "validation_interval_steps": 1, "outer_correctors": 10},
    }
    prepared = prepare_runnable_multiregion_case(request, root / "case", mesh_root)
    return {"contract": "spike/openfoam-board-package-air-contact-fixture/v1", "divisions": divisions, "request": request, "meshes": {"board": board_result, "package": package_result, "air": air_result}, "prepared": prepared}


__all__ = ["build_board_package_air_contact_fixture", "build_solid_vacuum_fixture", "build_two_region_slab_fixture"]
