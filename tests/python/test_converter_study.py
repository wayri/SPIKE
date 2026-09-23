import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.contracts import AnalysisResult, DesignIR
from python.spike_core.converter_study import (
    CONVERTER_STUDY_RESULT_CONTRACT,
    converter_capabilities,
    materialize_converter_workspace,
    run_converter_study,
    validate_converter_study,
)
from python.spike_core.extensions import ExtensionRegistry
from python.spike_core.extensions import default_extension_roots
from python.spike_core.service import handle


def design():
    return DesignIR(
        design_id="converter-board",
        name="Converter fixture",
        components=[
            {"id": "v1", "reference": "V1"},
            {"id": "r1", "reference": "R1"},
        ],
        pads=[
            {"id": "v1p", "ref": "V1", "name": "1", "net_name": "VIN"},
            {"id": "v1n", "ref": "V1", "name": "2", "net_name": "GND"},
            {"id": "r1p", "ref": "R1", "name": "1", "net_name": "VOUT"},
            {"id": "r1n", "ref": "R1", "name": "2", "net_name": "GND"},
        ],
    )


def workspace():
    return {
        "contract": "spike/spice-workspace/v1",
        "name": "Buck transient",
        "domain": "pi",
        "ground_node": "GND",
        "models": [
            {
                "id": "vin_source",
                "name": "Input source",
                "kind": "primitive",
                "primitive": "voltage_source",
                "pins": ["p", "n"],
                "value": "12",
                "origin": "built_in",
            },
            {
                "id": "load",
                "name": "Load",
                "kind": "primitive",
                "primitive": "resistor",
                "pins": ["p", "n"],
                "value": "5",
                "origin": "built_in",
            },
        ],
        "assignments": [
            {
                "id": "source",
                "component_ref": "V1",
                "model_id": "vin_source",
                "enabled": True,
                "pin_bindings": [
                    {"model_pin": "p", "pad_id": "v1p", "board_net": "VIN", "circuit_node": "VIN"},
                    {"model_pin": "n", "pad_id": "v1n", "board_net": "GND", "circuit_node": "GND"},
                ],
            },
            {
                "id": "load",
                "component_ref": "R1",
                "model_id": "load",
                "enabled": True,
                "pin_bindings": [
                    {"model_pin": "p", "pad_id": "r1p", "board_net": "VOUT", "circuit_node": "VOUT"},
                    {"model_pin": "n", "pad_id": "r1n", "board_net": "GND", "circuit_node": "GND"},
                ],
            },
        ],
        "parasitics": [],
        "analysis": {"mode": "transient", "time_step_s": 1e-6, "stop_time_s": 5e-6},
    }


def study():
    return {
        "contract": "spike/converter-study/v1",
        "study_id": "buck-1",
        "name": "Buck operating case",
        "topology": "buck",
        "switching": {"frequency_hz": 500_000, "duty_cycle": 0.5, "dead_time_s": 20e-9},
        "workspace": workspace(),
        "waveform_bindings": {
            "input_voltage": "v(vin)",
            "input_current": "i(vin)",
            "output_voltage": "v(vout)",
            "output_current": "i(load)",
        },
        "measurement_window": {"start_s": 2e-6, "stop_s": 5e-6, "purpose": "steady_state"},
        "loss_bindings": [{
            "id": "switch",
            "reference": "Q1",
            "power_vector": "p(q1)",
            "thermal": {"theta_ja_c_per_w": 10.0, "thermal_capacitance_j_per_c": 2.0},
        }],
        "thermal_scenario": {
            "contract": "spike/thermal/v1",
            "mode": "steady_state",
            "ambient_temperature_c": 25.0,
        },
    }


def circuit_result():
    return AnalysisResult(
        analysis_id="buck-1-ngspice",
        mode="spice",
        status="completed",
        model_status="solver_dependent",
        fields={"waveforms": {
            "time": [0, 1e-6, 2e-6, 3e-6, 4e-6, 5e-6],
            "v(vin)": [12, 12, 12, 12, 12, 12],
            "i(vin)": [2.5, 2.3, 2.2, 2.2, 2.2, 2.2],
            "v(vout)": [0, 3, 5.8, 6.0, 6.2, 6.0],
            "i(load)": [0, 0.6, 1.16, 1.2, 1.24, 1.2],
            "p(q1)": [0, 1.2, 1.8, 2.0, 2.2, 2.0],
        }, "visualization": {"time_series": {"times_s": [], "frames": []}}},
        networks={"component_stress": [{"reference": "Q1", "status": "within_assigned_limits"}]},
        provenance={"solver": "ngspice"},
    )


