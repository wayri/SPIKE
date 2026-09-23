"""Deterministic, integrity-bound SPIKES engine engineering-preview bundles."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence


RELEASE_MANIFEST_CONTRACT = "spikes/engine-release-manifest/v1"
_ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe release path: {value!r}")
    return path


@dataclass(frozen=True, slots=True)
class ReleaseInput:
    source: Path
    destination: str

    def validated(self, root: Path) -> "ReleaseInput":
        source = self.source.resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"release input is not a file: {source}")
        try:
            source.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"release input is outside the workspace: {source}") from exc
        return ReleaseInput(source, _safe_relative(self.destination).as_posix())


def collect_tree(root: Path, source: Path, destination: str) -> list[ReleaseInput]:
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError(f"release tree is not a directory: {source}")
    prefix = _safe_relative(destination)
    result: list[ReleaseInput] = []
    for item in sorted(source.rglob("*")):
        if not item.is_file() or "__pycache__" in item.parts or item.suffix in {".pyc", ".pyo"}:
            continue
        relative = PurePosixPath(item.relative_to(source).as_posix())
        result.append(ReleaseInput(item, (prefix / relative).as_posix()).validated(root))
    return result


def build_engine_release(
    *, root: str | Path, version: str, library: str | Path,
    output_root: str | Path, evidence: Sequence[str | Path] = (),
) -> tuple[Path, Path, dict[str, object]]:
    workspace = Path(root).resolve(strict=True)
    if not version or len(version) > 64 or any(ch not in "0123456789.-abcdefghijklmnopqrstuvwxyz" for ch in version.lower()):
        raise ValueError("version contains unsupported characters")
    destination_root = Path(output_root).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    package_name = f"SPIKES-{version}-windows-x64-engineering-preview"
    package = (destination_root / package_name).resolve()
    archive = (destination_root / f"{package_name}.zip").resolve()
    if package.exists() or archive.exists():
        raise FileExistsError("release destination already exists; use a fresh version/output root")
    if package.parent != destination_root or archive.parent != destination_root:
        raise ValueError("release destination escaped the requested output root")

    library_path = Path(library)
    if not library_path.is_absolute():
        library_path = workspace / library_path
    inputs = [
        ReleaseInput(workspace / "spikes.cmd", "spikes.cmd"),
        ReleaseInput(workspace / "LICENSE", "legal/LICENSE"),
        ReleaseInput(workspace / "THIRD_PARTY_NOTICES.md", "legal/THIRD_PARTY_NOTICES.md"),
        ReleaseInput(workspace / "RELEASE_NOTES.md", "RELEASE_NOTES.md"),
        ReleaseInput(workspace / "src/spikes/c_api.h", "include/spikes/c_api.h"),
        ReleaseInput(library_path, "bin/spikes_c_api.dll"),
    ]
    # A native build places the console, import archive, and static SDK
    # libraries beside the shared C ABI.  Keep them optional so the bundler
    # remains usable for ABI-only qualification builds, while complete release
    # builds automatically become both an application and a developer SDK.
    native_siblings = (
        ("spikes_console.exe", "bin/spikes_console.exe"),
        ("spikes_osdi_worker.exe", "bin/spikes_osdi_worker.exe"),
        ("spikes_appcontainer_launcher.exe", "bin/spikes_appcontainer_launcher.exe"),
        ("spikes_c_api.lib", "lib/spikes_c_api.lib"),
        ("spikes_core.lib", "lib/spikes_core.lib"),
        ("spikes_dashboard.lib", "lib/spikes_dashboard.lib"),
    )
    for filename, destination in native_siblings:
        source = library_path.parent / filename
        if source.is_file():
            inputs.append(ReleaseInput(source, destination))
    for header in (
        "dc_solver.hpp", "transient_solver.hpp", "transient_session.hpp",
        "console_dashboard.hpp", "osdi_device.hpp",
    ):
        inputs.append(ReleaseInput(workspace / "src/spikes" / header,
                                   f"include/spikes/{header}"))
    inputs.extend(collect_tree(workspace, workspace / "python/spikes", "python/spikes"))
    # The public CLI delegates strict project validation and bounded numerical
    # references to spike_core.  Include those reviewed Python sources so a
    # staged package never succeeds only because it was launched from a source
    # checkout.  ``python/core`` contains two geometry helpers imported by
    # spike_core; no GUI packages or local runtime downloads are admitted.
    inputs.extend(collect_tree(workspace, workspace / "python/spike_core", "python/spike_core"))
    inputs.extend(collect_tree(workspace, workspace / "python/core", "python/core"))
    if (workspace / "python/__init__.py").is_file():
        inputs.append(ReleaseInput(workspace / "python/__init__.py", "python/__init__.py"))
    inputs.append(ReleaseInput(
        workspace / "requirements-runtime-windows-x64.txt",
        "requirements-runtime-windows-x64.txt",
    ))
    inputs.append(ReleaseInput(
        workspace / "scripts/evaluate_spikes_hil_evidence.py",
        "bin/evaluate_spikes_hil_evidence.py",
    ))
    inputs.extend(collect_tree(workspace, workspace / "examples/spikes", "examples"))
    inputs.extend(collect_tree(workspace, workspace / "benchmarks/public_equal_model", "benchmarks/public_equal_model"))
    inputs.extend(collect_tree(workspace, workspace / "benchmarks/public_application", "benchmarks/public_application"))
    # Ship only the compiled, redistributable reference compact-model modules
    # and their upstream legal texts.  The Berkeley releases are ECL-2.0; the
    # complete source archives remain in the development tree and are recorded
    # by qualification evidence, but are not duplicated in this binary SDK.
    berkeley_models = (
        (
            "bsimbulk-107.2.1-windows-x64.osdi",
            "bsimbulk-107.2.1",
        ),
        (
            "bsimcmg-112.1.0-windows-x64.osdi",
            "bsimcmg-112.1.0",
        ),
    )
    for module_name, source_directory in berkeley_models:
        module = workspace / "artifacts/models" / module_name
        license_file = workspace / "tools/models/berkeley" / source_directory / "LICENSE.txt"
        notice_file = workspace / "tools/models/berkeley" / source_directory / "NOTICE.txt"
        present = (module.is_file(), license_file.is_file(), notice_file.is_file())
        if any(present) and not all(present):
            raise ValueError(
                f"incomplete Berkeley model package for {source_directory}; "
                "module, license, and notice must be supplied together"
            )
        if all(present):
            inputs.extend((
                ReleaseInput(module, f"models/{module_name}"),
                ReleaseInput(license_file, f"legal/{source_directory}/LICENSE.txt"),
                ReleaseInput(notice_file, f"legal/{source_directory}/NOTICE.txt"),
            ))
    for document in sorted((workspace / "docs").glob("SPIKES*.md")):
        inputs.append(ReleaseInput(document, f"docs/{document.name}"))
    inputs.append(ReleaseInput(workspace / "docs/SOLVER_STATUS.md", "docs/SOLVER_STATUS.md"))
    for document_name in (
        "BERKELEY_BSIM_OSDI_QUALIFICATION.md",
        "PHYSICAL_HIL_CERTIFICATION.md",
    ):
        inputs.append(ReleaseInput(workspace / "docs" / document_name,
                                   f"docs/{document_name}"))
    for item in evidence:
        path = Path(item)
        if not path.is_absolute():
            path = workspace / path
        inputs.append(ReleaseInput(path, f"evidence/{path.name}"))

    validated = [item.validated(workspace) for item in inputs]
    destinations = [item.destination for item in validated]
    if len(destinations) != len(set(destinations)):
        raise ValueError("release inputs contain duplicate destination paths")

    package.mkdir()
    records: list[dict[str, object]] = []
    for item in sorted(validated, key=lambda value: value.destination):
        target = package.joinpath(*PurePosixPath(item.destination).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item.source, target)
        records.append({
            "path": item.destination,
            "size": target.stat().st_size,
            "sha256": _sha256(target),
        })
    manifest: dict[str, object] = {
        "contract": RELEASE_MANIFEST_CONTRACT,
        "product": "SPIKES circuit engine and SDK",
        "version": version,
        "platform": "windows-x64",
        "channel": "engineering_preview",
        "files": records,
        "claims": {
            "engineering_preview": True,
            "complete_spice3_parity": False,
            "competitive_superiority": False,
            "hard_realtime": False,
            "physical_hil": False,
            "hostile_code_safe": False,
            "production_signed": False,
        },
    }
    manifest_path = package / "release.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for item in sorted(package.rglob("*")):
            if not item.is_file():
                continue
            relative = f"{package_name}/{item.relative_to(package).as_posix()}"
            info = zipfile.ZipInfo(relative, _ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, item.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    manifest["archive"] = {
        "path": archive.name,
        "size": archive.stat().st_size,
        "sha256": _sha256(archive),
    }
    return package, archive, manifest


__all__ = [
    "RELEASE_MANIFEST_CONTRACT", "ReleaseInput", "build_engine_release", "collect_tree",
]
