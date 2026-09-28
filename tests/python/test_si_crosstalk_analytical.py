# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import unittest
import numpy as np
from scripts.benchmark_si_crosstalk import run_benchmarks,line_fixture,independent_modal_s
from python.spike_core.si_coupled_channel import crosstalk_report,multiconductor_rlgc_network
from python.spike_core.si_crosstalk import analyze_crosstalk
from python.spike_core.sparameters import NetworkData


class CrosstalkAnalyticalTests(unittest.TestCase):
    def test_independent_oracle_and_convolution(self):
        report=run_benchmarks()
        self.assertTrue(report["passed"],report)

    def test_named_port_report_matches_complex_network(self):
        network=multiconductor_rlgc_network(line_fixture(),np.linspace(0,1e9,17),50.)
        report=crosstalk_report(network)
        self.assertEqual(report["port_order"],["aggressor.near","victim.near","aggressor.far","victim.far"])
        for name,port in (("next",1),("fext",3)):
            np.testing.assert_allclose([v["magnitude"] for v in report[name]["trace"]],np.abs(network.parameters[:,port,0]),atol=1e-15)

    def test_homogeneous_tem_modal_matching_caveat(self):
        fixture=line_fixture();r=fixture["rlgc_per_m"]
        r["resistance_ohm_per_m"]=np.zeros((2,2)).tolist();r["loss_tangent"]=0.
        lc=np.asarray(r["inductance_h_per_m"])@np.asarray(r["capacitance_f_per_m"])
        np.testing.assert_allclose(lc,np.eye(2)/(1.7e8)**2,atol=1e-31)
        s=independent_modal_s(fixture,np.linspace(0,2e9,129))
        # Equal 50-ohm loads mismatch the two modal impedances, allowing FEXT.
        self.assertGreater(np.max(np.abs(s[:,3,0])),1e-4)
        q=np.array([[1.,1.],[1.,-1.]])/np.sqrt(2)
        phase=np.exp(-2j*np.pi*1e9*.075/1.7e8)
        modal_matched_through=q@np.diag([phase,phase])@q.T
        self.assertLess(abs(modal_matched_through[1,0]),1e-15)

    def test_loaded_resistances_against_independent_nodal_equations(self):
        f=np.linspace(0,1e9,17);network=multiconductor_rlgc_network(line_fixture(),f,50.)
        ports={"aggressor_near":0,"victim_near":1,"aggressor_far":2,"victim_far":3}
        resistance=np.array([35.,75.,100.,40.])
        report=analyze_crosstalk(network,port_map=ports,termination_ohm=resistance.tolist())
        expected=[]
        for s in independent_modal_s(line_fixture(),f):
            admittance=np.linalg.solve((np.eye(4)+s).T,(np.eye(4)-s).T).T/50
            expected.append(np.linalg.solve(admittance+np.diag(1/resistance),[1/resistance[0],0,0,0]))
        for name,port in (("next",1),("fext",3)):
            actual=[complex(v["real"],v["imag"]) for v in report["frequency_response"][name]["trace"]]
            np.testing.assert_allclose(actual,np.asarray(expected)[:,port],atol=1e-11)

    def test_explicit_port_permutation_preserves_physics(self):
        f=np.linspace(0,1e9,17);original=multiconductor_rlgc_network(line_fixture(),f,50.)
        permutation=[3,0,2,1]
        reordered=NetworkData(frequencies_hz=f,parameters=original.parameters[:,permutation][:,:,permutation],
            reference_impedance_ohm=np.ones(4)*50,parameter_kind="S",data_format="RI")
        roles={"aggressor_near":0,"victim_near":1,"aggressor_far":2,"victim_far":3}
        a=analyze_crosstalk(original,port_map=roles,termination_ohm=[50.]*4)
        b=analyze_crosstalk(reordered,port_map={k:permutation.index(v) for k,v in roles.items()},termination_ohm=[50.]*4)
        for name in ("next","fext"):
            np.testing.assert_allclose([v["magnitude"] for v in a["frequency_response"][name]["trace"]],
                [v["magnitude"] for v in b["frequency_response"][name]["trace"]],atol=1e-13)
