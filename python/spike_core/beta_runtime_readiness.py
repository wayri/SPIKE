# SPDX-License-Identifier: Apache-2.0
"""Offline beta-readiness probe for SPIKE's public process boundaries.

This module verifies packaging and interface invariants.  It does not grant a
solver capability, qualify numerical physics, or launch a user job.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any, Mapping

from .spikes_native_adapter import capability_manifest as native_adapter_manifest
from .spikes_native_adapter import probe_runtime_capabilities
from python.spikes.version import ENGINE_VERSION


CONTRACT = "spike/beta-runtime-readiness/v1"
MAX_MANIFEST_BYTES = 8 * 1024 * 1024


class BetaReadinessError(ValueError):
    """A beta process artifact violated its public invariant."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BetaReadinessError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_MANIFEST_BYTES:
        raise BetaReadinessError(f"{label} is missing, empty, or oversized")
    try:
        value = json.loads(
            path.read_bytes().decode("utf-8"), object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                BetaReadinessError(f"non-finite JSON constant {token} is prohibited")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BetaReadinessError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise BetaReadinessError(f"{label} must contain one JSON object")
    return value


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def inspect_circuit_package(repository: Path) -> dict[str, Any]:
    package_parent = repository / "app" / "src-tauri" / "resources" / "worker"
    manifest_path = package_parent / "spike-circuit-worker.manifest.json"
    artifact_root = package_parent / "spike-circuit-worker"
    if not manifest_path.is_file() and not artifact_root.exists():
        return {
            "state": "not_packaged", "validation_state": "experimental",
            "product_qualified": False, "integrity_verified": False,
            "reason": "The optional packaged circuit worker is not installed.",
        }
    manifest = _read_object(manifest_path, "circuit-worker package manifest")
    if manifest.get("contract") != "spike/owned-spice-process-package/v1":
        raise BetaReadinessError("circuit-worker package contract is incompatible")
    capability = manifest.get("capability")
    files = manifest.get("files")
    if not isinstance(capability, Mapping) or not isinstance(files, list) or not files:
        raise BetaReadinessError("circuit-worker package manifest is incomplete")
    expected_capability = {
        "engine": "spike-circuit-worker", "validation_state": "experimental",
        "structured_workspace_only": True, "raw_netlist_accepted": False,
        "shell_invoked": False, "trusted_host_supervision_required": True,
        "binary_and_library_sha256_admission": True,
    }
    for field, expected in expected_capability.items():
        if capability.get(field) != expected:
            raise BetaReadinessError(
                f"circuit-worker capability field {field!r} is incompatible"
            )
    declared: set[str] = set()
    for item in files:
        if not isinstance(item, Mapping):
            raise BetaReadinessError("circuit-worker file record is malformed")
        name, size, digest = item.get("path"), item.get("bytes"), item.get("sha256")
        pure = PurePosixPath(name) if isinstance(name, str) else PurePosixPath()
        if (
            not name or pure.is_absolute() or "\\" in name
            or any(part in {"", ".", ".."} for part in pure.parts)
            or name in declared
        ):
            raise BetaReadinessError("circuit-worker file path is unsafe or repeated")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise BetaReadinessError(f"circuit-worker file size is invalid for {name}")
        if (
            not isinstance(digest, str) or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise BetaReadinessError(f"circuit-worker digest is invalid for {name}")
        declared.add(name)
        path = artifact_root.joinpath(*pure.parts)
        if not path.is_file() or path.stat().st_size != size or _digest(path) != digest:
            raise BetaReadinessError(f"circuit-worker integrity mismatch for {name}")
    actual = {
        path.relative_to(artifact_root).as_posix()
        for path in artifact_root.rglob("*") if path.is_file()
    }
    if actual != declared:
        raise BetaReadinessError("circuit-worker package file inventory is incomplete or stale")
    return {
        "state": "available", "validation_state": "experimental",
        "product_qualified": False, "integrity_verified": True,
        "package_contract": manifest["contract"], "files_verified": len(declared),
        "interface": capability.get("interface", []),
        "structured_workspace_only": True, "raw_netlist_accepted": False,
        "trusted_host_supervision_required": True,
    }


def inspect_layout_process(repository: Path) -> dict[str, Any]:
    entry = repository / "scripts" / "spike_layout_scoring_worker_entry.py"
    if not entry.is_file():
        raise BetaReadinessError("layout-scoring source entry point is missing")
    try:
        completed = subprocess.run(
            [sys.executable, str(entry), "--capabilities"],
            cwd=repository, stdin=subprocess.DEVNULL, capture_output=True,
            shell=False, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BetaReadinessError("layout-scoring capability probe failed") from exc
    if completed.returncode != 0 or completed.stderr or len(completed.stdout) > 256 * 1024:
        raise BetaReadinessError("layout-scoring capability process returned invalid output")
    try:
        capability = json.loads(
            completed.stdout.decode("utf-8"), object_pairs_hook=_strict_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BetaReadinessError("layout-scoring capability output is invalid") from exc
    expected = {
        "contract": "spike/layout-scoring-process-capability/v1",
        "engine": "spike-layout-scoring-worker",
        "validation_state": "experimental", "routes_or_places": False,
        "meshes_or_solves": False, "shell_invoked": False,
    }
    if not isinstance(capability, dict) or any(
        capability.get(field) != value for field, value in expected.items()
    ):
        raise BetaReadinessError("layout-scoring capability claims are incompatible")
    if capability.get("consumers") != ["autorouter", "autoplacer", "joint"]:
        raise BetaReadinessError("layout-scoring consumer contract is incompatible")
    return {
        "state": "available_from_source", "validation_state": "experimental",
        "product_qualified": False, "packaged_artifact_qualified": False,
        "interface": capability.get("interface", []),
        "consumers": capability["consumers"], "routes_or_places": False,
        "meshes_or_solves": False,
    }


def build_readiness_report(
    repository: str | Path,
    *,
    native_solver: str = "",
    require_circuit_worker: bool = False,
    require_native_runtime: bool = False,
) -> dict[str, Any]:
    root = Path(repository).resolve(strict=True)
    configuration = _read_object(
        root / "app" / "src-tauri" / "tauri.conf.json", "Tauri configuration",
    )
    version = configuration.get("version")
    if not isinstance(version, str) or not version:
        raise BetaReadinessError("public product version is missing")
    circuit = inspect_circuit_package(root)
    layout = inspect_layout_process(root)
    adapter = native_adapter_manifest()
    if (
        adapter.get("status") != "integration_pending"
        or adapter.get("physics") != []
        or adapter.get("capabilities") != ["probe", "self_test"]
    ):
        raise BetaReadinessError("native public adapter claims exceed the beta boundary")
    native = probe_runtime_capabilities(native_solver)
    errors: list[str] = []
    if require_circuit_worker and circuit["state"] != "available":
        errors.append("packaged circuit worker is required but unavailable")
    if require_native_runtime and native.get("status") != "available":
        errors.append("compatible native verification runtime is required but unavailable")
    return {
        "contract": CONTRACT,
        "product": "SPIKE", "version": version,
        "engine_product": "SPIKES", "engine_version": ENGINE_VERSION,
        "status": "passed" if not errors else "failed",
        "release_tier": "bounded_beta_candidate",
        "production_qualified": False,
        "components": {
            "circuit_worker": circuit,
            "layout_scoring_process": layout,
            "native_solver_adapter": {
                "state": "integration_pending", "physics": [],
                "runnable_capabilities": ["probe", "self_test"],
                "runtime_probe": native,
                "product_physics_eligible": False,
            },
        },
        "errors": errors,
        "limitations": [
            "The beta probe verifies public process and package invariants, not numerical accuracy.",
            "Layout scoring does not route, place, mesh, or solve.",
            "The circuit worker accepts only the reviewed structured workspace and remains experimental.",
            "Native solver physics remains integration_pending and verification-only at the public boundary.",
        ],
    }
