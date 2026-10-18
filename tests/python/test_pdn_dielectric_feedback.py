# SPDX-License-Identifier: Apache-2.0
"""Original discrete electrothermal feedback oracle, no external solver data."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import pdn_dielectric_feedback as feedback
from python.spike_core import pdn_dielectric_thermal as coupled
from tests.python.test_assembly_tetra_thermal import boundary, faces_at
from tests.python.test_pdn_dielectric_thermal import request as one_way_request


def request(alpha=.02, relaxation=1.):
    base = one_way_request(1)
    base["electrical_request"]["materials"][0]["loss_tangent"] = 0.
    mesh = base["thermal_request"]["mesh"]
    base["thermal_request"]["boundaries"] = boundary(faces_at(mesh, 0), "temperature", temperature_k=300.)
    return {"contract": feedback.REQUEST_CONTRACT, "base_request": base,
            "conductivity_laws": [{"material_id": "k", "reference_temperature_k": 300.,
                "temperature_coefficient_per_k": alpha, "temperature_range_k": [299., 320.]}],
            "iteration": {"initial_temperature_k": 300., "max_iterations": 100, "relaxation": relaxation,
                          "temperature_tolerance_k": 1e-8, "power_relative_tolerance": 1e-10}}


def discrete_reference(req):
    """Independently assemble (K-H) theta=f0, with theta=0 at x=0.

    Every electrical vertex is prescribed, so E=2*xhat exactly even for
    different cell sigma. A mean-temperature law gives q=q0+sigma*4*alpha
    *sum(theta_i)/4; equal P1 nodal source integrals give the rank-one
    H_e=volume*sigma*4*alpha*ones(4,4)/16. No feedback API or thermal kernel
    supplies this oracle's operator, load, gradients or reference solution.
    """
    base = req["base_request"]
    mesh = base["electrical_request"]["mesh"]
    xyz = np.array(mesh["vertices"])
    n = len(xyz)
    operator, rhs = np.zeros((n, n)), np.zeros(n)
    electrical = {m["id"]: m for m in base["electrical_request"]["materials"]}
    thermal = {m["id"]: m for m in base["thermal_request"]["materials"]}
    laws = {law["material_id"]: law for law in req["conductivity_laws"]}
    for cell in mesh["cells"]:
        nodes, material = cell["vertices"], cell["material_id"]
        positions = xyz[nodes]
        volume = abs(np.linalg.det(positions[1:] - positions[0])) / 6
        affine = np.column_stack((np.ones(4), positions))
        gradients = np.linalg.inv(affine)[1:, :]
        k = np.array(thermal[material]["thermal_conductivity_w_mk"])
        if k.ndim == 0:
            k = float(k) * np.eye(3)
        sigma = electrical[material]["conductivity_s_m"]
        alpha = laws[material]["temperature_coefficient_per_k"]
        local = volume * gradients.T @ k @ gradients - volume * sigma * 4 * alpha / 16 * np.ones((4, 4))
        operator[np.ix_(nodes, nodes)] += local
        rhs[nodes] += volume * sigma * 4 / 4
    free = np.flatnonzero(xyz[:, 0] > 0)
    result = np.full(n, 300.)
    result[free] += np.linalg.solve(operator[np.ix_(free, free)], rhs[free])
    return result


class PdnDielectricFeedbackTests(unittest.TestCase):
    def test_positive_and_negative_feedback_against_independent_discrete_system(self):
        for alpha in (.02, -.02):
            req = request(alpha)
            before = deepcopy(req)
            out = feedback.run_pdn_dielectric_feedback(req)
            self.assertEqual(req, before)
            expected = discrete_reference(req)
            actual = out["last_coupled_result"]["thermal_result"]["node_temperatures_k"]
            np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-8)
            np.testing.assert_allclose(out["operating_temperature_k"], expected, rtol=0, atol=2e-8)
            self.assertLessEqual(out["diagnostics"]["temperature_residual_k"], 1e-8)
            self.assertLessEqual(out["diagnostics"]["power_relative_change"], 1e-10)
            self.assertEqual(out["coupling_mode"], "two_way_conductivity_temperature")
            self.assertEqual(out["model_status"], "experimental")
            self.assertFalse(out["production_qualified"])
            self.assertIsNone(out["history"][0]["power_relative_change"])
            last = out["last_coupled_result"]
            self.assertLess(last["loss_relative_error"], 1e-12)
            self.assertLess(abs(last["thermal_result"]["heat_balance"]["imbalance_w"]), 1e-10)

    def test_zero_coefficient_and_zero_loss_equivalence(self):
        for sigma in (2., 0.):
            req = request(0.)
            req["base_request"]["electrical_request"]["materials"][0]["conductivity_s_m"] = sigma
            one = coupled.run_pdn_dielectric_thermal(req["base_request"])
            out = feedback.run_pdn_dielectric_feedback(req)
            last = out["last_coupled_result"]
            np.testing.assert_allclose(last["thermal_result"]["node_temperatures_k"],
                                       one["thermal_result"]["node_temperatures_k"], rtol=0, atol=1e-12)
            self.assertEqual(last["heat_sources_w_m3"], one["heat_sources_w_m3"])
            self.assertEqual(out["diagnostics"]["iterations"], 2)
            self.assertEqual(out["diagnostics"]["power_relative_change"], 0.)

    def test_underrelaxation_checks_raw_residual_and_reported_material_state(self):
        req = request(.1, .4)
        out = feedback.run_pdn_dielectric_feedback(req)
        np.testing.assert_allclose(out["last_coupled_result"]["thermal_result"]["node_temperatures_k"],
                                   discrete_reference(req), rtol=0, atol=2e-8)
        operating = np.array(out["operating_temperature_k"])
        target = np.array(out["last_coupled_result"]["thermal_result"]["node_temperatures_k"])
        self.assertEqual(float(np.max(abs(target - operating))), out["diagnostics"]["temperature_residual_k"])
        for cell, state in zip(req["base_request"]["electrical_request"]["mesh"]["cells"], out["cell_material_state"]):
            mean = np.mean(operating[cell["vertices"]])
            self.assertEqual(state["mean_temperature_k"], mean)
            self.assertAlmostEqual(state["conductivity_s_m"], 2 * (1 + .1 * (mean - 300)), delta=1e-14)
        req = request(0., 1e-6)
        req["iteration"].update(max_iterations=2, temperature_tolerance_k=1e-4)
        with self.assertRaises(feedback.PdnDielectricFeedbackError) as caught:
            feedback.run_pdn_dielectric_feedback(req)
        self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_FEEDBACK_NONCONVERGENCE")

    def test_original_material_mapping_ownership_and_generated_identity(self):
        req = request()
        base = req["base_request"]
        base["electrical_request"]["materials"].append({**base["electrical_request"]["materials"][0], "id": "other", "conductivity_s_m": 3.})
        base["thermal_request"]["materials"].append({"id": "other", "thermal_conductivity_w_mk": [[3., 0., 0.], [0., 2., 0.], [0., 0., 4.]]})
        req["conductivity_laws"].append({**req["conductivity_laws"][0], "material_id": "other", "temperature_coefficient_per_k": -.01})
        for owner in ("electrical_request", "thermal_request"):
            for cell in base[owner]["mesh"]["cells"][::2]:
                cell["material_id"] = "other"
        original = deepcopy(req)
        out = feedback.run_pdn_dielectric_feedback(req)
        self.assertEqual(req, original)
        np.testing.assert_allclose(out["last_coupled_result"]["thermal_result"]["node_temperatures_k"], discrete_reference(req), rtol=0, atol=2e-8)
        self.assertNotEqual(out["original_mesh_digest"], out["generated_mesh_digest"])
        self.assertEqual(out["generated_input_digest"], out["last_coupled_result"]["input_digest"])
        ids = set()
        for cell, state in zip(base["electrical_request"]["mesh"]["cells"], out["cell_material_state"]):
            self.assertEqual(state["original_material_id"], cell["material_id"])
            self.assertEqual(state["source_object_ids"], cell["source_object_ids"])
            self.assertEqual(state["cell_id"], cell["id"])
            ids.add(state["generated_material_id"])
        self.assertEqual(len(ids), len(out["cell_material_state"]))
        self.assertEqual(out["input_digest"], coupled._digest(original))

    def test_strict_law_and_iteration_admission(self):
        mutations = [lambda r: r.update(extra=True), lambda r: r.update(conductivity_laws=[]),
            lambda r: r["conductivity_laws"][0].update(material_id="unknown"),
            lambda r: r["conductivity_laws"][0].update(temperature_coefficient_per_k=True),
            lambda r: r["conductivity_laws"][0].update(temperature_coefficient_per_k=-.1),
            lambda r: r["conductivity_laws"][0].update(temperature_range_k=[301., 320.]),
            lambda r: r["iteration"].update(initial_temperature_k=321.),
            lambda r: r["iteration"].update(max_iterations=True),
            lambda r: r["iteration"].update(max_iterations=101),
            lambda r: r["iteration"].update(relaxation=0.),
            lambda r: r["iteration"].update(temperature_tolerance_k=2.),
            lambda r: r["iteration"].update(power_relative_tolerance=float("nan")),
            lambda r: r["base_request"]["thermal_request"].update(heat_sources_w_m3={"solid-0": 0.})]
        for index, mutate in enumerate(mutations):
            req = request(); mutate(req)
            with self.subTest(case=index), patch.object(coupled, "run_pdn_dielectric_thermal") as solve:
                with self.assertRaises(feedback.PdnDielectricFeedbackError):
                    feedback.run_pdn_dielectric_feedback(req)
                solve.assert_not_called()

    def test_range_exhaustion_and_resource_failures_publish_no_success(self):
        req = request()
        req["conductivity_laws"][0]["temperature_range_k"] = [299., 300.1]
        with self.assertRaises(feedback.PdnDielectricFeedbackError) as caught:
            feedback.run_pdn_dielectric_feedback(req)
        self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_FEEDBACK_TEMPERATURE_RANGE")
        req = request(); req["iteration"]["max_iterations"] = 1
        with self.assertRaises(feedback.PdnDielectricFeedbackError) as caught:
            feedback.run_pdn_dielectric_feedback(req)
        self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_FEEDBACK_NONCONVERGENCE")
        for constant in ("_MAX_REQUEST_BYTES", "_MAX_RESULT_BYTES", "_MAX_TOTAL_WORK"):
            with patch.object(feedback, constant, 1), patch.object(coupled, "run_pdn_dielectric_thermal") as solve:
                with self.assertRaises(feedback.PdnDielectricFeedbackError) as caught:
                    feedback.run_pdn_dielectric_feedback(request())
                self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_FEEDBACK_RESOURCE_LIMIT")
                solve.assert_not_called()

    def test_cancel_after_actual_subsolve_and_invalid_result(self):
        real_solve, finished = coupled.run_pdn_dielectric_thermal, False

        def complete(raw, **kwargs):
            nonlocal finished
            out = real_solve(raw, **kwargs)
            finished = True
            return out

        with patch.object(coupled, "run_pdn_dielectric_thermal", side_effect=complete):
            with self.assertRaises(feedback.PdnDielectricFeedbackError) as caught:
                feedback.run_pdn_dielectric_feedback(request(), cancel_check=lambda: finished)
            self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_FEEDBACK_CANCELLED")
        self.assertTrue(finished)
        with patch.object(coupled, "run_pdn_dielectric_thermal", return_value={}):
            with self.assertRaises(feedback.PdnDielectricFeedbackError) as caught:
                feedback.run_pdn_dielectric_feedback(request())
            self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_FEEDBACK_NUMERICAL_FAILURE")


if __name__ == "__main__":
    unittest.main()
