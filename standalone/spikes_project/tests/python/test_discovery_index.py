# SPDX-License-Identifier: Apache-2.0
"""Index equivalence protects exact IDs, fuzzy ranks and live collections."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.component_catalog import catalog
from spikes_studio.discovery_index import DiscoveryIndex, manufacturer_text
from spikes_studio.fuzzy_search import ranked
from spikes_studio.manufacturer_parts import load_catalog
from spikes_studio.quick_insert import suggestions


class DiscoveryIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records=catalog(include_passives=True,include_lumped_physics=True)['records']
        cls.manufacturers=load_catalog()['records']
        cls.index=DiscoveryIndex(cls.records)
        cls.manufacturer_index=DiscoveryIndex(cls.manufacturers,manufacturer_text)

    def test_rank_equivalence_for_literal_fuzzy_and_structured_queries(self):
        index=self.index
        for query in ('r','n','1k','resistor','capacitor','resistr','nmos','Nmos','0603','10',
                      '"metal film"','resistor -kelvin','generic.resistor.001',
                      '-resistor','', 'x'*513):
            for limit in (1,12,48):
                with self.subTest(query=query,limit=limit):
                    expected=ranked(self.records,query,text=index.text)[:limit]
                    self.assertEqual(index.query(self.records,query,limit),expected)

    def test_complete_suggestions_preserve_availability_and_live_signals(self):
        for query,category in [('resistor','All'),('resistr','All'),('LM358','All'),
                               ('','Components'),('','Discrete'),('V(o','Monitors')]:
            args=(query,self.records,self.manufacturers,['out','other'],['V1'],category)
            self.assertEqual(suggestions(*args),suggestions(*args,component_index=self.index,
                             manufacturer_index=self.manufacturer_index))
        args=('V(o',self.records,self.manufacturers)
        rows=suggestions(*args,nets=['output'],component_index=self.index)
        self.assertIn('V(output)',[row['payload'] for row in rows])
        self.assertNotIn('V(out)',[row['payload'] for row in rows])

    def test_collection_order_cache_bounds_and_return_isolation(self):
        index=DiscoveryIndex(self.records)
        chosen=list(reversed(self.records[:5]))
        self.assertEqual(index.query(chosen,'',3),chosen[:3])
        result=index.query(chosen,'',3);result.clear()
        self.assertEqual(index.query(chosen,'',3),chosen[:3])
        self.assertEqual(index.query(chosen[1:],'',3),chosen[1:4])
        for query in range(25):index.query(chosen,str(query),3)
        self.assertLessEqual(len(index.cache),16)
        with self.assertRaises(ValueError):index.query(chosen,'',101)

    def test_exact_text_precedes_word_matches_even_late_in_input(self):
        rows=[{'id':str(i),'text':'resistor variant '+str(i)} for i in range(60)]
        rows.append({'id':'exact','text':'resistor'})
        index=DiscoveryIndex(rows,lambda row:row['text'])
        self.assertEqual(index.query(rows,'resistor',10),ranked(rows,'resistor',text=index.text)[:10])


if __name__=='__main__':unittest.main()
