import unittest

from python.spike_core.contracts import DesignIR
from python.spike_core.native_circuit_compiler import (
    compile_spice_workspace_to_native_mna,
    run_spice_workspace_native_mna,
)
from python.spike_core.service import handle
from python.spike_core.spice_workspace import SPICE_WORKSPACE_CONTRACT


def design():
    return DesignIR(
        design_id="native-workspace",
        components=[
            {"id": "v1", "reference": "V1"},
            {"id": "r1", "reference": "R1"},
        ],
        pads=[
            {"id": "v1p", "ref": "V1", "name": "1", "net_name": "VIN"},
            {"id": "v1n", "ref": "V1", "name": "2", "net_name": "GND"},
            {"id": "r1p", "ref": "R1", "name": "1", "net_name": "VIN"},
            {"id": "r1n", "ref": "R1", "name": "2", "net_name": "GND"},
        ],
    )


def workspace(mode="operating_point"):
    analysis = {"mode": mode}
    if mode == "ac":
        analysis.update({"start_hz": 1e3, "stop_hz": 1e6, "points_per_decade": 10})
    elif mode == "transient":
        analysis.update({"time_step_s": 1e-5, "stop_time_s": 1e-3})
    return {
        "contract": SPICE_WORKSPACE_CONTRACT,
        "name": "Native PI circuit",
        "domain": "pi",
        "ground_node": "GND",
        "models": [
            {
                "id": "source", "kind": "primitive", "primitive": "voltage_source",
                "pins": ["p", "n"], "value": "5", "origin": "built_in",
                "parameters": {"dc_value": 5.0, "ac_magnitude": 1.0},
            },
            {
                "id": "load", "kind": "primitive", "primitive": "resistor",
                "pins": ["p", "n"], "value": "1000", "origin": "built_in",
                "parameters": {"resistance_ohm": 1000.0},
            },
        ],
        "assignments": [
            {
                "id": "source-binding", "component_ref": "V1", "model_id": "source", "enabled": True,
                "pin_bindings": [
                    {"model_pin": "p", "pad_id": "v1p", "circuit_node": "VIN"},
                    {"model_pin": "n", "pad_id": "v1n", "circuit_node": "GND"},
                ],
            },
            {
                "id": "load-binding", "component_ref": "R1", "model_id": "load", "enabled": True,
                "pin_bindings": [
                    {"model_pin": "p", "pad_id": "r1p", "circuit_node": "VIN"},
                    {"model_pin": "n", "pad_id": "r1n", "circuit_node": "GND"},
                ],
            },
        ],
        "parasitics": [],
        "analysis": analysis,
    }


