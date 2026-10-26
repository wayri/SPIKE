# SPDX-License-Identifier: Apache-2.0
"""Independent geometry/Cartesian polynomial oracles; no CFD solves."""
import copy
import itertools
import unittest

import numpy as np

from python.spike_core.solvers.thermal_fluid.flow.cfd_tetra_mesh import admit_cfd_tetra_mesh
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_cfd_refinement import refine_centroid_tetrahedra, refine_boundary_edge_stars
from tests.python.test_cfd_tetra_stokes import box_mesh


def field_layout(raw):
    # Independently construct the documented first-occurrence edge numbering.
    xyz = np.array(raw['vertices'])
    edges, local = {}, []
    nodes = list(xyz)
    for cell in raw['cells']:
        row = cell.copy()
        for pair in itertools.combinations(cell, 2):
            edge = tuple(sorted(pair))
            if edge not in edges:
                edges[edge] = len(nodes)
                nodes.append((xyz[edge[0]]+xyz[edge[1]])/2)
            row.append(edges[edge])
        local.append(row)
    return np.array(nodes), np.array(local)


def velocity(x):
    a, b, c = x.T
    return np.c_[1+2*a-3*b+4*c+a*a+2*a*b-3*a*c+4*b*b+5*b*c-6*c*c,
                 a*a-b*b+2*b*c+3*a, c*c+3*a*b-a*c+2*b+7]


def pressure(x):
    return 7+2*x[:, 0]-3*x[:, 1]+5*x[:, 2]


