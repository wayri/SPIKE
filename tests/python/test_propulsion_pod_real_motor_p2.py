# SPDX-License-Identifier: Apache-2.0
"""Actual-source P2 adapter reciprocity, field sampling and shape-work checks."""
import json
from pathlib import Path
import unittest
import numpy as np
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_real_motor_p2 import RealMotorP2FieldModel

class RealMotorP2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=Path(__file__).resolve().parents[2]/'output/promo-propulsion-pod-20261023/real_motor'
        if not (p/'native-section-fine.json').is_file():raise unittest.SkipTest('Run fine native geometry extraction first')
        cls.geometry=json.loads((p/'native-section-fine.json').read_text());cls.spec=json.loads((p/'central-support-material-request.json').read_text())
        cls.spec.update(edge_m=.003,refinements=0)
        cls.motor=RealMotorP2FieldModel(cls.geometry,cls.spec)

    def test_real_four_basis_states_one_factor_and_superposition(self):
        m=self.motor;ports=m.linear_ports(.002);L=np.array(ports['Lfull']);psi=np.array(ports['psi_full']);i=np.array([1.,-1.,0.]);state=m._state(i,.002)
        self.assertEqual(ports['factorization_count'],1)
        np.testing.assert_allclose(L,L.T,atol=2e-12);self.assertGreater(np.linalg.eigvalsh(L).min(),0)
        np.testing.assert_allclose(state['flux_linkage_wb_turn'],L@i+psi,atol=2e-12)
        self.assertAlmostEqual(state['magnetic_coenergy_j'],.5*i@L@i+i@psi+ports['C'],places=10)
        self.assertFalse(ports['material_qualified']);self.assertFalse(ports['winding_qualified'])

    def test_physical_linkage_by_independent_p2_edge_quadrature(self):
        state=self.motor._state([1.,-1.,0.],.002);f=state['field'];area=np.array(f['element_area_m2']);chi=np.array(f['winding_chi_per_m2'])
        A=np.array(f['p2_potential_a_wb_per_m']);tr=np.array(f['p2_triangles'])
        # Integrals of quadratic vertex shapes vanish; each edge integral is area/3.
        flux=.025*np.sum(area[:,None]*chi*A[tr[:,3:]].mean(axis=1)[:,None],axis=0)
        shifted=.025*np.sum(area[:,None]*chi*(A[tr[:,3:]]+7).mean(axis=1)[:,None],axis=0)
        np.testing.assert_allclose(flux,state['flux_linkage_wb_turn'],atol=2e-13)
        np.testing.assert_allclose(shifted,flux,atol=2e-13)
        self.assertEqual(len(f['potential_a_wb_per_m']),len(f['nodes_m']))
        self.assertGreater(len(A),len(f['nodes_m']))

    def test_p2_shape_derivative_fixed_A_and_independent_resolve(self):
        m=self.motor;t=.002;h=.00001
        weighted=m.volume_weighted_virtual_work([1.,-1.,0.],t)['torque_n_m']
        fixed=m.fixed_potential_virtual_work([1.,-1.,0.],t,h)['torque_n_m']
        resolved=m.resolved_coenergy_torque([1.,-1.,0.],t,h)['torque_n_m']
        self.assertLess(abs(weighted-fixed),1e-5)
        self.assertLess(abs(weighted-resolved),1e-5)
        out=m.evaluate([1.,-1.,0.],t,True)
        self.assertEqual(out['contract'],'spike/real-motor-geometry-p2-field/v1')
        self.assertFalse(out['production_qualified']);self.assertFalse(out['diagnostics']['torque_convergence_qualified'])

    def test_barycentric_field_reconstruction_is_linear_inside_cell(self):
        m=self.motor;state=m._state([1.,-1.,0.],.002);op=m._operator_at(.002)[0];A=np.array(state['field']['p2_potential_a_wb_per_m'])
        points=np.array([[.2,.3,.5],[.6,.2,.2]])
        expected=np.einsum('qi,eia->eqa',points,np.array(state['field']['p2_barycentric_b_t']))
        np.testing.assert_allclose(op.evaluate_b(A,points),expected,atol=3e-12,rtol=2e-11)

if __name__=='__main__':unittest.main()
