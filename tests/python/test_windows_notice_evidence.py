"""Focused fail-closed contracts for local Windows notice evidence collection."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

from scripts.collect_windows_notice_evidence import (
    NoticeEvidenceError,
    _npm_candidates,
    _wheel_candidates,
    collect_notice_evidence,
)


ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class WindowsNoticeEvidenceTests(unittest.TestCase):
    def make_fixture(self, directory: Path, *, unsafe: bool = False, oversized: bool = False, duplicate: bool = False) -> dict[str, Path]:
        build, runtime, cache = directory / "build", directory / "runtime", directory / "cache"
        for path in (build, runtime, cache, directory / "app" / "node_modules"):
            path.mkdir(parents=True, exist_ok=True)
        metadata = b"Metadata-Version: 2.1\nName: Demo_Pkg\nVersion: 1.0\nLicense-Expression: MIT\n\n"
        wheel = runtime / "demo_pkg-1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("demo_pkg-1.0.dist-info/METADATA", metadata)
            archive.writestr("../LICENSE" if unsafe else "demo_pkg-1.0.dist-info/LICENSE", b"MIT\n" if not oversized else b"x" * (4 * 1024 * 1024 + 1))
        if duplicate:
            with zipfile.ZipFile(build / "other.whl", "w") as archive:
                archive.writestr("demo_pkg-1.0.dist-info/METADATA", metadata)
                archive.writestr("demo_pkg-1.0.dist-info/LICENSE", b"different\n")
        build_lock, runtime_lock = directory / "build.txt", directory / "runtime.txt"
        build_lock.write_text("", encoding="utf-8")
        runtime_lock.write_text(f"demo-pkg==1.0 --hash=sha256:{digest(wheel)}\n", encoding="utf-8")
        package_lock = directory / "app" / "package-lock.json"
        package_lock.write_text(json.dumps({"lockfileVersion": 3, "packages": {}}), encoding="utf-8")
        cargo_lock, cargo_toml = directory / "Cargo.lock", directory / "Cargo.toml"
        cargo_lock.write_text("version = 4\n", encoding="utf-8")
        cargo_toml.write_text("[package]\nname = 'fixture'\nversion = '0.1.0'\nedition = '2021'\n", encoding="utf-8")
        record = {"purl": "pkg:pypi/demo-pkg@1.0", "name": "demo-pkg", "version": "1.0", "ecosystem": "python", "scope": "bundled",
                  "integrity": {"algorithm": "sha256", "value": digest(wheel)}, "declared_license": "MIT",
                  "license_evidence": {"kind": "wheel-metadata", "sha256": hashlib.sha256(metadata).hexdigest()}}
        record["identity_sha256"] = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        inventory = directory / "inventory.json"
        inventory.write_text(json.dumps({"contract": "spike/windows-component-inventory/v1", "platform": "windows-x64", "production_qualified": False,
                                         "sources": [{"id": "cargo_lock", "sha256": digest(cargo_lock)}, {"id": "npm_package_lock", "sha256": digest(package_lock)},
                                                     {"id": "python_build_lock", "sha256": digest(build_lock)}, {"id": "python_runtime_lock", "sha256": digest(runtime_lock)}],
                                         "components": [record]}), encoding="utf-8")
        return {"inventory": inventory, "package_lock": package_lock, "npm_root": directory / "app" / "node_modules", "cargo_lock": cargo_lock,
                "cargo_manifest": cargo_toml, "cargo_cache": cache, "build_requirements": build_lock, "runtime_requirements": runtime_lock,
                "build_wheel_dir": build, "runtime_wheel_dir": runtime, "output": directory / "out.json", "evidence_dir": directory / "evidence"}

    def test_collects_and_schema_validates_bounded_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.make_fixture(Path(temporary))
            result = collect_notice_evidence(**paths)
            self.assertEqual(result["summary"]["components"], 1)
            self.assertEqual(result["summary"]["candidates"], 1)
            self.assertFalse(result["components"][0]["missing"])
            self.assertEqual(result["components"][0]["candidates"][0]["source_kind"], "python-wheel")
            self.assertEqual(result["components"][0]["candidates"][0]["source_locator"], "runtime-wheel-dir/demo_pkg-1.0-py3-none-any.whl")
            self.assertNotIn("archive_path", result["components"][0]["candidates"][0])
            self.assertFalse(Path(result["components"][0]["candidates"][0]["source_locator"]).is_absolute())
            schema = json.loads((ROOT / "schemas" / "windows-notice-evidence-index-v1.schema.json").read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(result)

    def test_rejects_stale_input_and_unsafe_or_oversized_archive_members(self) -> None:
        for kind in ("stale", "unsafe", "oversized"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                paths = self.make_fixture(Path(temporary), unsafe=kind == "unsafe", oversized=kind == "oversized")
                if kind == "stale":
                    paths["runtime_requirements"].write_text("# changed\n" + paths["runtime_requirements"].read_text(encoding="utf-8"), encoding="utf-8")
                with self.assertRaises(NoticeEvidenceError):
                    collect_notice_evidence(**paths)

    def test_rejects_non_identical_duplicate_wheels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.make_fixture(Path(temporary), duplicate=True)
            with self.assertRaisesRegex(NoticeEvidenceError, "non-identical duplicate"):
                collect_notice_evidence(**paths)

    def test_npm_recursive_scan_does_not_cross_node_modules_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "app" / "node_modules"
            parent = root / "parent"
            child = parent / "node_modules" / "child"
            child.mkdir(parents=True)
            parent.joinpath("package.json").write_text('{"name": "parent", "version": "1.0"}', encoding="utf-8")
            child.joinpath("package.json").write_text('{"name": "child", "version": "2.0"}', encoding="utf-8")
            parent.joinpath("LICENSE").write_bytes(b"parent\n")
            child.joinpath("LICENSE").write_bytes(b"child\n")
            candidates = _npm_candidates(
                [("pkg:npm/parent@1.0", "node_modules/parent"), ("pkg:npm/child@2.0", "node_modules/parent/node_modules/child")],
                root,
                {"pkg:npm/parent@1.0": {"name": "parent", "version": "1.0"}, "pkg:npm/child@2.0": {"name": "child", "version": "2.0"}},
            )
            self.assertEqual([entry[2] for entry in candidates["pkg:npm/parent@1.0"]], [b"parent\n"])
            self.assertEqual([entry[2] for entry in candidates["pkg:npm/child@2.0"]], [b"child\n"])

    def test_wheel_candidate_scoping_isolates_vendored_dist_info(self) -> None:
        entries = [
            ("LICENSE", b"wheel-root"),
            ("top-1.0.dist-info/LICENSE", b"top"),
            ("vendor/site/vendor-2.0.dist-info/LICENSE", b"vendor"),
            ("package/LICENSE", b"unattributed"),
        ]
        top = _wheel_candidates(entries, PurePosixPath("top-1.0.dist-info"), include_wheel_root=True)
        vendor = _wheel_candidates(entries, PurePosixPath("vendor/site/vendor-2.0.dist-info"), include_wheel_root=False)
        self.assertEqual(top, [("LICENSE", b"wheel-root"), ("top-1.0.dist-info/LICENSE", b"top")])
        self.assertEqual(vendor, [("vendor/site/vendor-2.0.dist-info/LICENSE", b"vendor")])


if __name__ == "__main__":
    unittest.main()
