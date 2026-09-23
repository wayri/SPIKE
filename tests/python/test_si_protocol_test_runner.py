from __future__ import annotations

import unittest

from tests.python.test_si_channel import SiUniformChannelTests
from python.spike_core.service import handle
from python.spike_core.si_protocol_test_runner import (
    REQUEST_CONTRACT, SiProtocolTestRunnerError, run_si_protocol_test_suite,
)


def fixture_suite() -> dict:
    analysis_ids = ["topology", "impedance", "rlgc", "s_parameters", "tdr_tdt", "eye", "jitter", "compliance_review"]
    return {
        "contract": "spike/si-protocol-suite/v1",
        "id": "fixture.ddr.screen",
        "name": "Fixture DDR screen",
        "family": "DDR",
        "revision": "fixture",
        "description": "Test-only declarative suite without normative limits.",
        "signaling": "parallel_bus",
        "encoding": "NRZ",
        "topology": ["controller", "channel", "memory"],
        "requiredInputs": ["signal net", "reference layer"],
        "analyses": [{
            "id": analysis_id,
            "name": analysis_id,
            "requiredCapabilities": [],
            "status": "solver_gated" if analysis_id != "topology" else "available_input_review",
        } for analysis_id in analysis_ids],
        "rules": [],
        "provenance": {
            "title": "Test fixture",
            "locator": "local:test",
            "access": "user_defined",
            "reviewedOn": "2026-08-31",
        },
        "qualification": "setup_only",
        "custom": True,
    }


class SiProtocolTestRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = SiUniformChannelTests()
        self.design = fixture.design()
        self.channel = fixture.request()

    def request(self) -> dict:
        return {
            "contract": REQUEST_CONTRACT,
            "suite": fixture_suite(),
            "lanes": [{"lane_id": "DQ0", "channel_request": self.channel}],
        }

    def test_suite_executes_supported_tests_and_blocks_unbound_compliance(self) -> None:
        result = run_si_protocol_test_suite(self.design, self.request())
        self.assertEqual(result["contract"], "spike/si-protocol-test-suite-result/v1")
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["production_qualified"])
        tests = {item["analysis_id"]: item for item in result["lanes"][0]["tests"]}
        self.assertEqual(tests["s_parameters"]["status"], "completed")
        self.assertEqual(tests["eye"]["status"], "completed")
        self.assertEqual(tests["jitter"]["status"], "blocked")
        self.assertEqual(tests["compliance_review"]["status"], "blocked")

    def test_resource_limits_fail_closed(self) -> None:
        request = self.request()
        request["resource_limits"] = {"maximum_lanes": 1, "maximum_frequency_points": 10, "maximum_estimated_numeric_bytes": 1024}
        with self.assertRaisesRegex(SiProtocolTestRunnerError, "frequency points"):
            run_si_protocol_test_suite(self.design, request)

    def test_explicit_pam4_lane_executes_eye_and_pam4_stages_without_compliance(self) -> None:
        request = self.request()
        channel = request["lanes"][0]["channel_request"]
        channel.pop("bit_rate_hz")
        channel.pop("bit_count")
        channel["symbol_rate_hz"] = 1.0e9
        channel["symbol_count"] = 512
        channel["pam4_model"] = {
            "tx_ffe_taps": [1.0], "rx_dfe_taps": [0.0],
            "voltage_noise_rms_normalized": 0.01, "phase_bins": 17,
            "target_ber": 1.0e-6, "cdr_mode": "ideal_phase_search",
        }
        request["requested_tests"] = ["eye", "pam4", "compliance_review"]
        result = run_si_protocol_test_suite(self.design, request)
        tests = {item["analysis_id"]: item for item in result["lanes"][0]["tests"]}
        self.assertEqual(tests["eye"]["status"], "completed")
        self.assertEqual(tests["pam4"]["status"], "completed")
        self.assertEqual(tests["compliance_review"]["status"], "blocked")
        self.assertFalse(result["summary"]["protocol_pass_claimed"])

    def test_worker_route_returns_the_same_honest_contract(self) -> None:
        response = handle({"id": "suite-1", "method": "run_si_protocol_test_suite", "params": {
            "design": self.design.to_dict(), "request": self.request(),
        }})
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["compliance_status"], "not_evaluated")
        self.assertFalse(response["result"]["summary"]["protocol_pass_claimed"])


if __name__ == "__main__":
    unittest.main()
