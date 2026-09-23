# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import copy
import unittest
import numpy as np
from python.spike_core.si_workflow import run_si_workflow,REQUEST
from python.spike_core.sparameters import touchstone_text
from tests.python.test_si_resonance import fixture


def request():
    f,z,_=fixture("series_rlc",10,1025)
    s=np.zeros((len(f),2,2),complex)
    s[:,0,0]=(z-50)/(z+50)
    return {"contract":REQUEST,"channel":{"kind":"touchstone","name":"rlc.s2p","text":touchstone_text(f,s)},
        "sources":[{"port":0}],"receivers":[{"port":1}],"run_time_domain":False,
        "resonance_requests":[{"port":0,"model":"series_rlc","frequency_min_hz":float(f[0]),"frequency_max_hz":float(f[-1])}]}


class WorkflowResonanceTests(unittest.TestCase):
    def test_explicit_fit_with_matched_load_definition(self):
        result=run_si_workflow(request())
        self.assertEqual(result["resonance_fits"][0]["fit"]["status"],"qualified_model_fit")
        self.assertAlmostEqual(result["resonance_fits"][0]["fit"]["parameters"]["q_factor"],10,places=6)
        self.assertIn("NOT applied",result["resonance_fits"][0]["termination_definition"])

    def test_optional_absence(self):
        value=request();del value["resonance_requests"]
        self.assertEqual(run_si_workflow(value)["resonance_fits"],[])

    def test_bad_requests_and_uncovered_band(self):
        base=request()
        for change in ({"port":True},{"port":2},{"model":"auto"},{"frequency_min_hz":0},{"extra":1}):
            value=copy.deepcopy(base);value["resonance_requests"][0].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):
                run_si_workflow(value)
        value=copy.deepcopy(base);value["resonance_requests"][0].update(frequency_min_hz=1e12,frequency_max_hz=2e12)
        self.assertEqual(run_si_workflow(value)["resonance_fits"][0]["fit"]["status"],"not_qualified")

    def test_pole_is_not_silently_filtered(self):
        value=request();f=np.linspace(1e6,100e6,33);s=np.zeros((33,2,2),complex);s[16,0,0]=1
        value["channel"]["text"]=touchstone_text(f,s)
        value["resonance_requests"][0].update(frequency_min_hz=1e6,frequency_max_hz=100e6)
        fit=run_si_workflow(value)["resonance_fits"][0]["fit"]
        self.assertEqual(fit["status"],"not_qualified")
        self.assertIn("no samples were dropped",fit["reasons"][0])


if __name__=="__main__":
    unittest.main()
