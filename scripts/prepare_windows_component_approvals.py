"""Prepare a deterministic human-review overlay for a Windows component inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_approval_overlay(
    inventory_path: str | Path,
    notices_path: str | Path,
    output_path: str | Path,
    existing_path: str | Path | None = None,
) -> dict[str, Any]:
    inventory_file = Path(inventory_path).resolve()
    notices_file = Path(notices_path).resolve()
    inventory = json.loads(inventory_file.read_text(encoding="utf-8"))
    if inventory.get("contract") != "spike/windows-component-inventory/v1":
        raise ValueError("Unsupported Windows component inventory contract")
    if not notices_file.is_file():
        raise ValueError("Third-party notice file is missing")
    preserved: dict[str, Mapping[str, Any]] = {}
    if existing_path is not None and Path(existing_path).is_file():
        existing = json.loads(Path(existing_path).read_text(encoding="utf-8"))
        if existing.get("contract") == "spike/windows-component-approvals/v1":
            preserved = {
                str(item.get("purl", "")): item
                for item in existing.get("approvals", []) if isinstance(item, Mapping)
            }
    approvals = []
    for component in inventory.get("components", []):
        purl = str(component.get("purl", ""))
        identity = str(component.get("identity_sha256", ""))
        old = preserved.get(purl)
        if old is not None and old.get("identity_sha256") == identity:
            approvals.append(dict(old))
        else:
            approvals.append({
                "purl": purl,
                "identity_sha256": identity,
                "disposition": "pending_review",
            })
    approvals.sort(key=lambda item: item["purl"])
    document = {
        "contract": "spike/windows-component-approvals/v1",
        "platform": "windows-x64",
        "inventory_sha256": _digest(inventory_file),
        "notices_sha256": _digest(notices_file),
        "approvals": approvals,
    }
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--notices", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--existing", type=Path)
    args = parser.parse_args(argv)
    result = prepare_approval_overlay(args.inventory, args.notices, args.output, args.existing)
    pending = sum(item["disposition"] == "pending_review" for item in result["approvals"])
    print(f"Prepared {len(result['approvals'])} component decisions; pending review: {pending}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
