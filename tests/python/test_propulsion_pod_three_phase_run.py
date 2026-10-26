# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from unittest.mock import patch
import numpy as np
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_three_phase_run import DEFAULT_REQUEST, validate_three_phase_request, run_three_phase_pod

class ThreePhaseRunTests(unittest.TestCase):
    def request(self,dt=.0001,duration=.004):
        r=copy.deepcopy(DEFAULT_REQUEST);r['transient'].update(time_step_s=dt,duration_s=duration,field_output_interval_s=.002)
        return r

    def test_actual_compiled_c_three_phase_heat_and_ledger(self):
        request=self.request();before=copy.deepcopy(request);out=run_three_phase_pod(request)
        self.assertEqual(request,before);self.assertEqual(out['accepted_steps'],40)
        self.assertEqual(out['controller_ticks'],8)
        self.assertEqual(len(out['thermal_node_names']),11)
        self.assertEqual(out['provenance']['fluid_provider_kind'],'hover_bem')
        self.assertEqual(len(out['provenance']['controller_executable_sha256']),64)
        self.assertGreater(out['history'][-1]['speed_rad_s'],0)
        self.assertGreater(max(out['history'][-1]['temperature_k']),298.15)
        self.assertLess(out['energy']['maximum_current_sum_a'],1e-12)
        self.assertLess(out['energy']['maximum_phase_kvl_residual_v'],1e-9)
        self.assertLess(abs(out['energy']['defect_j']),1e-8)
        self.assertEqual(out['field_mesh']['region_ids'].count('a_pos'),out['field_mesh']['region_ids'].count('b_pos'))
        self.assertEqual(out['history'][-1]['cumulative_energy_j']['dc_source_work_j'],out['energy']['dc_source_work_j'])

    def test_step_refinement(self):
        speeds=[]
        for dt in (.0001,.00005,.000025):speeds.append(run_three_phase_pod(self.request(dt))['history'][-1]['speed_rad_s'])
        self.assertLess(abs(speeds[1]-speeds[2]),abs(speeds[0]-speeds[1]))

    def test_resistance_heat_feedback_changes_actual_loop(self):
        r=self.request(duration=.01)
        r['thermal']={'capacities_j_per_k':[.01]*3+[.001]*6+[80.,30.],
                      'copper_alpha_per_k':.03,'mosfet_alpha_per_k':.03,'minimum_temperature_k':290.}
        hot=run_three_phase_pod(r)
        r['thermal'].update(copper_alpha_per_k=0.,mosfet_alpha_per_k=0.)
        fixed=run_three_phase_pod(r)
        self.assertGreater(max(hot['history'][-1]['temperature_k']),298.2)
        self.assertGreater(abs(hot['history'][-1]['speed_rad_s']-fixed['history'][-1]['speed_rad_s']),1e-5)
        self.assertLess(abs(hot['energy']['defect_j']),1e-8)

    def test_invalid_rejected_before_compilation(self):
        cases=[]
        r=self.request();r['fluid']['kind']='cfd';cases.append(r)
        r=self.request();r['drive']['current_limit_a']=True;cases.append(r)
        r=self.request();r['thermal']={'extra':1};cases.append(r)
        r=self.request();r['field_motor']={'extra':1};cases.append(r)
        r=self.request();r['drive']['end_turn_inductance_h']=[0,0];cases.append(r)
        r=self.request();r['transient']['duration_s']=.00401;cases.append(r)
        with patch('python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_three_phase_run.create_three_phase_controller') as compiler:
            for r in cases:
                with self.subTest(r=r),self.assertRaises(ValueError):run_three_phase_pod(r)
            compiler.assert_not_called()

if __name__=='__main__':unittest.main()
