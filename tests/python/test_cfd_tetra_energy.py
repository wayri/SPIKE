# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent analytical RT0 conduction and tetra upwind energy checks."""
import copy
import itertools
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.cfd_tetra_mesh import admit_cfd_tetra_mesh
from python.spike_core.cfd_tetra_energy import CONTRACT, solve_cfd_tetra_energy
from tests.python.test_cfd_tetra_stokes import box_mesh


def layered_mesh(n=1):
    shape = (3*n, n, n)
    nodes = list(itertools.product(*(range(v+1) for v in shape)))
    ids = {v: i for i, v in enumerate(nodes)}
    vertices = np.asarray(nodes, float)/np.asarray(shape)
    cells = []
    for base in itertools.product(*(range(v) for v in shape)):
        for order in itertools.permutations(range(3)):
            pos = list(base); cell = [ids[tuple(pos)]]
            for axis in order:
                pos[axis] += 1; cell.append(ids[tuple(pos)])
            if np.linalg.det((vertices[cell[1:]]-vertices[cell[0]]).T) < 0.:
                cell[0], cell[1] = cell[1], cell[0]
            cells.append(cell)
    owners = {}
    for cell in cells:
        for face in itertools.combinations(cell, 3):
            key = tuple(sorted(face)); owners[key] = owners.get(key, 0)+1
    patches = {"left": [], "right": [], "sides": []}
    for face, count in owners.items():
        if count == 1:
            x = vertices[list(face), 0]
            name = "left" if np.all(x == 0.) else "right" if np.all(x == 1.) else "sides"
            patches[name].append(list(face))
    return {"contract": "spike/cfd-tetra-mesh/v1", "units": "m", "vertices": vertices.tolist(),
            "cells": cells, "boundary_patches": patches}


def base_request(mesh):
    geometry = admit_cfd_tetra_mesh(mesh)
    return {"contract": CONTRACT, "mesh": mesh,
            "cell_material_ids": ["fluid"]*len(mesh["cells"]),
            "materials": {"fluid": {"phase": "fluid", "conductivity_w_mk": 1., "specific_heat_j_kgk": 1.}},
            "face_mass_flow_kg_s": np.zeros(len(geometry["face_areas"])),
            "source_w_m3": np.zeros(len(mesh["cells"])), "reference_temperature_k": 300.,
            "boundaries": {key: {"type": "temperature", "temperature_k": 300.}
                           for key in mesh["boundary_patches"]}}, geometry


def quadratic_mean(points):
    # E[x_i^2] from simplex barycentric moments, independent of production M.
    count = points.shape[-2]
    return np.sum((np.sum(points*points, axis=-2)+np.sum(points, axis=-2)**2)
                  /(count*(count+1)), axis=-1)


def manufactured(n, layered=False):
    request, g = base_request(layered_mesh(n) if layered else box_mesh(n))
    if layered:
        x = g["cell_centroids"][:, 0]
        ids = ["left_solid" if v < 1/3 else "right_solid" if v > 2/3 else "fluid" for v in x]
        request["cell_material_ids"] = ids
        request["materials"].update(
            left_solid={"phase": "solid", "conductivity_w_mk": 2., "specific_heat_j_kgk": 0.},
            right_solid={"phase": "solid", "conductivity_w_mk": 4., "specific_heat_j_kgk": 0.})
        coefficients = np.array([request["materials"][v]["conductivity_w_mk"] for v in ids])
        fluid = np.array([v == "fluid" for v in ids])
        velocity = np.array([0., 1., .25])
        points = g["vertices"][g["cells"]].copy(); points[:, :, 0] = 0.
        exact = quadratic_mean(points)
        request["source_w_m3"] = -4.*coefficients+fluid*(g["cell_centroids"] @ (2.*velocity))
    else:
        fluid = np.ones(len(g["cells"]), bool)
        velocity = np.array([1., .5, .25])
        exact = quadratic_mean(g["vertices"][g["cells"]])
        request["source_w_m3"] = -6.+g["cell_centroids"] @ (2.*velocity)
    mass = g["face_areas"]*(g["face_normals"] @ velocity)
    for f, (left, right) in enumerate(g["face_owners"]):
        if not fluid[left] or (right >= 0 and not fluid[right]):
            mass[f] = 0.
    request["face_mass_flow_kg_s"] = mass
    for name, faces in g["boundary_patches"].items():
        points = g["vertices"][g["face_vertices"][faces]].copy()
        if layered:
            points[:, :, 0] = 0.
        request["boundaries"][name]["temperature_k"] = 300.+quadratic_mean(points)
    return request, g, exact


