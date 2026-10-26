# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from python.spike_core.em_resistor_cht_study import prepare_em_resistor_cht_study
from python.spike_core.contracts import SpiDeR
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.service import handle
from python.spike_core.service_em_cosimulation import handle_em_cosimulation_request
from python.spike_core.solvers.execution.coupling.em_network_resistor_cht import run_em_network_resistor_cht
from python.spike_core.spider_v2 import SpiDeRV2
from tests.python.test_em_network_resistor_cht import request


class EmResistorChtStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request, _ = request()
        cls.result = run_em_network_resistor_cht(cls.request)

    def prepared(self):
        return prepare_em_resistor_cht_study({"request": self.request, "result": self.result})

    def test_round_trip_preserves_exact_request_current_result_and_identity(self):
        first = self.prepared()
        reopened = prepare_em_resistor_cht_study({"request": deepcopy(self.request), "study": first})
        self.assertEqual(reopened, first)
        case = reopened["cases"][0]
        self.assertEqual(case["settings"]["request"], self.request)
        self.assertEqual(case["resultSnapshot"], self.result)
        self.assertEqual(case["mode"], "steady")
        self.assertFalse(case["resultSnapshot"]["production_qualified"])

    def test_four_physical_edits_invalidate_current_and_retain_history(self):
        mutations = [
            lambda r: r["ac_request"]["boundaries"][0]["p0"]["voltage_v"].__setitem__(0, 21.),
            lambda r: r["cht_request"]["energy"]["materials"]["solid"].__setitem__("conductivity_w_mk", 2.1),
            lambda r: next(iter(r["cht_request"]["energy"]["boundaries"].values()))["temperature_k"].__setitem__(0, 301.),
            lambda r: r["cht_request"]["mesh"]["vertices"][0].__setitem__(0, -.01),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                study = self.prepared()
                changed = deepcopy(self.request)
                mutate(changed)
                updated = prepare_em_resistor_cht_study({"request": changed, "study": study})
                case = updated["cases"][0]
                self.assertNotIn("resultSnapshot", case)
                self.assertEqual(case["runs"][-1]["resultSnapshot"], self.result)
                self.assertEqual(study["cases"][0]["settings"]["request"], self.request)

    def test_presentation_edits_preserve_current(self):
        study = self.prepared()
        study.update(name="Renamed", notes="Presentation", tags=["reviewed"])
        study["cases"][0].update(name="Case label", notes="Case note")
        updated = prepare_em_resistor_cht_study({"request": self.request, "study": study})
        self.assertEqual((updated["name"], updated["notes"], updated["tags"]),
                         ("Renamed", "Presentation", ["reviewed"]))
        self.assertEqual(updated["cases"][0]["resultSnapshot"], self.result)

    def test_forged_supplied_result_and_corrupt_unchanged_current_are_rejected(self):
        forged = deepcopy(self.result)
        forged["input_digest_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "digest"):
            prepare_em_resistor_cht_study({"request": self.request, "result": forged})
        study = self.prepared()
        study["cases"][0]["resultSnapshot"] = forged
        with self.assertRaisesRegex(ValueError, "stored current result"):
            prepare_em_resistor_cht_study({"request": self.request, "study": study})
        changed = deepcopy(self.request)
        changed["ac_request"]["boundaries"][0]["p0"]["voltage_v"][0] = 21.
        reopened = prepare_em_resistor_cht_study({"request": changed, "study": study})
        self.assertNotIn("resultSnapshot", reopened["cases"][0])
        self.assertEqual(reopened["cases"][0]["runs"][-1]["resultSnapshot"], forged)
        self.assertEqual(reopened["cases"][0]["runs"][-1]["facts"]["status"],
                         forged["cht"]["status"])

    def test_partial_result_with_valid_hashes_and_stale_ref_are_not_current(self):
        partial = {
            "contract": self.result["contract"], "model_status": "experimental",
            "production_qualified": False,
            "input_digest_sha256": self.result["input_digest_sha256"],
            "mesh_digest_sha256": self.result["mesh_digest_sha256"],
        }
        with self.assertRaisesRegex(ValueError, "does not match"):
            prepare_em_resistor_cht_study({"request": self.request, "result": partial})
        study = prepare_em_resistor_cht_study({"request": self.request})
        study["cases"][0]["resultRef"] = "old-result.json"
        changed = deepcopy(self.request)
        changed["ac_request"]["boundaries"][0]["p0"]["voltage_v"][0] = 22.
        updated = prepare_em_resistor_cht_study({"request": changed, "study": study})
        self.assertNotIn("resultRef", updated["cases"][0])

    def test_explicit_identical_capture_adds_event_but_reopen_does_not(self):
        first = self.prepared()
        first_runs = len(first["cases"][0]["runs"])
        reopened = prepare_em_resistor_cht_study({"request": self.request, "study": first})
        self.assertEqual(len(reopened["cases"][0]["runs"]), first_runs)
        captured = prepare_em_resistor_cht_study(
            {"request": self.request, "result": self.result, "study": reopened})
        self.assertEqual(len(captured["cases"][0]["runs"]), first_runs + 1)
        self.assertNotEqual(captured["cases"][0]["runs"][-1]["id"],
                            captured["cases"][0]["runs"][-2]["id"])

    def test_missing_invalid_and_ambiguous_targets_fail_without_solving(self):
        invalid = deepcopy(self.request)
        invalid["resistor_cell_weights"] = {}
        with patch("python.spike_core.solvers.execution.coupling.em_network_resistor_cht.solve_em_network_ac") as solve:
            with self.assertRaises(ValueError):
                prepare_em_resistor_cht_study({})
            with self.assertRaises(ValueError):
                prepare_em_resistor_cht_study({"request": invalid})
            solve.assert_not_called()
        study = self.prepared()
        study["cases"].append(deepcopy(study["cases"][0]))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            prepare_em_resistor_cht_study({"request": self.request, "study": study})

    def test_service_wrapper_and_finite_limits(self):
        response = handle_em_cosimulation_request(
            "prepare_em_resistor_cht_study", {"request": {"request": self.request}})
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["cases"][0]["type"], "em-resistor-cht")
        bad = deepcopy(self.request)
        bad["sample_index"] = float("nan")
        response = handle_em_cosimulation_request(
            "prepare_em_resistor_cht_study", {"request": {"request": bad}})
        self.assertFalse(response["ok"])
        boundary = handle({"method": "prepare_em_resistor_cht_study",
                           "params": {"request": {"request": self.request}}})
        self.assertTrue(boundary["ok"], boundary)
        self.assertEqual(boundary["result"]["cases"][0]["type"], "em-resistor-cht")

    def test_specialized_study_rejects_more_than_three_mib(self):
        study = prepare_em_resistor_cht_study({"request": self.request})
        study["notes"] = "x" * (3 * 1024**2)
        with self.assertRaisesRegex(ValueError, "study exceeds"):
            prepare_em_resistor_cht_study({"request": self.request, "study": study})

    def test_real_spike_package_write_read_preserves_study(self):
        study = self.prepared()
        design = SpiDeRV2.from_v1(SpiDeR(
            design_id="study-design", name="Study design", source_format="neutral",
            layers=[{"id": 0, "name": "F.Cu"}], metadata={"source_sha256": "a" * 64},
        )).to_dict()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "coupled-study.spike"
            write_spike_package(path, {
                "project": {"id": "em-resistor-cht", "name": "Coupled study", "studies": [study]},
                "design_ir": design,
            })
            reopened = read_project(path).payload["project"]["studies"][0]
        self.assertEqual(reopened, study)
        admitted = prepare_em_resistor_cht_study({"request": self.request, "study": reopened})
        self.assertEqual(admitted, study)


if __name__ == "__main__":
    unittest.main()
