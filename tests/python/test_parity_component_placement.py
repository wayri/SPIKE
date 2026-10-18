# SPDX-License-Identifier: Apache-2.0
"""Independent top/bottom datum and source-bound native placement checks."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.parity_component_placement_math import bounds, native_vertices, spike_vertices
from scripts.parity_native_step_placement_gate import validate_receipt

ROOT = Path(__file__).resolve().parents[2]


class PlacementDatumTests(unittest.TestCase):
    def test_zero_angle_front_and_back_cube_have_independent_depth_bounds(self):
        front = spike_vertices(native_vertices('front', 0., [0., 0., 0.], [0., 0., 0.], [1., 1., 1.]))
        back = spike_vertices(native_vertices('back', 0., [0., 0., 0.], [0., 0., 0.], [1., 1., 1.]))
        for actual, expected in zip(bounds(front), [20., 7., -4., 22., 10., 0.]):
            self.assertAlmostEqual(actual, expected, places=12)
        for actual, expected in zip(bounds(back), [20., 10., 1.6, 22., 13., 5.6]):
            self.assertAlmostEqual(actual, expected, places=12)

    def test_board_top_bottom_and_xy_datum_are_not_recentered(self):
        self.assertEqual(spike_vertices([[-1., 1., .8], [30., -20., -.8]]),
                         [[-1., -1., 0.], [30., 20., 1.6]])

    def test_step_copper_datum_preserves_observed_exporter_clearance(self):
        # Independent copper control: core [0,1.53], 0.035 mm copper each side.
        converted = spike_vertices([[0., 0., 1.565], [0., 0., -.035]], top_z=1.565)
        for actual, expected in zip(converted, [[0., 0., 0.], [0., 0., 1.6]]):
            for a, b in zip(actual, expected):
                self.assertAlmostEqual(a, b, places=12)
        front = spike_vertices(native_vertices('front', 0., [0., 0., 0.], [0., 0., 0.], [1., 1., 1.],
                                               surface_z=1.615), top_z=1.565)
        self.assertAlmostEqual(max(p[2] for p in front), -.05, places=12)


class NativeStepPlacementGateTests(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads((ROOT / 'docs/validation/parity/WF01-S04C3.json').read_text())

    def test_current_native_reference_passes(self):
        validate_receipt(self.receipt, ROOT)

    def test_completion_scope_and_source_integrity(self):
        for mutation in ('failed', 'qualified', 'source', 'foreign'):
            receipt = copy.deepcopy(self.receipt)
            if mutation == 'failed':
                receipt['status'] = 'failed'
            elif mutation == 'qualified':
                receipt['source_projection_enabled'] = True
            elif mutation == 'source':
                receipt['validators']['scripts/parity_component_placement_math.py'] = '0' * 64
            else:
                receipt['reference'] = '../foreign.json'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_receipt(receipt, ROOT)

    def test_geometry_coverage_and_datum_are_recomputed(self):
        reference = json.loads((ROOT / self.receipt['reference']).read_text())
        with tempfile.TemporaryDirectory(dir=ROOT / 'build/parity-test-temp') as directory:
            for mutation in ('missing', 'duplicate', 'vertices', 'volume', 'spike', 'vectors', 'clearance', 'export', 'datum'):
                modified = copy.deepcopy(reference)
                if mutation == 'missing':
                    modified['cases'].pop()
                elif mutation == 'duplicate':
                    modified['cases'][0] = copy.deepcopy(modified['cases'][1])
                elif mutation == 'vertices':
                    modified['cases'][0]['native']['vertices_mm'][0][0] += .1
                elif mutation == 'volume':
                    modified['cases'][0]['native']['volume_mm3'] = float('nan')
                elif mutation == 'spike':
                    modified['cases'][0]['spike_vertices_mm'][0][2] += .05
                elif mutation == 'vectors':
                    modified['cases'][0]['source_inputs']['scale'] = [1., 1., 1.]
                elif mutation == 'clearance':
                    modified['datum_controls']['front']['observed_mounting_clearance_mm'] = 0.
                elif mutation == 'export':
                    modified['exports']['front-90-export.json']['returncode'] = 1
                else:
                    modified['frame']['physical_copper_surfaces_mm']['front'] = 1.53
                path = Path(directory) / 'reference.json'
                path.write_text(json.dumps(modified))
                receipt = copy.deepcopy(self.receipt)
                receipt['reference'] = path.relative_to(ROOT).as_posix()
                receipt['reference_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    validate_receipt(receipt, ROOT)


if __name__ == '__main__':
    unittest.main()
