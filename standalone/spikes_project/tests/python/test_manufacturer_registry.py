from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio/python'))
from spikes_studio.component_catalog import catalog
from spikes_studio.library_browser import CatalogIndex
from spikes_studio.manufacturer_registry import capability_summary, source_report, SOURCES


class ManufacturerRegistryTests(unittest.TestCase):
    def test_counts_distinguish_presets_from_manufacturer_models(self):
        self.assertEqual(capability_summary(catalog()['records']), {
            'presets': 5000, 'archetypes': 100, 'native': 650,
            'bench_only': 4350, 'manufacturer_qualified': 0})

    def test_manufacturer_name_alone_does_not_qualify(self):
        record = deepcopy(catalog()['records'][0])
        record['manufacturer'] = 'Example manufacturer'
        record['qualification'] = 'manufacturer_qualified'
        self.assertEqual(capability_summary([record])['manufacturer_qualified'], 0)

    def test_search_provenance_without_invented_parts(self):
        index = CatalogIndex(catalog()['records'])
        self.assertEqual(index.query('manufacturer:"Texas Instruments"'), [])
        self.assertEqual(len(index.query('qualification:unqualified_presets', family='resistor')), 50)
        self.assertEqual(len(index.query('fidelity:generic_reduced_order', status='native_subcircuit')), 650)

    def test_source_directory_is_not_an_executable_model(self):
        for source in SOURCES:
            self.assertEqual(source['state'], 'source_identified_not_qualified')
            self.assertNotIn('source', source)
            self.assertTrue(source['model_url'].startswith('https://www.ti.com/'))
        self.assertIn('NOT installed components', source_report())


if __name__ == '__main__':
    unittest.main()
