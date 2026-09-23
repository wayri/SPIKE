import unittest

from python.spike_core.contracts import DesignIR
from python.spike_core.service import handle
from python.spike_core.spice_workspace import (
    SPICE_WORKSPACE_CONTRACT,
    compose_spice_workspace,
    validate_spice_workspace,
)


def fixture_design() -> DesignIR:
    return DesignIR(
        design_id="spice-board",
        name="SPICE assistant fixture",
        components=[
            {"id": "component-v1", "reference": "V1", "value": "source"},
            {"id": "component-r1", "reference": "R1", "value": "10"},
        ],
        pads=[
            {"id": "v1-1", "ref": "V1", "name": "1", "net_name": "VIN"},
            {"id": "v1-2", "ref": "V1", "name": "2", "net_name": "GND"},
            {"id": "r1-1", "ref": "R1", "name": "1", "net_name": "VIN"},
            {"id": "r1-2", "ref": "R1", "name": "2", "net_name": "GND"},
        ],
    )


def fixture_workspace() -> dict:
    return {
        "contract": SPICE_WORKSPACE_CONTRACT,
        "name": "PI transient",
        "domain": "pi",
        "ground_node": "GND",
        "models": [
            {"id": "source_12v", "name": "12 V source", "kind": "primitive", "primitive": "voltage_source", "pins": ["p", "n"], "value": "PULSE(0 12 0 1u 1u 1m 2m)", "origin": "built_in"},
            {"id": "resistor_10", "name": "10 ohm", "kind": "primitive", "primitive": "resistor", "pins": ["1", "2"], "value": "10", "origin": "built_in"},
        ],
        "assignments": [
            {"id": "assign-v1", "component_ref": "V1", "model_id": "source_12v", "enabled": True, "pin_bindings": [
                {"model_pin": "p", "pad_id": "v1-1", "board_net": "VIN", "circuit_node": "VIN"},
                {"model_pin": "n", "pad_id": "v1-2", "board_net": "GND", "circuit_node": "GND"},
            ]},
            {"id": "assign-r1", "component_ref": "R1", "model_id": "resistor_10", "enabled": True, "pin_bindings": [
                {"model_pin": "1", "pad_id": "r1-1", "board_net": "VIN", "circuit_node": "VIN"},
                {"model_pin": "2", "pad_id": "r1-2", "board_net": "GND", "circuit_node": "GND"},
            ]},
        ],
        "parasitics": [],
        "analysis": {"mode": "transient", "time_step_s": 1e-6, "stop_time_s": 2e-3},
    }


class SpiceWorkspaceTests(unittest.TestCase):
    def test_visual_workspace_composes_a_self_contained_netlist(self):
        result = compose_spice_workspace(fixture_workspace(), fixture_design())

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["validation"]["can_run"])
        self.assertEqual(result["node_aliases"]["GND"], "0")
        self.assertIn("VV1", result["netlist"])
        self.assertIn("RR1", result["netlist"])
        self.assertIn(".tran 1e-06 0.002", result["netlist"])
        self.assertIn(".options filetype=ascii", result["netlist"])
        self.assertFalse(result["provenance"]["geometry_parasitics_inferred"])

    def test_inline_models_reject_file_and_analysis_directives(self):
        workspace = fixture_workspace()
        workspace["models"].append({
            "id": "unsafe_model",
            "name": "Unsafe",
            "kind": "subcircuit",
            "subcircuit_name": "unsafe",
            "pins": ["a", "b"],
            "source": ".subckt unsafe a b\n.include vendor.lib\n.tran 1n 1u\n.ends unsafe",
            "origin": "imported",
        })
        validation = validate_spice_workspace(workspace, fixture_design())
        codes = {issue["code"] for issue in validation["issues"]}

        self.assertIn("SPICE_MODEL_DIRECTIVE_REJECTED", codes)
        self.assertFalse(validation["can_run"])

    def test_extracted_parasitics_require_explicit_endpoints_and_provenance_is_visible(self):
        workspace = fixture_workspace()
        workspace["parasitics"] = [{
            "id": "vin-path",
            "net": "VIN",
            "from_node": "VIN_SOURCE",
            "to_node": "VIN_LOAD",
            "reference_node": "GND",
            "resistance_ohm": 0.01,
            "inductance_h": 2e-9,
            "capacitance_f": 10e-12,
            "source_result_id": "peec-run-1",
            "model_status": "approximate",
            "endpoint_reviewed": True,
        }]
        result = compose_spice_workspace(workspace, fixture_design())

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["validation"]["warnings"][0]["code"], "SPICE_PARASITIC_NOT_VALIDATED")
        self.assertIn("source=peec-run-1 status=approximate", result["netlist"])
        self.assertIn("C", result["netlist"])

        workspace["parasitics"][0]["to_node"] = "VIN_SOURCE"
        blocked = validate_spice_workspace(workspace, fixture_design())
        self.assertIn("SPICE_PARASITIC_ENDPOINTS_INVALID", {issue["code"] for issue in blocked["issues"]})

        workspace["parasitics"][0]["to_node"] = "VIN_LOAD"
        workspace["parasitics"][0]["endpoint_reviewed"] = False
        blocked = validate_spice_workspace(workspace, fixture_design())
        self.assertIn("SPICE_PARASITIC_ENDPOINT_REVIEW_REQUIRED", {issue["code"] for issue in blocked["issues"]})

    def test_worker_exposes_validation_and_composition_contracts(self):
        design = fixture_design().to_dict()
        workspace = fixture_workspace()
        validation = handle({"method": "validate_spice_workspace", "params": {"design": design, "workspace": workspace}})
        preview = handle({"method": "compose_spice_workspace", "params": {"design": design, "workspace": workspace}})

        self.assertTrue(validation["ok"])
        self.assertTrue(validation["result"]["can_run"])
        self.assertTrue(preview["ok"])
        self.assertEqual(preview["result"]["status"], "ready")

    def test_workspace_domain_and_model_origin_are_required(self):
        workspace = fixture_workspace()
        del workspace["domain"]
        del workspace["models"][0]["origin"]
        validation = validate_spice_workspace(workspace, fixture_design())
        codes = {issue["code"] for issue in validation["issues"]}

        self.assertIn("SPICE_WORKSPACE_DOMAIN_INVALID", codes)
        self.assertIn("SPICE_MODEL_ORIGIN_INVALID", codes)
        self.assertFalse(validation["can_run"])


if __name__ == "__main__":
    unittest.main()
