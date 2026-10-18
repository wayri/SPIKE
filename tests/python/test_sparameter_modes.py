# SPDX-License-Identifier: Apache-2.0
"""Independent mode-wave oracles; original synthetic data, no vendor fixtures."""
import unittest
import numpy as np
from python.spike_core.sparameters import NetworkData, single_ended_to_mixed_mode, s_to_z
from python.spike_core.sparameter_modes import mixed_mode_network


def network(s, refs=None):
    s = np.asarray(s, complex)
    if s.ndim == 2:
        s = s[None]
    return NetworkData(np.arange(len(s), dtype=float)*1e9, s,
                       np.array(refs if refs is not None else [50.]*s.shape[1]))


class MixedModeTests(unittest.TestCase):
    def test_nonadjacent_polarity_and_order_analytic(self):
        # One physical transfer, receiver 3 from source 0, equals .8.
        s = np.zeros((5,5)); s[3,0] = .8
        result = mixed_mode_network(network(s, [50,75,75,50,33]), [(0,3),(2,1)], [4])
        expected = np.zeros((5,5))
        expected[0,0] = -.4; expected[0,2] = -.4
        expected[2,0] = .4; expected[2,2] = .4
        np.testing.assert_allclose(result.network.parameters[0], expected, atol=2e-16)
        np.testing.assert_equal(result.network.reference_impedance_ohm, [100,150,25,37.5,33])
        reversed_pair = mixed_mode_network(network(s), [(3,0),(2,1)], [4])
        self.assertAlmostEqual(reversed_pair.network.parameters[0,0,2].real, .4)
        self.assertEqual(result.port_mapping[-1], {'kind':'single_ended','port':4,'name':'P5'})

    def test_voltage_current_impedance_oracle(self):
        # Two uncoupled impedances, Zp=10, Zn=30, referenced to 50 ohm.
        source = network(np.diag([(10-50)/(10+50), (30-50)/(30+50)]))
        modes = mixed_mode_network(source, [(0,1)]).network
        # Vd=Vp-Vn, Id=(Ip-In)/2; Vc=(Vp+Vn)/2, Ic=Ip+In.
        np.testing.assert_allclose(s_to_z(modes.parameters, modes.reference_impedance_ohm)[0],
                                   [[40,-10],[-10,10]], atol=2e-14)

    def test_power_reciprocity_and_legacy(self):
        rng = np.random.default_rng(918)
        s = rng.normal(size=(3,6,6)) + 1j*rng.normal(size=(3,6,6))
        s = (s+s.transpose(0,2,1))/30
        result = mixed_mode_network(network(s), [(0,1),(2,3),(4,5)]).network
        np.testing.assert_allclose(result.parameters, single_ended_to_mixed_mode(s), atol=2e-16)
        np.testing.assert_allclose(np.linalg.svd(result.parameters, compute_uv=False),
                                   np.linalg.svd(s, compute_uv=False), atol=4e-16)
        np.testing.assert_allclose(result.parameters, result.parameters.transpose(0,2,1), atol=2e-16)

    def test_original_preserved_and_z_input(self):
        source = network(np.diag([10.,30.])); source.parameter_kind='Z'
        old = source.parameters.copy()
        result = mixed_mode_network(source, [(0,1)], port_names=['plus','minus'])
        result.network.frequencies_hz[0]=10
        result.network.parameters[0,0,0]=0
        np.testing.assert_equal(source.parameters, old)
        self.assertEqual(source.frequencies_hz[0],0)
        self.assertEqual(source.comments,[])
        self.assertEqual(result.port_mapping[0]['positive_name'],'plus')

    def test_invalid_partition_rejected(self):
        for pairs, singles in (([],[0,1,2,3]), ([(0,1)],[]), ([(0,1),(1,3)],[]),
                                ([(True,0),(2,3)],[]), ([(0,5),(2,3)],[]), ([(0,)], [1,2,3])):
            with self.subTest(pairs=pairs), self.assertRaises(ValueError):
                mixed_mode_network(network(np.eye(4)),pairs,singles)

    def test_invalid_data_rejected(self):
        for field, value in [('reference_impedance_ohm',np.array([50,75])),
                             ('reference_impedance_ohm',np.array([50+1j,50])),
                             ('reference_impedance_ohm',np.array([True,True])),
                             ('reference_impedance_ohm',np.array([0,0])),
                             ('parameters',np.full((1,2,2),np.nan)),
                             ('frequencies_hz',np.array([-1.])),
                             ('frequencies_hz',np.array([np.inf]))]:
            source=network(np.eye(2)); setattr(source,field,value)
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                mixed_mode_network(source,[(0,1)])
        for names in (['a','a'],['a'],['a','']):
            with self.assertRaises(ValueError): mixed_mode_network(network(np.eye(2)),[(0,1)],port_names=names)

    def test_active_network_is_not_repaired(self):
        result=mixed_mode_network(network(np.eye(2)*2),[(0,1)]).network
        np.testing.assert_allclose(np.linalg.svd(result.parameters,compute_uv=False),[[2,2]])


if __name__ == '__main__':
    unittest.main()
