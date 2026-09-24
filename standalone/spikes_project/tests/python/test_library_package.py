from pathlib import Path
import sys
import tempfile
import unittest
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.library_package import save,load,merge,LibraryStore
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

    def test_persistent_scopes_roundtrip_and_export(self):
        records=catalog()['records'][:1]
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);source=base/'source.spklib';save(source,records,[])
            store=LibraryStore(base/'store')
            installed=store.import_package(source,'generic.passives','1.0.0',scope='installed')
            store.import_package(source,'generic.passives','1.0.0',scope='project')
            self.assertEqual(installed['sha256'],store.list_packages(scope='installed')[0]['sha256'])
            self.assertEqual(len(LibraryStore(base/'store').list_packages()),2)
            self.assertEqual(store.get_package('generic.passives',scope='project')['records'],records)
            target=base/'export.spklib';store.export_package(target,'generic.passives',scope='installed')
            self.assertEqual(load(target)['records'],records)
            self.assertEqual(len(store.search('PASSIVES')),2)

    def test_conflict_update_and_rollback(self):
        records=catalog()['records'][:1]
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);source=base/'source.spklib';save(source,records,[])
            store=LibraryStore(base/'store')
            store.import_package(source,'generic.passives','1.0.0')
            changed=deepcopy(records);changed[0]['name']='Revision two';save(source,changed,[])
            with self.assertRaisesRegex(ValueError,'Conflicting package'):
                store.import_package(source,'generic.passives','1.0.0')
            store.import_package(source,'generic.passives','2.0.0')
            self.assertEqual(store.get_package('generic.passives')['records'],changed)
            self.assertEqual(store.rollback('generic.passives'),'1.0.0')
            self.assertEqual(LibraryStore(base/'store').get_package('generic.passives')['records'],records)
            with self.assertRaisesRegex(ValueError,'No prior'):
                store.rollback('generic.passives')
            store.activate('generic.passives','2.0.0')
            self.assertEqual(store.get_package('generic.passives')['records'],changed)

    def test_tampered_blob_rejected_without_activation(self):
        records=catalog()['records'][:1]
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);source=base/'source.spklib';save(source,records,[])
            store=LibraryStore(base/'store');info=store.import_package(source,'generic.passives','1.0.0')
            blob=base/'store'/'user'/'blobs'/(info['sha256']+'.spklib')
            blob.write_bytes(blob.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'modified'):
                store.get_package('generic.passives')
            with self.assertRaisesRegex(ValueError,'modified'):
                store.export_package(base/'export.spklib','generic.passives')
            self.assertFalse((base/'export.spklib').exists())

    def test_path_traversal_and_invalid_scope_rejected(self):
        records=catalog()['records'][:1]
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);source=base/'source.spklib';save(source,records,[])
            store=LibraryStore(base/'store')
            for package_id,version,scope in (('../outside','1.0.0','user'),('valid','../outside','user'),('valid','1.0.0','../outside')):
                with self.subTest(package_id=package_id,version=version,scope=scope):
                    with self.assertRaises(ValueError):store.import_package(source,package_id,version,scope=scope)
            self.assertFalse((base/'outside').exists())
            self.assertEqual(store.list_packages(),[])
