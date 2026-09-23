import unittest

from python.spike_core.assembly_resources import GIB, estimate_assembly_resources
from python.spike_core.assembly_scale import MAX_COMPONENTS_PER_BOARD, MAX_NETS_PER_BOARD
from python.spike_core.design_ir_v2 import AssemblyIRV1


def design(
    layer_count: int,
    primitive_count: int = 10,
    component_count: int = 0,
    net_count: int = 0,
    board_size_mm=None,
):
    result = {
        "design_id": "design",
        "layers": [
            {"id": f"layer-{index}", "name": "F.Cu" if index == 0 else f"In{index}.Cu", "layer_type": "copper"}
            for index in range(layer_count)
        ],
        "tracks": [{"id": f"track-{index}"} for index in range(primitive_count)],
        "vias": [],
        "pads": [],
        "zones": [],
        "components": [{"id": f"component-{index}"} for index in range(component_count)],
        "nets": [{"id": f"net-{index}"} for index in range(net_count)],
    }
    if board_size_mm is not None:
        result["metadata"] = {"board_size_mm": board_size_mm}
    return result


class AssemblyResourceAdmissionTests(unittest.TestCase):
    def test_thirty_32_layer_boards_scale_with_machine_policy(self):
        assembly = AssemblyIRV1.from_dict({
            "assembly_id": "thirty-board",
            "name": "Thirty-board fixture",
            "boards": [
                {"id": f"board-{index}", "design_id": f"design-{index}"}
                for index in range(30)
            ],
        })
        designs = {f"design-{index}": design(32, 20) for index in range(30)}
        result = estimate_assembly_resources(
            assembly,
            designs,
            workload="pi_dc",
            memory_limit_gb=32,
            cpu_limit=8,
            physical_memory_bytes=64 * GIB,
        )

        self.assertTrue(result["can_admit"])
        self.assertEqual(result["totals"]["boards"], 30)
        self.assertEqual(result["totals"]["copper_layers"], 960)
        self.assertEqual(result["effective_memory_limit_bytes"], 32 * GIB)
        self.assertLessEqual(result["effective_cpu_threads"], 8)
        self.assertIn("validity", result["meaning"])

    def test_machine_ceiling_can_block_an_assembly(self):
        assembly = AssemblyIRV1.from_dict({
            "assembly_id": "dense",
            "name": "Dense fixture",
            "boards": [{"id": "board", "design_id": "design"}],
        })
        result = estimate_assembly_resources(
            assembly,
            {"design": design(32, 12_000)},
            workload="pi_ac",
            memory_limit_gb=64,
            physical_memory_bytes=8 * GIB,
        )

        self.assertFalse(result["can_admit"])
        self.assertEqual(result["effective_memory_limit_bytes"], 6 * GIB)
        self.assertIn("ASSEMBLY_MEMORY_BUDGET_EXCEEDED", {item["code"] for item in result["issues"]})

    def test_missing_design_and_more_than_32_layers_fail_closed(self):
        assembly = AssemblyIRV1.from_dict({
            "assembly_id": "invalid",
            "name": "Invalid fixture",
            "boards": [
                {"id": "missing", "design_id": "missing-design"},
                {"id": "too-many-layers", "design_id": "large-design"},
            ],
        })
        result = estimate_assembly_resources(
            assembly,
            {"large-design": design(33)},
            workload="visualization",
            memory_limit_gb=2,
            physical_memory_bytes=16 * GIB,
        )

        self.assertFalse(result["can_admit"])
        codes = {item["code"] for item in result["issues"]}
        self.assertIn("ASSEMBLY_DESIGN_UNRESOLVED", codes)
        self.assertIn("ASSEMBLY_LAYER_LIMIT_EXCEEDED", codes)

    def test_memory_limit_and_workload_are_validated(self):
        assembly = AssemblyIRV1(assembly_id="empty", name="Empty")
        result = estimate_assembly_resources(
            assembly,
            {},
            workload="thermal",
            memory_limit_gb=1,
            physical_memory_bytes=16 * GIB,
        )
        self.assertFalse(result["can_admit"])
        self.assertIn("ASSEMBLY_MEMORY_LIMIT_INVALID", {item["code"] for item in result["issues"]})
        with self.assertRaisesRegex(ValueError, "Unsupported assembly workload"):
            estimate_assembly_resources(assembly, {}, workload="unknown", memory_limit_gb=2)

    def test_high_density_boards_are_counted_per_instance_at_product_scale(self):
        assembly = AssemblyIRV1.from_dict({
            "assembly_id": "high-density", "name": "High-density boards",
            "boards": [{"id": f"board-{index}", "design_id": "dense-design"} for index in range(20)],
        })
        result = estimate_assembly_resources(
            assembly,
            {"dense-design": design(32, 100, component_count=3_000, net_count=25_000, board_size_mm=[1_000, 1_000])},
            workload="pi_dc", memory_limit_gb=32, physical_memory_bytes=64 * GIB,
        )

        self.assertTrue(result["can_admit"])
        self.assertEqual(result["totals"]["components"], 60_000)
        self.assertEqual(result["totals"]["nets"], 500_000)
        self.assertEqual(result["totals"]["declared_board_area_mm2"], 20_000_000.0)
        self.assertEqual(result["boards"][0]["board_size_mm"], [1_000.0, 1_000.0])
        self.assertEqual(result["per_board_limits"]["maximum_nets"], MAX_NETS_PER_BOARD)

    def test_per_board_scale_limits_fail_closed(self):
        assembly = AssemblyIRV1.from_dict({
            "assembly_id": "over-limit", "name": "Over limit",
            "boards": [{"id": "board", "design_id": "design"}],
        })
        oversized = design(32, component_count=0, net_count=0, board_size_mm=[1_001, 1_000])
        oversized["components"] = [{}] * (MAX_COMPONENTS_PER_BOARD + 1)
        oversized["nets"] = [{}] * (MAX_NETS_PER_BOARD + 1)
        result = estimate_assembly_resources(
            assembly, {"design": oversized}, workload="visualization",
            memory_limit_gb=32, physical_memory_bytes=64 * GIB,
        )

        self.assertFalse(result["can_admit"])
        codes = {item["code"] for item in result["issues"]}
        self.assertTrue({
            "ASSEMBLY_COMPONENT_LIMIT_EXCEEDED", "ASSEMBLY_NET_LIMIT_EXCEEDED",
            "ASSEMBLY_BOARD_SIZE_LIMIT_EXCEEDED",
        }.issubset(codes))

    def test_legacy_kicad_board_bbox_is_admitted_as_a_declared_envelope(self):
        assembly = AssemblyIRV1.from_dict({
            "assembly_id": "legacy-bounds", "name": "Legacy bounds",
            "boards": [{"id": "board", "design_id": "design"}],
        })
        retained = design(2)
        retained["metadata"] = {"board_bbox": {"min_x": 10, "min_y": 20, "max_x": 110, "max_y": 70}}
        result = estimate_assembly_resources(
            assembly, {"design": retained}, workload="visualization",
            memory_limit_gb=4, physical_memory_bytes=8 * GIB,
        )
        self.assertTrue(result["can_admit"])
        self.assertEqual(result["boards"][0]["board_size_mm"], [100.0, 50.0])


if __name__ == "__main__":
    unittest.main()
