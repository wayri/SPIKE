from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.release_policy import CONTRACT,GATES,evaluate,digest,qt_dependencies


class ReleasePolicyTests(unittest.TestCase):
    def test_empty_and_skipped_never_pass(self):
        self.assertFalse(evaluate({},'.')['releasable'])
        self.assertEqual(len(evaluate({},'.')['gates']),len(GATES))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'evidence.txt';path.write_text('unit-test fixture, not real qualification')
            record=dict(status='passed',reviewed_by='test fixture',checks=dict(total=1,failed=0,skipped=0),artifacts=[dict(path=path.name,sha256=digest(path))])
            evidence=dict(contract=CONTRACT,candidate_sha256='test candidate',gates={key:record.copy() for key in GATES})
            self.assertTrue(evaluate(evidence,folder,candidate_sha256='test candidate')['releasable'])
            self.assertFalse(evaluate(evidence,folder,candidate_sha256='different candidate')['releasable'])
            evidence['gates']['gui_workflows']['checks']=dict(total=3,failed=0,skipped=1)
            self.assertFalse(evaluate(evidence,folder)['releasable'])
            evidence['gates']['gui_workflows']['checks']=dict(total=3,failed=0,skipped=0)
            path.write_text('changed artifact')
            self.assertFalse(evaluate(evidence,folder)['releasable'])

    def test_qt_scan(self):
        forbidden=['PySide6/QtCore.pyd','PyQt5.QtCore','Qt6Core.dll','libQt5Gui.so.5','pyqtgraph','vtkmodules.qt.QVTKRenderWindowInteractor']
        self.assertEqual(qt_dependencies(forbidden),sorted(forbidden))
        self.assertEqual(qt_dependencies(['wx._core','matplotlib.backends.backend_wxagg','plotly','no-qt-policy.txt']),[])
