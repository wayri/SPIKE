# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Export contract tests using synthetic fixtures, not solver evidence."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.export_crossboard_field import main
from tests.python.test_crossboard_field_screen import write_case


class FieldExportTests(unittest.TestCase):
    def invoke(self,case,out):
        with patch('sys.argv',['export','--case',str(case),'--output',str(out)]),contextlib.redirect_stdout(io.StringIO()):
            return main()

    def test_mapping_provenance_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as temp:
            case=Path(temp)/'case';out=Path(temp)/'export';write_case(case)
            self.assertEqual(self.invoke(case,out),0)
            result=json.loads((out/'loaded-crosstalk.json').read_text())
            self.assertEqual(result['field_provenance']['port_order'],['A.near','A.far','B.near','B.far'])
            self.assertFalse(result['field_provenance']['physical_accuracy_qualified'])
            self.assertTrue((out/'network.s4p').is_file())
            with self.assertRaises(FileExistsError):self.invoke(case,out)

    def test_failed_screen_never_exports_channel(self):
        with tempfile.TemporaryDirectory() as temp:
            case=Path(temp)/'case';out=Path(temp)/'export';write_case(case)
            field=case/'field-result.json';value=json.loads(field.read_text())
            value['s_real'][0][0][0]=2.
            data=json.dumps(value).encode();field.write_bytes(data)
            manifest=case/'execution.json';execution=json.loads(manifest.read_text())
            execution['artifact_sha256']['field-result.json']=hashlib.sha256(data).hexdigest()
            manifest.write_text(json.dumps(execution))
            self.assertEqual(self.invoke(case,out),1)
            self.assertTrue((out/'screening.json').is_file())
            self.assertFalse((out/'network.s4p').exists())
            self.assertFalse((out/'loaded-crosstalk.json').exists())


if __name__=='__main__':unittest.main()
