"""Verify deterministic Windows release provenance without network access."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_windows_release_provenance import (
    PROVENANCE_CONTRACT,
    SBOM_CONTRACT,
    ReleaseProvenanceError,
    _digest,
    _installer_identities,
    _load_object,
    _normalize_component,
    _safe_relative_name,
    _validate_digest,
    _validate_contract,
    _verify_worker_inventory,
    _verify_dependency_signature,
    _probe_detached_cms,
    _approved_inventory_components,
)


def _resolve_reference(base: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, Mapping):
        raise ReleaseProvenanceError(f"{label} reference is malformed")
    name = _safe_relative_name(raw.get("file"), f"{label} file")
    expected = _validate_digest(raw.get("sha256"), f"{label} digest")
    path = (base / name).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError as exc:
        raise ReleaseProvenanceError(f"{label} resolves outside the artifact root") from exc
    if not path.is_file() or _digest(path) != expected:
        raise ReleaseProvenanceError(f"{label} bytes do not match provenance")
    return path


def verify_release_provenance(
    provenance_path: str | Path,
    sbom_path: str | Path,
    artifact_root: str | Path,
    *,
    cms_probe: Callable[[Path, Path, str], Mapping[str, Any]] | None = None,
    worker_root: str | Path | None = None,
) -> dict[str, Any]:
    provenance_file = Path(provenance_path).resolve()
    sbom_file = Path(sbom_path).resolve()
    root = Path(artifact_root).resolve()
    provenance = _load_object(provenance_file, "release provenance")
    sbom = _load_object(sbom_file, "release SBOM")
    if provenance.get("contract") != PROVENANCE_CONTRACT:
        raise ReleaseProvenanceError("Unsupported Windows release provenance contract")
    if sbom.get("contract") != SBOM_CONTRACT:
        raise ReleaseProvenanceError("Unsupported Windows release SBOM contract")
    _validate_contract(provenance, "windows-release-provenance-v1.schema.json")
    _validate_contract(sbom, "windows-release-sbom-v1.schema.json")
    if provenance.get("product") != "SPIKE" or sbom.get("product") != "SPIKE":
        raise ReleaseProvenanceError("Release product identity is not SPIKE")
    if provenance.get("channel") != "production-candidate" or provenance.get("release_state") != "production-candidate":
        raise ReleaseProvenanceError("Release evidence is not a production candidate")
    if provenance.get("production_qualified") is not False:
        raise ReleaseProvenanceError("Provenance must not claim production qualification")
    if sbom.get("application_version") != provenance.get("application_version"):
        raise ReleaseProvenanceError("SBOM and provenance application versions differ")
    sbom_reference = provenance.get("sbom")
    if not isinstance(sbom_reference, Mapping):
        raise ReleaseProvenanceError("SBOM reference is malformed")
    expected_sbom = _safe_relative_name(sbom_reference.get("file"), "SBOM file")
    try:
        actual_sbom = sbom_file.relative_to(root).as_posix()
    except ValueError as exc:
        raise ReleaseProvenanceError("Verifier SBOM path is outside the artifact root") from exc
    if expected_sbom != actual_sbom:
        raise ReleaseProvenanceError("Verifier SBOM path does not match provenance")
    if _validate_digest(sbom_reference.get("sha256"), "SBOM digest") != _digest(sbom_file):
        raise ReleaseProvenanceError("SBOM bytes do not match provenance")

    installer_manifest = _resolve_reference(root, provenance.get("installer_manifest"), "installer manifest")
    manifest = _load_object(installer_manifest, "installer manifest")
    actual_installers = _installer_identities(manifest, root)
    if provenance.get("installers") != actual_installers:
        raise ReleaseProvenanceError("Installer identities do not match the bound manifest")

    inputs = provenance.get("inputs")
    if not isinstance(inputs, list) or len(inputs) not in {4, 6}:
        raise ReleaseProvenanceError("Release provenance must bind the complete legacy or reviewed source set")
    input_ids: set[str] = set()
    resolved: dict[str, Path] = {}
    for record in inputs:
        if not isinstance(record, Mapping):
            raise ReleaseProvenanceError("Release provenance has a malformed source input")
        identifier = str(record.get("id", ""))
        if identifier in input_ids or identifier not in {
            "dependencies_lock", "dependencies_signature", "worker_manifest",
            "third_party_notices", "component_inventory", "component_approvals",
        }:
            raise ReleaseProvenanceError("Release provenance has missing or duplicate source inputs")
        input_ids.add(identifier)
        resolved[identifier] = _resolve_reference(root, record, identifier)
    base_ids = {"dependencies_lock", "dependencies_signature", "worker_manifest", "third_party_notices"}
    modern_ids = base_ids | {"component_inventory", "component_approvals"}
    if input_ids != base_ids and input_ids != modern_ids:
        raise ReleaseProvenanceError("Release provenance source inputs are incomplete")
    if provenance.get("worker_manifest") != {
        "file": resolved["worker_manifest"].relative_to(root).as_posix(),
        "sha256": _digest(resolved["worker_manifest"]),
    }:
        raise ReleaseProvenanceError("Worker manifest reference is inconsistent")
    if provenance.get("notices") != {
        "file": resolved["third_party_notices"].relative_to(root).as_posix(),
        "sha256": _digest(resolved["third_party_notices"]),
    }:
        raise ReleaseProvenanceError("Notice bundle reference is inconsistent")
    notices = resolved["third_party_notices"].read_text(encoding="utf-8")
    if "this register is incomplete" in notices.lower() or "release-blocking" in notices.lower():
        raise ReleaseProvenanceError("Notice bundle is explicitly incomplete or release-blocking")
    dependencies = _load_object(resolved["dependencies_lock"], "dependency lock")
    worker = _load_object(resolved["worker_manifest"], "worker manifest")
    if dependencies.get("manifest") != "spike/dependencies/v1":
        raise ReleaseProvenanceError("Dependency lock contract is invalid")
    if worker.get("contract") != "spike/packaged-worker-manifest/v2":
        raise ReleaseProvenanceError("Worker manifest contract is invalid")
    signing_policy = manifest.get("signing_policy")
    expected_signer = str(signing_policy.get("expected_signer_thumbprint", "")) if isinstance(signing_policy, Mapping) else ""
    sidecar, _ = _verify_dependency_signature(
        resolved["dependencies_lock"], dependencies, expected_signer,
        cms_probe or _probe_detached_cms,
    )
    if sidecar.resolve() != resolved["dependencies_signature"].resolve():
        raise ReleaseProvenanceError("Dependency CMS input is not the lock-declared sidecar")
    _verify_worker_inventory(worker, resolved["worker_manifest"], worker_root)
    if input_ids == modern_ids:
        expected_components = _approved_inventory_components(
            resolved["component_inventory"], resolved["component_approvals"],
            resolved["third_party_notices"], root,
        )
    else:
        raw_components = dependencies.get("components", dependencies.get("dependencies"))
        if not isinstance(raw_components, list):
            raise ReleaseProvenanceError("Dependency component inventory is missing")
        notice_reference = {
            "file": resolved["third_party_notices"].relative_to(root).as_posix(),
            "sha256": _digest(resolved["third_party_notices"]),
        }
        expected_components = [
            _normalize_component(item, notices, notice_reference)
            for item in raw_components if isinstance(item, Mapping)
        ]
        if len(expected_components) != len(raw_components):
            raise ReleaseProvenanceError("Dependency component inventory is malformed")
    expected_components.sort(key=lambda item: item["id"])
    if sbom.get("components") != expected_components:
        raise ReleaseProvenanceError("SBOM components do not exactly match the approved dependency inventory")
    return {
        "contract": "spike/windows-release-provenance-verification/v1",
        "status": "passed",
        "production_qualified": False,
        "provenance_sha256": _digest(provenance_file),
        "sbom_sha256": _digest(sbom_file),
        "component_count": len(expected_components),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--sbom", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--worker-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = verify_release_provenance(
            args.provenance, args.sbom, args.artifact_root,
            worker_root=args.worker_root,
        )
    except ReleaseProvenanceError as exc:
        raise SystemExit(f"Windows release provenance rejected: {exc}") from exc
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
