from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.openfoam import prepare_case
from python.spike_core.openfoam_multiregion import (
    CASE_CONTRACT,
    REQUEST_CONTRACT,
    MultiRegionOpenFoamError,
    compile_multiregion_case,
    poly_mesh_digest,
    prepare_multiregion_case,
    prepare_runnable_multiregion_case,
)
from python.spike_core.thermal import ThermalScenario
from python.spike_core.service import handle


ROOT = Path(__file__).resolve().parents[2]


def evidence(identifier: str, contract: str = "spike/qualified-mesh/v1") -> dict:
    return {"id": identifier, "sha256": hashlib.sha256(identifier.encode("utf-8")).hexdigest(), "contract": contract, "qualified": True}


def polymesh_request() -> dict:
    """A tiny, digest-bound volume mesh for the worker materialization route."""
    mesh = {
        "contract": "spike/solver-mesh/v1", "units": "mm", "coordinate_system": "right_handed_xyz",
        "vertices": [[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10], [0, 0, -10]],
        "cells": [
            {"id": "upper", "kind": "tetrahedron", "vertices": [0, 1, 2, 3], "source_object_ids": ["solid:upper"], "material_id": "fr4"},
            {"id": "lower", "kind": "tetrahedron", "vertices": [0, 2, 1, 4], "source_object_ids": ["solid:lower"], "material_id": "fr4"},
        ],
        "object_map": {"solid:upper": {"kind": "solid"}, "solid:lower": {"kind": "solid"}},
        "counts": {"vertices": 5, "cells": 2},
    }
    digest = hashlib.sha256(json.dumps(mesh, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()
    return {
        "contract": "spike/openfoam-polymesh-request/v1", "region_id": "board", "mesh": mesh,
        "mesh_evidence": {"id": "mesh-board", "contract": "spike/solver-mesh/v1", "sha256": digest, "qualified": True},
        "boundary_patches": [
            {"name": "outer", "type": "wall", "faces": [[0, 1, 3], [1, 2, 3], [2, 0, 3], [0, 2, 4], [2, 1, 4]]},
            {"name": "coupled", "type": "mappedWall", "faces": [[1, 0, 4]], "neighbour_region": "air", "neighbour_patch": "board_coupled", "interface_id": "board_air"},
        ],
    }


def request() -> dict:
    return {
        "contract": REQUEST_CONTRACT,
        "mesh_evidence": evidence("assembly-mesh"),
        "materials": [
            {"id": "fr4", "phase": "solid", "conductivity_w_mk": 0.35, "density_kg_m3": 1850, "specific_heat_j_kgk": 900, "emissivity": 0.85},
            {"id": "aluminum", "phase": "solid", "conductivity_w_mk": 167, "density_kg_m3": 2700, "specific_heat_j_kgk": 896, "emissivity": 0.2},
            {"id": "epoxy", "phase": "solid", "conductivity_w_mk": 0.8, "density_kg_m3": 1200, "specific_heat_j_kgk": 1100},
            {"id": "air", "phase": "fluid", "conductivity_w_mk": 0.026, "density_kg_m3": 1.2, "specific_heat_j_kgk": 1006, "dynamic_viscosity_pa_s": 1.8e-5},
        ],
        "regions": [
            {"id": "board", "kind": "solid", "role": "board", "material_id": "fr4", "mesh_evidence": evidence("board-mesh")},
            {"id": "package", "kind": "solid", "role": "package", "material_id": "aluminum", "mesh_evidence": evidence("package-mesh")},
            {"id": "sink", "kind": "solid", "role": "heatsink", "material_id": "aluminum", "mesh_evidence": evidence("sink-mesh")},
            {"id": "potting", "kind": "solid", "role": "potting", "material_id": "epoxy", "mesh_evidence": evidence("potting-mesh")},
            {"id": "cabinet", "kind": "solid", "role": "enclosure", "material_id": "aluminum", "mesh_evidence": evidence("cabinet-mesh")},
            {"id": "air", "kind": "fluid", "role": "air", "material_id": "air", "mesh_evidence": evidence("air-mesh")},
        ],
        "interfaces": [
            {"id": "package_sink", "region_a": "package", "region_b": "sink", "kind": "thermal_contact", "thermal_resistance_k_per_w": 0.2, "contact_area_mm2": 100, "evidence": evidence("package-sink-contact", "spike/qualified-contact/v1")},
            {"id": "board_potting", "region_a": "board", "region_b": "potting", "kind": "conjugate", "evidence": evidence("board-potting-interface", "spike/qualified-contact/v1")},
            {"id": "potting_air", "region_a": "potting", "region_b": "air", "kind": "conjugate", "evidence": evidence("potting-air-interface", "spike/qualified-contact/v1")},
            {"id": "cabinet_air", "region_a": "cabinet", "region_b": "air", "kind": "conjugate", "evidence": evidence("cabinet-air-interface", "spike/qualified-contact/v1")},
        ],
        "heat_sources": [{"id": "U1", "solid_region_id": "package", "power_w": 4.0, "evidence": evidence("u1-power", "spike/component-power-table/v1")}],
        "environment": {
            "enclosure": "sealed", "radiation": True, "vacuum": False, "medium": "potting",
            "radiation_model": {
                "model": "viewFactor",
                "view_factor_evidence": evidence("view-factor-input", "spike/qualified-view-factor-input/v1"),
                "view_factor_controls": {"GaussQuadTol": 0.1, "distTol": 8.0, "alpha": 0.22, "intTol": 0.01, "useDirectSolver": False},
                "boundaries": [{
                    "region_id": "board", "patch": "outer", "material_id": "fr4", "emissivity": 0.85,
                    "external_radiative_flux_w_m2": 0.0,
                    "emissivity_evidence": evidence("fr4-emissivity", "spike/qualified-emissivity/v1"),
                    "boundary_evidence": evidence("board-radiation-boundary", "spike/qualified-radiation-boundary/v1"),
                }],
            },
        },
        "fans": [{"id": "fan1", "fluid_region_id": "air", "flow_rate_m3_s": 0.012, "boundary_evidence": evidence("fan-boundary", "spike/qualified-boundary/v1")}],
        "heatsinks": [{"id": "hs1", "region_id": "sink", "mount_interface_id": "package_sink"}],
    }


def _write_poly_mesh(root: Path, patches: list[str], cell_zones: list[str] | None = None, patch_groups: dict[str, list[str]] | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in ("points", "faces", "owner", "neighbour"):
        (root / name).write_text(f"FoamFile {{ object {name}; }}\n", encoding="utf-8")
    groups = patch_groups or {}
    blocks = "\n".join(
        f"{patch}\n{{\n    type wall;\n"
        + (f"    inGroups {len(groups[patch])}({' '.join(groups[patch])});\n" if groups.get(patch) else "")
        + f"    nFaces 1;\n    startFace {index};\n}}"
        for index, patch in enumerate(patches)
    )
    (root / "boundary").write_text(f"FoamFile {{ object boundary; }}\n{len(patches)}\n(\n{blocks}\n)\n", encoding="utf-8")
    if cell_zones:
        zone_blocks = "\n".join(f"{zone}\n{{\n    type cellZone;\n    cellLabels List<label>\n    1\n    (\n0\n    );\n}}" for zone in cell_zones)
        (root / "cellZones").write_text(f"FoamFile {{ object cellZones; }}\n{len(cell_zones)}\n(\n{zone_blocks}\n)\n", encoding="utf-8")


def materialize_runnable_request(mesh_root: Path, *, radiation: bool = False, vacuum: bool = False) -> dict:
    value = copy.deepcopy(request())
    value["environment"]["radiation"] = radiation
    value["environment"]["vacuum"] = vacuum
    if vacuum:
        removed = {region["id"] for region in value["regions"] if region["kind"] == "fluid"}
        value["regions"] = [region for region in value["regions"] if region["id"] not in removed]
        value["interfaces"] = [interface for interface in value["interfaces"] if interface["region_a"] not in removed and interface["region_b"] not in removed]
        value["fans"] = []
        value["environment"]["medium"] = "vacuum"
        value["environment"]["radiation_model"] = {
            "model": "externalAmbient",
            "background_temperature_k": 3.0,
            "boundaries": value["environment"]["radiation_model"]["boundaries"],
        }
    value["heat_sources"][0]["fv_option"] = {"cell_zone": "u1_zone", "volumetric_power_w_m3": 1.0e6}
    value["interfaces"][0]["openfoam_baffle"] = {"thickness_m": 2.0e-5, "conductivity_w_mk": 1.0}
    ownership = {region["id"]: {"outer": "external:outer"} for region in value["regions"]}
    for interface in value["interfaces"]:
        left_patch, right_patch = f"{interface['id']}_{interface['region_a']}", f"{interface['id']}_{interface['region_b']}"
        ownership[interface["region_a"]][left_patch] = f"interface:{interface['id']}"
        ownership[interface["region_b"]][right_patch] = f"interface:{interface['id']}"
    if value["fans"]:
        value["environment"]["enclosure"] = "vented_cabinet"
        value["environment"]["pressure_outlets"] = [{"fluid_region_id": "air", "boundary_patch": "fanOut", "static_pressure_pa": 101325, "backflow_temperature_k": 298.15}]
        ownership["air"]["fanOut"] = "external:pressure_outlet"
        value["fans"][0]["boundary_patch"] = "fanIn"
        ownership["air"]["fanIn"] = "fan:fan1"
    for region in value["regions"]:
        region["boundary_ownership"] = ownership[region["id"]]
        poly_mesh = mesh_root / region["id"] / "polyMesh"
        radiation_groups = {"outer": ["viewFactorWall"]} if radiation and not vacuum and region["id"] == "board" else None
        _write_poly_mesh(poly_mesh, sorted(region["boundary_ownership"]), ["u1_zone"] if region["id"] == "package" else None, radiation_groups)
        region["mesh_evidence"]["sha256"] = poly_mesh_digest(poly_mesh)
    for fan in value["fans"]:
        fan["boundary_evidence"]["sha256"] = next(region["mesh_evidence"]["sha256"] for region in value["regions"] if region["id"] == fan["fluid_region_id"])
    for boundary in value["environment"]["radiation_model"]["boundaries"]:
        boundary["boundary_evidence"]["sha256"] = next(
            region["mesh_evidence"]["sha256"] for region in value["regions"] if region["id"] == boundary["region_id"]
        )
    return value


class OpenFoamMultiRegionTests(unittest.TestCase):
    def test_compiles_strict_solid_fluid_material_contact_and_environment_metadata(self):
        result = compile_multiregion_case(request())
        self.assertEqual(result["contract"], CASE_CONTRACT)
        self.assertEqual(result["status"], "prepared_not_runnable")
        self.assertFalse(result["qualification"]["solver_ready"])
        self.assertFalse(result["qualification"]["production_qualified"])
        self.assertEqual(result["solver"]["command"], "chtMultiRegionFoam")
        self.assertTrue(result["requested_physics"]["radiation"])
        self.assertTrue(result["requested_physics"]["potting"])
        self.assertEqual(result["interfaces"][0]["id"], "board_potting")
        self.assertEqual(result["heat_sources"][0]["id"], "U1")

    def test_prepare_is_deterministic_and_manifest_binds_evidence_and_generated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first", Path(directory) / "second"
            first_result = prepare_multiregion_case(request(), first)
            second_result = prepare_multiregion_case(request(), second)
            self.assertEqual(first_result["status"], "prepared_not_runnable")
            self.assertEqual(first_result["manifest"]["request_digest"], second_result["manifest"]["request_digest"])
            self.assertEqual(first_result["manifest"]["files"], second_result["manifest"]["files"])
            self.assertTrue((first / "constant" / "regionProperties").is_file())
            self.assertTrue((first / "constant" / "spike-interfaces.json").is_file())
            self.assertIn("NOT-RUNNABLE", (first / "README.SPIKE-NOT-RUNNABLE.txt").read_text(encoding="utf-8"))
            persisted = json.loads((first / "spike_multiregion_case.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["assembly_mesh_evidence"]["id"], "assembly-mesh")
            self.assertFalse(persisted["qualification"]["field_result_produced"])
            request_schema = json.loads((ROOT / "schemas" / "openfoam-multiregion-request-v1.schema.json").read_text(encoding="utf-8"))
            case_schema = json.loads((ROOT / "schemas" / "openfoam-multiregion-case-v1.schema.json").read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(request_schema)
            Draft202012Validator(request_schema).validate(request())
            Draft202012Validator(case_schema).validate(persisted)
            catalog = json.loads((ROOT / "schemas" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(catalog["schemas"][REQUEST_CONTRACT], "openfoam-multiregion-request-v1.schema.json")
            self.assertEqual(catalog["schemas"][CASE_CONTRACT], "openfoam-multiregion-case-v1.schema.json")

    def test_worker_exposes_preparation_without_claiming_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            response = handle({
                "id": "prepare-multiregion", "method": "prepare_multiregion_thermal_case",
                "params": {"request": request(), "output_dir": str(Path(directory) / "case")},
            })
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["status"], "prepared_not_runnable")
        self.assertFalse(response["result"]["manifest"]["qualification"]["production_qualified"])

    def test_worker_materializes_polymesh_and_prepares_verified_runnable_case(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            materialized = handle({
                "id": "polymesh", "method": "materialize_openfoam_polymesh",
                "params": {"request": polymesh_request(), "output_dir": str(base / "polyMesh")},
            })
            self.assertTrue(materialized["ok"], materialized)
            self.assertEqual(materialized["result"]["status"], "materialized")
            mesh_root = base / "meshes"
            value = materialize_runnable_request(mesh_root)
            prepared = handle({
                "id": "runnable", "method": "prepare_runnable_multiregion_thermal_case",
                "params": {"request": value, "output_dir": str(base / "case"), "materialized_mesh_root": str(mesh_root)},
            })
            self.assertTrue(prepared["ok"], prepared)
            self.assertEqual(prepared["result"]["status"], "prepared_runnable_case")
            self.assertFalse(prepared["result"]["runnable_manifest"]["qualification"]["production_qualified"])

    def test_worker_requires_explicit_opt_in_before_multiregion_execution(self):
        response = handle({
            "id": "run-multiregion", "method": "run_multiregion_thermal_case",
            "params": {"case_dir": "does-not-matter", "allow_experimental": False},
        })
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["status"], "blocked")
        self.assertEqual(response["result"]["fields"], {})
        self.assertFalse(response["result"]["qualification"]["production_qualified"])

    def test_worker_exposes_candidate_validation_without_promoting_signoff(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "case"
            value = materialize_runnable_request(Path(directory) / "meshes")
            prepared = prepare_runnable_multiregion_case(value, case, Path(directory) / "meshes")
            record = {"contract": "spike/openfoam-multiregion-validation-record/v1", "manifest_digest": prepared["runnable_manifest"]["manifest_digest"], "conservation": {"input_power_w": 1, "boundary_power_w": 1, "relative_tolerance": .01}, "mesh_convergence": {"relative_tolerance": .01, "levels": [{"cells": 1, "maximum_temperature_k": 1}, {"cells": 2, "maximum_temperature_k": 1}, {"cells": 4, "maximum_temperature_k": 1}]}, "time_convergence": {"relative_tolerance": .01, "levels": [{"delta_t_s": 1, "maximum_temperature_k": 1}, {"delta_t_s": .5, "maximum_temperature_k": 1}, {"delta_t_s": .25, "maximum_temperature_k": 1}]}}
            response = handle({"id": "validate", "method": "validate_openfoam_multiregion_case", "params": {"case_dir": str(case), "result_record": record}})
            self.assertTrue(response["ok"], response)
            self.assertTrue(response["result"]["candidate_passed"])
            self.assertFalse(response["result"]["qualification"]["production_qualified"])

    def test_missing_qualified_region_mesh_or_contact_evidence_fails_closed(self):
        missing_mesh = request()
        missing_mesh["regions"][0]["mesh_evidence"]["qualified"] = False
        with self.assertRaisesRegex(MultiRegionOpenFoamError, "qualified=true"):
            compile_multiregion_case(missing_mesh)
        missing_contact = request()
        del missing_contact["interfaces"][0]["evidence"]
        with self.assertRaisesRegex(MultiRegionOpenFoamError, "interface package_sink evidence"):
            compile_multiregion_case(missing_contact)

    def test_vacuum_rejects_air_and_fan_metadata(self):
        value = request()
        value["environment"]["vacuum"] = True
        value["environment"]["medium"] = "vacuum"
        value["regions"][-1]["role"] = "vacuum"
        with self.assertRaisesRegex(MultiRegionOpenFoamError, "pseudo-fluid"):
            compile_multiregion_case(value)

    def test_cancellation_has_no_prepared_case(self):
        with self.assertRaisesRegex(MultiRegionOpenFoamError, "cancelled"):
            compile_multiregion_case(request(), cancel_check=lambda: True)

    def test_existing_single_region_adapter_remains_available_for_its_original_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            result = prepare_case(ThermalScenario(heat_sources=[{"id": "U1", "power_w": 1.0, "position": [10, 10, 3]}]), Path(directory) / "air")
        self.assertIn(result["status"], {"prepared_experimental_case", "prepared_runtime_unavailable"})

    def test_runnable_v2606_case_requires_verified_materialized_polymesh_and_exact_patch_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            mesh_root = base / "meshes"
            value = materialize_runnable_request(mesh_root)
            result = prepare_runnable_multiregion_case(value, base / "case", mesh_root)
            self.assertEqual(result["status"], "prepared_runnable_case")
            self.assertFalse(result["manifest"]["qualification"]["production_qualified"])
            self.assertIn("application chtMultiRegionFoam", (base / "case" / "system" / "controlDict").read_text(encoding="utf-8"))
            self.assertTrue((base / "case" / "constant" / "board" / "polyMesh" / "boundary").is_file())
            self.assertIn("scalarSemiImplicitSource", (base / "case" / "system" / "package" / "fvOptions").read_text(encoding="utf-8"))
            self.assertIn("volumeMode specific", (base / "case" / "system" / "package" / "fvOptions").read_text(encoding="utf-8"))
            self.assertIn("flowRateInletVelocity", (base / "case" / "0" / "air" / "U").read_text(encoding="utf-8"))
            self.assertIn("thicknessLayers (2e-05)", (base / "case" / "0" / "package" / "T").read_text(encoding="utf-8"))
            self.assertIn("radiationModel none", (base / "case" / "constant" / "air" / "radiationProperties").read_text(encoding="utf-8"))

    def test_runnable_v2606_radiation_case_emits_view_factor_and_evidence_bound_surface_dictionaries(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            value = materialize_runnable_request(base / "meshes", radiation=True)
            result = prepare_runnable_multiregion_case(value, base / "case", base / "meshes")
            self.assertEqual(result["status"], "prepared_runnable_case")
            self.assertFalse(result["manifest"]["qualification"]["production_qualified"])
            self.assertIn("radiationModel viewFactor", (base / "case" / "constant" / "board" / "radiationProperties").read_text(encoding="utf-8"))
            self.assertIn("opaqueDiffusive", (base / "case" / "constant" / "board" / "boundaryRadiationProperties").read_text(encoding="utf-8"))
            self.assertIn("viewFactorEvidence", (base / "case" / "constant" / "board" / "viewFactorsDict").read_text(encoding="utf-8"))
            self.assertIn("patchAgglomeration", (base / "case" / "constant" / "board" / "viewFactorsDict").read_text(encoding="utf-8"))
            self.assertIn("greyDiffusiveRadiationViewFactor", (base / "case" / "0" / "board" / "T").read_text(encoding="utf-8"))

    def test_radiation_generation_fails_closed_without_exact_qualified_boundary_or_emissivity_evidence(self):
        value = request()
        del value["environment"]["radiation_model"]["boundaries"][0]["emissivity_evidence"]
        with self.assertRaisesRegex(MultiRegionOpenFoamError, "emissivity evidence"):
            compile_multiregion_case(value)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            value = materialize_runnable_request(base / "meshes", radiation=True)
            value["environment"]["radiation_model"]["boundaries"][0]["boundary_evidence"]["sha256"] = "0" * 64
            result = prepare_runnable_multiregion_case(value, base / "case", base / "meshes")
            self.assertEqual(result["status"], "blocked")
            self.assertIn("exact materialized polyMesh digest", result["message"])

    def test_vacuum_radiation_case_requires_solid_surface_records_and_generates_radiation_dictionaries(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            value = materialize_runnable_request(base / "meshes", radiation=True, vacuum=True)
            result = prepare_runnable_multiregion_case(value, base / "case", base / "meshes")
            self.assertEqual(result["status"], "prepared_runnable_case")
            self.assertTrue(result["manifest"]["environment"]["vacuum"])
            self.assertFalse(any(item["kind"] == "fluid" for item in result["manifest"]["regions"]))
            self.assertFalse(result["manifest"]["requested_physics"]["fluid_flow"])
            self.assertIn("fluid ()", (base / "case" / "constant" / "regionProperties").read_text(encoding="utf-8"))
            self.assertEqual(result["runnable_manifest"]["view_factor_regions"], [])
            self.assertIn("radiationModel none", (base / "case" / "constant" / "board" / "radiationProperties").read_text(encoding="utf-8"))
            boundary = (base / "case" / "0" / "board" / "T").read_text(encoding="utf-8")
            self.assertIn("externalWallHeatFluxTemperature", boundary)
            self.assertIn("Ta constant 3.0", boundary)
            self.assertIn("h constant 0", boundary)

    def test_runnable_generation_fails_closed_when_mesh_absent_or_patch_ownership_is_wrong(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            missing = prepare_runnable_multiregion_case(request(), base / "missing-case", base / "none")
            self.assertEqual(missing["status"], "blocked")
            value = materialize_runnable_request(base / "meshes")
            value["regions"][0]["boundary_ownership"]["outer"] = "interface:not_declared"
            invalid = prepare_runnable_multiregion_case(value, base / "bad-case", base / "meshes")
            self.assertEqual(invalid["status"], "blocked")
            self.assertIn("interface boundary owner", invalid["message"])


if __name__ == "__main__":
    unittest.main()
