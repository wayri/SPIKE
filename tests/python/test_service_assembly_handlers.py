import unittest

from python.spike_core.assembly_resources import GIB
from python.spike_core.service import handle
from python.spike_core.service_assembly_handlers import handle_assembly_request


def _design(layer_count: int = 2, primitive_count: int = 4):
    return {
        "layers": [
            {"id": f"layer-{index}", "name": f"In{index}.Cu", "layer_type": "copper"}
            for index in range(layer_count)
        ],
        "tracks": [{"id": f"track-{index}"} for index in range(primitive_count)],
        "components": [],
    }


def _assembly():
    return {
        "assembly_id": "assembly-1",
        "name": "assembly",
        "boards": [
            {
                "id": "board-1",
                "design_id": "design-1",
                "transform": [
                    1, 0, 0, 0,
                    0, 1, 0, 0,
                    0, 0, 1, 0,
                    0, 0, 0, 1,
                ],
            }
        ],
        "parts": [],
        "harnesses": [],
        "connectors": [],
    }


class AssemblyServiceHandlerTests(unittest.TestCase):
    def test_unhandled_method_returns_none(self):
        self.assertIsNone(handle_assembly_request("health", {}))

    def test_worker_exposes_admission_contract(self):
        response = handle({
            "id": "assembly-admission-1",
            "method": "estimate_assembly_resources",
            "params": {
                "assembly": _assembly(),
                "designs": {"design-1": _design()},
                "workload": "pi_dc",
                "memory_limit_gb": 4,
                "physical_memory_bytes": 8 * GIB,
                "cpu_limit": 2,
            },
        })
        self.assertTrue(response["ok"])
        result = response["result"]
        self.assertEqual(result["contract"], "spike/assembly-resource-admission/v1")
        self.assertEqual(result["state"], "admitted")
        self.assertEqual(result["totals"]["boards"], 1)
        self.assertEqual(result["totals"]["copper_layers"], 2)

    def test_blocked_admission_is_an_inspectable_result(self):
        response = handle({
            "method": "estimate_assembly_resources",
            "params": {
                "assembly": _assembly(),
                "designs": {},
                "workload": "thermal",
                "memory_limit_gb": 2,
                "physical_memory_bytes": 4 * GIB,
            },
        })
        self.assertTrue(response["ok"])
        self.assertFalse(response["result"]["can_admit"])
        self.assertIn(
            "ASSEMBLY_DESIGN_UNRESOLVED",
            {issue["code"] for issue in response["result"]["issues"]},
        )

    def test_malformed_request_uses_canonical_error_envelope(self):
        response = handle({
            "id": "assembly-admission-invalid",
            "method": "estimate_assembly_resources",
            "params": {
                "assembly": _assembly(),
                "designs": {"design-1": _design()},
                "workload": "not-a-workload",
                "memory_limit_gb": 4,
            },
        })
        self.assertFalse(response["ok"])
        self.assertEqual(response["error_code"], "SPIKE-BE-IPC-E-0001")
        self.assertEqual(response["error_detail"]["operation_id"], "assembly-admission-invalid")


if __name__ == "__main__":
    unittest.main()
