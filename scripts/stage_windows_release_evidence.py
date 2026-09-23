"""Stage exact, reviewed Windows release inputs beside signed installers.

This copies only public release evidence. It never copies signing keys and never
changes installer bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_windows_component_approvals import verify_component_approvals


class ReleaseEvidenceStageError(ValueError):
    """Raised when public release evidence cannot be staged exactly."""


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
        raise ReleaseEvidenceStageError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseEvidenceStageError(f"{label} must be a JSON object: {path}")
    return value


def _safe_relative(value: Any, label: str) -> Path:
    raw = str(value or "").replace("\\", "/")
    pure = PurePosixPath(raw)
    if (
        not raw or raw.startswith("/") or ":" in raw
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ReleaseEvidenceStageError(f"{label} must be a safe relative path")
    return Path(*pure.parts)


def _under(root: Path, path: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ReleaseEvidenceStageError(f"{label} resolves outside its approved root") from exc
    return resolved


def stage_windows_release_evidence(
    source_root: str | Path,
    artifact_root: str | Path,
    *,
    dependencies_lock_path: str | Path,
    dependency_signature_path: str | Path,
    worker_manifest_path: str | Path,
    notices_path: str | Path,
    inventory_path: str | Path,
    approvals_path: str | Path,
) -> dict[str, Any]:
    source = Path(source_root).resolve()
    destination = Path(artifact_root).resolve()
    if not source.is_dir():
        raise ReleaseEvidenceStageError(f"Release evidence source root is missing: {source}")
    destination.mkdir(parents=True, exist_ok=True)

    dependencies = _under(source, Path(dependencies_lock_path), "dependency lock")
    signature = _under(destination, Path(dependency_signature_path), "dependency signature")
    worker_manifest = _under(source, Path(worker_manifest_path), "worker manifest")
    notices = _under(source, Path(notices_path), "notice bundle")
    inventory = _under(source, Path(inventory_path), "component inventory")
    approvals = _under(source, Path(approvals_path), "component approvals")
    for path, label in (
        (dependencies, "dependency lock"), (signature, "dependency signature"),
        (worker_manifest, "worker manifest"), (notices, "notice bundle"),
        (inventory, "component inventory"), (approvals, "component approvals"),
    ):
        if not path.is_file():
            raise ReleaseEvidenceStageError(f"Required {label} is missing: {path}")

    lock = _load_object(dependencies, "dependency lock")
    signature_policy = lock.get("signature")
    if not isinstance(signature_policy, Mapping):
        raise ReleaseEvidenceStageError("Dependency lock signature policy is missing")
    expected_sidecar = _safe_relative(signature_policy.get("sidecar"), "dependency sidecar")
    if len(expected_sidecar.parts) != 1 or signature.name != expected_sidecar.name:
        raise ReleaseEvidenceStageError("Dependency signature filename differs from the lock policy")

    verify_component_approvals(inventory, approvals, notices, source)
    approval_document = _load_object(approvals, "component approvals")
    evidence_paths: set[Path] = set()
    for decision in approval_document.get("approvals", []):
        if not isinstance(decision, Mapping):
            raise ReleaseEvidenceStageError("Component approval record is malformed")
        for raw in (
            decision.get("license_resolution_evidence"),
            decision.get("reciprocal_obligations", {}).get("evidence")
            if isinstance(decision.get("reciprocal_obligations"), Mapping) else None,
        ):
            if raw is None:
                continue
            if not isinstance(raw, Mapping):
                raise ReleaseEvidenceStageError("Component approval evidence is malformed")
            evidence_paths.add(_safe_relative(raw.get("file"), "component approval evidence"))

    copies: dict[Path, Path] = {
        dependencies: Path("dependencies.lock.json"),
        signature: Path(expected_sidecar.name),
        worker_manifest: Path("bundled") / "spike-worker.manifest.json",
        notices: Path(notices.name),
        inventory: Path("config") / "windows-component-inventory.json",
        approvals: Path("licenses") / "windows-component-approvals.json",
    }
    for relative in evidence_paths:
        copies[_under(source, source / relative, "component approval evidence")] = relative

    staged: list[dict[str, Any]] = []
    occupied: dict[str, str] = {}
    for input_path, relative in sorted(copies.items(), key=lambda item: item[1].as_posix()):
        output_path = _under(destination, destination / relative, "staged release evidence")
        relative_name = relative.as_posix()
        digest = _digest(input_path)
        previous = occupied.get(relative_name)
        if previous is not None and previous != digest:
            raise ReleaseEvidenceStageError(f"Conflicting evidence targets: {relative_name}")
        occupied[relative_name] = digest
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if input_path != output_path:
            shutil.copyfile(input_path, output_path)
        if _digest(output_path) != digest:
            raise ReleaseEvidenceStageError(f"Staged evidence digest changed: {relative_name}")
        staged.append({"file": relative_name, "sha256": digest, "size": output_path.stat().st_size})

    return {
        "contract": "spike/windows-release-evidence-stage/v1",
        "status": "passed",
        "production_qualified": False,
        "files": staged,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--dependencies-lock", type=Path, default=ROOT / "dependencies.lock.json")
    parser.add_argument("--dependency-signature", type=Path, required=True)
    parser.add_argument(
        "--worker-manifest", type=Path,
        default=ROOT / "app" / "src-tauri" / "resources" / "worker" / "spike-worker.manifest.json",
    )
    parser.add_argument("--notices", type=Path, default=ROOT / "THIRD_PARTY_NOTICES.md")
    parser.add_argument("--inventory", type=Path, default=ROOT / "config" / "windows-component-inventory.json")
    parser.add_argument("--approvals", type=Path, default=ROOT / "licenses" / "windows-component-approvals.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = stage_windows_release_evidence(
            args.source_root, args.artifact_root,
            dependencies_lock_path=args.dependencies_lock,
            dependency_signature_path=args.dependency_signature,
            worker_manifest_path=args.worker_manifest,
            notices_path=args.notices,
            inventory_path=args.inventory,
            approvals_path=args.approvals,
        )
    except ValueError as exc:
        raise SystemExit(f"Windows release evidence staging rejected: {exc}") from exc
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
