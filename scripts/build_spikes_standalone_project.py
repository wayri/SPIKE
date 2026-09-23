#!/usr/bin/env python3
"""Build a deterministic, self-contained SPIKES source/SDK project archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "standalone/spikes_project"
CONTRACT = "spikes/standalone-source-manifest/v1"
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def current_engine_version() -> str:
    """Read the canonical engine version without importing runtime dependencies."""
    version_file = ROOT / "python/spikes/version.py"
    for line in version_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("ENGINE_VERSION = "):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"ENGINE_VERSION was not found in {version_file}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_file(source: Path, target: Path) -> None:
    source = source.resolve(strict=True)
    try:
        source.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"source is outside the repository: {source}") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def copy_tree(source: Path, target: Path) -> None:
    source = source.resolve(strict=True)
    for item in sorted(source.rglob("*")):
        if not item.is_file() or "__pycache__" in item.parts or item.suffix in {".pyc", ".pyo"}:
            continue
        copy_file(item, target / item.relative_to(source))


def build(version: str, output_root: Path) -> tuple[Path, Path, Path]:
    if not version or len(version) > 64 or any(
        character not in "0123456789.-abcdefghijklmnopqrstuvwxyz" for character in version.lower()
    ):
        raise ValueError("version contains unsupported characters")
    destination_root = output_root.resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    package_name = f"SPIKES-{version}-standalone-source"
    package = destination_root / package_name
    archive = destination_root / f"{package_name}.zip"
    report = destination_root / f"{package_name}.json"
    if package.exists() or archive.exists() or report.exists():
        raise FileExistsError("standalone destination already exists; select a fresh version/output root")

    copy_tree(TEMPLATE, package)
    copy_tree(ROOT / 'scripts/studio_packaging', package / 'scripts/studio_packaging')
    copy_file(ROOT / 'scripts/build_spikes_studio_package.py', package / 'scripts/build_spikes_studio_package.py')
    copy_tree(ROOT / 'licenses', package / 'licenses')
    copy_tree(ROOT / "src/spikes", package / "engine/src/spikes")
    copy_tree(ROOT / "python/spikes", package / "python/spikes")
    copy_file(ROOT / "python/__init__.py", package / "python/__init__.py")
    # SPIKES' released Python reference analyses still use a small historical
    # `python.spike_core` namespace.  Package only the numerical/process modules
    # they actually consume; the standalone template supplies minimal package,
    # runtime-location, and solver-manifest shims so no PCB/UI service is pulled
    # into this project.
    for name in (
        "acceleration.py", "native_mna.py", "contracts.py", "ngspice_plugin.py",
        "spice_netlist_safety.py", "sparselizard_process.py",
    ):
        copy_file(ROOT / "python/spike_core" / name, package / "python/spike_core" / name)
    copy_tree(ROOT / "examples/spikes", package / "examples/spikes")
    copy_tree(ROOT / "benchmarks/public_equal_model", package / "benchmarks/public_equal_model")
    copy_tree(ROOT / "benchmarks/public_application", package / "benchmarks/public_application")

    native_tests = (
        "test_spikes_dc.cpp", "test_spikes_c_api.cpp", "test_spikes_transient.cpp",
        "test_spikes_transient_c_api.cpp", "test_spikes_transient_session.cpp",
        "test_spikes_transient_session_c_api.cpp", "test_spikes_console_dashboard.cpp",
    )
    for name in native_tests:
        copy_file(ROOT / "tests" / name, package / "tests/native" / name)
    integration_only_tests = {
        "test_spikes_engine_version.py",
        "test_spikes_release_verifier.py",
        "test_spikes_worker_runtime.py",
    }
    for test in sorted((ROOT / "tests/python").glob("test_spikes*.py")):
        if test.name in integration_only_tests:
            continue
        copy_file(test, package / "tests/python" / test.name)

    for document in sorted((ROOT / "docs").glob("SPIKES*.md")):
        copy_file(document, package / "docs" / document.name)
    for name in (
        "SOLVER_STATUS.md", "BERKELEY_BSIM_OSDI_QUALIFICATION.md",
        "PHYSICAL_HIL_CERTIFICATION.md",
    ):
        copy_file(ROOT / "docs" / name, package / "docs" / name)
    copy_file(
        ROOT / "docs/validation/spikes-ngspice-competitive-gate.json",
        package / "docs/validation/spikes-ngspice-competitive-gate.json",
    )
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "RELEASE_NOTES.md"):
        copy_file(ROOT / name, package / name)

    for name in (
        "bsimbulk-107.2.1-windows-x64.osdi",
        "bsimcmg-112.1.0-windows-x64.osdi",
    ):
        copy_file(ROOT / "artifacts/models" / name, package / "models" / name)
    fixtures = {
        ROOT / "artifacts/hdl-qualification-wave4-current/spikes_linear_resistor.osdi":
            "spikes_linear_resistor.osdi",
        ROOT / "artifacts/hdl-qualification-wave5-capacitor.osdi":
            "hdl-qualification-wave5-capacitor.osdi",
        ROOT / "artifacts/hdl-qualification-wave5-noise.osdi":
            "hdl-qualification-wave5-noise.osdi",
    }
    for source, name in fixtures.items():
        copy_file(source, package / "models/fixtures" / name)
    for family in ("bsimbulk-107.2.1", "bsimcmg-112.1.0"):
        for legal in ("LICENSE.txt", "NOTICE.txt"):
            copy_file(
                ROOT / "tools/models/berkeley" / family / legal,
                package / "models/legal" / family / legal,
            )

    evidence_names = (
        "spikes-competitive-converter-rf-motor-2026-08-31.json",
        "spikes-qualification-report-0.3.0-alpha.4-2026-08-31.json",
        "spikes-parity-check-report-0.3.0-alpha.4-2026-08-31.json",
        "spikes-physical-hil-gate-2026-08-31.json",
    )
    copy_file(
        ROOT / "artifacts/models/berkeley-bsim-osdi-qualification-2026-08-31.json",
        package / "evidence/berkeley-bsim-osdi-qualification-2026-08-31.json",
    )
    for name in evidence_names:
        copy_file(ROOT / "artifacts" / name, package / "evidence" / name)

    records: list[dict[str, object]] = []
    for item in sorted(package.rglob("*")):
        if item.is_file():
            records.append({
                "path": item.relative_to(package).as_posix(),
                "size": item.stat().st_size,
                "sha256": sha256(item),
            })
    manifest = {
        "contract": CONTRACT,
        "product": "SPIKES standalone engine and Studio source project",
        "version": version,
        "channel": "engineering_preview_source",
        "files": records,
        "claims": {
            "standalone_source_project": True,
            "engine_and_console_buildable": True,
            "studio_gui_implemented": False,
            "studio_wxpython_workbench_runnable": True,
            "studio_cpp_vtk_gui_implemented": False,
            "complete_spice3_parity": False,
            "physical_hil_certified": False,
            "production_signed": False,
        },
    }
    manifest_path = package / "source.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for item in sorted(package.rglob("*")):
            if not item.is_file():
                continue
            relative = PurePosixPath(package_name) / PurePosixPath(item.relative_to(package).as_posix())
            info = zipfile.ZipInfo(relative.as_posix(), ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, item.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    outer_report = {
        "contract": CONTRACT,
        "version": version,
        "package": str(package),
        "manifest_sha256": sha256(manifest_path),
        "archive": {
            "path": archive.name,
            "size": archive.stat().st_size,
            "sha256": sha256(archive),
        },
        "file_count": len(records),
        "claims": manifest["claims"],
    }
    report.write_text(json.dumps(outer_report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return package, archive, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=current_engine_version())
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/projects")
    arguments = parser.parse_args()
    package, archive, report = build(arguments.version, arguments.output_root)
    print(f"Standalone project: {package}")
    print(f"Source archive: {archive}")
    print(f"Build report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
