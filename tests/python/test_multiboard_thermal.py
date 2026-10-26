# SPDX-License-Identifier: Apache-2.0
import copy
import json
import math
from pathlib import Path
import unittest

from python.spike_core.solvers.thermal_fluid.heat.multiboard_thermal import MultiboardThermalError, run_multiboard_thermal
from python.spike_core.spider_v2 import AssemblyIRV1


def request(conductance=1.0):
    return {"contract": "spike/multiboard-thermal-request/v1", "assembly": {
        "contract": "spike/assembly-ir/v1", "assembly_id": "stack", "name": "Stack",
        "boards": [{"id": board, "design_id": "shared-design", "frame": {"frame_id": board}}
                   for board in ("A", "B")],
        "thermal_contacts": [{"id": "stack-contact", "endpoint_a": "A", "endpoint_b": "B", "contact_type": "connector"}]},
        "board_models": [{"board_id": board, "elements": [{"id": "board", "power_w": power,
            "ambient_resistance_c_per_w": 1, "thermal_capacitance_j_per_c": 1}], "links": []}
            for board, power in (("A", 10), ("B", 0))],
        "contact_models": [{"contact_id": "stack-contact", "from": {"board_id": "A", "node": "board"},
            "to": {"board_id": "B", "node": "board"}, "conductance_w_per_k": conductance}],
        "ambient_temperature_c": 25, "mode": "steady_state"}


class MultiboardThermalTests(unittest.TestCase):
    def test_worker_executes_coupled_network(self):
        from python.spike_core.service import handle
        response = handle({"id": "thermal-coupled", "method": "run_multiboard_thermal", "params": {"request": request()}})
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["contract"], "spike/multiboard-thermal-result/v1")
        self.assertAlmostEqual(response["result"]["board_temperatures_c"]["B"]["board"], 25 + 10 / 3)

    def test_schema_accepts_canonical_request(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        root = Path(__file__).resolve().parents[2] / "schemas"
        resources = [json.loads(path.read_text()) for path in root.glob("*.schema.json")]
        registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema))
                                             for schema in resources if "$id" in schema)
        schema = json.loads((root / "multiboard-thermal-request-v1.schema.json").read_text())
        raw = request()
        raw["assembly"] = json.loads(json.dumps(AssemblyIRV1.from_dict(raw["assembly"]).to_dict()))
        Draft202012Validator(schema, registry=registry).validate(raw)

    def test_two_board_reference_and_contact_sensitivity(self):
        # K=[[2,-1],[-1,2]], P=[10,0]. Exact rises [20/3,10/3] K.
        result = run_multiboard_thermal(request())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_status"], "approximate")
        self.assertTrue(result["coupled_physics"])
        self.assertAlmostEqual(result["board_temperatures_c"]["A"]["board"], 25 + 20 / 3)
        self.assertAlmostEqual(result["board_temperatures_c"]["B"]["board"], 25 + 10 / 3)
        self.assertAlmostEqual(result["contact_heat_flows"][0]["steady_heat_flow_w"], 10 / 3)
        self.assertLess(abs(result["summary"]["energy_balance_residual_w"]), 1e-12)
        self.assertLess(result["summary"]["max_node_residual_w"], 1e-12)
        weaker = run_multiboard_thermal(request(.1))
        self.assertGreater(weaker["board_temperatures_c"]["A"]["board"], result["board_temperatures_c"]["A"]["board"])
        self.assertLess(weaker["board_temperatures_c"]["B"]["board"], result["board_temperatures_c"]["B"]["board"])

    def test_transient_matches_independent_eigenmode_oracle_and_converges(self):
        # Mean rise has eigenvalue 1; half difference eigenvalue 3, C=I.
        exact_a = 25 + 5 * (1 - math.exp(-1)) + 5 / 3 * (1 - math.exp(-3))
        errors = []
        for step in (.1, .05, .025):
            raw = request()
            raw.update(mode="transient", duration_s=1, time_step_s=step)
            result = run_multiboard_thermal(raw)
            a, b = result["nodes"]
            self.assertEqual(result["transient"][0]["time_s"], 0)
            self.assertEqual(result["transient"][-1]["time_s"], 1)
            errors.append(abs(a["temperature_c"] - exact_a))
            self.assertAlmostEqual(result["contact_heat_flows"][0]["heat_flow_w"], a["temperature_c"] - b["temperature_c"])
            prior = result["transient"][-2]["temperatures_c"]
            # Backward-Euler storage + heat to ambient balances both-board power.
            stored_w = sum((node["temperature_c"] - prior[node["id"]]) / step for node in result["nodes"])
            ambient_w = sum(node["temperature_c"] - 25 for node in result["nodes"])
            self.assertAlmostEqual(stored_w + ambient_w, 10, places=10)
        self.assertLess(errors[1], errors[0])
        self.assertLess(errors[2], errors[1])
        self.assertLess(errors[2], .04)

    def test_invalid_identity_and_numeric_inputs(self):
        mutations = [lambda r: r["board_models"].pop(),
            lambda r: r["contact_models"].clear(),
            lambda r: r["contact_models"][0].update(contact_id="missing"),
            lambda r: r["contact_models"][0]["from"].update(board_id="B"),
            lambda r: r["contact_models"][0].update(conductance_w_per_k=float("nan")),
            lambda r: r["board_models"][0]["elements"][0].update(power_w=True),
            lambda r: r.update(ambient_temperature_c=-274),
            lambda r: r.update(mode="transient", duration_s=1, time_step_s=0),
            lambda r: r.update(mode="transient", duration_s=1, time_step_s=1e-12),
            lambda r: r["board_models"][0]["elements"].append(copy.deepcopy(r["board_models"][0]["elements"][0]))]
        for mutate in mutations:
            raw = request()
            mutate(raw)
            with self.subTest(mutate=mutate), self.assertRaises(MultiboardThermalError):
                run_multiboard_thermal(raw)

    def test_disconnected_ambient_and_missing_capacitance_block(self):
        raw = request()
        for board in raw["board_models"]:
            del board["elements"][0]["ambient_resistance_c_per_w"]
        result = run_multiboard_thermal(raw)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["coupled_physics"])
        raw = request()
        raw.update(mode="transient", duration_s=1, time_step_s=.1)
        del raw["board_models"][0]["elements"][0]["thermal_capacitance_j_per_c"]
        self.assertEqual(run_multiboard_thermal(raw)["status"], "blocked")

    def test_local_links_and_namespace_collision_safety(self):
        raw = request()
        model = raw["board_models"][0]
        model["elements"].append({"id": "chip", "power_w": 2})
        model["links"] = [{"id": "chip-path", "from_id": "chip", "to_id": "board", "conductance_w_per_k": 2}]
        result = run_multiboard_thermal(raw)
        self.assertAlmostEqual(result["board_temperatures_c"]["A"]["chip"] - result["board_temperatures_c"]["A"]["board"], 1)
        self.assertLess(result["summary"]["max_node_residual_w"], 1e-12)


if __name__ == "__main__":
    unittest.main()
