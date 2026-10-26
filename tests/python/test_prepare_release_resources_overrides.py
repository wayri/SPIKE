# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.prepare_release_resources import prepare


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PrepareReleaseResourceOverrideTests(unittest.TestCase):
    def repository(self, directory):
        root = Path(directory)
        config = root / "app/src-tauri/tauri.conf.json"
        source = root / "python"
        worker = root / "app/src-tauri/resources/worker"
        source.mkdir(parents=True)
        worker.mkdir(parents=True)
        config.parent.mkdir(parents=True, exist_ok=True)
        (source / "owned.py").write_text("owned = True\n", encoding="utf-8")
        (worker / "README.md").write_text("retained ancillary worker resource\n", encoding="utf-8")
        current = worker / "spike-worker"
        current.mkdir()
        executable = "spike-worker.exe" if os.name == "nt" else "spike-worker"
        (current / executable).write_bytes(b"current-worker")
        config.write_text(json.dumps({
            "identifier": "org.spike.desktop",
            "bundle": {"resources": {
                "../../python": "python",
                "resources/worker": "bundled",
            }},
        }, indent=2)+"\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "python/owned.py", "app/src-tauri/tauri.conf.json"],
                       cwd=root, check=True)
        return root, config, worker, executable

    def candidate(self, root, executable):
        package = root / "build/reviewed-worker"
        artifact = package / "spike-worker"
        artifact.mkdir(parents=True)
        binary = artifact / executable
        support = artifact / "runtime.dat"
        binary.write_bytes(b"reviewed-candidate-worker")
        support.write_bytes(b"reviewed-runtime")
        report_relative = Path("evidence/release-runtime-qualification.json")
        report = package / report_relative
        report.parent.mkdir()
        report.write_text(
            json.dumps({"status": "passed"}), encoding="utf-8")
        manifest = {
            "contract": "spike/packaged-worker-manifest/v2",
            "worker_version": "candidate",
            "benchmark_summary": {"total": 15, "passed": 15, "failed": 0},
            "runtime_qualification": {"status": "passed",
                                      "summary": {"total": 8, "passed": 8, "failed": 0},
                                      "report": report_relative.as_posix()},
            "geometry_arrow_probe": {
                "contract": "spike/packaged-arrow-probe/v1", "status": "passed",
                "table_contract": "spike/copper-geometry-arrow/v4", "rows": 4,
                "artifact_sha256": "a"*64, "design_id": "release-fixture",
                "retained_unresolved_occurrences": 1,
            },
            "files": [{"path": path.name, "size": path.stat().st_size,
                       "sha256": digest(path)} for path in (binary, support)],
        }
        manifest_path = package / "spike-worker.manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
        return package, artifact, manifest_path, report_relative

    def test_fresh_custom_stage_uses_verified_override_and_relative_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root, config, current, executable = self.repository(directory)
            package, artifact, manifest, report_relative = self.candidate(root, executable)
            original_config = config.read_text(encoding="utf-8")
            current_bytes = (current / "spike-worker" / executable).read_bytes()
            stage = root / "build/stages/cfd-cht-candidate"
            output = root / "build/tauri.cfd-cht.json"
            self.assertEqual(prepare(root, output, stage_root=stage, worker_root=artifact), output)
            self.assertEqual(config.read_text(encoding="utf-8"), original_config)
            self.assertEqual((current / "spike-worker" / executable).read_bytes(), current_bytes)
            self.assertEqual((stage / "bundled/spike-worker" / executable).read_bytes(),
                             b"reviewed-candidate-worker")
            self.assertEqual((stage / "bundled/spike-worker.manifest.json").read_bytes(),
                             manifest.read_bytes())
            self.assertEqual((stage / "bundled" / report_relative).read_text(
                encoding="utf-8"), (package / report_relative).read_text(
                    encoding="utf-8"))
            self.assertFalse((stage / "bundled" / report_relative.name).exists())
            self.assertTrue((stage / "bundled/README.md").is_file())
            self.assertTrue((stage / "python/owned.py").is_file())
            resources = json.loads(output.read_text(encoding="utf-8"))["bundle"]["resources"]
            self.assertEqual(resources, {"../../build/stages/cfd-cht-candidate/": "./"})

    def test_custom_stage_must_be_fresh_and_strictly_under_build_without_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _, _ = self.repository(directory)
            existing = root / "build/existing-stage"
            existing.mkdir(parents=True)
            sentinel = existing / "preserve.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "must be fresh"):
                prepare(root, root / "build/config.json", stage_root=existing)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")

            outside = root / "caller-directory"
            outside.mkdir()
            outside_sentinel = outside / "preserve.txt"
            outside_sentinel.write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "strictly under"):
                prepare(root, root / "build/config.json", stage_root=outside)
            self.assertEqual(outside_sentinel.read_text(encoding="utf-8"), "preserve")
            with self.assertRaisesRegex(RuntimeError, "strictly under"):
                prepare(root, root / "build/config.json", stage_root=root / "build")

    def test_tampered_worker_is_rejected_before_custom_stage_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _, executable = self.repository(directory)
            _, artifact, _, _ = self.candidate(root, executable)
            (artifact / executable).write_bytes(b"tampered-after-manifest")
            stage = root / "build/stages/rejected"
            with self.assertRaisesRegex(RuntimeError, "member_integrity"):
                prepare(root, root / "build/rejected.json", stage_root=stage,
                        worker_root=artifact)
            self.assertFalse(stage.exists())

    def test_copy_corruption_is_rejected_before_config_emission(self):
        with tempfile.TemporaryDirectory() as directory:
            root, config, current, executable = self.repository(directory)
            _, artifact, _, _ = self.candidate(root, executable)
            stage = root / "build/stages/corrupted-copy"
            output = root / "build/corrupted-copy.json"
            original_copytree = shutil.copytree

            def corrupt_copy(source, target, *args, **kwargs):
                result = original_copytree(source, target, *args, **kwargs)
                if Path(source).resolve() == artifact.resolve():
                    (Path(target) / executable).write_bytes(b"corrupted-during-copy")
                return result

            with patch("scripts.prepare_release_resources.shutil.copytree",
                       side_effect=corrupt_copy):
                with self.assertRaisesRegex(RuntimeError, "member_integrity"):
                    prepare(root, output, stage_root=stage, worker_root=artifact)
            self.assertFalse(output.exists(), "configuration must not publish a corrupted stage")
            self.assertTrue(stage.exists(), "failed custom stages are not silently deleted")
            self.assertEqual((current / "spike-worker" / executable).read_bytes(),
                             b"current-worker")
            self.assertTrue(config.is_file())


if __name__ == "__main__":
    unittest.main()
