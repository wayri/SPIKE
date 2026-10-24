# SPDX-License-Identifier: Apache-2.0
import copy,json,math
from pathlib import Path
import unittest
import numpy as np
from python.spike_core.propulsion_pod_real_motor_domains import build_real_motor_domains,p2_interface_trace,refine_existing_domains
from python.spike_core.propulsion_pod_magnetic_p2 import P2MagneticOperator

class StaticDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=Path(__file__).resolve().parents[2]/'output/promo-propulsion-pod-20261023/real_motor'
        if not (p/'native-section-fine.json').is_file():raise unittest.SkipTest('Run actual native section extractor first')
        cls.geometry=json.loads((p/'native-section-fine.json').read_text());cls.spec=json.loads((p/'p2-fine-material-request.json').read_text())
        cls.domains=build_real_motor_domains(cls.geometry,cls.spec,257,.001)

    def test_actual_static_regions_and_balanced_sources(self):
        o=self.domains
        self.assertFalse(o['circle_trace_geometry_exact']);self.assertFalse(o['material_qualified'])
        self.assertEqual(o['omitted_vacuum_annulus_m'],[.04430,.04450])
        self.assertEqual(len(set(x for x in o['stator']['region_ids'] if x.startswith('Coil'))),480)
        self.assertEqual(len(set(x for x in o['rotor']['region_ids'] if x.startswith('Magnet'))),28)
        self.assertEqual(np.max(np.abs(o['rotor']['winding_chi_per_m2'])),0.)
        np.testing.assert_allclose(o['stator']['signed_turn_integrals'],[0,0,0],atol=1e-12)
        self.assertEqual(o['rotor']['dirichlet_vertex_ids'],[])
        self.assertGreater(len(o['stator']['dirichlet_vertex_ids']),256)

    def test_all_uniform_p2_interface_dofs_and_chord_error_retained(self):
        for name in ('rotor','stator'):
            d=self.domains[name];op=P2MagneticOperator(d['nodes_m'],d['triangles'],d['solver_region_ids'],d['materials'],.025,maximum_nodes=100000)
            trace=p2_interface_trace(op,d);self.assertEqual(len(trace['dof_ids']),514)
            self.assertEqual(len(set(trace['dof_ids'])),514)
            np.testing.assert_allclose(np.diff(trace['angles_rad']),math.pi/257,atol=1e-14)
            self.assertFalse(trace['fourier_projection_performed']);self.assertTrue(trace['all_trace_dofs_retained'])
            expected=d['interface_radius_m']*(1-math.cos(math.pi/257))
            self.assertAlmostEqual(trace['maximum_radial_chord_error_m'],expected,places=11)

    def test_domain_area_matches_straight_polygon_partition(self):
        o=self.domains;N=257
        rotor_expected=N*.04430**2*math.sin(2*math.pi/N)/2
        outer_count=len(o['stator']['outer_boundary_vertex_ids'])
        outer_area=outer_count*.085**2*math.sin(2*math.pi/outer_count)/2
        hole_area=N*.04450**2*math.sin(2*math.pi/N)/2
        self.assertAlmostEqual(o['rotor']['domain_area_m2'],rotor_expected,places=12)
        self.assertAlmostEqual(o['stator']['domain_area_m2'],outer_area-hole_area,places=12)
        # The helper deliberately does not claim an exact circular partition.
        self.assertGreater(o['straight_chord_radial_error_bound_m'],3e-6)

    def test_malformed_trace_and_interpretation_and_crossing_material_rejected(self):
        with self.assertRaises(ValueError):build_real_motor_domains(self.geometry,self.spec,True,.001)
        with self.assertRaises(ValueError):build_real_motor_domains(self.geometry,self.spec,257,.001,repeat_rotor_sector=True)
        with self.assertRaises(ValueError):build_real_motor_domains(self.geometry,{**self.spec,'acknowledge_intended_connector_clearance':False},257,.001)
        bad=copy.deepcopy(self.geometry);mag=next(x for x in bad['bodies'] if x['label'].startswith('Magnet'))
        mag['loops_m']=[[[x*2,y*2] for x,y in loop] for loop in mag['loops_m']]
        with self.assertRaises(ValueError):build_real_motor_domains(bad,self.spec,257,.001)

    def test_repeated_rotor_exact_rotated_connectivity_and_source(self):
        from scipy.spatial import cKDTree
        o=build_real_motor_domains(self.geometry,self.spec,1008,.001,repeat_rotor_sector=True)
        d=o['rotor'];xy=np.asarray(d['nodes_m']);tri=np.asarray(d['triangles']);angle=2*math.pi/14
        Q=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
        distance,permutation=cKDTree(xy).query(xy@Q.T)
        self.assertLess(float(max(distance)),2e-11)
        original={tuple(sorted(row)) for row in tri}
        self.assertEqual(original,{tuple(sorted(row)) for row in permutation[tri]})
        regions=d['solver_region_ids'];bytri={tuple(sorted(row)):j for j,row in enumerate(tri)}
        for j,row in enumerate(tri):
            k=bytri[tuple(sorted(permutation[row]))];a=d['materials'][regions[j]];b=d['materials'][regions[k]]
            self.assertEqual(a['mu_r'],b['mu_r'])
            np.testing.assert_allclose(Q@np.asarray(a.get('remanence_t',[0,0])),b.get('remanence_t',[0,0]),atol=1e-11)
        self.assertEqual(np.max(np.abs(d['winding_chi_per_m2'])),0)
        self.assertTrue(o['rotor_sector_repeated'])

    def test_true_interior_refinement_preserves_polygon_and_sources(self):
        a=build_real_motor_domains(self.geometry,self.spec,252,.001,repeat_rotor_sector=True)
        b=build_real_motor_domains(self.geometry,self.spec,252,.001,repeat_rotor_sector=True,uniform_refinements=1)
        for name in ('rotor','stator'):
            x,y=a[name],b[name]
            self.assertEqual(len(x['interface_vertex_ids']),len(y['interface_vertex_ids']))
            self.assertAlmostEqual(x['domain_area_m2'],y['domain_area_m2'],places=12)
            np.testing.assert_allclose(x['signed_turn_integrals'],y['signed_turn_integrals'],atol=1e-12)
            self.assertGreater(len(y['triangles']),3*len(x['triangles']))
            # The former long interior air edges genuinely shrink; trace
            # chords and outer polygon remain exactly the same geometry.
            self.assertLess(y['element_geometry_statistics']['air']['maximum_edge_m'],.6*x['element_geometry_statistics']['air']['maximum_edge_m'])

    def test_pure_vacuum_trace_layers_and_source_geometry_preserved(self):
        a=build_real_motor_domains(self.geometry,self.spec,252,.001,repeat_rotor_sector=True)
        b=build_real_motor_domains(self.geometry,self.spec,252,.001,repeat_rotor_sector=True,vacuum_trace_layers_m=[25e-6,50e-6,75e-6])
        for name in('rotor','stator'):
            x,y=a[name],b[name]
            self.assertAlmostEqual(x['domain_area_m2'],y['domain_area_m2'],places=12)
            np.testing.assert_allclose(x['signed_turn_integrals'],y['signed_turn_integrals'],atol=1e-12)
            self.assertLess(y['trace_adjacent_element_statistics']['maximum_radial_span_m'],25.001e-6)
            for label in set(x['region_ids']):
                if label=='air':continue
                area_x=sum(v for r,v in zip(x['region_ids'],x['element_area_m2']) if r==label)
                area_y=sum(v for r,v in zip(y['region_ids'],y['element_area_m2']) if r==label)
                self.assertAlmostEqual(area_x,area_y,places=12)
        with self.assertRaises(ValueError):build_real_motor_domains(self.geometry,self.spec,252,.001,vacuum_trace_layers_m=[.0001])

    def test_bound_marked_refinement_orbits_nesting_and_variational_response(self):
        from python.spike_core.propulsion_pod_separated_motor import SeparatedMotor
        a=build_real_motor_domains(self.geometry,self.spec,252,.001,repeat_rotor_sector=True)
        bindings={name:{'mesh_sha256':a[name]['mesh_sha256'],'triangle_ids':list(range(0,len(a[name]['triangles']),31))} for name in('rotor','stator')}
        b=build_real_motor_domains(self.geometry,self.spec,252,.001,repeat_rotor_sector=True,interior_marked_triangles=bindings)
        for name in('rotor','stator'):
            x,y=a[name],b[name];m=y['marked_refinement']
            self.assertEqual(m['coarse_mesh_sha256'],x['mesh_sha256'])
            self.assertLess(m['maximum_added_node_midpoint_error_m'],2e-12)
            self.assertAlmostEqual(x['domain_area_m2'],y['domain_area_m2'],places=12)
            np.testing.assert_allclose(x['signed_turn_integrals'],y['signed_turn_integrals'],atol=1e-12)
            if name=='rotor':self.assertEqual(m['orbit_closed_count']%14,0)
        def response(domain):
            q=SeparatedMotor(domain,maximum_mode=7).linear_ports(.012);M=np.zeros((4,4))
            M[0,0]=2*q['coenergy_zero_current_j'];M[0,1:]=q['pm_flux_linkage_wb_turn'];M[1:,0]=M[0,1:];M[1:,1:]=q['inductance_h']
            D=np.diag([1.,10.,10.,10.]);return D@M@D
        delta=response(b)-response(a)
        self.assertGreater(np.linalg.eigvalsh(delta).min(),-1e-9)
        bad=copy.deepcopy(bindings);bad['stator']['mesh_sha256']='0'*64
        with self.assertRaises(ValueError):build_real_motor_domains(self.geometry,self.spec,252,.001,repeat_rotor_sector=True,interior_marked_triangles=bad)
        second={name:{'mesh_sha256':b[name]['mesh_sha256'],'triangle_ids':[0]} for name in('rotor','stator')}
        c=refine_existing_domains(b,second)
        for name in('rotor','stator'):
            self.assertEqual(len(c[name]['marked_refinement_history']),2)
            self.assertGreater(len(c[name]['triangles']),len(b[name]['triangles']))
            self.assertAlmostEqual(c[name]['domain_area_m2'],b[name]['domain_area_m2'],places=12)
        with self.assertRaises(ValueError):refine_existing_domains(b,bindings)
        tampered=copy.deepcopy(b);tampered['stator']['nodes_m'][0][0]+=.0001
        with self.assertRaises(ValueError):refine_existing_domains(tampered,second)

if __name__=='__main__':unittest.main()
