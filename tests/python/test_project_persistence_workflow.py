import copy
import base64
import json
import tempfile
import unittest
import zlib
from pathlib import Path

from python.spike_core.contracts import SpiDeR
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.odb_importer import import_odb_design
from python.spike_core.normalized_source_codec import decode_normalized_source, encode_normalized_source
from python.spike_core.service_project_persistence import merge_future_fields, project_for_desktop
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.project_package import ProjectPackageError, read_spike_package
from tests.python.test_odb_harness_extensions import write_board


class ProjectPersistenceWorkflowTests(unittest.TestCase):
    def request(self, method, **params):
        response = handle_project_request(method, params, request_id="persistence-test", application_version="0.2.10")
        self.assertTrue(response["ok"], response)
        return response["result"]

    def test_desktop_save_open_save_as_keeps_odb_results_and_future_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            canonical = SpiDeRV2.from_v1(import_odb_design(str(write_board(directory)))).to_dict()
            canonical["future_geometry"] = {"curves": [1, 2], "vendor": "kept"}
            canonical["source"]["artifact_path"] = ""
            normalized = {"contract": "spike/design-snapshot/v1", "canonical_design": canonical,
                          "design": SpiDeRV2.from_dict(canonical).to_v1().to_dict()}
            results = [{"analysis_id": f"R{i}", "outputs": {"waveform": [i, i + 1]}, "future": {"unit": "A"}} for i in range(25)]
            snapshot = {"format": "spike-project-package/v2", "project": {"name": "ODB saved"},
                        "design": {"source_file": "job.spike-design.json", "source_format": "spike-normalized",
                                   "source_board": json.dumps(normalized), "canonical_design": canonical},
                        "analysis": {"latest_result": results[-1], "result_history": [{"id": item["analysis_id"], "bundle": item} for item in results],
                                     "result_display": "none", "future_setting": {"mode": "vendor"}},
                        "future_project": {"keep": True}}
            first = Path(directory) / "first.spike"
            saved = self.request("write_project_package", path=str(first), snapshot=snapshot)
            opened = self.request("read_project_package", path=str(first), defer_artifacts=True)
            history = opened["project"]["analysis"]["result_history"]
            self.assertEqual(len(history), 25)
            self.assertEqual(opened["canonical"]["design_ir"]["future_geometry"], canonical["future_geometry"])
            for i, record in enumerate(history):
                restored = self.request("read_project_state_artifact", path=str(first), reference=record["bundle"],
                                        expected_manifest_payload_sha256=saved["manifest"]["manifest_payload_sha256"])
                self.assertEqual(restored["value"], results[i])
            hydrated = self.request("read_project_package", path=str(first))["project"]
            self.assertEqual(hydrated["analysis"], snapshot["analysis"])
            second = Path(directory) / "copy.spike"
            hydrated["analysis"]["result_history"][0]["bundle"]["future"]["changed"] = True
            self.request("write_project_package", path=str(second), snapshot=hydrated, base_package_path=str(first))
            reopened = self.request("read_project_package", path=str(second))
            self.assertEqual(reopened["project"]["analysis"], hydrated["analysis"])
            self.assertEqual(reopened["project"]["future_project"], {"keep": True})
            for key, value in canonical["metadata"].items():
                self.assertEqual(reopened["canonical"]["design_ir"]["metadata"][key], json.loads(json.dumps(value)))

    def test_opened_multiboard_projection_resaves_exact_canonical_ids_and_links(self):
        legacy = SpiDeR(
            design_id="source-native-overlap", name="Source native overlap", source_format="kicad",
            layers=[{"id": 1, "name": "F.Cu"}], nets=[{"id": 1, "name": "GND"}],
            metadata={"source_sha256": "7" * 64},
        )
        canonical = SpiDeRV2.from_v1(legacy).to_dict()
        assembly_ir = {
            "contract": "spike/assembly-ir/v1", "assembly_id": "assembly", "name": "Assembly",
            "units": "mm", "coordinate_frame": "right-handed-z-up", "frames": [], "parts": [],
            "boards": [{"id": "board-a", "design_id": canonical["design_id"]}],
            "harnesses": [], "connector_mappings": [], "rigid_flex_links": [], "metadata": {},
        }
        retained_active = copy.deepcopy(canonical)
        retained_active["name"] = "Pre-resolution active record"
        assembly_designs = {"contract": "spike/assembly-designs/v1",
                            "active_design_id": canonical["design_id"], "designs": [retained_active]}
        package_payload = {"project": {"id": "roundtrip", "name": "Roundtrip"},
                           "design_ir": canonical, "assembly_ir": assembly_ir,
                           "assembly_designs": assembly_designs}
        projected = project_for_desktop(package_payload, {
            "format": "spike-project-package/v2", "project": {"name": "Roundtrip"}, "analysis": {},
            "design": SpiDeRV2.from_dict(canonical).to_v1().to_dict(),
            "assembly_ir": assembly_ir, "assembly_designs": assembly_designs,
        })
        # The legacy view retains colliding source-native layer/net IDs. The
        # exact canonical view remains authoritative for package persistence.
        self.assertEqual(projected["design"]["layers"][0]["id"], projected["design"]["nets"][0]["id"])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "roundtrip.spike"
            self.request("write_project_package", path=str(target), snapshot=projected,
                         generate_geometry_tables=False)
            reopened = read_spike_package(target).payload
        self.assertEqual(reopened["design_ir"]["design_id"], canonical["design_id"])
        self.assertEqual(reopened["design_ir"]["source"], canonical["source"])
        for collection in ("layers", "nets", "tracks", "vias", "pads", "zones", "components"):
            self.assertEqual([item["id"] for item in reopened["design_ir"][collection]],
                             [item["id"] for item in canonical[collection]])
        self.assertEqual(reopened["design_ir"]["components"], canonical["components"])
        reopened_active = reopened["assembly_designs"]["designs"][0]
        self.assertEqual(reopened_active["name"], reopened["design_ir"]["name"])
        for collection in ("layers", "nets", "tracks", "vias", "pads", "zones", "components"):
            self.assertEqual([item["id"] for item in reopened_active[collection]],
                             [item["id"] for item in reopened["design_ir"][collection]])
        self.assertEqual([(board["id"], board["design_id"]) for board in reopened["assembly_ir"]["boards"]],
                         [(board["id"], board["design_id"]) for board in assembly_ir["boards"]])

        damaged = copy.deepcopy(projected)
        damaged["design"]["canonical_design"]["nets"][0]["id"] = canonical["layers"][0]["id"]
        with tempfile.TemporaryDirectory() as directory:
            failed = handle_project_request("write_project_package", {
                "path": str(Path(directory) / "damaged.spike"), "snapshot": damaged,
                "generate_geometry_tables": False,
            }, request_id="damaged-canonical", application_version="test")
            self.assertFalse(failed["ok"])
            self.assertIn("canonical entity IDs must be unique", failed["error"])

    def test_engineering_review_evidence_survives_native_package_roundtrip(self):
        from python.spike_core.engineering_review import review_engineering
        from tests.python.test_engineering_review import request
        with tempfile.TemporaryDirectory() as directory:
            canonical = SpiDeRV2.from_v1(import_odb_design(str(write_board(directory)))).to_dict()
            canonical["source"]["artifact_path"] = ""
            review_request = request()
            evidence = {"contract": "spike/engineering-review-workspace/v1", "scope_sha256": "a" * 64,
                        "overrides": review_request["overrides"], "result": review_engineering(review_request)}
            snapshot = {"format": "spike-project-package/v2", "project": {"name": "Review persistence"},
                        "design": {"canonical_design": canonical, "source_format": "spike-normalized",
                                   "source_file": "review.spike-design.json",
                                   "source_board": json.dumps({"contract": "spike/design-snapshot/v1",
                                       "canonical_design": canonical, "design": SpiDeRV2.from_dict(canonical).to_v1().to_dict()})},
                        "analysis": {"engineering_review": evidence}}
            path = Path(directory) / "review.spike"
            self.request("write_project_package", path=str(path), snapshot=snapshot)
            loaded = self.request("read_project_package", path=str(path))["project"]
            self.assertEqual(loaded["analysis"]["engineering_review"], evidence)
            # Re-saving preserves complete review evidence, decimal strings and scoped identities.
            second = Path(directory) / "review-again.spike"
            self.request("write_project_package", path=str(second), snapshot=loaded, base_package_path=str(path))
            self.assertEqual(self.request("read_project_package", path=str(second))["project"]["analysis"]["engineering_review"], evidence)

    def test_binary_odb_projects_project_complete_canonical_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            canonical = SpiDeRV2.from_v1(import_odb_design(str(write_board(directory)))).to_dict()
        canonical["future_geometry"] = {"polarity": "negative", "vendor": ["A", "B"]}
        canonical["source"]["artifact_path"] = "package:sources/job.tgz"
        projected = project_for_desktop({"design_ir": canonical}, {"design": {}, "analysis": {}})
        snapshot = json.loads(projected["design"]["source_board"])
        self.assertEqual(projected["design"]["source_format"], "spike-normalized")
        self.assertEqual(snapshot["canonical_design"], json.loads(json.dumps(canonical)))
        self.assertTrue(snapshot["design"]["pads"])
        self.assertTrue(snapshot["design"]["zones"])

    def test_deferred_open_uses_single_authoritative_canonical_transport_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            canonical = SpiDeRV2.from_v1(import_odb_design(str(write_board(directory)))).to_dict()
            canonical["source"]["artifact_path"] = ""
            snapshot = {"format": "spike-project-package/v2", "project": {"name": "deferred"},
                        "design": {"source_file": "job.spike-design.json", "source_format": "spike-normalized",
                                   "source_board": json.dumps({"contract": "spike/design-snapshot/v1",
                                                               "canonical_design": canonical,
                                                               "design": SpiDeRV2.from_dict(canonical).to_v1().to_dict()}),
                                   "canonical_design": canonical},
                        "analysis": {}}
            project = Path(directory) / "deferred.spike"
            self.request("write_project_package", path=str(project), snapshot=snapshot)
            opened = self.request("read_project_package", path=str(project), defer_artifacts=True,
                                  compact_normalized_source=True)
        self.assertNotIn("canonical_design", opened["project"]["design"])
        self.assertEqual(opened["canonical"]["design_ir"]["design_id"], canonical["design_id"])

    def test_transport_projection_can_skip_deep_copy_without_mutating_input(self):
        canonical = {"contract": "spike/design-ir/v2", "source": {"source_format": "kicad"}}
        projected = {"design": {"source_board": "board"}, "assembly_designs": {"designs": [{"id": "shared"}]}}
        result = project_for_desktop({"design_ir": canonical}, projected, copy_project=False)
        self.assertIs(result["assembly_designs"], projected["assembly_designs"])
        self.assertIsNot(result["design"], projected["design"])
        self.assertNotIn("canonical_design", projected["design"])
        self.assertIs(result["design"]["canonical_design"], canonical)

    def test_compact_normalized_source_save_and_open_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            canonical = SpiDeRV2.from_v1(import_odb_design(str(write_board(directory)))).to_dict()
            canonical["source"]["artifact_path"] = ""
            normalized = json.dumps({"contract": "spike/design-snapshot/v1",
                                     "canonical_design": canonical,
                                     "design": SpiDeRV2.from_dict(canonical).to_v1().to_dict()})
            snapshot = {"format": "spike-project-package/v2", "project": {"name": "compact"},
                        "design": {"source_file": "job.spike-design.json", "source_format": "spike-normalized",
                                   "source_board": encode_normalized_source(normalized)}, "analysis": {}}
            project = Path(directory) / "compact.spike"
            self.request("write_project_package", path=str(project), snapshot=snapshot)
            opened = self.request("read_project_package", path=str(project), compact_normalized_source=True)
            wrapper = opened["project"]["design"]["source_board"]
            projected_source = json.loads(decode_normalized_source(wrapper))
            self.assertTrue(wrapper["canonical_design_omitted"])
            self.assertNotIn("canonical_design", projected_source)
            self.assertEqual(projected_source["design"], json.loads(normalized)["design"])
            projected_source["canonical_design"] = opened["canonical"]["design_ir"]
            self.assertEqual(projected_source["canonical_design"]["design_id"], canonical["design_id"])
            self.assertNotIn("canonical_design", opened["project"]["design"])
            self.assertEqual(opened["canonical"]["design_ir"]["design_id"], canonical["design_id"])
            string_snapshot = copy.deepcopy(snapshot)
            string_snapshot["design"]["source_board"] = json.dumps(string_snapshot["design"]["source_board"])
            self.request("write_project_package", path=str(Path(directory) / "string-wrapper.spike"),
                         snapshot=string_snapshot)
            damaged = copy.deepcopy(snapshot)
            damaged["design"]["source_board"]["sha256"] = "0" * 64
            failed = handle_project_request("write_project_package", {"path": str(Path(directory) / "bad.spike"),
                                                                       "snapshot": damaged},
                                            request_id="bad-wrapper", application_version="test")
            self.assertFalse(failed["ok"])

    def test_normalized_source_decoder_bounds_expansion_and_rejects_trailing_streams(self):
        expanded = encode_normalized_source("x" * 100_000)
        expanded["bytes"] = 4
        with self.assertRaisesRegex(ProjectPackageError, "exceeds its declared byte count"):
            decode_normalized_source(expanded)

        trailing = encode_normalized_source("bounded")
        compressed = base64.b64decode(trailing["data"])
        trailing["data"] = base64.b64encode(compressed + zlib.compress(b"second stream")).decode("ascii")
        with self.assertRaisesRegex(ProjectPackageError, "trailing stream"):
            decode_normalized_source(trailing)

    def test_future_fields_survive_edits_without_resurrecting_deleted_objects(self):
        base = {"future": {"units": "mm"}, "analysis": {"active": "a", "custom": [1]},
                "parts": [{"id": "a", "value": 1, "vendor": "retained"}, {"id": "deleted"}]}
        edited = {"analysis": {"active": None}, "parts": [{"id": "a", "value": 2}]}
        result = merge_future_fields(base, edited)
        self.assertEqual(result["future"], base["future"])
        self.assertEqual(result["analysis"], {"active": None, "custom": [1]})
        self.assertEqual(result["parts"], [{"id": "a", "value": 2, "vendor": "retained"}])
