# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Build-input and command tests; these do not execute a frozen worker."""
import os
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_packaged_worker as builder


class NativeKernelPackagingTests(unittest.TestCase):
    def kernels(self, root):
        suffix = ".exe" if os.name == "nt" else ""
        paths = tuple(root / (name + suffix) for name in
                      ("spike_native_airflow", "spike_native_cht"))
        for path in paths:
            path.write_bytes(b"test input, not an executable")
        return paths

    def test_explicit_directory_requires_both_without_default_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.kernels(root)
            self.assertEqual(builder._native_kernels(root), tuple(p.resolve() for p in paths))
            paths[1].unlink()
            with self.assertRaisesRegex(RuntimeError, "spike_native_cht"):
                builder._native_kernels(root)

    def test_missing_kernel_fails_before_replacing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(builder, "_require_pyinstaller", return_value="test"), \
                    patch.object(builder, "_native_extension"), \
                    patch.object(builder, "_spikes_library"), \
                    patch.object(builder, "_remove_managed_tree") as remove:
                with self.assertRaisesRegex(RuntimeError, "Native airflow/CHT"):
                    builder.build(native_kernel_dir=Path(directory))
                remove.assert_not_called()

    def test_freezer_command_collects_both_kernels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernels = self.kernels(root)
            resources = root / "resources"
            worker = resources / "spike-worker" / ("spike-worker.exe" if os.name == "nt" else "spike-worker")
            def freeze(command, **kwargs):
                worker.parent.mkdir(parents=True)
                worker.write_bytes(b"mock freezer output")
            with patch.object(builder, "RESOURCE_ROOT", resources), \
                    patch.object(builder, "BUILD_ROOT", root / "work"), \
                    patch.object(builder, "_require_pyinstaller", return_value="test"), \
                    patch.object(builder, "_native_extension", return_value=root / "binding"), \
                    patch.object(builder, "_spikes_library", return_value=root / "engine"), \
                    patch.object(builder.shutil, "copytree"), \
                    patch.object(builder.subprocess, "run", side_effect=freeze) as run, \
                    patch.object(builder, "_verify", return_value=({}, {}, {}, {}, {})), \
                    patch.object(builder, "_write_runtime_qualification"), \
                    patch.object(builder, "_write_manifest", return_value=root / "manifest.json"):
                builder.build(keep_work=True, native_kernel_dir=root)
                command = run.call_args.args[0]
            for binary in kernels:
                token = f"{binary.resolve()}{os.pathsep}native"
                self.assertEqual(command.count(token), 1)
                self.assertEqual(command[command.index(token)-1], "--add-binary")

    def test_cleanup_tree_inputs_reject_without_deleting_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources, scratch = root / "resources", root / "work"
            artifact = resources / "spike-worker"
            artifact.mkdir(parents=True)
            sentinel = artifact / "retained-input.txt"
            sentinel.write_text("retained", encoding="utf-8")
            for kernel_dir in (artifact / "_internal/native", scratch / "kernels"):
                kernel_dir.mkdir(parents=True)
                self.kernels(kernel_dir)
                with self.subTest(kernel_dir=kernel_dir), \
                        patch.object(builder, "RESOURCE_ROOT", resources), \
                        patch.object(builder, "BUILD_ROOT", scratch), \
                        patch.object(builder, "_require_pyinstaller", return_value="test"), \
                        patch.object(builder, "_native_extension"), \
                        patch.object(builder, "_spikes_library"), \
                        patch.object(builder, "_remove_managed_tree") as remove:
                    with self.assertRaisesRegex(RuntimeError, "outside worker output"):
                        builder.build(native_kernel_dir=kernel_dir)
                    remove.assert_not_called()
                    self.assertEqual(sentinel.read_text(encoding="utf-8"), "retained")
                    self.assertTrue(all(p.is_file() for p in builder._native_kernels(kernel_dir)))

    def test_cli_forwards_explicit_directory(self):
        with patch.object(builder.sys, "argv", ["builder", "--native-kernel-dir", "chosen"]), \
                patch.object(builder, "build", return_value=(Path("worker"), Path("manifest"))) as build:
            self.assertEqual(builder.main(), 0)
            build.assert_called_once_with(keep_work=False, native_kernel_dir=Path("chosen"))

    def test_native_cht_probe_failure_cannot_be_omitted_or_swallowed(self):
        self._assert_probe_required("scripts.verify_native_cht_runtime.verify_native_cht_runtime")

    def test_moving_lid_probe_failure_cannot_be_omitted_or_swallowed(self):
        self._assert_probe_required("scripts.verify_native_momentum_runtime.verify_native_momentum_runtime")

    def _assert_probe_required(self, target):
        worker = Path("mock-artifact/spike-worker.exe").resolve()
        snapshot = {"health": {"status": "ready"}, "solver_plugins": [
            {"id": "spike.peec_2_5d", "state": "available"}],
            "benchmarks": {"status": "passed", "summary": {"failed": 0, "skipped": 0}}}
        def request(executable, method, params=None):
            if method == "cfd_capabilities":
                return {"result": {"engines": {"spike.native_cavity": {
                    "available": True, "executable": str(worker.parent / "_internal/native/airflow")}}}}
            return {"result": {"status": "converged", "production_qualified": False}}
        with ExitStack() as stack:
            for name, value in (("collect_runtime_snapshot", snapshot),
                                ("qualify_runtime_snapshots", {"status": "passed"}),
                                ("_verify_geometry_arrow_package", {}),
                                ("_verify_spikes_engine", {})):
                stack.enter_context(patch.object(builder, name, return_value=value))
            stack.enter_context(patch.object(builder, "_request", side_effect=request))
            for target in ("scripts.verify_packaged_schema_catalog.verify_packaged_schema_catalog",
                           "scripts.verify_extension_runtime.verify_extension_runtime",
                           "scripts.verify_em_cosimulation_runtime.verify_em_cosimulation_runtime"):
                stack.enter_context(patch(target, return_value={}))
            if "verify_native_momentum_runtime" in target:
                stack.enter_context(patch("scripts.verify_native_cht_runtime.verify_native_cht_runtime",
                                          return_value={"status": "passed"}))
            native = stack.enter_context(patch(target,
                side_effect=RuntimeError("required native CHT probe")))
            with self.assertRaisesRegex(RuntimeError, "required native CHT probe"):
                builder._verify(worker)
            native.assert_called_once()
