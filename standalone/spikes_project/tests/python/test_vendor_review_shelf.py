from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.vendor_intake import inspect_text,store_review
from spikes_studio.document import Document


class VendorShelfTests(unittest.TestCase):
    def test_continuations_parameters_pins_and_dependencies(self):
        report=inspect_text('.subckt AMP INP INN\n+ VP VN OUT params: gain=10\nG1 OUT 0 VALUE={IF(V(INP)>0,1,0)}\nX1 OUT 0 missing\n.include external.lib\n.ends\n.model DS D(KF=1e-10)')
        self.assertEqual(report['subcircuits'][0]['pins'],['INP','INN','VP','VN','OUT'])
        self.assertEqual(report['inventory']['unresolved_subcircuits'],['missing'])
        self.assertEqual(report['dependencies_not_loaded'],['external.lib'])
        self.assertIn('behavioral VALUE',report['inventory']['features_requiring_review'])
        self.assertEqual(report['execution'],'not_approved')

    def test_review_is_persistent_undoable_and_cannot_self_approve(self):
        doc=Document.from_netlist('Example\nV1 a 0 1\nR1 a 0 1k\n.op\n.end')
        report=inspect_text('.model DTEST D(IS=1p)');report['execution']='approved'
        key=store_review(doc,report,'Example manufacturer','TEST','https://example.com/model')
        self.assertEqual(doc.data['metadata']['manufacturer_models'][key]['execution'],'not_approved')
        self.assertEqual(Document(doc.data).data['metadata']['manufacturer_models'][key]['original_source'],report['original_source'])
        doc.undo();self.assertNotIn('manufacturer_models',doc.data['metadata'])

    def test_invalid_provenance_and_binary(self):
        with self.assertRaises(ValueError):inspect_text('.model X D\x00')
        doc=Document.from_netlist('Example\nV1 a 0 1\nR1 a 0 1k\n.op\n.end')
        with self.assertRaises(ValueError):store_review(doc,inspect_text('.model X D'),'TI','X','file:///model')


if __name__=='__main__':unittest.main()
