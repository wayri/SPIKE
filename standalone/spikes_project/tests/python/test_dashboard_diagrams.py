# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.dashboard import widget,validate_dashboard,connect_widgets,remove_widget,update_widget


class DiagramTests(unittest.TestCase):
    def test_links_are_stable_and_removed_with_items(self):
        a,b=widget('Diagram block'),widget('Meter');data={'version':1,'widgets':[a,b]}
        linked=connect_widgets(data,a['id'],b['id']);self.assertNotIn('connections',data)
        moved=update_widget(linked,a['id'],x=400);self.assertEqual(moved['connections'],linked['connections'])
        self.assertEqual(remove_widget(moved,a['id'])['connections'],[])
        with self.assertRaises(ValueError):connect_widgets(linked,a['id'],b['id'])
        with self.assertRaises(ValueError):connect_widgets(data,a['id'],'missing')
        with self.assertRaises(ValueError):connect_widgets(data,a['id'],a['id'])

    def test_data_only_dut_mapping_and_legacy_admission(self):
        row=widget('Source control');data={'version':1,'widgets':[row]};validate_dashboard(data)
        binding=dict(device='probe',connector='J1',pin='3',gpio='PA5',direction='Write',safe_value=0)
        mapped=update_widget(data,row['id'],dut_binding=binding)
        self.assertEqual(mapped['widgets'][0]['dut_binding'],binding)
        self.assertNotIn('dut_binding',row)
        with self.assertRaises(ValueError):update_widget(data,row['id'],dut_binding=dict(binding,safe_value=3))

    def test_malformed_links_rejected(self):
        with self.assertRaises(ValueError):validate_dashboard({'version':1,'widgets':[],'connections':[{}]})
