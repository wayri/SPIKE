# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from python.spike_core.service import handle
from python.spike_core.pdn_series_capacitors import review_series_capacitor_leg
from tests.python.test_pdn_network import basic, element
from tests.python.test_pdn_shunt_capacitance import supplied


class PdnNetworkWorkerTests(unittest.TestCase):
    def test_live_dielectric_extraction_attaches_as_extracted(self):
        from tests.python.test_pdn_electrostatic import plate, EPSILON_0
        raw = plate(2)
        response = handle({'method': 'extract_pdn_electrostatic', 'params': {'request': raw}})
        self.assertTrue(response['ok'], response)
        field = response['result']
        self.assertAlmostEqual(field['pdn_elements'][0]['capacitance_f']/(4*EPSILON_0), 1.)
        self.assertEqual(field['pdn_elements'][0]['provenance']['kind'], 'extracted')
        self.assertEqual(field['pdn_elements'][0]['negative'], 'return-terminal')
    def test_actual_worker_ac_and_preflight(self):
        raw = basic([element('r', 'resistor', positive='V', negative='GND', resistance_ohm=2.)])
        for method in ('validate_pdn_network', 'evaluate_pdn_network'):
            response = handle({'method': method, 'params': {'request': raw}})
            self.assertTrue(response['ok'], response)
        invalid = handle({'method': 'evaluate_pdn_network', 'params': {'request': raw, 'executable': 'untrusted'}})
        self.assertFalse(invalid['ok'])

    def test_explicit_context_capacitor_attach(self):
        request = supplied()
        params = {'request': request, 'expected_context_digest': 'a'*64}
        result = handle({'method': 'pdn_capacitor_elements', 'params': params})
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['result']['elements'][0]['negative'], 'return-42')
        params['expected_context_digest'] = 'b'*64
        self.assertFalse(handle({'method': 'pdn_capacitor_elements', 'params': params})['ok'])

    def test_series_voltage_rating_not_sum_of_labels(self):
        capacitors = [{'id': name, 'capacitance_f': 10e-6, 'tolerance_fraction': .2,
                       'rated_voltage_v': 6.3, 'leakage_resistance_ohm': None,
                       'balancing_resistance_ohm': None} for name in ('C1', 'C2')]
        raw = {'contract': 'spike/series-capacitor-leg/v1', 'voltage_v': 12., 'capacitors': capacitors}
        result = review_series_capacitor_leg(raw)
        self.assertAlmostEqual(result['equivalent_capacitance_f'], 5e-6)
        self.assertAlmostEqual(result['capacitors'][0]['capacitive_worst_tolerance_voltage_v'], 7.2)
        self.assertTrue(result['capacitors'][0]['capacitive_rating_exceeded'])
        self.assertFalse(result['dc_leakage_model_complete'])
        self.assertFalse(result['automatic_voltage_uprating_permitted'])
        raw['capacitors'][0]['leakage_resistance_ohm'] = 1e6
        raw['capacitors'][1]['leakage_resistance_ohm'] = 2e6
        result = review_series_capacitor_leg(raw)
        self.assertAlmostEqual(result['capacitors'][1]['modeled_dc_voltage_v'], 8.)
        for c in raw['capacitors']: c['balancing_resistance_ohm'] = 1e4
        self.assertLess(review_series_capacitor_leg(raw)['capacitors'][1]['modeled_dc_voltage_v'], 6.1)

    def test_series_intermediate_node_is_not_ground(self):
        raw = basic([element('c1', 'capacitor', positive='V', negative='mid', capacitance_f=10e-6),
                     element('c2', 'capacitor', positive='mid', negative='GND', capacitance_f=10e-6)], nodes=['V', 'mid'])
        result = handle({'method': 'evaluate_pdn_network', 'params': {'request': raw}})
        self.assertTrue(result['ok'], result)
        import math
        self.assertAlmostEqual(result['result']['ac'][0]['impedance_ohm'][0][0]['imag'], -1/(2*math.pi*1000*5e-6))

    def test_asymmetric_series_tolerance_corners_and_unknown_leakage(self):
        import itertools
        caps = [{'id': str(i), 'capacitance_f': c, 'tolerance_fraction': t,
                 'rated_voltage_v': 100., 'leakage_resistance_ohm': None,
                 'balancing_resistance_ohm': 1e4}
                for i, (c, t) in enumerate(((1e-6, .1), (2e-6, .2), (4e-6, .3)))]
        request = {'contract': 'spike/series-capacitor-leg/v1', 'voltage_v': 30., 'capacitors': caps}
        result = review_series_capacitor_leg(request)
        corners = []
        for signs in itertools.product((-1, 1), repeat=3):
            inverse = [1/(c['capacitance_f']*(1+s*c['tolerance_fraction'])) for c, s in zip(caps, signs)]
            corners.append([30*v/sum(inverse) for v in inverse])
        for i, row in enumerate(result['capacitors']):
            self.assertAlmostEqual(row['capacitive_worst_tolerance_voltage_v'], max(c[i] for c in corners))
            self.assertIsNone(row['modeled_dc_voltage_v'])
        self.assertFalse(result['dc_leakage_model_complete'])
        self.assertFalse(result['automatic_voltage_uprating_permitted'])
        for value in (True, float('inf'), float('nan'), 10**400, 1e-250):
            invalid = copy.deepcopy(request)
            invalid['capacitors'][0]['capacitance_f'] = value
            with self.assertRaises(ValueError):
                review_series_capacitor_leg(invalid)
