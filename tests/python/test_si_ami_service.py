# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Process exposure does not admit a native model for execution."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from python.spike_core.service_si_models import handle_si_model_request
from tests.python.test_si_ami_inventory import document, package


class AmiServiceTests(unittest.TestCase):
    def test_exact_wrapper_and_nonexecution(self):
        for method, params in (("inspect_si_ami_parameters", {"text": document()}),
                               ("inspect_si_ami_package", {"request": package()})):
            with self.subTest(method=method):
                reply = handle_si_model_request(method, params)
                self.assertTrue(reply["ok"])
                self.assertFalse(reply["result"]["execution_admitted"])
                self.assertFalse(handle_si_model_request(method, {**params, "execute": True})["ok"])
        self.assertIsNone(handle_si_model_request("run_si_ami_binary", {}))

    def test_fresh_json_line_worker(self):
        message = {"id": "ami-inventory", "method": "inspect_si_ami_package", "params": {"request": package()}}
        run = subprocess.run([sys.executable, "-m", "python.spike_core.service"],
            input=json.dumps(message)+"\n", cwd=Path(__file__).resolve().parents[2],
            capture_output=True, text=True, timeout=30, check=True)
        reply = json.loads(run.stdout)
        self.assertTrue(reply["ok"])
        self.assertFalse(reply["result"]["execution_admitted"])
        self.assertFalse(reply["result"]["abi_verified"])


if __name__ == "__main__":
    unittest.main()