class TetraEnergyTests(unittest.TestCase):
    def solve(self, request):
        result = solve_cfd_tetra_energy(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertTrue(result["research_only"])
        self.assertFalse(result["production_qualified"])
        self.assertLessEqual(result["diagnostics"]["mixed_relative_residual"], 1e-10)
        self.assertLessEqual(result["diagnostics"]["cell_energy_relative_defect"], 1e-9)
        self.assertLessEqual(result["diagnostics"]["global_energy_relative_defect"], 1e-9)
        return result

    def test_affine_conduction_exact_means_flux_and_constant_state(self):
        request, g = base_request(box_mesh(2, shear=True))
        grad = np.array([2., -1., .5])
        request["materials"]["fluid"]["conductivity_w_mk"] = 2.5
        for key, faces in g["boundary_patches"].items():
            request["boundaries"][key]["temperature_k"] = 301.+g["face_centroids"][faces] @ grad
        result = self.solve(request)
        np.testing.assert_allclose(result["fields"]["temperature_rise_k"], 1.+g["cell_centroids"] @ grad,
                                   rtol=1e-11, atol=1e-12)
        np.testing.assert_allclose(result["fields"]["face_conductive_heat_flow_w"],
                                   -2.5*(g["face_normals"] @ grad)*g["face_areas"], rtol=1e-11, atol=1e-12)
        for bc in request["boundaries"].values():
            bc["temperature_k"] = 300.
        result = self.solve(request)
        np.testing.assert_array_equal(result["fields"]["temperature_rise_k"], 0.)
        np.testing.assert_array_equal(result["fields"]["face_conductive_heat_flow_w"], 0.)

    def test_two_solids_and_fluid_planar_contact_exact(self):
        request, g, _ = manufactured(2, layered=True)
        request["face_mass_flow_kg_s"][:] = 0.
        request["source_w_m3"][:] = 0.
        request["boundaries"] = {"left": {"type": "temperature", "temperature_k": 320.},
                                 "right": {"type": "temperature", "temperature_k": 300.},
                                 "sides": {"type": "heat_flux", "outward_heat_flux_w_m2": 0.}}
        result = self.solve(request)
        flux = 20./((1/3)/2.+1/3+(1/3)/4.)
        x = g["cell_centroids"][:, 0]
        resistance = np.minimum(x, 1/3)/2.+np.clip(x-1/3, 0., 1/3)+np.maximum(x-2/3, 0.)/4.
        np.testing.assert_allclose(result["fields"]["temperature_rise_k"], 20.-flux*resistance,
                                   rtol=1e-11, atol=1e-12)
        np.testing.assert_allclose(result["fields"]["face_conductive_heat_flow_w"],
                                   flux*g["face_normals"][:, 0]*g["face_areas"], rtol=1e-11, atol=1e-12)
        self.assertGreater(result["diagnostics"]["solid_cells"], 0)
        self.assertGreater(result["diagnostics"]["fluid_cells"], 0)

    def test_prescribed_flux_and_robin(self):
        request, g = base_request(layered_mesh(1))
        request["materials"]["fluid"]["conductivity_w_mk"] = 2.
        for right in ({"type": "heat_flux", "outward_heat_flux_w_m2": 2.},
                      {"type": "convection", "heat_transfer_coefficient_w_m2k": 4.,
                       "ambient_temperature_k": 299.5}):
            request["boundaries"] = {"left": {"type": "temperature", "temperature_k": 301.},
                                     "right": right,
                                     "sides": {"type": "heat_flux", "outward_heat_flux_w_m2": 0.}}
            result = self.solve(request)
            np.testing.assert_allclose(result["fields"]["temperature_rise_k"], 1.-g["cell_centroids"][:, 0],
                                       rtol=1e-11, atol=1e-12)

    def test_nonlinear_field_advection_conduction_refinement(self):
        for layered, levels in ((False, (2, 4, 8)), (True, (1, 2, 4))):
            errors = []
            for n in levels:
                request, g, exact = manufactured(n, layered)
                result = self.solve(request)
                actual = np.asarray(result["fields"]["temperature_rise_k"])
                errors.append(math.sqrt(np.sum(g["cell_volumes"]*(actual-exact)**2)
                                        / np.sum(g["cell_volumes"]*exact**2)))
            orders = [math.log(errors[i]/errors[i+1], 2.) for i in range(2)]
            self.assertTrue(all(v >= .8 for v in orders), (layered, errors, orders))
            self.assertLess(errors[-1], .05, (layered, errors))

    def test_temperature_reference_shift_and_flux_scaling(self):
        request, _, _ = manufactured(2)
        base = self.solve(request)
        shifted = copy.deepcopy(request); shifted["reference_temperature_k"] += 1000.
        for bc in shifted["boundaries"].values():
            bc["temperature_k"] += 1000.
        result = self.solve(shifted)
        np.testing.assert_allclose(result["fields"]["temperature_rise_k"],
                                   base["fields"]["temperature_rise_k"], rtol=1e-10, atol=1e-11)
        for scale in (1e-15, 1e15):
            scaled = copy.deepcopy(request)
            scaled["materials"]["fluid"]["conductivity_w_mk"] *= scale
            scaled["face_mass_flow_kg_s"] *= scale
            scaled["source_w_m3"] *= scale
            result = self.solve(scaled)
            np.testing.assert_allclose(result["fields"]["temperature_rise_k"],
                                       base["fields"]["temperature_rise_k"], rtol=1e-10, atol=1e-11)

    def test_rejection_and_cancellation_never_publish_fields(self):
        request, g, _ = manufactured(1, layered=True)
        mutations = [
            lambda r: r["materials"]["fluid"].__setitem__("conductivity_w_mk", 0.),
            lambda r: r["face_mass_flow_kg_s"].__setitem__(0, .3),
            lambda r: r["source_w_m3"].__setitem__(0, math.nan),
            lambda r: r["boundaries"].pop("left"),
            lambda r: r.__setitem__("extra", True),
            lambda r: r["mesh"]["cells"][0].__setitem__(0, 10**8),
            lambda r: r.__setitem__("boundaries", {k: {"type": "heat_flux", "outward_heat_flux_w_m2": 0.}
                                                 for k in r["boundaries"]}),
        ]
        for mutation in mutations:
            bad = copy.deepcopy(request); mutation(bad)
            result = solve_cfd_tetra_energy(bad)
            self.assertEqual(result["status"], "blocked", result)
            self.assertNotIn("fields", result)
        for callback in (lambda: True,):
            result = solve_cfd_tetra_energy(request, cancel_check=callback)
            self.assertEqual(result["status"], "cancelled")
            self.assertNotIn("fields", result)
        with patch("python.spike_core.cfd_tetra_energy.MAX_FIELD_BYTES", 1):
            result = solve_cfd_tetra_energy(request)
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("fields", result)
        request, _, _ = manufactured(2)
        request["cell_material_ids"][0] = "fluid2"
        request["materials"]["fluid2"] = {"phase": "fluid", "conductivity_w_mk": 1.,
                                         "specific_heat_j_kgk": 2.}
        result = solve_cfd_tetra_energy(request)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("heat capacity", str(result["issues"]))

    def test_mass_inflow_anchor_and_representability_guards(self):
        request, _, _ = manufactured(2)
        invalid_mass = copy.deepcopy(request)
        invalid_mass["face_mass_flow_kg_s"][0] += .1
        result = solve_cfd_tetra_energy(invalid_mass)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("mass balance", str(result["issues"]))
        incoming = copy.deepcopy(request)
        incoming["boundaries"]["inlet"] = {"type": "heat_flux", "outward_heat_flux_w_m2": 0.}
        result = solve_cfd_tetra_energy(incoming)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("inflow temperature", str(result["issues"]))
        unanchored = copy.deepcopy(request)
        unanchored["face_mass_flow_kg_s"][:] = 0.
        unanchored["boundaries"] = {key: {"type": "heat_flux", "outward_heat_flux_w_m2": 0.}
                                    for key in unanchored["boundaries"]}
        result = solve_cfd_tetra_energy(unanchored)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("anchor", str(result["issues"]))
        extreme = copy.deepcopy(request)
        extreme["materials"]["fluid"]["conductivity_w_mk"] = 1e-320
        result = solve_cfd_tetra_energy(extreme)
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("fields", result)
        polls = [0]
        def late_cancel():
            polls[0] += 1
            return polls[0] > 30
        result = solve_cfd_tetra_energy(request, cancel_check=late_cancel)
        self.assertEqual(result["status"], "cancelled")
        self.assertNotIn("fields", result)

    def test_nonzero_reference_throughflow_and_resource_guards(self):
        request, g = base_request(box_mesh(2))
        request["materials"]["fluid"].update(conductivity_w_mk=.6, specific_heat_j_kgk=1000.)
        request["face_mass_flow_kg_s"] = g["face_areas"]*(g["face_normals"] @ np.array([1., .5, .25]))
        for bc in request["boundaries"].values():
            bc["temperature_k"] = 350.
        result = self.solve(request)
        np.testing.assert_allclose(result["fields"]["temperature_k"], 350., rtol=0., atol=1e-8)
        self.assertGreater(np.max(abs(np.asarray(result["fields"]["face_advective_heat_flow_w"]))), 1000.)
        self.assertGreater(result["diagnostics"]["factor_nonzeros"], 0)
        for name, limit in (("MAX_FACTOR_NONZEROS", 1), ("MAX_SECONDS", -1.)):
            with patch("python.spike_core.cfd_tetra_energy."+name, limit):
                failed = solve_cfd_tetra_energy(request)
            self.assertEqual(failed["status"], "blocked", failed)
            self.assertNotIn("fields", failed)

    def test_si_scale_constant_lift_retains_absolute_mass_defect(self):
        # An independently generated millimetre sheared box, not copied CAD
        # data. The old 50 K unlifted solve failed its unchanged energy gate.
        mesh = box_mesh(2, shear=True)
        mesh["vertices"] = (np.asarray(mesh["vertices"])*.001).tolist()
        request, g = base_request(mesh)
        request["materials"]["fluid"].update(conductivity_w_mk=.6, specific_heat_j_kgk=1000.)
        mass = g["face_areas"]*(g["face_normals"] @ np.array([1e-7, 0., 0.]))
        request["face_mass_flow_kg_s"] = mass
        for bc in request["boundaries"].values():
            bc["temperature_k"] = 350.
        for perturb in (False, True):
            if perturb:
                mass[g["boundary_patches"]["inlet"][0]] *= 1.+1e-11
            result = self.solve(request)
            self.assertEqual(result["diagnostics"]["internal_temperature_lift_k"], 350.)
            self.assertEqual(result["diagnostics"]["reference_temperature_k"], 300.)
            np.testing.assert_allclose(result["fields"]["temperature_k"], 350., rtol=0., atol=1e-8)
            np.testing.assert_allclose(result["fields"]["temperature_rise_k"], 50., rtol=0., atol=1e-8)
            np.testing.assert_allclose(result["fields"]["face_advective_heat_flow_w"],
                                       mass*350000., rtol=1e-12, atol=0.)
            if perturb:
                exterior = np.flatnonzero(g["face_owners"][:, 1] < 0)
                net_mass = math.fsum(mass[exterior])
                net_heat = math.fsum(np.asarray(result["fields"]["face_conductive_heat_flow_w"])[exterior])
                self.assertGreater(result["diagnostics"]["mass_relative_defect"], 1e-12)
                # Absolute 350 K, not reference 300 K or rise 50 K, must
                # balance the nonzero accepted boundary mass defect.
                self.assertAlmostEqual(net_heat/(-350000.*net_mass), 1., delta=1e-8)
        request["face_mass_flow_kg_s"] = np.zeros_like(mass)
        result = self.solve(request)
        np.testing.assert_array_equal(result["fields"]["face_conductive_heat_flow_w"], 0.)


if __name__ == "__main__":
    unittest.main()
