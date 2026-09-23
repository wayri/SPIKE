from copy import deepcopy
from pathlib import Path
import sys
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.component_catalog import catalog
from spikes_studio.library_browser import CatalogIndex,insertion_plan,apply_insertion
from spikes_studio.document import Document,RC_DECK,Keymap
import tempfile


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.records=catalog()['records'];cls.index=CatalogIndex(cls.records)
    def test_search_filters_numeric_sort(self):
        self.assertEqual(len(self.index.query('family:resistor -cable')),50)
        self.assertEqual(len(self.index.query('category:"Basic RF"',status='native_subcircuit')),250)
        rows=self.index.query(family='resistor',minimum=500,maximum=2000,sort='Primary value',descending=True)
        values=[r['parameters']['r'] for r in rows];self.assertEqual(values,sorted(values,reverse=True));self.assertTrue(all(500<=v<=2000 for v in values))
        self.assertEqual(self.index.query('nonexistentpart'),[])
        with self.assertRaises(ValueError):self.index.query('unknown:field')
        with self.assertRaises(ValueError):self.index.query(minimum=float('nan'))
    def test_favorites_recent_and_cache(self):
        ident=self.records[0]['id'];self.assertEqual([r['id'] for r in self.index.query(favorites=[ident],only_favorites=True)],[ident])
        self.assertEqual([r['id'] for r in self.index.query(recent=[ident])],[ident])
        a=self.index.query('family:resistor');a.clear();self.assertEqual(len(self.index.query('family:resistor')),50)
        for i in range(40):self.index.query(str(i))
        self.assertLessEqual(len(self.index.cache),32)
    def test_atomic_multi_instance_mapping_and_undo(self):
        record=self.index.query('family:resistor')[0];doc=Document.from_netlist(RC_DECK);before=deepcopy(doc.data)
        plan=insertion_plan(doc,record,{'P':'load_{n}','N':'0'},count=3,x=500,y=500)
        self.assertEqual(doc.data,before);self.assertEqual(plan['refs'],['XCAT1','XCAT2','XCAT3'])
        self.assertEqual(plan['source'].lower().count('.subckt '),1)
        new=[p for p in plan['components'] if p['ref'].startswith('XCAT')]
        self.assertEqual([p['nodes'][0] for p in new],['load_1','load_2','load_3'])
        self.assertEqual(len({(p['x'],p['y']) for p in new}),3)
        apply_insertion(doc,plan,record['id']);self.assertEqual(doc.data['metadata']['library_browser']['recent'],[record['id']]);doc.undo();self.assertEqual(doc.data,before)
        doc.redo();second=insertion_plan(doc,record,{'P':'load','N':'0'},count=2);self.assertEqual(second['refs'],['XCAT4','XCAT5']);self.assertEqual(second['source'].lower().count('.subckt '),1)
    def test_reject_without_mutation_and_preserve_layout(self):
        doc=Document.from_netlist(RC_DECK);doc.data['components'][0]['x']=555;before=deepcopy(doc.data)
        record=self.index.query('family:resistor')[0]
        for kwargs in ({'count':101},{'count':0},{'x':float('inf')}):
            with self.assertRaises(ValueError):insertion_plan(doc,record,{'P':'out','N':'0'},**kwargs)
        with self.assertRaises(ValueError):insertion_plan(doc,record,{'P':'bad\n.end','N':'0'})
        with self.assertRaises(ValueError):insertion_plan(doc,self.index.query('family:npn')[0],{'P':'out','N':'0'})
        self.assertEqual(doc.data,before)
        plan=insertion_plan(doc,record,{'P':'out','N':'0'});self.assertEqual(plan['components'][0]['x'],555)

    def test_part_shortcut_profiles(self):
        keys=Keymap();self.assertEqual(keys.bindings['part.resistor'],'R')
        keys=Keymap(keys.bindings|{'part:generic.resistor.001':'Alt+R'},False)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'parts.spkkeys';keys.save(path);loaded=Keymap.load(path)
            self.assertEqual(loaded.bindings,keys.bindings);self.assertFalse(loaded.part_shortcuts)
        self.assertEqual(Keymap.from_data({'contract':'spikes/shortcuts/v1','bindings':{'file.open':'Ctrl+O'}}).bindings,{'file.open':'Ctrl+O'})
        for bindings in ({'part:generic.resistor.001':'R','part.resistor':'r'}, {'part:../bad':'Q'}, {'part.resistor':1}):
            with self.assertRaises(ValueError):Keymap(bindings)
        with self.assertRaises(ValueError):Keymap(part_shortcuts='false')

if __name__=='__main__':unittest.main()
