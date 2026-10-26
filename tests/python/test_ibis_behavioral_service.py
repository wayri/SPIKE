# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from python.spike_core.service import handle


class BehavioralServiceTests(unittest.TestCase):
    def request(self):
        return json.loads((Path(__file__).resolve().parents[2] / "examples/si/ibis_driver_receiver/request.json").read_text())

    def test_compile_dispatch_never_launches(self):
        with patch("python.spike_core.solvers.signal_integrity.receivers.ibis_behavioral_execution.supervise_process") as launch:
            result = handle({"method": "compile_ibis_behavioral", "params": {"request": self.request()}})
        launch.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["status"], "ready")

    def test_raw_netlist_and_implicit_native_execution_rejected(self):
        with patch("python.spike_core.solvers.signal_integrity.receivers.ibis_behavioral_execution.supervise_process") as launch:
            for method, params in (("compile_ibis_behavioral", {"netlist": "arbitrary"}),
                                   ("run_ibis_behavioral", {"request": self.request(), "executable": "unused", "executable_sha256": "a"*64, "execution_requested": False}),
                                   ("run_ibis_behavioral", {"request": self.request(), "executable": "unused", "executable_sha256": None, "execution_requested": True})):
                with self.subTest(method=method, params=list(params)):
                    self.assertFalse(handle({"method": method, "params": params})["ok"])
        launch.assert_not_called()

    def test_spatial_context_reaches_public_dispatch(self):
        from tests.python.test_si_spatial_context import SpatialContextTests
        result = handle({"method": "inspect_si_spatial_context", "params": SpatialContextTests().params()})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["victimNetId"], "V")


if __name__ == "__main__": unittest.main()
