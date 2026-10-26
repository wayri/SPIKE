# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
import numpy as np
from python.spike_core.solvers.electromagnetics.fields.multiboard_em import run_multiboard_em
from tests.python.test_harness_authoring import fixture


def request():
    return {"contract": "spike/multiboard-em-request/v1", "assembly": fixture()["assembly"],
            "loops": [{"loop_id": b, "board_id": b, "resistance_ohm": 2., "self_inductance_h": 1e-6,
                       "voltage_real_v": 1. if b == "a" else 0., "voltage_imag_v": 0.} for b in ("a", "b")],
            "mutual_inductances": [{"loop_a": "a", "loop_b": "b", "mutual_inductance_h": .5e-6}],
            "frequency_hz": [1e6], "connector_models": []}


class CoupledEMTests(unittest.TestCase):
    def test_part_loop_induced_current_power_and_schema(self):
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator
        raw = request()
        raw["assembly"]["boards"] = raw["assembly"]["boards"][:1]
        raw["assembly"]["harnesses"] = []
        raw["assembly"]["connector_mappings"] = []
        raw["assembly"]["parts"] = [{"id": "case", "part_type": "enclosure", "model_id": "case-step"},
                                    {"id": "group", "part_type": "subassembly"}]
        row = raw["loops"][1]
        del row["board_id"]
        row["part_id"] = "case"
        schema = json.loads((Path(__file__).resolve().parents[2] / "schemas/multiboard-em-request-v1.schema.json").read_text())
        Draft202012Validator(schema).validate(raw)
        result = run_multiboard_em(raw)
        self.assertEqual(result["excluded_hierarchy_part_ids"], ["group"])
        self.assertTrue(result["coupling_included"])
        sample = result["samples"][0]
        current = sample["loops"][1]
        self.assertEqual(current["part_id"], "case")
        self.assertNotIn("board_id", current)
        z, mutual = 2 + 2j*np.pi, 1j*np.pi
        expected = -mutual / (z*z-mutual*mutual)
        self.assertAlmostEqual(abs(complex(current["current_real_a"], current["current_imag_a"]) - expected), 0, places=13)
        self.assertLess(abs(sample["power_balance_residual_w"]), 1e-14)
        raw["mutual_inductances"][0]["mutual_inductance_h"] = 0
        self.assertEqual(run_multiboard_em(raw)["samples"][0]["loops"][1]["current_magnitude_a"], 0)
        for change in (lambda r: r["loops"][1].update(board_id="a"),
                       lambda r: r["loops"][1].update(part_id="missing"),
                       lambda r: r["loops"].pop(),
                       lambda r: r["loops"][1].update(part_id="group"),
                       lambda r: r["mutual_inductances"][0].update(mutual_inductance_h=2e-6),
                       lambda r: r["mutual_inductances"][0].update(loop_b=[]),
                       lambda r: r.update(connector_models=[{"loop_id": "b", "board_id": "a", "connector_id": "J1", "pin": "1", "resistance_ohm": 0, "inductance_h": 0}])):
            invalid = copy.deepcopy(raw); change(invalid)
            with self.assertRaises(ValueError): run_multiboard_em(invalid)

    def test_unmodelled_part_and_electrical_topologies_refused(self):
        raw = request()
        raw["assembly"]["parts"] = [{"id": "case", "part_type": "enclosure", "model_id": "case-step"}]
        with self.assertRaisesRegex(ValueError, "Each retained board and part"):
            run_multiboard_em(raw)
        for field, row in (("rigid_flex_links", {"id": "flex", "kind": "rigid-flex", "data": {}}),
                           ("electrical_bonds", {"id": "bond", "endpoint_a": "a", "endpoint_b": "b"})):
            raw = request(); raw["assembly"][field] = [row]
            with self.assertRaisesRegex(ValueError, "unsupported"):
                run_multiboard_em(raw)

    def test_worker_and_schema(self):
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator
        from python.spike_core.service import handle
        raw = request()
        schema = json.loads((Path(__file__).resolve().parents[2] / "schemas/multiboard-em-request-v1.schema.json").read_text())
        Draft202012Validator(schema).validate(raw)
        response = handle({"method": "run_multiboard_em", "params": {"request": raw}})
        self.assertTrue(response["ok"], response)
        self.assertTrue(response["result"]["coupling_included"])

    def test_closed_form_induced_current_and_power(self):
        raw = request()
        sample = run_multiboard_em(raw)["samples"][0]
        z, mutual = 2 + 2j*np.pi, 1j*np.pi
        expected = -mutual / (z*z-mutual*mutual)
        induced = sample["loops"][1]
        self.assertAlmostEqual(induced["current_real_a"], expected.real, places=13)
        self.assertAlmostEqual(induced["current_imag_a"], expected.imag, places=13)
        self.assertLess(abs(sample["power_balance_residual_w"]), 1e-14)
        raw["mutual_inductances"][0]["mutual_inductance_h"] = 0
        independent = run_multiboard_em(raw)
        self.assertFalse(independent["coupling_included"])
        self.assertEqual(independent["samples"][0]["loops"][1]["current_real_a"], 0.)

    def test_reciprocity_and_connector_property_sensitivity(self):
        raw = request()
        forward = run_multiboard_em(raw)["samples"][0]["loops"][1]
        raw["loops"][0]["voltage_real_v"], raw["loops"][1]["voltage_real_v"] = 0, 1
        reverse = run_multiboard_em(raw)["samples"][0]["loops"][0]
        self.assertAlmostEqual(forward["current_real_a"], reverse["current_real_a"], places=13)
        self.assertAlmostEqual(forward["current_imag_a"], reverse["current_imag_a"], places=13)
        raw = request()
        raw["connector_models"] = [{"loop_id": "a", "board_id": "a", "connector_id": "J1", "pin": "1",
                                    "resistance_ohm": 10., "inductance_h": 0.}]
        contacted = run_multiboard_em(raw)["samples"][0]["loops"][1]
        self.assertLess(abs(complex(contacted["current_real_a"], contacted["current_imag_a"])),
                        abs(complex(forward["current_real_a"], forward["current_imag_a"])))

    def test_nonpassive_duplicate_and_nonfinite_refused(self):
        for change in (lambda r: r["mutual_inductances"][0].update(mutual_inductance_h=2e-6),
                       lambda r: r["frequency_hz"].append(1e6),
                       lambda r: r["loops"][0].update(resistance_ohm=True),
                       lambda r: r["loops"][0].update(self_inductance_h=float("nan")),
                       lambda r: r["loops"].pop()):
            raw = copy.deepcopy(request()); change(raw)
            with self.assertRaises(ValueError): run_multiboard_em(raw)

    def test_whole_energy_matrix_checked_beyond_pair_bounds(self):
        raw = request()
        raw["assembly"]["boards"].append({"id": "c", "design_id": "d", "frame": {"frame_id": "cf"}})
        raw["loops"].append({**raw["loops"][1], "board_id": "c", "loop_id": "c"})
        # Every individual |M| < sqrt(Li Lj), but the full energy matrix is
        # indefinite; pairwise bounds alone would wrongly admit this model.
        raw["mutual_inductances"] = [{"loop_a": a, "loop_b": b, "mutual_inductance_h": -.9e-6}
                                      for a, b in (("a", "b"), ("a", "c"), ("b", "c"))]
        with self.assertRaisesRegex(ValueError, "non-passive"):
            run_multiboard_em(raw)


if __name__ == "__main__": unittest.main()
