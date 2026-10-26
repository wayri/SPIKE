# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Executed AC/heat/elastic chain, independently derived slab and stress oracles."""
from copy import deepcopy
import hashlib
import json
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.solvers.power_integrity.pdn import pdn_dielectric_thermomechanical as chain
from tests.python.test_pdn_dielectric_thermal import request as electrothermal_request, uniform_density
from tests.python.test_assembly_tetra_structural import request as structural_request, fix, rigid_constraints


def request(n=2):
    electrical_heat = electrothermal_request(n)
    mechanics = structural_request(n)
    mechanics["mesh"] = deepcopy(electrical_heat["electrical_request"]["mesh"])
    mechanics["context_digest"] = electrical_heat["electrical_request"]["context_digest"]
    for node in range(len(mechanics["mesh"]["vertices"])):
        fix(mechanics, node)
    return {"contract": chain.REQUEST_CONTRACT, "electrothermal_request": electrical_heat,
            "structural_request": mechanics}


class DielectricThermomechanicalTests(unittest.TestCase):
    def test_executed_loss_temperature_clamped_stress_and_energy(self):
        raw = request(); before = deepcopy(raw)
        result = chain.run_pdn_dielectric_thermomechanical(raw)
        self.assertEqual(raw, before)
        q = uniform_density()
        thermal = result["electrothermal"]["thermal_result"]
        mesh = raw["structural_request"]["mesh"]
        xyz = np.array(mesh["vertices"])
        # Conservative P1 tetra mesh: verify temperature against slab continuum,
        # not just the child result or heat balance. This mesh has a finite error.
        exact_temperature = 300 + q*xyz[:, 0]*(1-xyz[:, 0])/4
        self.assertLess(np.max(np.abs(np.array(thermal["node_temperatures_k"])-exact_temperature)), .1)
        self.assertAlmostEqual(result["electrothermal"]["total_dielectric_power_w"], q, delta=1e-11)
        self.assertAlmostEqual(thermal["heat_balance"]["source_w"], q, delta=1e-11)
        self.assertLessEqual(abs(thermal["heat_balance"]["imbalance_w"]),
                             thermal["heat_balance"]["acceptance_tolerance_w"])
        temperatures = np.array(thermal["node_temperatures_k"])
        energy = 0.
        for cell, response in zip(mesh["cells"], result["structural"]["cells"]):
            self.assertEqual(cell["id"], response["cell_id"])
            self.assertEqual(cell["source_object_ids"], response["source_object_ids"])
            ids = cell["vertices"]
            volume = abs(np.linalg.det((xyz[ids][1:]-xyz[ids][0]).T))/6
            eigenstrain = 1e-5*(temperatures[ids].mean()-300)
            # Fully clamped isotropic law: sigma=-E*alpha*dT/(1-2nu)*I.
            pressure = -2e9*eigenstrain/(1-2*.25)
            np.testing.assert_allclose(response["stress_pa"], [pressure]*3+[0.]*3, atol=1e-8)
            self.assertLess(response["von_mises_pa"], 1e-7)
            energy += -.5*volume*3*pressure*eigenstrain
        self.assertAlmostEqual(result["structural"]["elastic_energy_j"], energy, delta=1e-11)
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["structural"]["input_digest"], result["generated_structural_input_digest"])

    def test_zero_loss_uniform_temperature_free_expansion(self):
        raw = request(1)
        material = raw["electrothermal_request"]["electrical_request"]["materials"][0]
        material.update(conductivity_s_m=0., loss_tangent=0.)
        for face in raw["electrothermal_request"]["thermal_request"]["boundaries"]:
            face["temperature_k"] = 350.
        mechanics = raw["structural_request"]
        mechanics["dirichlet"] = []
        rigid_constraints(mechanics)
        result = chain.run_pdn_dielectric_thermomechanical(raw)
        self.assertEqual(result["electrothermal"]["total_dielectric_power_w"], 0.)
        np.testing.assert_allclose(result["structural"]["node_displacements_m"],
                                   np.array(mechanics["mesh"]["vertices"])*.0005, atol=1e-15)
        self.assertLess(result["structural"]["elastic_energy_j"], 1e-22)

    def test_unicode_digest_profiles_are_preserved(self):
        raw = request(1)
        for mesh in (raw["electrothermal_request"]["electrical_request"]["mesh"],
                     raw["electrothermal_request"]["thermal_request"]["mesh"],
                     raw["structural_request"]["mesh"]):
            mesh["object_map"]["solid"]["body_id"] = "\u03bc-solid"
        result = chain.run_pdn_dielectric_thermomechanical(raw)
        digest = lambda value, escape: hashlib.sha256(json.dumps(value, sort_keys=True,
            separators=(",", ":"), ensure_ascii=escape, allow_nan=False).encode()).hexdigest()
        self.assertEqual(result["mesh_digest"], digest(raw["structural_request"]["mesh"], False))
        self.assertEqual(result["electrothermal"]["mesh_digest"], digest(raw["structural_request"]["mesh"], True))
        self.assertNotEqual(result["mesh_digest"], result["electrothermal"]["mesh_digest"])

    def test_invalid_context_mesh_temperatures_and_extra_fields_precede_solve(self):
        for mutation in ("context", "mesh", "number_type", "temperature", "extra", "nan"):
            raw = request(1)
            if mutation == "context": raw["structural_request"]["context_digest"] = "b"*64
            if mutation == "mesh": raw["structural_request"]["mesh"]["vertices"][0][0] = .01
            if mutation == "number_type": raw["structural_request"]["mesh"]["vertices"][0][0] = False
            if mutation == "temperature": raw["structural_request"]["nodal_temperatures_k"] = {"0": 300}
            if mutation == "extra": raw["result"] = {}
            if mutation == "nan": raw["structural_request"]["materials"][0]["young_modulus_pa"] = math.nan
            with self.subTest(mutation=mutation), patch.object(chain, "run_pdn_dielectric_thermal") as solve:
                with self.assertRaises(chain.PdnDielectricThermomechanicalError):
                    chain.run_pdn_dielectric_thermomechanical(raw)
                solve.assert_not_called()

    def test_bad_structural_preflight_and_double_heat_do_not_succeed(self):
        raw = request(1); raw["structural_request"]["dirichlet"] = []
        with patch.object(chain, "run_pdn_dielectric_thermal") as solve:
            with self.assertRaisesRegex(chain.PdnDielectricThermomechanicalError, "Rigid|rigid|condition"):
                chain.run_pdn_dielectric_thermomechanical(raw)
            solve.assert_not_called()
        raw = request(1)
        raw["electrothermal_request"]["thermal_request"]["heat_sources_w_m3"] = {"solid-0": 1.}
        with self.assertRaises(chain.PdnDielectricThermomechanicalError):
            chain.run_pdn_dielectric_thermomechanical(raw)

    def test_tampered_child_identity_and_temperatures_rejected(self):
        raw = request(1)
        actual = chain.run_pdn_dielectric_thermal(raw["electrothermal_request"])
        for mutation in ("digest", "status", "temperature_count", "temperature_type", "negative", "heat_contract"):
            response = deepcopy(actual)
            if mutation == "digest": response["input_digest"] = "0"*64
            if mutation == "status": response["production_qualified"] = True
            if mutation == "temperature_count": response["thermal_result"]["node_temperatures_k"].pop()
            if mutation == "temperature_type": response["thermal_result"]["node_temperatures_k"][0] = True
            if mutation == "negative": response["thermal_result"]["node_temperatures_k"][0] = -1.
            if mutation == "heat_contract": response["thermal_result"]["contract"] = "foreign"
            with self.subTest(mutation=mutation), patch.object(chain, "run_pdn_dielectric_thermal", return_value=response):
                with self.assertRaises(chain.PdnDielectricThermomechanicalError):
                    chain.run_pdn_dielectric_thermomechanical(raw)

    def test_cancellation_and_callback_failure_have_stable_codes(self):
        with self.assertRaises(chain.PdnDielectricThermomechanicalError) as caught:
            chain.run_pdn_dielectric_thermomechanical(request(1), cancel_check=lambda: True)
        self.assertTrue(caught.exception.code.endswith("CANCELLED"))
        def failed(): raise RuntimeError("callback failed")
        with self.assertRaises(chain.PdnDielectricThermomechanicalError) as caught:
            chain.run_pdn_dielectric_thermomechanical(request(1), cancel_check=failed)
        self.assertTrue(caught.exception.code.endswith("CANCEL_CHECK_FAILED"))
        stopped = [False]
        original = chain.run_pdn_dielectric_thermal
        def solve(value, **kwargs):
            result = original(value, **kwargs); stopped[0] = True
            return result
        with patch.object(chain, "run_pdn_dielectric_thermal", side_effect=solve):
            with self.assertRaises(chain.PdnDielectricThermomechanicalError) as caught:
                chain.run_pdn_dielectric_thermomechanical(request(1), cancel_check=lambda: stopped[0])
            self.assertTrue(caught.exception.code.endswith("CANCELLED"))

    def test_request_and_result_resource_limits(self):
        with patch.object(chain, "_REQUEST_LIMIT", 256):
            with self.assertRaises(chain.PdnDielectricThermomechanicalError) as caught:
                chain.run_pdn_dielectric_thermomechanical(request(1))
            self.assertTrue(caught.exception.code.endswith("RESOURCE_LIMIT"))
        with patch.object(chain, "_RESULT_LIMIT", 256):
            with self.assertRaises(chain.PdnDielectricThermomechanicalError) as caught:
                chain.run_pdn_dielectric_thermomechanical(request(1))
            self.assertTrue(caught.exception.code.endswith("RESOURCE_LIMIT"))

    def test_child_cancellation_and_resource_classification_survives_coupling(self):
        from python.spike_core.solvers.power_integrity.pdn.pdn_dielectric_thermal import PdnDielectricThermalError
        from python.spike_core.solvers.mechanics.elasticity.assembly_tetra_structural import AssemblyTetraStructuralError
        for name, error_type in (("run_pdn_dielectric_thermal", PdnDielectricThermalError),
                                 ("run_assembly_tetra_structural", AssemblyTetraStructuralError)):
            for code in ("cancelled", "cancel_check_failed", "resource_limit"):
                with self.subTest(owner=name, code=code), patch.object(chain, name,
                        side_effect=error_type(code, "declared subsolve failure")):
                    with self.assertRaises(chain.PdnDielectricThermomechanicalError) as caught:
                        chain.run_pdn_dielectric_thermomechanical(request(1))
                    self.assertTrue(caught.exception.code.endswith(code.upper()))
    def test_slab_temperature_refinement_is_not_just_heat_conservation(self):
        errors = []
        for n in (1, 2, 4):
            raw = request(n)
            result = chain.run_pdn_dielectric_thermomechanical(raw)
            xyz = np.asarray(raw["structural_request"]["mesh"]["vertices"])
            temperatures = np.asarray(result["electrothermal"]["thermal_result"]["node_temperatures_k"])
            error = 0.
            for cell in raw["structural_request"]["mesh"]["cells"]:
                ids = cell["vertices"]; points = xyz[ids]
                volume = abs(np.linalg.det((points[1:]-points[0]).T))/6
                x = points[:, 0].mean()
                difference = temperatures[ids].mean() - (300+uniform_density()*x*(1-x)/4)
                error += volume*difference*difference
            errors.append(math.sqrt(error))
        self.assertGreater(errors[0], 0.)
        for coarse, fine in zip(errors, errors[1:]):
            self.assertGreaterEqual(math.log(coarse/fine, 2), 1.7)


if __name__ == "__main__":
    unittest.main()
