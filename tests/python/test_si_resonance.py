# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Single-RLC analytical oracles, not arbitrary-network resonance claims."""
import unittest
import numpy as np
from python.spike_core.si_resonance import fit_single_rlc


def fixture(model,q=10,points=4097):
    f0=10e6;omega0=2*np.pi*f0;inductance=1e-6;capacitance=1/(omega0**2*inductance)
    resistance=omega0*inductance/q if model=="series_rlc" else q/(omega0*capacitance)
    lower=f0*(np.sqrt(1+1/(4*q*q))-1/(2*q));upper=f0*(np.sqrt(1+1/(4*q*q))+1/(2*q))
    f=np.linspace(.5*lower,1.5*upper,points);w=2*np.pi*f
    z=(resistance+1j*(w*inductance-1/(w*capacitance)) if model=="series_rlc" else 1/(1/resistance+1j*(w*capacitance-1/(w*inductance))))
    return f,z,{"resonance_hz":f0,"q_factor":q,"resistance_ohm":resistance,"inductance_h":inductance,"capacitance_f":capacitance}


class ResonanceTests(unittest.TestCase):
    def test_analytic_series_parallel_and_different_q(self):
        for model in ("series_rlc","parallel_rlc"):
            for q in (.5,2,10,100):
                with self.subTest(model=model,q=q):
                    f,z,expected=fixture(model,q)
                    result=fit_single_rlc(f,z,model=model)
                    self.assertEqual(result["status"],"qualified_model_fit",result["reasons"])
                    for key,value in expected.items():
                        self.assertAlmostEqual(result["parameters"][key]/value,1,places=10)
                    self.assertLess(result["independent_half_power"]["q_relative_error"],.01)
                    self.assertFalse(result["physical_resonance_qualified"])

    def test_small_deterministic_noise_fit(self):
        f,z,_=fixture("series_rlc",q=10)
        noise=np.random.default_rng(17).normal(size=(2,len(f)))
        z=z*(1+1e-5*(noise[0]+1j*noise[1]))
        result=fit_single_rlc(f,z,model="series_rlc")
        self.assertEqual(result["status"],"qualified_model_fit",result["reasons"])
        self.assertLess(abs(result["parameters"]["q_factor"]/10-1),.001)

    def test_missing_halfpower_band_and_coarse_grid_rejected(self):
        f,z,_=fixture("series_rlc")
        subset=f<10e6
        result=fit_single_rlc(f[subset],z[subset],model="series_rlc")
        self.assertEqual(result["status"],"not_qualified")
        self.assertNotIn("parameters",result)
        f,z,_=fixture("series_rlc",100,32)
        self.assertEqual(fit_single_rlc(f,z,model="series_rlc")["status"],"not_qualified")

    def test_negative_resistance_and_multimode_misfit(self):
        f,z,_=fixture("series_rlc")
        negative=-z.real+1j*z.imag
        self.assertEqual(fit_single_rlc(f,negative,model="series_rlc")["status"],"not_qualified")
        w=2*np.pi*f
        second=1/(1/100+1j*(w*5e-11-1/(w*3e-6)))
        result=fit_single_rlc(f,z+second,model="series_rlc")
        self.assertEqual(result["status"],"not_qualified")
        self.assertTrue(result["reasons"])

    def test_invalid_contract_values(self):
        f,z,_=fixture("series_rlc")
        for frequency,impedance,model in ((f,z,"auto"),(f[:5],z[:5],"series_rlc"),
            (np.zeros(len(f)),z,"series_rlc"),(f,np.full(len(f),complex("nan")),"parallel_rlc")):
            with self.assertRaises(ValueError):
                fit_single_rlc(frequency,impedance,model=model)


if __name__=="__main__":
    unittest.main()
