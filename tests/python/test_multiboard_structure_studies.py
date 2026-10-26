# SPDX-License-Identifier: Apache-2.0
"""Portable study setup/results retain mechanical owners without promoting scope."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from python.spike_core.multiboard_study import prepare_multiboard_study, physical_assembly, validate_study_result
from python.spike_core.solvers.circuits.models.multiboard_circuit import run_multiboard_circuit
from python.spike_core.solvers.electromagnetics.fields.multiboard_em import run_multiboard_em
from python.spike_core.solvers.thermal_fluid.heat.multiboard_thermal import run_multiboard_thermal
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.project_state_artifacts import hydrate_result_state
from python.spike_core.service_project_handlers import handle_project_request
from tests.python.test_assembly_batch_import import active_design
from tests.python.test_multiboard_circuit_parts import fixture as circuit_case
from tests.python.test_multiboard_thermal_parts import case_request as thermal_case
from tests.python.test_multiboard_em import request as board_em


def magnetic_case():
    raw = board_em()
    removed = raw["assembly"]["boards"].pop()["id"]
    raw["assembly"]["harnesses"] = []
    raw["assembly"]["connector_mappings"] = []
    raw["assembly"]["parts"] = [{"id": "case", "model_id": "case-step", "part_type": "enclosure"}]
    for loop in raw["loops"]:
        if loop.get("board_id") == removed:
            loop.pop("board_id")
            loop["part_id"] = "case"
    return raw


class MechanicalStructureStudyTests(unittest.TestCase):
    def test_drafts_include_parts_bonds_contacts_and_ignore_containers(self):
        raw = circuit_case()
        raw["assembly"]["parts"].append({"id": "group", "part_type": "subassembly"})
        raw["assembly"]["thermal_contacts"] = [{"id": "mount", "endpoint_a": "board", "endpoint_b": "case"}]
        for domain in ("pi", "si", "thermal", "emi"):
            draft = prepare_multiboard_study({"assembly": raw["assembly"], "domain": domain})["request"]
            validate_study_result(raw["assembly"], domain, draft, None)
            if domain == "emi":
                self.assertEqual([row["part_id"] for row in draft["loops"] if "part_id" in row], ["case"])
            else:
                self.assertEqual([row["part_id"] for row in draft["part_models"]], ["case"])
            if domain in ("si", "pi"):
                self.assertEqual(draft["electrical_bond_models"][0]["endpoint_b"], {"part_id": "case", "node": "chassis"})
                self.assertIsNone(draft["electrical_bond_models"][0]["resistance_ohm"])
            if domain == "thermal":
                self.assertEqual(draft["contact_models"][0]["to"], {"part_id": "case", "node": "body"})
        raw["assembly"]["parts"] = [{"id": "group", "part_type": "subassembly"}]
        with self.assertRaisesRegex(ValueError, "physical mechanical part"):
            prepare_multiboard_study({"assembly": raw["assembly"], "domain": "thermal"})

    def test_solved_structure_studies_save_reopen_and_bind_placement(self):
        for domain, make, run in (("si", circuit_case, run_multiboard_circuit),
                                  ("thermal", thermal_case, run_multiboard_thermal),
                                  ("emi", magnetic_case, run_multiboard_em)):
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as directory:
                raw = make()
                raw["assembly"] = physical_assembly(raw["assembly"])
                result = run(raw)
                self.assertEqual(result["status"], "completed")
                setup = {key: value for key, value in raw.items() if key != "assembly"}
                validate_study_result(raw["assembly"], domain, setup, result)
                path = Path(directory) / "assembly-case.spike"
                artifact = b"ISO-10303-21;END-ISO-10303-21;"  # Package identity fixture, not a solved solid.
                payload = {"project": {"id": "case-study", "name": "Case study"}, "design_ir": active_design(), "assembly_ir": raw["assembly"],
                    "models": {"contract": "spike/model-index/v1", "models": [{"id": "case-step", "model_type": "step",
                        "uri": "package:models/artifacts/case.step", "digest": hashlib.sha256(artifact).hexdigest()}]}}
                manifest = write_spike_package(path, payload, model_artifacts={"case.step": artifact})
                response = handle_project_request("save_multiboard_study_in_project", {
                    "project_path": str(path), "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                    "domain": domain, "request": setup, "result": result, "assembly_digest": result["assembly_digest"]},
                    request_id=1, application_version="test")
                self.assertTrue(response["ok"], response)
                opened = read_project(path, include_members=True)
                restored = hydrate_result_state(opened.payload, path, opened.manifest["manifest_payload_sha256"])
                study = restored["assembly_ir"]["extensions"]["spike.multiboard-studies"][domain]
                self.assertEqual(study["request"], setup)
                self.assertEqual(study["result"], result)
                self.assertEqual(opened.members["models/artifacts/case.step"], artifact)
                validate_study_result(restored["assembly_ir"], domain, setup, result)
                changed = copy.deepcopy(restored["assembly_ir"])
                changed["parts"][0]["frame"]["transform"] = list(changed["parts"][0]["frame"]["transform"])
                changed["parts"][0]["frame"]["transform"][3] += 1
                with self.assertRaisesRegex(ValueError, "different physical assembly"):
                    validate_study_result(changed, domain, setup, result)

    def test_malformed_part_results_are_refused(self):
        for domain, make, run, field, bad in (("thermal", thermal_case, run_multiboard_thermal, "part_temperatures_c", {"case": {"body": True}}),
                                             ("si", circuit_case, run_multiboard_circuit, "part_node_map", {"case": None})):
            raw = make(); result = run(raw); result[field] = bad
            with self.assertRaisesRegex(ValueError, "Malformed"):
                validate_study_result(raw["assembly"], domain, raw, result)

    def test_old_or_incomplete_results_cannot_silently_omit_casings(self):
        for domain, make, run, field in (("thermal", thermal_case, run_multiboard_thermal, "part_temperatures_c"),
                                        ("si", circuit_case, run_multiboard_circuit, "part_node_map")):
            raw = make(); result = run(raw)
            legacy = copy.deepcopy(raw); legacy.pop("part_models")
            with self.assertRaisesRegex(ValueError, "explicit models"):
                validate_study_result(raw["assembly"], domain, legacy, result)
            result.pop(field)
            with self.assertRaisesRegex(ValueError, "omit or misidentify"):
                validate_study_result(raw["assembly"], domain, raw, result)
        raw = magnetic_case(); result = run_multiboard_em(raw)
        result["samples"][0]["loops"].pop()
        with self.assertRaisesRegex(ValueError, "omit or misidentify"):
            validate_study_result(raw["assembly"], "emi", raw, result)

    def test_colon_containing_occurrence_endpoint_remains_exact(self):
        raw = circuit_case()
        raw["assembly"]["parts"][0]["id"] = "case:one"
        raw["assembly"]["electrical_bonds"][0]["endpoint_b"] = "case:one::contact"
        raw["assembly"]["electrical_bonds"][1]["endpoint_a"] = "case:one"
        draft = prepare_multiboard_study({"assembly": raw["assembly"], "domain": "si"})["request"]
        self.assertEqual(draft["electrical_bond_models"][0]["endpoint_b"], {"part_id": "case:one", "node": "chassis"})
        self.assertEqual(draft["electrical_bond_models"][1]["endpoint_a"]["part_id"], "case:one")

    def test_incomplete_passive_type_change_is_saveable_but_not_executable(self):
        raw = circuit_case()
        raw["part_models"][0]["elements"][0]["capacitance_f"] = None
        validate_study_result(raw["assembly"], "si", raw, None)
        with self.assertRaises(ValueError):
            run_multiboard_circuit(raw)


if __name__ == "__main__":
    unittest.main()
