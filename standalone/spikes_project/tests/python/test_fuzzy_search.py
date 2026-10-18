# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.fuzzy_search import matches,score,ranked


class FuzzySearchTests(unittest.TestCase):
    def test_typos_swaps_and_long_terms(self):
        for word,typo in [('resistor','resistr'),('capacitor','capaciotr'),('oscilloscope','osciloscope'),('lm358','lm385')]:
            self.assertTrue(matches(word,typo),(word,typo))
        self.assertFalse(matches('resistor','capacitor'))
        self.assertTrue(matches('v(output)','v(ouptut)'))

    def test_short_numeric_and_quoted_terms_remain_literal(self):
        self.assertFalse(matches('out','otu'));self.assertFalse(matches('12345','12354'))
        self.assertFalse(matches('Run 2 r=2000','2,000'))
        self.assertFalse(matches('1e4','1e3'))
        self.assertTrue(matches('precision analog amplifier','"precision analog"'))
        self.assertFalse(matches('precision excellent analog','"precision analog"'))
        self.assertFalse(matches('resistor cable','resistr -cable'))
        self.assertTrue(matches('resistor cable','resistr -cablx'))

    def test_ranking_and_bounds(self):
        self.assertEqual(ranked(['resistr','power resistor','resistor'],'resistor'),['resistor','power resistor','resistr'])
        self.assertTrue(matches('anything',''));self.assertFalse(matches('anything','x'*513))
        self.assertTrue(matches('ＣＡＰＡＣＩＴＯＲ','capacitor'))
        self.assertFalse(matches('opamp precision','opamp missing'))

    def test_catalog_filters_and_exclusions_stay_literal(self):
        from spikes_studio.component_catalog import catalog
        from spikes_studio.library_browser import CatalogIndex
        index=CatalogIndex(catalog()['records'])
        rows=index.query('resistr',category='Passives');self.assertTrue(any(r['family']=='resistor' for r in rows))
        self.assertEqual(index.query('family:resistr'),[])
        self.assertTrue(all(r['family']!='resistor' for r in index.query('-resistor')))
        self.assertEqual(index.query('manufacturer:missing'),[])

    def test_parts_plot_and_canvas_search_use_shared_matching(self):
        from spikes_studio.manufacturer_parts import query,load_catalog
        from spikes_studio.quick_insert import suggestions
        from spikes_studio.plot_workspace import _matches_filter
        rows=query(load_catalog()['records'],'lm385');self.assertTrue(any(r['mpn']=='LM358P' for r in rows))
        self.assertFalse(query(load_catalog()['records'],'lm385',category='capacitor'))
        self.assertTrue(_matches_filter('v(output)','outpt'))
        self.assertEqual(suggestions('resistr')[0]['payload'],'generic.resistor.001')


if __name__=='__main__':unittest.main()
