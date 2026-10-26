# SPDX-License-Identifier: Apache-2.0
"""Actual retained OpenMotor native sections; source-dependent integration checks."""
import copy,json
from pathlib import Path
import unittest
import numpy as np
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_real_motor import RealMotorFieldModel, derive_winding_sides, build_section_mesh, mechanical_period_geometry_proof

class RealMotorFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=Path(__file__).resolve().parents[2]/'output/promo-propulsion-pod-20261023/real_motor'
        if not (p/'native-section.json').is_file():raise unittest.SkipTest('Run native real-motor extractor first; actual source geometry required')
        cls.geometry=json.loads((p/'native-section.json').read_text());cls.spec=json.loads((p/'illustrative-material-request.json').read_text())
        cls.motor=RealMotorFieldModel(cls.geometry,cls.spec)

    def test_intended_winding_requires_two_explicit_assembly_gates(self):
        for a,b in ((False,False),(True,False),(False,True)):
            with self.assertRaises(ValueError):derive_winding_sides(self.geometry,a,b)
        sides,graph=derive_winding_sides(self.geometry,True,True)
        self.assertEqual(len(sides),480);self.assertEqual(graph['parallel_branches_per_phase'],[4,4,4])
        self.assertFalse(graph['literal_CAD_electrical_continuity_qualified'])
        self.assertGreater(graph['native_internal_connector_overlap_mm3'],4.)
        for phase in range(3):self.assertEqual(sum(v[1] for v in sides.values() if v[0]==phase),0.)

    def test_actual_rotor_period_and_declared_magnetization(self):
        proof=mechanical_period_geometry_proof(self.geometry,self.spec['pm_polarity_signs'])
        self.assertTrue(proof['coefficient_geometry_periodicity_verified'])
        self.assertFalse(proof['numerical_mesh_periodicity_qualified'])
        self.assertLess(proof['maximum_geometry_hausdorff_m'],2e-10)
        with self.assertRaises(ValueError):mechanical_period_geometry_proof(self.geometry,[1]*28)

    def test_native_topology_and_interface_mesh(self):
        self.assertEqual(sum(b['label'].startswith('Tooth') for b in self.geometry['bodies']),24)
        self.assertEqual(sum(b['label'].startswith('Magnet') for b in self.geometry['bodies']),28)
        nodes,tris,regions,boundary=self.motor._anchor_mesh
        self.assertGreater(len(nodes),6000);self.assertGreater(len(tris),12000)
        self.assertTrue(all(np.linalg.norm(nodes[k])>.0849 for k in boundary))
        self.assertTrue(all(0<=v<len(nodes) for row in tris for v in row))

    def test_four_actual_field_states_reciprocity_and_balanced_superposition(self):
        m=self.motor;t=self.spec['anchor_angle_rad'];ports=m.linear_ports(t);L=np.array(ports['Lfull']);psi=np.array(ports['psi_full'])
        np.testing.assert_allclose(L,L.T,atol=1e-12);self.assertGreater(np.linalg.eigvalsh(L).min(),0)
        self.assertEqual(ports['field_solves'],4);self.assertTrue(all(v['converged'] for v in ports['solver_errors']))
        i=np.array([1.,-1.,0.]);direct=m._state(i.tolist(),t)
        np.testing.assert_allclose(direct['flux_linkage_wb_turn'],L@i+psi,atol=2e-12)
        self.assertAlmostEqual(direct['magnetic_coenergy_j'],.5*i@L@i+i@psi+ports['C'],places=9)
        self.assertFalse(ports['torque_convergence_qualified'])
        # Actual nonzero common-mode linkage is retained, never projected away.
        self.assertGreater(abs(psi.sum()),1e-5)

    def test_linkage_independent_element_quadrature_and_gauge_shift(self):
        m=self.motor;state=m._state([1.,-1.,0.],self.spec['anchor_angle_rad']);f=state['field']
        n=np.array(f['nodes_m']);tr=np.array(f['triangles']);chi=np.array(f['winding_chi_per_m2']);a=np.array(f['potential_a_wb_per_m'])
        x=n[tr[:,1]]-n[tr[:,0]];y=n[tr[:,2]]-n[tr[:,0]];area=np.abs(x[:,0]*y[:,1]-x[:,1]*y[:,0])/2
        lam=.025*np.sum(area[:,None]*chi*(a[tr]+7).mean(axis=1)[:,None],axis=0)
        np.testing.assert_allclose(lam,state['flux_linkage_wb_turn'],atol=2e-13)

    def test_ale_rigid_rotor_fixed_stator_and_small_angle_torque(self):
        m=self.motor;t=self.spec['anchor_angle_rad'];h=.0001
        a=m._state([1.,-1.,0.],t);b=m._state([1.,-1.,0.],t+h)
        self.assertEqual(a['field']['triangles'],b['field']['triangles'])
        self.assertGreater(b['diagnostics']['minimum_jacobian_ratio'],.05)
        nodes=np.array(a['field']['nodes_m']);moved=np.array(b['field']['nodes_m']);r=np.linalg.norm(nodes,axis=1)
        np.testing.assert_allclose(nodes[r>=.0446],moved[r>=.0446],atol=1e-13)
        np.testing.assert_allclose(np.linalg.norm(moved[r<=.0442],axis=1),r[r<=.0442],atol=1e-13)
        out=m.evaluate([1.,-1.,0.],t)
        self.assertTrue(np.isfinite(out['torque_n_m']));self.assertFalse(out['production_qualified'])
        self.assertFalse(out['diagnostics']['torque_convergence_qualified'])

    def test_stationary_nodal_virtual_work_matches_resolved_derivative_limit(self):
        m=self.motor;t=self.spec['anchor_angle_rad']
        direct=m.resolved_coenergy_torque([1.,-1.,0.],t)['torque_n_m']
        values=[m.fixed_potential_virtual_work([1.,-1.,0.],t,h)['torque_n_m'] for h in (.0001,.00005,.000025)]
        self.assertLess(abs(values[1]-values[2]),abs(values[0]-values[1]))
        # Different finite-angle functionals approach the same discrete shape derivative.
        self.assertLess(abs(direct-values[-1]),.01)

    def test_source_and_patch_and_material_admission(self):
        with self.assertRaises(ValueError):RealMotorFieldModel({**self.geometry,'source_sha256':'wrong'},self.spec)
        for key in ('acknowledge_isotropic_steel_approximation','acknowledge_intended_connector_clearance'):
            with self.assertRaises(ValueError):RealMotorFieldModel(self.geometry,{**self.spec,key:False})
        with self.assertRaises(ValueError):self.motor.evaluate([1,0,0],self.spec['anchor_angle_rad'])
        with self.assertRaises(ValueError):self.motor.evaluate([1,-1,0],self.spec['anchor_angle_rad']+.002)
        with self.assertRaises(ValueError):self.motor.evaluate([True,-1,0],self.spec['anchor_angle_rad'])

