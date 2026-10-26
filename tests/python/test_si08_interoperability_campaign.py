# SPDX-License-Identifier: Apache-2.0
"""Original import/transform/neutral-export witnesses, independent of round trips."""
import hashlib
import json
import unittest

import numpy as np

from examples.si08_interoperability.run_campaign import capture
from python.spike_core.solvers.signal_integrity.networks.sparameters import (
    parse_touchstone_text, touchstone_text)


class InteroperabilityCampaignTests(unittest.TestCase):
    def test_two_port_asymmetric_source_order_all_formats_and_units(self):
        for unit, frequency in [('Hz', 1e9), ('kHz', 1e6), ('MHz', 1e3), ('GHz', 1)]:
            for fmt, row in [('RI', '0 0 0.6 0 0 -0.8 0 0'),
                             ('MA', '0 0 0.6 0 0.8 -90 0 0'),
                             ('DB', '-6000 0 -4.436974992327127 0 -1.938200260161128 -90 -6000 0')]:
                with self.subTest(unit=unit, fmt=fmt):
                    text = f'# {unit} S {fmt} R 50\n{frequency} {row}\n'
                    out = json.loads(capture(text, 'original.s2p', ['TX+', 'RX−'], [(0, 1)]))
                    # Physical receiver1/source0=.6; receiver0/source1=-.8j.
                    expected = [[-.3+.4j, -.3-.4j], [.3+.4j, .3-.4j]]
                    actual = np.array(out['derived_network']['s_parameters'])
                    np.testing.assert_allclose(actual[0, :, :, 0]+1j*actual[0, :, :, 1], expected, atol=3e-16, rtol=0)
                    self.assertEqual(out['derived_network']['frequencies_hz'], [1e9])
                    self.assertEqual(out['source']['text'], text)
                    self.assertEqual(out['source']['sha256'], hashlib.sha256(text.encode()).hexdigest())
                    self.assertEqual(out['port_mapping'][0]['negative_name'], 'RX−')

    def test_three_port_row_order_unpaired_and_reference_retention(self):
        # Touchstone2 full N>=3 matrices are receiver-major; S20=.8 only.
        text = '[Version] 2.0\n# Hz S RI R 50\n[Number of Ports] 3\n[Number of Frequencies] 1\n[Reference] 50 33 50\n[Network Data]\n0 0 0 0 0 0 0\n0 0 0 0 0 0\n.8 0 0 0 0 0\n[End]\n'
        out = json.loads(capture(text, 'native.s3p', ['launch', 'monitor', 'return'], [(0, 2)], [1]))
        raw = np.array(out['derived_network']['s_parameters'])[0]
        expected = [[-.4, -.4, 0], [.4, .4, 0], [0, 0, 0]]
        np.testing.assert_allclose(raw[:, :, 0], expected, rtol=0, atol=2e-16)
        self.assertEqual(out['derived_network']['reference_impedance_ohm'], [100, 25, 33])
        self.assertEqual(out['port_mapping'][-1], {'kind': 'single_ended', 'port': 1, 'name': 'monitor'})
        self.assertEqual(out['source_causality'], 'unknown')
        self.assertFalse(out['physical_qualified']); self.assertFalse(out['production_qualified'])

    def test_touchstone1_export_rejects_unequal_modes_instead_of_losing_references(self):
        # A companion JSON is necessary: a v1 scalar reference cannot encode D/C.
        text = '# Hz S RI R 50\n0 0 0 0.6 0 0.2 0 0 0\n'
        out = json.loads(capture(text, 'fixture.s2p', ['p', 'n'], [(0, 1)]))
        data = out['derived_network']; raw = np.array(data['s_parameters'])
        with self.assertRaises(ValueError):
            touchstone_text(data['frequencies_hz'], raw[:, :, :, 0]+1j*raw[:, :, :, 1], data['reference_impedance_ohm'])
        self.assertEqual(json.loads(json.dumps(out)), out)

    def test_explicit_pair_polarity_export_and_source_identity(self):
        text = '# Hz S RI R 50\n0 0 0 0.6 0 0.2 0 0 0\n'
        first = json.loads(capture(text, 'directional.s2p', ['p', 'n'], [(0, 1)]))
        second = json.loads(capture(text, 'directional.s2p', ['p', 'n'], [(1, 0)]))
        a = np.array(first['derived_network']['s_parameters'])[0, :, :, 0]
        b = np.array(second['derived_network']['s_parameters'])[0, :, :, 0]
        np.testing.assert_allclose(b, [[a[0, 0], -a[0, 1]], [-a[1, 0], a[1, 1]]], atol=1e-16)
        self.assertEqual(first['source'], second['source'])
        self.assertEqual(second['port_mapping'][0]['positive_name'], 'n')

    def test_invalid_names_partition_and_source_are_rejected(self):
        text = '# Hz S RI R 50\n0 0 0 0.6 0 0.2 0 0 0\n'
        for names, pairs, singles in [(['same', 'same'], [(0, 1)], []),
                                      (['p', 'n'], [(0, 1)], [0]),
                                      (['p', 'n'], [(0, 0)], []),
                                      (['p', 'n'], [(True, 0)], [])]:
            with self.subTest(names=names, pairs=pairs), self.assertRaises(ValueError):
                capture(text, 'bad.s2p', names, pairs, singles)
        with self.assertRaises(ValueError):
            parse_touchstone_text('# Hz S RI R 50\n0 1 0\n', 'bad.s2p')


if __name__ == '__main__':
    unittest.main()
