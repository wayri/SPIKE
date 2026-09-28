import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from python.spike_core.multiboard_analysis import (
    MultiboardAnalysisError,
    plan_multiboard_analysis,
)
from python.spike_core.multiboard_execution import (
    COUPLED_BIND_REQUEST_CONTRACT,
    HARNESS_COMPILE_REQUEST_CONTRACT,
    SI_BATCH_REQUEST_CONTRACT,
    MultiboardExecutionError,
    bind_coupled_reduced_network,
    compile_harness_electrical_network,
    run_independent_si_batch,
)
from python.spike_core.service import handle
from tests.python.test_si_channel import SiUniformChannelTests
from tests.python.test_si_protocol_test_runner import fixture_suite


ROOT = Path(__file__).resolve().parents[2]


def design(design_id: str, layers: int = 32, size_mm: float = 1000.0):
    return {
        "contract": "spike/design-ir/v2",
        "design_id": design_id,
        "layers": [
            {"id": f"{design_id}-layer-{index}", "name": "F.Cu" if index == 0 else f"In{index}.Cu", "layer_type": "copper"}
            for index in range(layers)
        ],
        "tracks": [{"id": f"{design_id}-extent", "start_mm": [0, 0], "end_mm": [size_mm, size_mm]}],
        "arcs": [], "vias": [], "pads": [], "zones": [], "regions": [],
        "components": [], "nets": [],
    }


def assembly(count: int = 30, reverse: bool = False):
    boards = [
        {
            "id": f"board-{index:02d}", "name": f"Board {index}", "design_id": f"design-{index:02d}",
            "frame": {"frame_id": f"frame-{index:02d}", "parent_frame_id": "assembly"},
        }
        for index in range(count)
    ]
    if reverse:
        boards.reverse()
    return {
        "contract": "spike/assembly-ir/v1", "assembly_id": "assembly-30", "name": "Thirty boards",
        "frame": {"frame_id": "assembly"}, "boards": boards,
        "harnesses": [{
            "id": "harness-a-b", "name": "A-B", "endpoint_a": "board-00:J1", "endpoint_b": "board-01:J2",
            "length_mm": 250.0, "conductor_material_id": "copper", "pin_map": {"2": "2", "1": "1"},
        }] if count > 1 else [],
        "connector_mappings": [], "rigid_flex_links": [], "parts": [], "materials": [],
        "thermal_contacts": [], "electrical_bonds": [], "extensions": {}, "metadata": {},
    }


def request(*, count: int = 30, mode: str = "independent_board_batch", reverse: bool = False):
    return {
        "contract": "spike/multiboard-analysis-request/v1", "domain": "pi", "mode": mode,
        "assembly": assembly(count, reverse),
        "designs": {f"design-{index:02d}": design(f"design-{index:02d}") for index in range(count)},
    }


def xyz_transform(x: float, y: float, z: float, rx_deg: float, ry_deg: float, rz_deg: float) -> list[float]:
    """Row-major XYZ placement, matching the retained AssemblyIR convention."""
    rx, ry, rz = (math.radians(value) for value in (rx_deg, ry_deg, rz_deg))
    sx, cx = math.sin(rx), math.cos(rx)
    sy, cy = math.sin(ry), math.cos(ry)
    sz, cz = math.sin(rz), math.cos(rz)
    return [
        cy * cz, sx * sy * cz - cx * sz, cx * sy * cz + sx * sz, x,
        cy * sz, sx * sy * sz + cx * cz, cx * sy * sz - sx * cz, y,
        -sy, sx * cy, cx * cy, z,
        0, 0, 0, 1,
    ]