class ConverterStudyTests(unittest.TestCase):
    def test_validation_requires_explicit_transient_vectors_and_window(self):
        request = study()
        del request["waveform_bindings"]["output_current"]
        request["workspace"]["analysis"]["mode"] = "ac"
        validation = validate_converter_study(request, design())
        codes = {item["code"] for item in validation["issues"]}
        self.assertIn("CONVERTER_WAVEFORM_BINDING_REQUIRED", codes)
        self.assertIn("CONVERTER_TRANSIENT_REQUIRED", codes)
        self.assertFalse(validation["can_run"])

    def test_structured_pwm_source_is_materialized_as_spice_pulse(self):
        request = study()
        request["switching"]["sources"] = [{
            "model_id": "vin_source",
            "role": "input",
            "low": 0,
            "high": 12,
            "delay_s": 100e-9,
            "rise_s": 20e-9,
            "fall_s": 30e-9,
            "on_time_s": 800e-9,
            "phase_deg": 90,
        }]
        compiled = materialize_converter_workspace(request)
        value = compiled["models"][0]["value"]
        self.assertTrue(value.startswith("PULSE(0 12 "))
        self.assertIn("2e-08 3e-08 8e-07 2e-06", value)
        self.assertEqual(validate_converter_study(request, design())["materialized_pwm_sources"], 1)

    def test_pwm_source_rejects_non_source_model_and_invalid_timing(self):
        request = study()
        request["switching"]["sources"] = [{
            "model_id": "load", "high": 1, "rise_s": -1,
        }]
        validation = validate_converter_study(request, design())
        codes = {item["code"] for item in validation["issues"]}
        self.assertIn("CONVERTER_PWM_SOURCE_MODEL_INVALID", codes)
        self.assertIn("CONVERTER_PWM_TIMING_INVALID", codes)

    def test_time_weighted_metrics_and_engineering_limits_are_reported(self):
        request = study()
        request["limits"] = {
            "minimum_efficiency_percent": 50,
            "maximum_output_ripple_v": 0.1,
            "maximum_input_inrush_a": 2,
        }
        with patch("python.spike_core.converter_study.NgspicePlugin") as plugin:
            plugin.return_value.run.return_value = circuit_result()
            result = run_converter_study(design(), request)
        self.assertEqual(result["summary"]["statistics_method"], "time_weighted_trapezoidal")
        codes = {item["code"] for item in result["issues"]}
        self.assertIn("CONVERTER_EFFICIENCY_LIMIT", codes)
        self.assertIn("CONVERTER_RIPPLE_LIMIT", codes)
        self.assertIn("CONVERTER_INRUSH_LIMIT", codes)

    @patch("python.spike_core.converter_study.NgspicePlugin")
    def test_completed_study_computes_windowed_power_ripple_loss_and_thermal(self, plugin):
        plugin.return_value.run.return_value = circuit_result()
        result = run_converter_study(design(), study())

        self.assertEqual(result["contract"], CONVERTER_STUDY_RESULT_CONTRACT)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"]["measurement_window"]["sample_count"], 4)
        self.assertAlmostEqual(result["summary"]["average_input_power_w"], 26.4)
        self.assertAlmostEqual(result["summary"]["average_output_power_w"], 7.284)
        self.assertAlmostEqual(result["summary"]["output_ripple_peak_to_peak_v"], 0.4)
        self.assertAlmostEqual(result["component_losses"][0]["average_power_w"], 2.033333333333333)
        self.assertAlmostEqual(result["summary"]["bound_component_loss_w"], 2.033333333333333)
        self.assertAlmostEqual(result["summary"]["unallocated_loss_w"], 17.082666666666668)
        self.assertAlmostEqual(result["thermal"]["summary"]["max_steady_temperature_c"], 45.33333333333333)
        self.assertGreaterEqual(result["elapsed_seconds"], 0)
        self.assertEqual(result["model_status"], "approximate")

    @patch("python.spike_core.converter_study.NgspicePlugin")
    def test_missing_bound_result_vector_fails_instead_of_fabricating_metrics(self, plugin):
        incomplete = circuit_result()
        del incomplete.fields["waveforms"]["i(load)"]
        plugin.return_value.run.return_value = incomplete
        result = run_converter_study(design(), study())

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["issues"][-1]["code"], "CONVERTER_ANALYTICS_BINDING_FAILED")

    def test_service_exposes_validation_and_capability_gates(self):
        capabilities = handle({"method": "converter_capabilities", "params": {}})
        validation = handle({
            "method": "validate_converter_study",
            "params": {"design": design().to_dict(), "study": study()},
        })
        self.assertTrue(capabilities["ok"])
        self.assertIn("bode_loop_gain", capabilities["result"]["gated"])
        self.assertTrue(validation["ok"])
        self.assertTrue(validation["result"]["can_run"])

    def test_bundled_converter_extension_is_discoverable_and_invokable(self):
        root = Path(__file__).parents[2]
        registry = ExtensionRegistry()
        diagnostics = registry.discover([root / "extensions"], trusted_roots=[root / "extensions"])
        self.assertTrue(any(
            item["id"] == "spike.converter-analysis" and item["status"] == "loaded"
            for item in diagnostics
        ))
        result = registry.invoke("spike.converter-analysis", "converter-study-assistant", {
            "design": design().to_dict(),
            "selection": {"type": "component", "id": "r1"},
        })
        self.assertEqual(result["contract"], "spike/extension-result/v1")
        self.assertEqual(result["data"]["study_contract"], "spike/converter-study/v1")

    def test_packaged_workspace_extension_root_is_discoverable(self):
        root = Path(__file__).parents[2]
        with patch.dict("os.environ", {"SPIKE_WORKSPACE": str(root)}):
            roots = {path.resolve() for path in default_extension_roots()}
        self.assertIn((root / "extensions").resolve(), roots)


if __name__ == "__main__":
    unittest.main()
