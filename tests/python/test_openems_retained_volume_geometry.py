# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original analytic geometry oracles, not mocked field-solver validation."""
import copy
import inspect
import unittest
from unittest.mock import Mock, patch

import numpy as np

from extensions.openems_suite.retained_volume_geometry import (
    compile_retained_volume_geometry, emit_retained_volume_geometry, _tetra_intersects_open_box,
)
from python.spike_core.assembly_field_handoff import prepare_assembly_field_handoff
from python.spike_core.multiboard_identity import canonical_json_digest
from tests.python.test_assembly_tetra_thermal import cube, exterior


def fixture(mesh=None):
    left = mesh or cube(unit='mm')
    right = cube(unit='mm')
    parts, bodies = [], []
    for name, mesh, x in [('return', left, 0), ('signal', right, 2)]:
        parts.append({'id': name, 'model_id': name, 'part_type': 'mechanical',
                      'frame': {'frame_id': name, 'transform':
                                [1,0,0,x,0,1,0,0,0,0,1,0,0,0,0,1]}})
        bodies.append({'occurrence_id': name, 'reference_id': name, 'source_sha256': 'a'*64,
                       'mesh': mesh, 'material_map': {'k': 'metal'},
                       'boundary_faces': [{'id': str(i), 'vertices': face}
                                          for i, face in enumerate(exterior(mesh))]})
    chosen = []
    for body, x in zip(bodies, (1, 0)):
        face = next(f for f in body['boundary_faces'] if
                    all(body['mesh']['vertices'][i][0] == x for i in f['vertices']) and
                    np.mean([body['mesh']['vertices'][i][1] for i in f['vertices']]) >
                    np.mean([body['mesh']['vertices'][i][2] for i in f['vertices']]))
        chosen.append({'occurrence_id': body['occurrence_id'], 'face_id': face['id']})
    request = {'contract': 'spike/assembly-field-handoff-request/v1', 'domain': 'em',
               'assembly': {'contract': 'spike/assembly-ir/v1', 'assembly_id': 'original',
                            'name': 'Original conductor pair', 'parts': parts},
               'materials': [{'id': 'metal', 'provenance': 'Original geometry oracle',
                              'relative_permittivity': 1, 'relative_permeability': 1,
                              'conductivity_s_m': 5.8e7}], 'bodies': bodies,
               'ports': [{'id': 'p1', 'return': chosen[0], 'signal': chosen[1],
                          'reference_impedance_ohm': 50}]}
    ports = [{'id': 'p1', 'start_m': [.001,.0006,.0002], 'stop_m': [.002,.0007,.0003],
              'direction': 'x', 'excite': True}]
    return request, ports


def surface_volume(primitive):
    # Divergence theorem, using a translated origin to avoid cancellation.
    vertices = np.array(primitive['vertices_m'])
    vertices -= vertices[0]
    return sum(np.dot(vertices[a], np.cross(vertices[b], vertices[c])) / 6
               for a, b, c in primitive['faces'])


def compile_request(request, ports):
    return compile_retained_volume_geometry(prepare_assembly_field_handoff(request), ports)


