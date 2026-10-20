# SPDX-License-Identifier: Apache-2.0
"""Independent integration and contract checks for refined obstacle CHT v2."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
import numpy as np

from python.spike_core.enclosure_cht import solve_enclosure_cht
from python.spike_core.enclosure_cht_v2 import REQUEST, solve_enclosure_cht_v2
from python.spike_core.service_cfd import handle_cfd_request


ROOT = Path(__file__).resolve().parents[2]
FACES = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")


def material(name="fluid", phase="fluid", conductivity=1.0, capacity=1.0):
    value = {"id": name, "phase": phase, "density_kg_m3": 1.0,
             "specific_heat_j_kgk": capacity, "conductivity_w_mk": conductivity}
    if phase == "fluid":
        value["dynamic_viscosity_pa_s"] = 1.0
    return value


def fixture(shape=(4, 4, 4), *, obstacle=True, refined=False):
    ids = np.full(shape, "fluid", dtype="U8")
    materials = [material()]
    if obstacle:
        ids[1:3, 1:3, 1:3] = "solid"
        materials.append(material("solid", "solid", 3.0, 2.0))
    force = np.zeros((*shape, 3))
    force[..., 0] = np.arange(shape[1])[None, :, None] * 0.01
    force[ids != "fluid"] = 0.0
    heat = np.zeros(shape)
    heat[ids != "fluid"] = 100.0
    request = {
        "contract": REQUEST,
        "grid": {"shape": list(shape), "spacing_m": [0.1] * 3,
                 "origin_m": [0.0] * 3, "local_refinement": []},
        "materials": materials,
        "material_ids": ids.tolist(),
        "flow": {"model": "rectilinear_laminar", "body_force_n_m3": force.tolist(),
                 "nonlinear_controls": {"max_iterations": 60, "relaxation": 1.0,
                                        "relative_tolerance": 1e-10}},
        "heat_sources_w_m3": heat.tolist(),
        "boundaries": {face: {"type": "temperature", "temperature_k": 300.0}
                       for face in FACES},
        "study": {"type": "steady"},
    }
    if refined:
        request["grid"]["local_refinement"] = [{
            "bounds_m": [[0.08, 0.32], [0.08, 0.32], [0.08, 0.32]],
            "split_factor": 2,
        }]
    return request


def object_paths(value, path=()):
    if isinstance(value, dict):
        yield path
        for key, child in value.items():
            yield from object_paths(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from object_paths(child, (*path, index))


def at(value, path):
    for key in path:
        value = value[key]
    return value


class EnclosureChtV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validators = {}
        for kind in ("request", "result"):
            schema = json.loads((ROOT / "schemas" / f"enclosure-cht-{kind}-v2.schema.json").read_text())
            Draft202012Validator.check_schema(schema)
            cls.validators[kind] = Draft202012Validator(schema)

    def accepted(self, request):
        result = solve_enclosure_cht_v2(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertFalse(result["production_qualified"])
        self.validators["request"].validate(json.loads(json.dumps(request, allow_nan=False)))
        self.validators["result"].validate(json.loads(json.dumps(result, allow_nan=False)))
        return result

    def test_obstacle_inertia_heat_and_manual_cuts_share_one_conservative_grid(self):
        request = fixture(refined=True)
        request["materials"][0]["density_kg_m3"] = 200000.0
        result = self.accepted(request)
        self.assertEqual(result["grid"]["shape"], [8, 8, 8])
        self.assertEqual(result["flow_diagnostics"]["momentum_grid_shape"], [8, 8, 8])
        self.assertTrue(result["grid"]["momentum_locally_refined"])
        self.assertEqual(result["grid"]["momentum_grid"], "resolved_nested_tensor_planes")
        self.assertFalse(result["grid"]["confined_patch_amr"])
        self.assertEqual(result["flow_diagnostics"]["momentum_grid_kind"],
                         "tensor_plane_rectilinear_not_octree")
        self.assertGreater(result["flow_diagnostics"]["force_work_w"], 0.0)
        self.assertGreater(result["flow_diagnostics"]["reynolds_upper_bound"], 1.0)
        self.assertGreaterEqual(result["flow_diagnostics"]["iterations"], 3)
        self.assertGreater(result["flow_diagnostics"]["momentum_residual_history"][0], 1e-4)
        self.assertLessEqual(result["flow_diagnostics"]["momentum_residual_history"][-1], 1e-10)
        self.assertGreater(result["energy_diagnostics"]["maximum_temperature_k"], 300.0)
        self.assertAlmostEqual(result["energy_diagnostics"]["generated_heat_w"], 0.8, delta=1e-12)
        self.assertLess(result["independent_mass_diagnostics"][
            "independent_maximum_divergence_s_inv"], result["independent_mass_diagnostics"][
                "independent_divergence_budget_s_inv"])
        self.assertLess(abs(result["energy_diagnostics"]["raw_energy_balance_w"]), 1e-12)
        self.assertGreater(len(result["interfaces"]), 0)

    def test_manual_cuts_change_actual_momentum_unknowns_and_solution(self):
        coarse_request, refined_request = fixture(refined=False), fixture(refined=True)
        coarse_request["materials"][0]["density_kg_m3"] = 200000.0
        refined_request["materials"][0]["density_kg_m3"] = 200000.0
        coarse = self.accepted(coarse_request)
        refined = self.accepted(refined_request)
        self.assertEqual(coarse["flow_diagnostics"]["momentum_grid_shape"], [4, 4, 4])
        self.assertEqual(refined["flow_diagnostics"]["momentum_grid_shape"], [8, 8, 8])
        self.assertGreater(refined["flow_diagnostics"]["velocity_unknowns"],
                           coarse["flow_diagnostics"]["velocity_unknowns"])
        # A transfer-only implementation preserves integrated coarse momentum work;
        # the independently assembled fine solve does not.
        self.assertGreater(abs(refined["flow_diagnostics"]["force_work_w"]
                               - coarse["flow_diagnostics"]["force_work_w"]), 1e-12)
        coarse_face = coarse["fields"]["face_velocity_m_s"][0][2][0][1]
        refined_same_point = refined["fields"]["face_velocity_m_s"][0][4][0][2]
        self.assertGreater(abs(refined_same_point - coarse_face), 1e-7)

    def test_disconnected_hydrostatic_components_have_zero_flow_and_uniform_temperature(self):
        request = fixture((5, 3, 3), obstacle=False)
        ids = np.full((5, 3, 3), "fluid", dtype="U8")
        ids[2, :, :] = "wall"
        request["materials"].append(material("wall", "solid", 2.0))
        request["material_ids"] = ids.tolist()
        force = np.broadcast_to([1.0, -0.5, 0.25], (5, 3, 3, 3)).copy()
        force[ids == "wall"] = 0.0
        request["flow"]["body_force_n_m3"] = force.tolist()
        request["heat_sources_w_m3"] = np.zeros((5, 3, 3)).tolist()
        result = self.accepted(request)
        self.assertEqual(result["flow_diagnostics"]["fluid_components"], 2)
        for values in result["fields"]["face_velocity_m_s"]:
            self.assertLess(float(np.max(np.abs(values), initial=0.0)), 1e-14)
        np.testing.assert_array_equal(result["fields"]["temperature_k"], 300.0)
        pressure = np.asarray(result["fields"]["gauge_pressure_pa"])
        for slab in (pressure[:2], pressure[3:]):
            np.testing.assert_allclose(np.diff(slab, axis=0), 0.1, atol=1e-13)
            np.testing.assert_allclose(np.diff(slab, axis=1), -0.05, atol=1e-13)
            np.testing.assert_allclose(np.diff(slab, axis=2), 0.025, atol=1e-13)

    def test_adiabatic_multimaterial_transient_startup_energy(self):
        request = fixture(refined=True)
        ids = np.asarray(request["material_ids"])
        capacities = {entry["id"]: entry["density_kg_m3"] * entry["specific_heat_j_kgk"]
                      for entry in request["materials"]}
        rate = 0.2
        request["flow"]["body_force_n_m3"] = np.zeros((4, 4, 4, 3)).tolist()
        request["heat_sources_w_m3"] = np.vectorize(lambda mid: rate * capacities[mid])(ids).tolist()
        request["boundaries"] = {face: {"type": "adiabatic"} for face in FACES}
        request["study"] = {"type": "transient", "time_step_s": 0.1, "steps": 4,
                            "initial_temperature_k": 300.0, "output_stride": 2}
        result = self.accepted(request)
        for frame in result["temperature_frames"]:
            np.testing.assert_allclose(frame["temperature_k"],
                                       300.0 + rate * frame["time_s"], atol=2e-12)
        self.assertLess(abs(result["energy_diagnostics"]["raw_integrated_energy_balance_j"]),
                        1e-12)

    def test_forged_cross_wall_momentum_is_rejected_by_coupler(self):
        request = fixture((3, 3, 3), obstacle=False)
        ids = np.full((3, 3, 3), "fluid", dtype="U8")
        ids[1, 1, 1] = "wall"
        request["materials"].append(material("wall", "solid"))
        request["material_ids"] = ids.tolist()
        request["flow"]["body_force_n_m3"] = np.zeros((3, 3, 3, 3)).tolist()
        faces = [np.zeros((4, 3, 3)), np.zeros((3, 4, 3)), np.zeros((3, 3, 4))]
        faces[0][1, 1, 1] = 1.0  # Fluid-to-solid face.
        forged = {"status": "completed", "fields": {
            "face_velocity_m_s": [value.tolist() for value in faces],
            "pressure_pa": np.zeros((3, 3, 3)).tolist()}, "diagnostics": {}}
        with patch("python.spike_core.enclosure_rectilinear_momentum."
                   "solve_enclosure_rectilinear_momentum", return_value=forged):
            result = solve_enclosure_cht_v2(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertNotIn("fields", result)
        self.assertRegex(str(result), "crosses a closed wall|supplied solid")

    def test_overflowing_forged_mass_field_is_rejected_before_thermal_solve(self):
        request = fixture((2, 2, 2), obstacle=False)
        request["grid"]["spacing_m"] = [1e-8] * 3
        request["flow"]["body_force_n_m3"] = np.zeros((2, 2, 2, 3)).tolist()
        faces = [np.zeros((3, 2, 2)), np.zeros((2, 3, 2)), np.zeros((2, 2, 3))]
        faces[0][1, :, :] = 1e302
        faces[1][:, 1, :] = -1e302
        forged = {"status": "completed", "fields": {
            "face_velocity_m_s": [value.tolist() for value in faces],
            "pressure_pa": np.zeros((2, 2, 2)).tolist()}, "diagnostics": {}}
        with patch("python.spike_core.enclosure_rectilinear_momentum."
                   "solve_enclosure_rectilinear_momentum", return_value=forged), patch(
                       "python.spike_core.enclosure_cht_v2.solve_enclosure_energy") as thermal:
            result = solve_enclosure_cht_v2(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertNotIn("fields", result)
        thermal.assert_not_called()

    def test_rejection_cancellation_resource_and_publication_guards_leak_no_fields(self):
        variants = []
        for path, value in [(("contract",), "bad"), (("extra",), 1),
                            (("flow", "model"), "turbulent"),
                            (("flow", "model"), "rotor"),
                            (("flow", "nonlinear_controls", "unknown"), 1)]:
            changed = fixture(obstacle=False)
            at(changed, path[:-1])[path[-1]] = value
            variants.append(changed)
        too_many_cells = fixture((17, 17, 17), obstacle=False)
        variants.append(too_many_cells)
        excessive_transient = fixture((16, 16, 16), obstacle=False)
        excessive_transient["flow"]["body_force_n_m3"] = np.zeros((16, 16, 16, 3)).tolist()
        excessive_transient["study"] = {"type": "transient", "time_step_s": 1.0,
                                         "steps": 256, "initial_temperature_k": 300.0,
                                         "output_stride": 1}
        excessive_transient["boundaries"] = {face: {"type": "adiabatic"} for face in FACES}
        variants.append(excessive_transient)
        for changed in variants:
            result = solve_enclosure_cht_v2(changed)
            self.assertEqual(result["status"], "blocked", result)
            self.assertNotIn("fields", result)
        cancelled = solve_enclosure_cht_v2(fixture(), cancel_check=lambda: True)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertNotIn("fields", cancelled)

        from python.spike_core import enclosure_cht_v2
        original = enclosure_cht_v2._snapshot

        def reject_result(value, **kwargs):
            if kwargs.get("label") == "result":
                raise ValueError("Enclosure result exceeds 8 MiB")
            return original(value, **kwargs)

        with patch.object(enclosure_cht_v2, "_snapshot", side_effect=reject_result):
            oversized = solve_enclosure_cht_v2(fixture(obstacle=False))
        self.assertEqual(oversized["status"], "blocked")
        self.assertNotIn("fields", oversized)

        underflow = fixture((2, 2, 2), obstacle=False)
        underflow["flow"]["body_force_n_m3"] = np.zeros((2, 2, 2, 3)).tolist()
        underflow["heat_sources_w_m3"] = np.full((2, 2, 2), 1e-310).tolist()
        rejected = solve_enclosure_cht_v2(underflow)
        self.assertEqual(rejected["status"], "blocked", rejected)
        self.assertNotIn("fields", rejected)

    def test_schema_is_strict_for_executed_request_result_and_diagnostics(self):
        request = fixture(refined=True)
        result = self.accepted(request)
        for kind, example in (("request", request), ("result", result)):
            for path in object_paths(example):
                changed = deepcopy(example)
                at(changed, path)["unrecognized_schema_probe"] = 0
                with self.subTest(kind=kind, path=path):
                    self.assertFalse(self.validators[kind].is_valid(changed))
        for section in ("flow_diagnostics", "independent_mass_diagnostics", "energy_diagnostics"):
            for key in result[section]:
                changed = deepcopy(result)
                del changed[section][key]
                self.assertFalse(self.validators["result"].is_valid(changed), (section, key))

    def test_unsuccessful_schema_accepts_actual_results_and_forbids_partial_fields(self):
        malformed = fixture(obstacle=False)
        malformed["extra"] = 1
        results = [solve_enclosure_cht_v2(malformed),
                   solve_enclosure_cht_v2(fixture(), cancel_check=lambda: True)]
        accepted = self.accepted(fixture(obstacle=False))
        for result in results:
            self.validators["result"].validate(result)
            for key in ("request_sha256", "grid", "fields", "history", "temperature_frames",
                        "interfaces", "flow_diagnostics", "independent_mass_diagnostics",
                        "energy_diagnostics", "limitations"):
                changed = deepcopy(result)
                changed[key] = accepted[key]
                self.assertFalse(self.validators["result"].is_valid(changed), key)

    def test_v1_contract_and_behavior_remain_unchanged(self):
        request = fixture(obstacle=False)
        request["contract"] = "spike/enclosure-cht-request/v1"
        request["flow"] = {"model": "creeping",
                           "body_force_n_m3": np.zeros((4, 4, 4, 3)).tolist()}
        result = solve_enclosure_cht(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["contract"], "spike/enclosure-cht-result/v1")
        self.assertFalse(result["grid"]["momentum_locally_refined"])

    def test_service_and_actual_cli_route_the_v2_contract(self):
        request = fixture((2, 2, 2), obstacle=False)
        response = handle_cfd_request("run_enclosure_cht_v2", {"request": request})
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["status"], "completed", response)
        catalog = handle_cfd_request("cfd_capabilities", {})["result"]
        capability = catalog["engines"]["spike.enclosure_cht_v2"]
        self.assertTrue(capability["selected_region_momentum_sizing"])
        self.assertTrue(capability["obstacle_inertia"])
        self.assertEqual(capability["momentum_grid"], "resolved_nested_tensor_planes")
        self.assertFalse(capability["confined_patch_amr"])
        self.assertFalse(capability["turbulence"])
        self.assertFalse(capability["rotating_machinery"])
        self.assertFalse(capability["production_qualified"])

        (ROOT / "build").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="enclosure-cht-v2-", dir=ROOT / "build") as name:
            directory = Path(name)
            request_path, output_path = directory / "request.json", directory / "result.json"
            request_path.write_text(json.dumps(request, allow_nan=False), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "run_cfd.py"), "--engine",
                 "enclosure-cht-v2", "--request", str(request_path), "--output", str(output_path)],
                cwd=ROOT, capture_output=True, text=True, timeout=60, shell=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            process = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(process["ok"], process)
            self.assertEqual(process["result"]["contract"], "spike/enclosure-cht-result/v2")


if __name__ == "__main__":
    unittest.main()
