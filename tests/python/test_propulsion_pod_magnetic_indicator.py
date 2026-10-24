# SPDX-License-Identifier: Apache-2.0
import unittest
import numpy as np
from python.spike_core.propulsion_pod_magnetic_p2 import P2MagneticOperator
from python.spike_core.propulsion_pod_magnetic_indicator import magnetic_refinement_indicator,hierarchical_magnetic_correction


class MagneticIndicatorTests(unittest.TestCase):
    def operator(self,pm_jump=False):
        return P2MagneticOperator([[0.,0.],[1.,0.],[1.,1.],[0.,1.]],
            [[0,1,2],[0,3,2]],['a','b'],
            {'a':{'permeability_h_m':1.,'remanence_t':[1.,0.] if pm_jump else [.3,.2]},
             'b':{'permeability_h_m':1.,'remanence_t':[0.,-1.] if pm_jump else [.3,.2]}})

    def test_exact_quadratic_manufactured_field_has_zero_residual(self):
        op=self.operator();xy=op.nodes_m
        A=np.sum(xy**2,axis=1)
        out=magnetic_refinement_indicator(op,A,[-4.,-4.])
        self.assertLess(out['sum_indicator_j'],1e-27)
        self.assertFalse(out['certified_error_bound'])

    def test_continuous_B_normal_does_not_hide_constitutive_flux_jump(self):
        op=self.operator();A=op.nodes_m.min(axis=1)
        out=magnetic_refinement_indicator(op,A,[0.,0.])
        # A=y and A=x on the two cells. q normal jump=sqrt(2), edge=sqrt(2).
        np.testing.assert_allclose(out['interior_flux_jump_indicator_j'],[2.,2.],atol=1e-14)
        self.assertAlmostEqual(out['sum_indicator_j'],4.,places=13)
        self.assertEqual(out['boundary_edges_excluded'],4)

    def test_remanence_is_included_in_interface_flux(self):
        op=self.operator(pm_jump=True);A=op.nodes_m.min(axis=1)
        # Each region has B=Br, hence H=q=0 despite the discontinuous B.
        out=magnetic_refinement_indicator(op,A,[0.,0.])
        self.assertLess(out['sum_indicator_j'],1e-28)
        with self.assertRaises(ValueError):magnetic_refinement_indicator(op,A,[float('nan'),0.])

    def test_hierarchical_correction_integrates_polynomial_without_aspect_weight(self):
        def mesh(n,height=1.,shift_y=0.):
            xy=[[i/n,j/n*height+shift_y] for j in range(n+1) for i in range(n+1)];tri=[]
            for j in range(n):
                for i in range(n):
                    a=j*(n+1)+i;b=a+1;c=a+n+1;d=c+1
                    tri.extend([[a,b,d],[a,d,c]])
            return P2MagneticOperator(xy,tri,['m']*len(tri),{'m':{'permeability_h_m':1.}},.3)
        coarse=mesh(1);fine=mesh(2)
        quadratic=lambda op:np.sum(op.nodes_m**2,axis=1)
        out=hierarchical_magnetic_correction(coarse,fine,np.zeros(len(coarse.nodes_m)),quadratic(fine))
        # .5*.3*integral((2x)^2+(2y)^2)=.4 J.
        self.assertAlmostEqual(out['sum_correction_energy_j'],.4,places=14)
        same=hierarchical_magnetic_correction(coarse,fine,quadratic(coarse),quadratic(fine))
        self.assertLess(same['sum_correction_energy_j'],1e-28)
        self.assertFalse(out['gap_energy_included']);self.assertFalse(out['certified_error_bound'])
        thin_coarse=mesh(1,height=1e-6);thin_fine=mesh(2,height=1e-6,shift_y=.5e-12)
        zero0=np.zeros(len(thin_coarse.nodes_m));zero1=np.zeros(len(thin_fine.nodes_m))
        with self.assertRaisesRegex(ValueError,'not contained'):
            hierarchical_magnetic_correction(thin_coarse,thin_fine,zero0,zero1)
        tolerated=hierarchical_magnetic_correction(thin_coarse,thin_fine,zero0,zero1,nesting_tolerance_m=2e-12)
        self.assertGreater(tolerated['maximum_physical_outside_distance_m'],.49e-12)
        self.assertLess(tolerated['maximum_physical_outside_distance_m'],.51e-12)


if __name__=='__main__':unittest.main()
