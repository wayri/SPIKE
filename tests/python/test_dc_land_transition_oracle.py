# SPDX-License-Identifier: Apache-2.0
"""Independent same-face cosine oracle and 3-D field/work verification.

Original separation derivation, using the Laplace/Ohm foundations in MIT
Electromagnetic Fields and Energy sections 5.4 and 7.2 (reviewed 2026-10-21).
No solver mass, hybrid matrix, or assembly code supplies expected values.
"""
import math
import unittest

import numpy as np

from python.spike_core.dc_land_transition import solve_land_transition


CONTRACT = "spike/dc-land-transition-request/v1"


def same_face_series_reference(cutoff=4096):
    """Positive resistance partial sum and conservative omitted-tail bound.

    On z=0 of a 1 x 1 x 0.2 mm prism, inject I uniformly through the left
    x-half and withdraw I through the right half, each covering the full y.
    All other faces are insulating. For k=m*pi/Lx the bottom flux coefficient
    is g_m=8I*sin(m*pi/2)/(Lx*Ly*m*pi). The potential is proportional to
    cos(k*x)*cosh(k*(Lz-z))/(sigma*k*sinh(k*Lz)). Integrating terminal work
    gives R=32*Lx/(sigma*Lx*Ly*pi^3) sum_{odd m} coth(k*Lz)/m^3.

    For m>N, coth(k*Lz)<=coth(pi*(N+1)*Lz/Lx) and the sum over *all*
    m>N of 1/m^3 is <= integral_N^infinity x^-3 dx=1/(2*N^2).
    This bounds the positive omitted tail conservatively. It is an analytic
    truncation bound; ordinary floating evaluation is not interval arithmetic.
    """
    lx, ly, lz, sigma = .001, .001, .0002, 5.8e7
    factor = 32*lx/(sigma*lx*ly*math.pi**3)
    partial = factor*math.fsum(1/(math.tanh(m*math.pi*lz/lx)*m**3)
                               for m in range(1, cutoff+1, 2))
    tail = factor/(2*cutoff**2*math.tanh((cutoff+1)*math.pi*lz/lx))
    return partial, tail