class CentroidRefinementTests(unittest.TestCase):
    def test_partition_faces_and_unselected_neighbour_conformity(self):
        raw = box_mesh(1, shear=True)
        original = copy.deepcopy(raw)
        answer = refine_centroid_tetrahedra(raw, [0])
        mesh, info = answer['mesh'], answer['provenance']
        self.assertEqual(raw, original)
        self.assertEqual(mesh['vertices'][:len(raw['vertices'])], raw['vertices'])
        self.assertEqual(mesh['boundary_patches'], raw['boundary_patches'])
        self.assertEqual(mesh['cells'][1:6], raw['cells'][1:6])
        old, new = admit_cfd_tetra_mesh(raw), admit_cfd_tetra_mesh(mesh)
        self.assertEqual(len(new['components']), 1)
        self.assertEqual(new['cells'].shape, (9, 4))
        self.assertAlmostEqual(sum(new['volumes']), 1., places=13)
        children = info['children'][0]['child_cell_ids']
        np.testing.assert_allclose(new['volumes'][children], old['volumes'][0]/4,
                                   rtol=2e-14, atol=0)
        old_faces = {tuple(sorted(f)) for f in old['face_vertices']}
        new_faces = {tuple(sorted(f)) for f in new['face_vertices']}
        self.assertTrue(old_faces <= new_faces)
        self.assertTrue(info['full_source_and_destination_geometry_admitted'])
        self.assertFalse(info['load_qualified'])

    def test_exact_cartesian_quadratic_velocity_and_affine_pressure(self):
        raw = box_mesh(1, shear=True, shift=3.)
        xyz, local = field_layout(raw)
        fields = {'P2_nodes_m': xyz, 'cell_P2_nodes': local,
                  'P1_nodes_m': raw['vertices'], 'tetrahedra': raw['cells'],
                  'P2_velocity_m_s': velocity(xyz), 'P1_pressure_pa': pressure(np.array(raw['vertices']))}
        answer = refine_centroid_tetrahedra(raw, [4, 0], initial_fields=fields)
        guess = answer['initial_guess']
        np.testing.assert_allclose(guess['P2_velocity_m_s'], velocity(guess['P2_nodes_m']),
                                   rtol=2e-14, atol=2e-14)
        np.testing.assert_allclose(guess['P1_pressure_pa'], pressure(guess['P1_nodes_m']),
                                   rtol=2e-14, atol=2e-14)
        self.assertEqual(guess['status'], 'unsolved_initial_guess')
        self.assertTrue(guess['nonlinear_source_kernel_energy_load_gates_required'])
        # Test values between nodes as well, using independently fitted
        # Cartesian monomials rather than implementation barycentric bases.
        def monomials(points):
            a, b, c = points.T
            return np.c_[np.ones(len(a)), a, b, c, a*a, a*b, a*c, b*b, b*c, c*c]
        rng = np.random.default_rng(1921)
        fields['P2_velocity_m_s'] = rng.normal(size=(len(xyz), 3))
        random_guess = refine_centroid_tetrahedra(raw, [0], validate=False,
                                                initial_fields=fields)['initial_guess']
        original_coeff = np.linalg.solve(monomials(xyz[local[0]]), fields['P2_velocity_m_s'][local[0]])
        for child in (0, 6, 7, 8):
            ids = random_guess['cell_P2_nodes'][child]
            child_coeff = np.linalg.solve(monomials(random_guess['P2_nodes_m'][ids]),
                                         random_guess['P2_velocity_m_s'][ids])
            point = random_guess['P1_nodes_m'][random_guess['tetrahedra'][child]].mean(axis=0)[None]
            np.testing.assert_allclose(monomials(point)@child_coeff,
                                       monomials(point)@original_coeff, rtol=2e-9, atol=2e-9)

    def test_invalid_markers_budgets_and_geometry_are_rejected(self):
        raw = box_mesh(1)
        for markers in ([], [-1], [6], [True], [0., 1], [0, 0], '0'):
            with self.subTest(markers=markers), self.assertRaises(ValueError):
                refine_centroid_tetrahedra(raw, markers, validate=False)
        for budget in (True, 0, 8, 40001):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                refine_centroid_tetrahedra(raw, [0], max_cells=budget, validate=False)
        for kind in ('inverted', 'degenerate', 'nonfinite', 'index', 'missing_face'):
            bad = copy.deepcopy(raw)
            if kind == 'inverted':
                bad['cells'][0][0], bad['cells'][0][1] = bad['cells'][0][1], bad['cells'][0][0]
            elif kind == 'degenerate':
                bad['vertices'][1] = bad['vertices'][0].copy()
            elif kind == 'nonfinite':
                bad['vertices'][1][0] = float('nan')
            elif kind == 'index':
                bad['cells'][0][0] = 999
            else:
                bad['boundary_patches']['inlet'].pop()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                refine_centroid_tetrahedra(bad, [0])

    def test_stale_field_layout_is_rejected(self):
        raw = box_mesh(1)
        xyz, local = field_layout(raw)
        fields = {'P2_nodes_m': xyz, 'cell_P2_nodes': local, 'P1_nodes_m': raw['vertices'],
                  'tetrahedra': raw['cells'], 'P2_velocity_m_s': velocity(xyz),
                  'P1_pressure_pa': pressure(np.array(raw['vertices']))}
        fields['P2_nodes_m'] = xyz.copy()
        fields['P2_nodes_m'][0, 0] += 1e-14
        with self.assertRaisesRegex(ValueError, 'source layout mismatch'):
            refine_centroid_tetrahedra(raw, [0], validate=False, initial_fields=fields)

    def test_candidate_status_determinism_and_cancellation(self):
        raw = box_mesh(1)
        a = refine_centroid_tetrahedra(raw, [2, 0], validate=False)
        b = refine_centroid_tetrahedra(raw, [0, 2], validate=False)
        self.assertEqual(a, b)
        self.assertEqual(a['provenance']['status'], 'globally_unadmitted_candidate')
        self.assertFalse(a['provenance']['full_source_and_destination_geometry_admitted'])
        with self.assertRaises(InterruptedError):
            refine_centroid_tetrahedra(raw, [0], cancel_check=lambda: True)

    def test_nonreal_bool_and_object_fields_are_rejected_before_coercion(self):
        raw = box_mesh(1)
        xyz, local = field_layout(raw)
        fields = {'P2_nodes_m': xyz, 'cell_P2_nodes': local, 'P1_nodes_m': raw['vertices'],
                  'tetrahedra': raw['cells'], 'P2_velocity_m_s': velocity(xyz),
                  'P1_pressure_pa': pressure(np.array(raw['vertices']))}
        bad_values = {'P2_velocity_m_s': velocity(xyz).astype(complex)+1j,
                      'P1_pressure_pa': np.zeros(len(raw['vertices']), dtype=bool),
                      'P2_nodes_m': xyz.astype(object),
                      'P1_nodes_m': np.asarray(raw['vertices'], dtype=complex)}
        for name, value in bad_values.items():
            bad = {**fields, name: value}
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Real numeric'):
                refine_centroid_tetrahedra(raw, [0], validate=False, initial_fields=bad)


