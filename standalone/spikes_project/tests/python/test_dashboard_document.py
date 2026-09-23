import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio'/'python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.dashboard import widget

class DashboardDocumentTests(unittest.TestCase):
    def test_saved_layout_undo_and_validation(self):
        doc=Document.from_netlist(RC_DECK)
        doc.commit(lambda d:d['dashboard']['widgets'].append(widget('Meter','v(out)')))
        restored=Document(doc.data)
        self.assertEqual(restored.data['dashboard'],doc.data['dashboard'])
        before=doc.data['revision']
        with self.assertRaises(ValueError):
            doc.commit(lambda d:d['dashboard']['widgets'][0].update(width=-1))
        self.assertEqual(doc.data['revision'],before)
        doc.undo();self.assertEqual(doc.data['dashboard']['widgets'],[])
        doc.redo();self.assertEqual(len(doc.data['dashboard']['widgets']),1)

if __name__=='__main__':unittest.main()
