from pathlib import Path
import sys
import unittest
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document, RC_DECK
from spikes_studio.model_fidelity import default_policy, inherited, preflight, resolve


class FidelityTests(unittest.TestCase):
    def test_parent_enforcement(self):
        p=default_policy()
        p['subsheets']['X1']={'tier':'ideal','enforce':True}
        p['components']['X1:R1']={'tier':'validated','enforce':False}
        active,origin,lock,ignored=inherited(p,'X1:R1')
        self.assertEqual((active['tier'],origin,lock,ignored),('ideal','X1','X1',['X1:R1']))
        p['schematic']['enforce']=True
        self.assertEqual(inherited(p,'X1:R1')[1],'schematic')

    def test_preflight_and_roundtrip(self):
        doc=Document.from_netlist(RC_DECK)
        report=preflight(doc.data)
        self.assertFalse(report['errors']);self.assertEqual(report['analysis'],'tran')
        self.assertEqual(report['source'],RC_DECK)
        doc.commit(lambda d:d['model_policy']['components'].update(R1={'tier':'ideal','enforce':False}))
        self.assertEqual(Document(doc.data).data['model_policy'],doc.data['model_policy'])
        doc.undo();self.assertFalse(doc.data['model_policy']['components'])

    def test_no_silent_fallback(self):
        for entry in ({'tier':'validated','enforce':False},
                      {'tier':'ideal','enforce':False,'required_parasitics':['ESR']}):
            doc=Document.from_netlist(RC_DECK)
            doc.data['model_policy']['components']['C1']=entry
            with self.assertRaises(ValueError):preflight(doc.data)
        doc=Document.from_netlist(RC_DECK)
        doc.data['model_policy']['components']['MISSING']={'tier':'source','enforce':False}
        self.assertTrue(resolve(doc.data)['errors'])

    def test_analysis_gate(self):
        doc=Document.from_netlist(RC_DECK)
        doc.data['model_policy']['schematic']={'tier':'ideal','enforce':True}
        with self.assertRaises(ValueError):preflight(doc.data,'noise')