def same_face_request(nx):
    return {"contract": CONTRACT,
        "axes_mm": [np.linspace(0, 1, nx+1).tolist(), [0., 1.],
                    np.linspace(0, .2, nx//2+1).tolist()],
        "conductivity_s_m": 5.8e7,
        "contacts": [
            {"id": "source", "attachment_id": "same-semantic-node", "face": "z_min",
             "rectangle_mm": [[0., .5], [0., 1.]], "current_a": 1.},
            {"id": "sink", "attachment_id": "same-semantic-node", "face": "z_min",
             "rectangle_mm": [[.5, 1.], [0., 1.]], "current_a": -1.}]}


def gauss_field_integrals(result, sigma):
    """Integrate returned component fields in SI coordinates independently."""
    abscissa, weights = np.polynomial.legendre.leggauss(2)
    volume_total, heat_total = 0., 0.
    cell_integrals = []
    for cell in result["cells"]:
        bounds = np.asarray(cell["bounds_mm"])*1e-3
        lengths = bounds[:, 1]-bounds[:, 0]
        endpoint = np.asarray(cell["component_endpoint_density_a_m2"])
        volume, heat = 0., 0.
        for i, x in enumerate(abscissa):
            for j, y in enumerate(abscissa):
                for k, z in enumerate(abscissa):
                    fraction = (np.array([x, y, z])+1)/2
                    field = endpoint[:, 0]*(1-fraction)+endpoint[:, 1]*fraction
                    dv = math.prod(lengths)*weights[i]*weights[j]*weights[k]/8
                    volume += dv
                    heat += float(field@field)*dv/sigma
        cell_integrals.append((volume, heat))
        volume_total += volume; heat_total += heat
    return volume_total, heat_total, cell_integrals


class LandTransitionOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = [solve_land_transition(same_face_request(nx)) for nx in (4, 8, 16)]

    def test_independent_same_face_series_truncation(self):
        previous, previous_bound = same_face_series_reference(128)
        for cutoff in (512, 2048, 4096):
            actual, bound = same_face_series_reference(cutoff)
            self.assertGreater(actual, previous)
            self.assertLess(actual-previous, previous_bound)
            self.assertLess(bound, previous_bound)
            previous, previous_bound = actual, bound
        self.assertLess(previous_bound/previous, 2e-8)

    def test_three_level_resistance_and_heat_convergence(self):
        partial, tail = same_face_series_reference()
        errors, heat_errors = [], []
        for result in self.results:
            source, sink = result["contacts"]
            resistance = source["mean_potential_v"]-sink["mean_potential_v"]
            # Test both ends of the independent continuum-reference interval.
            errors.append(max(abs(resistance/exact-1) for exact in (partial, partial+tail)))
            heat_errors.append(max(abs(result["joule_heat_w"]/exact-1) for exact in (partial, partial+tail)))
            self.assertEqual(source["attachment_id"], sink["attachment_id"])
            self.assertFalse(set(source["face_ids"]) & set(sink["face_ids"]))
            self.assertAlmostEqual(source["area_m2"], .5e-6, delta=1e-20)
            self.assertAlmostEqual(sink["area_m2"], .5e-6, delta=1e-20)
            self.assertAlmostEqual(result["signed_terminal_work_w"], resistance, delta=1e-15)
            self.assertFalse(result["complete_board_physical_volume"])
            self.assertFalse(result["production_qualified"])
        # Frozen before the first run: finest <2%, improving over coarsest.
        self.assertLess(errors[-1], .02)
        self.assertLess(errors[-1], errors[0])
        self.assertLess(heat_errors[-1], .02)
        self.assertLess(heat_errors[-1], heat_errors[0])
        self.assertEqual([len(r["cells"]) for r in self.results], [8, 32, 128])

    def test_returned_variable_field_integrates_to_cell_and_terminal_heat(self):
        for result in self.results:
            volume, heat, cells = gauss_field_integrals(result, 5.8e7)
            self.assertAlmostEqual(volume/.0000000002, 1., places=13)
            self.assertAlmostEqual(volume/result["total_volume_m3"], 1., places=13)
            self.assertAlmostEqual(heat/result["joule_heat_w"], 1., places=12)
            self.assertAlmostEqual(heat/result["signed_terminal_work_w"], 1., places=9)
            for cell, (v, p) in zip(result["cells"], cells):
                self.assertAlmostEqual(v/cell["volume_m3"], 1., places=13)
                self.assertAlmostEqual(p, cell["joule_heat_w"], delta=1e-12*heat)
                self.assertAlmostEqual(cell["mean_joule_density_w_m3"]*v, p, delta=1e-12*heat)
                lengths = np.diff(np.asarray(cell["bounds_mm"])*1e-3, axis=1).ravel()
                endpoints = np.asarray(cell["component_endpoint_density_a_m2"])
                areas = np.array([lengths[1]*lengths[2], lengths[0]*lengths[2], lengths[0]*lengths[1]])
                signed_face_integrals = (endpoints*np.array([-1., 1.])*areas[:, None]).ravel()
                np.testing.assert_allclose(signed_face_integrals, cell["outward_face_current_a"], atol=1e-13, rtol=1e-11)

    def test_all_three_affine_components_from_harmonic_quadratic_potential(self):
        # phi=ax^2+by^2+cz^2, a+b+c=0: exact div J=0, J=-sigma grad phi.
        # Constant normal flux on each full boundary face makes admissible
        # Neumann data; all three nonconstant components lie in cuboid RT0.
        coefficients = np.array([1000., 2000., -3000.])  # V/m2
        sigma, length = 2.5e7, .001
        axes = [[-.5, -.25, 0., .5], [-.5, 0., .125, .5], [-.5, -.1, .5]]
        contacts = []
        for axis in range(3):
            for side, normal in (("min", -1.), ("max", 1.)):
                coordinate = normal*length/2
                current = float(2*sigma*coefficients[axis]*coordinate*normal*length**2)
                name = "xyz"[axis]+"_"+side
                contacts.append({"id": name, "attachment_id": "all-six-share-a-label", "face": name,
                    "rectangle_mm": [[-.5, .5], [-.5, .5]], "current_a": current})
        result = solve_land_transition({"contract": CONTRACT, "axes_mm": axes,
                                       "conductivity_s_m": sigma, "contacts": contacts})
        gauge = result["contacts"][0]["mean_potential_v"]-coefficients[0]*length**2/6
        for cell in result["cells"]:
            bounds = np.asarray(cell["bounds_mm"])*1e-3
            expected = -2*sigma*coefficients[:, None]*bounds
            np.testing.assert_allclose(cell["component_endpoint_density_a_m2"], expected,
                                       rtol=2e-10, atol=1e-3)
            square_means = (bounds[:, 0]**2+bounds[:, 0]*bounds[:, 1]+bounds[:, 1]**2)/3
            self.assertAlmostEqual(cell["mean_potential_v"], float(coefficients@square_means)+gauge,
                                   delta=1e-12)
            for axis in range(3):
                for side in (0, 1):
                    face_means = square_means.copy(); face_means[axis] = bounds[axis, side]**2
                    expected_trace = float(coefficients@face_means)+gauge
                    fid = cell["face_ids"][2*axis+side]
                    self.assertAlmostEqual(result["face_potential_v"][fid], expected_trace, delta=1e-12)
        # Exact full-face averages: phi_bar(axis)=coefficient_axis*L^2/6.
        reference_contact = result["contacts"][0]
        for index, contact in enumerate(result["contacts"]):
            expected_difference = (coefficients[index//2]-coefficients[0])*length**2/6
            self.assertAlmostEqual(contact["mean_potential_v"]-reference_contact["mean_potential_v"],
                                   expected_difference, delta=1e-12)
        exact_heat = sigma*length**5*float(coefficients@coefficients)/3
        self.assertAlmostEqual(result["joule_heat_w"]/exact_heat, 1., places=10)
        volume, heat, _ = gauss_field_integrals(result, sigma)
        self.assertAlmostEqual(volume/length**3, 1., places=13)
        self.assertAlmostEqual(heat/exact_heat, 1., places=10)


if __name__ == "__main__":
    unittest.main()
