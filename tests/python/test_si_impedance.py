# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import unittest
import numpy as np
from python.spike_core.si_impedance import analyze_impedance, network_impedance_report
from unittest.mock import patch
from python.spike_core.sparameters import NetworkData


def network(s, reference=50, f=None):
    s = np.asarray(s, complex)
    if s.ndim == 2:
        s = np.tile(s, (3,1,1))
    return NetworkData(np.arange(len(s), dtype=float) if f is None else np.asarray(f), s, np.ones(s.shape[1])*reference)


class ImpedanceTests(unittest.TestCase):
    def test_matched_through_not_open_circuit_z11(self):
        with patch("numpy.linalg.cond", side_effect=AssertionError("matched path must not condition")), patch("numpy.linalg.solve", side_effect=AssertionError("matched path must not solve")):
            result = analyze_impedance(network([[0,1],[1,0]]))
        self.assertEqual(result["termination_mode"], "matched")
        self.assertAlmostEqual(result["ports"][0]["trace"][0]["real_ohm"],50)

    def test_optional_summary_budget_and_delegation(self):
        oversized = network(np.zeros((17,17)))
        self.assertEqual(network_impedance_report(oversized)["status"], "unsupported_budget")
        self.assertEqual(network_impedance_report(network([[0]]))["status"], "completed")

    def test_loaded_ideal_through_sees_other_load(self):
        result = analyze_impedance(network([[0,1],[1,0]]), termination_ohm=[23,123])
        self.assertAlmostEqual(result["ports"][0]["trace"][0]["real_ohm"],123)
        self.assertAlmostEqual(result["ports"][1]["trace"][0]["real_ohm"],23)

    def test_open_short_and_match(self):
        for reflection, status, value in ((1,"open_or_pole",None),(-1,"finite",0),(0,"finite",50)):
            result = analyze_impedance(network([[reflection]]))
            row=result["ports"][0]["trace"][0]
            self.assertEqual(row["status"],status)
            self.assertEqual(row["real_ohm"],value)

    def test_loaded_nodal_resistor_oracle(self):
        y=np.array([[.02,-.01],[-.01,.03]])
        s=np.linalg.solve(np.eye(2)+50*y,np.eye(2)-50*y)
        result=analyze_impedance(network(s),termination_ohm=[50,100])
        expected=1/(y[0,0]-y[0,1]*y[1,0]/(y[1,1]+1/100))
        self.assertAlmostEqual(result["ports"][0]["trace"][0]["real_ohm"],expected)

    def test_sampled_rlc_dip_and_reactance_bracket(self):
        f=np.linspace(1e6,100e6,100)
        w=2*np.pi*f
        z=5+1j*(w*1e-6-1/(w*1e-10))
        s=((z-50)/(z+50))[:,None,None]
        result=analyze_impedance(network(s,f=f))
        candidates=result["ports"][0]["sampled_candidates"]
        dips=[c for c in candidates if c["kind"]=="sampled_magnitude_dip"]
        crossings=[c for c in candidates if c["kind"]=="reactance_sign_change"]
        resonance=1/(2*np.pi*np.sqrt(1e-6*1e-10))
        self.assertEqual(len(dips),1)
        self.assertLessEqual(crossings[0]["bracket_hz"][0],resonance)
        self.assertGreaterEqual(crossings[0]["bracket_hz"][1],resonance)
        self.assertFalse(result["physical_resonance_qualified"])

    def test_input_validation_and_cancel(self):
        n=network([[0,1],[1,0]])
        for kw in ({"termination_ohm":[0,50]}, {"ports":[0,0]}, {"ports":[True]}, {"trace_limit":2}, {"cancel_check":lambda:True}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                analyze_impedance(n,**kw)


if __name__ == "__main__":
    unittest.main()
