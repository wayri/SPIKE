# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_convergence import assess_load_convergence


def cases():
    return [dict(mesh_scale=h,domain_scale=d,torque_nm=q,thrust_n=2*q,
                 torque_absolute_tolerance_nm=1e-8,thrust_absolute_tolerance_n=1e-8,
                 traction_relative_error=.01,continuity_energy_relative_error=.0001,
                 nonlinear_relative_residual=1e-9,geometry_sha256='a'*64,
                 physics_sha256='b'*64,case_sha256=str(j)*64)
            for j,(h,d,q) in enumerate(((1.,1.,1.1),(.5,1.,1.01),(.25,1.,1.),(.25,2.,1.005)))]


class LoadConvergenceTests(unittest.TestCase):
    def test_independent_grid_and_domain(self):
        s=cases();before=copy.deepcopy(s);out=assess_load_convergence(s)
        self.assertTrue(out['declared_load_change_screen_passed']);self.assertFalse(out['physical_regime_qualified'])
        self.assertEqual(s,before)
    def test_actual_motor_nonmonotone_pattern_rejected(self):
        s=cases()
        for row,q in zip(s,(1.602,.112,.571,.571)):row['torque_nm']=q
        self.assertFalse(assess_load_convergence(s)['declared_load_change_screen_passed'])
    def test_residual_alone_cannot_qualify(self):
        s=cases();s[-1]['traction_relative_error']=.328
        self.assertFalse(assess_load_convergence(s)['declared_load_change_screen_passed'])
        s=cases();s[-1]['torque_nm']=1.2
        self.assertFalse(assess_load_convergence(s)['declared_load_change_screen_passed'])
    def test_case_identity_and_false_tolerances_rejected(self):
        for change in ('duplicate','physics','grid','nan'):
            s=cases()
            if change=='duplicate':s[1]['case_sha256']=s[0]['case_sha256']
            if change=='physics':s[-1]['physics_sha256']='c'*64
            if change=='grid':s[-1]['mesh_scale']=.5
            if change=='nan':s[-1]['torque_nm']=float('nan')
            with self.subTest(change=change),self.assertRaises(ValueError):assess_load_convergence(s)
        for tolerance in (True,0.,-.1,1.,float('inf')):
            with self.assertRaises(ValueError):assess_load_convergence(cases(),mesh_tolerance=tolerance)


if __name__=='__main__':unittest.main()
