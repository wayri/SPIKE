"""Verify exact human approval and notice coverage for a Windows component inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SPDX = re.compile(r"^[A-Za-z0-9.+()-]+(?:\s+(?:AND|OR|WITH)\s+[A-Za-z0-9.+()-]+)*$")


class ComponentApprovalError(ValueError):
    """Raised when human component approval evidence is incomplete or stale."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_evidence(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, Mapping):
        raise ComponentApprovalError(f"{label} evidence is missing")
    relative = str(raw.get("file", "")).replace("\\", "/")
    if not relative or relative.startswith("/") or ":" in relative or ".." in relative.split("/"):
        raise ComponentApprovalError(f"{label} evidence path is unsafe")
    expected = str(raw.get("sha256", "")).lower()
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ComponentApprovalError(f"{label} evidence escapes the review root") from exc
    if not path.is_file() or _SHA256.fullmatch(expected) is None or _digest(path) != expected:
        raise ComponentApprovalError(f"{label} evidence digest does not match")
    return path


def verify_component_approvals(
    inventory_path: str | Path,
    approvals_path: str | Path,
    notices_path: str | Path,
    evidence_root: str | Path,
) -> dict[str, Any]:
    inventory_file = Path(inventory_path).resolve()
    approvals_file = Path(approvals_path).resolve()
    notices_file = Path(notices_path).resolve()
    root = Path(evidence_root).resolve()
    inventory = json.loads(inventory_file.read_text(encoding="utf-8"))
    approvals = json.loads(approvals_file.read_text(encoding="utf-8"))
    if inventory.get("contract") != "spike/windows-component-inventory/v1":
        raise ComponentApprovalError("Unsupported component inventory contract")
    if approvals.get("contract") != "spike/windows-component-approvals/v1":
        raise ComponentApprovalError("Unsupported component approval contract")
    if approvals.get("platform") != "windows-x64" or inventory.get("platform") != "windows-x64":
        raise ComponentApprovalError("Component evidence platform is not windows-x64")
    if approvals.get("inventory_sha256") != _digest(inventory_file):
        raise ComponentApprovalError("Component approvals are stale for this inventory")
    if approvals.get("notices_sha256") != _digest(notices_file):
        raise ComponentApprovalError("Component approvals are stale for this notice bundle")
    components = inventory.get("components")
    decisions = approvals.get("approvals")
    if not isinstance(components, list) or not isinstance(decisions, list):
        raise ComponentApprovalError("Component inventory or approval list is malformed")
    by_purl = {str(item.get("purl", "")): item for item in components if isinstance(item, Mapping)}
    approval_by_purl = {str(item.get("purl", "")): item for item in decisions if isinstance(item, Mapping)}
    if len(by_purl) != len(components) or len(approval_by_purl) != len(decisions):
        raise ComponentApprovalError("Component evidence contains duplicate or malformed purls")
    if set(by_purl) != set(approval_by_purl):
        raise ComponentApprovalError("Component approval coverage is not exact")
    notice_text = notices_file.read_text(encoding="utf-8")
    if "this register is incomplete" in notice_text.lower() or "release-blocking" in notice_text.lower():
        raise ComponentApprovalError("Third-party notice bundle remains explicitly incomplete")
    for purl, component in by_purl.items():
        decision = approval_by_purl[purl]
        if decision.get("identity_sha256") != component.get("identity_sha256"):
            raise ComponentApprovalError(f"Approval identity is stale for {purl}")
        if decision.get("disposition") != "approved" or decision.get("compliance_approved") is not True:
            raise ComponentApprovalError(f"Component is not approved: {purl}")
        expression = str(decision.get("approved_license_expression", "")).strip()
        if not expression or _SPDX.fullmatch(expression) is None or expression.startswith("LicenseRef-"):
            raise ComponentApprovalError(f"Approved SPDX license expression is invalid for {purl}")
        observed = str(component.get("declared_license", "")).strip()
        observed_is_spdx = (
            bool(observed) and _SPDX.fullmatch(observed) is not None
            and not observed.startswith("LicenseRef-")
        )
        if not observed_is_spdx or expression != observed:
            _safe_evidence(
                root, decision.get("license_resolution_evidence"),
                f"license resolution for {purl}",
            )
        review = decision.get("review")
        if not isinstance(review, Mapping) or not all(str(review.get(key, "")).strip() for key in ("ticket", "reviewer", "reviewed_at")):
            raise ComponentApprovalError(f"Human review identity is incomplete for {purl}")
        notice = decision.get("notice")
        if not isinstance(notice, Mapping):
            raise ComponentApprovalError(f"Notice decision is missing for {purl}")
        if component.get("scope") == "bundled":
            if decision.get("redistribution_approved") is not True or notice.get("status") != "included":
                raise ComponentApprovalError(f"Bundled component lacks redistribution/notice approval: {purl}")
            if notice.get("sha256") != _digest(notices_file) or notice.get("file") != notices_file.name:
                raise ComponentApprovalError(f"Notice identity is stale for {purl}")
            marker = str(notice.get("marker", ""))
            if not marker or marker not in notice_text:
                raise ComponentApprovalError(f"Notice marker is absent for {purl}")
        elif notice.get("status") not in {"included", "not-required"}:
            raise ComponentApprovalError(f"Build-only notice disposition is invalid for {purl}")
        if "GPL" in expression and component.get("scope") == "bundled":
            reciprocal = decision.get("reciprocal_obligations")
            if not isinstance(reciprocal, Mapping) or reciprocal.get("status") != "satisfied":
                raise ComponentApprovalError(f"Reciprocal obligations are not satisfied for {purl}")
            _safe_evidence(root, reciprocal.get("evidence"), f"reciprocal obligations for {purl}")
    return {
        "contract": "spike/windows-component-approval-verification/v1",
        "status": "passed", "production_qualified": False,
        "inventory_sha256": _digest(inventory_file),
        "approvals_sha256": _digest(approvals_file),
        "notices_sha256": _digest(notices_file),
        "components": len(components),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--approvals", required=True, type=Path)
    parser.add_argument("--notices", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_component_approvals(args.inventory, args.approvals, args.notices, args.evidence_root)
    except ComponentApprovalError as exc:
        raise SystemExit(f"Windows component approvals rejected: {exc}") from exc
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
