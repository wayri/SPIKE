# SPDX-License-Identifier: Apache-2.0
"""Exact source ownership and lossless bounded legacy projection checks."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from python.spike_core.arc_legacy_projection import EXTENSION
from python.spike_core.arc_legacy_projection import require_legacy_arc_geometry
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.geometry_arrow import canonical_geometry_rows
from python.spike_core.spikes_layout_geometry_handoff import _supported_sources
from python.spike_core.thermal_copper_geometry import rasterize_copper

ROOT = Path(__file__).resolve().parents[2]


class ExactArcProjectionTests(unittest.TestCase):
    def design(self, source=None):
        if source is None:
            return import_kicad_design(str(ROOT / 'benchmarks/parity-import/geometry.kicad_pcb'))
        with tempfile.TemporaryDirectory(dir=ROOT / 'build/parity-test-temp') as directory:
            path = Path(directory) / 'board.kicad_pcb'
            path.write_text(source)
            return import_kicad_design(str(path))

    def test_exact_arc_has_one_canonical_and_one_legacy_representation(self):
        legacy = self.design()
        canonical = SpiDeRV2.from_v1(legacy)
        self.assertEqual(len(legacy.tracks), 8)
        self.assertEqual(len(canonical.tracks), 0)
        self.assertEqual(len(canonical.arcs), 1)
        arc = canonical.arcs[0]
        self.assertEqual((arc.start_mm, arc.mid_mm, arc.end_mm), ((10.,0.),(12.,2.),(14.,0.)))
        self.assertEqual(arc.width_mm, .3)
        self.assertEqual(canonical.to_v1().tracks, legacy.tracks)
        transported = SpiDeRV2.from_dict(json.loads(json.dumps(canonical.to_dict())))
        self.assertEqual(json.dumps(transported.to_v1().tracks), json.dumps(legacy.tracks))
        rows = canonical_geometry_rows(canonical)
        self.assertEqual(len([row for row in rows if row['kind'] == 'arc']), 1)
        self.assertEqual(len([row for row in rows if row['kind'] == 'track']), 0)
        # The layout handoff's pad envelope separately rejects this rotated pad.
        # Verify exact Arc admission on the explicitly isolated arc-only source.
        arc_only = SpiDeRV2.from_dict(canonical.to_dict())
        arc_only.pads, arc_only.pins, arc_only.components = [], [], []
        handed = _supported_sources(arc_only)
        self.assertEqual(len(handed['arcs']), 1)
        self.assertEqual(handed['tracks'], [])

    def test_interleaved_straight_tracks_restore_original_order(self):
        source = (ROOT / 'benchmarks/parity-import/geometry.kicad_pcb').read_text()
        line = '(segment (start 1 1) (end 2 1) (width .2) (layer "F.Cu") (net 1) (uuid "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))\n'
        source = source.replace('  (arc ', line+'  (arc ')
        source = source.replace('  (gr_rect ', '(segment (start 3 1) (end 4 1) (width .2) (layer "F.Cu") (net 1) (uuid "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))\n  (gr_rect ', 1)
        legacy = self.design(source)
        canonical = SpiDeRV2.from_v1(legacy)
        self.assertEqual(len(canonical.tracks), 2)
        self.assertEqual(canonical.to_v1().tracks, legacy.tracks)

    def test_duplicate_anonymous_source_arcs_have_stable_separate_owners(self):
        source = (ROOT / 'benchmarks/parity-import/geometry.kicad_pcb').read_text()
        start = source.index('  (arc ')
        end = source.index('  (gr_rect ', start)
        anonymous = source[start:end].replace('(uuid "77777777-7777-4777-8777-777777777777")', '')
        source = source[:start]+anonymous+anonymous+source[end:]
        one = SpiDeRV2.from_v1(self.design(source))
        two = SpiDeRV2.from_v1(self.design(source))
        self.assertEqual(len(one.arcs), 2)
        self.assertEqual(len({arc.source_id for arc in one.arcs}), 2)
        self.assertEqual([arc.source_id for arc in one.arcs], [arc.source_id for arc in two.arcs])
        self.assertEqual(one.tracks, [])
        self.assertEqual(len(one.to_v1().tracks), 16)

    def test_edited_exact_geometry_or_surrogate_cannot_reuse_old_chords(self):
        canonical = SpiDeRV2.from_v1(self.design())
        canonical.arcs[0].width_mm = .4
        with self.assertRaisesRegex(ValueError, 'STALE'):
            canonical.to_v1()

    def test_missing_surrogate_blocks_solver_projection_but_retains_presentation(self):
        canonical = SpiDeRV2.from_v1(self.design())
        del canonical.arcs[0].extensions[EXTENSION]
        with self.assertRaisesRegex(ValueError, 'ARC_UNSUPPORTED'):
            canonical.to_v1()
        self.assertEqual(len(canonical.to_v1(allow_unprojected_arcs=True).metadata['arcs']), 1)
        with self.assertRaisesRegex(ValueError, 'ARC_UNSUPPORTED'):
            require_legacy_arc_geometry(canonical.to_v1(allow_unprojected_arcs=True))

    def test_false_child_ownership_is_rejected_before_canonicalization(self):
        for change in ('net', 'width', 'circle', 'continuity', 'sweep'):
            legacy = self.design()
            if change == 'net':
                legacy.tracks[0]['net_id'] = 999
            elif change == 'width':
                legacy.tracks[0]['width'] = 9
            elif change == 'circle':
                legacy.tracks[0]['start'] = (100.,100.)
            elif change == 'continuity':
                legacy.tracks[1]['start'] = legacy.tracks[0]['start']
            else:
                legacy.tracks[3]['end'] = (12., -2.)
            with self.assertRaisesRegex(ValueError, 'ARC_PROJECTION_INVALID'):
                SpiDeRV2.from_v1(legacy)

    def test_canonical_json_cannot_forge_a_surrogate_by_rehashing_it(self):
        for change in ('width', 'start'):
            canonical = SpiDeRV2.from_v1(self.design())
            projection = canonical.arcs[0].extensions[EXTENSION]
            projection['children'][0]['row'][change] = 9. if change == 'width' else [100.,100.]
            projection['children_sha256'] = hashlib.sha256(json.dumps(
                projection['children'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            restored = SpiDeRV2.from_dict(json.loads(json.dumps(canonical.to_dict())))
            with self.assertRaisesRegex(ValueError, 'ARC_PROJECTION_INVALID'):
                restored.to_v1()

    def test_width_mm_and_layer_id_aliases_are_validated(self):
        legacy = self.design()
        for row in [*legacy.tracks, *legacy.metadata['arcs']]:
            row['width_mm'] = row.pop('width')
            row['layer_id'] = row.pop('layer')
        canonical = SpiDeRV2.from_v1(legacy)
        self.assertEqual(len(canonical.arcs), 1)
        legacy.tracks[0]['layer_id'] = 'B.Cu'
        with self.assertRaisesRegex(ValueError, 'ARC_PROJECTION_INVALID'):
            SpiDeRV2.from_v1(legacy)

    def test_copper_raster_does_not_drop_unprojected_arcs(self):
        canonical = SpiDeRV2.from_v1(self.design())
        del canonical.arcs[0].extensions[EXTENSION]
        legacy = canonical.to_v1(allow_unprojected_arcs=True)
        with self.assertRaisesRegex(ValueError, 'ARC_UNSUPPORTED'):
            rasterize_copper(legacy, (-1.,-1.,30.,20.), (1,1), (31.,21.), ['F.Cu'])
        canonical = SpiDeRV2.from_v1(self.design())
        canonical.arcs[0].extensions[EXTENSION]['children'][0]['row']['width'] = .4
        with self.assertRaisesRegex(ValueError, 'STALE'):
            canonical.to_v1()
