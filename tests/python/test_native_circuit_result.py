import unittest

from python.spike_core.native_circuit_result import native_mna_to_analysis_result
from python.spike_core.native_mna import REQUEST_CONTRACT, run_native_mna


class NativeCircuitResultTests(unittest.TestCase):
    def request(self, mode="operating_point"):
        analysis = {"mode": mode}
        if mode == "ac":
            analysis.update({"start_hz": 10.0, "stop_hz": 100.0, "points": 3, "scale": "log"})
        elif mode == "transient":
            analysis.update({"time_step_s": 1e-4, "stop_time_s": 1e-3})
        return {
            "contract": REQUEST_CONTRACT,
            "request_id": f"result-{mode}",
            "ground_node": "0",
            "analysis": analysis,
            "resource_limits": {"memory_limit_gb": 2},
            "elements": [
                {"id": "V1", "type": "voltage_source", "positive_node": "in", "negative_node": "0", "value": 10, "ac_magnitude": 1},
                {"id": "R1", "type": "resistor", "positive_node": "in", "negative_node": "out", "resistance_ohm": 1000},
                {"id": "R2", "type": "resistor", "positive_node": "out", "negative_node": "0", "resistance_ohm": 1000},
            ],
        }

    def test_operating_point_maps_to_common_contract_without_fake_spatial_fields(self):
        request = self.request()
        converted = native_mna_to_analysis_result(run_native_mna(request), request)
        self.assertEqual(converted.status, "completed")
        self.assertEqual(converted.mode, "dc")
        self.assertAlmostEqual(converted.fields["waveforms"]["v(out)"][0], 5.0)
        self.assertNotIn("visualization", converted.fields)
        self.assertEqual(converted.provenance["spatial_visualization"], "not_generated")

    def test_ac_preserves_complex_series_and_plot_magnitudes(self):
        request = self.request("ac")
        converted = native_mna_to_analysis_result(run_native_mna(request), request)
        self.assertEqual(converted.fields["waveforms"]["frequency"], [10.0, 31.622776601683793, 100.0])
        self.assertEqual(len(converted.fields["waveforms"]["v(out)"]), 3)
        self.assertIn("complex_waveforms", converted.fields)

    def test_blocked_native_validation_is_exposed_as_analysis_issues(self):
        request = self.request()
        request["elements"] = []
        converted = native_mna_to_analysis_result(run_native_mna(request), request)
        self.assertEqual(converted.status, "blocked")
        self.assertTrue(any(issue.code == "MNA_ELEMENT_COUNT_INVALID" for issue in converted.issues))


if __name__ == "__main__":
    unittest.main()
