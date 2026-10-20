# SPDX-License-Identifier: Apache-2.0
"""Independent cylindrical conduction oracles; no board qualification claim."""
import math
import sys
import unittest
from pathlib import Path

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.integrate import quad
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"python"))
from spike_core.dc_annular_land import radial_mass, solve_annular_land
from spike_core.dc_annular_land_input import prepare


def contact(name, face, interval, current):
    return {"id": name, "attachment_id": "same-semantic-label", "face": face,
            "interval_mm": interval, "current_a": float(current)}


def request(face="r", current=1.):
    interval = [0., .1] if face == "r" else [.1, .4]
    return {"contract": "spike/dc-annular-land-request/v1",
            "radial_planes_mm": [.1, .15, .25, .4], "axial_planes_mm": [0., .04, .1],
            "conductivity_s_m": 5.8e7,
            "contacts": [contact("in", face+"_min", interval, current),
                         contact("out", face+"_max", interval, -current)]}


def spreading_request(n):
    raw = request()
    raw["radial_planes_mm"] = np.linspace(.2, .6, n+1).tolist()
    raw["axial_planes_mm"] = np.linspace(0., .2, n//2+1).tolist()
    raw["contacts"] = [contact("in", "z_min", [.2, .4], 1.),
                       contact("out", "z_min", [.4, .6], -1.)]
    return raw


def finite_volume_spreading_resistance(n):
    """Independent cell-center strong-form flux balance with Neumann half cells.

    Radial edge resistance integrates dr/(2*pi*sigma*r*dz); axial resistance
    is dz/(sigma*area). This oracle is numerically converged, not exact.
    """
    r = np.linspace(.0002, .0006, n+1)
    z = np.linspace(0., .0002, n//2+1)
    rc, zc = (r[:-1]+r[1:])/2, (z[:-1]+z[1:])/2
    area = math.pi*np.diff(r*r); dz = np.diff(z); sigma = 5.8e7
    nz = len(zc); size = n*nz
    rows, cols, values = [], [], []
    for i in range(n):
        for j in range(nz):
            a = i*nz+j
            edges = []
            if i+1 < n:
                edges.append((a+nz, 2*math.pi*sigma*dz[j]/math.log(rc[i+1]/rc[i])))
            if j+1 < nz:
                edges.append((a+1, sigma*area[i]/(zc[j+1]-zc[j])))
            for b, g in edges:
                rows.extend((a, a, b, b)); cols.extend((a, b, a, b)); values.extend((g, -g, -g, g))
    operator = coo_matrix((values, (rows, cols)), shape=(size, size)).tocsr()
    current = np.zeros(size)
    inner = area[:n//2].sum(); outer = area[n//2:].sum()
    inward = np.where(np.arange(n) < n//2, area/inner, -area/outer)
    current[np.arange(n)*nz] = inward
    phi = np.zeros(size)
    phi[1:] = spsolve(operator[1:, 1:], current[1:])
    face_phi = phi[np.arange(n)*nz]+inward*zc[0]/(sigma*area)
    return float(np.dot(inward, face_phi))


class AnnularLandTests(unittest.TestCase):
    def test_radial_and_axial_closed_forms_sign_and_scaling(self):
        for axis in ("r", "z"):
            expected = (math.log(4)/(2*math.pi*5.8e7*.0001) if axis == "r" else
                        .0001/(5.8e7*math.pi*(.0004**2-.0001**2)))
            for current in (1., -2.3):
                result = solve_annular_land(request(axis, current))
                self.assertAlmostEqual(result["joule_heat_w"]/(expected*current**2), 1., delta=2e-10)
                a, b = result["contacts"]
                self.assertAlmostEqual((a["mean_potential_v"]-b["mean_potential_v"])/(current*expected), 1., delta=2e-10)
                self.assertFalse(result["production_qualified"])
                self.assertFalse(result["complete_board_physical_volume"])
                self.assertTrue(set(a["face_ids"]).isdisjoint(b["face_ids"]))
                for cell in result["cells"]:
                    r0, r1 = np.array(cell["radial_bounds_mm"])*1e-3
                    expected_j = current/(2*math.pi*((r0+r1)/2)*.0001) if axis == "r" else current/(math.pi*(.0004**2-.0001**2))
                    jr, jz = cell["center_density_rz_a_m2"]
                    self.assertAlmostEqual((jr if axis == "r" else jz)/expected_j, 1., delta=2e-10)
                    self.assertLess(abs(jz if axis == "r" else jr), abs(expected_j)*2e-10)

    def test_radial_quadrature_against_adaptive_scalar_integration(self):
        for ratio in (1.000001, 1.2, 2.):
            r0, dr, h, sigma = .0001, .0001*(ratio-1), .00003, 5.8e7
            # Independent scalar expansion in local radial coordinate; adaptive
            # QUADPACK integration differs from production fixed Gauss nodes.
            def entry(u, i, j):
                r = r0+dr*u
                s = u*(2*r0+dr*u)/(2*r0+dr)
                f = (s-1, s)
                return f[i]*f[j]*dr/(r*2*math.pi*sigma*h)
            oracle = np.array([[quad(entry, 0., 1., args=(i, j), epsabs=1e-25, epsrel=1e-12)[0]
                                for j in range(2)] for i in range(2)])
            np.testing.assert_allclose(radial_mass(r0, dr, h, sigma), oracle, rtol=2e-13, atol=0.)

    def test_quadratic_harmonic_exact_both_components_and_means(self):
        raw = request()
        raw["axial_planes_mm"] = [.03, .07, .13]
        r0, r1, z0, z1 = .0001, .0004, .00003, .00013
        sigma, coefficient = raw["conductivity_s_m"], 10.
        area, height = math.pi*(r1*r1-r0*r0), z1-z0
        raw["contacts"] = [
            contact("ri", "r_min", [.03, .13], -4*math.pi*sigma*coefficient*r0*r0*height),
            contact("ro", "r_max", [.03, .13], 4*math.pi*sigma*coefficient*r1*r1*height),
            contact("zi", "z_min", [.1, .4], 4*sigma*coefficient*z0*area),
            contact("zo", "z_max", [.1, .4], -4*sigma*coefficient*z1*area)]
        result = solve_annular_land(raw)
        # phi=C(r^2-2z^2) is harmonic under cylindrical divergence.
        exact_heat = 4*sigma*coefficient**2*math.pi*((r1**4-r0**4)*height/2
                     +4*(r1*r1-r0*r0)*(z1**3-z0**3)/3)
        self.assertAlmostEqual(result["joule_heat_w"]/exact_heat, 1., delta=3e-10)
        first = result["cells"][0]
        def exact_mean(cell):
            a, b = np.array(cell["radial_bounds_mm"])*1e-3
            c, d = np.array(cell["axial_bounds_mm"])*1e-3
            return coefficient*((a*a+b*b)/2-2*(c*c+c*d+d*d)/3)
        gauge = first["mean_potential_v"]-exact_mean(first)
        for cell in result["cells"]:
            a, b = np.array(cell["radial_bounds_mm"])*1e-3
            c, d = np.array(cell["axial_bounds_mm"])*1e-3
            expected = [-2*sigma*coefficient*(a+b)/2, 4*sigma*coefficient*(c+d)/2]
            np.testing.assert_allclose(cell["center_density_rz_a_m2"], expected, rtol=3e-10)
            self.assertAlmostEqual(cell["mean_potential_v"]-gauge, exact_mean(cell), delta=1e-15)

    def test_independent_volume_gauss_integration_of_returned_fields(self):
        raw = spreading_request(8)
        result = solve_annular_land(raw)
        xr, wr = leggauss(32); xz, wz = leggauss(3)
        integrated = 0.
        for cell in result["cells"]:
            r0, r1 = np.array(cell["radial_bounds_mm"])*1e-3
            z0, z1 = np.array(cell["axial_bounds_mm"])*1e-3
            r = (r0+r1)/2+(r1-r0)*xr/2
            t = (xz+1)/2; s = (r*r-r0*r0)/(r1*r1-r0*r0)
            # Reconstruct from exported endpoint component data, not kernel mass.
            n0, n1 = cell["radial_current_numerator_endpoint_a"]
            e0, e1 = cell["axial_component_endpoint_density_a_m2"]
            jr = (n0*(1-s)+n1*s)/(2*math.pi*r*(z1-z0))
            jz = e0*(1-t)+e1*t
            energy = float(np.sum((jr[:, None]**2+jz[None, :]**2)*r[:, None]
                                 *wr[:, None]*wz[None, :])
                           *2*math.pi*(r1-r0)*(z1-z0)/(4*raw["conductivity_s_m"]))
            self.assertAlmostEqual(energy/cell["joule_heat_w"], 1., delta=2e-12)
            integrated += energy
        self.assertAlmostEqual(integrated/result["signed_terminal_work_w"], 1., delta=2e-10)

    def test_partial_same_face_spreading_against_converged_finite_volume(self):
        reference64 = finite_volume_spreading_resistance(64)
        reference128 = finite_volume_spreading_resistance(128)
        self.assertLess(abs(reference64/reference128-1), .002)
        errors = []
        for n in (4, 8, 16):
            result = solve_annular_land(spreading_request(n))
            errors.append(abs(result["joule_heat_w"]/reference128-1))
        self.assertLess(errors[-1], .02)
        self.assertLess(errors[-1], errors[0])
        self.assertTrue(all(b < a for a, b in zip(errors, errors[1:])))

    def test_strict_admission_and_underflow_stamping(self):
        cases = []
        for field, value in (("radial_planes_mm", [0., .1, .2]),
                             ("radial_planes_mm", [.1, .3, .4]),
                             ("conductivity_s_m", float("nan")), ("conductivity_s_m", True)):
            raw = request(); raw[field] = value; cases.append(raw)
        raw = request(); raw["contacts"][1]["face"] = "r_min"; cases.append(raw)
        raw = request(); raw["contacts"][0]["interval_mm"] = [0., .05]; cases.append(raw)
        raw = request(); raw["contacts"][1]["current_a"] = -.9; cases.append(raw)
        raw = request(); raw["extra"] = True; cases.append(raw)
        raw = request(); raw["radial_planes_mm"] = np.linspace(.1, .4, 65).tolist()
        raw["axial_planes_mm"] = np.linspace(0., .1, 65).tolist(); cases.append(raw)
        for raw in cases:
            with self.assertRaises(ValueError):
                solve_annular_land(raw)
        tiny = request(current=1e-300)
        data = prepare(tiny)
        self.assertEqual(np.count_nonzero(data["prescribed"]), 4)
        self.assertAlmostEqual(float(np.abs(data["prescribed"]).sum())/2e-300, 1., delta=1e-14)
        with self.assertRaises(ValueError):  # nonzero-current heat cannot silently underflow
            solve_annular_land(tiny)
        zero = solve_annular_land(request(current=0.))
        self.assertEqual(zero["joule_heat_w"], 0.)

    def test_patch_order_and_axial_translation_preserve_solution(self):
        raw = spreading_request(8)
        baseline = solve_annular_land(raw)
        raw["contacts"].reverse()
        raw["axial_planes_mm"] = [value+10. for value in raw["axial_planes_mm"]]
        shifted = solve_annular_land(raw)
        self.assertAlmostEqual(shifted["joule_heat_w"]/baseline["joule_heat_w"], 1., delta=2e-11)
        np.testing.assert_allclose(shifted["face_potential_v"], baseline["face_potential_v"], rtol=2e-11, atol=1e-16)
        # Returned evidence is detached from the caller's mutable request.
        raw["contacts"][0]["current_a"] = -9.
        self.assertEqual(shifted["source_request"]["contacts"][0]["current_a"], -1.)


if __name__ == "__main__":
    unittest.main()
