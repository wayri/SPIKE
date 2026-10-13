# SPDX-License-Identifier: Apache-2.0
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from python.spike_core.cli import main,EXIT_VALIDATION
from python.spike_core.contracts import SpiDeR

class CliTests(unittest.TestCase):
    def test_capabilities_use_registered_worker_contract(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):code=main(["spider-capabilities"])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(output.getvalue())["contract"],"spider/api-result/v1")
    def test_query_request_and_validation_failure_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"request.json"
            path.write_text(json.dumps({"document":SpiDeR(design_id="cli",name="CLI").to_dict(),"entity_types":["nets"],"limit":1}))
            output=io.StringIO()
            with contextlib.redirect_stdout(output):code=main(["spider-query","--request",str(path)])
            self.assertEqual(code,0);self.assertEqual(json.loads(output.getvalue())["page"]["limit"],1)
            path.write_text(json.dumps({"document":{"contract":"invalid"}}))
            with contextlib.redirect_stdout(io.StringIO()):code=main(["spider-validate","--request",str(path)])
            self.assertEqual(code,EXIT_VALIDATION)
if __name__=="__main__":unittest.main()
