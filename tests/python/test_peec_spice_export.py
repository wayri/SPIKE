import unittest
from unittest.mock import patch

from python.spike_core.contracts import AnalysisResult, DesignIR
from python.spike_core.peec_spice_export import (
    import_peec_rlcg,
    list_peec_spice_networks,
    run_staged_hybrid_cosimulation,
)
from python.spike_core.ngspice_plugin import _find_ngspice
from python.spike_core.spice_workspace import SPICE_WORKSPACE_CONTRACT


def extraction_result():
    return {
        "analysis_id": "peec-ac-1",
        "model_status": "approximate",
        "provenance": {"solver": "spike-peec-native/v0.4"},
        "networks": {"parasitics": [{
            "contract": "spike/rlgc-network/v1",
            "model_status": "approximate",
            "net": "VDD",
            "load": "U1.1",
            "source_node": 10,
            "sink_node": 42,
            "resistance_ohm": 0.012,
            "inductance_h": 3.4e-9,
            "capacitance_f": 18e-12,
            "conductance_s": 2e-8,
            "impedance": [{"frequency_hz": 1e6, "magnitude_ohm": 0.025}],
        }]},
    }


def workspace():
    return {
        "contract": SPICE_WORKSPACE_CONTRACT,
        "name": "Hybrid PI",
        "domain": "pi",
        "ground_node": "GND",
        "models": [{
            "id": "source",
            "name": "Source",
            "kind": "primitive",
            "primitive": "voltage_source",
            "pins": ["p", "n"],
            "value": "12",
            "origin": "built_in",
        }],
        "assignments": [{
            "id": "source-binding",
            "component_ref": "V1",
            "model_id": "source",
            "enabled": True,
            "pin_bindings": [
                {"model_pin": "p", "pad_id": "v1p", "board_net": "VDD", "circuit_node": "VDD_SRC"},
                {"model_pin": "n", "pad_id": "v1n", "board_net": "GND", "circuit_node": "GND"},
            ],
        }],
        "parasitics": [],
        "analysis": {"mode": "transient", "time_step_s": 1e-8, "stop_time_s": 1e-5},
    }


def design():
    return DesignIR(
        design_id="hybrid-board",
        components=[{"id": "v1", "reference": "V1"}],
        pads=[
            {"id": "v1p", "ref": "V1", "name": "1", "net_name": "VDD"},
            {"id": "v1n", "ref": "V1", "name": "2", "net_name": "GND"},
        ],
    )


class PeecSpiceExportTests(unittest.TestCase):
    def test_catalog_exposes_mesh_endpoints_without_inferring_circuit_nodes(self):
        catalog = list_peec_spice_networks(extraction_result())
        self.assertEqual(catalog["status"], "mapping_required")
        self.assertEqual(catalog["networks"][0]["source_mesh_node"], 10)
        self.assertEqual(catalog["limits"]["endpoint_inference"], "forbidden")

    def test_import_requires_reviewed_distinct_endpoints(self):
        mapping = {"network_index": 0, "from_node": "VDD_SRC", "to_node": "VDD_LOAD", "reference_node": "GND"}
        with self.assertRaisesRegex(ValueError, "endpoint_reviewed"):
            import_peec_rlcg(extraction_result(), workspace(), [mapping])
        mapping["endpoint_reviewed"] = True
        mapping["to_node"] = "VDD_SRC"
        with self.assertRaisesRegex(ValueError, "distinct"):
            import_peec_rlcg(extraction_result(), workspace(), [mapping])

    def test_import_preserves_status_and_does_not_claim_frequency_fit(self):
        imported = import_peec_rlcg(extraction_result(), workspace(), [{
            "network_index": 0,
            "from_node": "VDD_SRC",
            "to_node": "VDD_LOAD",
            "reference_node": "GND",
            "endpoint_reviewed": True,
        }])
        parasitic = imported["workspace"]["parasitics"][0]
        self.assertEqual(parasitic["model_status"], "approximate")
        self.assertEqual(parasitic["source_mesh_nodes"], [10, 42])
        self.assertFalse(imported["validity"]["preserves_frequency_sweep"])
        self.assertEqual(workspace()["parasitics"], [])

    @patch("python.spike_core.peec_spice_export.NgspicePlugin")
    def test_hybrid_runner_composes_geometry_parasitics_for_ngspice(self, plugin_type):
        plugin_type.return_value.run.return_value = AnalysisResult(
            analysis_id="hybrid",
            mode="spice",
            status="completed",
            model_status="solver_dependent",
        )
        result = run_staged_hybrid_cosimulation(design(), extraction_result(), workspace(), [{
            "network_index": 0,
            "from_node": "VDD_SRC",
            "to_node": "VDD_LOAD",
            "reference_node": "GND",
            "endpoint_reviewed": True,
        }])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_status"], "approximate")
        self.assertIn("RPpeec_1", result["netlist_preview"]["netlist"])
        self.assertIn("LPpeec_1", result["netlist_preview"]["netlist"])
        self.assertTrue(result["result"]["provenance"]["geometry_parasitics_included"])
        self.assertIn("HYBRID_COSIMULATION_NON_ITERATIVE", {issue["code"] for issue in result["result"]["issues"]})

    @unittest.skipUnless(_find_ngspice(), "ngspice executable is not installed")
    def test_hybrid_runner_executes_real_geometry_derived_rlcg_netlist(self):
        circuit = workspace()
        circuit["models"].append({
            "id": "load",
            "name": "Load",
            "kind": "primitive",
            "primitive": "resistor",
            "pins": ["1", "2"],
            "value": "10",
            "origin": "built_in",
        })
        circuit["assignments"].append({
            "id": "load-binding",
            "component_ref": "RLOAD",
            "model_id": "load",
            "enabled": True,
            "pin_bindings": [
                {"model_pin": "1", "pad_id": "loadp", "board_net": "VDD", "circuit_node": "VDD_LOAD"},
                {"model_pin": "2", "pad_id": "loadn", "board_net": "GND", "circuit_node": "GND"},
            ],
        })
        board = design()
        board.components.append({"id": "rload", "reference": "RLOAD"})
        board.pads.extend([
            {"id": "loadp", "ref": "RLOAD", "name": "1", "net_name": "VDD"},
            {"id": "loadn", "ref": "RLOAD", "name": "2", "net_name": "GND"},
        ])
        result = run_staged_hybrid_cosimulation(board, extraction_result(), circuit, [{
            "network_index": 0,
            "from_node": "VDD_SRC",
            "to_node": "VDD_LOAD",
            "reference_node": "GND",
            "endpoint_reviewed": True,
        }])
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["result"]["provenance"]["geometry_parasitics_included"])
        self.assertEqual(result["result"]["provenance"]["coupling"], "one_way_staged")


if __name__ == "__main__":
    unittest.main()
