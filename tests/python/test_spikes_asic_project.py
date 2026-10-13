# SPDX-License-Identifier: Apache-2.0
import hashlib
from contextlib import redirect_stdout,redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from python.spikes.asic_project import CONTRACT,plan


class AsicProjectTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.project=dict(contract=CONTRACT,name='demo',kind='digital',top='top',pdk_revision='synthetic-fixture-rev1',
                          artifacts=[],engines={},runsets={})

    def artifact(self,path,text):
        (self.root/path).write_text(text,encoding='utf-8')
        return dict(path=path,sha256=hashlib.sha256((self.root/path).read_bytes()).hexdigest())

    def test_missing_gates_are_blocked_and_never_claim_release(self):
        result=plan(self.project,self.root)
        self.assertEqual(result['user_facing_applications'],['SPIKES','KLayout'])
        self.assertFalse(result['release_ready'])
        self.assertTrue(all(row['status']=='blocked' and row['evidence_status']=='not_run' for row in result['stages']))
        self.assertIn('parasitic_extraction',[row['id'] for row in result['stages']])

    def test_mixed_signal_requires_explicit_analog_macro_views(self):
        result=plan(dict(self.project,kind='mixed_signal'),self.root)
        physical=next(stage for stage in result['stages'] if stage['id']=='floorplan_place_cts_route')
        self.assertIn('analog_macro_lef',physical['required_inputs'])
        self.assertTrue(any(stage['id']=='post_layout_simulation' for stage in result['stages']))
        self.assertFalse(result['qualification'])

    def test_matching_inputs_do_not_fabricate_stage_results(self):
        rtl=self.artifact('top.v','module top(); endmodule\n')
        tool=self.artifact('synthetic-engine','not executable, preflight identity fixture')
        deck=self.artifact('lint.script','original inert fixture')
        self.artifact('engine-license.txt','Synthetic fixture Apache-2.0')
        self.project['artifacts']=[dict(rtl,role='rtl')]
        self.project['engines']={'synthesis':dict(tool,license_record='engine-license.txt')}
        self.project['runsets']={'rtl_check':deck}
        result=plan(self.project,self.root)
        self.assertEqual(result['stages'][0]['status'],'ready_for_review')
        self.assertEqual(result['stages'][0]['evidence_status'],'not_run')
        (self.root/'top.v').write_text('changed',encoding='utf-8')
        self.assertEqual(plan(self.project,self.root)['stages'][0]['status'],'blocked')

    def test_unknown_unpinned_and_escaping_inputs_fail(self):
        for change in [dict(pdk_revision=''),dict(kind='auto_signoff'),dict(runsets={'unknown':{}})]:
            with self.assertRaises(ValueError):plan(dict(self.project,**change),self.root)
        self.project['artifacts']=[dict(role='rtl',path='../outside.v',sha256='0'*64)]
        with self.assertRaises(ValueError):plan(self.project,self.root)

    def test_cli_roundtrip_preserves_project(self):
        from python.spikes.cli import main
        path=self.root/'demo.spkasic';original=json.dumps(self.project)
        path.write_text(original,encoding='utf-8')
        with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            self.assertEqual(main(['asic-plan',str(path)]),0)
            self.assertEqual(main(['asic-plan',str(path),'-o',str(path)]),2)
        self.assertEqual(path.read_text(encoding='utf-8'),original)


if __name__=='__main__':unittest.main()
