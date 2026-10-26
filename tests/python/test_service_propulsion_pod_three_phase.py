# SPDX-License-Identifier: Apache-2.0
"""Actual public IPC route checks, including compiled controller execution."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from python.spike_core.service import handle
from python.spike_core.service_propulsion_pod import handle_propulsion_pod_request
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_three_phase_run import DEFAULT_REQUEST, REQUEST, RESULT

class ThreePhaseServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_temp=tempfile.tempdir
        cls.old_env={key:os.environ.get(key) for key in ('TMP','TEMP')}
        folder=Path(__file__).resolve().parents[2]/'.tmp'
        if not folder.is_dir():raise RuntimeError('Existing workspace .tmp is required for local C compilation')
        tempfile.tempdir=str(folder)
        for key in cls.old_env:os.environ[key]=str(folder)

    @classmethod
    def tearDownClass(cls):
        tempfile.tempdir=cls.old_temp
        for key,value in cls.old_env.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value

    def call(self,method,params):return handle({'method':method,'params':params})

    def test_capabilities_and_default_isolation(self):
        out=self.call('propulsion_pod_three_phase_capabilities',{})
        self.assertTrue(out['ok']);cap=out['result']
        self.assertEqual(cap['request_contract'],REQUEST);self.assertEqual(cap['result_contract'],RESULT)
        self.assertFalse(cap['production_qualified']);self.assertFalse(cap['real_motor_characterization'])
        self.assertTrue(cap['compiles_builtin_controller_on_run'])
        cap['default_request']['drive']['dc_bus_v']=99
        self.assertEqual(self.call('propulsion_pod_three_phase_capabilities',{})['result']['default_request']['drive']['dc_bus_v'],12.)

    def test_validation_normalizes_without_running(self):
        out=self.call('validate_propulsion_pod_three_phase',{'request':copy.deepcopy(DEFAULT_REQUEST)})
        self.assertTrue(out['ok']);self.assertTrue(out['result']['valid'])
        self.assertEqual(out['result']['steps'],500);self.assertEqual(out['result']['controller_stride'],5)
        self.assertEqual(len(out['result']['request']['thermal']['initial_temperature_k']),11)

    def test_strict_errors_and_unhandled_routes(self):
        malformed=[]
        for params in ({},None,{'request':DEFAULT_REQUEST,'extra':1}):malformed.append(('validate_propulsion_pod_three_phase',params))
        bad=copy.deepcopy(DEFAULT_REQUEST);bad['field_motor']={'unknown':1};malformed.append(('validate_propulsion_pod_three_phase',{'request':bad}))
        bad=copy.deepcopy(DEFAULT_REQUEST);bad['drive']['dc_bus_v']=True;malformed.append(('run_propulsion_pod_three_phase',{'request':bad}))
        bad=copy.deepcopy(DEFAULT_REQUEST);bad['fluid']['kind']='not_a_provider';malformed.append(('validate_propulsion_pod_three_phase',{'request':bad}))
        malformed.append(('propulsion_pod_three_phase_capabilities',{'extra':1}))
        for method,params in malformed:
            with self.subTest(method=method,params=params):
                out=self.call(method,params);self.assertFalse(out['ok']);self.assertIn('error',out)
        self.assertIsNone(handle_propulsion_pod_request('not_a_pod_route',{}))
        self.assertFalse(self.call('not_a_pod_route',{})['ok'])

    def test_actual_compiled_short_run_through_public_service(self):
        request=copy.deepcopy(DEFAULT_REQUEST);request['transient']['duration_s']=.001
        out=self.call('run_propulsion_pod_three_phase',{'request':request})
        self.assertTrue(out['ok'],out)
        result=out['result'];self.assertEqual(result['contract'],RESULT)
        self.assertEqual(result['accepted_steps'],10);self.assertEqual(result['controller_ticks'],2)
        self.assertEqual(len(result['history']),11)
        self.assertEqual(len(result['provenance']['controller_executable_sha256']),64)
        self.assertGreater(result['history'][-1]['speed_rad_s'],0.)
        self.assertLess(result['energy']['maximum_current_sum_a'],1e-12)
        self.assertLess(result['energy']['maximum_phase_kvl_residual_v'],1e-9)
        self.assertLess(abs(result['energy']['defect_j']),1e-8)
        self.assertEqual(result['provenance']['fluid_provider_kind'],'hover_bem')

if __name__=='__main__':unittest.main()
