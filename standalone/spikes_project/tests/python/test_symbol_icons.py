# SPDX-License-Identifier: Apache-2.0
import os
import sys
import unittest
from pathlib import Path


STUDIO = Path(__file__).resolve().parents[2] / "studio" / "python"
sys.path.insert(0, str(STUDIO))

from spikes_studio.symbol_icons import CANONICAL_KEYS, SymbolImages, key_for


class SymbolIconContractTests(unittest.TestCase):
    def test_aliases_share_canonical_indices(self):
        indices = {key: index for index, key in enumerate(CANONICAL_KEYS)}
        for alias, canonical in (
            ("R", "resistor"), ("operational amplifier", "opamp"),
            ("nmos_enhancement", "mosfet"), ("ntc_thermistor", "thermal"),
            ("ptc_resettable_fuse", "fuse"), ("genericcomponent", "generic"),
            ('op','operating_point'),('param','parameter'),('rect','rectangle'),
        ):
            self.assertEqual(indices[key_for(alias)], indices[canonical])

    def test_unknowns_have_clear_bounded_fallback(self):
        self.assertEqual(key_for("vendor-private-part-8472"), "generic")
        self.assertEqual(len(CANONICAL_KEYS), len(set(CANONICAL_KEYS)))
        self.assertLessEqual(len(CANONICAL_KEYS), 40)


@unittest.skipUnless(os.environ.get("SPIKES_TEST_WX"), "set SPIKES_TEST_WX=1 for native wx bitmap checks")
class NativeWxSymbolIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx
        cls.wx = wx
        cls.app = wx.App.Get() or wx.App(False)
        cls.palette = dict(field="#ffffff", panel="#ffffff", fg="#202830", muted="#66717d", accent="#2863a2", danger="#b44040")

    def test_fixed_image_count_and_dimensions(self):
        images = SymbolImages(None, self.palette, size=20)
        self.assertEqual(images.image_list.GetImageCount(), len(CANONICAL_KEYS))
        dimensions = images.image_list.GetSize(0)
        self.assertEqual(tuple(dimensions), (20, 20))

    def test_rcl_bitmaps_are_visually_distinct(self):
        from spikes_studio.symbol_icons import bitmap
        def rgb_bytes(key):
            image = bitmap(key, self.palette).ConvertToImage()
            return bytes(image.GetDataBuffer())
        self.assertEqual(len({rgb_bytes("resistor"), rgb_bytes("capacitor"), rgb_bytes("inductor")}), 3)

    def test_assigns_tree_and_list_with_expected_indices(self):
        frame = self.wx.Frame(None)
        try:
            tree = self.wx.TreeCtrl(frame)
            tree_images = SymbolImages(tree, self.palette)
            listing = self.wx.ListCtrl(frame, style=self.wx.LC_REPORT)
            list_images = SymbolImages(listing, self.palette)
            self.assertEqual(tree_images.index("nmos_enhancement"), tree_images.index("mosfet"))
            self.assertEqual(list_images.index("operational_amplifier"), list_images.index("opamp"))
            self.assertEqual(tree.GetImageList().GetImageCount(), len(CANONICAL_KEYS))
            self.assertEqual(listing.GetImageList(self.wx.IMAGE_LIST_SMALL).GetImageCount(), len(CANONICAL_KEYS))
        finally:
            frame.Destroy()


if __name__ == "__main__":
    unittest.main()
