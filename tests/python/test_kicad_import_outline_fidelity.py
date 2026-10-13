# SPDX-License-Identifier: Apache-2.0
"""Original outline/cutout transport checks, not thermal solver qualification."""
from pathlib import Path
import unittest

from python.spike_core.board_outline_geometry import straight_outline_rings
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.assembly_thermal_meshing import _board_model
from python.spike_core.mcad_export_design import _rings_from_drawings

ROOT = Path(__file__).resolve().parents[2]


def rectangle(a, b):
    return {'type': 'rect', 'layer': 'Edge.Cuts', 'start': a, 'end': b}


class OutlineFidelityTests(unittest.TestCase):
    def test_import_bounds_and_holes_reach_canonical_volume_consumer(self):
        legacy = import_kicad_design(str(ROOT / 'benchmarks/parity-import/geometry.kicad_pcb'))
        self.assertEqual(legacy.metadata['board_bounds_mm'], [-1., -1., 30., 20.])
        canonical = SpiDeRV2.from_v1(legacy, source_digest=legacy.metadata['source_sha256']).to_dict()
        rings = canonical['metadata']['board_outline_rings']
        self.assertEqual([row['role'] for row in rings], ['outer', 'cutout'])
        layers = [layer for layer in canonical['layers'] if layer.get('extensions', {}).get('spike.v1.stackup')]
        compiled, _ = _board_model(canonical, {'representation': 'layer_homogenized',
                                  'layer_materials': {layer['id']: 'reviewed-effective' for layer in layers}})
        # Independent original source dimensions: 31*21 - 2*2 square mm.
        self.assertAlmostEqual(compiled['evidence']['board_area_mm2'], 647., places=9)
        self.assertEqual(len(compiled['solids']), 3)
        volume = 0.
        for solid in compiled['solids']:
            shape = solid['shape']
            self.assertEqual(len(shape['holes_mm']), 1)
            self.assertEqual(set(map(tuple, shape['holes_mm'][0])), {(6.,6.),(8.,6.),(8.,8.),(6.,8.)})
            volume += 647. * (shape['z_max_mm'] - shape['z_min_mm'])
        self.assertAlmostEqual(volume, 1035.2, places=9)

    def test_mcad_fallback_uses_same_outer_cutout_topology(self):
        drawings = [rectangle([-1,-1],[30,20]), rectangle([6,6],[8,8])]
        self.assertEqual(_rings_from_drawings(drawings), straight_outline_rings(drawings))
        # Input order and winding do not change deterministic ownership.
        self.assertEqual(straight_outline_rings(drawings), straight_outline_rings(list(reversed(drawings))))

    def test_open_branched_overlapping_and_nested_loops_are_rejected(self):
        for rows in (
            [{'type':'line','layer':'Edge.Cuts','start':[0,0],'end':[1,0]}],
            [rectangle([0,0],[10,10]), rectangle([20,20],[21,21])],
            [rectangle([0,0],[10,10]), rectangle([0,2],[2,4])],
            [rectangle([0,0],[10,10]), rectangle([2,2],[6,6]), rectangle([3,3],[4,4])],
            [rectangle([0,0],[10,10]), rectangle([2,2],[6,6]), rectangle([5,5],[7,7])],
            [rectangle([0,0],[10,10]), rectangle([0,0],[10,10])],
        ):
            with self.assertRaises(ValueError):
                straight_outline_rings(rows)

    def test_nonfinite_and_curve_substitution_are_rejected(self):
        with self.assertRaises(ValueError):
            straight_outline_rings([rectangle([0,0],[float('nan'),1])])
        with self.assertRaises(ValueError):
            straight_outline_rings([{'type':'arc','layer':'Edge.Cuts'}])
