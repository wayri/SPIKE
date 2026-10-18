# SPDX-License-Identifier: Apache-2.0
"""Independent attenuated-wave/PDE and finite-pulse quadrature references.

Preset V/I2e-10SI+1e-9relative; localdensity1e-14J/m+1e-9relative;
finite-pulse energy1e-20J+1e-9relative. No arbitrary dispersive-loss oracle.
"""
from copy import deepcopy
from fractions import Fraction
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad

from python.spike_core import distortionless_line_transient as lossy
from tests.python.test_lossless_line_transient import request as line_request, boundary, source_value


def request(rate=1e7, left_r=25., right_r=100.):
    return {"contract": lossy.REQUEST_CONTRACT, "line_request": line_request(left_r, right_r), "attenuation_rate_per_s": rate}


def geometric(req, time, position):
    source = req["line_request"]; rate = req["attenuation_rate_per_s"]
    z = math.sqrt(source["inductance_h_per_m"]/source["capacitance_f_per_m"])
    tau = source["length_m"]*math.sqrt(source["inductance_h_per_m"]*source["capacitance_f_per_m"])
    left, right = source["left_boundary"], source["right_boundary"]
    gl, gr = [(b["resistance_ohm"]-z)/(b["resistance_ohm"]+z) for b in (left, right)]
    al, ar = [z/(b["resistance_ohm"]+z) for b in (left, right)]
    forward, backward = [], []
    for m in range(int(time/tau)+2):
        factor = (gl*gr)**m
        forward.append(factor*(al*math.exp(-rate*(2*m+position)*tau)*source_value(time-(2*m+position)*tau, left)
                              +gl*ar*math.exp(-rate*(2*m+1+position)*tau)*source_value(time-(2*m+1+position)*tau, right)))
        backward.append(factor*(ar*math.exp(-rate*(2*m+1-position)*tau)*source_value(time-(2*m+1-position)*tau, right)
                               +gr*al*math.exp(-rate*(2*m+2-position)*tau)*source_value(time-(2*m+2-position)*tau, left)))
    return math.fsum(forward), math.fsum(backward)


def gauss(a, b, count=8):
    nodes, weights = np.polynomial.legendre.leggauss(count)
    return .5*(a+b)+.5*(b-a)*nodes, .5*(b-a)*weights


