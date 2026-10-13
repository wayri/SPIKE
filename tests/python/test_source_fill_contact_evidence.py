# SPDX-License-Identifier: Apache-2.0
"""Contact observation preserves full source evidence without generating a mesh."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.spider_v2_schema import content_digest
from python.spike_core.zone_pad_connection_evidence import (
    build_zone_pad_connection_evidence, validate_zone_pad_connection_evidence,
)

ROOT = Path(__file__).resolve().parents[2]


class SourceFillContactEvidenceTests(unittest.TestCase):
    def test_holed_source_contacts_preserve_all_records_and_provenance(self):
        points = [(0, 0), (8, 0), (8, 6), (0, 6), (0, 0),
                  (6, 4), (6, 2), (2, 2), (2, 4), (6, 4)]
        pts = ' '.join(f'(xy {x} {y})' for x, y in points)
        pads = ''.join(
            f'(footprint "Fixture:Pad" (layer "F.Cu") (at {x} {y}) '
            f'(uuid "fp-{name}") (property "Reference" "{name}") '
            f'(pad "1" smd rect (at 0 0) (size 0.2 0.2) (layers "F.Cu") '
            f'(net 1 "VCC") (uuid "{name}")))'
            for name, x, y in [('bridge-gap', 4.5, 3), ('copper', 1, 1), ('hole-edge', 2, 3)]
        )
        source = (
            '(kicad_pcb (version 20260101) (layers (0 "F.Cu" signal)) (net 1 "VCC") '
            '(zone (net 1) (net_name "VCC") (layer "F.Cu") (uuid "zone") '
            '(connect_pads yes (clearance 0.2)) '
            '(fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4)) '
            f'(polygon (pts (xy 0 0) (xy 8 0) (xy 8 6) (xy 0 6))) '
            f'(filled_polygon (layer "F.Cu") (pts {pts}))) {pads})'
        )
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / 'contact.kicad_pcb'
            path.write_text(source, encoding='utf-8')
            design = SpiDeRV2.from_v1(import_kicad_design(str(path)))
        with patch('python.spike_core.hybrid_mesh.prepare_filled_path',
                   side_effect=AssertionError('Contact evidence must not validate a mesh domain')):
            report = build_zone_pad_connection_evidence(design)
            validate_zone_pad_connection_evidence(report, source_geometry=design)
        pad_ids = {pad.id: pad.source_id for pad in design.pads}
        observations = {pad_ids[row['pad_id']]: row['observation'] for row in report['records']}
        self.assertEqual(len(report['records']), 3)
        self.assertEqual(observations['bridge-gap'], 'no_source_filled_copper_contact')
        self.assertEqual(observations['copper'], 'source_filled_copper_contact')
        self.assertEqual(observations['hole-edge'], 'source_filled_copper_contact')
        self.assertEqual(report['source']['design_sha256'], content_digest(design.to_dict()))
        self.assertFalse(report['qualification']['solver_ready'])
        self.assertFalse(report['qualification']['physics_ready'])


if __name__ == '__main__':
    unittest.main()
