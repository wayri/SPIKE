import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.project_package import ProjectPackageError, _sha256, read_spike_package, write_spike_package
from python.spike_core.project_state_artifacts import (
    STATE_REFERENCE, externalize_result_state, hydrate_result_state, read_verified_artifacts,
)
from python.spike_core.project_visual_artifacts import prepare_visual_artifacts, read_saved_visual_stage
from tests.python import test_project_package_v3 as fixtures
from tests.python.test_staged_visual_import import glb_bytes


class ProjectStateArtifactTests(unittest.TestCase):
    def test_repeated_dense_result_serializes_once_without_copying_its_tree(self):
        class NoDeepCopy(dict):
            def __deepcopy__(self, memo):
                raise AssertionError("Dense result must not be deep-copied before externalization")
        result = NoDeepCopy(analysis_id="dense", scalar_fields={"voltage_v": list(range(100_000))})
        payload = {"analyses": {"latest_result": result, "history": [{"bundle": result} for _ in range(30)]}}
        from python.spike_core.project_state_artifacts import _json_bytes
        with patch("python.spike_core.project_state_artifacts._json_bytes", wraps=_json_bytes) as encode:
            externalized, artifacts = externalize_result_state(payload)
        self.assertEqual(encode.call_count, 1)
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(json.loads(next(iter(artifacts.values()))), result)
        self.assertIs(payload["analyses"]["latest_result"], result)
        externalized["analyses"]["latest_result"]["bytes"] = 0
        self.assertGreater(externalized["analyses"]["history"][0]["bundle"]["bytes"], 0)

    def test_all_result_history_and_future_fields_round_trip_without_metadata_duplication(self):
        payload = fixtures.ProjectPackageV3Tests().payload()
        results = [{"analysis_id": f"run-{i}", "mode": "transient", "scalar_fields": {"voltage_v": [{"value": i}]},
                    "time_series": {"times_s": [0, 1], "frames": [{"new_field": [i, i + 1]}]},
                    "future_engine_output": {"units": "mm", "custom": [i]}} for i in range(25)]
        analysis = {"latest_result": results[-1], "result_history": [
            {"id": item["analysis_id"], "label": item["analysis_id"], "bundle": item} for item in results]}
        payload["analyses"] = analysis
        payload["extensions"] = {"legacy": {"analysis": copy.deepcopy(analysis), "future_setup": {"opaque": "retained"}}}
        externalized, artifacts = externalize_result_state(payload)
        self.assertEqual(len(artifacts), 25, "latest result and duplicate legacy snapshot must share artifacts")
        self.assertEqual(externalized["analyses"]["latest_result"]["contract"], STATE_REFERENCE)
        self.assertEqual(len(externalized["analyses"]["result_history"]), 25)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.spike"
            manifest = write_spike_package(path, externalized, preserved_members=artifacts)
            opened = read_spike_package(path)
            restored = hydrate_result_state(opened.payload, path, manifest["manifest_payload_sha256"])
        self.assertEqual(restored["analyses"], analysis)
        self.assertEqual(restored["extensions"], payload["extensions"])

    def test_state_read_rejects_stale_identity_wrong_hash_and_wrong_prefix(self):
        payload = fixtures.ProjectPackageV3Tests().payload()
        payload["analyses"] = {"latest_result": {"analysis_id": "A", "outputs": {"mesh": [1, 2, 3]}}}
        externalized, artifacts = externalize_result_state(payload)
        reference = externalized["analyses"]["latest_result"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.spike"
            manifest = write_spike_package(path, externalized, preserved_members=artifacts)
            for changed, digest, prefix in [
                (reference, "0" * 64, "state/artifacts/"),
                ({**reference, "sha256": "0" * 64}, manifest["manifest_payload_sha256"], "state/artifacts/"),
                (reference, manifest["manifest_payload_sha256"], "visuals/artifacts/"),
            ]:
                with self.assertRaises(ProjectPackageError):
                    read_verified_artifacts(path, [changed], expected_manifest_payload_sha256=digest, allowed_prefix=prefix)

    def test_visuals_restore_without_source_files_and_keep_native_copper_mode(self):
        def artifact(role, data):
            return {"role": role, "media_type": "image/svg+xml" if role.startswith("layer:") else "model/gltf-binary",
                    "bytes": len(data), "sha256": _sha256(data), "artifact_base64": base64.b64encode(data).decode()}
        raw = {"contract": "spike/saved-board-visuals/v1", "board_includes_copper": False,
               "view_box": [0, 0, 40, 20], "quality": {"missing_references": ["F1"]},
               "artifacts": [artifact("board", glb_bytes()), artifact("components", glb_bytes()),
                             artifact("layer:In2.Cu", b'<svg viewBox="0 0 40 20"/>')]}
        index, artifacts = prepare_visual_artifacts(raw, "1" * 64)
        self.assertEqual(len(artifacts), 2, "identical bytes must be deduplicated even across visual roles")
        payload = fixtures.ProjectPackageV3Tests().payload()
        payload["extensions"] = {"board_visuals": index}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "visuals.spike"
            manifest = write_spike_package(path, payload, preserved_members=artifacts)
            for stage in ("layout", "board", "components"):
                restored = read_saved_visual_stage(path, index, stage, manifest["manifest_payload_sha256"])
                self.assertFalse(restored["quality"]["board_includes_copper"])
                self.assertEqual(restored["layout"]["view_box"], [0, 0, 40, 20])
                self.assertEqual(set(restored["scenes"]), set() if stage == "layout" else {stage})
                self.assertEqual(len(restored["layout"]["layers"]), 1 if stage == "layout" else 0)
        damaged = copy.deepcopy(raw)
        damaged["artifacts"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ProjectPackageError, "SHA-256"):
            prepare_visual_artifacts(damaged, "1" * 64)
