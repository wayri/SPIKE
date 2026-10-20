# SPDX-License-Identifier: Apache-2.0
"""Independent steady/transient 3-D energy, material and flow composition oracles."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.enclosure_cht import REQUEST, solve_enclosure_cht


def material(name="fluid", phase="fluid", conductivity=1., capacity=1.):
    value = {"id": name, "phase": phase, "density_kg_m3": 1.,
             "specific_heat_j_kgk": capacity, "conductivity_w_mk": conductivity}
    if phase == "fluid":
        value["dynamic_viscosity_pa_s"] = 1.
    return value


def fixture(shape=(3, 3, 3)):
    return {"contract": REQUEST, "grid": {"shape": list(shape), "spacing_m": [.1]*3,
            "origin_m": [0.]*3, "local_refinement": []}, "materials": [material()],
        "material_ids": np.full(shape, "fluid").tolist(),
        "flow": {"model": "creeping", "body_force_n_m3": np.zeros((*shape, 3)).tolist()},
        "heat_sources_w_m3": np.zeros(shape).tolist(),
        "boundaries": {face: {"type": "temperature", "temperature_k": 300.}
                       for face in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")},
        "study": {"type": "steady"}}


def layered_fixture(refined=False):
    q = fixture((6, 2, 2))
    q["materials"] = [material(conductivity=.5), material("left", "solid", 2.), material("right", "solid", 4.)]
    ids = np.full((6, 2, 2), "fluid", dtype="U8")
    ids[0] = "left"
    ids[-1] = "right"
    q["material_ids"] = ids.tolist()
    q["boundaries"] = {face: {"type": "adiabatic"} for face in q["boundaries"]}
    q["boundaries"]["x_min"] = {"type": "temperature", "temperature_k": 310.}
    q["boundaries"]["x_max"] = {"type": "temperature", "temperature_k": 300.}
    if refined:
        q["grid"]["local_refinement"] = [{"bounds_m": [[.22, .38], [.05, .15], [.05, .15]], "split_factor": 2}]
    return q


class EnclosureChtTests(unittest.TestCase):
    def test_three_dimensional_conduction_spatial_refinement(self):
        errors = []
        for n in (4, 8, 12):
            q = fixture((n, n, n))
            q["grid"]["spacing_m"] = [1/n]*3
            centers = (np.arange(n)+.5)/n
            x, y, z = np.meshgrid(centers, centers, centers, indexing="ij")
            rise = np.sin(math.pi*x)*np.sin(math.pi*y)*np.sin(math.pi*z)
            q["heat_sources_w_m3"] = (3*math.pi**2*rise).tolist()
            r = self.accepted(q)
            error = np.linalg.norm(np.asarray(r["fields"]["temperature_k"])-300-rise)/np.linalg.norm(rise)
            errors.append(float(error))
        self.assertLess(errors[-1], .01)
        for first, second, ratio in zip(errors, errors[1:], (2., 1.5)):
            self.assertGreater(math.log(first/second)/math.log(ratio), 1.8)

    def test_rejected_publication_never_leaks_accepted_fields(self):
        from python.spike_core import enclosure_cht
        original = enclosure_cht._snapshot

        def reject_result(value, **kwargs):
            if kwargs.get("label") == "result":
                raise ValueError("Enclosure result exceeds 8 MiB")
            return original(value, **kwargs)

        with patch.object(enclosure_cht, "_snapshot", side_effect=reject_result):
            result = solve_enclosure_cht(fixture())
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("fields", result)
        self.assertNotIn("request_sha256", result)

    def accepted(self, q):
        result = solve_enclosure_cht(q)
        self.assertEqual(result["status"], "completed", result)
        self.assertFalse(result["production_qualified"])
        return result

    def test_isothermal_state_exact_with_obstacle_and_refinement(self):
        q = fixture((4, 4, 4))
        ids = np.full((4, 4, 4), "fluid", dtype="U8")
        ids[1:3, 1:3, 1:3] = "block"
        q["material_ids"] = ids.tolist()
        q["materials"].append(material("block", "solid", 7., 9.))
        q["grid"]["local_refinement"] = [{"bounds_m": [[.15, .25]]*3, "split_factor": 2}]
        result = self.accepted(q)
        np.testing.assert_array_equal(result["fields"]["temperature_k"], 300.)
        self.assertEqual(result["energy_diagnostics"]["raw_energy_balance_w"], 0.)
        self.assertFalse(result["grid"]["momentum_locally_refined"])

    def test_three_material_continuous_series_resistance_and_interfaces(self):
        for refined in (False, True):
            q = layered_fixture(refined)
            r = self.accepted(q)
            expected_q = 10/(.1/2+.4/.5+.1/4)
            self.assertAlmostEqual(r["energy_diagnostics"]["outward_heat_w"]["x_min"], -expected_q*.04, delta=1e-12)
            self.assertAlmostEqual(r["energy_diagnostics"]["outward_heat_w"]["x_max"], expected_q*.04, delta=1e-12)
            axes = r["grid"]["axes_m"]
            for i, x in enumerate((np.asarray(axes[0][:-1])+axes[0][1:])/2):
                resistance = x/2 if x < .1 else .1/2+(x-.1)/.5 if x < .5 else .1/2+.4/.5+(x-.5)/4
                np.testing.assert_allclose(np.asarray(r["fields"]["temperature_k"])[i], 310-expected_q*resistance, atol=1e-11)
            self.assertGreater(len(r["interfaces"]), 0)
            self.assertLess(r["energy_diagnostics"]["maximum_interface_temperature_jump_k"], 1e-12)

    def test_nonzero_3d_recirculation_couples_solid_heat_and_conserves(self):
        q = fixture((5, 4, 4))
        ids = np.full((5, 4, 4), "fluid", dtype="U8")
        ids[2, 1:3, 1:3] = "heater"
        q["material_ids"] = ids.tolist()
        q["materials"].append(material("heater", "solid", 3.))
        force = np.zeros((5, 4, 4, 3))
        force[..., 0] = np.arange(4)[None, :, None]*.01
        force[ids == "heater"] = 0.
        q["flow"]["body_force_n_m3"] = force.tolist()
        heat = np.zeros((5, 4, 4))
        heat[ids == "heater"] = 100.
        q["heat_sources_w_m3"] = heat.tolist()
        q["grid"]["local_refinement"] = [{"bounds_m": [[.2, .3], [.1, .3], [.1, .3]], "split_factor": 2}]
        r = self.accepted(q)
        self.assertGreater(r["flow_diagnostics"]["force_work_w"], 0.)
        self.assertGreater(r["energy_diagnostics"]["maximum_temperature_k"], 300.)
        self.assertAlmostEqual(r["energy_diagnostics"]["generated_heat_w"], .4, delta=1e-13)
        self.assertLess(abs(r["energy_diagnostics"]["raw_energy_balance_w"]), 1e-11)
        self.assertLess(r["transfer_diagnostics"]["maximum_fine_divergence_s_inv"], 1e-10)

    def test_adiabatic_multimaterial_startup_exact_energy(self):
        q = layered_fixture(True)
        ids = np.asarray(q["material_ids"])
        q["materials"][1]["specific_heat_j_kgk"] = 2.
        q["materials"][2]["specific_heat_j_kgk"] = 3.
        capacities = {m["id"]: m["density_kg_m3"]*m["specific_heat_j_kgk"] for m in q["materials"]}
        q["heat_sources_w_m3"] = np.vectorize(lambda mid: .2*capacities[mid])(ids).tolist()
        q["boundaries"] = {face: {"type": "adiabatic"} for face in q["boundaries"]}
        q["study"] = {"type": "transient", "time_step_s": .1, "steps": 8,
                      "initial_temperature_k": 300., "output_stride": 2}
        r = self.accepted(q)
        for frame in r["temperature_frames"]:
            np.testing.assert_allclose(frame["temperature_k"], 300+.2*frame["time_s"], atol=1e-12)
        self.assertLess(abs(r["energy_diagnostics"]["raw_integrated_energy_balance_j"]), 1e-12)
        self.assertEqual(r["energy_diagnostics"]["factorizations"], 1)

    def test_backward_euler_converges_to_independent_exponential(self):
        errors = []
        for steps in (8, 16, 32):
            q = fixture((1, 1, 1))
            q["grid"]["spacing_m"] = [1.]*3
            q["boundaries"] = {face: {"type": "convection", "ambient_temperature_k": 300.,
                 "heat_transfer_coefficient_w_m2k": .1} for face in q["boundaries"]}
            q["study"] = {"type": "transient", "time_step_s": 1/steps, "steps": steps,
                          "initial_temperature_k": 310., "output_stride": steps}
            result = self.accepted(q)
            exact = 300+10*math.exp(-6/(.5+10))
            actual = result["fields"]["temperature_k"][0][0][0]
            errors.append(abs(actual-exact))
        self.assertGreater(math.log(errors[0]/errors[1], 2), .9)
        self.assertGreater(math.log(errors[1]/errors[2], 2), .9)

    def test_inertial_box_composition_and_solid_walls(self):
        q = fixture((4, 4, 4))
        ids = np.full((4, 4, 4), "wall", dtype="U8")
        ids[1:3, 1:3, 1:3] = "fluid"
        q["material_ids"] = ids.tolist()
        q["materials"].append(material("wall", "solid", 2.))
        q["flow"] = {"model": "laminar_inertial", "body_force_n_m3": np.zeros((4, 4, 4, 3)).tolist(),
                     "nonlinear_controls": {"max_iterations": 30, "relaxation": 1., "relative_tolerance": 1e-10}}
        r = self.accepted(q)
        np.testing.assert_array_equal(r["fields"]["temperature_k"], 300.)
        self.assertEqual(r["flow_diagnostics"]["thermal_grid_fluid_box_indices"], [[1, 1, 1], [3, 3, 3]])
        q["material_ids"][1][1][1] = "wall"
        rejected = solve_enclosure_cht(q)
        self.assertEqual(rejected["status"], "blocked")
        self.assertNotIn("fields", rejected)

    def test_failures_and_cancellation_publish_no_partial_fields(self):
        variants = []
        for key, value in (("contract", "bad"), ("materials", []), ("extra", 1)):
            q = fixture()
            q[key] = value
            variants.append(q)
        q = fixture()
        q["flow"]["body_force_n_m3"][0][0][0][0] = True
        variants.append(q)
        q = fixture()
        q["boundaries"] = {face: {"type": "adiabatic"} for face in q["boundaries"]}
        variants.append(q)
        q = fixture()
        q["flow"]["model"] = "SST"
        variants.append(q)
        for q in variants:
            rejected = solve_enclosure_cht(q)
            self.assertEqual(rejected["status"], "blocked", rejected)
            self.assertNotIn("fields", rejected)
        cancelled = solve_enclosure_cht(fixture(), cancel_check=lambda: True)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertNotIn("fields", cancelled)

    def test_weak_anchor_cannot_hide_arbitrary_constant_temperature(self):
        q = fixture()
        q["grid"]["spacing_m"] = [.001]*3
        q["materials"][0]["conductivity_w_mk"] = 1e5
        q["boundaries"] = {face: {"type": "convection", "ambient_temperature_k": 300.,
            "heat_transfer_coefficient_w_m2k": 1e-12} for face in q["boundaries"]}
        heat = np.zeros((3, 3, 3))
        heat[0] = 1e12
        heat[-1] = -1e12
        q["heat_sources_w_m3"] = heat.tolist()
        rejected = solve_enclosure_cht(q)
        self.assertEqual(rejected["status"], "blocked", rejected)
        self.assertNotIn("fields", rejected)
        self.assertRegex(str(rejected), "condition|anchor")
        for bc in q["boundaries"].values():
            bc["heat_transfer_coefficient_w_m2k"] = 1000.
        resolved = self.accepted(q)
        self.assertAlmostEqual(float(np.mean(resolved["fields"]["temperature_k"])), 300., delta=1e-7)

    def test_large_origin_metric_mismatch_rejects_before_flow_acceptance(self):
        q = fixture((4, 4, 4))
        q["grid"]["spacing_m"] = [.3]*3
        q["grid"]["origin_m"] = [1e15]*3
        rejected = solve_enclosure_cht(q)
        self.assertEqual(rejected["status"], "blocked", rejected)
        self.assertNotIn("fields", rejected)


if __name__ == "__main__":
    unittest.main()
