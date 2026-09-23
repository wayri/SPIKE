from pathlib import Path
import sys
import tempfile
import unittest
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.library_package import save,load,merge
from spikes_studio.component_catalog import catalog


class PackageTests(unittest.TestCase):
    def test_roundtrip_and_conflict(self):
        records=catalog()['records'][:2]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'library.spklib';save(path,records,[])
            self.assertEqual(load(path)['records'],records)
        self.assertEqual(merge(records,records),records)
        changed=deepcopy(records);changed[0]['name']='different'
        with self.assertRaises(ValueError):merge(records,changed)
    def test_execution_claim_rejected(self):
        from spikes_studio.library_package import validate,CONTRACT
        record=next(r for r in catalog()['records'] if r['family']=='and');record['status']='native_subcircuit'
        with self.assertRaises(ValueError):validate({'contract':CONTRACT,'records':[record],'symbols':[]})
