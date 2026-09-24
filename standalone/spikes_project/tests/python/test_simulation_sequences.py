from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.simulation_setup import default_profile
from spikes_studio.simulation_sequences import validate,plan


class Sequences(unittest.TestCase):
    def sequence(self):
        return {'name':'Qualification','entries':[{'enabled':True,'profile':default_profile()|{'name':'Bias','analysis':'operating_point'}},{'enabled':True,'profile':default_profile()|{'name':'Startup','analysis':'transient'}}]}
    def test_order_overrides_and_persistence(self):
        sequence=self.sequence();jobs=plan(RC_DECK,sequence)
        self.assertIn('.op',jobs[0]['source']);self.assertIn('.tran',jobs[1]['source'])
        d=Document.from_netlist(RC_DECK);d.commit(lambda data:data.update(simulation_sequences=[sequence]))
        self.assertEqual(Document(d.data).data['simulation_sequences'],[sequence]);self.assertEqual(d.data['source'],RC_DECK)
        d.undo();self.assertEqual(d.data['simulation_sequences'],[])
    def test_disabled_selected_and_rejections(self):
        s=self.sequence();s['entries'][0]['enabled']=False
        self.assertEqual([j['index'] for j in plan(RC_DECK,s)],[1])
        self.assertEqual(plan(RC_DECK,s,0)[0]['index'],0)
        with self.assertRaises(ValueError):validate([s,s])
        s['entries'][1]['profile']['execution']='continuous'
        with self.assertRaises(ValueError):validate([s])

    def test_explicit_compatibility_job_preserves_backend(self):
        sequence=self.sequence()
        sequence['entries'][0]['profile']['backend']='ngspice'
        jobs=plan(RC_DECK,sequence,0)
        self.assertEqual(jobs[0]['profile']['backend'],'ngspice')
        with self.assertRaisesRegex(ValueError,'Unsafe ngspice directive'):
            plan(RC_DECK.replace('.end','.include vendor.lib\n.end'),sequence,0)