class NativeCircuitCompilerTests(unittest.TestCase):
    def test_compiles_and_runs_reviewed_workspace(self):
        compiled = compile_spice_workspace_to_native_mna(workspace(), design())
        self.assertEqual(compiled["status"], "ready")
        self.assertTrue(compiled["native_validation"]["valid"])
        self.assertFalse(compiled["request"]["provenance"]["topology_inference"])

        solved = run_spice_workspace_native_mna(workspace(), design())
        self.assertEqual(solved["result"]["status"], "completed")
        self.assertEqual(solved["analysis_result"]["contract"], "spike/v1")
        self.assertEqual(solved["analysis_result"]["mode"], "dc")
        self.assertNotIn("visualization", solved["analysis_result"]["fields"])
        self.assertAlmostEqual(solved["result"]["data"]["node_voltage_v"]["VIN"], 5.0)
        self.assertAlmostEqual(solved["result"]["data"]["element_power_w"]["A_load-binding"], 0.025)

    def test_compiles_workspace_ac_grid(self):
        compiled = compile_spice_workspace_to_native_mna(workspace("ac"), design())
        self.assertEqual(compiled["request"]["analysis"]["points"], 31)
        solved = run_spice_workspace_native_mna(workspace("ac"), design())
        self.assertEqual(solved["result"]["diagnostics"]["points"], 31)

    def test_structured_transient_waveform_is_preserved(self):
        candidate = workspace("transient")
        candidate["models"][0]["parameters"] = {
            "waveform": {"type": "step", "initial": 0.0, "final": 5.0, "delay_s": 1e-4, "rise_time_s": 1e-5}
        }
        candidate["models"][0]["value"] = "structured"
        compiled = compile_spice_workspace_to_native_mna(candidate, design())
        self.assertEqual(compiled["status"], "ready")
        self.assertEqual(compiled["request"]["elements"][0]["waveform"]["type"], "step")

    def test_blocks_nonlinear_and_raw_source_expression(self):
        nonlinear = workspace()
        nonlinear["models"][1].update({"primitive": "diode", "value": "D_DEFAULT"})
        compiled = compile_spice_workspace_to_native_mna(nonlinear, design())
        self.assertEqual(compiled["status"], "blocked")
        self.assertIn("NATIVE_CIRCUIT_MODEL_UNSUPPORTED", {item["code"] for item in compiled["issues"]})

        raw = workspace("transient")
        raw["models"][0]["value"] = "PULSE(0 5 0 1n 1n 1u 2u)"
        raw["models"][0].pop("parameters")
        compiled = compile_spice_workspace_to_native_mna(raw, design())
        self.assertEqual(compiled["status"], "blocked")
        self.assertIn("NATIVE_CIRCUIT_PARAMETER_INVALID", {item["code"] for item in compiled["issues"]})

    def test_accepts_deterministic_spice_suffixes_and_dc_prefix(self):
        candidate = workspace("transient")
        candidate["models"][0].pop("parameters")
        candidate["models"][0]["value"] = "DC 5"
        candidate["models"][1].pop("parameters")
        candidate["models"][1]["value"] = "1k"
        compiled = compile_spice_workspace_to_native_mna(candidate, design())
        self.assertEqual(compiled["status"], "ready")
        self.assertEqual(compiled["request"]["elements"][0]["dc_value"], 5.0)
        self.assertEqual(compiled["request"]["elements"][1]["resistance_ohm"], 1000.0)

    def test_compiles_reviewed_peec_rlcg_without_artificial_short(self):
        candidate = workspace("ac")
        candidate["assignments"][1]["pin_bindings"][0]["circuit_node"] = "LOAD"
        candidate["parasitics"] = [{
            "id": "path", "enabled": True, "endpoint_reviewed": True,
            "from_node": "VIN", "to_node": "LOAD", "reference_node": "GND",
            "resistance_ohm": 0.02, "inductance_h": 2e-9,
            "capacitance_f": 10e-12, "conductance_s": 1e-8,
            "model_status": "approximate",
        }]
        compiled = compile_spice_workspace_to_native_mna(candidate, design())
        self.assertEqual(compiled["status"], "ready")
        types = [item["type"] for item in compiled["request"]["elements"]]
        self.assertEqual(types.count("inductor"), 1)
        self.assertEqual(types.count("capacitor"), 1)
        self.assertEqual(types.count("resistor"), 3)

        candidate["parasitics"][0]["resistance_ohm"] = 0.0
        candidate["parasitics"][0]["inductance_h"] = 0.0
        compiled = compile_spice_workspace_to_native_mna(candidate, design())
        self.assertIn("NATIVE_CIRCUIT_PARASITIC_SERIES_PATH_REQUIRED", {item["code"] for item in compiled["issues"]})

    def test_worker_exposes_native_workspace_compile_and_run(self):
        params = {"design": design().to_dict(), "workspace": workspace()}
        compiled = handle({"method": "compile_spice_workspace_native_mna", "params": params})
        solved = handle({"method": "run_spice_workspace_native_mna", "params": params})
        self.assertTrue(compiled["ok"])
        self.assertEqual(compiled["result"]["status"], "ready")
        self.assertTrue(solved["ok"])
        self.assertEqual(solved["result"]["result"]["status"], "completed")

    def test_current_controlled_source_requires_enabled_voltage_source_assignment(self):
        candidate = workspace()
        candidate["models"].append({
            "id": "dependent", "kind": "primitive", "primitive": "cccs",
            "pins": ["p", "n"], "value": "2", "origin": "built_in",
            "parameters": {"control_source_assignment_id": "missing"},
        })
        candidate["assignments"].append({
            "id": "dependent-binding", "component_ref": "R1", "model_id": "dependent", "enabled": True,
            "pin_bindings": [
                {"model_pin": "p", "pad_id": "r1p", "circuit_node": "VIN"},
                {"model_pin": "n", "pad_id": "r1n", "circuit_node": "GND"},
            ],
        })
        compiled = compile_spice_workspace_to_native_mna(candidate, design())
        self.assertEqual(compiled["status"], "blocked")
        self.assertIn("SPICE_CONTROL_SOURCE_UNKNOWN", {item["code"] for item in compiled["issues"]})


if __name__ == "__main__":
    unittest.main()
