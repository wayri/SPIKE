"""Build deterministic, offline Windows release SBOM and provenance evidence.

This is a post-signing evidence builder.  It never changes installer bytes and
never promotes a production candidate to a qualified release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]

SBOM_CONTRACT = "spike/windows-release-sbom/v1"
PROVENANCE_CONTRACT = "spike/windows-release-provenance/v1"
INSTALLER_CONTRACT = "spike/windows-installer-manifest/v2"
WORKER_CONTRACT = "spike/packaged-worker-manifest/v2"
DEPENDENCY_CONTRACT = "spike/dependencies/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXACT_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+!-]*$")
_SAFE_NAME = re.compile(r"^[^\\/:]+$")
_SCOPES = {"bundled", "build-only", "external-not-distributed"}
_INTEGRITY_ALGORITHMS = {
    "sha256", "sha512-sri", "cargo-sha256", "installed-record-sha256"
}
_MUTABLE_VERSION_WORDS = {
    "bundled", "latest", "unselected", "optional-pinned", "pinned-per-release",
    "externally-provisioned-pinned-per-platform", "customer-supplied",
}


class ReleaseProvenanceError(ValueError):
    """Raised when release provenance inputs are incomplete or inconsistent."""


def _validate_contract(document: Mapping[str, Any], schema_name: str) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise ReleaseProvenanceError(
            "jsonschema is required to validate public release evidence contracts"
        ) from exc
    schema = _load_object(ROOT / "schemas" / schema_name, f"{schema_name} schema")
    try:
        Draft202012Validator(schema).validate(document)
    except Exception as exc:
        raise ReleaseProvenanceError(f"Generated evidence violates {schema_name}: {exc}") from exc


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseProvenanceError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseProvenanceError(f"{label} must be a JSON object: {path}")
    return value


def _safe_basename(value: Any, label: str) -> str:
    name = str(value or "")
    if not name or not _SAFE_NAME.fullmatch(name) or name in {".", ".."} or ".." in name:
        raise ReleaseProvenanceError(f"{label} must be a safe basename")
    return name


def _safe_relative_name(value: Any, label: str) -> str:
    name = str(value or "").replace("\\", "/")
    pure = PurePosixPath(name)
    if (
        not name or name.startswith("/") or ":" in name
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ReleaseProvenanceError(f"{label} must be a safe relative file path")
    return pure.as_posix()


def _reference(path: Path, root: Path) -> dict[str, str]:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ReleaseProvenanceError(f"Evidence file is outside the artifact root: {path}") from exc
    return {"file": _safe_relative_name(relative, "evidence file"), "sha256": _digest(path)}


def _validate_digest(value: Any, label: str) -> str:
    digest = str(value or "").lower()
    if _SHA256.fullmatch(digest) is None:
        raise ReleaseProvenanceError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _normalize_component(
    raw: Mapping[str, Any], notices: str, notice_reference: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    identifier = str(raw.get("id", "")).strip()
    name = str(raw.get("name", identifier)).strip()
    version = str(raw.get("version", "")).strip()
    ecosystem = str(raw.get("ecosystem", "")).strip().lower()
    license_expression = str(raw.get("license", "")).strip()
    scope = str(raw.get("scope", "")).strip()
    purl = str(raw.get("purl", "")).strip()
    raw_notice = raw.get("notice")
    integrity = raw.get("integrity")
    if not identifier or not name or not ecosystem or not license_expression or not purl:
        raise ReleaseProvenanceError(
            f"Dependency component {identifier or '<missing>'!r} lacks identity, purl, ecosystem, or license"
        )
    if (
        not version or _EXACT_VERSION.fullmatch(version) is None
        or any(mark in version for mark in "*<>=~^")
        or version.lower() in _MUTABLE_VERSION_WORDS
        or not any(character.isdigit() for character in version)
    ):
        raise ReleaseProvenanceError(f"Dependency component {identifier!r} is not exactly versioned")
    if scope not in _SCOPES:
        raise ReleaseProvenanceError(f"Dependency component {identifier!r} has an unsupported scope")
    if license_expression.lower() in {"unknown", "unlicensed", "pending", "tbd"}:
        raise ReleaseProvenanceError(f"Dependency component {identifier!r} has an unreviewed license")
    if not isinstance(integrity, Mapping):
        raise ReleaseProvenanceError(f"Dependency component {identifier!r} lacks integrity evidence")
    algorithm = str(integrity.get("algorithm", "")).strip()
    value = str(integrity.get("value", "")).strip()
    if algorithm not in _INTEGRITY_ALGORITHMS or not value:
        raise ReleaseProvenanceError(f"Dependency component {identifier!r} has invalid integrity evidence")
    if algorithm in {"sha256", "cargo-sha256", "installed-record-sha256"} and _SHA256.fullmatch(value.lower()) is None:
        raise ReleaseProvenanceError(f"Dependency component {identifier!r} has invalid SHA-256 integrity")
    if algorithm == "sha512-sri" and not value.startswith("sha512-"):
        raise ReleaseProvenanceError(f"Dependency component {identifier!r} has invalid SRI integrity")
    notice_marker = ""
    if isinstance(raw_notice, str):
        notice_marker = raw_notice.strip()
    elif isinstance(raw_notice, Mapping):
        notice_marker = str(raw_notice.get("component", raw_notice.get("marker", ""))).strip()
    if scope == "bundled":
        if raw.get("redistribution_approved") is not True:
            raise ReleaseProvenanceError(
                f"Bundled dependency component {identifier!r} lacks explicit redistribution approval"
            )
        if ("GPL" in license_expression or "Proprietary" in license_expression) and raw.get("reciprocal_compliance_approved") is not True:
            raise ReleaseProvenanceError(
                f"Bundled dependency component {identifier!r} lacks reciprocal/proprietary compliance approval"
            )
        if not notice_marker or notice_marker not in notices:
            raise ReleaseProvenanceError(
                f"Bundled dependency component {identifier!r} lacks a matching approved notice"
            )
        notice_status = "included"
    else:
        notice_status = "not-required"
    if notice_reference is None:
        supplied = raw_notice if isinstance(raw_notice, Mapping) else {}
        notice_file = _safe_relative_name(supplied.get("file"), "component notice file")
        notice_digest = _validate_digest(supplied.get("sha256"), "component notice digest")
    else:
        notice_file = _safe_relative_name(notice_reference.get("file"), "component notice file")
        notice_digest = _validate_digest(notice_reference.get("sha256"), "component notice digest")
    return {
        "id": identifier,
        "purl": purl,
        "name": name,
        "version": version,
        "ecosystem": ecosystem,
        "license": license_expression,
        "scope": scope,
        "integrity": {"algorithm": algorithm, "value": value},
        "notice": {"status": notice_status, "file": notice_file, "sha256": notice_digest},
    }


def _installer_identities(manifest: Mapping[str, Any], artifact_root: Path) -> dict[str, dict[str, str]]:
    if manifest.get("contract") != INSTALLER_CONTRACT:
        raise ReleaseProvenanceError("Release provenance requires a v2 signed-candidate installer manifest")
    if manifest.get("channel") != "production-candidate" or manifest.get("release_state") != "production-candidate":
        raise ReleaseProvenanceError("Installer manifest is not a production candidate")
    if manifest.get("production_qualified") is not False:
        raise ReleaseProvenanceError("Installer manifest must not claim production qualification")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 2:
        raise ReleaseProvenanceError("Installer manifest must contain exactly MSI and NSIS artifacts")
    identities: dict[str, dict[str, str]] = {}
    for record in files:
        if not isinstance(record, Mapping):
            raise ReleaseProvenanceError("Installer manifest contains a malformed artifact")
        kind = str(record.get("kind", ""))
        if kind not in {"msi", "nsis"} or kind in identities:
            raise ReleaseProvenanceError("Installer manifest must contain one MSI and one NSIS artifact")
        name = _safe_basename(record.get("file"), f"{kind} installer file")
        path = artifact_root / name
        expected = _validate_digest(record.get("sha256"), f"{kind} installer digest")
        if not path.is_file() or _digest(path) != expected:
            raise ReleaseProvenanceError(f"{kind} installer bytes do not match the manifest")
        if path.stat().st_size != int(record.get("size", -1)):
            raise ReleaseProvenanceError(f"{kind} installer size does not match the manifest")
        signature = record.get("authenticode")
        if not isinstance(signature, Mapping) or signature.get("status") != "Valid":
            raise ReleaseProvenanceError(f"{kind} installer lacks valid Authenticode metadata")
        identities[kind] = {
            "identity": f"windows-{kind}", "file": name, "sha256": expected
        }
    return {"msi": identities["msi"], "nsis": identities["nsis"]}


def _verify_worker_inventory(
    worker: Mapping[str, Any],
    worker_manifest_path: Path,
    worker_root: str | Path | None = None,
) -> None:
    worker_files = worker.get("files")
    if not isinstance(worker_files, list) or not worker_files:
        raise ReleaseProvenanceError("Worker manifest has no packaged-file inventory")
    resolved_worker_root = (
        Path(worker_root).resolve()
        if worker_root is not None
        else (worker_manifest_path.parent / "spike-worker").resolve()
    )
    seen: set[str] = set()
    for record in worker_files:
        if not isinstance(record, Mapping):
            raise ReleaseProvenanceError("Worker manifest contains a malformed file record")
        member = _safe_relative_name(record.get("path"), "worker member")
        if member in seen:
            raise ReleaseProvenanceError("Worker manifest contains duplicate member paths")
        seen.add(member)
        path = (resolved_worker_root / member).resolve()
        try:
            path.relative_to(resolved_worker_root)
        except ValueError as exc:
            raise ReleaseProvenanceError("Worker member resolves outside the worker root") from exc
        expected = _validate_digest(record.get("sha256"), "worker member digest")
        try:
            expected_size = int(record.get("size", -1))
        except (TypeError, ValueError):
            expected_size = -1
        if not path.is_file() or path.stat().st_size != expected_size or _digest(path) != expected:
            raise ReleaseProvenanceError(f"Worker member does not match its manifest: {member}")


def _probe_detached_cms(
    content_path: Path, signature_path: Path, expected_thumbprint: str,
) -> Mapping[str, Any]:
    powershell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    helper = ROOT / "scripts" / "windows_cms.ps1"
    if not powershell.is_file() or not helper.is_file():
        raise ReleaseProvenanceError("Windows PowerShell CMS verification is unavailable")
    quote = lambda value: str(value).replace("'", "''")
    expression = (
        f". '{quote(helper)}'; "
        f"Get-SpikeDetachedCmsMetadata '{quote(content_path)}' '{quote(signature_path)}' "
        f"'{quote(expected_thumbprint)}' | ConvertTo-Json -Compress"
    )
    process = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", expression],
        cwd=ROOT, text=True, capture_output=True, check=False, timeout=60,
    )
    if process.returncode != 0:
        raise ReleaseProvenanceError(
            f"Detached dependency CMS verification failed: {process.stderr.strip()}"
        )
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseProvenanceError("Detached dependency CMS verifier returned invalid JSON") from exc
    if not isinstance(result, Mapping):
        raise ReleaseProvenanceError("Detached dependency CMS verifier returned invalid metadata")
    return result


def _verify_dependency_signature(
    dependency_path: Path,
    dependencies: Mapping[str, Any],
    expected_thumbprint: str,
    cms_probe: Callable[[Path, Path, str], Mapping[str, Any]],
) -> tuple[Path, Mapping[str, Any]]:
    policy = dependencies.get("signature")
    if not isinstance(policy, Mapping) or policy.get("required") is not True:
        raise ReleaseProvenanceError("Dependency lock must require a detached CMS signature")
    if policy.get("format") != "cms-detached-sha256":
        raise ReleaseProvenanceError("Dependency lock must require detached SHA-256 CMS")
    sidecar_name = _safe_basename(policy.get("sidecar"), "dependency CMS sidecar")
    signature_path = dependency_path.with_name(sidecar_name)
    if not signature_path.is_file():
        raise ReleaseProvenanceError(f"Required dependency CMS sidecar is missing: {signature_path}")
    metadata = cms_probe(dependency_path, signature_path, expected_thumbprint)
    if (
        metadata.get("contract") != "spike/detached-cms-metadata/v1"
        or metadata.get("status") != "Valid" or metadata.get("detached") is not True
        or metadata.get("digest_algorithm") != "sha256"
        or str(metadata.get("signer_thumbprint", "")).upper() != expected_thumbprint.upper()
        or _validate_digest(metadata.get("signature_sha256"), "dependency CMS digest") != _digest(signature_path)
    ):
        raise ReleaseProvenanceError("Dependency CMS metadata does not match the signed release identity")
    return signature_path, metadata


def _approved_inventory_components(
    inventory_path: Path,
    approvals_path: Path,
    notices_path: Path,
    evidence_root: Path,
) -> list[dict[str, Any]]:
    from scripts.verify_windows_component_approvals import verify_component_approvals

    verify_component_approvals(inventory_path, approvals_path, notices_path, evidence_root)
    inventory = _load_object(inventory_path, "component inventory")
    approvals = _load_object(approvals_path, "component approvals")
    decisions = {
        str(item.get("purl", "")): item
        for item in approvals.get("approvals", []) if isinstance(item, Mapping)
    }
    components = []
    for item in inventory.get("components", []):
        if not isinstance(item, Mapping):
            raise ReleaseProvenanceError("Component inventory contains a malformed record")
        decision = decisions.get(str(item.get("purl", "")))
        if not isinstance(decision, Mapping):
            raise ReleaseProvenanceError("Approved component decision is missing")
        notice = decision.get("notice")
        if not isinstance(notice, Mapping):
            raise ReleaseProvenanceError("Approved component notice is missing")
        components.append({
            "id": f"c-{str(item.get('identity_sha256', ''))[:24]}",
            "purl": str(item.get("purl", "")), "name": str(item.get("name", "")),
            "version": str(item.get("version", "")), "ecosystem": str(item.get("ecosystem", "")),
            "license": str(decision.get("approved_license_expression", "")),
            "scope": str(item.get("scope", "")), "integrity": dict(item.get("integrity", {})),
            "notice": {
                "status": str(notice.get("status", "")), "file": str(notice.get("file", "")),
                "sha256": str(notice.get("sha256", "")),
            },
        })
    return components


def build_release_provenance(
    installer_manifest_path: str | Path,
    worker_manifest_path: str | Path,
    dependencies_lock_path: str | Path,
    notices_path: str | Path,
    artifact_root: str | Path,
    sbom_path: str | Path,
    provenance_path: str | Path,
    *,
    cms_probe: Callable[[Path, Path, str], Mapping[str, Any]] | None = None,
    component_inventory_path: str | Path | None = None,
    component_approvals_path: str | Path | None = None,
    approval_evidence_root: str | Path | None = None,
    worker_root: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build and write canonical evidence, rejecting incomplete release inputs."""
    installer_path = Path(installer_manifest_path).resolve()
    worker_path = Path(worker_manifest_path).resolve()
    dependency_path = Path(dependencies_lock_path).resolve()
    notice_path = Path(notices_path).resolve()
    root = Path(artifact_root).resolve()
    output_sbom = Path(sbom_path).resolve()
    output_provenance = Path(provenance_path).resolve()
    for path, label in (
        (installer_path, "installer manifest"), (worker_path, "worker manifest"),
        (dependency_path, "dependency lock"), (notice_path, "notice bundle"),
    ):
        if not path.is_file():
            raise ReleaseProvenanceError(f"Required {label} is missing: {path}")
    installer = _load_object(installer_path, "installer manifest")
    worker = _load_object(worker_path, "worker manifest")
    dependencies = _load_object(dependency_path, "dependency lock")
    if worker.get("contract") != WORKER_CONTRACT:
        raise ReleaseProvenanceError("Worker manifest must use spike/packaged-worker-manifest/v2")
    if dependencies.get("manifest") != DEPENDENCY_CONTRACT:
        raise ReleaseProvenanceError("Dependency lock must use spike/dependencies/v1")
    signing_policy = installer.get("signing_policy")
    expected_signer = str(signing_policy.get("expected_signer_thumbprint", "")) if isinstance(signing_policy, Mapping) else ""
    if not re.fullmatch(r"[0-9A-F]{40}", expected_signer):
        raise ReleaseProvenanceError("Installer manifest lacks an exact signing identity")
    dependency_signature, _ = _verify_dependency_signature(
        dependency_path, dependencies, expected_signer, cms_probe or _probe_detached_cms,
    )
    notices = notice_path.read_text(encoding="utf-8")
    lowered = notices.lower()
    if "this register is incomplete" in lowered or "release-blocking" in lowered:
        raise ReleaseProvenanceError("Third-party notices remain explicitly incomplete or release-blocking")
    notice_reference = _reference(notice_path, root)
    modern_inventory = component_inventory_path is not None or component_approvals_path is not None
    if modern_inventory:
        if component_inventory_path is None or component_approvals_path is None:
            raise ReleaseProvenanceError("Component inventory and approval overlay must be supplied together")
        inventory_path = Path(component_inventory_path).resolve()
        approvals_path = Path(component_approvals_path).resolve()
        components = _approved_inventory_components(
            inventory_path, approvals_path, notice_path,
            Path(approval_evidence_root).resolve() if approval_evidence_root else root,
        )
    else:
        raw_components = dependencies.get("components", dependencies.get("dependencies"))
        if not isinstance(raw_components, list) or not raw_components:
            raise ReleaseProvenanceError("Dependency lock contains no release component inventory")
        components = [
            _normalize_component(item, notices, notice_reference)
            for item in raw_components if isinstance(item, Mapping)
        ]
        if len(components) != len(raw_components):
            raise ReleaseProvenanceError("Dependency lock contains a malformed release component")
    components.sort(key=lambda item: item["id"])
    ids = [item["id"] for item in components]
    purls = [item["purl"] for item in components]
    if len(ids) != len(set(ids)) or len(purls) != len(set(purls)):
        raise ReleaseProvenanceError("Release component IDs and purls must be unique")
    _verify_worker_inventory(worker, worker_path, worker_root)

    sbom = {
        "contract": SBOM_CONTRACT,
        "product": "SPIKE",
        "version": str(installer.get("version", "")),
        "application_version": str(installer.get("application_version", "")),
        "channel": "production-candidate",
        "release_state": "production-candidate",
        "production_qualified": False,
        "components": components,
    }
    _validate_contract(sbom, "windows-release-sbom-v1.schema.json")
    output_sbom.parent.mkdir(parents=True, exist_ok=True)
    output_sbom.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inputs = [
        {"id": "dependencies_lock", **_reference(dependency_path, root)},
        {"id": "dependencies_signature", **_reference(dependency_signature, root)},
        {"id": "worker_manifest", **_reference(worker_path, root)},
        {"id": "third_party_notices", **notice_reference},
    ]
    if modern_inventory:
        inputs.extend([
            {"id": "component_inventory", **_reference(inventory_path, root)},
            {"id": "component_approvals", **_reference(approvals_path, root)},
        ])
    inputs.sort(key=lambda item: item["id"])
    provenance = {
        "contract": PROVENANCE_CONTRACT,
        "product": "SPIKE",
        "version": str(installer.get("version", "")),
        "application_version": str(installer.get("application_version", "")),
        "channel": "production-candidate",
        "release_state": "production-candidate",
        "production_qualified": False,
        "installer_manifest": _reference(installer_path, root),
        "installers": _installer_identities(installer, root),
        "inputs": inputs,
        "worker_manifest": _reference(worker_path, root),
        "sbom": _reference(output_sbom, root),
        "notices": notice_reference,
    }
    _validate_contract(provenance, "windows-release-provenance-v1.schema.json")
    output_provenance.parent.mkdir(parents=True, exist_ok=True)
    output_provenance.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return sbom, provenance


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer-manifest", required=True, type=Path)
    parser.add_argument("--worker-manifest", required=True, type=Path)
    parser.add_argument("--dependencies-lock", required=True, type=Path)
    parser.add_argument("--notices", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--sbom-output", required=True, type=Path)
    parser.add_argument("--provenance-output", required=True, type=Path)
    parser.add_argument("--component-inventory", type=Path)
    parser.add_argument("--component-approvals", type=Path)
    parser.add_argument("--approval-evidence-root", type=Path)
    parser.add_argument("--worker-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        build_release_provenance(
            args.installer_manifest, args.worker_manifest, args.dependencies_lock,
            args.notices, args.artifact_root, args.sbom_output, args.provenance_output,
            component_inventory_path=args.component_inventory,
            component_approvals_path=args.component_approvals,
            approval_evidence_root=args.approval_evidence_root,
            worker_root=args.worker_root,
        )
    except ReleaseProvenanceError as exc:
        raise SystemExit(f"Windows release provenance rejected: {exc}") from exc
    print(f"Windows release SBOM: {args.sbom_output.resolve()}")
    print(f"Windows release provenance: {args.provenance_output.resolve()}")
    print("Production qualification remains false; separate acceptance evidence is required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
