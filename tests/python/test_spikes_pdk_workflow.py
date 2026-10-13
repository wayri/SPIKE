# SPDX-License-Identifier: Apache-2.0
from contextlib import redirect_stdout,redirect_stderr
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from python.spikes.pdk_workflow import _library,prepare,run


class PdkWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        (self.root/'LICENSE').write_text('Original synthetic test data; Apache-2.0',encoding='utf-8')
        (self.root/'model.lib').write_text('.lib tt\n.include "core.spice"\n.endl tt\n.lib ff\n.include "missing.spice"\n.endl ff\n',encoding='utf-8')
        (self.root/'core.spice').write_text('* Original synthetic model, not SKY130\n.model TEST NMOS (LEVEL=1 VTO=.4 KP=.001)\n',encoding='utf-8')
        self.config=dict(pdk_id='sky130',root=str(self.root),entry='model.lib',corner='tt',temperature_c=27,
                         backend='ngspice',circuit='VD d 0 1\nVG g 0 0\nM1 d g 0 0 TEST W=1u L=1u\n.dc VG 0 1 .5')

    def test_cli_catalog_prepare_export_and_input_preservation(self):
        from python.spikes.cli import main
        config=self.root/'config.json';deck=self.root/'run.cir';report=self.root/'report.json'
        original=json.dumps(self.config);config.write_text(original,encoding='utf-8')
        model_original=(self.root/'core.spice').read_bytes()
        with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            self.assertEqual(main(['pdk','catalog']),0)
            self.assertEqual(main(['pdk','prepare','--config',str(config),'--deck',str(deck),'-o',str(report)]),0)
            self.assertEqual(main(['pdk','prepare','--config',str(config),'--deck',str(deck)]),2)
            self.assertEqual(main(['pdk','prepare','--config',str(config),'-o',str(config)]),2)
            self.assertEqual(main(['pdk','run','--config',str(config)]),2)
            self.assertEqual(main(['pdk','prepare','--config',str(config),'-o',str(self.root/'core.spice')]),2)
        self.assertEqual(config.read_text(encoding='utf-8'),original)
        self.assertEqual((self.root/'core.spice').read_bytes(),model_original)
        self.assertIn('.model TEST',deck.read_text(encoding='utf-8'))
        self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['status'],'prepared')

    def test_selected_corner_dependencies_digest_and_inert_preparation(self):
        result=prepare(self.config)
        self.assertEqual(result['status'],'prepared')
        self.assertEqual(result['backend'],'ngspice')
        self.assertNotIn('missing.spice',result['source'])
        self.assertNotIn('.include',result['source'])
        self.assertEqual(len(result['dependencies']),2)
        self.assertEqual(len(result['approval_sha256']),64)
        self.assertEqual(prepare(self.config)['approval_sha256'],result['approval_sha256'])
        with self.assertRaises(ValueError):run(result,approval_sha256='0'*64)
        digest=result['approval_sha256'];result['source']+='* modified\n'
        with self.assertRaises(ValueError):run(result,approval_sha256=digest)

    def test_fail_closed_native_missing_corner_and_unsafe_source(self):
        for change in [dict(backend='native'),dict(corner='ff'),dict(corner='absent'),
                       dict(circuit='.include secret'),dict(circuit='.control\nshell whatever\n.endc'),
                       dict(circuit='V1 a 0 1\n.temp 100'),dict(temperature_c=-273.15)]:
            with self.subTest(change=change),self.assertRaises((ValueError,OSError)):
                prepare(dict(self.config,**change))

    def test_library_rejects_cycles_escape_ambiguous_corner_and_loader(self):
        for body in ['.lib tt\n.include model.lib\n.endl',
                     '.lib tt\npre_osdi model.osdi\n.endl',
                     '.lib tt\n.param a=1\n.endl\n.lib tt\n.param a=2\n.endl',
                     '.lib tt\n.include ../outside.spice\n.endl',
                     '.lib tt\n.param a=1']:
            (self.root/'model.lib').write_text(body,encoding='utf-8')
            with self.subTest(body=body),self.assertRaises((ValueError,OSError)):
                _library(self.root,self.root/'model.lib','tt')

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_NGSPICE'),'explicit ngspice fixture execution')
    def test_actual_compiled_backend_on_synthetic_not_foundry_model(self):
        from unittest.mock import patch
        prepared=prepare(self.config)
        with patch('python.spike_core.ngspice_plugin._find_ngspice',return_value=os.environ['SPIKES_TEST_NGSPICE']):
            result=run(prepared,approval_sha256=prepared['approval_sha256'])
        self.assertEqual(result['status'],'completed',result.get('issues'))
        self.assertFalse(result['provenance']['pdk_qualification'])
        self.assertEqual(result['provenance']['pdk_approval_sha256'],prepared['approval_sha256'])


if __name__=='__main__':unittest.main()