class DistortionlessTests(unittest.TestCase):
    def assertVI(self, actual, expected):
        self.assertAlmostEqual(actual, expected, delta=2e-10+1e-9*abs(expected))

    def assertEnergy(self, actual, expected):
        self.assertAlmostEqual(actual, expected, delta=1e-20+1e-9*abs(expected))

    def check_fields(self, req, out):
        source, rate = req["line_request"], req["attenuation_rate_per_s"]
        z = out["characteristic_impedance_ohm"]
        for point in out["points"]:
            for probe in point["probe_values"]:
                f, b = geometric(req, point["time_s"], probe["fractional_position"])
                v, i = f+b, (f-b)/z
                for field, expected in (("forward_voltage_v", f), ("backward_voltage_v", b), ("voltage_v", v),
                                        ("current_left_to_right_a", i), ("transported_power_w", (f*f-b*b)/z)):
                    self.assertVI(probe[field], expected)
                density = source["capacitance_f_per_m"]*(f*f+b*b)
                self.assertAlmostEqual(probe["energy_density_j_per_m"], density, delta=1e-14+1e-9*abs(density))
                self.assertVI(probe["conductor_loss_w_per_m"], rate*source["inductance_h_per_m"]*i*i)
                self.assertVI(probe["dielectric_loss_w_per_m"], rate*source["capacitance_f_per_m"]*v*v)
                self.assertVI(probe["total_loss_w_per_m"], 2*rate*density)
            for index, name in enumerate(("left", "right")):
                f, b = geometric(req, point["time_s"], index)
                row = point["boundary_values"][name]; into = (f-b)/z*(1 if index == 0 else -1)
                self.assertVI(row["voltage_v"], f+b); self.assertVI(row["current_into_line_a"], into)
                self.assertVI(row["source_voltage_v"]-row["voltage_v"]-source[name+"_boundary"]["resistance_ohm"]*into, 0.)

    def test_zero_loss_exact_parent_points_provenance_and_nonzero_coefficients(self):
        req = request(0.); before = deepcopy(req)
        actual = lossy.run_distortionless_line_transient(req)
        parent = lossy.lossless.run_lossless_line_transient(req["line_request"])
        self.assertEqual(req, before); self.assertEqual(actual["source_request"], req)
        self.assertEqual(actual["input_digest"], lossy.sampling._digest(req))
        stripped = deepcopy(actual["points"])
        for point in stripped:
            for probe in point["probe_values"]:
                for field in ("conductor_loss_w_per_m", "dielectric_loss_w_per_m", "total_loss_w_per_m"):
                    self.assertEqual(probe.pop(field), 0.)
        self.assertEqual(stripped, parent["points"])
        req = request(); out = lossy.run_distortionless_line_transient(req)
        self.assertVI(out["resistance_ohm_per_m"], 2.5)
        self.assertVI(out["conductance_s_per_m"], .001)
        self.assertVI(out["attenuation_neper_per_m"], .05)
        self.assertVI(out["one_way_voltage_attenuation"], math.exp(-.25))

    def test_matched_ramp_analytic_attenuation_and_smooth_pde_identity(self):
        req = request(left_r=50., right_r=50.)
        req["line_request"]["output_times_s"] = [5e-9, 15e-9, 30e-9]
        req["line_request"]["probes"] = [{"id": "smooth", "fractional_position": .2}]
        out = lossy.run_distortionless_line_transient(req); self.check_fields(req, out)
        for point in out["points"]:
            self.assertEqual(point["probe_values"][0]["backward_voltage_v"], 0.)
        # At x=1m,t=15ns the ramp reaches its plateau endpoint. Use a
        # separate strictly interior ramp time to test analytic PDE derivatives.
        req["line_request"]["output_times_s"] = [10e-9]
        probe = lossy.run_distortionless_line_transient(req)["points"][0]["probe_values"][0]
        voltage = probe["voltage_v"]; dvdt = .5*math.exp(-.05)/10e-9
        dvdx = -.05*voltage-dvdt/2e8
        du_dt = 2*100e-12*voltage*dvdt
        dp_dx = 2*voltage*dvdx/50.
        self.assertAlmostEqual(du_dt+dp_dx, -probe["total_loss_w_per_m"], delta=1e-12)

    def test_geometric_multiple_echoes_both_drives_and_ideal_source_boundaries(self):
        for rleft, rright in ((25., 100.), (0., 0.)):
            req = request(left_r=rleft, right_r=rright)
            req["line_request"]["right_boundary"] = boundary(rright, [(0., 0.), (7e-9, -.7), (40e-9, .4), (200e-9, -.2)])
            out = lossy.run_distortionless_line_transient(req); self.check_fields(req, out)
            self.assertTrue(all(p["total_loss_w_per_m"] >= 0 for row in out["points"] for p in row["probe_values"]))

    def test_finite_pulse_source_storage_terminal_and_distributed_heat_balance(self):
        req = request(left_r=50., right_r=50.); source = req["line_request"]
        source["left_boundary"] = boundary(50., [(0., 0.), (1e-9, 2.), (2e-9, 0.), (30e-9, 0.)])
        source["right_boundary"] = boundary(50., [(0., 0.), (30e-9, 0.)])
        # Resolve all integrals from actual kernel samples using independent
        # Gaussian quadrature. t_final26ns leaves the pulse tail inside and
        # its leading half outside, so both storage and outflow are nonzero.
        nodes, weights = gauss(4.8, 5.)
        stored_req = deepcopy(req); stored_req["line_request"]["probes"] = [{"id": str(i), "fractional_position": x/5} for i, x in enumerate(nodes)]
        stored_req["line_request"]["output_times_s"] = [26e-9]
        stored = sum(w*p["energy_density_j_per_m"] for w, p in zip(weights, lossy.run_distortionless_line_transient(stored_req)["points"][0]["probe_values"]))
        work_source = work_injected = source_heat = outflow = distributed_heat = 0.
        for start, end in ((0., 1.), (1., 2.), (25., 26.)):
            tnodes, tweights = gauss(start, end)
            sample = deepcopy(req); sample["line_request"]["output_times_s"] = list(tnodes*1e-9)
            result = lossy.run_distortionless_line_transient(sample)
            for weight, point in zip(tweights*1e-9, result["points"]):
                left, right = point["boundary_values"]["left"], point["boundary_values"]["right"]
                work_source += weight*left["source_voltage_v"]*left["current_into_line_a"]
                work_injected += weight*left["voltage_v"]*left["current_into_line_a"]
                source_heat += weight*left["resistor_power_w"]
                outflow -= weight*right["voltage_v"]*right["current_into_line_a"]
        for start, end in ((0., 1.), (1., 2.)):
            snodes, sweights = gauss(start, end, 6)
            for emission_ns, sweight in zip(snodes, sweights*1e-9):
                xmax = min(5., (26-emission_ns)*.2)
                xnodes, xweights = gauss(0., xmax)
                sample = deepcopy(req)
                sample["line_request"]["probes"] = [{"id": str(i), "fractional_position": x/5} for i, x in enumerate(xnodes)]
                sample["line_request"]["output_times_s"] = list((emission_ns+xnodes/0.2)*1e-9)
                result = lossy.run_distortionless_line_transient(sample)
                distributed_heat += sweight*sum(weight*point["probe_values"][i]["total_loss_w_per_m"] for i, (weight, point) in enumerate(zip(xweights, result["points"])))
        self.assertGreater(stored, 0.); self.assertGreater(outflow, 0.); self.assertGreater(distributed_heat, 0.)
        self.assertEnergy(work_injected, 2e-9/(3*50))
        self.assertEnergy(work_source, source_heat+stored+outflow+distributed_heat)
        self.assertEnergy(work_injected, stored+outflow+distributed_heat)
        # Independent characteristic-path integral of loss for each emitted
        # pulse slice; includes its finite distance before t_final.
        def lost(ns):
            triangle = ns if ns < 1 else 2-ns
            xmax = min(5., (26-ns)*.2)
            return triangle**2/50*(1-math.exp(-.1*xmax))*1e-9
        reference_heat = sum(quad(lost, a, b, epsabs=1e-24)[0] for a, b in ((0., 1.), (1., 2.)))
        self.assertEnergy(distributed_heat, reference_heat)

    def test_time_length_units_and_exact_shared_sample_refinement(self):
        req = request(); base = lossy.run_distortionless_line_transient(req)
        refined = deepcopy(req); refined["line_request"]["output_times_s"] = sorted(set(req["line_request"]["output_times_s"]+[8e-9, 47e-9, 163e-9]))
        out = lossy.run_distortionless_line_transient(refined); shared = {p["time_s"]: p for p in out["points"]}
        for point in base["points"]: self.assertEqual(shared[point["time_s"]], point)
        scaled = deepcopy(req); factor = 1000.
        scaled["attenuation_rate_per_s"] /= factor
        scaled["line_request"]["inductance_h_per_m"] *= factor; scaled["line_request"]["capacitance_f_per_m"] *= factor
        for name in ("left_boundary", "right_boundary"):
            for p in scaled["line_request"][name]["voltage_points"]: p["time_s"] *= factor
        scaled["line_request"]["output_times_s"] = [t*factor for t in req["line_request"]["output_times_s"]]
        out = lossy.run_distortionless_line_transient(scaled)
        for row, expected in zip(out["points"], base["points"]):
            for a, b in zip(row["probe_values"], expected["probe_values"]):
                for field in ("voltage_v", "current_left_to_right_a", "conductor_loss_w_per_m", "dielectric_loss_w_per_m", "total_loss_w_per_m"):
                    self.assertVI(a[field], b[field])
                self.assertAlmostEqual(a["energy_density_j_per_m"], factor*b["energy_density_j_per_m"], delta=1e-14+1e-9*abs(factor*b["energy_density_j_per_m"]))
        longer = deepcopy(req); longer["line_request"]["length_m"] *= 2
        self.assertVI(lossy.run_distortionless_line_transient(longer)["one_way_voltage_attenuation"], base["one_way_voltage_attenuation"]**2)

    def test_invalid_loss_exponent_precision_resources_and_cancellation(self):
        for rate in (-1., True, float("inf"), 1e-320, 1e-20, 1e308):
            req = request(rate)
            with self.assertRaises(lossy.DistortionlessLineTransientError): lossy.run_distortionless_line_transient(req)
        req = request(); req["extra"] = 0
        with self.assertRaises(lossy.DistortionlessLineTransientError): lossy.run_distortionless_line_transient(req)
        for name in ("_MAX_WORK", "_MAX_RESULT_BYTES"):
            with patch.object(lossy, name, 1), patch.object(lossy.lossless, "_value", side_effect=AssertionError("preflight before evaluation")):
                with self.assertRaises(lossy.DistortionlessLineTransientError): lossy.run_distortionless_line_transient(request())
        for rate, time in ((1e308, Fraction(10)), (1e-300, Fraction(1e-300)), (1000., Fraction(1)), (1e-30, Fraction(1))):
            with self.assertRaises((lossy.DistortionlessLineTransientError, OverflowError)):
                lossy._attenuation(rate, time)
        calls = []; lossy.run_distortionless_line_transient(request(), cancel_check=lambda: calls.append(1) or False)
        for threshold in (1, len(calls)//2, len(calls)):
            seen = []
            def cancel(): seen.append(1); return len(seen) >= threshold
            with self.assertRaises(lossy.DistortionlessLineTransientError) as caught:
                lossy.run_distortionless_line_transient(request(), cancel_check=cancel)
            self.assertIn("CANCELLED", caught.exception.code)


if __name__ == "__main__": unittest.main()
