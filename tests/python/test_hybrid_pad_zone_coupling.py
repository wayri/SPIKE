# SPDX-License-Identifier: MIT
"""Zone contact must not be duplicated by a centroid-dependent pad shortcut."""
import unittest

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.hybrid_mesh import _Builder


class HybridPadZoneCouplingTests(unittest.TestCase):
    def builder(self, target, with_conductors=False):
        design = DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            nets=[{"id": 1, "name": "VCC"}],
            zones=[{"id": "zone", "net_name": "VCC", "layer": "F.Cu",
                    "points": [[-2, -2], [2, -2], [2, 2], [-2, 2]]}],
            pads=[{"id": "pad", "net_name": "VCC", "layers": ["F.Cu"],
                   "at": [0, 0], "shape": "rect", "size": [2, 2]}],
            tracks=([{"id": "track", "net_name": "VCC", "layer": "F.Cu",
                      "start": [-1.5, 0], "end": [.25, 0], "width": .2}] if with_conductors else []),
            vias=([{"id": "via", "net_name": "VCC", "layers": ["F.Cu", "B.Cu"],
                    "at": [-.25, .25], "drill": .3}] if with_conductors else []),
        )
        return _Builder(design, AnalysisSpec(mode="dc", net_names=["VCC"],
            mesh={"target_size_mm": target, "zone_cell_mm": target}))

    def test_zone_contact_has_no_second_centroid_based_pad_path(self):
        for target in (1.0, .5, .25):
            with self.subTest(target=target):
                builder = self.builder(target)
                mesh = builder.build()
                zone_nodes = {node for region in builder.zone_regions for node in region["nodes"]}
                shortcuts = [b for b in mesh.branches if b.kind == "pad_attachment" and b.node_p in zone_nodes]
                self.assertEqual(shortcuts, [], "Zone contact must be owned exclusively by explicit pad-zone coupling")
                self.assertTrue(any(b.kind == "pad_zone_attachment" for b in mesh.branches))

    def test_track_and_via_pad_attachments_are_preserved(self):
        builder = self.builder(.5, with_conductors=True)
        builder.tracks()
        track_nodes = {b.node_p for b in builder.mesh.branches} | {b.node_n for b in builder.mesh.branches}
        builder.vias()
        via_nodes = {node for b in builder.mesh.branches if b.kind == "via" for node in (b.node_p, b.node_n)}
        builder.zones()
        builder.pads()
        attached = {b.node_p for b in builder.mesh.branches if b.kind == "pad_attachment"}
        self.assertTrue(attached & track_nodes)
        self.assertTrue(attached & via_nodes)


if __name__ == "__main__":
    unittest.main()
