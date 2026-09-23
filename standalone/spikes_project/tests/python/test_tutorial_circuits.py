from pathlib import Path
import sys
import os
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.help_center import example_dir
from spikes_studio.document import Document


class Tutorials(unittest.TestCase):
    def test_all_decks_parse_and_sources_exist(self):
        paths=sorted(example_dir().glob('*.cir'));self.assertEqual(len(paths),9)
        for path in paths:
            with self.subTest(path=path.name):Document.from_netlist(path.read_text())

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Native DLL not configured')
    def test_native_behaviors(self):
        from spikes_studio.run_control import native_batch
        for path in sorted(example_dir().glob('*.cir')):
            with self.subTest(path=path.name):
                result=native_batch(path.read_text(),os.environ['SPIKES_TEST_NATIVE_LIBRARY'])
                self.assertEqual(result['status'],'completed')
                data=result.get('data',{})
                if path.name.startswith('01'):self.assertAlmostEqual(data['node_voltage_v']['out'],6,places=8)
                if path.name.startswith('02'):self.assertAlmostEqual(data['node_voltage_v']['out'][-1],4.9663,delta=.003)
                if path.name.startswith('03'):self.assertAlmostEqual(data['element_current_a']['L1'][-1],.99326,delta=.003)
                if path.name.startswith('05'):self.assertEqual(len(result['runs']),3)
                if path.name.startswith('06'):self.assertAlmostEqual(data['node_voltage_v']['out'],2.4,places=8)