class RetainedVolumeGeometryTests(unittest.TestCase):
    def test_exact_cube_surfaces_volume_and_ownership(self):
        request, ports = fixture()
        saved = copy.deepcopy(request)
        result = compile_request(request, ports)
        self.assertEqual(request, saved)
        self.assertEqual(result['surface_face_count'], 24)
        self.assertEqual(len(result['primitives']), 2)
        for primitive in result['primitives']:
            self.assertEqual(len(primitive['faces']), 12)
            self.assertAlmostEqual(surface_volume(primitive), 1e-9, delta=1e-23)
            self.assertEqual(len(primitive['cell_ids']), 6)
            self.assertTrue(primitive['source_object_ids'])
        self.assertEqual(result['bounds_m'], {'start': [0.,0.,0.], 'stop': [.003,.001,.001]})
        self.assertEqual(result['ports'][0]['reference_impedance_ohm'], 50)
        self.assertEqual(result['ports'][0]['terminal_convention'], 'start_return_stop_signal')
        self.assertFalse(result['production_qualified'])

    def test_cavity_survives_surface_extraction(self):
        mesh = cube(n=3, unit='mm')
        mesh['cells'] = [c for c in mesh['cells'] if not all(
            1/3 <= mesh['vertices'][i][axis] <= 2/3 for i in c['vertices'] for axis in range(3))]
        mesh['counts']['cells'] = len(mesh['cells'])
        request, ports = fixture(mesh)
        # Choose identical tiny line terminals within matching exterior triangles.
        left = request['bodies'][0]
        face = next(f for f in left['boundary_faces'] if f['id'] == request['ports'][0]['return']['face_id'])
        center = np.mean([left['mesh']['vertices'][i] for i in face['vertices']], axis=0) * .001
        ports[0]['start_m'] = center.tolist()
        ports[0]['stop_m'] = [.002, float(center[1]), float(center[2])]
        result = compile_request(request, ports)
        solid = next(p for p in result['primitives'] if p['occurrence_id'] == 'return')
        self.assertAlmostEqual(surface_volume(solid), (1 - 1/27) * 1e-9, delta=2e-23)
        inner = [f for f in solid['faces'] if all(
            .001/3 - 1e-15 <= solid['vertices_m'][i][axis] <= .002/3 + 1e-15
            for i in f for axis in range(3))]
        self.assertEqual(len(inner), 12)

    def test_rotated_translated_placement_applied_once(self):
        request, ports = fixture()
        # Rotate each occurrence 90 degrees around z; apply one common translation.
        for part in request['assembly']['parts']:
            x = part['frame']['transform'][3]
            part['frame']['transform'] = [0,-1,0,10,1,0,0,20+x,0,0,1,30,0,0,0,1]
        for key in ('start_m', 'stop_m'):
            x, y, z = ports[0][key]
            ports[0][key] = [.01-y, .02+x, .03+z]
        ports[0]['direction'] = 'y'
        result = compile_request(request, ports)
        np.testing.assert_allclose(result['bounds_m']['start'], [.009,.02,.03], atol=1e-16)
        for primitive in result['primitives']:
            self.assertAlmostEqual(surface_volume(primitive), 1e-9, delta=1e-22)

    def test_material_interface_is_retained(self):
        request, ports = fixture()
        body = request['bodies'][0]
        # One tetrahedron becomes a dielectric; select one away from the terminal face.
        face_id = request['ports'][0]['return']['face_id']
        face = next(f for f in body['boundary_faces'] if f['id'] == face_id)
        cell = next(c for c in body['mesh']['cells'] if not set(face['vertices']) <= set(c['vertices']))
        cell['material_id'] = 'd'
        body['material_map']['d'] = 'dielectric'
        request['materials'].append({'id': 'dielectric', 'provenance': 'Original interface oracle',
                                    'relative_permittivity': 4, 'relative_permeability': 1,
                                    'conductivity_s_m': 0})
        result = compile_request(request, ports)
        self.assertGreater(result['surface_face_count'], 24)
        self.assertAlmostEqual(sum(surface_volume(p) for p in result['primitives']), 2e-9, delta=1e-22)
        self.assertTrue(any(p['material']['relative_permittivity'] == 4 for p in result['primitives']))

    def test_port_rectangles_and_identity_rejections(self):
        changes = [lambda p: p[0].update(id='missing'), lambda p: p[0].update(direction='z'),
                   lambda p: p[0].update(excite=False), lambda p: p[0].update(excite=1),
                   lambda p: p[0].update(start_m=[.001,.0006,float('nan')]),
                   lambda p: p[0].update(stop_m=[.002,.0007,.0008]),
                   lambda p: p[0].update(start_m=[.0011,.0006,.0002]),
                   lambda p: p[0].update(extra=True), lambda p: p.clear()]
        for change in changes:
            request, ports = fixture()
            change(ports)
            with self.subTest(change=change), self.assertRaises(ValueError):
                compile_request(request, ports)

    def test_nonconductor_unknown_connectivity_stale_and_budget_rejections(self):
        request, ports = fixture()
        handoff = prepare_assembly_field_handoff(request)
        for change in [lambda h: h['materials'][0].update(conductivity_s_m=0),
                       lambda h: h['execution_issues'].append({'code': 'UNKNOWN'}),
                       lambda h: h.update(domain='thermal')]:
            bad = copy.deepcopy(handoff)
            change(bad)
            bad['handoff_digest'] = canonical_json_digest({k:v for k,v in bad.items() if k != 'handoff_digest'})
            with self.assertRaises(ValueError):
                compile_retained_volume_geometry(bad, ports)
        handoff['mesh']['vertices'][0][0] += .1
        with self.assertRaisesRegex(ValueError, 'stale'):
            compile_retained_volume_geometry(handoff, ports)
        with patch('extensions.openems_suite.retained_volume_geometry.MAX_SURFACE_FACES', 23):
            with self.assertRaisesRegex(ValueError, 'budget'):
                compile_request(request, ports)

    def test_intervening_conductor_rejected_in_rectangle_and_line_ports(self):
        for line in (False, True):
            request, ports = fixture()
            obstacle = copy.deepcopy(request['bodies'][0])
            obstacle.update(occurrence_id='obstacle', reference_id='obstacle')
            obstacle['mesh']['vertices'] = [[x * .1 for x in p] for p in obstacle['mesh']['vertices']]
            request['bodies'].append(obstacle)
            request['assembly']['parts'].append({'id': 'obstacle', 'model_id': 'obstacle',
                'part_type': 'mechanical', 'frame': {'frame_id': 'obstacle', 'transform':
                [1,0,0,1.4,0,1,0,.6,0,0,1,.2,0,0,0,1]}})
            if line:
                ports[0]['start_m'][1:] = [.00065,.00025]
                ports[0]['stop_m'][1:] = [.00065,.00025]
            with self.assertRaisesRegex(ValueError, 'interior intersects'):
                compile_request(request, ports)

    def test_port_intersection_analytical_simplex(self):
        # Independent shape oracle: x,y,z >= 0 and x+y+z <= 1.
        tetra = [[0.,0.,0.], [1.,0.,0.], [0.,1.,0.], [0.,0.,1.]]
        self.assertFalse(_tetra_intersects_open_box(tetra, [.8,.8,.8], [.9,.9,.9]))
        self.assertTrue(_tetra_intersects_open_box(tetra, [.1,.1,.1], [.2,.2,.2]))
        self.assertTrue(_tetra_intersects_open_box(tetra, [.1,.1,0.], [.5,.1,0.]))
        self.assertFalse(_tetra_intersects_open_box(tetra, [.1,.1,-.1], [.5,.1,-.1]))

    def test_emitter_exact_polyhedra_and_fail_before_mutation(self):
        request, ports = fixture()
        result = compile_request(request, ports)
        csx = Mock()
        namespace = {}
        exec(inspect.getsource(emit_retained_volume_geometry), namespace)
        namespace['emit_retained_volume_geometry'](csx, result)
        self.assertEqual(csx.AddMaterial.call_count, 2)
        material = csx.AddMaterial.return_value
        self.assertEqual(material.AddPolyhedron.call_count, 2)
        self.assertEqual(material.AddPolyhedron.return_value.AddFace.call_count, 24)
        self.assertEqual(material.AddPolyhedron.return_value.AddVertex.call_count, 16)
        material.AddBox.assert_not_called()
        self.assertEqual(csx.AddMaterial.call_args.kwargs, {'epsilon': 1, 'mue': 1, 'kappa': 5.8e7})
        result['primitives'][0]['vertices_m'][0][0] += .1
        csx.reset_mock()
        with self.assertRaisesRegex(ValueError, 'stale'):
            namespace['emit_retained_volume_geometry'](csx, result)
        csx.AddMaterial.assert_not_called()


if __name__ == '__main__':
    unittest.main()
