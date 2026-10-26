# SPDX-License-Identifier: Apache-2.0
import copy
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from python.spike_core.solvers.circuits.models.multiboard_circuit import run_multiboard_circuit
from python.spike_core.solvers.thermal_fluid.heat.multiboard_thermal import run_multiboard_thermal
from python.spike_core.solvers.electromagnetics.fields.multiboard_em import run_multiboard_em
from python.spike_core.multiboard_identity import assembly_physics_digest, legacy_assembly_physics_digest, migrate_legacy_result_assembly_digest
from python.spike_core.multiboard_study import prepare_multiboard_study, physical_assembly, validate_study_result
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.service_project_persistence import without_saved_results
from python.spike_core.service_project_persistence import prepare_persistent_state
from python.spike_core.project_state_artifacts import hydrate_result_state
from tests.python.test_assembly_batch_import import active_design
from tests.python.test_multiboard_circuit import fixture as circuit_request
from tests.python.test_multiboard_thermal import request as thermal_request
from tests.python.test_multiboard_em import request as em_request


class MultiboardStudyTests(unittest.TestCase):
    def test_verified_legacy_results_migrate_without_weakening_binding(self):
        for domain, make, run in (("pi", circuit_request, run_multiboard_circuit),
                                  ("si", circuit_request, run_multiboard_circuit),
                                  ("thermal", thermal_request, run_multiboard_thermal),
                                  ("emi", em_request, run_multiboard_em)):
            with self.subTest(domain=domain):
                raw = make()
                if domain == "si":
                    raw["domain"] = "si"
                    raw["analysis"] = {"mode": "ac", "start_hz": 1000, "stop_hz": 1000000, "points": 3, "scale": "log"}
                raw["assembly"] = physical_assembly(raw["assembly"])
                raw["assembly"]["boards"][0]["frame"]["transform"] = [
                    float(value) for value in raw["assembly"]["boards"][0]["frame"]["transform"]]
                result = run(raw)
                result["assembly_digest"] = legacy_assembly_physics_digest(raw["assembly"])
                result["request_digest"] = hashlib.sha256(json.dumps(
                    raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
                original_result = copy.deepcopy(result)
                persisted = copy.deepcopy(raw["assembly"])
                persisted["extensions"]["spike.multiboard-studies"] = {
                    domain: {"request": {k: v for k, v in raw.items() if k != "assembly"}}}
                original_persisted = copy.deepcopy(persisted)
                migrated = migrate_legacy_result_assembly_digest(result, persisted)
                self.assertEqual(result, original_result)
                self.assertEqual(persisted, original_persisted)
                self.assertEqual(migrated["assembly_identity_migration"]["from"], result["assembly_digest"])
                transported = json.loads(json.dumps(persisted), parse_float=lambda value:
                                         int(float(value)) if float(value).is_integer() else float(value))
                setup = transported["extensions"]["spike.multiboard-studies"][domain]["request"]
                validate_study_result(transported, domain, setup, migrated)
                changed = copy.deepcopy(persisted)
                changed["boards"][0]["frame"]["transform"][3] += 0.0000000001
                self.assertEqual(migrate_legacy_result_assembly_digest(result, changed), result)
                with self.assertRaisesRegex(ValueError, "different physical assembly"):
                    validate_study_result(changed, domain, setup, migrated)
                changed = copy.deepcopy(persisted)
                changed["extensions"]["spike.multiboard-studies"][domain]["request"]["identity-change"] = 1
                self.assertEqual(migrate_legacy_result_assembly_digest(result, changed), result)
                unknown = {**result, "contract": "unknown/result/v1"}
                self.assertEqual(migrate_legacy_result_assembly_digest(unknown, persisted), unknown)

    def test_physical_identity_survives_json_number_transport(self):
        raw = circuit_request()
        assembly = physical_assembly(raw["assembly"])
        assembly["boards"][0]["frame"]["transform"] = [
            float(value) for value in assembly["boards"][0]["frame"]["transform"]]
        assembly["boards"][0]["frame"]["transform"][3] = -0.0
        # Match JS JSON.stringify's loss of integral-float and signed-zero
        # spellings, including numbers nested in unconstrained extension data.
        assembly.setdefault("extensions", {})["identity-test"] = {
            "coordinates": [0.0, -0.0, 11.0, 1.0000000000000002], "enabled": True}
        transported = json.loads(json.dumps(assembly), parse_float=lambda value:
                                 int(float(value)) if float(value).is_integer() else float(value))
        raw["assembly"] = assembly
        result = run_multiboard_circuit(raw)
        self.assertEqual(assembly_physics_digest(assembly), assembly_physics_digest(transported))
        validate_study_result(transported, "pi", raw, result)
        transported["extensions"]["spike.multiboard-studies"] = {"pi": {"result": result}}
        self.assertEqual(assembly_physics_digest(assembly), assembly_physics_digest(transported))
        transported["extensions"]["identity-test"]["coordinates"][-1] = 1.0
        self.assertNotEqual(assembly_physics_digest(assembly), assembly_physics_digest(transported))
        transported = copy.deepcopy(assembly)
        transported["extensions"]["identity-test"]["enabled"] = 1
        self.assertNotEqual(assembly_physics_digest(assembly), assembly_physics_digest(transported))

    def test_all_domains_execute_save_reopen_and_remove_only_results(self):
        for domain, make, run in (("pi", circuit_request, run_multiboard_circuit),
                                  ("si", circuit_request, run_multiboard_circuit),
                                  ("thermal", thermal_request, run_multiboard_thermal),
                                  ("emi", em_request, run_multiboard_em)):
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as directory:
                raw = make()
                if domain == "si":
                    raw["domain"] = "si"
                    raw["analysis"] = {"mode": "ac", "start_hz": 1000, "stop_hz": 1000000, "points": 3, "scale": "log"}
                for board in raw["assembly"]["boards"]: board["design_id"] = "base"
                raw["assembly"] = physical_assembly(raw["assembly"])
                result = run(raw)
                self.assertEqual(result["status"], "completed")
                path = Path(directory) / "stack.spike"
                payload = {"project": {"id": "stack", "name": "Stack"}, "design_ir": active_design(), "assembly_ir": raw["assembly"]}
                manifest = write_spike_package(path, payload)
                setup = {k: v for k, v in raw.items() if k != "assembly"}
                response = handle_project_request("save_multiboard_study_in_project", {
                    "project_path": str(path), "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                    "domain": domain, "request": setup, "result": result, "assembly_digest": result["assembly_digest"]},
                    request_id=1, application_version="test")
                self.assertTrue(response["ok"], response)
                opened = read_project(path, include_members=True)
                stored = opened.payload["assembly_ir"]["extensions"]["spike.multiboard-studies"][domain]["result"]
                self.assertEqual(stored["contract"], "spike/state-artifact-reference/v1")
                reopened = hydrate_result_state(opened.payload, path, opened.manifest["manifest_payload_sha256"])
                study = reopened["assembly_ir"]["extensions"]["spike.multiboard-studies"][domain]
                self.assertEqual(study["request"], setup)
                self.assertEqual(study["result"], result)
                self.assertEqual(assembly_physics_digest(reopened["assembly_ir"]), result["assembly_digest"])
                validate_study_result(reopened["assembly_ir"], domain, setup, result)
                copy_payload = without_saved_results(reopened)
                clean = copy_payload["assembly_ir"]["extensions"]["spike.multiboard-studies"][domain]
                self.assertNotIn("result", clean)
                self.assertEqual(clean["request"], setup)
                copy_path = Path(directory) / "setup.spike"
                copy_payload, members = prepare_persistent_state(copy_payload, None, opened.members)
                write_spike_package(copy_path, copy_payload, preserved_members=members)
                self.assertNotIn("result", read_project(copy_path).payload["assembly_ir"]["extensions"]["spike.multiboard-studies"][domain])
                self.assertFalse(any(name.startswith("state/artifacts/") for name in read_project(copy_path, include_members=True).members))

    def test_changed_properties_or_placement_cannot_reuse_results(self):
        raw = circuit_request(); raw["assembly"] = physical_assembly(raw["assembly"])
        result = run_multiboard_circuit(raw)
        setup = {k: copy.deepcopy(v) for k, v in raw.items() if k != "assembly"}
        setup["link_models"][0]["pins"][0]["resistance_ohm"] += .1
        with self.assertRaisesRegex(ValueError, "setup changed"):
            validate_study_result(raw["assembly"], "pi", setup, result)
        changed = copy.deepcopy(raw["assembly"])
        changed["boards"][1]["frame"]["transform"] = list(changed["boards"][1]["frame"]["transform"])
        changed["boards"][1]["frame"]["transform"][3] += 1
        with self.assertRaisesRegex(ValueError, "different physical assembly"):
            validate_study_result(changed, "pi", raw, result)

    def test_templates_derive_graph_without_guessing_physical_values(self):
        raw = circuit_request()
        for domain in ("pi", "si", "thermal", "emi"):
            draft = prepare_multiboard_study({"assembly": raw["assembly"], "domain": domain})
            self.assertTrue(draft["missing_properties_require_review"])
            self.assertEqual(draft["assembly_digest"], assembly_physics_digest(raw["assembly"]))
            validate_study_result(raw["assembly"], domain, draft["request"], None)
        electrical = prepare_multiboard_study({"assembly": raw["assembly"], "domain": "si"})["request"]
        self.assertEqual(electrical["link_models"][0]["link_id"], "cable")
        self.assertIsNone(electrical["link_models"][0]["pins"][0]["resistance_ohm"])
        self.assertEqual(electrical["analysis"]["mode"], "ac")

    def test_malformed_setup_and_promoted_result_refused(self):
        raw = circuit_request(); raw["assembly"] = physical_assembly(raw["assembly"])
        with self.assertRaisesRegex(ValueError, "Invalid study setup"):
            validate_study_result(raw["assembly"], "pi", {"contract": raw["contract"], "domain": "pi"}, None)
        result = run_multiboard_circuit(raw); result["production_qualified"] = True
        with self.assertRaisesRegex(ValueError, "unqualified model status"):
            validate_study_result(raw["assembly"], "pi", raw, result)
        result["production_qualified"] = False
        result["node_map"] = {"a": None}
        with self.assertRaisesRegex(ValueError, "Malformed circuit result node map"):
            validate_study_result(raw["assembly"], "pi", raw, result)


if __name__ == "__main__": unittest.main()
