import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from python.spikes.mixed_library import inspect_library, CONTRACT


class MixedLibraryTests(unittest.TestCase):
    def test_integrity_and_no_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b'not a real DLL'
            (root / 'model.dll').write_bytes(payload)
            data = dict(contract=CONTRACT, id='example', version='1', license='MIT', modules=[
                dict(id='motor', kind='dll', domains=['mechanical', 'electrical'],
                     path='model.dll', sha256=hashlib.sha256(payload).hexdigest())])
            manifest = root / 'library.json'
            manifest.write_text(json.dumps(data))
            self.assertFalse(inspect_library(manifest)['execution_enabled'])
            for bad in ('../model.dll', 'C:/model.dll', '/model.dll', 'a\\model.dll'):
                data['modules'][0]['path'] = bad
                manifest.write_text(json.dumps(data))
                with self.assertRaises(ValueError): inspect_library(manifest)
            data['modules'][0]['path'] = 'model.dll'
            data['modules'][0]['sha256'] = '0' * 64
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError): inspect_library(manifest)
