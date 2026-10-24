# SPDX-License-Identifier: Apache-2.0
"""Final-payload integrity and launch admission without executing a solver."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from python.spike_core.circuit_worker_supervisor import SupervisionResult
from scripts import verify_unix_release_payload as verifier


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(root):
    bundled = root / "bundled"
    worker = bundled / "spike-worker"
    circuit = bundled / "spike-circuit-worker"
    worker.mkdir(parents=True)
    (circuit / "_internal/spikes").mkdir(parents=True)
    suffix = ".exe" if os.name == "nt" else ""
    (worker / ("spike-worker" + suffix)).write_bytes(b"original main worker fixture")
    (circuit / ("spike-circuit-worker" + suffix)).write_bytes(b"original circuit worker fixture")
    (circuit / "_internal/spikes" / verifier._library_name()).write_bytes(b"original library fixture")
    def inventory(folder, size_key):
        return [{"path": path.relative_to(folder).as_posix(), size_key: path.stat().st_size,
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for path in folder.rglob("*") if path.is_file()]
    main = {"contract": "spike/packaged-worker-manifest/v2", "worker_version": "0.4.1",
            "python": "3.12.9", "pyinstaller": "6.21.0", "machine": "fixture-architecture",
            "files": inventory(worker, "size"),
            "benchmark_summary": {"total": 15, "passed": 15, "failed": 0},
            "runtime_qualification": {"status": "passed", "summary": {"total": 8, "passed": 8, "failed": 0}},
            "geometry_arrow_probe": {"contract": "spike/packaged-arrow-probe/v1", "status": "passed",
                "table_contract": "spike/copper-geometry-arrow/v4", "rows": 4,
                "retained_unresolved_occurrences": 1, "artifact_sha256": "a"*64, "design_id": "fixture"}}
    auxiliary = {"contract": "spike/owned-spice-process-package/v1", "product_qualified": False,
                 "files": inventory(circuit, "bytes"), "capability": {
                     "engine": "spike-circuit-worker", "validation_state": "experimental",
                     "structured_workspace_only": True, "raw_netlist_accepted": False,
                     "shell_invoked": False, "trusted_host_supervision_required": True,
                     "binary_and_library_sha256_admission": True}}
    write_json(bundled / "spike-worker.manifest.json", main)
    write_json(bundled / "spike-circuit-worker.manifest.json", auxiliary)
    return bundled, main, auxiliary


def smoke(**kwargs):
    write_json(kwargs["job_root"] / kwargs["result"], {
        "contract": "spike/owned-spice-process-result/v1", "status": "completed",
        "validation_state": "experimental", "circuit": {"status": "completed"}})
    return SupervisionResult("completed", 0, .01, "mock-test-only")


class UnixReleasePayloadTests(unittest.TestCase):
    def test_intact_payload_runs_admitted_supervisor_and_report_has_no_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundled, _, _ = fixture(root)
            before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            with patch.object(verifier, "run_circuit_worker", side_effect=smoke) as run:
                result = verifier.verify(root)
            run.assert_called_once()
            self.assertEqual(run.call_args.kwargs["worker_executable"].parent, (bundled / "spike-circuit-worker").resolve(strict=True))
            self.assertEqual(run.call_args.kwargs["library_sha256"], result["circuit_library_sha256"])
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["versions"]["worker_version"], "0.4.1")
            self.assertNotIn(str(root), json.dumps(result))
            self.assertEqual(before, {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()})

    def test_tampered_missing_and_extra_payload_members_reject_before_execution(self):
        for modification in ("worker", "library", "missing", "extra"):
            with self.subTest(modification=modification), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                bundled, main, _ = fixture(root)
                if modification == "worker":
                    (bundled / "spike-worker" / main["files"][0]["path"]).write_bytes(b"modified by signing")
                elif modification == "library":
                    (bundled / "spike-circuit-worker/_internal/spikes" / verifier._library_name()).write_bytes(b"tampered")
                elif modification == "missing":
                    (bundled / "spike-circuit-worker/_internal/spikes" / verifier._library_name()).unlink()
                else:
                    (bundled / "spike-circuit-worker/unrecorded.txt").write_text("extra")
                with patch.object(verifier, "run_circuit_worker") as run, self.assertRaises(ValueError):
                    verifier.verify(root)
                run.assert_not_called()

    def test_failed_authoritative_worker_check_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundled, main, _ = fixture(root)
            main["benchmark_summary"]["failed"] = 1
            write_json(bundled / "spike-worker.manifest.json", main)
            with patch.object(verifier, "run_circuit_worker") as run, self.assertRaisesRegex(ValueError, "acceptance"):
                verifier.verify(root)
            run.assert_not_called()

    def test_supervisor_failure_and_post_probe_mutation_fail_closed(self):
        for modification in ("timeout", "mutation"):
            with self.subTest(modification=modification), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                bundled, main, _ = fixture(root)
                def failure(**kwargs):
                    if modification == "timeout":
                        return SupervisionResult("timeout", -1, 30, "mock-test-only")
                    outcome = smoke(**kwargs)
                    (bundled / "spike-worker" / main["files"][0]["path"]).write_bytes(b"changed during probe")
                    return outcome
                with patch.object(verifier, "run_circuit_worker", side_effect=failure), self.assertRaises(ValueError):
                    verifier.verify(root)

    def test_packaging_checks_final_signed_and_assembled_payload(self):
        source = (verifier.ROOT / "scripts/package_unix_release.py").read_text(encoding="utf-8")
        mac = source.index("run('python', 'scripts/verify_unix_release_payload.py'")
        self.assertLess(source.index("run('codesign', '--verify'"), mac)
        self.assertLess(mac, source.index("run('hdiutil', 'create'"))
        linux = source.index("run('python', 'scripts/verify_unix_release_payload.py'", mac + 1)
        self.assertLess(source.index("run('flatpak', 'build-finish'"), linux)
        self.assertLess(linux, source.index("run('flatpak', 'build-export'"))


if __name__ == "__main__":
    unittest.main()
