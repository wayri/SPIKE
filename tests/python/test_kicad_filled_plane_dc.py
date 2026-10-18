# SPDX-License-Identifier: Apache-2.0
"""KiCad filled-plane import, hole-preserving mesh and DC execution regression."""
import tempfile
import unittest
from pathlib import Path

from python.spike_core.contracts import AnalysisSpec
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.filled_copper_path import FilledCopperPath
from python.spike_core.hybrid_mesh import (
    _normalize_filled_zone_polygon, _polygon_area,
    _polygon_is_contained_in, _segment_inside_polygon, build_hybrid_mesh,
)
from python.spike_core.solver_plugins import default_solver_registry


class KicadFilledPlaneDcTests(unittest.TestCase):
    def test_retraced_cutout_survives_import_mesh_and_dc(self):
        # Independently authored 8 x 6 mm plane minus a 4 x 2 mm void.
        # KiCad encodes the hole with an exactly retraced connector, not copper.
        path = [(0,0),(8,0),(8,6),(0,6),(0,0),(6,4),(6,2),(2,2),(2,4),(6,4)]
        points = ' '.join(f'(xy {x} {y})' for x,y in path)
        source = f'''(kicad_pcb (version 20240108) (generator "SPIKE-regression")
          (general (thickness 1.6))
          (layers (0 "F.Cu" signal) (31 "B.Cu" signal))
          (net 0 "") (net 1 "VCC")
          (zone (net 1) (net_name "VCC") (layer "F.Cu")
            (hatch edge 0.5) (connect_pads (clearance 0.2)) (min_thickness 0.1)
            (fill yes (thermal_gap 0.2) (thermal_bridge_width 0.2))
            (polygon (pts (xy 0 0) (xy 8 0) (xy 8 6) (xy 0 6)))
            (filled_polygon (layer "F.Cu") (pts {points}))))'''
        with tempfile.TemporaryDirectory() as directory:
            board = Path(directory) / 'plane-with-cutout.kicad_pcb'
            board.write_text(source, encoding='utf-8')
            design = import_kicad_design(str(board))
        self.assertEqual(len(design.zones), 1)
        zone = design.zones[0]
        domain = _normalize_filled_zone_polygon([tuple(p) for p in zone['points']])
        self.assertIsInstance(domain, FilledCopperPath)
        spec = AnalysisSpec(mode='dc', net_names=['VCC'],
            sources=[{'position_mm':[1,3], 'layer':'F.Cu', 'voltage_v':5}],
            loads=[{'position_mm':[7,3], 'layer':'F.Cu', 'current_a':0.1}],
            mesh={'zone_cell_mm':1.0, 'node_tolerance_mm':0.01})
        mesh = build_hybrid_mesh(design, spec)
        self.assertEqual(mesh.geometry_counts['zone'], 1)
        self.assertFalse(mesh.truncated)
        self.assertFalse([issue for issue in mesh.issues if issue.severity == 'error'])
        cells = [c for c in mesh.cells if c['source_id'] == zone['id']]
        self.assertTrue(cells)
        self.assertAlmostEqual(sum(_polygon_area([(p[0],p[1]) for p in c['vertices_mm']]) for c in cells),40.0,places=8)
        for branch in mesh.branches:
            a,b = mesh.nodes[branch.node_p],mesh.nodes[branch.node_n]
            self.assertTrue(_segment_inside_polygon((a.x_mm,a.y_mm),(b.x_mm,b.y_mm),domain,1e-10))
        result = default_solver_registry().run(design,spec)
        self.assertEqual(result.status,'completed')
        self.assertEqual(result.model_status,'approximate')
        samples = result.fields['visualization']['scalar_fields']['current_density_a_mm2']
        plane_samples = [sample for sample in samples if sample.get('vertices_mm')]
        self.assertTrue(plane_samples)
        for sample in plane_samples:
            self.assertTrue(_polygon_is_contained_in([(p[0],p[1]) for p in sample['vertices_mm']],domain,1e-10))


if __name__ == '__main__':
    unittest.main()
