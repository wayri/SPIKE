# SPDX-License-Identifier: Apache-2.0
import unittest
from python.spike_core.service import handle
from python.spike_core.mcp_server import TOOLS
from tests.python.test_harness_signal import fixture
from tests.python.test_harness_mtl import fixture as mtl_fixture
from tests.python.test_harness_rlgc_geometry import fixture as geometry_fixture


class HarnessAnalysisWorkerTests(unittest.TestCase):
    def test_multiconductor_and_geometry_are_strict_worker_operations(self):
        for method, request, tool in (
            ("run_harness_mtl", mtl_fixture(2), "spike_run_harness_mtl"),
            ("extract_harness_round_wire_rlgc", geometry_fixture(), "spike_extract_harness_round_wire_rlgc"),
        ):
            response = handle({"id": method, "method": method, "params": {"request": request}})
            self.assertTrue(response["ok"], response)
            self.assertEqual(TOOLS[tool].method, method)
            self.assertFalse(handle({"id": method, "method": method, "params": {"request": request, "infer": True}})["ok"])

    def test_si_actual_worker_preserves_supplied_request(self):
        request = fixture()
        response = handle({"id": "harness-si-test", "method": "run_harness_si", "params": {"request": request}})
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["request_snapshot"], request)
        self.assertEqual(response["result"]["mode"], "differential")
        self.assertEqual(len(response["result"]["frequency_hz"]), 9)
        self.assertEqual(TOOLS["spike_run_harness_si"].method, "run_harness_si")

    def test_em_is_explicitly_unsupported_and_transport_is_strict(self):
        request = {"contract": "spike/harness-em-request/v1", "harness": fixture()["harness"], "wire_ids": ["p", "n"]}
        response = handle({"id": "harness-em-test", "method": "prepare_harness_em", "params": {"request": request}})
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["status"], "unsupported")
        self.assertFalse(response["result"]["field_coupling_executed"])
        self.assertFalse(handle({"id": "extra", "method": "prepare_harness_em", "params": {"request": request, "infer": True}})["ok"])


if __name__ == "__main__":
    unittest.main()
