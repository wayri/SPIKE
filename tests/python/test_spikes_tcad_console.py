# SPDX-License-Identifier: Apache-2.0
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('SPIKES_TEST_TCAD_CONSOLE'),'native TCAD console required')
class TcadConsoleTests(unittest.TestCase):
    def invoke(self,*args):
        return subprocess.run([os.environ['SPIKES_TEST_TCAD_CONSOLE'],*args],capture_output=True,text=True,
                              timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

    def test_native_pn_result_and_inferred_contact_difference(self):
        result=self.invoke('--grid','401')
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout);self.assertTrue(data['converged'])
        self.assertEqual(len(data['potential_v']),401)
        self.assertEqual(len(data['face_electric_field_v_per_m']),400)
        self.assertLessEqual(data['residual_norm'],data['residual_tolerance'])
        vt=1.380649e-23*300/1.602176634e-19
        expected=2*vt*math.asinh(1e22/(2*1.45e16))
        self.assertAlmostEqual(data['potential_v'][-1]-data['potential_v'][0],expected,delta=1e-13)
        self.assertEqual(data['backend'],'SPIKES C++')

    def test_exact_intrinsic_uniform_and_output_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'result.json'
            result=self.invoke('--profile','uniform','--density-m3','0','--output',str(path))
            self.assertEqual(result.returncode,0,result.stderr)
            original=path.read_bytes();data=json.loads(original)
            self.assertEqual(max(map(abs,data['electric_field_v_per_m'])),0.)
            result=self.invoke('--output',str(path))
            self.assertEqual(result.returncode,2)
            self.assertEqual(path.read_bytes(),original)

    def test_bad_geometry_grid_and_doping_file_rejected(self):
        for args in [('--grid','2'),('--grid','3garbage'),('--temperature-k','0'),('--profile','biased_transport')]:
            with self.subTest(args=args):self.assertEqual(self.invoke(*args).returncode,2)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'doping.txt';path.write_text('1 2',encoding='utf-8')
            self.assertEqual(self.invoke('--grid','3','--doping-file',str(path)).returncode,2)
