# SPDX-License-Identifier: Apache-2.0
from contextlib import redirect_stdout,redirect_stderr
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from python.spikes.cli import main


class SMPSCLITests(unittest.TestCase):
    def test_native_default_requires_library_without_reference_fallback(self):
        output=io.StringIO();errors=io.StringIO()
        with redirect_stdout(output),redirect_stderr(errors):status=main(['smps-stability'])
        self.assertEqual(status,2)
        self.assertIn('library',output.getvalue()+errors.getvalue())

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_SMPS_LIBRARY'),'native analysis library required')
    def test_native_default_records_backend(self):
        output=io.StringIO();errors=io.StringIO()
        with redirect_stdout(output),redirect_stderr(errors):
            status=main(['smps-stability','--library',os.environ['SPIKES_TEST_SMPS_LIBRARY']])
        self.assertEqual(status,0,errors.getvalue())
        self.assertIn('C++',json.loads(output.getvalue())['backend'])

    def invoke(self,args):
        if '--default-config' not in args:args=[*args,'--backend','reference']
        output=io.StringIO();errors=io.StringIO()
        with redirect_stdout(output),redirect_stderr(errors):status=main(args)
        return status,output.getvalue(),errors.getvalue()

    def test_default_config_and_explicit_averaged_analysis(self):
        status,text,_=self.invoke(['smps-stability','--default-config'])
        self.assertEqual(status,0);config=json.loads(text)
        self.assertEqual(config['topology'],'buck')
        status,text,_=self.invoke(['smps-stability'])
        self.assertEqual(status,0);result=json.loads(text)
        self.assertIn('closed_loop_poles_rad_s',result)
        self.assertEqual(result['config'],config)

    def test_duplicate_and_invalid_config_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json';path.write_text('{"duty_cycle":0.2,"duty_cycle":0.5}',encoding='ascii')
            status,text,errors=self.invoke(['smps-stability','--config',str(path)])
            self.assertEqual(status,2);self.assertIn('Duplicate',text+errors)
            path.write_text('[]',encoding='ascii')
            status,text,errors=self.invoke(['smps-stability','--config',str(path)])
            self.assertEqual(status,2);self.assertIn('object',text+errors)

    def test_bundled_power_and_isolated_examples(self):
        root=Path(__file__).resolve().parents[2]/'examples/spikes/smps_stability'
        for name,voltage,power in [('buck_5w',12,5),('buck_1kw',200,1000),
                                   ('buck_1mw',750,1e6),('flyback_24w',12,24)]:
            with self.subTest(example=name):
                status,text,_=self.invoke(['smps-stability','--config',str(root/(name+'.json'))])
                self.assertEqual(status,0,text);result=json.loads(text)
                self.assertAlmostEqual(result['operating_point']['output_voltage_v'],voltage)
                self.assertAlmostEqual(result['operating_point']['output_power_w'],power)
                self.assertEqual(result['model_status'],'approximate')
                self.assertTrue(result['ccm']['admissible'])

    def test_output_cannot_replace_input_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'setup.json';original='{"controller_gain":5}'
            path.write_text(original,encoding='ascii')
            status,text,errors=self.invoke(['smps-stability','--config',str(path),'-o',str(path)])
            self.assertEqual(status,2);self.assertIn('overwrite',text+errors)
            self.assertEqual(path.read_text(encoding='ascii'),original)
