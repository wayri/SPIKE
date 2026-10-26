# SPDX-License-Identifier: Apache-2.0
"""Bounded worker admission and source identity; ports are explicit fixtures."""
import copy
import unittest
from unittest.mock import patch
from tests.python.test_propulsion_pod_energy_table import table
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_geometry_run import prepare_geometry_run
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_energy_table import PeriodicLinearMagneticPort
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_load_table import CfdLoadTable, CONTRACT
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_three_phase_run import DEFAULT_REQUEST
from python.spike_core.service_propulsion_pod import handle_propulsion_pod_request


def parameters():
    r=copy.deepcopy(DEFAULT_REQUEST);t=r['transient'];t.pop('field_output_interval_s')
    t.update(duration_s=.003,target_speed_rad_s=35.,maximum_speed_rad_s=50.)
    field=table();field['maximum_phase_current_a']=10.
    magnetic=PeriodicLinearMagneticPort(field,r['drive']['end_turn_inductance_h'])
    fluid=CfdLoadTable({'contract':CONTRACT,'geometry_sha256':'a'*64,'physics_sha256':'b'*64,
        'evidence':{'fixture_only':True},'anchors':[{'omega_rad_s':w,'torque_nm':w*1e-6,
            'thrust_n':w*1e-5,'case_sha256':str(i)*64} for i,w in enumerate((0.,30.,60.))]})
    return {'request':{'initial_currents_a':[0.,0.,0.],'initial_angle_rad':.2,'initial_speed_rad_s':30.,
        'thermal':{},'drive':r['drive'],'shaft':{k:r['shaft'][k] for k in ('inertia_kg_m2','damping_n_m_s')},
        'transient':t},'magnetic_table':magnetic.table,'cfd_table':fluid.table,
        'expected_field_sha256':magnetic.source_sha256,'expected_fluid_sha256':fluid.source_sha256}


class GeometryRunAdmissionTests(unittest.TestCase):
    def test_immutable_preparation_expands_thermal_without_claiming_convergence(self):
        params=parameters();before=copy.deepcopy(params)
        r,port,fluid,d=prepare_geometry_run(params)
        self.assertEqual(params,before)
        self.assertEqual(d['accepted_steps_if_successful'],30)
        self.assertEqual(len(r['thermal']['initial_temperature_k']),11)
        self.assertTrue(d['representation_only']);self.assertFalse(d['physical_load_qualified'])
        self.assertEqual(port.source_sha256,params['expected_field_sha256'])
        self.assertEqual(fluid.source_sha256,params['expected_fluid_sha256'])

    def test_invalid_inputs_fail_before_any_controller_compilation(self):
        mutations=[lambda p:p.update(expected_field_sha256='0'*64),
            lambda p:p.update(expected_fluid_sha256='0'*64),
            lambda p:p['request'].update(initial_currents_a=[1.,1.,1.]),
            lambda p:p['request']['drive'].update(dc_bus_v=-48.),
            lambda p:p['request']['drive'].update(source='untrusted injected C'),
            lambda p:p['request']['transient'].update(time_step_s=1e-6,duration_s=10.),
            lambda p:p['request']['transient'].update(maximum_speed_rad_s=70.),
            lambda p:p['request']['drive'].update(current_limit_a=100.),
            lambda p:p['request']['shaft'].update(inertia_kg_m2=True)]
        with patch('python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_geometry_loop.create_three_phase_controller') as compiler:
            for mutate in mutations:
                p=parameters();mutate(p)
                with self.subTest(mutation=mutate):
                    response=handle_propulsion_pod_request('run_propulsion_pod_geometry',p)
                    self.assertFalse(response['ok'],response)
            compiler.assert_not_called()

    def test_capabilities_are_explicit_and_unrelated_methods_are_not_consumed(self):
        response=handle_propulsion_pod_request('propulsion_pod_geometry_capabilities',{})
        self.assertTrue(response['ok']);self.assertFalse(response['result']['production_qualified'])
        self.assertFalse(handle_propulsion_pod_request('propulsion_pod_geometry_capabilities',{'extra':1})['ok'])
        self.assertIsNone(handle_propulsion_pod_request('unrelated',{}))


if __name__=='__main__':unittest.main()
