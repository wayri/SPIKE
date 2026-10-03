# SPDX-License-Identifier: Apache-2.0
"""Git worktree inventory tests for the integrated Python workspace."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.script_workspace_files import (
    GIT_WORKTREE_TIMEOUT_SECONDS,
    MAX_GIT_OUTPUT_BYTES,
    python_workspace_files,
)


class ScriptWorkspaceWorktreesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def call(self, root: Path) -> dict[str, object]:
        return python_workspace_files({"root": str(root), "action": "worktrees"})

    def git(self, *arguments: str, cwd: Path) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *arguments], cwd=cwd, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    @unittest.skipUnless(shutil.which("git"), "Git is required for the integration check.")
    def test_real_repository_lists_main_and_linked_worktree(self):
        repository = self.base / "repository with spaces"
        repository.mkdir()
        self.git("init", "-b", "main", cwd=repository)
        self.git("-c", "user.name=SPIKE Test", "-c", "user.email=spike@example.invalid",
                 "commit", "--allow-empty", "-m", "initial", cwd=repository)
        linked = self.base / "linked worktree"
        self.git("worktree", "add", "-b", "feature/worktree-test", str(linked), cwd=repository)

        result = self.call(repository)

        self.assertEqual(result["contract"], "spike/python-workspace-files/v1")
        self.assertTrue(result["available"])
        by_path = {entry["path"]: entry for entry in result["worktrees"]}
        self.assertEqual(set(by_path), {str(repository.resolve()), str(linked.resolve())})
        self.assertEqual(by_path[str(repository.resolve())]["branch"], "refs/heads/main")
        self.assertEqual(by_path[str(linked.resolve())]["branch"], "refs/heads/feature/worktree-test")
        self.assertRegex(by_path[str(linked.resolve())]["head"], r"^[0-9a-f]{40,64}$")

    def test_non_repository_is_reported_as_unavailable(self):
        result = self.call(self.base)

        self.assertFalse(result["available"])
        self.assertEqual(result["worktrees"], [])
        self.assertIn("not an available Git worktree", result["message"])

    def test_porcelain_z_preserves_spaces_and_newlines_and_flags(self):
        first = self.base / "tree with spaces"
        second = self.base / "tree\nwith newline"
        output = (
            b"worktree " + str(first).encode() + b"\0"
            + b"HEAD " + b"a" * 40 + b"\0"
            + b"branch refs/heads/topic\0locked maintenance\0\0"
            + b"worktree " + str(second).encode() + b"\0"
            + b"HEAD " + b"B" * 40 + b"\0detached\0prunable metadata missing\0\0"
        )
        completed = subprocess.CompletedProcess([], 0, stdout=output, stderr=b"")

        with (
            patch("python.spike_core.script_workspace_files.subprocess.run", return_value=completed) as run,
            patch(
                "python.spike_core.script_workspace_files._validated_worktree_path",
                side_effect=lambda value: Path(value),
            ),
        ):
            result = self.call(self.base)

        self.assertEqual([item["path"] for item in result["worktrees"]], [
            str(first), str(second),
        ])
        self.assertEqual(result["worktrees"][0]["branch"], "refs/heads/topic")
        self.assertTrue(result["worktrees"][0]["locked"])
        self.assertTrue(result["worktrees"][1]["detached"])
        self.assertTrue(result["worktrees"][1]["prunable"])
        self.assertEqual(result["worktrees"][1]["head"], "b" * 40)
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[-3:], ["list", "--porcelain", "-z"])
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(run.call_args.kwargs["timeout"], GIT_WORKTREE_TIMEOUT_SECONDS)
        self.assertEqual(run.call_args.kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")

    def test_missing_git_and_timeout_are_graceful(self):
        with patch("python.spike_core.script_workspace_files.subprocess.run", side_effect=FileNotFoundError):
            missing = self.call(self.base)
        with patch(
            "python.spike_core.script_workspace_files.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["git"], GIT_WORKTREE_TIMEOUT_SECONDS),
        ):
            timed_out = self.call(self.base)

        self.assertFalse(missing["available"])
        self.assertIn("not available", missing["message"])
        self.assertFalse(timed_out["available"])
        self.assertIn("timed out", timed_out["message"])

    def test_inventory_rejects_unbounded_output(self):
        completed = subprocess.CompletedProcess(
            [], 0, stdout=b"x" * (MAX_GIT_OUTPUT_BYTES + 1), stderr=b"",
        )
        with patch("python.spike_core.script_workspace_files.subprocess.run", return_value=completed):
            result = self.call(self.base)

        self.assertFalse(result["available"])
        self.assertEqual(result["worktrees"], [])
        self.assertIn("output limit", result["message"])


if __name__ == "__main__":
    unittest.main()
