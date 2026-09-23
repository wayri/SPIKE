from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio import symbol_design as d


class SymbolDesignTests(unittest.TestCase):
    def test_default(self):d.checked(d.new_symbol())
    def test_drag_changes_edge_and_snaps(self):
        s=d.drag_pin(d.new_symbol(),0,13,-75);p=s['terminals'][0]
        self.assertEqual(p['direction'],'north');self.assertEqual(p['at'],[10,-60]);self.assertEqual(p['leg_endpoint'],[10,-40])
    def test_collision_atomic(self):
        original=d.new_symbol()
        with self.assertRaises(ValueError):d.set_pin(original,None,'3','COLLIDE','west',0)
        self.assertEqual(len(original['terminals']),2)
    def test_duplicate_number(self):
        with self.assertRaises(ValueError):d.set_pin(d.new_symbol(),None,'1','DUP','west',20)
    def test_resize_keeps_legs(self):
        s=d.resize(d.new_symbol(),140,100)
        self.assertEqual(s['body_keepout']['max'],[70,50]);self.assertEqual(s['terminals'][0]['leg_endpoint'],[-70,0]);d.checked(s)
    def test_metadata_and_named_pin(self):
        s=d.set_pin(d.new_symbol(),0,'7','VCC','north',20)
        self.assertEqual(s['terminals'][0]['id'],'7');self.assertNotIn('model',s)

if __name__=='__main__':unittest.main()
