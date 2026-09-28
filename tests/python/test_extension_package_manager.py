# SPDX-License-Identifier: Apache-2.0
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from python.spike_core.extensions import ExtensionPackageManager, ExtensionRegistry


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
            source.rename(external_package)
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
