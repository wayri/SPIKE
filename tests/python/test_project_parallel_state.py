# SPDX-License-Identifier: Apache-2.0
import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from python.spike_core.parallel_pool import _digest, run_parallel_batch
from python.spike_core.project_package import ProjectPackageError, _json_bytes, _sha256, read_project
from python.spike_core.project_parallel_state import empty_parallel_state, validate_parallel_state
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.service_project_persistence import migrate_saved_assembly_results, read_persistent_artifact
from tests.python.test_harness_pi import fixture
from tests.python.test_parallel_pool import batch


class ProjectParallelStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = batch([{"id": "electrical", "method": "run_harness_pi", "params": {"request": fixture()}}])
        cls.result = run_parallel_batch(cls.request)
        if cls.result["status"] != "completed":
            raise AssertionError(cls.result)

    def state(self):
        state = empty_parallel_state()
        state["draft"]["jobs_json"] = json.dumps(self.request["jobs"])
        state["runs"] = [{"id": "run-1", "request": copy.deepcopy(self.request),
                          "result": copy.deepcopy(self.result), "status": "completed"}]
        return state

    def snapshot(self, state=None):
        return {"format": "spike-project-package/v2", "project": {"name": "parallel"},
                "design": {"name": "empty"}, "analysis": {"parallel_execution": state or self.state()}}

    def call(self, method, **params):
        if method == "write_project_package":
            params.setdefault("generate_geometry_tables", False)
        response = handle_project_request(method, params, request_id="parallel-persist", application_version="0.2.10")
        self.assertTrue(response["ok"], response)
        return response["result"]

    def test_actual_package_roundtrip_and_deferred_save_as(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "first.spike"
            self.call("write_project_package", path=str(path), snapshot=self.snapshot())
            with patch("python.spike_core.parallel_pool.run_parallel_batch", side_effect=AssertionError("must not execute")):
                opened = self.call("read_project_package", path=str(path))
                self.assertEqual(opened["project"]["analysis"]["parallel_execution"], self.state())
                self.assertEqual(opened["canonical"]["analyses"]["parallel_execution"], self.state())
                deferred = self.call("read_project_package", path=str(path), defer_artifacts=True)
                reference = deferred["project"]["analysis"]["parallel_execution"]["runs"][0]["result"]
                self.assertEqual(reference["contract"], "spike/state-artifact-reference/v1")
                second = Path(directory) / "second.spike"
                self.call("write_project_package", path=str(second), snapshot=deferred["project"], base_package_path=str(path))
                reopened = self.call("read_project_package", path=str(second))
                self.assertEqual(reopened["project"]["analysis"]["parallel_execution"], self.state())

    def test_hash_bound_nested_assembly_result_is_not_migrated(self):
        state = self.state()
        result = state["runs"][0]["result"]
        job = result["outcomes"][0]
        job["result"] = {"contract": "spike/multiboard-circuit-result/v1", "assembly_digest": "legacy-digest",
                         "assembly_identity_migration": {"from": "older", "to": "legacy-digest"}}
        job["provenance"]["response_sha256"] = _digest({"id": job["id"], "ok": True, "result": job["result"], "meta": job["worker_meta"]})
        with patch("python.spike_core.service_project_persistence.migrate_legacy_result_assembly_digest", side_effect=AssertionError("immutable batch")):
            self.assertEqual(migrate_saved_assembly_results(result, {"contract": "spike/assembly-ir/v1"}), result)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "nested.spike"
                self.call("write_project_package", path=str(path), snapshot=self.snapshot(state))
                opened = read_project(path)
                reference = opened.payload["analyses"]["parallel_execution"]["runs"][0]["result"]
                restored = read_persistent_artifact("read_project_state_artifact", {"path": str(path), "reference": reference,
                    "expected_manifest_payload_sha256": opened.manifest["manifest_payload_sha256"]})
                self.assertEqual(restored["value"], result)

    def test_inline_request_result_contract_is_not_externalized(self):
        state = self.state()
        run = state["runs"][0]
        run["request"]["jobs"][0]["params"]["request"]["retained_input"] = {
            "contract": "spike/prior-result/v1", "values": [1, 2, 3]}
        run["result"]["provenance"]["request_sha256"] = _digest(run["request"])
        run["result"]["outcomes"][0]["provenance"]["request_sha256"] = _digest(run["request"]["jobs"][0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inline.spike"
            self.call("write_project_package", path=str(path), snapshot=self.snapshot(state))
            opened = self.call("read_project_package", path=str(path))
            self.assertEqual(opened["project"]["analysis"]["parallel_execution"], state)

    def test_cluster_result_and_port_id_are_portable(self):
        state = self.state()
        cluster = {"contract": "spike/cluster-batch-result/v1", "request_sha256": _digest(self.request),
                   "jobs": [{**self.result["outcomes"][0], "node_id": "worker-1", "node_certificate_sha256": "a" * 64}],
                   "execution": "independent_jobs", "distributed_single_solve": "unsupported"}
        state["runs"][0]["result"] = cluster
        state["draft"]["jobs_json"] = '{"port_id":"J1","nodes":[1,2]}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.spike"
            self.call("write_project_package", path=str(path), snapshot=self.snapshot(state))
            self.assertEqual(self.call("read_project_package", path=str(path))["project"]["analysis"]["parallel_execution"], state)

    def test_failed_and_unknown_delivery_outcomes_preserve_truth(self):
        request = batch([{"id": "bad", "method": "run_harness_pi", "params": {"request": {}}}])
        result = run_parallel_batch(request)
        self.assertEqual(result["status"], "completed_with_errors")
        state = empty_parallel_state()
        state["runs"] = [{"id": "failed-child", "request": request, "result": result, "status": "completed_with_errors"}]
        self.assertEqual(validate_parallel_state(state), state)
        state["runs"][0]["result"] = {"contract": "spike/cluster-batch-result/v1", "request_sha256": _digest(request),
            "jobs": [{"id": "bad", "node_id": "Lab worker 1", "state": "unknown", "error_code": "SPIKE-CLUSTER-TRANSPORT", "error": "Unknown delivery"}],
            "execution": "independent_jobs", "distributed_single_solve": "unsupported"}
        self.assertEqual(validate_parallel_state(state), state)
        state["runs"][0]["status"] = "completed"
        with self.assertRaisesRegex(ValueError, "status"):
            validate_parallel_state(state)

    def test_cluster_identity_and_execution_semantics_rejected(self):
        for change in (lambda r: r.update(execution="single_distributed_solve"),
                       lambda r: r["jobs"][0].update(node_id=""),
                       lambda r: r["jobs"][0].update(node_certificate_sha256="not-a-hash")):
            state = self.state()
            result = {"contract": "spike/cluster-batch-result/v1", "request_sha256": _digest(self.request),
                "jobs": [{**self.result["outcomes"][0], "node_id": "worker", "node_certificate_sha256": "a" * 64}],
                "execution": "independent_jobs", "distributed_single_solve": "unsupported"}
            change(result)
            state["runs"][0]["result"] = result
            with self.assertRaises(ValueError):
                validate_parallel_state(state)

    def test_no_results_and_design_exchange_retain_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            for options in ({"include_results": False}, {"profile": "design_exchange"}):
                path = Path(directory) / "setup.spike"
                self.call("write_project_package", path=str(path), snapshot=self.snapshot(), **options)
                opened = self.call("read_project_package", path=str(path))
                state = opened["project"]["analysis"]["parallel_execution"]
                self.assertEqual(state["draft"], self.state()["draft"])
                self.assertEqual(state["runs"], [])
                with zipfile.ZipFile(path) as archive:
                    self.assertFalse(any(name.startswith("state/artifacts/") for name in archive.namelist()))

    def test_legacy_missing_state_and_unfinished_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.spike"
            old = self.snapshot()
            old["analysis"] = {}
            path.write_text(json.dumps(old), encoding="utf-8")
            self.assertNotIn("parallel_execution", read_project(path).payload["analyses"])
            desktop_analysis = self.call("read_project_package", path=str(path))["project"]["analysis"]
            self.assertNotIn("parallel_execution", desktop_analysis)
            self.assertEqual(validate_parallel_state(desktop_analysis.get("parallel_execution")), empty_parallel_state())
            state = empty_parallel_state()
            state["draft"]["jobs_json"] = '[{"id":'
            self.call("write_project_package", path=str(path), snapshot=self.snapshot(state))
            self.assertEqual(self.call("read_project_package", path=str(path))["project"]["analysis"]["parallel_execution"], state)

    def test_reject_digest_corruption_bounds_nonfinite_and_credentials(self):
        changes = [lambda s: s["runs"][0]["request"].update(timeout_s=31),
                   lambda s: s["runs"][0]["result"]["outcomes"][0]["result"].update(tampered=True),
                   lambda s: s.update(runs=s["runs"] * 33),
                   lambda s: s["runs"][0]["result"].update(future=float("nan")),
                   lambda s: s["draft"].update(jobs_json='{"private_key":"secret"}'),
                   lambda s: s["draft"].update(jobs_json='{"password":"unfinished'),
                   lambda s: s["draft"].update(jobs_json='{"host":"node.local"}'),
                   lambda s: s["draft"].update(jobs_json='-----BEGIN PRIVATE KEY-----'),
                   lambda s: s["runs"][0]["result"].update(client_cert="C:/secret.pem")]
        for change in changes:
            state = self.state()
            change(state)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_parallel_state(state)

    def test_manifest_rehashed_corrupt_result_still_rejected_on_open(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.spike"
            self.call("write_project_package", path=str(path), snapshot=self.snapshot())
            with zipfile.ZipFile(path) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            # Corrupt request binding while keeping ZIP/manifest transport hashes valid.
            analyses = json.loads(members["analyses/index.json"])
            analyses["parallel_execution"]["runs"][0]["request"]["timeout_s"] = 31
            members["analyses/index.json"] = _json_bytes(analyses)
            manifest = json.loads(members["manifest.json"])
            for record in manifest["members"]:
                record.update(sha256=_sha256(members[record["path"]]), size=len(members[record["path"]]))
            manifest.pop("manifest_payload_sha256")
            manifest["manifest_payload_sha256"] = _sha256(_json_bytes(manifest))
            members["manifest.json"] = _json_bytes(manifest)
            with zipfile.ZipFile(path, "w") as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
            with self.assertRaisesRegex(ProjectPackageError, "digest mismatch"):
                read_project(path)

    def test_old_v3_missing_field_defaults_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.spike"
            self.call("write_project_package", path=str(path), snapshot=self.snapshot(empty_parallel_state()))
            with zipfile.ZipFile(path) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            members["analyses/index.json"] = _json_bytes({})
            members["extensions/index.json"] = _json_bytes({})
            manifest = json.loads(members["manifest.json"])
            manifest["schemas"].pop("parallel_execution")
            for record in manifest["members"]:
                record.update(sha256=_sha256(members[record["path"]]), size=len(members[record["path"]]))
            manifest.pop("manifest_payload_sha256")
            manifest["manifest_payload_sha256"] = _sha256(_json_bytes(manifest))
            members["manifest.json"] = _json_bytes(manifest)
            with zipfile.ZipFile(path, "w") as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
            self.assertNotIn("parallel_execution", read_project(path).payload["analyses"])
            desktop_analysis = self.call("read_project_package", path=str(path))["project"]["analysis"]
            self.assertNotIn("parallel_execution", desktop_analysis)
            self.assertEqual(validate_parallel_state(desktop_analysis.get("parallel_execution")), empty_parallel_state())
