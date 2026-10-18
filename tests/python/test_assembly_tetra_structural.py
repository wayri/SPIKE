# SPDX-License-Identifier: Apache-2.0
"""Original analytical elasticity patches, energy and manufactured refinement."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import assembly_tetra_structural as structural
from tests.python.test_assembly_tetra_thermal import cube, faces_at


def request(n=1):
    mesh = cube(n)
    return {"contract": structural.REQUEST_CONTRACT, "mesh": mesh,
            "materials": [{"id": "k", "young_modulus_pa": 2e9, "poisson_ratio": .25,
                           "thermal_expansion_per_k": 1e-5, "reference_temperature_k": 300.}],
            "nodal_temperatures_k": None, "dirichlet": [], "nodal_forces_n": {}, "context_digest": "a"*64}


def fix(req, node, components="xyz", values=(0., 0., 0.)):
    for c in components:
        req["dirichlet"].append({"node_id": node, "component": c, "displacement_m": float(values["xyz".index(c)])})


def rigid_constraints(req):
    xyz = req["mesh"]["vertices"]
    fix(req, xyz.index([0., 0., 0.]))
    fix(req, xyz.index([1., 0., 0.]), "yz")
    fix(req, xyz.index([0., 1., 0.]), "z")


def analytic_stress(gradient, young=2e9, poisson=.25, eigenstrain=0.):
    strain = .5*(gradient+gradient.T)-np.eye(3)*eigenstrain
    mu, lam = young/(2*(1+poisson)), young*poisson/((1+poisson)*(1-2*poisson))
    return 2*mu*strain+lam*np.trace(strain)*np.eye(3)


def voigt(tensor):
    return [tensor[0, 0], tensor[1, 1], tensor[2, 2], tensor[0, 1], tensor[1, 2], tensor[0, 2]]


def refinement_error(n):
    req = request(n); a = 1e-4
    xyz = np.array(req["mesh"]["vertices"])
    for i, p in enumerate(xyz):
        if any(x == 0 or x == 1 for x in p):
            fix(req, i, values=(a*p[0]**2, 0., 0.))
    # div(sigma)_x=2*a*(lambda+2*mu); integrate constant body force by V/4.
    force = np.zeros_like(xyz)
    lam, mu = .8e9, .8e9
    for cell in req["mesh"]["cells"]:
        ids = cell["vertices"]; p = xyz[ids]
        volume = abs(np.linalg.det((p[1:]-p[0]).T))/6
        force[ids, 0] -= volume*2*a*(lam+2*mu)/4
    req["nodal_forces_n"] = {str(i): f.tolist() for i, f in enumerate(force)}
    result = structural.run_assembly_tetra_structural(req)
    displacement = np.array(result["node_displacements_m"])
    error = 0.
    for cell, data in zip(req["mesh"]["cells"], result["cells"]):
        ids = cell["vertices"]; center = xyz[ids].mean(0)
        difference = displacement[ids].mean(0)-[a*center[0]**2, 0., 0.]
        error += data["volume_m3"]*float(difference@difference)
    return np.sqrt(error)


class StructuralTests(unittest.TestCase):
    def test_affine_patch_rotated_mesh_stress_energy_and_lineage(self):
        req = request(); original = np.array(req["mesh"]["vertices"])
        rotation = np.array([[.8, -.6, 0], [.6, .8, 0], [0, 0, 1.]])
        xyz = original@rotation.T+[.2, -.3, .7]
        req["mesh"]["vertices"] = xyz.tolist()
        gradient = np.array([[1e-4, 2e-5, -3e-5], [4e-5, -2e-4, 6e-5], [8e-5, -7e-5, 3e-4]])
        for i, p in enumerate(xyz): fix(req, i, values=gradient@p)
        before = deepcopy(req); result = structural.run_assembly_tetra_structural(req)
        expected = analytic_stress(gradient)
        for cell in result["cells"]:
            np.testing.assert_allclose(cell["stress_pa"], voigt(expected), rtol=1e-12, atol=1e-8)
            self.assertEqual(cell["source_object_ids"], ["solid"])
        strain = .5*(gradient+gradient.T)
        self.assertAlmostEqual(result["elastic_energy_j"], .5*np.sum(strain*expected), delta=1e-10)
        self.assertEqual(req, before)
        self.assertEqual(result["mesh"], before["mesh"])

    def test_free_expansion_minimal_constraints_and_full_clamping(self):
        req = request(); rigid_constraints(req)
        req["nodal_temperatures_k"] = {str(i): 350. for i in range(8)}
        result = structural.run_assembly_tetra_structural(req)
        np.testing.assert_allclose(result["node_displacements_m"], np.array(req["mesh"]["vertices"])*.0005, rtol=2e-13, atol=1e-17)
        self.assertLess(max(np.max(np.abs(c["stress_pa"])) for c in result["cells"]), 1e-7)
        self.assertLess(result["elastic_energy_j"], 1e-24)
        req["dirichlet"] = []
        for i in range(8): fix(req, i)
        result = structural.run_assembly_tetra_structural(req)
        for cell in result["cells"]:
            np.testing.assert_allclose(cell["stress_pa"], [-2e6]*3+[0.]*3, rtol=2e-15, atol=1e-10)
            self.assertAlmostEqual(cell["von_mises_pa"], 0., delta=1e-10)
        self.assertAlmostEqual(result["elastic_energy_j"], 1500., delta=1e-10)

    def test_bar_traction_reactions_energy_and_millimetres(self):
        for unit, length in (("m", 1.), ("mm", .001)):
            req = request(); req["mesh"]["units"] = unit
            req["materials"][0]["poisson_ratio"] = 0.
            xyz = np.array(req["mesh"]["vertices"])
            for i, p in enumerate(xyz):
                if p[0] == 0: fix(req, i)
            traction = 1e5; loads = np.zeros_like(xyz)
            for face in faces_at(req["mesh"], 1):
                p = xyz[face]*length
                area = np.linalg.norm(np.cross(p[1]-p[0], p[2]-p[0]))/2
                loads[face, 0] += traction*area/3
            req["nodal_forces_n"] = {str(i): f.tolist() for i, f in enumerate(loads)}
            result = structural.run_assembly_tetra_structural(req)
            expected = np.zeros_like(xyz); expected[:, 0] = traction/2e9*xyz[:, 0]*length
            np.testing.assert_allclose(result["node_displacements_m"], expected, rtol=1e-12, atol=1e-18)
            reaction = sum(r["force_n"] for r in result["reactions_n"] if r["component"] == "x")
            self.assertAlmostEqual(reaction, -traction*length**2, delta=1e-10*length**2)
            self.assertAlmostEqual(result["elastic_energy_j"], traction**2/(2*2e9)*length**3, delta=1e-12*length**3)

    def test_manufactured_quadratic_field_refinement(self):
        errors = [refinement_error(n) for n in (1, 2, 3)]
        self.assertGreater(errors[0]/errors[1], 3.9)
        self.assertGreater(errors[1]/errors[2], 2.2)
        self.assertLess(errors[2], 3e-6)

    def test_multimaterial_reference_temperature_and_null_semantics(self):
        req = request()
        other = deepcopy(req["materials"][0]); other["id"] = "other"; other["reference_temperature_k"] = 350.
        req["materials"].append(other)
        req["mesh"]["cells"][0]["material_id"] = "other"
        for i in range(8): fix(req, i)
        result = structural.run_assembly_tetra_structural(req)
        self.assertEqual(result["elastic_energy_j"], 0.)
        req["nodal_temperatures_k"] = {str(i): 350. for i in range(8)}
        result = structural.run_assembly_tetra_structural(req)
        self.assertEqual(result["cells"][0]["stress_pa"], [0.]*6)
        self.assertLess(result["cells"][1]["stress_pa"][0], 0.)
        req["nodal_temperatures_k"] = {str(i): 300.+i*10 for i in range(8)}
        result = structural.run_assembly_tetra_structural(req)
        for source, cell in zip(req["mesh"]["cells"], result["cells"]):
            reference = 350. if source["material_id"] == "other" else 300.
            eigenstrain = 1e-5*(np.mean([req["nodal_temperatures_k"][str(i)] for i in source["vertices"]])-reference)
            np.testing.assert_allclose(cell["thermal_strain"], [eigenstrain]*3+[0.]*3, rtol=1e-14, atol=1e-20)
            np.testing.assert_allclose(cell["stress_pa"], voigt(analytic_stress(np.zeros((3, 3)), eigenstrain=eigenstrain)), rtol=1e-14, atol=1e-9)

    def test_rigid_modes_geometry_material_and_input_refusals(self):
        for mutation in ("rigid", "poisson", "boolean", "material", "temperature", "force", "duplicate", "inverted", "sliver", "context", "unknown"):
            req = request(); rigid_constraints(req)
            if mutation == "rigid": req["dirichlet"] = []
            elif mutation == "poisson": req["materials"][0]["poisson_ratio"] = .499
            elif mutation == "boolean": req["materials"][0]["young_modulus_pa"] = True
            elif mutation == "material": req["materials"][0]["id"] = "missing"
            elif mutation == "temperature": req["nodal_temperatures_k"] = {"0": 300.}
            elif mutation == "force": req["nodal_forces_n"] = {"00": [0, 0, 0]}
            elif mutation == "duplicate": req["dirichlet"].append(deepcopy(req["dirichlet"][0]))
            elif mutation == "inverted": req["mesh"]["cells"][0]["vertices"][1:3] = reversed(req["mesh"]["cells"][0]["vertices"][1:3])
            elif mutation == "sliver": req["mesh"]["vertices"] = [[x, y, z*1e-12] for x, y, z in req["mesh"]["vertices"]]
            elif mutation == "context": req["context_digest"] = "missing"
            else: req["extra"] = 1
            with self.subTest(mutation=mutation), self.assertRaises(structural.AssemblyTetraStructuralError):
                structural.run_assembly_tetra_structural(req)

    def test_resources_cancel_and_finite_result(self):
        req = request(4)
        with patch.object(structural.mesh_validation, "validate_request", side_effect=AssertionError("must preflight")):
            with self.assertRaisesRegex(structural.AssemblyTetraStructuralError, "192"):
                structural.run_assembly_tetra_structural(req)
        req = request(); rigid_constraints(req)
        for threshold in (1, 4, 12):
            calls = []
            def cancel():
                calls.append(1)
                return len(calls) >= threshold
            with self.subTest(threshold=threshold), self.assertRaises(structural.AssemblyTetraStructuralError) as caught:
                structural.run_assembly_tetra_structural(req, cancel_check=cancel)
            self.assertIn("CANCELLED", caught.exception.code)
        with patch.object(structural, "_MAX_WORK", 1):
            with self.assertRaisesRegex(structural.AssemblyTetraStructuralError, "work"):
                structural.run_assembly_tetra_structural(req)
        req["materials"][0]["young_modulus_pa"] = float("inf")
        with self.assertRaises(structural.AssemblyTetraStructuralError):
            structural.run_assembly_tetra_structural(req)


if __name__ == "__main__": unittest.main()
