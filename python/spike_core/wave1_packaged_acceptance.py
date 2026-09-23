"""Fail-closed evidence composition for Wave 1 packaged assembly acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, Iterable, Mapping

from .project_package import read_project
from .wave1_packaged_mutation import probe_packaged_worker_mutation_roundtrip
REPORT_CONTRACT = "spike/wave1-packaged-acceptance/v1"
HUMAN_EVIDENCE_CONTRACT = "spike/wave1-human-acceptance-evidence/v1"
REPORT_CONTRACT_V2 = "spike/wave1-packaged-acceptance/v2"
HUMAN_EVIDENCE_CONTRACT_V2 = "spike/wave1-human-acceptance-evidence/v2"
INSTALLER_MANIFEST_CONTRACT_V1 = "spike/windows-installer-manifest/v1"
INSTALLER_MANIFEST_CONTRACT_V2 = "spike/windows-installer-manifest/v2"
REQUIRED_HUMAN_CHECKS = (
    "install_launch",
    "file_association",
    "assembly_hierarchy",
    "pixel_views",
    "placement_persistence",
    "reparent_world_pose",
    "topology_snap",
    "structure_persistence",
    "operation_cancellation",
    "upgrade_uninstall",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_THUMBPRINT = re.compile(r"^[0-9A-F]{40}$")
_CHUNK_BYTES = 1024 * 1024
class Wave1AcceptanceError(ValueError):
    """Raised when acceptance evidence is malformed or fails a required check."""
def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_BYTES):
            value.update(chunk)
    return value.hexdigest()
def _check(identifier: str, passed: bool, detail: str, **evidence: Any) -> Dict[str, Any]:
    return {
        "id": identifier,
        "status": "passed" if passed else "failed",
        "detail": detail,
        "evidence": evidence,
    }
def _summary(checks: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    records = list(checks)
    passed = sum(item.get("status") == "passed" for item in records)
    return {"total": len(records), "passed": passed, "failed": len(records) - passed}
def verify_installer_manifest(
    manifest_path: str | Path,
    artifact_dir: str | Path,
    *,
    expected_application_version: str | None = None,
    authenticode_probe: Callable[[Path], Mapping[str, Any]] | None = None,
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    manifest_file = Path(manifest_path)
    root = Path(artifact_dir).resolve()
    raw = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
    contract = raw.get("contract")
    checks: list[Dict[str, Any]] = []
    if contract == INSTALLER_MANIFEST_CONTRACT_V2:
        return _verify_signed_installer_manifest_v2(
            raw, manifest_file, root, expected_application_version,
            authenticode_probe or _probe_windows_authenticode,
        )
    checks.append(_check(
        "installer.manifest_contract",
        contract == INSTALLER_MANIFEST_CONTRACT_V1,
        "Windows installer manifest contract must be v1.",
        contract=raw.get("contract"),
    ))
    files = raw.get("files")
    valid_files = isinstance(files, list) and len(files) == 2
    checks.append(_check(
        "installer.candidate_set", valid_files,
        "The candidate must contain exactly MSI and NSIS artifacts.",
        count=len(files) if isinstance(files, list) else 0,
    ))
    candidates = []
    candidate_suffixes: set[str] = set()
    if isinstance(files, list):
        for index, item in enumerate(files):
            name = str(item.get("file", "")) if isinstance(item, Mapping) else ""
            safe_name = Path(name).name == name and name.lower().endswith((".msi", ".exe"))
            path = root / name
            actual = _digest(path) if safe_name and path.is_file() else ""
            actual_size = path.stat().st_size if safe_name and path.is_file() else -1
            expected = str(item.get("sha256", "")).lower() if isinstance(item, Mapping) else ""
            try:
                expected_size = int(item.get("size", -1)) if isinstance(item, Mapping) else -1
            except (TypeError, ValueError):
                expected_size = -1
            passed = (
                safe_name
                and _SHA256.fullmatch(expected) is not None
                and actual == expected
                and expected_size >= 0
                and actual_size == expected_size
            )
            checks.append(_check(
                f"installer.artifact_{index}", passed,
                "Installer path, SHA-256, and manifest identity must match.",
                file=name, expected_sha256=expected, actual_sha256=actual,
                expected_size=expected_size, actual_size=actual_size,
            ))
            if safe_name:
                candidate_suffixes.add(Path(name).suffix.lower())
            candidates.append({
                "file": name, "sha256": expected,
                "size": expected_size,
                "authenticode": str(item.get("authenticode", "")) if isinstance(item, Mapping) else "",
            })
    identity_ok = (
        raw.get("product") == "SPIKE"
        and raw.get("channel") == "engineering-preview"
        and isinstance(raw.get("version"), str)
        and bool(re.fullmatch(r"\d+\.\d+\.\d+", raw["version"]))
        and isinstance(raw.get("application_version"), str)
        and bool(raw["application_version"].strip())
        and (expected_application_version is None or raw["application_version"] == expected_application_version)
        and candidate_suffixes == {".msi", ".exe"}
    )
    checks.append(_check(
        "installer.release_identity", identity_ok,
        "Product, preview channel, application/MSI versions, and MSI/NSIS candidate types must match.",
        product=raw.get("product"), channel=raw.get("channel"), version=raw.get("version"),
        application_version=raw.get("application_version"),
        expected_application_version=expected_application_version,
        candidate_types=sorted(candidate_suffixes),
    ))
    preview_boundary = raw.get("production_qualified") is False and all(
        item.get("authenticode") == "NotSigned" for item in candidates
    )
    checks.append(_check(
        "installer.preview_boundary", preview_boundary,
        "This candidate is an unsigned engineering preview and must not claim production qualification.",
        production_qualified=raw.get("production_qualified"),
    ))
    return checks, {
        "contract": INSTALLER_MANIFEST_CONTRACT_V1,
        "manifest": str(manifest_file.resolve()),
        "manifest_sha256": _digest(manifest_file),
        "generated_at": raw.get("generated_at"),
        "version": raw.get("version"),
        "application_version": raw.get("application_version"),
        "channel": raw.get("channel"),
        "artifacts": candidates,
    }
def _verify_signed_installer_manifest_v2(
    raw: Mapping[str, Any], manifest_file: Path, root: Path, expected_application_version: str | None,
    authenticode_probe: Callable[[Path], Mapping[str, Any]],
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    """Verify a post-signing candidate without allowing signing to assert qualification."""
    checks = [_check(
        "installer.manifest_contract", True,
        "Windows installer manifest contract is v2.", contract=raw.get("contract"),
    )]
    files = raw.get("files")
    valid_files = isinstance(files, list) and len(files) == 2
    checks.append(_check(
        "installer.candidate_set", valid_files,
        "The signed candidate must contain exactly one MSI and one NSIS artifact.",
        count=len(files) if isinstance(files, list) else 0,
    ))
    policy = raw.get("signing_policy") if isinstance(raw.get("signing_policy"), Mapping) else {}
    expected_signer = str(policy.get("expected_signer_thumbprint", "")).upper()
    policy_ok = (
        policy.get("required") is True
        and _THUMBPRINT.fullmatch(expected_signer) is not None
        and policy.get("digest_algorithm") == "sha256"
        and policy.get("timestamp_required") is True
        and policy.get("timestamp_protocol") == "rfc3161"
    )
    candidates: list[Dict[str, Any]] = []
    candidate_kinds: set[str] = set()
    if isinstance(files, list):
        for index, item in enumerate(files):
            name = str(item.get("file", "")) if isinstance(item, Mapping) else ""
            kind = str(item.get("kind", "")) if isinstance(item, Mapping) else ""
            expected_suffix = ".msi" if kind == "msi" else ".exe" if kind == "nsis" else None
            safe_name = expected_suffix is not None and Path(name).name == name and "\\" not in name and name.lower().endswith(expected_suffix)
            path = root / name
            expected = str(item.get("sha256", "")).lower() if isinstance(item, Mapping) else ""
            try:
                expected_size = int(item.get("size", -1)) if isinstance(item, Mapping) else -1
            except (TypeError, ValueError):
                expected_size = -1
            actual = _digest(path) if safe_name and path.is_file() else ""
            actual_size = path.stat().st_size if safe_name and path.is_file() else -1
            signature = item.get("authenticode") if isinstance(item, Mapping) and isinstance(item.get("authenticode"), Mapping) else {}
            signer = str(signature.get("signer_thumbprint", "")).upper()
            authority = str(signature.get("timestamp_authority_thumbprint", "")).upper()
            try:
                actual_signature = dict(authenticode_probe(path)) if safe_name and path.is_file() else {}
            except (OSError, ValueError, subprocess.SubprocessError):
                actual_signature = {}
            actual_status = str(actual_signature.get("status", ""))
            actual_signer = str(actual_signature.get("signer_thumbprint", "")).upper()
            actual_authority = str(actual_signature.get("timestamp_authority_thumbprint", "")).upper()
            signature_ok = (
                policy_ok and signature.get("status") == "Valid"
                and signature.get("file_digest_algorithm") == "sha256"
                and signer == expected_signer and _THUMBPRINT.fullmatch(signer) is not None
                and signature.get("timestamp_protocol") == "rfc3161"
                and _THUMBPRINT.fullmatch(authority) is not None
                and actual_status == "Valid" and actual_signer == signer and actual_authority == authority
            )
            passed = safe_name and _SHA256.fullmatch(expected) is not None and actual == expected and expected_size >= 0 and actual_size == expected_size and signature_ok
            checks.append(_check(
                f"installer.artifact_{index}", passed,
                "Signed installer path, SHA-256, size, signer, and RFC 3161 timestamp identity must match.",
                file=name, kind=kind, expected_sha256=expected, actual_sha256=actual,
                expected_size=expected_size, actual_size=actual_size, signer_thumbprint=signer,
                timestamp_authority_thumbprint=authority, actual_authenticode_status=actual_status,
                actual_signer_thumbprint=actual_signer,
                actual_timestamp_authority_thumbprint=actual_authority,
            ))
            if safe_name:
                candidate_kinds.add(kind)
            candidates.append({"file": name, "kind": kind, "sha256": expected, "size": expected_size, "authenticode": dict(signature)})
    identity_ok = (
        raw.get("product") == "SPIKE" and raw.get("channel") == "production-candidate"
        and raw.get("release_state") == "production-candidate" and raw.get("production_qualified") is False
        and isinstance(raw.get("license_key_id"), str) and bool(raw["license_key_id"].strip())
        and isinstance(raw.get("version"), str) and bool(re.fullmatch(r"\d+\.\d+\.\d+", raw["version"]))
        and isinstance(raw.get("application_version"), str) and bool(raw["application_version"].strip())
        and (expected_application_version is None or raw["application_version"] == expected_application_version)
        and candidate_kinds == {"msi", "nsis"}
    )
    checks.append(_check(
        "installer.release_identity", identity_ok,
        "Signed candidate identity must be SPIKE production-candidate with MSI and NSIS artifacts.",
        channel=raw.get("channel"), release_state=raw.get("release_state"), candidate_types=sorted(candidate_kinds),
    ))
    checks.append(_check(
        "installer.production_candidate_boundary", policy_ok and raw.get("production_qualified") is False,
        "Authenticode establishes a production candidate only; it cannot assert production qualification.",
        production_qualified=raw.get("production_qualified"), signing_policy=dict(policy),
    ))
    return checks, {
        "contract": INSTALLER_MANIFEST_CONTRACT_V2,
        "manifest": str(manifest_file.resolve()), "manifest_sha256": _digest(manifest_file),
        "generated_at": raw.get("generated_at"), "version": raw.get("version"),
        "application_version": raw.get("application_version"), "channel": raw.get("channel"),
        "license_key_id": raw.get("license_key_id"),
        "release_state": raw.get("release_state"), "production_qualified": False,
        "signing_policy": dict(policy), "artifacts": candidates,
    }
def _probe_windows_authenticode(path: Path) -> Mapping[str, Any]:
    """Inspect the actual Windows Authenticode envelope; manifest metadata is never sufficient."""
    if os.name != "nt":
        return {"status": "Unavailable", "signer_thumbprint": "", "timestamp_authority_thumbprint": ""}
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell = system_root / "System32/WindowsPowerShell/v1.0/powershell.exe"
    if not powershell.is_file():
        return {"status": "Unavailable", "signer_thumbprint": "", "timestamp_authority_thumbprint": ""}
    command = (
        "$s=Get-AuthenticodeSignature -LiteralPath $env:SPIKE_ACCEPTANCE_INSTALLER_PATH;"
        "$o=[ordered]@{status=$s.Status.ToString();"
        "signer_thumbprint=if($s.SignerCertificate){$s.SignerCertificate.Thumbprint}else{''};"
        "timestamp_authority_thumbprint=if($s.TimeStamperCertificate){$s.TimeStamperCertificate.Thumbprint}else{''}};"
        "$o|ConvertTo-Json -Compress"
    )
    environment = os.environ.copy()
    environment["SPIKE_ACCEPTANCE_INSTALLER_PATH"] = str(path.resolve())
    completed = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
        text=True, capture_output=True, check=False, timeout=30, env=environment,
    )
    if completed.returncode != 0:
        raise ValueError("Windows Authenticode inspection failed.")
    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("Windows Authenticode inspection returned invalid JSON.") from error
    if not isinstance(raw, Mapping):
        raise ValueError("Windows Authenticode inspection returned an invalid record.")
    return raw


def verify_packaged_worker_manifest(manifest_path: str | Path, worker_root: str | Path) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    manifest_file = Path(manifest_path)
    root = Path(worker_root).resolve()
    raw = json.loads(manifest_file.read_text(encoding="utf-8"))
    checks = [_check(
        "worker.manifest_contract",
        raw.get("contract") == "spike/packaged-worker-manifest/v2",
        "Packaged worker manifest contract must be v2.",
        contract=raw.get("contract"),
    )]
    files = raw.get("files")
    failures: list[str] = []
    if not isinstance(files, list) or not files or len(files) > 4096:
        failures.append("invalid file inventory")
        files = []
    for item in files:
        relative = str(item.get("path", "")) if isinstance(item, Mapping) else ""
        posix = PurePosixPath(relative)
        safe = bool(relative) and not posix.is_absolute() and ".." not in posix.parts
        path = root.joinpath(*posix.parts) if safe else root / "__invalid__"
        expected = str(item.get("sha256", "")).lower() if isinstance(item, Mapping) else ""
        expected_size = int(item.get("size", -1)) if isinstance(item, Mapping) else -1
        if (
            not safe or not path.is_file() or _SHA256.fullmatch(expected) is None
            or path.stat().st_size != expected_size or _digest(path) != expected
        ):
            failures.append(relative or "<missing path>")
    checks.append(_check(
        "worker.member_integrity", not failures,
        "Every packaged worker member must match its declared size and SHA-256.",
        member_count=len(files), failed=failures[:10],
    ))
    benchmark = raw.get("benchmark_summary") if isinstance(raw.get("benchmark_summary"), Mapping) else {}
    benchmark_passed = benchmark.get("total") == 15 and benchmark.get("passed") == 15 and benchmark.get("failed") == 0
    checks.append(_check(
        "worker.benchmark_summary", benchmark_passed,
        "The packaged regression corpus must pass all 15 cases.", summary=dict(benchmark),
    ))
    qualification = raw.get("runtime_qualification") if isinstance(raw.get("runtime_qualification"), Mapping) else {}
    parity_passed = qualification.get("status") == "passed" and qualification.get("summary") == {"total": 8, "passed": 8, "failed": 0}
    checks.append(_check(
        "worker.embedded_runtime_parity", parity_passed,
        "The worker manifest must carry a passing 8/8 runtime-parity record.",
        qualification=dict(qualification),
    ))
    arrow_probe = raw.get("geometry_arrow_probe") if isinstance(raw.get("geometry_arrow_probe"), Mapping) else {}
    arrow_passed = (
        arrow_probe.get("contract") == "spike/packaged-arrow-probe/v1"
        and arrow_probe.get("status") == "passed"
        and arrow_probe.get("table_contract") == "spike/copper-geometry-arrow/v4"
        and arrow_probe.get("rows") == 4
        and arrow_probe.get("retained_unresolved_occurrences") == 1
        and _SHA256.fullmatch(str(arrow_probe.get("artifact_sha256", ""))) is not None
        and bool(str(arrow_probe.get("design_id", "")).strip())
    )
    checks.append(_check(
        "worker.geometry_arrow_round_trip", arrow_passed,
        "The frozen worker must source-verify Arrow v4 geometry and package-bind one retained-unresolved occurrence without treating it as copper.",
        probe=dict(arrow_probe),
    ))
    return checks, {
        "manifest": str(manifest_file.resolve()),
        "worker_root": str(root),
        "worker_version": raw.get("worker_version"),
        "member_count": len(files),
        "geometry_arrow_probe": dict(arrow_probe),
    }
def probe_packaged_worker_health(executable: str | Path, *, cwd: str | Path) -> tuple[Dict[str, Any], Dict[str, Any]]:
    path = Path(executable).resolve()
    request = json.dumps({"id": "wave1-acceptance-health", "method": "health", "params": {}}) + "\n"
    completed = subprocess.run(
        [str(path)], cwd=str(Path(cwd).resolve()), input=request, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    response: Dict[str, Any] = {}
    try:
        response = json.loads(completed.stdout.strip())
    except json.JSONDecodeError:
        pass
    result = response.get("result") if isinstance(response.get("result"), Mapping) else {}
    passed = completed.returncode == 0 and response.get("ok") is True and result.get("status") == "ready"
    return _check(
        "worker.extracted_health", passed,
        "The worker launched from the extracted image must report ready.",
        returncode=completed.returncode, health=dict(result), stderr=completed.stderr[-1000:],
    ), dict(result)


def probe_packaged_worker_fixture(
    executable: str | Path,
    *,
    cwd: str | Path,
    fixture: str | Path,
    manifest_payload_sha256: str,
    model_ids: Iterable[str],
    shape_ids: Iterable[str],
) -> Dict[str, Any]:
    path = Path(executable).resolve()
    project = Path(fixture).resolve()
    model_ids = list(model_ids)
    shape_ids = list(shape_ids)
    requests = [
        {"id": "wave1-fixture-open", "method": "read_project_package", "params": {"path": str(project)}},
        {"id": "wave1-fixture-models", "method": "read_project_model_artifacts", "params": {
            "path": str(project), "model_ids": model_ids,
            "expected_manifest_payload_sha256": manifest_payload_sha256,
        }},
        {"id": "wave1-fixture-selectors", "method": "read_project_package_shape_selector_previews", "params": {
            "path": str(project), "shape_ids": shape_ids,
            "expected_manifest_payload_sha256": manifest_payload_sha256,
        }},
    ]
    completed = subprocess.run(
        [str(path)], cwd=str(Path(cwd).resolve()),
        input="".join(json.dumps(item) + "\n" for item in requests), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    responses: list[Mapping[str, Any]] = []
    try:
        responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    except json.JSONDecodeError:
        responses = []
    opened = responses[0].get("result", {}) if len(responses) > 0 and isinstance(responses[0], Mapping) else {}
    projected = opened.get("project", {}) if isinstance(opened, Mapping) else {}
    design = projected.get("design", {}) if isinstance(projected, Mapping) else {}
    models = responses[1].get("result", {}) if len(responses) > 1 and isinstance(responses[1], Mapping) else {}
    selectors = responses[2].get("result", {}) if len(responses) > 2 and isinstance(responses[2], Mapping) else {}
    model_artifacts = models.get("artifacts", []) if isinstance(models, Mapping) else []
    selector_artifacts = selectors.get("artifacts", []) if isinstance(selectors, Mapping) else []
    passed = (
        completed.returncode == 0
        and len(responses) == 3
        and all(response.get("ok") is True for response in responses)
        and isinstance(design, Mapping)
        and bool(str(design.get("source_board", "")))
        and len(model_artifacts) == len(model_ids)
        and len(selector_artifacts) == len(shape_ids)
    )
    return _check(
        "worker.fixture_desktop_projection", passed,
        "The packaged worker must project the embedded active design and return every visual and exact-selector artifact.",
        response_count=len(responses), model_count=len(model_artifacts),
        selector_count=len(selector_artifacts), source_bytes=len(str(design.get("source_board", ""))) if isinstance(design, Mapping) else 0,
        errors=[response.get("error") for response in responses if response.get("ok") is not True],
        stderr=completed.stderr[-1000:],
    )
def verify_runtime_report(path: str | Path) -> tuple[Dict[str, Any], Dict[str, Any]]:
    report_path = Path(path)
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    passed = (
        raw.get("contract") == "spike/release-runtime-qualification/v1"
        and raw.get("status") == "passed"
        and raw.get("summary") == {"total": 8, "passed": 8, "failed": 0}
        and raw.get("source_snapshot_digest") == raw.get("packaged_snapshot_digest")
        and _SHA256.fullmatch(str(raw.get("source_snapshot_digest", ""))) is not None
    )
    return _check(
        "worker.current_runtime_parity", passed,
        "Fresh source and packaged runtime snapshots must match across all 8 checks.",
        report=str(report_path.resolve()), generated_at=raw.get("generated_at"),
        source_snapshot_digest=raw.get("source_snapshot_digest"),
        packaged_snapshot_digest=raw.get("packaged_snapshot_digest"),
    ), raw
def verify_acceptance_fixture(path: str | Path) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    project_path = Path(path)
    opened = read_project(project_path, include_members=True)
    payload = opened.payload
    assembly = payload.get("assembly_ir") if isinstance(payload.get("assembly_ir"), Mapping) else {}
    retained = payload.get("assembly_designs") if isinstance(payload.get("assembly_designs"), Mapping) else {}
    index = payload.get("assembly_package_shapes") if isinstance(payload.get("assembly_package_shapes"), Mapping) else {}
    models = payload.get("models") if isinstance(payload.get("models"), Mapping) else {}
    boards = assembly.get("boards") if isinstance(assembly.get("boards"), list) else []
    harnesses = assembly.get("harnesses") if isinstance(assembly.get("harnesses"), list) else []
    parts = assembly.get("parts") if isinstance(assembly.get("parts"), list) else []
    designs = retained.get("designs") if isinstance(retained.get("designs"), list) else []
    shapes = index.get("shapes") if isinstance(index.get("shapes"), list) else []
    model_rows = models.get("models") if isinstance(models.get("models"), list) else []
    checks = [
        _check("fixture.package_reopen", not opened.migrated and len(opened.members) >= 20, "The canonical v3 fixture must reopen with retained members.", member_count=len(opened.members)),
        _check("fixture.multi_design", len(designs) == 2 and len(boards) == 2, "The fixture must retain exactly two complete designs and board instances.", designs=len(designs), boards=len(boards)),
        _check("fixture.structure", len(harnesses) >= 1 and len(assembly.get("connector_mappings", [])) >= 1 and len(assembly.get("rigid_flex_links", [])) >= 1, "Harness, connector mapping, and rigid/flex structure must be present.", harnesses=len(harnesses)),
        _check("fixture.mcad_parts", len(parts) >= 3, "The fixture must retain two STEP-derived parts and a direct GLB part.", parts=len(parts)),
    ]
    exact_ready = len(shapes) == 2
    for item in shapes:
        extraction = item.get("extraction") if isinstance(item, Mapping) else None
        selector = item.get("selector_preview") if isinstance(item, Mapping) else None
        exact_ready = exact_ready and (
            isinstance(extraction, Mapping)
            and extraction.get("topology_ready") is True
            and extraction.get("solver_ready") is False
            and isinstance(selector, Mapping)
            and selector.get("visual_only") is True
            and selector.get("solver_ready") is False
        )
    checks.append(_check(
        "fixture.exact_shapes", exact_ready,
        "Both STEP parts must own exact topology and visual-only selector previews without solver claims.",
        shapes=len(shapes),
    ))
    step_count = sum(isinstance(item, Mapping) and item.get("model_type") == "step" for item in model_rows)
    glb_count = sum(isinstance(item, Mapping) and item.get("model_type") == "glb" for item in model_rows)
    checks.append(_check(
        "fixture.visual_models", step_count >= 2 and glb_count >= 3,
        "Retained STEP sources, two tessellations, and one direct GLB must be present.",
        step_models=step_count, glb_models=glb_count,
    ))
    return checks, {
        "path": str(project_path.resolve()),
        "manifest_payload_sha256": opened.manifest.get("manifest_payload_sha256"),
        "member_count": len(opened.members), "designs": len(designs), "boards": len(boards),
        "parts": len(parts), "shapes": len(shapes), "solver_ready": False,
        "model_ids": [str(item.get("model_id")) for item in parts if isinstance(item, Mapping)],
        "shape_ids": [str(item.get("shape_id")) for item in shapes if isinstance(item, Mapping)],
    }
def validate_human_evidence(path: str | Path | None) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    if path is None:
        return [_check(
            identifier, False, "Reviewed clean-machine evidence has not been supplied."
        ) for identifier in REQUIRED_HUMAN_CHECKS], {"status": "pending", "evidence": None}
    evidence_path = Path(path)
    raw = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence_contract = raw.get("contract")
    if evidence_contract not in {HUMAN_EVIDENCE_CONTRACT, HUMAN_EVIDENCE_CONTRACT_V2}:
        raise Wave1AcceptanceError("Human evidence uses an unsupported contract.")
    records = raw.get("checks")
    if not isinstance(records, list) or len(records) != len(REQUIRED_HUMAN_CHECKS):
        raise Wave1AcceptanceError("Human evidence must contain the complete Wave 1 check set.")
    by_id = {str(item.get("id", "")): item for item in records if isinstance(item, Mapping)}
    if set(by_id) != set(REQUIRED_HUMAN_CHECKS):
        raise Wave1AcceptanceError("Human evidence check identities are incomplete or duplicated.")
    checks = []
    for identifier in REQUIRED_HUMAN_CHECKS:
        item = by_id[identifier]
        artifacts = item.get("artifacts")
        artifact_ok = isinstance(artifacts, list) and bool(artifacts) and len(artifacts) <= 50
        verified = []
        if isinstance(artifacts, list):
            for record in artifacts:
                relative = str(record.get("path", "")) if isinstance(record, Mapping) else ""
                posix = PurePosixPath(relative)
                safe = (
                    bool(relative)
                    and "\\" not in relative
                    and ":" not in relative
                    and not posix.is_absolute()
                    and ".." not in posix.parts
                )
                artifact = evidence_path.parent.joinpath(*posix.parts) if safe else evidence_path.parent / "__invalid__"
                expected = str(record.get("sha256", "")).lower() if isinstance(record, Mapping) else ""
                matches = safe and artifact.is_file() and _SHA256.fullmatch(expected) is not None and _digest(artifact) == expected
                artifact_ok = artifact_ok and matches
                verified.append({"path": relative, "sha256": expected, "verified": matches})
        if identifier == "pixel_views":
            artifact_ok = artifact_ok and any(
                PurePosixPath(str(record.get("path", ""))).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                for record in artifacts or []
                if isinstance(record, Mapping)
            )
        passed = item.get("status") == "passed" and artifact_ok
        checks.append(_check(identifier, passed, str(item.get("detail", "Reviewed human acceptance evidence.")), artifacts=verified))
    required_text = all(isinstance(raw.get(key), str) and raw.get(key).strip() for key in ("reviewer", "reviewed_at", "installer_sha256", "before_manifest_payload_sha256", "after_manifest_payload_sha256"))
    digests_ok = all(_SHA256.fullmatch(str(raw.get(key, "")).lower()) is not None for key in ("installer_sha256", "before_manifest_payload_sha256", "after_manifest_payload_sha256"))
    if not required_text or not digests_ok:
        raise Wave1AcceptanceError("Human evidence is missing reviewer, timestamp, or SHA-256 identities.")
    try:
        reviewed_at = datetime.fromisoformat(str(raw["reviewed_at"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise Wave1AcceptanceError("Human evidence reviewed_at must be an RFC 3339 timestamp.") from error
    if reviewed_at.tzinfo is None:
        raise Wave1AcceptanceError("Human evidence reviewed_at must include a timezone.")
    environment = raw.get("environment")
    required_environment = ("os", "gpu", "webview2_version", "display_scale_percent")
    if not isinstance(environment, Mapping) or any(key not in environment for key in required_environment):
        raise Wave1AcceptanceError("Human evidence must identify OS, GPU, WebView2, and display scale.")
    try:
        display_scale = float(environment["display_scale_percent"])
    except (TypeError, ValueError) as error:
        raise Wave1AcceptanceError("Human evidence display scale must be numeric.") from error
    if not 50.0 <= display_scale <= 500.0:
        raise Wave1AcceptanceError("Human evidence display scale must be between 50 and 500 percent.")
    if raw["before_manifest_payload_sha256"].lower() == raw["after_manifest_payload_sha256"].lower():
        raise Wave1AcceptanceError("Human evidence must bind the changed project manifest after persistence checks.")
    installer_file = None
    installer_manifest_sha256 = None
    authenticode: Dict[str, Any] = {}
    if evidence_contract == HUMAN_EVIDENCE_CONTRACT_V2:
        installer_file = str(raw.get("installer_file", ""))
        installer_manifest_sha256 = str(raw.get("installer_manifest_sha256", "")).lower()
        supplied_authenticode = raw.get("authenticode")
        authenticode = dict(supplied_authenticode) if isinstance(supplied_authenticode, Mapping) else {}
        signer = str(authenticode.get("signer_thumbprint", "")).upper()
        authority = str(authenticode.get("timestamp_authority_thumbprint", "")).upper()
        if (
            Path(installer_file).name != installer_file or "\\" in installer_file
            or _SHA256.fullmatch(installer_manifest_sha256) is None
            or _THUMBPRINT.fullmatch(signer) is None
            or authenticode.get("timestamp_protocol") != "rfc3161"
            or _THUMBPRINT.fullmatch(authority) is None
        ):
            raise Wave1AcceptanceError("Signed-candidate human evidence is missing exact installer, manifest, signer, or RFC 3161 timestamp identity.")
    harness_records = []
    for item in records:
        if not isinstance(item, Mapping) or not isinstance(item.get("artifacts"), list):
            continue
        for artifact in item["artifacts"]:
            if isinstance(artifact, Mapping) and PurePosixPath(str(artifact.get("path", ""))).name == "harness-run.json":
                harness_records.append(artifact)
    if len(harness_records) != 1:
        raise Wave1AcceptanceError("Human evidence must attach exactly one clean-machine harness-run.json record.")
    harness_relative = str(harness_records[0].get("path", ""))
    harness_posix = PurePosixPath(harness_relative)
    harness_path = evidence_path.parent.joinpath(*harness_posix.parts)
    try:
        harness = json.loads(harness_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Wave1AcceptanceError("Clean-machine harness record is unreadable.") from error
    if not isinstance(harness, Mapping) or harness.get("contract") != "spike/wave1-clean-machine-harness/v2":
        raise Wave1AcceptanceError("Human evidence must attach a v2 clean-machine harness; legacy v1 is not eligible for qualification.")
    isolated_providers = {"windows-sandbox", "hyperv-vm", "external-clean-vm", "physical-clean-machine"}
    if harness.get("provider") not in isolated_providers or harness.get("eligible_for_human_review") is not True:
        raise Wave1AcceptanceError("Clean-machine harness provider is not eligible for human review.")
    if _SHA256.fullmatch(str(harness.get("inputs_sha256", "")).lower()) is None:
        raise Wave1AcceptanceError("Clean-machine harness inputs identity is missing or invalid.")
    harness_environment = harness.get("environment")
    residue = harness_environment.get("pre_install_spike_residue") if isinstance(harness_environment, Mapping) else None
    required_harness_environment = {"provider", "os", "gpu", "webview2_version", "display_scale_percent", "process_path_entries", "pre_install_spike_residue"}
    environment_ok = (
        isinstance(harness_environment, Mapping)
        and required_harness_environment.issubset(harness_environment)
        and harness_environment.get("provider") == harness.get("provider")
        and isinstance(harness_environment.get("os"), Mapping) and bool(harness_environment["os"])
        and isinstance(harness_environment.get("gpu"), list) and bool(harness_environment["gpu"])
        and isinstance(residue, Mapping)
        and {"uninstall_products", "install_paths", "file_association"}.issubset(residue)
        and isinstance(residue.get("file_association"), Mapping) and bool(residue["file_association"])
        and dict(harness_environment) == dict(environment)
    )
    if not environment_ok:
        raise Wave1AcceptanceError("Clean-machine harness environment does not bind the human evidence environment.")
    mechanics = harness.get("mechanics")
    mechanics_ok = (
        isinstance(mechanics, Mapping)
        and mechanics.get("staged_hashes_verified") is True
        and mechanics.get("installer_started") is True
        and mechanics.get("installer_exit_code") == 0
        and isinstance(mechanics.get("installed_product"), list) and bool(mechanics["installed_product"])
        and isinstance(mechanics.get("spike_association"), Mapping) and bool(mechanics["spike_association"].get("command"))
        and isinstance(mechanics.get("launched_process_id"), int)
        and mechanics["launched_process_id"] > 0
        and mechanics.get("after_project_supplied") is True
    )
    if not mechanics_ok:
        raise Wave1AcceptanceError("Clean-machine harness mechanics are incomplete or unsuccessful.")
    harness_artifacts = harness.get("artifacts")
    required_harness_artifacts = {"after-project.spike", "mechanics.json", "preflight.json", "review-required.json", "inputs.json", "executing-runner.ps1", "environment-attestation.json"}
    verified_harness_artifacts: set[str] = set()
    if not isinstance(harness_artifacts, list) or not 1 <= len(harness_artifacts) <= 100:
        raise Wave1AcceptanceError("Clean-machine harness artifact ledger is missing or unbounded.")
    for artifact_record in harness_artifacts:
        relative = str(artifact_record.get("path", "")) if isinstance(artifact_record, Mapping) else ""
        expected = str(artifact_record.get("sha256", "")).lower() if isinstance(artifact_record, Mapping) else ""
        safe = (
            bool(relative) and PurePosixPath(relative).name == relative
            and "\\" not in relative and ":" not in relative
            and _SHA256.fullmatch(expected) is not None
        )
        artifact_path = harness_path.parent / relative if safe else harness_path.parent / "__invalid__"
        if not safe or not artifact_path.is_file() or _digest(artifact_path) != expected:
            raise Wave1AcceptanceError(f"Clean-machine harness artifact is unsafe, missing, or changed: {relative or '<missing>'}.")
        if relative in verified_harness_artifacts:
            raise Wave1AcceptanceError(f"Clean-machine harness artifact ledger has a duplicate path: {relative}.")
        verified_harness_artifacts.add(relative)
    if not required_harness_artifacts.issubset(verified_harness_artifacts):
        raise Wave1AcceptanceError("Clean-machine harness artifact ledger is incomplete.")
    inputs_path = harness_path.parent / "inputs.json"
    runner_path = harness_path.parent / "executing-runner.ps1"
    try:
        copied_inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Wave1AcceptanceError("Clean-machine harness copied inputs.json is unreadable.") from error
    runner_record = copied_inputs.get("runner") if isinstance(copied_inputs, Mapping) else None
    if (
        _digest(inputs_path) != str(harness.get("inputs_sha256", "")).lower()
        or not isinstance(copied_inputs, Mapping) or copied_inputs.get("run_id") != harness.get("run_id")
        or not isinstance(runner_record, Mapping) or _digest(runner_path) != str(runner_record.get("sha256", "")).lower()
    ):
        raise Wave1AcceptanceError("Clean-machine harness copied inputs or executing runner is not hash-bound.")
    attestation = harness.get("environment_attestation")
    required_attestation = {"status", "cryptographically_verified", "eligible_for_human_review", "note", "contract", "provider", "run_id", "inputs_sha256", "attestor", "issued_at", "environment_id", "isolation_claim", "artifact"}
    try:
        attestation_issued_at = datetime.fromisoformat(str(attestation.get("issued_at", "")).replace("Z", "+00:00")) if isinstance(attestation, Mapping) else None
    except ValueError:
        attestation_issued_at = None
    if (
        not isinstance(attestation, Mapping) or set(attestation) != required_attestation
        or attestation.get("status") != "supplied_for_human_review"
        or attestation.get("cryptographically_verified") is not False
        or attestation.get("eligible_for_human_review") is not True
        or attestation.get("contract") != "spike/wave1-environment-attestation/v1"
        or attestation.get("provider") != harness.get("provider") or attestation.get("run_id") != harness.get("run_id")
        or str(attestation.get("inputs_sha256", "")).lower() != str(harness.get("inputs_sha256", "")).lower()
        or any(not isinstance(attestation.get(key), str) or not attestation[key].strip() for key in ("attestor", "issued_at", "environment_id", "isolation_claim", "note"))
        or attestation_issued_at is None or attestation_issued_at.tzinfo is None
    ):
        raise Wave1AcceptanceError("Clean-machine environment attestation is missing, unbound, or not eligible for human review; it remains a review input, not proof.")
    attestation_path = harness_path.parent / "environment-attestation.json"
    attestation_artifact = attestation.get("artifact")
    try:
        supplied_attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Wave1AcceptanceError("Clean-machine environment attestation copy is unreadable.") from error
    if (
        not isinstance(attestation_artifact, Mapping) or attestation_artifact.get("path") != "environment-attestation.json"
        or _digest(attestation_path) != str(attestation_artifact.get("sha256", "")).lower()
        or not isinstance(supplied_attestation, Mapping)
        or set(supplied_attestation) != (required_attestation - {"status", "cryptographically_verified", "eligible_for_human_review", "note", "artifact"})
        or any(supplied_attestation.get(key) != attestation.get(key) for key in set(supplied_attestation) - {"inputs_sha256"})
        or str(supplied_attestation.get("inputs_sha256", "")).lower() != str(attestation.get("inputs_sha256", "")).lower()
    ):
        raise Wave1AcceptanceError("Clean-machine environment attestation copy is not hash-bound to this run.")
    for key in ("installer_sha256", "before_manifest_payload_sha256", "after_manifest_payload_sha256"):
        if str(harness.get(key, "")).lower() != str(raw.get(key, "")).lower():
            raise Wave1AcceptanceError(f"Clean-machine harness {key} does not bind the human evidence.")
    status = "passed" if _summary(checks)["failed"] == 0 else "failed"
    return checks, {
        "status": status, "evidence": str(evidence_path.resolve()),
        "reviewer": raw.get("reviewer"), "reviewed_at": raw.get("reviewed_at"),
        "environment": dict(environment), "installer_sha256": raw.get("installer_sha256"),
        "before_manifest_payload_sha256": raw.get("before_manifest_payload_sha256"),
        "after_manifest_payload_sha256": raw.get("after_manifest_payload_sha256"),
        **({"contract": evidence_contract, "installer_file": installer_file, "installer_manifest_sha256": installer_manifest_sha256, "authenticode": authenticode} if evidence_contract == HUMAN_EVIDENCE_CONTRACT_V2 else {}),
    }
def compose_report(
    *, automated_checks: list[Dict[str, Any]], human_checks: list[Dict[str, Any]],
    candidate: Mapping[str, Any], worker: Mapping[str, Any], fixture: Mapping[str, Any],
    runtime: Mapping[str, Any], human: Mapping[str, Any],
) -> Dict[str, Any]:
    human_checks = list(human_checks)
    if human.get("evidence"):
        installer_sha256 = str(human.get("installer_sha256", "")).lower()
        candidate_digests = {
            str(item.get("sha256", "")).lower()
            for item in candidate.get("artifacts", [])
            if isinstance(item, Mapping)
        }
        human_checks.append(_check(
            "evidence.installer_binding",
            installer_sha256 in candidate_digests,
            "Reviewed evidence must name one exact installer candidate digest.",
            installer_sha256=installer_sha256,
        ))
        if candidate.get("contract") == INSTALLER_MANIFEST_CONTRACT_V2:
            selected = next((
                item for item in candidate.get("artifacts", [])
                if isinstance(item, Mapping)
                and item.get("file") == human.get("installer_file")
                and str(item.get("sha256", "")).lower() == installer_sha256
            ), None)
            signature = selected.get("authenticode", {}) if isinstance(selected, Mapping) and isinstance(selected.get("authenticode"), Mapping) else {}
            human_signature = human.get("authenticode", {}) if isinstance(human.get("authenticode"), Mapping) else {}
            signed_binding = (
                human.get("contract") == HUMAN_EVIDENCE_CONTRACT_V2
                and str(human.get("installer_manifest_sha256", "")).lower() == str(candidate.get("manifest_sha256", "")).lower()
                and isinstance(selected, Mapping)
                and str(human_signature.get("signer_thumbprint", "")).upper() == str(signature.get("signer_thumbprint", "")).upper()
                and human_signature.get("timestamp_protocol") == "rfc3161" == signature.get("timestamp_protocol")
                and str(human_signature.get("timestamp_authority_thumbprint", "")).upper() == str(signature.get("timestamp_authority_thumbprint", "")).upper()
            )
            human_checks.append(_check(
                "evidence.signed_candidate_binding", signed_binding,
                "Reviewed evidence must bind one exact signed candidate file, manifest digest, signer, and RFC 3161 timestamp authority.",
                installer_file=human.get("installer_file"), installer_manifest_sha256=human.get("installer_manifest_sha256"),
            ))
        fixture_before = str(human.get("before_manifest_payload_sha256", "")).lower()
        expected_fixture = str(fixture.get("manifest_payload_sha256", "")).lower()
        human_checks.append(_check(
            "evidence.fixture_binding",
            fixture_before == expected_fixture and _SHA256.fullmatch(expected_fixture) is not None,
            "Reviewed evidence must begin from the exact acceptance fixture manifest.",
            before_manifest_payload_sha256=fixture_before,
            expected_manifest_payload_sha256=expected_fixture,
        ))
    automated_summary = _summary(automated_checks)
    human_summary = _summary(human_checks)
    automated_status = "passed" if automated_summary["failed"] == 0 else "failed"
    if human_summary["failed"] == 0:
        human_status = "passed"
    elif human.get("status") == "pending" and not human.get("evidence"):
        human_status = "pending"
    else:
        human_status = "failed"
    status = "passed" if automated_status == human_status == "passed" else "failed" if automated_status == "failed" or human_status == "failed" else "pending_human"
    return {
        "contract": REPORT_CONTRACT_V2 if candidate.get("contract") == INSTALLER_MANIFEST_CONTRACT_V2 else REPORT_CONTRACT, "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "automated": {"status": automated_status, "summary": automated_summary, "checks": automated_checks},
        "human": {**dict(human), "status": human_status, "summary": human_summary, "checks": human_checks},
        "candidate": dict(candidate), "worker": dict(worker), "fixture": dict(fixture),
        "runtime": {
            "generated_at": runtime.get("generated_at"),
            "source_snapshot_digest": runtime.get("source_snapshot_digest"),
            "packaged_snapshot_digest": runtime.get("packaged_snapshot_digest"),
        },
        "qualification": {
            "assembly_foundation": "packaged_acceptance" if status == "passed" else "contract_tested",
            "physics": "not_qualified",
            "solver_ready": False,
        },
    }
