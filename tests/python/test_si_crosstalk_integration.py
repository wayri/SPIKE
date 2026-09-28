# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from tests.python import test_si_channel as fixtures
from python.spike_core.si_channel import analyze_uniform_design_channel


class CrosstalkIntegrationTests(unittest.TestCase):
    def request(self):
        request = fixtures.SiUniformChannelTests().coupled_request()
        request["crosstalk_model"] = {
            "port_map": {"aggressor_near": 0, "victim_near": 1,
                         "aggressor_far": 2, "victim_far": 3},
            "termination_ohm": [35, 75, 50, 100],
            "waveform_v": [0] * 8 + [1] * 32 + [0] * 24,
            "trace_limit": 64,
        }
        return request

    def test_geometry_result_and_schema(self):
        request = self.request()
        schema = json.loads(Path("schemas/si-uniform-channel-request-v1.schema.json").read_text())
        Draft202012Validator(schema).validate(request)
        result = analyze_uniform_design_channel(fixtures.SiUniformChannelTests().coupled_design(), request)
        loaded = result["crosstalk"]["loaded"]
        self.assertEqual(loaded["time_domain"]["status"], "completed")
        self.assertEqual(len(loaded["time_domain"]["next_v"]), 64)
        self.assertGreater(loaded["time_domain"]["peak_abs_next_v"], 0)
        self.assertEqual(loaded["termination_ohm"], [35, 75, 50, 100])
        json.dumps(result, allow_nan=False)

    def test_invalid_model_rejected_before_geometry_allocation(self):
        for change in ({"shell": "bad"}, {"termination_ohm": [50]},
                       {"port_map": {"aggressor_near": 0}}, {"waveform_v": [float("nan"), 0]}):
            request = self.request()
            request["crosstalk_model"].update(change)
            with patch("python.spike_core.si_coupled_channel.extract_coupled_path_rlgc") as extract:
                with self.assertRaises(ValueError):
                    analyze_uniform_design_channel(fixtures.SiUniformChannelTests().coupled_design(), request)
                extract.assert_not_called()

    def test_missing_victim_not_silently_ignored(self):
        request = self.request()
        del request["victim_net"]
        with self.assertRaisesRegex(ValueError, "victim_net"):
            analyze_uniform_design_channel(fixtures.SiUniformChannelTests().design(), request)


if __name__ == "__main__":
    unittest.main()
