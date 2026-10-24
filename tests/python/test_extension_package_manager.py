# SPDX-License-Identifier: Apache-2.0
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from python.spike_core.extensions import ExtensionPackageManager, ExtensionRegistry
from python.spike_core import extensions


def manifest(extension_id: str = "example.managed", *, bundled: bool = False) -> dict:
    return {
        "contract": "spike/extension/v1",
        "api_version": 1,
        "id": extension_id,
        "name": "Managed example",
        "version": "1.0.0",
        "provider": "Tests",
        "description": "Extension-manager fixture.",
        "execution": "process",
        "runtime": "python",
        "entrypoint": "extension.py",
        "state": "available",
        "license": "MIT",
        "bundled": bundled,
        "permissions": [],
        "contributes": {"commands": [{"id": "run", "name": "Run"}]},
    }


def write_package(root: Path, value: dict | None = None) -> Path:
    package = root / "package"
    package.mkdir()
    (package / "spike-extension.json").write_text(
        json.dumps(value or manifest()), encoding="utf-8",
    )
    (package / "extension.py").write_text("print('fixture')\n", encoding="utf-8")
    return package


class ExtensionPackageManagerTests(unittest.TestCase):
    def test_windows_directory_move_retries_only_bounded_denials(self):
        for code in (5, 32, 33):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                source, destination = Path(directory) / "source", Path(directory) / "target"
                source.mkdir()
                (source / "proof").write_text("retained", encoding="utf-8")
                denied = PermissionError("forced transient denial")
                denied.winerror = code
                rename = os.rename
                calls = 0
                def transient(src, dst):
                    nonlocal calls
                    calls += 1
                    if calls < 3:
                        raise denied
                    return rename(src, dst)
                with patch.object(extensions.sys, "platform", "win32"), patch.object(
                    extensions.os, "rename", side_effect=transient
                ) as move, patch.object(extensions.time, "sleep") as sleep:
                    extensions._rename_extension_directory(source, destination)
                self.assertEqual(move.call_count, 3)
                self.assertEqual([call.args[0] for call in sleep.call_args_list], [.05, .1])
                self.assertFalse(source.exists())
                self.assertEqual((destination / "proof").read_text(encoding="utf-8"), "retained")

    def test_move_exhaustion_unrelated_errors_and_nonwindows_are_not_hidden(self):
        for platform, code, attempts in (("win32", 5, 3), ("win32", 32, 3),
                                          ("win32", 33, 3), ("win32", 2, 1), ("linux", 5, 1)):
            with self.subTest(platform=platform, code=code), tempfile.TemporaryDirectory() as directory:
                source, destination = Path(directory) / "source", Path(directory) / "target"
                source.mkdir()
                denied = PermissionError("forced persistent denial")
                denied.winerror = code
                with patch.object(extensions.sys, "platform", platform), patch.object(
                    extensions.os, "rename", side_effect=denied
                ) as move, patch.object(extensions.time, "sleep") as sleep:
                    with self.assertRaises(PermissionError) as raised:
                        extensions._rename_extension_directory(source, destination)
                self.assertIs(raised.exception, denied)
                self.assertEqual(move.call_count, attempts)
                self.assertEqual(sleep.call_count, attempts - 1)
                self.assertTrue(source.is_dir())
                self.assertFalse(destination.exists())

    def test_retry_never_overwrites_destination_created_during_delay(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory) / "source", Path(directory) / "target"
            source.mkdir()
            denied = PermissionError("forced denial")
            denied.winerror = 5
            def collision(_delay):
                destination.mkdir()
                (destination / "foreign").write_text("preserve", encoding="utf-8")
            with patch.object(extensions.sys, "platform", "win32"), patch.object(
                extensions.os, "rename", side_effect=denied
            ) as move, patch.object(extensions.time, "sleep", side_effect=collision):
                with self.assertRaises(FileExistsError):
                    extensions._rename_extension_directory(source, destination)
            self.assertEqual(move.call_count, 1)
            self.assertTrue(source.is_dir())
            self.assertEqual((destination / "foreign").read_text(encoding="utf-8"), "preserve")

    def test_failed_replacement_restores_previous_managed_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = write_package(root)
            manager = ExtensionPackageManager(root / "installed")
            manager.install(source)
            destination = manager.install_root / "example.managed"
            previous = {p.name: p.read_bytes() for p in destination.iterdir()}
            (source / "extension.py").write_text("print('replacement')\n", encoding="utf-8")
            denied = PermissionError("forced replacement denial")
            denied.winerror = 5
            rename = os.rename
            attempts = 0
            def reject_stage(src, dst):
                nonlocal attempts
                if Path(src).name.startswith(".install-"):
                    attempts += 1
                    raise denied
                return rename(src, dst)
            with patch.object(extensions.sys, "platform", "win32"), patch.object(
                extensions.os, "rename", side_effect=reject_stage
            ), patch.object(extensions.time, "sleep"):
                with self.assertRaises(PermissionError) as raised:
                    manager.install(source, replace=True)
            self.assertIs(raised.exception, denied)
            self.assertEqual(attempts, 3)
            self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, previous)
            self.assertEqual(list(manager.install_root.iterdir()), [destination])

    def test_exhausted_rollback_retains_recoverable_previous_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = write_package(root)
            manager = ExtensionPackageManager(root / "installed")
            manager.install(source)
            destination = manager.install_root / "example.managed"
            previous = {p.name: p.read_bytes() for p in destination.iterdir()}
            denied = PermissionError("forced commit and rollback denial")
            denied.winerror = 32
            rename = os.rename
            counts = {"stage": 0, "rollback": 0}
            def reject_commit_and_restore(src, dst):
                name = Path(src).name
                kind = "stage" if name.startswith(".install-") else "rollback" if name.startswith(".replace-") else None
                if kind:
                    counts[kind] += 1
                    raise denied
                return rename(src, dst)
            with patch.object(extensions.sys, "platform", "win32"), patch.object(
                extensions.os, "rename", side_effect=reject_commit_and_restore
            ), patch.object(extensions.time, "sleep"):
                with self.assertRaises(PermissionError):
                    manager.install(source, replace=True)
            self.assertEqual(counts, {"stage": 3, "rollback": 3})
            self.assertFalse(destination.exists())
            backups = list(manager.install_root.glob(".replace-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual({p.name: p.read_bytes() for p in backups[0].iterdir()}, previous)
            registry = ExtensionRegistry()
            registry.discover([manager.install_root])
            self.assertEqual(registry.catalog(), [])

    def test_directory_install_is_untrusted_managed_and_removable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = write_package(root)
            manager = ExtensionPackageManager(root / "installed")
            preview = manager.preview(package)
            self.assertTrue(preview["can_install"])
            self.assertFalse(preview["installed"])
            self.assertEqual(preview["file_count"], 2)

            installed = manager.install(package)
            self.assertEqual(installed["action"], "installed")
            self.assertFalse(installed["trusted"])
            registry = ExtensionRegistry()
            registry.discover([root / "installed"])
            browser = manager.browse(registry)
            self.assertTrue(browser["extensions"][0]["managed"])
            self.assertTrue(browser["extensions"][0]["can_remove"])
            self.assertFalse(browser["extensions"][0]["trusted"])

            removed = manager.remove("example.managed")
            self.assertTrue(removed["removed"])
            self.assertFalse((root / "installed" / "example.managed").exists())

    def test_install_refuses_unmanaged_collision_and_self_bundled_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = ExtensionPackageManager(root / "installed")
            package = write_package(root)
            collision = root / "installed" / "example.managed"
            collision.mkdir(parents=True)
            with self.assertRaisesRegex(FileExistsError, "not owned"):
                manager.install(package)
            with self.assertRaisesRegex(PermissionError, "Only extensions installed"):
                manager.remove("example.managed")

            bundled_root = root / "bundled-source"
            bundled_root.mkdir()
            (bundled_root / "spike-extension.json").write_text(
                json.dumps(manifest("example.false-bundle", bundled=True)), encoding="utf-8",
            )
            (bundled_root / "extension.py").write_text("pass\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot declare themselves bundled"):
                manager.preview(bundled_root)

    def test_archive_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "unsafe.spike-extension"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("spike-extension.json", json.dumps(manifest()))
                package.writestr("extension.py", "pass\n")
                package.writestr("../escape.py", "bad\n")
            manager = ExtensionPackageManager(root / "installed")
            with self.assertRaisesRegex(ValueError, "Unsafe extension archive member"):
                manager.install(archive)
            self.assertFalse((root / "escape.py").exists())

    def test_nested_archive_installs_and_can_be_browsed_as_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "example.spike-extension"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("example/spike-extension.json", json.dumps(manifest()))
                package.writestr("example/extension.py", "pass\n")
            manager = ExtensionPackageManager(root / "installed")
            browser = manager.browse(ExtensionRegistry(), archive)
            self.assertEqual(browser["candidate"]["manifest"]["id"], "example.managed")
            installed = manager.install(archive)
            self.assertEqual(installed["extension_id"], "example.managed")
            self.assertTrue((root / "installed" / "example.managed" / "extension.py").is_file())

    def test_worker_methods_install_list_and_remove_managed_package(self) -> None:
        from python.spike_core import service

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = write_package(root)
            state = root / "state"
            with patch.dict(os.environ, {"SPIKE_STATE_HOME": str(state)}, clear=False), patch.object(
                service, "_extension_packages", ExtensionPackageManager(state / "extensions")
            ), patch.object(service, "_extension_registry", ExtensionRegistry()):
                service._refresh_extensions()
                preview = service.handle({
                    "method": "inspect_extension_package", "params": {"path": str(package)},
                })
                self.assertTrue(preview["ok"])
                install = service.handle({
                    "method": "install_extension", "params": {"path": str(package)},
                })
                self.assertTrue(install["ok"])
                self.assertFalse(install["result"]["extension"]["trusted"])
                catalog = service.handle({"method": "list_extensions", "params": {}})
                entry = next(item for item in catalog["result"]["extensions"] if item["id"] == "example.managed")
                self.assertTrue(entry["managed"])
                self.assertTrue(entry["can_remove"])
                remove = service.handle({
                    "method": "remove_extension", "params": {"extension_id": "example.managed"},
                })
                self.assertTrue(remove["ok"])
                bundled = service.handle({
                    "method": "remove_extension", "params": {"extension_id": "spike.emerge-suite"},
                })
                self.assertFalse(bundled["ok"])

    def test_worker_rejects_id_already_loaded_from_external_root(self) -> None:
        from python.spike_core import service

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = write_package(root)
            external_root = root / "external"
            external_root.mkdir()
            external_package = external_root / "example.managed"
            extensions._rename_extension_directory(source, external_package)
            self.assertFalse(source.exists())
            self.assertTrue((external_package / "spike-extension.json").is_file())
            replacement = write_package(root)
            state = root / "state"
            environment = {"SPIKE_STATE_HOME": str(state), "SPIKE_EXTENSION_PATH": str(external_root)}
            with patch.dict(os.environ, environment, clear=False), patch.object(
                service, "_extension_packages", ExtensionPackageManager(state / "extensions")
            ), patch.object(service, "_extension_registry", ExtensionRegistry()):
                service._refresh_extensions()
                preview = service.handle({"method": "inspect_extension_package", "params": {"path": str(replacement)}})
                self.assertTrue(preview["ok"])
                self.assertFalse(preview["result"]["can_install"])
                install = service.handle({"method": "install_extension", "params": {"path": str(replacement)}})
                self.assertFalse(install["ok"])
                self.assertFalse((state / "extensions" / "example.managed").exists())


if __name__ == "__main__":
    unittest.main()
