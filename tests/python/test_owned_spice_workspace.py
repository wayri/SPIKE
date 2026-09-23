# SPDX-License-Identifier: MIT
import unittest
from unittest.mock import patch

from python.spike_core.owned_spice_workspace import (
    REQUEST_CONTRACT,
    RESULT_CONTRACT,
    run_owned_spice_workspace,
    validate_owned_spice_workspace_request,
)
from python.spike_core.service import handle
from tests.python.test_native_circuit_compiler import design, workspace


def request(**updates):
    value = {
        "contract": REQUEST_CONTRACT,
        "request_id": "owned-spice-1",
        "workspace": workspace(),
        "probes": [],
        "resource_limits": {
            "maximum_netlist_bytes": 2 * 1024 * 1024,
            "maximum_result_bytes": 64 * 1024 * 1024,
            "maximum_probes": 16,
        },
    }
    value.update(updates)
    return value


class OwnedSpiceWorkspaceTests(unittest.TestCase):
    def test_structured_workspace_executes_the_release_owned_engine(self):
        result = run_owned_spice_workspace(
            request(probes=["V(VIN)", "I(V1)", "P(V1)"]), design(),
        )
        self.assertEqual(result["contract"], RESULT_CONTRACT)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["circuit_result"]["contract"], "spikes/circuit-result/v1")
        self.assertEqual(
            result["netlist_sha256"],
            result["circuit_result"]["provenance"]["source_sha256"],
        )
        self.assertNotIn("library", result["circuit_result"]["provenance"])
        self.assertEqual(result["circuit_result"]["provenance"]["library_origin"], "release_owned")
        self.assertTrue(result["provenance"]["structured_workspace_only"])
        self.assertIn("V(VIN)", result["circuit_result"]["probes"])
        self.assertEqual(
            result["circuit_result"]["probes"]["V(VIN)"]["descriptor"]["targets"],
            ["vin"],
        )
        self.assertIn("I(V1)", result["circuit_result"]["probes"])
        self.assertIn("P(V1)", result["circuit_result"]["probes"])

    def test_raw_netlist_and_unknown_limits_fail_closed(self):
        raw = request(netlist="V1 out 0 1\n.op\n")
        validation = validate_owned_spice_workspace_request(raw, design())
        self.assertFalse(validation["valid"])
        self.assertEqual(validation["issues"][0]["code"], "SPIKE-BE-SPICE-E-0050")

        bad_limit = request(resource_limits={"executable": "calc.exe"})
        validation = validate_owned_spice_workspace_request(bad_limit, design())
        self.assertFalse(validation["valid"])
        self.assertIn("SPIKE-BE-SPICE-E-0051", {item["code"] for item in validation["issues"]})

    def test_probe_identity_is_unique_after_parser_canonicalization(self):
        validation = validate_owned_spice_workspace_request(
            request(probes=["V(out)", " v(OUT) "]), design(),
        )
        self.assertFalse(validation["valid"])
        self.assertIn(
            "unique after canonicalization",
            next(item["message"] for item in validation["issues"] if item["path"] == "probes[1]"),
        )
        for expression in ("V(not_a_workspace_node)", "I(not_a_workspace_element)"):
            unknown = validate_owned_spice_workspace_request(
                request(probes=[expression]), design(),
            )
            self.assertFalse(unknown["valid"])
            self.assertEqual(
                next(item for item in unknown["issues"] if item["path"] == "probes")["code"],
                "SPIKE-BE-SPICE-E-0052",
            )

    def test_malformed_owned_engine_result_is_not_republished(self):
        malformed = {
            "contract": "spikes/circuit-result/v1",
            "status": "completed",
            "model_status": "validated",
            "analysis": {},
            "data": {},
            "probes": {},
            "diagnostics": {},
            "measurements": {},
            "issues": [],
            "provenance": {"source_sha256": "unreachable"},
        }
        with patch("python.spike_core.owned_spice_workspace.run_netlist", return_value=malformed):
            with self.assertRaisesRegex(RuntimeError, "unsupported model status"):
                run_owned_spice_workspace(request(), design())

    def test_worker_exposes_validation_and_execution(self):
        params = {"design": design().to_dict(), "request": request()}
        validation = handle({"id": "owned-spice-validate", "method": "validate_owned_spice_workspace", "params": params})
        executed = handle({"id": "owned-spice-run", "method": "run_owned_spice_workspace", "params": params})
        self.assertTrue(validation["ok"])
        self.assertTrue(validation["result"]["valid"])
        self.assertTrue(executed["ok"])
        self.assertEqual(executed["result"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
