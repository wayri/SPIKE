# SPDX-License-Identifier: Apache-2.0
"""Independent coupling review: API admission and continuous/finite-step oracles."""
import copy
import math
import unittest
import numpy as np
from scipy.linalg import expm
from python.spike_core.propulsion_pod import DEFAULT_REQUEST, validate_request, coupled_step
from python.spike_core.propulsion_pod_field import FieldMotor
from python.spike_core.propulsion_pod_propeller import evaluate_propeller
from python.spike_core.service_propulsion_pod import handle_propulsion_pod_request


class IndependentPropulsionPodReview(unittest.TestCase):
    def test_public_validation_rejects_invalid_field_spec(self):
        for field in ({'unsupported_key':1},{'remanence_t':float('nan')},{'turns':True}):
            request=copy.deepcopy(DEFAULT_REQUEST);request['field_motor']=field
            response=handle_propulsion_pod_request('validate_propulsion_pod',{'request':request})
            self.assertFalse(response['ok'],field)

    def test_capabilities_does_not_expose_mutable_global_default(self):
        response=handle_propulsion_pod_request('propulsion_pod_capabilities',{})
        self.assertTrue(response['ok'])
        exposed=response['result']['default_request']
        self.assertIsNot(exposed,DEFAULT_REQUEST)
        self.assertIsNot(exposed['drive'],DEFAULT_REQUEST['drive'])

    def test_no_pm_rl_against_independent_matrix_exponential(self):
        motor=FieldMotor({'remanence_t':0.});prop=copy.deepcopy(DEFAULT_REQUEST['propeller'])
        R=np.array([.5,.7]);end=np.array([.0002,.00015]);L=motor.inductance_h+np.diag(end)
        v=np.array([.7,-.5]);i0=np.array([.2,-.1]);end_time=.0012
        steady=v/R;expected=steady+expm(-np.linalg.solve(L,np.diag(R))*end_time)@(i0-steady)
        errors=[]
        for count in (12,24,48):
            i=i0.tolist();angle=.4;speed=0.;dt=end_time/count
            for _ in range(count):
                r=coupled_step(motor,prop,i,angle,speed,v.tolist(),dt,R.tolist(),end.tolist(),5e-6,1e-6,500.)
                i,angle,speed=r['currents_a'],r['angle_rad'],r['speed_rad_s']
                self.assertEqual(speed,0.)
                self.assertLess(abs(r['energy']['defect_j']),1e-11)
            errors.append(float(np.linalg.norm(np.asarray(i)-expected,np.inf)))
        self.assertGreater(errors[0]/errors[1],3.8)
        self.assertGreater(errors[1]/errors[2],3.8)
        self.assertLess(errors[-1],.001)

    def test_actual_same_step_work_and_unwrapped_angle_crossing(self):
        motor=FieldMotor();prop=copy.deepcopy(DEFAULT_REQUEST['propeller'])
        old_i=[-2.,0.];old_angle=2*math.pi-.002;old_w=100.;dt=.0001
        old=motor.evaluate(old_i,old_angle);R=[.5,.5];end=[.0002,.0002]
        dpsi=np.asarray(old['angular_derivatives']['dflux_dangle_wb_turn_per_rad'])
        voltage=np.asarray(old_i)*R+old_w*dpsi
        r=coupled_step(motor,prop,old_i,old_angle,old_w,voltage.tolist(),dt,R,end,5e-6,1e-6,500.)
        self.assertGreater(r['angle_rad'],2*math.pi)
        self.assertEqual(old_i,[-2.,0.])
        mid_w=(old_w+r['speed_rad_s'])/2
        fluid=evaluate_propeller(prop,mid_w)
        self.assertAlmostEqual(r['energy']['propeller_shaft_work_j'],dt*fluid['torque_nm']*mid_w,places=15)
        final=motor.evaluate(r['currents_a'],r['angle_rad'])
        actual_delta=final['magnetic_energy_j']-old['magnetic_energy_j']+.5*sum(l*(b*b-a*a) for l,a,b in zip(end,old_i,r['currents_a']))
        self.assertAlmostEqual(r['energy']['magnetic_energy_change_j'],actual_delta,places=14)
        delta=r['angle_rad']-old_angle;ibar=(np.asarray(old_i)+r['currents_a'])/2
        pm_work=ibar@(np.asarray(final['pm_flux_linkage_wb_turn'])-old['pm_flux_linkage_wb_turn'])
        potential_work=final['pm_source_potential_j']-old['pm_source_potential_j']
        self.assertLess(abs(r['torque_dg_n_m']*delta-pm_work-potential_work),1e-12)
        self.assertLess(abs(r['energy']['defect_j']),1e-11)


if __name__=='__main__':unittest.main()
