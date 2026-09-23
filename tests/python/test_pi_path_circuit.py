import unittest

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.pi_path import PI_PATH_CONTRACT
from python.spike_core.pi_path_circuit import (
    COMPILE_CONTRACT,
    compile_pi_path_to_native_mna,
    run_pi_path_native_mna,
)
from python.spike_core.service import handle


def three_net_design() -> DesignIR:
    return DesignIR(
        design_id="three-net-path",
        name="VIN through R1 and R2 to VOUT",
        layers=[{"name": "F.Cu"}],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        nets=[
            {"id": 1, "name": "VIN"},
            {"id": 2, "name": "VMID"},
            {"id": 3, "name": "VOUT"},
            {"id": 4, "name": "GND"},
        ],
        tracks=[
            {"id": "vin-track", "start": [0, 0], "end": [3, 0], "width": 1, "layer": "F.Cu", "net_name": "VIN"},
            {"id": "mid-track", "start": [4, 0], "end": [7, 0], "width": 1, "layer": "F.Cu", "net_name": "VMID"},
            {"id": "out-track", "start": [8, 0], "end": [11, 0], "width": 1, "layer": "F.Cu", "net_name": "VOUT"},
        ],
        pads=[
            {"id": "source-pad", "ref": "J1", "name": "1", "at": [0, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VIN"},
            {"id": "r1-in", "ref": "R1", "name": "1", "at": [3, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VIN"},
            {"id": "r1-out", "ref": "R1", "name": "2", "at": [4, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VMID"},
            {"id": "r2-in", "ref": "R2", "name": "1", "at": [7, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VMID"},
            {"id": "r2-out", "ref": "R2", "name": "2", "at": [8, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VOUT"},
            {"id": "load-pad", "ref": "J2", "name": "1", "at": [11, 0], "size": [1, 1], "layers": ["F.Cu"], "layer": "F.Cu", "net_name": "VOUT"},
        ],
        components=[
            {"id": "r1", "reference": "R1", "ref": "R1", "value": "100m"},
            {"id": "r2", "reference": "R2", "ref": "R2", "value": "200m"},
        ],
    )


def path() -> dict:
    return {
        "contract": PI_PATH_CONTRACT,
        "id": "three-net-reviewed-path",
        "source_terminal": {"net": "VIN", "pad_id": "source-pad"},
        "load_terminal": {"net": "VOUT", "pad_id": "load-pad"},
        "segments": [
            {"id": "vin", "net": "VIN"},
            {"id": "mid", "net": "VMID"},
            {"id": "out", "net": "VOUT"},
        ],
        "transitions": [
            {
                "id": "r1", "component_ref": "R1", "from_segment_id": "vin",
                "to_segment_id": "mid", "input_pad_id": "r1-in", "output_pad_id": "r1-out",
                "model": {"primitive": "resistor", "connection_resistance_ohm": 0.1, "model_ref": "reviewed:R1"},
            },
            {
                "id": "r2", "component_ref": "R2", "from_segment_id": "mid",
                "to_segment_id": "out", "input_pad_id": "r2-in", "output_pad_id": "r2-out",
                "model": {"primitive": "resistor", "connection_resistance_ohm": 0.2, "model_ref": "reviewed:R2"},
            },
        ],
    }


def extraction() -> dict:
    def network(net: str, resistance: float, inductance: float, capacitance: float) -> dict:
        return {
            "contract": "spike/rlgc-network/v1",
            "net": net,
            "resistance_ohm": resistance,
            "inductance_h": inductance,
            "capacitance_f": capacitance,
            "conductance_s": 1e-9,
        }

    return {
        "analysis_id": "reviewed-peec-extraction",
        "model_status": "experimental",
        "networks": {"parasitics": [
            network("VIN", 0.01, 10e-9, 5e-12),
            network("VMID", 0.02, 15e-9, 7e-12),
            network("VOUT", 0.03, 20e-9, 9e-12),
        ]},
    }


def mappings() -> list[dict]:
    return [
        {"segment_id": "vin", "network_index": 0, "from_pad_id": "source-pad", "to_pad_id": "r1-in", "endpoint_reviewed": True},
        {"segment_id": "mid", "network_index": 1, "from_pad_id": "r1-out", "to_pad_id": "r2-in", "endpoint_reviewed": True},
        {"segment_id": "out", "network_index": 2, "from_pad_id": "r2-out", "to_pad_id": "load-pad", "endpoint_reviewed": True},
    ]


def ac_spec() -> AnalysisSpec:
    return AnalysisSpec(
        analysis_id="path-ac",
        mode="ac",
        net_names=["VIN", "VMID", "VOUT"],
        sources=[{"id": "source", "net": "VIN", "voltage_v": 1.0, "ac_magnitude_v": 1.0}],
        loads=[{"id": "load", "net": "VOUT", "current_a": 0.001, "ac_magnitude_a": 0.001}],
        return_path={"net": "GND", "circuit_node": "0"},
        frequency_start_hz=1e3,
        frequency_stop_hz=1e6,
        frequency_points=5,
        mesh={"solver_memory_limit_gb": 2},
        options={"pi_path": path()},
    )


class PiPathCircuitTests(unittest.TestCase):
    def test_compiles_every_segment_and_transition_without_ideal_short(self):
        compiled = compile_pi_path_to_native_mna(
            three_net_design(), ac_spec(), extraction(), mappings(),
        )
        self.assertEqual(compiled["contract"], COMPILE_CONTRACT)
        self.assertEqual(compiled["status"], "ready", compiled["issues"])
        self.assertEqual(len(compiled["segment_bindings"]), 3)
        elements = compiled["request"]["elements"]
        transition_resistors = [item for item in elements if item["id"].startswith("X_")]
        self.assertEqual([item["resistance_ohm"] for item in transition_resistors], [0.1, 0.2])
        self.assertTrue(all(binding["source_from_pad_id"] for binding in compiled["segment_bindings"]))
        self.assertFalse(compiled["request"]["provenance"]["topology_inference"])

    def test_runs_reviewed_ac_path_through_native_mna(self):
        result = run_pi_path_native_mna(
            three_net_design(), ac_spec(), extraction(), mappings(),
        )
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["analysis_result"]["mode"], "ac")
        self.assertEqual(result["analysis_result"]["provenance"]["pi_path_id"], "three-net-reviewed-path")
        self.assertEqual(len(result["analysis_result"]["provenance"]["segment_bindings"]), 3)
        self.assertEqual(len(result["analysis_result"]["networks"]["parasitics"]), 3)
        self.assertEqual(
            result["analysis_result"]["provenance"]["spatial_binding"],
            "reviewed_segment_endpoints",
        )
        self.assertFalse(result["analysis_result"]["provenance"]["spatial_fields_available"])

    def test_runs_step_and_pulse_path_transient(self):
        spec = ac_spec()
        spec.analysis_id = "path-transient"
        spec.mode = "transient"
        spec.transient = {"time_step_s": 1e-7, "stop_time_s": 5e-6}
        spec.sources[0]["profile"] = {
            "kind": "step", "initial_value": 0.0, "delay_s": 2e-7, "rise_time_s": 1e-7,
        }
        spec.loads[0]["profile"] = {
            "kind": "pulse", "initial_value": 0.0, "delay_s": 5e-7,
            "rise_time_s": 1e-7, "fall_time_s": 1e-7,
            "pulse_width_s": 1e-6, "period_s": 2e-6,
        }
        result = run_pi_path_native_mna(
            three_net_design(), spec, extraction(), mappings(),
        )
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["compile"]["request"]["analysis"]["mode"], "transient")
        self.assertGreater(len(result["result"]["data"]["time_s"]), 2)

    def test_rejects_unreviewed_or_wrong_endpoint_mapping(self):
        bad = mappings()
        bad[1]["endpoint_reviewed"] = False
        bad[2]["to_pad_id"] = "r2-in"
        result = compile_pi_path_to_native_mna(
            three_net_design(), ac_spec(), extraction(), bad,
        )
        self.assertEqual(result["status"], "blocked")
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("PI_PATH_CIRCUIT_ENDPOINT_REVIEW_REQUIRED", codes)
        self.assertIn("PI_PATH_CIRCUIT_ENDPOINT_PAD_MISMATCH", codes)

    def test_rejects_nonlinear_transition_in_native_linear_path(self):
        spec = ac_spec()
        spec.options["pi_path"]["transitions"][0]["model"] = {
            "primitive": "mosfet", "model_ref": "library:Q1",
        }
        result = compile_pi_path_to_native_mna(
            three_net_design(), spec, extraction(), mappings(),
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn(
            "PI_PATH_CIRCUIT_MODEL_UNSUPPORTED_NATIVE",
            {issue["code"] for issue in result["issues"]},
        )

    def test_worker_exposes_compile_and_run_boundaries(self):
        params = {
            "design": three_net_design().to_dict(),
            "spec": ac_spec().to_dict(),
            "extraction_result": extraction(),
            "segment_mappings": mappings(),
        }
        compiled = handle({"method": "compile_pi_path_native_mna", "params": params})
        self.assertTrue(compiled["ok"])
        self.assertEqual(compiled["result"]["status"], "ready", compiled)
        solved = handle({"method": "run_pi_path_native_mna", "params": params})
        self.assertTrue(solved["ok"])
        self.assertEqual(solved["result"]["status"], "completed", solved)


if __name__ == "__main__":
    unittest.main()
