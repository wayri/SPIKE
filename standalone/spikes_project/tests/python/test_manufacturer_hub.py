# SPDX-License-Identifier: Apache-2.0
"""Manufacturer identities stay distinct from model execution and generic grids."""
from copy import deepcopy
import os
import tempfile
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio/python'))
from spikes_studio.manufacturer_discovery import validate, search


def fixture():
    return {'contract': 'spikes/manufacturer-discovery/v1', 'records': [
        {'id': 'ti.lm358', 'manufacturer': 'Texas Instruments', 'part_number': 'LM358',
         'category': 'opamp', 'description': 'Dual operational amplifier',
         'product_url': 'https://www.ti.com/product/LM358', 'model_url': None,
         'model_status': 'model_not_reviewed', 'checked_on': '2026-10-19'},
        {'id': 'adi.ad822', 'manufacturer': 'Analog Devices', 'part_number': 'AD822',
         'category': 'opamp', 'description': 'Dual operational amplifier',
         'product_url': 'https://www.analog.com/en/products/ad822.html', 'model_url': None,
         'model_status': 'model_not_reviewed', 'checked_on': '2026-10-19'}]}


class ManufacturerDiscoveryTests(unittest.TestCase):
    def test_fuzzy_search_and_filters_preserve_product_identity(self):
        rows = validate(fixture())['records']
        self.assertEqual(search(rows, 'LM358')[0]['part_number'], 'LM358')
        self.assertEqual(search(rows, '', manufacturer='Analog Devices'), [rows[1]])
        self.assertEqual(search(rows, category='nonexistent'), [])
        self.assertEqual(len(search(rows, 'amplifer')), 2)
        self.assertEqual(search(rows, 'ADI'), [rows[1]])

    def test_duplicate_identity_and_execution_approval_are_rejected(self):
        for mutation in ('duplicate', 'approved', 'bad_url', 'bad_source_url', 'missing_link'):
            data = deepcopy(fixture())
            if mutation == 'duplicate': data['records'].append(deepcopy(data['records'][0]))
            elif mutation == 'approved': data['records'][0]['model_status'] = 'qualified'
            elif mutation == 'bad_url': data['records'][0]['product_url'] = 'file:///model'
            elif mutation == 'bad_source_url': data['records'][0]['source_urls'] = ['file:///datasheet']
            else: data['records'][0]['model_status'] = 'source_identified_not_qualified'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): validate(data)


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX') == '1', 'requires native wx')
class ManufacturerHubWxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx
        cls.wx = wx; cls.app = wx.GetApp() or wx.App(False)

    def setUp(self):
        from spikes_studio import manufacturer_library_hub as hub
        from spikes_studio.themes import PALETTES
        self.hub = hub; self.frame = self.wx.Frame(None)
        self.owner = SimpleNamespace(palette=PALETTES['Light'], guarded=lambda fn: fn(),
                                    catalog_panel=SimpleNamespace(vendor=lambda: None, project_model_shelf=lambda: None))
        with patch.object(hub, 'load_catalog', return_value=fixture()):
            self.panel = hub.ManufacturerLibraryHub(self.frame, self.owner)

    def tearDown(self):
        self.frame.Destroy(); self.wx.Yield()

    def test_products_are_default_and_generic_values_are_not_product_rows(self):
        self.assertEqual(self.panel.book.GetSelection(), 0)
        self.assertEqual(self.panel.products.listing.GetItemCount(), 2)
        self.assertEqual(self.panel.book.GetPageText(2), 'Local LTspice')
        self.panel.search.SetValue('LM358'); self.wx.Yield()
        self.assertEqual(self.panel.products.listing.rows[0]['part_number'], 'LM358')
        self.assertFalse(self.panel.products.model_button.IsEnabled())

    def test_generic_workbench_manufacturer_button_uses_product_route(self):
        from spikes_studio.component_panel import ComponentPanel
        calls = []
        owner = SimpleNamespace(show_manufacturer_library=lambda: calls.append('products'),
                                show_manufacturer_parts=lambda: calls.append('electrical'))
        ComponentPanel.manufacturer_library(SimpleNamespace(owner=owner))
        self.assertEqual(calls, ['products'])

    def test_selection_follows_identity_after_column_sort(self):
        listing = self.panel.products.listing
        listing.SetItemState(0, self.wx.LIST_STATE_SELECTED, self.wx.LIST_STATE_SELECTED)
        identity = listing.rows[0]['id']
        event = self.wx.ListEvent(self.wx.wxEVT_LIST_COL_CLICK); event.SetColumn(1)
        listing.sort(event); self.panel.products.select()
        self.assertEqual(self.panel.products.selected()['id'], identity)
        self.assertNotIn('JSON', self.panel.products.detail.GetValue())

    def test_local_metadata_roundtrip_links_exact_product_and_rejects_bad_rows(self):
        index = {'contract': 'spikes/ltspice-local-library/v1', 'root': 'local', 'files': [],
                 'symbols': [], 'diagnostics': [], 'status': {'complete': True},
                 'models': [{'id': 'test', 'name': 'LM358', 'kind': 'subckt', 'pins': ['IN', 'OUT'],
                             'source_path': 'part.sub', 'sha256': 'a' * 64}]}
        self.panel.local.accept_index(index)
        self.panel.products.search.SetValue('LM358'); self.wx.Yield()
        self.panel.products.listing.SetItemState(0, self.wx.LIST_STATE_SELECTED, self.wx.LIST_STATE_SELECTED)
        self.panel.products.select()
        self.assertTrue(self.panel.products.local_button.IsEnabled())
        self.panel.show_local_for(self.panel.products.selected())
        self.assertEqual(self.panel.book.GetSelection(), 2)
        self.panel.local.listing.SetItemState(0, self.wx.LIST_STATE_SELECTED, self.wx.LIST_STATE_SELECTED)
        self.panel.local.select()
        self.assertFalse(self.panel.local.place_button.IsEnabled())
        bad = deepcopy(index); bad['models'][0]['pins'] = [object()]
        with self.assertRaises(ValueError): self.panel.local.accept_index(bad)

    def test_imported_index_cannot_choose_its_own_source_root(self):
        from spikes_studio.document import write_json
        index = {'contract': 'spikes/ltspice-local-library/v1', 'root': '//untrusted-server/library',
                 'files': [], 'symbols': [], 'diagnostics': [], 'models': [], 'status': {'complete': True}}
        class Choice:
            def __init__(self, path): self.path = path
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def ShowModal(self): return self_wx.ID_OK
            def GetPath(self): return self.path
        self_wx = self.wx
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'index.spkindex'; write_json(path, index)
            with patch.object(self.wx, 'FileDialog', return_value=Choice(str(path))), \
                 patch.object(self.wx, 'DirDialog', return_value=Choice(folder)):
                self.panel.local.open()
            self.assertEqual(self.panel.local.index['root'], folder)


if __name__ == '__main__': unittest.main()
