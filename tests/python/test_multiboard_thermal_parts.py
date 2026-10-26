# SPDX-License-Identifier: Apache-2.0
"""Assembly structure ownership and independently derived RC heat balances."""
import copy
import json
import math
from pathlib import Path
import unittest

from python.spike_core.solvers.thermal_fluid.heat.multiboard_thermal import MultiboardThermalError, run_multiboard_thermal
from python.spike_core.spider_v2 import AssemblyIRV1
from tests.python.test_multiboard_thermal import request as board_request
from tests.python.test_multiboard_radiation import request as radiation_request, scalar_closed_pair_heat


def case_request(raw=None):
    raw = copy.deepcopy(raw or board_request())
    raw["assembly"]["boards"].pop()
    raw["assembly"]["parts"] = [{"id": "case", "part_type": "enclosure", "model_id": "case-step",
                                 "frame": {"frame_id": "case-frame"}}]
    raw["assembly"]["thermal_contacts"][0]["endpoint_b"] = "case"
    model = raw["board_models"].pop()
    model.pop("board_id")
    raw["part_models"] = [dict(model, part_id="case")]
    raw["contact_models"][0]["to"] = {"part_id": "case", "node": "board"}
    for surface in raw.get("radiation_surfaces", []):
        if surface.get("board_id") == "B":
            surface.pop("board_id")
            surface["part_id"] = "case"
    return raw


