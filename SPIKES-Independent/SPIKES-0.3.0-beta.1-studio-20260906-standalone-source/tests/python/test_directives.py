from copy import deepcopy
from pathlib import Path
import sys
import os
import time
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.directives import scan,valid_text,OFF


class DirectiveTests(unittest.TestCase):
    def test_legacy_discovers_analysis_and_persists_metadata(self):
        doc=Document.from_netlist(RC_DECK);item=doc.data['directives'][0]
        self.assertEqual(item['group'],'Simulation');self.assertEqual(item['line'],5)
        doc.organize_directives([item['id']],group='Startup checks',x=300,y=600,visible=False)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'a.spksch';doc.save(path)
            self.assertEqual(Document.load(path).data['directives'],doc.data['directives'])
        doc.undo();self.assertTrue(doc.data['directives'][0]['visible']);doc.redo()
        self.assertEqual(doc.data['source'],RC_DECK)

    def test_edit_analysis_updates_netlist_atomically(self):
        doc=Document.from_netlist(RC_DECK);ident=doc.data['directives'][0]['id']
        doc.edit_directive(ident,text='.tran 20u 2m uic',group='Simulation',title='Fast check')
        self.assertIn('.tran 20u 2m uic',doc.data['source']);self.assertEqual(doc.data['revision'],1)
        self.assertEqual(doc.data['directives'][0]['id'],ident)
        doc.undo();self.assertEqual(doc.data['source'],RC_DECK);doc.redo()
        before=deepcopy(doc.data)
        with self.assertRaises(ValueError):doc.edit_directive(ident,text='.invented garbage')
        self.assertEqual(doc.data,before)

    def test_disabled_unsupported_draft_can_round_trip_but_not_enable(self):
        doc=Document.from_netlist(RC_DECK)
        ident=doc.edit_directive(text='.invented behavior\n+ continued',enabled=False,group='Processing')
        self.assertIn(OFF+'.invented',doc.data['source']);self.assertIn(OFF+'+ continued',doc.data['source'])
        item=next(v for v in doc.data['directives'] if v['id']==ident)
        self.assertFalse(item['enabled']);before=deepcopy(doc.data)
        with self.assertRaises(ValueError):doc.edit_directive(ident,text=item['text'],enabled=True)
        self.assertEqual(doc.data,before)
        doc.remove_directives([ident]);self.assertEqual(doc.data['source'],RC_DECK)
        doc.undo();self.assertEqual(doc.data,before)

    def test_supported_parameter_toggle_and_source_reconciliation(self):
        doc=Document.from_netlist(RC_DECK)
        ident=doc.edit_directive(text='.param gain=2',group='Processing')
        doc.edit_directive(ident,text='.param gain=2',enabled=False,group='Tuning',x=245)
        doc.edit_directive(ident,text='.param gain=3',enabled=True,group='Tuning',x=245)
        doc.apply_source(doc.data['source'].replace('.param gain=3','.param gain=4'))
        item=next(v for v in doc.data['directives'] if v['id']==ident)
        self.assertEqual((item['group'],item['x'],item['text']),('Tuning',245,'.param gain=4'))

    def test_parameter_edit_reelaborates_components(self):
        doc=Document.from_netlist(RC_DECK.replace('R1 in out 1k','.param rval=1k\nR1 in out {rval}'))
        part=doc.data['components'][1];pid=part['id'];doc.update([pid],{'package':'0603'})
        item=next(v for v in doc.data['directives'] if v['text'].startswith('.param'))
        doc.edit_directive(item['id'],text='.param rval=2k')
        self.assertEqual(doc.data['components'][1]['value'],'2000')
        self.assertEqual(doc.data['components'][1]['id'],pid)
        self.assertEqual(doc.data['components'][1]['package'],'0603')

    def test_no_structural_or_multistatement_edits(self):
        for text in ('.end','.subckt test a b','.lib vendor\n+ xx','.param a=1\nR1 a 0 1k','.param a=1\n.tran 1u 1m'):
            with self.subTest(text=text),self.assertRaises(ValueError):valid_text(text)
        source='Title\n.subckt foo a b\n.param local=1\n.ends\n.param global=2\n.end\n'
        self.assertEqual([v['text'] for v in scan(source)],['.param global=2'])
        self.assertEqual(scan('Title\n.lib typical\n.model rect D(IS=1p)\n.endl\n.end\n'),[])
        from spikes_studio.directives import rewrite
        source='Title\n.model rect D(IS=1p\n* explanation\n+ N=1)\n.end\n'
        with self.assertRaises(ValueError):rewrite(source,scan(source)[0],'.model rect D(IS=2p)',True)

    def test_duplicate_keywords_keep_exact_match_identity(self):
        doc=Document.from_netlist(RC_DECK);one=doc.edit_directive(text='.param first=1',group='First')
        two=doc.edit_directive(text='.param second=2',group='Second')
        doc.apply_source(doc.data['source'].replace('.param first=1','.param added=0\n.param first=1'))
        self.assertEqual(next(v['group'] for v in doc.data['directives'] if v['id']==one),'First')
        self.assertEqual(next(v['group'] for v in doc.data['directives'] if v['id']==two),'Second')

    def test_bulk_organization_delete_and_rollback(self):
        doc=Document.from_netlist(RC_DECK)
        ids=[doc.edit_directive(text=f'.param p{i}={i}') for i in range(2)]
        doc.organize_directives(ids,group='Processing',visible=False)
        before=deepcopy(doc.data)
        with self.assertRaises(ValueError):doc.organize_directives(ids,x=float('nan'))
        self.assertEqual(doc.data,before)
        doc.remove_directives(ids);self.assertEqual(doc.data['source'],RC_DECK)
        doc.undo();self.assertEqual(doc.data,before)

    def test_bulk_enable_disable_is_one_transaction(self):
        doc=Document.from_netlist(RC_DECK)
        ids=[doc.edit_directive(text=f'.param p{i}={i}') for i in range(2)]
        before=deepcopy(doc.data);doc.enable_directives(ids,False)
        self.assertTrue(all(not v['enabled'] for v in doc.data['directives'] if v['id'] in ids))
        doc.undo();self.assertEqual(doc.data,before)
        draft=doc.edit_directive(text='.invented bad',enabled=False);before=deepcopy(doc.data)
        with self.assertRaises(ValueError):doc.enable_directives([ids[0],draft],True)
        self.assertEqual(doc.data,before)


@unittest.skipUnless(os.environ.get('SPIKES_TEST_LIBRARY'),'Set SPIKES_TEST_LIBRARY for native measurement tests')
class NativeDirectiveTests(unittest.TestCase):
    def test_batch_reduces_native_samples_and_reports_bad_observation(self):
        from spikes_studio.run_control import BatchRun
        source=RC_DECK.replace('.end','.measure tran settling AVG V(out) FROM=1m TO=5m\n.measure tran outside FIND V(out) AT=20m\n.end')
        run=BatchRun(source,os.environ['SPIKES_TEST_LIBRARY'])
        try:
            deadline=time.monotonic()+20
            while run.state=='running' and time.monotonic()<deadline:run.poll();time.sleep(.01)
            self.assertEqual(run.state,'completed',run.error)
            data=run.result['data'];measures=run.result['measurements']
            samples=[v for t,v in zip(data['time_s'],data['node_voltage_v']['out']) if .001<=t<=.005]
            self.assertAlmostEqual(measures['settling']['value'],sum(samples)/len(samples),places=12)
            self.assertEqual(measures['outside']['status'],'failed')
            self.assertIn('native recorded samples',run.result['provenance']['measurement_processing'])
        finally:run.stop()


if __name__=='__main__':unittest.main()
