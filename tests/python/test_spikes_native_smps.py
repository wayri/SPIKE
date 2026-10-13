# SPDX-License-Identifier: Apache-2.0
import ctypes as ct
import json
import os
import unittest
import numpy as np
from python.spikes.smps_stability import analyze as reference,default_config,TOPOLOGIES,CONTROLLERS
from python.spikes.native_smps import analyze,Config,_library
from pathlib import Path

LIBRARY=os.environ.get('SPIKES_TEST_SMPS_LIBRARY')


@unittest.skipUnless(LIBRARY,'explicit new native SMPS library required')
class NativeSMPSChecks(unittest.TestCase):
    def test_all_topologies_controllers_and_bulk_arrays(self):
        for topology in TOPOLOGIES:
            for controller in CONTROLLERS:
                config=dict(topology=topology,controller_type=controller,controller_gain=5,points=101)
                expected=reference(config);actual=analyze(config,LIBRARY)
                self.assertEqual(actual['stability'],expected['stability'])
                self.assertIn('C++',actual['backend'])
                for key in ('frequency_hz','plant','loop','plant_gain_db','plant_phase_deg','loop_gain_db','loop_phase_deg'):
                    np.testing.assert_allclose(actual[key],expected[key],rtol=1e-10,atol=1e-9,err_msg=topology+'/'+controller+'/'+key)
                for key in ('plant_poles_rad_s','plant_zeros_rad_s','closed_loop_poles_rad_s'):
                    a=np.array([complex(*v) for v in actual[key]]);b=[complex(*v) for v in expected[key]]
                    self.assertEqual(len(a),len(b))
                    for pole in b:self.assertLess(min(abs(a-pole),default=0),1e-6*max(1,abs(pole)))
                for key in ('gain_crossings','phase_crossings'):
                    self.assertEqual(len(actual['margins'][key]),len(expected['margins'][key]))
                    for a,b in zip(actual['margins'][key],expected['margins'][key]):
                        self.assertAlmostEqual(a['frequency_hz']/b['frequency_hz'],1,delta=1e-8)
                json.dumps(actual,allow_nan=False)

    def test_invalid_and_native_abi_version_rejection(self):
        with self.assertRaises(ValueError):analyze({'load_resistance_ohm':1e9},LIBRARY)
        path=Path(LIBRARY).resolve();stat=path.stat();native=_library(str(path),stat.st_mtime_ns,stat.st_size)
        bad=Config();bad.api_version=99;bad.struct_size=ct.sizeof(Config);result=ct.c_void_p(123)
        self.assertNotEqual(native._library.spikes_smps_analyze(ct.byref(bad),ct.byref(result)),0)
        self.assertIsNone(result.value)
        native._library.spikes_smps_result_destroy(None)
