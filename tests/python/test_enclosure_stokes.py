# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import copy
import unittest
import numpy as np
from python.spike_core.enclosure_stokes import CONTRACT, solve_enclosure_stokes, _assemble


def fixture(shape=(4, 4, 3)):
    return {"contract": CONTRACT, "shape": list(shape), "spacing_m": [.1, .1, .1],
            "fluid_mask": np.ones(shape, dtype=bool).tolist(),
            "body_force_n_m3": np.zeros(shape + (3,)).tolist(),
            "dynamic_viscosity_pa_s": 1., "density_kg_m3": 1.}


class EnclosureStokesTests(unittest.TestCase):
    def test_zero_and_conservative_force(self):
        for vector in ([0., 0., 0.], [1., -2., .5]):
            q = fixture()
            q["body_force_n_m3"] = np.broadcast_to(vector, (4, 4, 3, 3)).tolist()
            r = solve_enclosure_stokes(q)
            self.assertEqual(r["status"], "completed", r)
            self.assertLess(max(np.max(np.abs(v)) for v in r["fields"]["face_velocity_m_s"]), 1e-14)
            pressure = np.asarray(r["fields"]["pressure_pa"])
            for axis in range(3):
                np.testing.assert_allclose(np.diff(pressure, axis=axis), .1 * vector[axis], atol=1e-14)

    def test_recirculation_and_power_identity(self):
        q = fixture()
        force = np.zeros((4, 4, 3, 3))
        force[..., 0] = np.arange(4)[None, :, None] * .1
        q["body_force_n_m3"] = force.tolist()
        r = solve_enclosure_stokes(q)
        self.assertEqual(r["status"], "completed", r)
        v = [np.asarray(a) for a in r["fields"]["face_velocity_m_s"]]
        self.assertGreater(v[0].max(), 1e-6)
        self.assertLess(v[0].min(), -1e-6)
        div = sum(np.diff(a, axis=i) / .1 for i, a in enumerate(v))
        self.assertLess(np.max(np.abs(div)), 1e-14)
        d = r["diagnostics"]
        self.assertAlmostEqual(d["force_work_w"], d["viscous_dissipation_w"], delta=1e-16)

    def test_obstacles_disconnected_and_isolated(self):
        q = fixture((5, 4, 3))
        mask = np.ones((5, 4, 3), bool)
        mask[2] = False
        mask[0, 0, 0] = False
        q["fluid_mask"] = mask.tolist()
        r = solve_enclosure_stokes(q)
        self.assertEqual(r["status"], "completed", r)
        self.assertEqual(r["diagnostics"]["fluid_components"], 2)
        self.assertTrue(np.all(np.asarray(r["fields"]["face_velocity_m_s"][0])[2:4] == 0))
        q = fixture((1, 1, 1))
        r = solve_enclosure_stokes(q)
        self.assertEqual(r["status"], "completed", r)
        self.assertEqual(r["diagnostics"]["velocity_unknowns"], 0)

    def test_discrete_manufactured_saddle_identity(self):
        shape = (3, 3, 2)
        h = np.array([.1, .2, .3])
        cells, faces, a, d, _, gauges = _assemble(shape, h, np.ones(shape, bool), np.zeros(shape + (3,)), 2., None)
        np.testing.assert_allclose(a.toarray(), a.T.toarray(), atol=0)
        self.assertGreater(np.linalg.eigvalsh(a.toarray()).min(), 0)
        self.assertEqual(np.linalg.matrix_rank(d.toarray()), len(cells)-len(gauges))
        # A four-face circulation is exactly divergence-free on anisotropic cells.
        v = np.zeros(len(faces))
        mapping = {(axis, c): i for i, (axis, c, _) in enumerate(faces)}
        v[mapping[(0, (0, 0, 0))]] = h[0]
        v[mapping[(1, (1, 0, 0))]] = h[1]
        v[mapping[(0, (0, 1, 0))]] = -h[0]
        v[mapping[(1, (0, 0, 0))]] = -h[1]
        np.testing.assert_allclose(d @ v, 0, atol=1e-15)
        p = np.arange(len(cells)) * .01
        f = a @ v - d.T @ p
        self.assertAlmostEqual(float(v @ f), float(v @ (a @ v)), places=12)

    def test_forced_obstacle_faces_and_power(self):
        q = fixture((6, 5, 4))
        mask = np.ones((6, 5, 4), bool)
        mask[2:4, 2, :] = False
        q["fluid_mask"] = mask.tolist()
        force = np.zeros((6, 5, 4, 3))
        force[..., 0] = np.arange(5)[None, :, None] * .1
        q["body_force_n_m3"] = force.tolist()
        r = solve_enclosure_stokes(q)
        self.assertEqual(r["status"], "completed", r)
        fields = [np.asarray(a) for a in r["fields"]["face_velocity_m_s"]]
        self.assertGreater(max(np.max(np.abs(a)) for a in fields), 1e-6)
        for axis, field in enumerate(fields):
            for index in np.ndindex(field.shape):
                left, right = list(index), list(index)
                left[axis] -= 1
                if not (0 <= left[axis] and right[axis] < mask.shape[axis]
                        and mask[tuple(left)] and mask[tuple(right)]):
                    self.assertEqual(field[index], 0.)
        divergence = sum(np.diff(a, axis=i) / .1 for i, a in enumerate(fields))
        self.assertLess(np.max(np.abs(divergence[mask])), 1e-13)
        d = r["diagnostics"]
        self.assertGreater(d["viscous_dissipation_w"], 0)
        self.assertAlmostEqual(d["force_work_w"], d["viscous_dissipation_w"], delta=1e-15)

    def test_continuum_manufactured_second_order_velocity(self):
        # psi=amp*sin(pi*x)^2*sin(pi*y)^2*sin(pi*z), u=(psi_y,-psi_x,0).
        # Exact divergence-free no-slip solution with p=0; f=-Laplacian(u).
        errors = []
        for n in (4, 8, 12):
            h, p, amp = 1/n, np.pi, 1e-4
            centers = (np.arange(n)+.5)*h
            x,y,z = np.meshgrid(centers,centers,centers,indexing="ij")
            force = np.zeros((n,n,n,3))
            force[...,0] = -amp*p**3*np.sin(2*p*y)*np.sin(p*z)*(2*np.cos(2*p*x)-5*np.sin(p*x)**2)
            force[...,1] = amp*p**3*np.sin(2*p*x)*np.sin(p*z)*(2*np.cos(2*p*y)-5*np.sin(p*y)**2)
            q = fixture((n,n,n))
            q["spacing_m"] = [h]*3
            q["body_force_n_m3"] = force.tolist()
            r = solve_enclosure_stokes(q)
            self.assertEqual(r["status"], "completed", r)
            x,y,z = np.meshgrid(np.arange(n+1)*h,centers,centers,indexing="ij")
            exact = amp*p*np.sin(p*x)**2*np.sin(2*p*y)*np.sin(p*z)
            actual = np.asarray(r["fields"]["face_velocity_m_s"][0])
            x,y,z = np.meshgrid(centers,np.arange(n+1)*h,centers,indexing="ij")
            exact_y = -amp*p*np.sin(2*p*x)*np.sin(p*y)**2*np.sin(p*z)
            actual_y = np.asarray(r["fields"]["face_velocity_m_s"][1])
            actual_z = np.asarray(r["fields"]["face_velocity_m_s"][2])
            errors.append(np.sqrt((np.linalg.norm(actual-exact)**2 + np.linalg.norm(actual_y-exact_y)**2
                + np.linalg.norm(actual_z)**2)
                / (np.linalg.norm(exact)**2 + np.linalg.norm(exact_y)**2)))
        self.assertLess(errors[-1], .005)
        for i, ratio in enumerate((2.,1.5)):
            self.assertGreater(np.log(errors[i]/errors[i+1])/np.log(ratio), 1.8)

    def test_invalid_resource_finite_and_inertia(self):
        q = fixture()
        variants = []
        for key, value in (("shape", [64,64,64]), ("spacing_m", [0,1,1]),
                           ("density_kg_m3", True), ("dynamic_viscosity_pa_s", 10**1000),
                           ("fluid_mask", np.zeros((4,4,3), bool).tolist()), ("extra", 1)):
            v = copy.deepcopy(q)
            v[key] = value
            variants.append(v)
        for value in (float("nan"), float("inf"), 1e200):
            v = copy.deepcopy(q)
            v["body_force_n_m3"][1][1][1][0] = value
            variants.append(v)
        for v in variants:
            r = solve_enclosure_stokes(v)
            self.assertEqual(r["status"], "blocked", r)
            self.assertNotIn("fields", r)

    def test_cancelled_discards_fields(self):
        r = solve_enclosure_stokes(fixture(), cancel_check=lambda: True)
        self.assertEqual(r["status"], "cancelled")
        self.assertNotIn("fields", r)


if __name__ == "__main__":
    unittest.main()