def four_marble_board_request() -> dict:
    """Four retained Marble-scale boards with distinct identities and 3D placements."""
    board_specs = [
        ("marble-power", "marble-power-design", (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
        ("marble-control", "marble-control-design", (14.0, -9.0, 6.0, 10.0, 0.0, 90.0)),
        ("marble-sensor", "marble-sensor-design", (-12.0, 7.5, 18.0, 0.0, -20.0, 35.0)),
        ("marble-interface", "marble-interface-design", (5.0, 16.0, 29.0, 15.0, 25.0, -40.0)),
    ]
    boards = [{
        "id": board_id, "name": board_id.replace("marble-", "Marble ").title(), "design_id": design_id,
        "frame": {
            "frame_id": f"{board_id}-frame", "parent_frame_id": "assembly",
            "transform": xyz_transform(*placement),
        },
    } for board_id, design_id, placement in board_specs]
    return {
        "contract": "spike/multiboard-analysis-request/v1", "domain": "pi", "mode": "independent_board_batch",
        "assembly": {
            "contract": "spike/assembly-ir/v1", "assembly_id": "marble-four", "name": "Four Marble boards",
            "frame": {"frame_id": "assembly"}, "boards": boards,
            "harnesses": [
                {"id": "power-to-control", "name": "Power to control", "endpoint_a": "marble-power::J_PWR", "endpoint_b": "marble-control::J_IN", "length_mm": 45.0, "conductor_material_id": "copper", "pin_map": {"1": "1"}},
                {"id": "control-to-sensor", "name": "Control to sensor", "endpoint_a": "marble-control::J_SENS", "endpoint_b": "marble-sensor::J_IN", "length_mm": 52.0, "conductor_material_id": "copper", "pin_map": {"2": "2"}},
                {"id": "sensor-to-interface", "name": "Sensor to interface", "endpoint_a": "marble-sensor::J_OUT", "endpoint_b": "marble-interface::J_IN", "length_mm": 61.0, "conductor_material_id": "copper", "pin_map": {"3": "3"}},
            ],
            "connector_mappings": [], "rigid_flex_links": [], "parts": [], "materials": [],
            "thermal_contacts": [], "electrical_bonds": [], "extensions": {}, "metadata": {},
        },
        "designs": {design_id: design(design_id, layers=8, size_mm=72.0) for _, design_id, _ in board_specs},
    }


class MultiboardAnalysisTests(unittest.TestCase):
    def test_four_marble_board_fixture_retains_xyz_placement_design_and_harness_identities(self):
        value = four_marble_board_request()
        result = plan_multiboard_analysis(value)

        self.assertTrue(result["can_plan"])
        self.assertEqual(
            ["marble-control", "marble-interface", "marble-power", "marble-sensor"],
            [board["board_id"] for board in result["graph"]["boards"]],
        )
        source_boards = {board["id"]: board for board in value["assembly"]["boards"]}
        for board in result["graph"]["boards"]:
            source = source_boards[board["board_id"]]
            self.assertEqual(board["design_id"], source["design_id"])
            self.assertEqual(board["transform"], source["frame"]["transform"])
        self.assertEqual(
            [("marble-control", "J_SENS", "marble-sensor", "J_IN"),
             ("marble-power", "J_PWR", "marble-control", "J_IN"),
             ("marble-sensor", "J_OUT", "marble-interface", "J_IN")],
            [(item["endpoint_a"]["board_id"], item["endpoint_a"]["connector_id"], item["endpoint_b"]["board_id"], item["endpoint_b"]["connector_id"])
             for item in result["graph"]["harnesses"]],
        )

    def _si_batch_request(self) -> dict:
        fixture = SiUniformChannelTests()
        si_design = fixture.design().to_dict()
        multiboard = request(count=2)
        multiboard["domain"] = "si"
        multiboard["designs"] = {"design-00": si_design, "design-01": si_design}
        suite_request = {
            "contract": "spike/si-protocol-test-suite-request/v1",
            "suite": fixture_suite(),
            "lanes": [{"lane_id": "DQ0", "channel_request": fixture.request()}],
            "requested_tests": ["topology", "s_parameters", "eye", "compliance_review"],
        }
        return {
            "contract": SI_BATCH_REQUEST_CONTRACT,
            "multiboard_request": multiboard,
            "jobs": [
                {"board_id": "board-00", "suite_request": suite_request},
                {"board_id": "board-01", "suite_request": suite_request},
            ],
        }

    def _coupled_bind_request(self, *, domain: str = "pi") -> dict:
        multiboard = request(count=2, mode="coupled_harness_network")
        multiboard["domain"] = domain
        multiboard["assembly"]["harnesses"][0]["pin_map"] = {"1": "1", "2": "2"}
        digest = "a" * 64
        return {
            "contract": COUPLED_BIND_REQUEST_CONTRACT,
            "multiboard_request": multiboard,
            "reference_nodes": [{"reference_id": "return-common", "circuit_node": "0", "role": "return"}],
            "board_port_networks": [
                {"board_id": "board-00", "network_id": "board-a-reduced", "network_kind": "native_linear_fragment", "model_sha256": digest, "ports": [
                    {"port_id": "a-p1", "connector_id": "J1", "pin": "1", "signal_node": "a:signal:1", "return_node": "a:return", "return_reference_id": "return-common"},
                    {"port_id": "a-p2", "connector_id": "J1", "pin": "2", "signal_node": "a:signal:2", "return_node": "a:return", "return_reference_id": "return-common"},
                ]},
                {"board_id": "board-01", "network_id": "board-b-reduced", "network_kind": "nport_s_parameters", "model_sha256": "b" * 64, "ports": [
                    {"port_id": "b-p1", "connector_id": "J2", "pin": "1", "signal_node": "b:signal:1", "return_node": "b:return", "return_reference_id": "return-common"},
                    {"port_id": "b-p2", "connector_id": "J2", "pin": "2", "signal_node": "b:signal:2", "return_node": "b:return", "return_reference_id": "return-common"},
                ]},
            ],
            "conductor_models": [{"harness_id": "harness-a-b", "conductors": [
                {"source_pin": "1", "target_pin": "1", "resistance_ohm": 0.05, "inductance_h": 1e-7},
                {"source_pin": "2", "target_pin": "2", "resistance_ohm": 0.05, "inductance_h": 1e-7},
            ]}],
            "connector_bindings": [
                {"binding_id": "a-1", "board_id": "board-00", "connector_id": "J1", "pin": "1", "port_id": "a-p1", "harness_id": "harness-a-b", "harness_side": "a", "harness_pin": "1", "resistance_ohm": 0.01, "inductance_h": 1e-9},
                {"binding_id": "a-2", "board_id": "board-00", "connector_id": "J1", "pin": "2", "port_id": "a-p2", "harness_id": "harness-a-b", "harness_side": "a", "harness_pin": "2", "resistance_ohm": 0.01, "inductance_h": 1e-9},
                {"binding_id": "b-1", "board_id": "board-01", "connector_id": "J2", "pin": "1", "port_id": "b-p1", "harness_id": "harness-a-b", "harness_side": "b", "harness_pin": "1", "resistance_ohm": 0.01, "inductance_h": 1e-9},
                {"binding_id": "b-2", "board_id": "board-01", "connector_id": "J2", "pin": "2", "port_id": "b-p2", "harness_id": "harness-a-b", "harness_side": "b", "harness_pin": "2", "resistance_ohm": 0.01, "inductance_h": 1e-9},
            ],
            "return_paths": [{"harness_id": "harness-a-b", "source_port_id": "a-p2", "target_port_id": "b-p2", "resistance_ohm": 0.04, "inductance_h": 1.5e-7}],
            "mutual_terms": [{"term_id": "pair-12", "conductor_a_id": "harness:harness-a-b:1", "conductor_b_id": "harness:harness-a-b:2", "mutual_inductance_h": 2e-8}],
        }

    def test_thirty_32_layer_one_metre_boards_form_admitted_independent_plan(self):
        result = plan_multiboard_analysis(request())
        self.assertTrue(result["can_plan"])
        self.assertTrue(result["independent_jobs_admissible"])
        self.assertFalse(result["can_execute_coupled"])
        self.assertEqual(result["state"], "admitted")
        self.assertEqual(len(result["graph"]["boards"]), 30)
        self.assertTrue(all(board["copper_layers"] == 32 for board in result["graph"]["boards"]))
        self.assertEqual(result["graph"]["boards"][0]["dimensions_mm"], [1000.0, 1000.0])
        self.assertEqual(result["graph"]["harnesses"][0]["pin_map"], {"1": "1", "2": "2"})
        self.assertFalse(result["coupled_physics"])

    def test_graph_digest_is_independent_of_retained_board_order(self):
        forward = plan_multiboard_analysis(request())
        reverse = plan_multiboard_analysis(request(reverse=True))
        self.assertEqual(forward["graph_digest"], reverse["graph_digest"])

    def test_coupled_pi_and_si_remain_fail_closed_on_the_valid_graph(self):
        for domain in ("pi", "si"):
            value = request(count=2, mode="coupled_harness_network")
            value["domain"] = domain
            result = plan_multiboard_analysis(value)
            self.assertFalse(result["can_plan"])
            self.assertFalse(result["can_execute_coupled"])
            self.assertEqual(result["graph"]["domain"], domain)
            self.assertIn("MULTIBOARD_COUPLED_SOLVER_NOT_QUALIFIED", {issue["code"] for issue in result["issues"]})

    def test_thermal_and_emi_plans_keep_domain_specific_assembly_scope(self):
        for domain, retained_key in (("thermal", "thermal_contacts"), ("emi", "electrical_bonds")):
            with self.subTest(domain=domain):
                value = request(count=2)
                value["domain"] = domain
                value["assembly"]["thermal_contacts"] = [{"id": "contact-a-b", "endpoint_a": "board-00", "endpoint_b": "board-01", "contact_type": "board-stack"}]
                value["assembly"]["electrical_bonds"] = [{"id": "bond-a-b", "endpoint_a": "board-00::J1", "endpoint_b": "board-01::J2", "bond_type": "ground-bond"}]
                independent = plan_multiboard_analysis(value)
                self.assertTrue(independent["independent_jobs_admissible"])
                self.assertIn(retained_key, independent["graph"])
                self.assertEqual(len(independent["graph"][retained_key]), 1)
                self.assertIn("parts", independent["graph"])
                schema = json.loads((ROOT / "schemas" / "multiboard-analysis-plan-v1.schema.json").read_text(encoding="utf-8"))
                Draft202012Validator(schema).validate(independent)
                value["mode"] = "coupled_assembly"
                coupled = plan_multiboard_analysis(value)
                self.assertFalse(coupled["can_plan"])
                self.assertIn("MULTIBOARD_COUPLED_SOLVER_NOT_QUALIFIED", {issue["code"] for issue in coupled["issues"]})
                Draft202012Validator(schema).validate(coupled)

    def test_stack_mates_and_harnesses_remain_distinct_edges(self):
        value = request(count=3)
        value["assembly"]["connector_mappings"] = [{
            "id": "stack-mate", "kind": "connector-mate", "name": "Stack header",
            "data": {"endpoint_a": "board-00::J_STACK", "endpoint_b": "board-02::J_STACK",
                     "pin_map": {"1": "2", "2": "1"}},
        }]
        plan = plan_multiboard_analysis(value)
        self.assertTrue(plan["can_plan"])
        self.assertEqual(len(plan["graph"]["harnesses"]), 1)
        self.assertEqual(plan["graph"]["mated_connectors"][0]["pin_map"], {"1": "2", "2": "1"})
        self.assertEqual(plan["graph"]["mated_connectors"][0]["endpoint_a"]["board_id"], "board-00")
        value["selected_board_ids"] = ["board-00", "board-01"]
        subset = plan_multiboard_analysis(value)
        self.assertEqual(subset["graph"]["mated_connectors"], [])
        self.assertEqual(subset["omitted_mate_ids"], ["stack-mate"])

    def test_stack_mate_rejects_harness_pin_reuse_and_duplicate_mate_pins(self):
        value = request(count=3)
        mate = {"id": "stack-mate", "kind": "connector-mate", "name": "Stack header",
                "data": {"endpoint_a": "board-00::J1", "endpoint_b": "board-02::J_STACK",
                         "pin_map": {"1": "1"}}}
        value["assembly"]["connector_mappings"] = [mate]
        with self.assertRaisesRegex(ValueError, "already assigned"):
            plan_multiboard_analysis(value)
        mate["data"]["endpoint_a"] = "board-00::J_STACK"
        mate["data"]["pin_map"] = {"1": "1", "2": "1"}
        with self.assertRaisesRegex(ValueError, "duplicate pin"):
            plan_multiboard_analysis(value)

    def test_coupled_modes_are_specific_to_their_physics(self):
        value = request(count=2, mode="coupled_harness_network")
        value["domain"] = "thermal"
        with self.assertRaisesRegex(MultiboardAnalysisError, "only to PI and SI"):
            plan_multiboard_analysis(value)
        value["domain"] = "pi"
        value["mode"] = "coupled_assembly"
        with self.assertRaisesRegex(MultiboardAnalysisError, "only to thermal and EMI"):
            plan_multiboard_analysis(value)

    def test_layer_and_dimension_limits_block_without_truncating_geometry(self):
        value = request(count=2)
        value["designs"]["design-00"] = design("design-00", layers=33)
        value["designs"]["design-01"] = design("design-01", size_mm=1000.001)
        result = plan_multiboard_analysis(value)
        self.assertFalse(result["can_plan"])
        self.assertEqual(
            {"MULTIBOARD_LAYER_LIMIT", "MULTIBOARD_DIMENSION_LIMIT"},
            {issue["code"] for issue in result["issues"] if issue["severity"] == "error"},
        )
        self.assertEqual(result["graph"]["boards"][1]["dimensions_mm"], [1000.001, 1000.001])

    def test_harness_endpoint_must_resolve_to_a_distinct_board(self):
        value = request(count=2)
        value["assembly"]["harnesses"][0]["endpoint_b"] = "missing:J2"
        with self.assertRaisesRegex(MultiboardAnalysisError, "unknown board"):
            plan_multiboard_analysis(value)
        value["assembly"]["harnesses"][0]["endpoint_b"] = "board-00:J2"
        with self.assertRaisesRegex(MultiboardAnalysisError, "distinct"):
            plan_multiboard_analysis(value)

    def test_worker_and_public_schema_expose_the_plan(self):
        response = handle({"id": "multiboard-plan", "method": "plan_multiboard_analysis", "params": {"request": request(count=2)}})
        self.assertTrue(response["ok"])
        result = response["result"]
        schema = json.loads((ROOT / "schemas" / "multiboard-analysis-plan-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(result)
        catalog = json.loads((ROOT / "schemas" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["schemas"][result["contract"]], "multiboard-analysis-plan-v1.schema.json")

    def test_independent_si_batch_executes_each_retained_board_sequentially(self):
        result = run_independent_si_batch(self._si_batch_request())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["execution_strategy"], "sequential_independent_board_jobs")
        self.assertFalse(result["coupling"]["included"])
        self.assertEqual([job["board_id"] for job in result["jobs"]], ["board-00", "board-01"])
        self.assertFalse(result["production_qualified"])
        response = handle({"id": "multiboard-si", "method": "run_multiboard_si_independent_batch", "params": {"request": self._si_batch_request()}})
        self.assertTrue(response["ok"])
        schema = json.loads((ROOT / "schemas" / "multiboard-si-independent-batch-result-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(response["result"])

    def test_independent_si_batch_admits_thirty_jobs_and_rejects_thirty_one(self):
        value = self._si_batch_request()
        value["multiboard_request"] = request(count=30)
        value["multiboard_request"]["domain"] = "si"
        si_design = SiUniformChannelTests().design().to_dict()
        value["multiboard_request"]["designs"] = {f"design-{index:02d}": si_design for index in range(30)}
        suite = value["jobs"][0]["suite_request"]
        value["jobs"] = [{"board_id": f"board-{index:02d}", "suite_request": suite} for index in range(30)]
        stub_result = {"resource_admission": {"actual_lanes": 1, "actual_frequency_points": 1, "estimated_numeric_bytes": 1}}
        with patch("python.spike_core.multiboard_execution.run_si_protocol_test_suite", return_value=stub_result) as runner:
            result = run_independent_si_batch(value)
        self.assertEqual(len(result["jobs"]), 30)
        self.assertEqual(runner.call_count, 30)
        value["jobs"].append({"board_id": "board-00", "suite_request": suite})
        with self.assertRaisesRegex(MultiboardExecutionError, "1 through 30"):
            run_independent_si_batch(value)

    def test_harness_compilation_requires_explicit_per_conductor_electrical_values(self):
        raw = request(count=2, mode="coupled_harness_network")
        raw["assembly"]["harnesses"][0]["pin_map"] = {"1": "1", "2": "2"}
        compiled = compile_harness_electrical_network({
            "contract": HARNESS_COMPILE_REQUEST_CONTRACT,
            "multiboard_request": raw,
            "conductor_models": [{"harness_id": "harness-a-b", "conductors": [
                {"source_pin": "1", "target_pin": "1", "resistance_ohm": 0.08, "inductance_h": 1.2e-7, "capacitance_to_reference_f": 2e-11, "reference_node": "return:common"},
                {"source_pin": "2", "target_pin": "2", "resistance_ohm": 0.08, "inductance_h": 1.2e-7},
            ]}],
        })
        self.assertEqual(compiled["status"], "compiled")
        self.assertTrue(compiled["coupling"]["cross_board_harness_elements_compiled"])
        self.assertFalse(compiled["coupling"]["field_coupling_executed"])
        self.assertFalse(compiled["production_qualified"])
        self.assertEqual(len(compiled["circuit_fragment"]["elements"]), 5)
        with self.assertRaisesRegex(MultiboardExecutionError, "exactly one explicit conductor"):
            compile_harness_electrical_network({
                "contract": HARNESS_COMPILE_REQUEST_CONTRACT,
                "multiboard_request": raw,
                "conductor_models": [{"harness_id": "harness-a-b", "conductors": [
                    {"source_pin": "1", "target_pin": "1", "resistance_ohm": 0.08, "inductance_h": 1.2e-7},
                ]}],
            })

    def test_coupled_reduced_network_binds_explicit_ports_connector_return_and_mutual_terms(self):
        request_value = self._coupled_bind_request()
        result = bind_coupled_reduced_network(request_value)
        self.assertEqual(result["status"], "bound")
        self.assertTrue(result["coupling"]["board_port_models_bound"])
        self.assertTrue(result["coupling"]["connector_models_bound"])
        self.assertTrue(result["coupling"]["return_paths_bound"])
        self.assertTrue(result["coupling"]["mutual_terms_provided"])
        self.assertFalse(result["coupling"]["mutual_terms_executed"])
        self.assertFalse(result["coupling"]["solver_executed"])
        self.assertFalse(result["production_qualified"])
        self.assertEqual(len(result["connector_bindings"]), 4)
        response = handle({"id": "coupled-bind", "method": "bind_multiboard_coupled_reduced_network", "params": {"request": request_value}})
        self.assertTrue(response["ok"])
        schema = json.loads((ROOT / "schemas" / "multiboard-coupled-reduced-network-bind-result-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(response["result"])

    def test_coupled_reduced_network_fails_closed_when_return_or_connector_binding_is_missing(self):
        missing_return = self._coupled_bind_request()
        missing_return["return_paths"] = []
        with self.assertRaisesRegex(MultiboardExecutionError, "return_paths"):
            bind_coupled_reduced_network(missing_return)
        missing_connector = self._coupled_bind_request()
        missing_connector["connector_bindings"].pop()
        with self.assertRaisesRegex(MultiboardExecutionError, "cover every"):
            bind_coupled_reduced_network(missing_connector)


if __name__ == "__main__":
    unittest.main()
