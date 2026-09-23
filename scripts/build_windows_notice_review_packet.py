"""Build a deterministic, non-decisional Windows notice-review packet.

This script joins the machine-derived component inventory with the human-review
overlay.  It intentionally does not create notice text or make compliance,
redistribution, or approval assertions.  Every component remains explicitly
queued for legal review in the emitted packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT = "spike/windows-notice-review-packet/v1"
INVENTORY_CONTRACT = "spike/windows-component-inventory/v1"
APPROVALS_CONTRACT = "spike/windows-component-approvals/v1"
_SPDX_SHAPED = re.compile(
    r"^[A-Za-z0-9.+()-]+(?:\s+(?:AND|OR|WITH)\s+[A-Za-z0-9.+()-]+)*$"
)
_LICENSE_REF = re.compile(r"(?:^|\s)LicenseRef-[A-Za-z0-9.+()-]+(?:$|\s)")


class NoticeReviewPacketError(ValueError):
    """Raised when source review inputs cannot form an exact packet."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_document(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NoticeReviewPacketError(f"{label} is unreadable: {path}") from exc
    if not isinstance(document, dict):
        raise NoticeReviewPacketError(f"{label} must be a JSON object")
    return document


def _component_map(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    components = document.get("components")
    if not isinstance(components, list):
        raise NoticeReviewPacketError("component inventory must contain a component list")
    result: dict[str, Mapping[str, Any]] = {}
    for item in components:
        if not isinstance(item, Mapping):
            raise NoticeReviewPacketError("component inventory contains a malformed component")
        purl = item.get("purl")
        identity = item.get("identity_sha256")
        if not isinstance(purl, str) or not purl or not isinstance(identity, str) or not identity:
            raise NoticeReviewPacketError("component inventory component lacks purl or identity")
        if purl in result:
            raise NoticeReviewPacketError(f"component inventory contains duplicate purl: {purl}")
        result[purl] = item
    return result


def _approval_map(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    approvals = document.get("approvals")
    if not isinstance(approvals, list):
        raise NoticeReviewPacketError("component approvals must contain an approval list")
    result: dict[str, Mapping[str, Any]] = {}
    for item in approvals:
        if not isinstance(item, Mapping):
            raise NoticeReviewPacketError("component approvals contains a malformed approval")
        purl = item.get("purl")
        identity = item.get("identity_sha256")
        if not isinstance(purl, str) or not purl or not isinstance(identity, str) or not identity:
            raise NoticeReviewPacketError("component approval lacks purl or identity")
        if purl in result:
            raise NoticeReviewPacketError(f"component approvals contains duplicate purl: {purl}")
        result[purl] = item
    return result


def _proposed_marker(purl: str, identity: str) -> str:
    """Return a stable candidate marker; collision detection occurs at packet build."""
    seed = f"{CONTRACT}\0{purl}\0{identity}".encode("utf-8")
    return "NOTICE-REVIEW-" + hashlib.sha256(seed).hexdigest()


def _review_status(approval: Mapping[str, Any]) -> str:
    """Avoid carrying an approval assertion into a non-decisional review packet."""
    return "pending_review" if approval.get("disposition") == "pending_review" else "requires_manual_verification"


def _license_classification(expression: str) -> tuple[bool, bool]:
    """Return (invalid_spdx_shaped, unresolved_spdx_shaped) without interpreting licenses."""
    shaped = bool(expression) and _SPDX_SHAPED.fullmatch(expression) is not None
    return (not shaped, shaped and _LICENSE_REF.search(expression) is not None)


def build_notice_review_packet(
    inventory_path: str | Path,
    approvals_path: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Join exact inventory/overlay coverage and optionally write canonical JSON."""
    inventory_file = Path(inventory_path).resolve()
    approvals_file = Path(approvals_path).resolve()
    inventory = _read_document(inventory_file, "component inventory")
    approvals = _read_document(approvals_file, "component approvals")
    if inventory.get("contract") != INVENTORY_CONTRACT:
        raise NoticeReviewPacketError("unsupported component inventory contract")
    if approvals.get("contract") != APPROVALS_CONTRACT:
        raise NoticeReviewPacketError("unsupported component approvals contract")
    if inventory.get("platform") != "windows-x64" or approvals.get("platform") != "windows-x64":
        raise NoticeReviewPacketError("component review inputs must target windows-x64")

    components = _component_map(inventory)
    decisions = _approval_map(approvals)
    if set(components) != set(decisions):
        raise NoticeReviewPacketError("component approval coverage is not exact")

    entries: list[dict[str, Any]] = []
    markers: set[str] = set()
    invalid_spdx = 0
    unresolved_spdx = 0
    for purl in sorted(components):
        component = components[purl]
        approval = decisions[purl]
        identity = str(component["identity_sha256"])
        if approval.get("identity_sha256") != identity:
            raise NoticeReviewPacketError(f"component approval identity is stale for {purl}")
        marker = _proposed_marker(purl, identity)
        if marker in markers:
            raise NoticeReviewPacketError(f"proposed notice marker collision for {purl}")
        markers.add(marker)
        declared_license = str(component.get("declared_license", "")).strip()
        invalid, unresolved = _license_classification(declared_license)
        invalid_spdx += int(invalid)
        unresolved_spdx += int(unresolved)
        entries.append({
            "purl": purl,
            "identity_sha256": identity,
            "scope": str(component.get("scope", "")),
            "ecosystem": str(component.get("ecosystem", "")),
            "name": str(component.get("name", "")),
            "version": str(component.get("version", "")),
            "declared_license": declared_license,
            "proposed_notice_marker": marker,
            "review_status": _review_status(approval),
            "needs_notice_text": True,
            "needs_legal_review": True,
        })

    document = {
        "contract": CONTRACT,
        "platform": "windows-x64",
        "production_qualified": False,
        "inventory_sha256": _digest(inventory_file),
        "approvals_sha256": _digest(approvals_file),
        "components": entries,
        "summary": {
            "components": len(entries),
            "bundled_components": sum(item["scope"] == "bundled" for item in entries),
            "build_only_components": sum(item["scope"] == "build-only" for item in entries),
            "pending_review_components": sum(item["review_status"] == "pending_review" for item in entries),
            "manual_verification_components": sum(item["review_status"] == "requires_manual_verification" for item in entries),
            "needs_notice_text_components": len(entries),
            "needs_legal_review_components": len(entries),
            "invalid_spdx_declarations": invalid_spdx,
            "unresolved_spdx_declarations": unresolved_spdx,
        },
    }
    if output_path is not None:
        destination = Path(output_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("config/windows-component-inventory.json"))
    parser.add_argument("--approvals", type=Path, default=Path("licenses/windows-component-approvals.json"))
    parser.add_argument("--output", required=True, type=Path, help="JSON review-packet path, normally under build/.")
    args = parser.parse_args(argv)
    packet = build_notice_review_packet(args.inventory, args.approvals, args.output)
    print(json.dumps(packet["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
