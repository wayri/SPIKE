# SPDX-License-Identifier: Apache-2.0
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.spikes_native_adapter import (
    SpikesNativeAdapterError,
    capability_manifest,
    map_result_bundle,
    prepare_job_envelope,
    probe_runtime_capabilities,
    resolve_runtime_executable,
)


class SpikesNativeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.design = DesignIR(design_id="design-1")
        self.spec = AnalysisSpec(
            analysis_id="analysis-1",
            options={"native_study": {"type": "stationary"}},
        )
        self.artifact = {"path": "model.json", "sha256": "a" * 64, "bytes": 100}

    def test_manifest_remains_integration_pending(self):
        manifest = capability_manifest()
        self.assertEqual(manifest["capabilities"], ["probe", "self_test"])
        self.assertEqual(manifest["status"], "integration_pending")
        self.assertEqual(manifest["physics"], [])
        self.assertIn("reference_diffusion_fem_2d_verification", manifest["verification_capabilities"])
        self.assertIn(
            "prepared_frequency_domain_maxwell_compact_verification",
            manifest["verification_capabilities"],
        )
        self.assertIn(
            "prepared_modal_dtn_operator_sweep_verification",
            manifest["verification_capabilities"],
        )

    def test_runtime_resolution_does_not_embed_a_development_checkout(self):
        with patch.dict("os.environ", {}, clear=True), patch("shutil.which", return_value=None):
            self.assertEqual(resolve_runtime_executable(), "")

    def test_runtime_probe_preserves_verification_only_boundary(self):
        payload = (
            b'{"abi_version":1,"backends":{"reference":true},'
            b'"capabilities":["probe","reference_diffusion_fem_2d_verification"],'
            b'"contracts":["spike/solver-job/v1","spike/mesh-tri/v1"],'
            b'"contract":"spike/native-capability/v1","engine":"spike-native-solver",'
            b'"engine_version":"0.0.1-m0","execution":["serial_reference"],'
            b'"index_type":"int64","limitations":["No product physics is validated."],'
            b'"scalar_type":"real64","validation_state":"verification_only"}'
        )

        class Completed:
            returncode = 0

        def fake_run(_command, **kwargs):
            kwargs["stdout"].write(payload)
            return Completed()

        with patch(
            "python.spike_core.spikes_native_adapter.resolve_runtime_executable",
            return_value=str(Path(__file__).resolve()),
        ), patch("python.spike_core.spikes_native_adapter.subprocess.run", side_effect=fake_run):
            result = probe_runtime_capabilities()
        self.assertEqual(result["status"], "available")
        self.assertFalse(result["product_physics_eligible"])
        self.assertEqual(result["manifest"]["validation_state"], "verification_only")

    def test_runtime_probe_validates_prepared_capability_and_build_identity(self):
        payload = (
            b'{"abi_version":1,"backends":{"reference":true},'
            b'"build_identity":{"external_backends_qualified":false},'
            b'"capabilities":["probe"],"contracts":["spike/solver-job/v1"],'
            b'"contract":"spike/native-capability/v1","engine":"spike-native-solver",'
            b'"engine_version":"0.0.1-m0","execution":["serial_reference"],'
            b'"index_type":"int64","limitations":[],"mpi":"none",'
            b'"prepared_capabilities":["prepared_frequency_domain_maxwell_compact_verification"],'
            b'"scalar_type":"real64","validation_state":"verification_only"}'
        )

        class Completed:
            returncode = 0

        def fake_run(_command, **kwargs):
            kwargs["stdout"].write(payload)
            return Completed()

        with patch(
            "python.spike_core.spikes_native_adapter.resolve_runtime_executable",
            return_value=str(Path(__file__).resolve()),
        ), patch("python.spike_core.spikes_native_adapter.subprocess.run", side_effect=fake_run):
            result = probe_runtime_capabilities()
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["manifest"]["mpi"], "none")

        duplicate = payload.replace(
            b'"prepared_frequency_domain_maxwell_compact_verification"]',
            b'"prepared_frequency_domain_maxwell_compact_verification",'
            b'"prepared_frequency_domain_maxwell_compact_verification"]',
        )

        def fake_duplicate(_command, **kwargs):
            kwargs["stdout"].write(duplicate)
            return Completed()

        with patch(
            "python.spike_core.spikes_native_adapter.resolve_runtime_executable",
            return_value=str(Path(__file__).resolve()),
        ), patch("python.spike_core.spikes_native_adapter.subprocess.run", side_effect=fake_duplicate):
            rejected = probe_runtime_capabilities()
        self.assertEqual(rejected["status"], "incompatible")

    def test_runtime_probe_rejects_duplicate_json_keys(self):
        payload = b'{"contract":"spike/native-capability/v1","contract":"duplicate"}'

        class Completed:
            returncode = 0

        def fake_run(_command, **kwargs):
            kwargs["stdout"].write(payload)
            return Completed()

        with patch(
            "python.spike_core.spikes_native_adapter.resolve_runtime_executable",
            return_value=str(Path(__file__).resolve()),
        ), patch("python.spike_core.spikes_native_adapter.subprocess.run", side_effect=fake_run):
            result = probe_runtime_capabilities()
        self.assertEqual(result["status"], "incompatible")
        self.assertFalse(result["product_physics_eligible"])

    def test_job_mapping_is_bounded_and_integrity_bound(self):
        job = prepare_job_envelope(self.design, self.spec, self.artifact, request_id="job-1")
        self.assertEqual(job["contract"], "spike/solver-job/v1")
        self.assertEqual(job["model"], self.artifact)
        self.assertNotIn("adapter_context", job)

    def test_traversal_and_bad_digest_are_rejected(self):
        with self.assertRaises(SpikesNativeAdapterError):
            prepare_job_envelope(self.design, self.spec, {**self.artifact, "path": "../model.json"}, request_id="job-1")
        with self.assertRaises(SpikesNativeAdapterError):
            prepare_job_envelope(self.design, self.spec, {**self.artifact, "sha256": "bad"}, request_id="job-1")

    def test_frequency_domain_prepared_model_can_be_mapped(self):
        self.spec.options["native_study"] = {"type": "frequency_domain"}
        job = prepare_job_envelope(self.design, self.spec, self.artifact, request_id="job-frequency")
        self.assertEqual(job["study"], {"type": "frequency_domain"})
        self.assertEqual(job["model"], self.artifact)
        self.assertEqual(capability_manifest()["physics"], [])

    def test_frequency_domain_cannot_override_bound_model_inputs(self):
        for key, value in (("frequency_hz", 1e9), ("ports", []), ("integrator", "bdf2"),
                           ("time_step", .1), ("steps", 1), ("executable", "solver.exe")):
            self.spec.options["native_study"] = {"type": "frequency_domain", key: value}
            with self.subTest(key=key), self.assertRaises(SpikesNativeAdapterError):
                prepare_job_envelope(self.design, self.spec, self.artifact, request_id="job-frequency")

    def test_frequency_domain_result_stays_verification_only(self):
        result = map_result_bundle({"contract": "spike/result-bundle/v2", "status": "completed",
            "validation_state": "verification_only", "summary": {"frequency_count": 2}, "issues": []}, self.spec)
        self.assertEqual(result.model_status, "verification_only")

    def test_result_mapping_drops_unbounded_fields(self):
        mapped = map_result_bundle({
            "contract": "spike/result-bundle/v2",
            "status": "completed",
            "validation_state": "verification_only",
            "summary": {"l2_error": 1e-8, "nested": {"unsafe": "payload"}},
            "fields": {"large": [1, 2, 3]},
            "issues": [],
            "provenance": {"backend": "reference"},
        }, self.spec)
        self.assertEqual(mapped.summary, {"l2_error": 1e-8})
        self.assertEqual(mapped.fields, {})
        self.assertEqual(mapped.model_status, "verification_only")


if __name__ == "__main__":
    unittest.main()
