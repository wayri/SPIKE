from pathlib import Path
import sys
import unittest
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document, RC_DECK
from spikes_studio.model_fidelity import default_policy, inherited, preflight, preflight_compatibility, resolve


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

    def test_compatibility_preflight_is_explicit_and_does_not_rewrite_models(self):
        doc=Document.from_netlist(RC_DECK);original=doc.data['source']
        report=preflight_compatibility(doc.data)
        self.assertEqual(report['backend'],'ngspice')
        self.assertEqual(report['model_status'],'solver_dependent')
        self.assertEqual(doc.data['source'],original)
        for selection in ({'tier':'ideal','enforce':False},
                          {'tier':'source','enforce':False,'parasitic_values':{'esr_ohm':0.1}}):
            candidate=deepcopy(doc.data)
            candidate['model_policy']['components']['C1']=selection
            with self.assertRaisesRegex(ValueError,'Compatibility model preflight'):
                preflight_compatibility(candidate)
        candidate=deepcopy(doc.data)
        candidate['source']=original.replace('.end','.include vendor.lib\n.end')
        with self.assertRaisesRegex(ValueError,'Unsafe ngspice directive'):
            preflight_compatibility(candidate)