class ArkkioQuadratureTests(unittest.TestCase):
    def test_manufactured_radial_and_azimuthal_vacuum_reference(self):
        # Br=.004/r, Btheta=.002/r is source-free in the annulus and gives
        # d*2*pi*.004*.002/mu0 = exactly 1 N m for d=.025 m.
        errors=[]
        for count in (64,128):
            phi=np.arange(count)*2*np.pi/count;radii=np.linspace(.044,.045,count//8+1)
            nodes=np.array([[r*np.cos(t),r*np.sin(t)] for r in radii for t in phi]);tri=[]
            for k in range(len(radii)-1):
                for j in range(count):
                    a=k*count+j;b=k*count+(j+1)%count;c=(k+1)*count+j;d=(k+1)*count+(j+1)%count
                    tri.extend(((a,b,d),(a,d,c)))
            tri=np.array(tri);centers=nodes[tri].mean(axis=1);r=np.linalg.norm(centers,axis=1)
            er=centers/r[:,None];et=np.column_stack((-er[:,1],er[:,0]));B=.004/r[:,None]*er+.002/r[:,None]*et
            fake=object.__new__(RealMotorFieldModel)
            fake._state=lambda i,t:{'field':{'nodes_m':nodes.tolist(),'triangles':tri.tolist(),'element_b_t':B.tolist(),'region_ids':['air']*len(tri)}}
            out=fake.arkkio_torque([0.,0.,0.],0.)
            errors.append(abs(out['torque_n_m']-1.))
        self.assertLess(errors[1],errors[0]/3.)
        self.assertLess(errors[1],.003)

if __name__=='__main__':unittest.main()
