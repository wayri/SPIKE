# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio' / 'python'))

from spikes_studio.command_registry import CommandRegistry, Context
from spikes_studio.model_collection import search_entries


class FuzzySurfaceTests(unittest.TestCase):
    def test_command_search_handles_typo_and_preserves_availability(self):
        registry = CommandRegistry.from_actions(
            {'run.pause': lambda: None, 'view.fit': lambda: None}, lambda: Context())

        rows = registry.search('puase', {'run.pause': 'F6'})

        self.assertEqual([row['id'] for row in rows], ['run.pause'])
        self.assertEqual(rows[0]['shortcut'], 'F6')
        self.assertIn('continuous', rows[0]['disabled_reason'])

    def test_empty_command_search_keeps_enabled_first_order(self):
        registry = CommandRegistry.from_actions(
            {'view.fit': lambda: None, 'run.pause': lambda: None}, lambda: Context())

        self.assertEqual([row['id'] for row in registry.search()], ['view.fit', 'run.pause'])

    def test_model_search_handles_typo_without_weakening_exact_kind_filter(self):
        entries = [
            {'id': 'first', 'kind': 'model', 'name': 'Precision Diode', 'path': 'a.lib'},
            {'id': 'excluded', 'kind': 'subcircuit', 'name': 'Precision Diode', 'path': 'b.lib'},
            {'id': 'last', 'kind': 'model', 'name': 'Voltage Regulator', 'path': 'c.lib'},
        ]
        index = {'entries': entries}

        self.assertEqual(
            [entry['id'] for entry in search_entries(index, 'precison', kind='model')],
            ['first'])
        self.assertEqual(
            [entry['id'] for entry in search_entries(index, kind='model')],
            ['first', 'last'])


if __name__ == '__main__':
    unittest.main()
