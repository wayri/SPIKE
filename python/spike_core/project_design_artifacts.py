"""Validation for immutable design-source artifacts in project packages."""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping


def validate_design_source_artifacts(
    design_ir: Mapping[str, Any],
    assembly_designs: Mapping[str, Any],
    member_digests: Mapping[str, str],
    *,
    safe_member_path: Callable[[str], str],
    error_type: type[Exception],
) -> None:
    """Ensure every declared package source is safely addressed and immutable."""

    designs = [design_ir]
    designs.extend(
        item for item in assembly_designs.get("designs", [])
        if isinstance(item, Mapping) and item.get("design_id") != design_ir.get("design_id")
    )
    for design in designs:
        source = design.get("source") if isinstance(design.get("source"), Mapping) else {}
        artifact_uri = str(source.get("artifact_path", ""))
        if not artifact_uri:
            continue
        if not artifact_uri.startswith("package:sources/") or "\\" in artifact_uri:
            raise error_type("DesignIR source artifacts must use a safe package:sources URI.")
        member_path = safe_member_path(artifact_uri.removeprefix("package:"))
        expected_digest = str(source.get("source_digest", ""))
        if re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None:
            raise error_type("DesignIR source artifacts require a canonical SHA-256 digest.")
        if member_digests.get(member_path) != expected_digest:
            raise error_type(
                f"DesignIR source artifact is missing or does not match its digest: {member_path}"
            )
