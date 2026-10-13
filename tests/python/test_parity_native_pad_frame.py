# SPDX-License-Identifier: Apache-2.0
"""Native source and geometry consumers must agree on the pad frame."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from python.core.board_parser import KicadParser
from scripts.capture_parity_native_geometry import shape_source
from scripts.parity_native_geometry_gate import (
    validate_native_facts, validate_pad_cohort, validate_kicad_source_geometry,
    validate_native_export_geometry,
)

ROOT = Path(__file__).resolve().parents[2]


class NativePadFrameTests(unittest.TestCase):
    def setUp(self):
        self.source = ROOT / 'benchmarks/parity-import/geometry.kicad_pcb'
        self.native = json.loads((ROOT / 'docs/validation/parity/WF01-S02-native-geometry.json').read_text(encoding='utf-8'))

    def test_native_48_pose_and_8_supported_shape_cases_recompute_current_geometry(self):
        validate_native_facts(self.native, self.source)
        validate_pad_cohort(self.native, self.source)

    def test_native_angle_and_extra_reflection_cannot_be_hidden_by_counts(self):
        payload = json.loads((ROOT / 'docs/validation/parity/WF01-S02-import.json').read_text(encoding='utf-8'))
        validate_kicad_source_geometry(payload, self.native)
        for mutation in ('angle', 'position', 'source_angle'):
            changed = copy.deepcopy(payload)
            pad = changed['design']['pads'][0]
            if mutation == 'angle': pad['extensions']['spike.v1']['rotation'] = 90
            elif mutation == 'source_angle': pad['extensions']['spike.v1']['native_pad_rotation_deg'] = 90
            else: pad['center_mm'][0] = 19
            with self.assertRaisesRegex(ValueError, 'pose or physical perimeter'):
                validate_kicad_source_geometry(changed, self.native)

    def test_native_export_gate_rejects_missing_cutout_or_changed_net(self):
        native = json.loads((ROOT / 'docs/validation/parity/WF01-S04B-native-geometry.json').read_text(encoding='utf-8'))
        payload = json.loads((ROOT / 'docs/validation/parity/WF01-S04B-import.json').read_text(encoding='utf-8'))
        archive = ROOT / 'benchmarks/parity-import/geometry-native-odb-qualified.zip'
        validate_native_export_geometry(payload, native, archive)
        for mutation in ('cutout', 'net', 'width'):
            changed = copy.deepcopy(payload)
            if mutation == 'cutout': changed['design']['metadata']['board_outline_rings'].pop()
            elif mutation == 'net': changed['design']['arcs'][0]['net_id'] = 'missing'
            else: changed['design']['arcs'][0]['width_mm'] = .6
            with self.assertRaises(ValueError):
                validate_native_export_geometry(changed, native, archive)

    def test_circular_anchor_union_remains_explicitly_unsupported(self):
        base = self.source.read_text(encoding='utf-8')
        text = shape_source(base, 'B.Cu', 90, 'custom').replace('(anchor rect)', '(anchor circle)')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom.kicad_pcb'
            path.write_text(text, encoding='utf-8')
            with redirect_stdout(StringIO()): parser = KicadParser(path)
            self.assertEqual(parser.pads[0]['custom_geometry']['status'], 'unsupported')
            self.assertEqual(parser.pads[0]['custom_geometry']['reason'], 'anchor_circle_union_pending')


if __name__ == '__main__':
    unittest.main()
