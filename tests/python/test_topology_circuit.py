import unittest

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.service import handle
from python.spike_core.topology_circuit import (
    TOPOLOGY_CIRCUIT_CONTRACT,
    bridge_topology_to_analysis_spec,
    validate_topology_circuit,
)


def design() -> DesignIR:
    return DesignIR(
        design_id="topology-fixture",
        components=[
            {"reference": "R1", "value": "10"},
            {"reference": "C1", "value": "100nF"},
            {"reference": "Q1", "value": "MOSFET"},
        ],
        pads=[
            {"id": "r1-1", "ref": "R1", "net_name": "VIN"},
            {"id": "r1-2", "ref": "R1", "net_name": "VOUT"},
            {"id": "c1-1", "ref": "C1", "net_name": "VOUT"},
            {"id": "c1-2", "ref": "C1", "net_name": "GND"},
            {"id": "q1-1", "ref": "Q1", "net_name": "VOUT"},
            {"id": "q1-2", "ref": "Q1", "net_name": "GND"},
        ],
    )


def topology() -> dict:
    return {
        "contract": "spike/topology/v1",
        "domain": "pi",
        "name": "VIN to VOUT passive path",
        "nodes": [
            {"id": "vin", "kind": "source"},
            {"id": "vin_rail", "kind": "rail"},
            {"id": "r1", "kind": "passive", "ref": "R1", "orientation": "series", "circuit_model": {
                "primitive": "resistor", "value": "10ohm", "pins": [
                    {"pad_id": "r1-1", "circuit_node": "VIN"},
                    {"pad_id": "r1-2", "circuit_node": "VOUT"},
                ],
            }},
            {"id": "vout", "kind": "rail"},
            {"id": "c1", "kind": "passive", "ref": "C1", "orientation": "shunt", "circuit_model": {
                "primitive": "capacitor", "value": "100nF", "pins": [
                    {"pad_id": "c1-1", "circuit_node": "VOUT"},
                    {"pad_id": "c1-2", "circuit_node": "GND"},
                ],
            }},
            {"id": "gnd", "kind": "return"},
            {"id": "load", "kind": "load"},
        ],
        "edges": [
            {"id": "e1", "from": "vin", "to": "vin_rail", "kind": "power"},
            {"id": "e2", "from": "vin_rail", "to": "r1", "kind": "power"},
            {"id": "e3", "from": "r1", "to": "vout", "kind": "power"},
            {"id": "e4", "from": "vout", "to": "load", "kind": "power"},
            {"id": "e5", "from": "vout", "to": "c1", "kind": "power"},
            {"id": "e6", "from": "c1", "to": "gnd", "kind": "return"},
        ],
    }


class TopologyCircuitTests(unittest.TestCase):
    def test_validates_explicit_series_and_shunt_passives(self):
        result = validate_topology_circuit(topology(), design())

        self.assertTrue(result["valid"])
        self.assertTrue(result["can_handoff"])
        self.assertFalse(result["can_execute"])
        self.assertEqual([item["primitive"] for item in result["supported_elements"]], ["resistor", "capacitor"])
        self.assertAlmostEqual(result["supported_elements"][1]["value"]["si"], 100e-9)

    def test_bridge_keeps_execution_gated_and_attaches_to_analysis_spec(self):
        result = bridge_topology_to_analysis_spec(topology(), design(), AnalysisSpec(mode="ac", net_names=["VOUT"]))

        self.assertEqual(result["contract"], TOPOLOGY_CIRCUIT_CONTRACT)
        self.assertEqual(result["status"], "ready")
        handoff = result["analysis_spec"]["options"]["topology_circuit"]
        self.assertFalse(handoff["execution"]["implicit_spice_execution"])
        self.assertEqual(handoff["execution"]["state"], "not_executed")
        self.assertEqual(len(handoff["elements"]), 2)

    def test_behavioral_device_is_not_converted_to_a_passive_element(self):
        candidate = topology()
        candidate["nodes"].append({
            "id": "q1", "kind": "regulator", "ref": "Q1", "simulationModel": "mosfet",
            "circuit_model": {"type": "voltage_dependent_resistance"},
        })
        candidate["edges"].extend([
            {"id": "e7", "from": "vout", "to": "q1", "kind": "power"},
            {"id": "e8", "from": "q1", "to": "gnd", "kind": "return"},
        ])
        result = validate_topology_circuit(candidate, design())

        self.assertTrue(result["valid"])
        self.assertEqual(len(result["supported_elements"]), 2)
        self.assertEqual(result["unsupported_models"][0]["reference"], "Q1")
        self.assertFalse(result["can_execute"])

    def test_series_element_requires_a_complete_power_path(self):
        candidate = topology()
        candidate["edges"] = [edge for edge in candidate["edges"] if edge["id"] != "e3"]
        result = validate_topology_circuit(candidate, design())

        self.assertFalse(result["valid"])
        self.assertIn("TOPOLOGY_SERIES_PATH_INVALID", {issue["code"] for issue in result["issues"]})

    def test_worker_exposes_bounded_handoff(self):
        response = handle({
            "method": "bridge_topology_to_analysis_spec",
            "params": {"design": design().to_dict(), "topology": topology(), "spec": {"mode": "dc", "net_names": ["VOUT"]}},
        })

        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["status"], "ready")
        self.assertFalse(response["result"]["validation"]["can_execute"])


if __name__ == "__main__":
    unittest.main()