class AssemblyPartThermalTests(unittest.TestCase):
    def test_board_case_analytical_conduction_identity_and_provenance(self):
        result = run_multiboard_thermal(case_request())
        # Identical two-node K to board fixture: [[2,-1],[-1,2]] W/K.
        self.assertAlmostEqual(result["board_temperatures_c"]["A"]["board"], 25 + 20 / 3)
        self.assertAlmostEqual(result["part_temperatures_c"]["case"]["board"], 25 + 10 / 3)
        self.assertEqual(result["nodes"][0]["id"], '["A","board"]')
        self.assertEqual(result["nodes"][1]["id"], '["part","case","board"]')
        self.assertEqual(result["nodes"][1]["part_id"], "case")
        self.assertNotIn("board_id", result["nodes"][1])
        self.assertEqual(result["provenance"]["part_ids"], ["case"])
        self.assertEqual(result["contact_heat_flows"][0]["to"], {"part_id": "case", "node": "board"})
        self.assertEqual(result["model_status"], "approximate")
        self.assertFalse(result["production_qualified"])
        self.assertLess(abs(result["summary"]["energy_balance_residual_w"]), 1e-12)

    def test_multiple_boards_case_and_nested_hierarchy(self):
        raw = case_request()
        raw["assembly"]["boards"].append(board_request()["assembly"]["boards"][1])
        raw["board_models"].append(board_request()["board_models"][1])
        raw["assembly"]["thermal_contacts"].append({"id": "b-case", "endpoint_a": "B", "endpoint_b": "case", "contact_type": "mechanical"})
        raw["contact_models"].append({"contact_id": "b-case", "from": {"board_id": "B", "node": "board"},
                                      "to": {"part_id": "case", "node": "board"}, "conductance_w_per_k": 1})
        raw["assembly"]["parts"].append({"id": "group", "part_type": "subassembly", "frame": {"frame_id": "group-frame"}})
        raw["assembly"]["parts"][0]["frame"]["parent_frame_id"] = "group-frame"
        result = run_multiboard_thermal(raw)
        # Star network: 2a-c=10, 2b-c=0, 3c-a-b=0 -> c=2.5 K.
        self.assertAlmostEqual(result["board_temperatures_c"]["A"]["board"], 31.25)
        self.assertAlmostEqual(result["board_temperatures_c"]["B"]["board"], 26.25)
        self.assertAlmostEqual(result["part_temperatures_c"]["case"]["board"], 27.5)
        self.assertEqual(result["provenance"]["excluded_hierarchy_part_ids"], ["group"])
        self.assertLess(result["summary"]["max_node_residual_w"], 1e-12)
        self.assertLess(abs(result["summary"]["energy_balance_residual_w"]), 1e-12)

    def test_part_transient_refinement_and_storage_conservation(self):
        exact = 25 + 5 * (1 - math.exp(-1)) - 5 / 3 * (1 - math.exp(-3))
        errors = []
        for dt in (.1, .05, .025):
            raw = case_request()
            raw.update(mode="transient", duration_s=1, time_step_s=dt)
            result = run_multiboard_thermal(raw)
            errors.append(abs(result["part_temperatures_c"]["case"]["board"] - exact))
            prior = result["transient"][-2]["temperatures_c"]
            stored = sum((node["temperature_c"] - prior[node["id"]]) / dt for node in result["nodes"])
            ambient = sum(node["temperature_c"] - 25 for node in result["nodes"])
            self.assertAlmostEqual(stored + ambient, 10, places=10)
        self.assertLess(errors[2], errors[1])
        self.assertLess(errors[1], errors[0])
        self.assertLess(errors[2], .04)

    def test_required_part_models_and_scoped_endpoints_fail_closed(self):
        mutations = [lambda r: r.pop("part_models"), lambda r: r.update(part_models=None),
            lambda r: r["part_models"].append(copy.deepcopy(r["part_models"][0])),
            lambda r: r["part_models"][0].update(part_id="missing"),
            lambda r: r["part_models"][0].update(board_id="A"),
            lambda r: r["part_models"][0].update(elements=[]),
            lambda r: r["part_models"][0]["elements"][0].update(thermal_capacitance_j_per_c=-1),
            lambda r: r["contact_models"][0]["to"].update(part_id="missing"),
            lambda r: r["contact_models"][0]["to"].update(board_id="A"),
            lambda r: r["contact_models"][0].update(to={"board_id": "case", "node": "board"}),
            lambda r: r["contact_models"][0]["to"].update(node="missing")]
        for mutation in mutations:
            raw = case_request()
            mutation(raw)
            with self.subTest(mutation=mutation), self.assertRaises(MultiboardThermalError):
                run_multiboard_thermal(raw)

    def test_part_missing_transient_capacity_stays_blocked(self):
        raw = case_request(radiation_request())
        raw.update(mode="transient", duration_s=1, time_step_s=.1)
        raw["part_models"][0]["elements"][0].pop("thermal_capacitance_j_per_c")
        result = run_multiboard_thermal(raw)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["part_temperatures_c"], {})
        self.assertFalse(result["coupled_physics"])

    def test_part_to_part_contact_and_local_paths(self):
        raw = case_request()
        raw["assembly"]["parts"].append({"id": "lid", "part_type": "heatsink", "model_id": "lid-step",
                                         "frame": {"frame_id": "lid-frame"}})
        raw["part_models"].append({"part_id": "lid", "elements": [{"id": "skin", "power_w": 2}], "links": []})
        raw["assembly"]["thermal_contacts"].append({"id": "lid-case", "endpoint_a": "lid", "endpoint_b": "case", "contact_type": "mechanical"})
        raw["contact_models"].append({"contact_id": "lid-case", "from": {"part_id": "lid", "node": "skin"},
                                      "to": {"part_id": "case", "node": "board"}, "conductance_w_per_k": 2})
        raw["part_models"][0]["elements"].append({"id": "mount", "power_w": 3})
        raw["part_models"][0]["links"] = [{"from_id": "mount", "to_id": "board", "conductance_w_per_k": 3}]
        result = run_multiboard_thermal(raw)
        case = result["part_temperatures_c"]["case"]
        self.assertAlmostEqual(case["mount"] - case["board"], 1)
        self.assertAlmostEqual(result["part_temperatures_c"]["lid"]["skin"] - case["board"], 1)
        self.assertAlmostEqual(result["summary"]["ambient_heat_flow_w"], 15)

    def test_part_radiative_transient_storage_conservation(self):
        raw = case_request(radiation_request())
        raw.update(mode="transient", duration_s=1, time_step_s=.05)
        result = run_multiboard_thermal(raw)
        prior = result["transient"][-2]["temperatures_c"]
        stored = sum(2 * (node["temperature_c"] - prior[node["id"]]) / .05 for node in result["nodes"])
        ambient = sum(.1 * (node["temperature_c"] - 25) for node in result["nodes"])
        self.assertAlmostEqual(stored + ambient, 10, places=8)
        self.assertLess(result["summary"]["max_transient_energy_balance_error_w"], 1e-8)

    def test_part_radiation_oracle_and_membership(self):
        result = run_multiboard_thermal(case_request(radiation_request(.6)))
        a = result["board_temperatures_c"]["A"]["board"]
        b = result["part_temperatures_c"]["case"]["board"]
        self.assertAlmostEqual(result["radiation_exchange"][0]["heat_flow_w"], scalar_closed_pair_heat(a, b, .6, .6), places=10)
        self.assertEqual(result["radiation_surfaces"][1]["part_id"], "case")
        self.assertLess(abs(result["summary"]["energy_balance_residual_w"]), 1e-8)
        for update in ({"part_id": "missing"}, {"board_id": "A"}, {"node": "missing"}):
            raw = case_request(radiation_request())
            raw["radiation_surfaces"][1].update(update)
            with self.subTest(update=update), self.assertRaises(MultiboardThermalError):
                run_multiboard_thermal(raw)

    def test_radiation_only_explicit_ambient_path_and_closed_floating_block(self):
        raw = case_request(radiation_request(.8, .8))
        raw["assembly"]["thermal_contacts"] = []
        raw["contact_models"] = []
        for model in raw["board_models"] + raw["part_models"]:
            model["elements"][0].pop("ambient_resistance_c_per_w")
        result = run_multiboard_thermal(raw)
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["summary"]["radiation_ambient_heat_flow_w"], 10, places=8)
        for surface in raw["radiation_surfaces"]:
            other = "face-b" if surface["id"] == "face-a" else "face-a"
            surface["view_factors"] = {other: 1}
        self.assertEqual(run_multiboard_thermal(raw)["status"], "blocked")
        raw["radiation_surfaces"][1]["part_id"] = "missing"
        with self.assertRaises(MultiboardThermalError):
            run_multiboard_thermal(raw)

    def test_schema_compatibility_and_exclusive_endpoint_scope(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        root = Path(__file__).resolve().parents[2] / "schemas"
        schemas = [json.loads(path.read_text()) for path in root.glob("*.schema.json")]
        registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas if "$id" in schema)
        schema = json.loads((root / "multiboard-thermal-request-v1.schema.json").read_text())
        validator = Draft202012Validator(schema, registry=registry)
        for raw in (board_request(), case_request(), case_request(radiation_request())):
            raw["assembly"] = json.loads(json.dumps(AssemblyIRV1.from_dict(raw["assembly"]).to_dict()))
            validator.validate(raw)
        raw["contact_models"][0]["to"]["board_id"] = "A"
        self.assertTrue(list(validator.iter_errors(raw)))
        raw["contact_models"][0]["to"].pop("board_id")
        raw["radiation_surfaces"][1]["board_id"] = "A"
        self.assertTrue(list(validator.iter_errors(raw)))


if __name__ == "__main__":
    unittest.main()
