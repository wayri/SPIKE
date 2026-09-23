# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import unittest
import numpy as np
from python.spike_core.multi_excitation_network import solve_multi_excitation


class MultiExcitationTests(unittest.TestCase):
    def test_nondiagonal_incident_recovers_known_network(self):
        s=np.array([[[.1,.7j],[.7j,.1]],[[.2,.3],[.3,.2]]],complex)
        a=np.array([[[1,.2j],[.1,1]],[[2,.4],[.3j,1]]],complex);b=s@a
        actual,evidence=solve_multi_excitation(a,b)
        np.testing.assert_allclose(actual,s,atol=1e-15)
        self.assertLess(evidence["maximum_relative_residual"],1e-14)
        self.assertGreater(np.max(abs(b/np.diagonal(a,axis1=1,axis2=2)[:,None,:]-s)),.01)
        self.assertFalse(evidence["passivity_enforced"])

    def test_rank_deficient_nonfinite_and_shape_rejected(self):
        for a,b in ((np.ones((1,2,2)),np.ones((1,2,2))),
                    (np.full((1,2,2),np.nan),np.zeros((1,2,2))),
                    (np.zeros((2,2)),np.zeros((2,2)))):
            with self.assertRaises(ValueError):solve_multi_excitation(a,b)

    def test_zero_reflection_and_experiment_scaling(self):
        a=np.array([[[1,.1j],[.2,1]]],complex)
        result,_=solve_multi_excitation(a,np.zeros_like(a));self.assertEqual(np.max(abs(result)),0)
        expected=np.array([[[0,.8],[.8,0]]],complex)
        scales=np.array([2j,3.])
        result,_=solve_multi_excitation(a*scales,(expected@a)*scales)
        np.testing.assert_allclose(result,expected,atol=1e-15)
