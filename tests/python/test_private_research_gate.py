# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.check_private_research import private_paths


ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check_private_research.py"


class PrivateResearchGateTests(unittest.TestCase):
    def git(self, repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repository), *args], text=True,
            capture_output=True, check=True,
        )

    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        fixture_root = ROOT / "build" / "private-research-gate-tests"
        fixture_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(
            prefix="spike-private-gate-", dir=fixture_root,
        )
        repository = Path(temporary.name)
        self.git(repository, "init", "-q")
        self.git(repository, "config", "user.name", "SPIKE Test")
        self.git(repository, "config", "user.email", "spike-test@example.invalid")
        (repository / ".gitignore").write_text("/src/optics/\n", encoding="utf-8")
        public = repository / "extensions" / "optycal_suite" / "study.py"
        public.parent.mkdir(parents=True)
        public.write_text("PUBLIC = True\n", encoding="utf-8")
        self.git(repository, "add", ".gitignore", "extensions/optycal_suite/study.py")
        self.git(repository, "commit", "-qm", "public fixture")
        return temporary, repository

    def run_gate(self, repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GATE), "--repo", str(repository), *args],
            text=True, capture_output=True, check=False,
        )

    def test_public_optycal_is_allowed_and_ignored_local_research_is_allowed(self):
        temporary, repository = self.fixture()
        self.addCleanup(temporary.cleanup)
        private = repository / "src" / "optics" / "planar_reference.cpp"
        private.parent.mkdir(parents=True)
        private.write_text("private\n", encoding="utf-8")
        result = self.run_gate(repository)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("passed", result.stdout)

    def test_force_added_private_source_is_rejected(self):
        temporary, repository = self.fixture()
        self.addCleanup(temporary.cleanup)
        private = repository / "src" / "optics" / "planar_reference.cpp"
        private.parent.mkdir(parents=True)
        private.write_text("private\n", encoding="utf-8")
        self.git(repository, "add", "-f", "src/optics/planar_reference.cpp")
        result = self.run_gate(repository)
        self.assertEqual(result.returncode, 1)
        self.assertIn("src/optics/planar_reference.cpp", result.stderr)

    def test_committed_private_plan_remains_rejected(self):
        temporary, repository = self.fixture()
        self.addCleanup(temporary.cleanup)
        plan = repository / "docs" / "CHARGED_PARTICLE_VACUUM_PLAN.md"
        plan.parent.mkdir(parents=True)
        plan.write_text("private\n", encoding="utf-8")
        self.git(repository, "add", "-f", "docs/CHARGED_PARTICLE_VACUUM_PLAN.md")
        self.git(repository, "commit", "-qm", "force private plan")
        result = self.run_gate(repository)
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/CHARGED_PARTICLE_VACUUM_PLAN.md", result.stderr)

    def test_release_file_listing_is_checked(self):
        temporary, repository = self.fixture()
        self.addCleanup(temporary.cleanup)
        listing = repository / "archive-files.txt"
        listing.write_text(
            "extensions/optycal_suite/study.py\n"
            "docs/solvers/reference-physics/README.md\n",
            encoding="utf-8",
        )
        result = self.run_gate(repository, "--paths-from", str(listing))
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/solvers/reference-physics/README.md", result.stderr)

    def test_electron_optics_names_are_private_without_matching_optycal(self):
        blocked = private_paths([
            "python/spike_core/electron_optics_raytrace.py",
            "docs/validation/NEW_ELECTRON_OPTICS_REFERENCE.md",
            "examples/optycal/study.py",
        ])
        self.assertEqual(blocked, [
            "docs/validation/NEW_ELECTRON_OPTICS_REFERENCE.md",
            "python/spike_core/electron_optics_raytrace.py",
        ])

    def test_grouped_research_is_private(self):
        names = [
            "src/solvers/optics/reference.cpp",
            "src/solvers/particles/reference.cpp",
            "python/spike_core/solvers/electron_optics/trajectory.py",
            "src/Solvers/Optics/Reference.cpp",
        ]
        self.assertEqual(private_paths(names), sorted(names))

    def test_exported_manifest_cannot_bypass_resource_gate(self):
        import json
        from scripts.prepare_release_resources import prepare

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "RELEASE_SOURCE_MANIFEST.json").write_text(json.dumps({
                "files": [{"path": "src/optics/private.cpp"}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Unpublished research"):
                prepare(root)

    def test_dirty_tree_freezer_blocks_ignored_grouped_research(self):
        from scripts import build_packaged_worker

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "python/spike_core/solvers/particles/reference.py"
            source.parent.mkdir(parents=True)
            source.write_text("PRIVATE = True\n", encoding="utf-8")
            with patch.object(build_packaged_worker, "ROOT", root), \
                 patch.object(build_packaged_worker, "_require_pyinstaller") as freezer:
                with self.assertRaisesRegex(RuntimeError, "Unpublished research"):
                    build_packaged_worker.build()
                freezer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
