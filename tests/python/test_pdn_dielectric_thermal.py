# SPDX-License-Identifier: Apache-2.0
"""Original RMS dielectric-loss and heated-slab coupling oracles."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import pdn_dielectric_thermal as coupled
from python.spike_core.pdn_dielectric_ac import extract_pdn_dielectric_ac
from tests.python.test_assembly_tetra_thermal import boundary, faces_at
from tests.python.test_pdn_dielectric_ac import plate, layered


def request(refinement=2):
    electrical = plate(refinement, epsilon=.01, sigma=2., tangent=.2, frequencies=[10.])
    thermal = {"contract": "spike/assembly-tetra-thermal-request/v1", "mesh": deepcopy(electrical["mesh"]),
               "materials": [{"id": "k", "thermal_conductivity_w_mk": 2.}],
               "boundaries": boundary(faces_at(electrical["mesh"], 0), "temperature", temperature_k=300.)
               + boundary(faces_at(electrical["mesh"], 1), "temperature", temperature_k=300.)}
    return {"contract": coupled.REQUEST_CONTRACT, "electrical_request": electrical,
            "drive": {"frequency_hz": 10., "voltages_v": {"load-terminal": {"real": 2., "imag": 0.}}},
            "thermal_request": thermal}


def uniform_density():
    return (2. + 2 * math.pi * 10 * .2 * .01) * 4.


class PdnDielectricThermalTests(unittest.TestCase):
    def test_rms_plate_cell_loads_and_independent_power_balance(self):
        req = request(2)
        original = deepcopy(req)
        result = coupled.run_pdn_dielectric_thermal(req)
        self.assertEqual(req, original)
        density = uniform_density()
        self.assertEqual(result["coupling_mode"], "one_way_no_temperature_feedback")
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["model_status"], "experimental")
        for cell in req["electrical_request"]["mesh"]["cells"]:
            self.assertAlmostEqual(result["heat_sources_w_m3"][cell["id"]], density, delta=2e-12)
            self.assertAlmostEqual(result["cell_power_w"][cell["id"]], density / 48, delta=2e-13)
        self.assertAlmostEqual(result["total_dielectric_power_w"], density, delta=2e-12)
        self.assertAlmostEqual(result["port_power_w"], density, delta=2e-12)
        self.assertLess(result["loss_relative_error"], 2e-12)
        balance = result["thermal_result"]["heat_balance"]
        self.assertAlmostEqual(balance["source_w"], density, delta=2e-12)
        self.assertAlmostEqual(balance["temperature_reaction_inward_w"], -density, delta=2e-9)
        self.assertLess(abs(balance["imbalance_w"]), 2e-9)
        self.assertTrue(all(item["source_object_ids"] == ["solid"] for item in result["cell_lineage"]))
        self.assertNotEqual(result["thermal_input_digest"], result["generated_thermal_input_digest"])

    def test_uniform_heated_slab_p1_refinement_against_parabolic_solution(self):
        errors = []
        for refinement in (2, 3, 4):
            req = request(refinement)
            result = coupled.run_pdn_dielectric_thermal(req)
            mesh = req["electrical_request"]["mesh"]
            temperatures = np.array(result["thermal_result"]["node_temperatures_k"])
            squared_error = 0.
            for cell, lineage in zip(mesh["cells"], result["cell_lineage"]):
                x = np.mean([mesh["vertices"][i][0] for i in cell["vertices"]])
                exact = 300 + uniform_density() * x * (1 - x) / (2 * 2.)
                # The tetra centroid interpolant is the mean of four P1
                # nodal temperatures. Compare to the analytic parabola there.
                actual = float(np.mean(temperatures[cell["vertices"]]))
                squared_error += lineage["volume_m3"] * (actual - exact)**2
            errors.append(math.sqrt(squared_error))
        self.assertGreater(errors[0] / errors[1], 1.8)
        self.assertGreater(errors[1] / errors[2], 1.5)
        self.assertLess(errors[-1], .04)

    def test_phase_invariance_quadratic_amplitude_and_zero_loss(self):
        base = coupled.run_pdn_dielectric_thermal(request())
        for real, imag, factor in ((0., 2., 1.), (4., 0., 4.)):
            req = request()
            req["drive"]["voltages_v"]["load-terminal"] = {"real": real, "imag": imag}
            result = coupled.run_pdn_dielectric_thermal(req)
            self.assertAlmostEqual(result["total_dielectric_power_w"] / base["total_dielectric_power_w"], factor, delta=2e-12)
            np.testing.assert_allclose(np.array(result["thermal_result"]["node_temperatures_k"]) - 300,
                                       factor * (np.array(base["thermal_result"]["node_temperatures_k"]) - 300), atol=2e-10)
        req = request()
        req["electrical_request"]["materials"][0].update(conductivity_s_m=0., loss_tangent=0.)
        result = coupled.run_pdn_dielectric_thermal(req)
        self.assertEqual(result["total_dielectric_power_w"], 0.)
        self.assertTrue(all(value == 0. for value in result["heat_sources_w_m3"].values()))
        np.testing.assert_allclose(result["thermal_result"]["node_temperatures_k"], 300., atol=2e-10)

    def test_heterogeneous_loss_with_coherent_multielectrode_cross_terms(self):
        req = request()
        electrical = layered(2)
        electrical["frequencies_hz"] = [10.]
        electrical["electrodes"].insert(1, {"id": "middle", "node": "middle-node",
            "vertices": [i for i, p in enumerate(electrical["mesh"]["vertices"]) if p[0] == .5]})
        req["electrical_request"] = electrical
        req["thermal_request"]["mesh"] = deepcopy(electrical["mesh"])
        req["thermal_request"]["materials"].append({"id": "second", "thermal_conductivity_w_mk": 7.})
        middle, last = 1 + 1j, 2 - .5j
        req["drive"]["voltages_v"] = {"middle-node": {"real": middle.real, "imag": middle.imag},
                                        "load-terminal": {"real": last.real, "imag": last.imag}}
        result = coupled.run_pdn_dielectric_thermal(req)
        losses = {m["id"]: m["conductivity_s_m"] + 2 * math.pi * 10 * m["loss_tangent"] * m["permittivity_f_m"]
                  for m in electrical["materials"]}
        densities = {"k": 4 * losses["k"] * abs(middle)**2, "second": 4 * losses["second"] * abs(last - middle)**2}
        for cell in electrical["mesh"]["cells"]:
            self.assertAlmostEqual(result["heat_sources_w_m3"][cell["id"]], densities[cell["material_id"]], delta=2e-16)
        expected = .5 * sum(densities.values())
        self.assertAlmostEqual(result["total_dielectric_power_w"], expected, delta=2e-16)
        self.assertAlmostEqual(result["port_power_w"], expected, delta=2e-16)
        independent_port_sum = 2 * losses["k"] * abs(middle)**2 + 2 * losses["second"] * (abs(middle)**2 + abs(last)**2)
        self.assertGreater(abs(expected - independent_port_sum), .25 * expected)

    def test_mesh_double_heat_drive_and_material_admission(self):
        mutations = [lambda r: r["thermal_request"]["mesh"]["vertices"][0].__setitem__(0, .00001),
            lambda r: r["thermal_request"].update(heat_sources_w_m3={"solid-0": 0.}),
            lambda r: r["thermal_request"].update(heat_sources_w_m3=[]),
            lambda r: r["drive"].update(frequency_hz=20.),
            lambda r: r["electrical_request"].update(frequencies_hz=[10., 20.]),
            lambda r: r["drive"].update(voltages_v={}),
            lambda r: r["drive"]["voltages_v"].update({"return-terminal": {"real": 0., "imag": 0.}}),
            lambda r: r["drive"]["voltages_v"]["load-terminal"].update(real=True),
            lambda r: r["thermal_request"]["materials"][0].update(id="other"),
            lambda r: r.update(electrical_result={})]
        for index, mutate in enumerate(mutations):
            req = request(); mutate(req)
            with self.subTest(case=index), patch.object(coupled, "extract_pdn_dielectric_ac") as solve:
                with self.assertRaises(coupled.PdnDielectricThermalError) as caught:
                    coupled.run_pdn_dielectric_thermal(req)
                self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_THERMAL_INVALID_REQUEST")
                solve.assert_not_called()

    def test_corrupted_fields_fail_conservation_before_thermal_solve(self):
        req = request()
        bad = extract_pdn_dielectric_ac(req["electrical_request"])
        for field in bad["ac"][0]["basis_cell_electric_field_v_m"]:
            for direction in field:
                for value in direction:
                    value["real"] *= 1.1; value["imag"] *= 1.1
        with patch.object(coupled, "extract_pdn_dielectric_ac", return_value=bad), \
                patch.object(coupled, "run_assembly_tetra_thermal") as thermal:
            with self.assertRaises(coupled.PdnDielectricThermalError) as caught:
                coupled.run_pdn_dielectric_thermal(req)
            self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_THERMAL_POWER_BALANCE_FAILURE")
            thermal.assert_not_called()
        bad["ac"][0]["basis_cell_electric_field_v_m"].pop()
        with patch.object(coupled, "extract_pdn_dielectric_ac", return_value=bad):
            with self.assertRaisesRegex(coupled.PdnDielectricThermalError, "dimensions"):
                coupled.run_pdn_dielectric_thermal(req)

    def test_resource_preflight_and_cancelled_thermal_result_not_published(self):
        for attribute in ("_MAX_REQUEST_BYTES", "_MAX_RESULT_BYTES"):
            with patch.object(coupled, attribute, 1), patch.object(coupled, "extract_pdn_dielectric_ac") as solve:
                with self.assertRaises(coupled.PdnDielectricThermalError) as caught:
                    coupled.run_pdn_dielectric_thermal(request())
                self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_THERMAL_RESOURCE_LIMIT")
                solve.assert_not_called()
        finished = False
        thermal = coupled.run_assembly_tetra_thermal

        def finish_then_cancel(raw):
            nonlocal finished
            result = thermal(raw)
            finished = True
            return result

        with patch.object(coupled, "run_assembly_tetra_thermal", side_effect=finish_then_cancel):
            with self.assertRaises(coupled.PdnDielectricThermalError) as caught:
                coupled.run_pdn_dielectric_thermal(request(), cancel_check=lambda: finished)
            self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_THERMAL_CANCELLED")
        self.assertTrue(finished)


if __name__ == "__main__":
    unittest.main()