def star_marker(raw, edge):
    return {'edge_vertex_ids': list(edge), 'parent_cell_ids': [
        i for i, row in enumerate(raw['cells']) if all(v in row for v in edge)]}


class BoundaryEdgeRefinementTests(unittest.TestCase):
    def test_disjoint_stars_have_deterministic_face_ancestry(self):
        raw=box_mesh(2)
        marks=[star_marker(raw,(0,4)),star_marker(raw,(4,8))]
        a=refine_boundary_edge_stars(raw,marks,boundary_patch='inlet')
        b=refine_boundary_edge_stars(raw,list(reversed(marks)),boundary_patch='inlet')
        self.assertEqual(a,b)
        self.assertEqual(len(a['mesh']['vertices']),len(raw['vertices'])+2)
        for patch,faces in a['mesh']['boundary_patches'].items():
            self.assertEqual(len(a['provenance']['output_patch_face_parent_ids'][patch]),len(faces))

    def test_complete_star_partition_oriented_surface_and_neighbours(self):
        raw = box_mesh(1)
        original = copy.deepcopy(raw)
        marker = star_marker(raw, (0, 3))
        answer = refine_boundary_edge_stars(raw, [marker], boundary_patch='inlet')
        mesh, info = answer['mesh'], answer['provenance']
        self.assertEqual(raw, original)
        self.assertEqual(mesh['vertices'][:8], raw['vertices'])
        self.assertEqual(mesh['vertices'][8], [0., .5, .5])
        self.assertEqual(len(mesh['cells']), 6+len(marker['parent_cell_ids']))
        self.assertEqual(len(mesh['boundary_patches']['inlet']), 4)
        for name in ('outlet', 'prescribed_sides'):
            self.assertEqual(raw['boundary_patches'][name], mesh['boundary_patches'][name])
        old, new = admit_cfd_tetra_mesh(raw), admit_cfd_tetra_mesh(mesh)
        for ci in set(range(6))-set(marker['parent_cell_ids']):
            self.assertEqual(raw['cells'][ci], mesh['cells'][ci])
        for child in info['edge_stars'][0]['children']:
            np.testing.assert_allclose(new['volumes'][child['child_cell_ids']],
                                       old['volumes'][child['parent_cell_id']]/2, atol=1e-15)
        for record in info['edge_stars'][0]['boundary_face_children']:
            face = np.array(raw['vertices'])[raw['boundary_patches']['inlet'][record['source_face_id']]]
            area_vector = np.cross(face[1]-face[0], face[2]-face[0])
            for child in record['child_face_ids']:
                points = np.array(mesh['vertices'])[mesh['boundary_patches']['inlet'][child]]
                np.testing.assert_array_equal(np.cross(points[1]-points[0], points[2]-points[0]), area_vector/2)
        self.assertAlmostEqual(sum(new['volumes']), sum(old['volumes']), places=14)
        self.assertTrue(info['boundary_polyhedral_support_exactly_preserved'])
        self.assertFalse(info['wall_normal_altitudes_reduced_by_edge_split'])

    def test_restriction_cartesian_and_piecewise_polynomials_owner_layout(self):
        raw = box_mesh(1)
        xyz, local = field_layout(raw)
        fields = {'P2_nodes_m': xyz, 'cell_P2_nodes': local, 'P1_nodes_m': raw['vertices'],
                  'tetrahedra': raw['cells'], 'P2_velocity_m_s': velocity(xyz),
                  'P1_pressure_pa': pressure(np.array(raw['vertices']))}
        markers = [star_marker(raw, (0, 3))]
        answer = refine_boundary_edge_stars(raw, markers, boundary_patch='inlet', initial_fields=fields)
        guess = answer['initial_guess']
        expected_nodes, expected_local = field_layout(answer['mesh'])
        np.testing.assert_array_equal(guess['P2_nodes_m'], expected_nodes)
        np.testing.assert_array_equal(guess['cell_P2_nodes'], expected_local)
        np.testing.assert_allclose(guess['P2_velocity_m_s'], velocity(expected_nodes), atol=2e-14)
        np.testing.assert_allclose(guess['P1_pressure_pa'], pressure(guess['P1_nodes_m']), atol=2e-14)
        # Arbitrary continuous nodal data gives different parent polynomials.
        rng = np.random.default_rng(714)
        fields['P2_velocity_m_s'] = rng.normal(size=(len(xyz), 3))
        fields['P1_pressure_pa'] = rng.normal(size=len(raw['vertices']))
        answer = refine_boundary_edge_stars(raw, markers, boundary_patch='inlet',
                                           validate=False, initial_fields=fields)
        fine = answer['initial_guess']
        def mono(points):
            x,y,z = points.T
            return np.c_[np.ones(len(x)),x,y,z,x*x,x*y,x*z,y*y,y*z,z*z]
        old_pressure_integral = new_pressure_integral = 0.
        old_admit, new_admit = admit_cfd_tetra_mesh(raw), admit_cfd_tetra_mesh(answer['mesh'])
        for parent, tet in enumerate(raw['cells']):
            old_pressure_integral += old_admit['volumes'][parent]*fields['P1_pressure_pa'][tet].mean()
        for ci, parent in enumerate(answer['provenance']['output_cell_parent_ids']):
            old_coeff = np.linalg.solve(mono(xyz[local[parent]]), fields['P2_velocity_m_s'][local[parent]])
            ids = fine['cell_P2_nodes'][ci]
            new_coeff = np.linalg.solve(mono(fine['P2_nodes_m'][ids]), fine['P2_velocity_m_s'][ids])
            points = fine['P1_nodes_m'][fine['tetrahedra'][ci]]
            samples = np.array([[.1,.2,.3,.4],[.4,.1,.2,.3]])@points
            np.testing.assert_allclose(mono(samples)@new_coeff, mono(samples)@old_coeff, atol=2e-13)
            np.testing.assert_allclose(new_coeff, old_coeff, atol=2e-13)
            new_pressure_integral += new_admit['volumes'][ci]*fine['P1_pressure_pa'][fine['tetrahedra'][ci]].mean()
        self.assertAlmostEqual(old_pressure_integral, new_pressure_integral, places=14)
        self.assertEqual(fine['status'], 'unsolved_initial_guess')

    def test_wall_altitude_unchanged_then_centroid_quartered(self):
        raw = box_mesh(1)
        tangential = refine_boundary_edge_stars(raw, [star_marker(raw, (0, 3))], boundary_patch='inlet')
        parents = [ci for star in tangential['provenance']['edge_stars']
                   for record in star['children'] for ci in record['child_cell_ids']]
        paired = refine_centroid_tetrahedra(tangential['mesh'], parents)
        def heights(mesh):
            x=np.array(mesh['vertices']); answer=[]
            for f in mesh['boundary_patches']['inlet']:
                tet=next(c for c in mesh['cells'] if all(v in c for v in f))
                d=next(v for v in tet if v not in f)
                n=np.cross(x[f[1]]-x[f[0]],x[f[2]]-x[f[0]])
                answer.append(abs(np.dot(x[d]-x[f[0]],n))/np.linalg.norm(n))
            return np.array(answer)
        np.testing.assert_array_equal(heights(tangential['mesh']), np.ones(4))
        np.testing.assert_array_equal(heights(paired['mesh']), np.ones(4)/4)

    def test_reject_partial_overlap_seam_nonrepresentable_and_budget_without_mutation(self):
        raw = box_mesh(1)
        marker = star_marker(raw, (0, 3)); original=copy.deepcopy(raw)
        partial=copy.deepcopy(marker);partial['parent_cell_ids'].pop()
        cases = [([partial], {}, 'star'), ([marker, marker], {}, 'overlapping'),
                 ([marker, star_marker(raw, (0, 1))], {}, 'overlapping|patch seams'),
                 ([star_marker(raw, (0, 1))], {}, 'patch seams'),
                 ([marker], {'max_cells':6}, 'budget'),
                 ([marker], {'max_vertices':8}, 'budget')]
        for marks, options, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                refine_boundary_edge_stars(raw, marks, boundary_patch='inlet', validate=False, **options)
            self.assertEqual(raw, original)
        shifted=box_mesh(1)
        shifted['vertices'][0][1]=float(np.nextafter(0., 1.))
        with self.assertRaisesRegex(ValueError, 'not exactly representable'):
            refine_boundary_edge_stars(shifted, [star_marker(shifted, (0,3))],
                                       boundary_patch='inlet', validate=False)
        contact=copy.deepcopy(raw)
        contact['vertices'].extend([[0.,.5,.5],[-1.,.5,.5],[-1.,1.5,.5],[-1.,.5,-.5]])
        contact['cells'].append([8,9,10,11])
        contact['boundary_patches']['other']=[list(f) for f in itertools.combinations([8,9,10,11],3)]
        with self.assertRaisesRegex(ValueError,'coincides'):
            refine_boundary_edge_stars(contact,[marker],boundary_patch='inlet',validate=False)
        for kind in ('negative', 'degenerate', 'missing_face'):
            bad=copy.deepcopy(raw)
            if kind=='negative':bad['cells'][0][0],bad['cells'][0][1]=bad['cells'][0][1],bad['cells'][0][0]
            elif kind=='degenerate':bad['vertices'][1]=bad['vertices'][0].copy()
            else:bad['boundary_patches']['outlet'].pop()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                refine_boundary_edge_stars(bad, [marker], boundary_patch='inlet')

    def test_nonreal_fields_cancellation_and_marker_order(self):
        raw=box_mesh(1);xyz,local=field_layout(raw)
        fields={'P2_nodes_m':xyz,'cell_P2_nodes':local,'P1_nodes_m':raw['vertices'],
                'tetrahedra':raw['cells'],'P2_velocity_m_s':velocity(xyz),
                'P1_pressure_pa':pressure(np.array(raw['vertices']))}
        for key,value in [('P2_velocity_m_s',velocity(xyz).astype(complex)+1j),
                          ('P1_pressure_pa',np.zeros(8,dtype=bool))]:
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'Real numeric'):
                refine_boundary_edge_stars(raw,[star_marker(raw,(0,3))],boundary_patch='inlet',
                                           validate=False,initial_fields={**fields,key:value})
        with self.assertRaises(InterruptedError):
            refine_boundary_edge_stars(raw,[star_marker(raw,(0,3))],boundary_patch='inlet',cancel_check=lambda:True)
        a=star_marker(raw,(0,3));b=copy.deepcopy(a);b['edge_vertex_ids'].reverse();b['parent_cell_ids'].reverse()
        self.assertEqual(refine_boundary_edge_stars(raw,[a],boundary_patch='inlet',validate=False),
                         refine_boundary_edge_stars(raw,[b],boundary_patch='inlet',validate=False))


if __name__ == '__main__':
    unittest.main()
