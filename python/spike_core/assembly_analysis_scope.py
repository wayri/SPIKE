"""Fail-closed execution scope for analyses launched from an AssemblyIR project."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping

from .contracts import DesignIR
from .design_ir_v2 import AssemblyIRV1


SCOPE_CONTRACT = "spike/assembly-analysis-scope/v1"
CASE_SCOPE_FILENAME = "spike_assembly_scope.json"


class AssemblyAnalysisScopeError(ValueError):
    """Raised when an assembly analysis would have ambiguous solver scope."""


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _design_identities(design: DesignIR) -> set[str]:
    values = {str(design.design_id or "").strip()}
    metadata = design.metadata if isinstance(design.metadata, dict) else {}
    values.add(str(metadata.get("design_ir_v2_id") or "").strip())
    values.add(str(metadata.get("legacy_design_id") or "").strip())
    return {value for value in values if value}


def validate_assembly_analysis_scope(raw: Mapping[str, Any], design: DesignIR | None = None) -> Dict[str, Any]:
    """Normalize one explicit board-only scope; coupled assembly solving is gated."""

    if not isinstance(raw, Mapping):
        raise AssemblyAnalysisScopeError("Assembly analysis scope must be an object.")
    if raw.get("contract") != SCOPE_CONTRACT:
        raise AssemblyAnalysisScopeError(f"Assembly analysis scope contract must be {SCOPE_CONTRACT}.")
    mode = str(raw.get("mode") or raw.get("scope") or "").strip()
    if mode == "assembly_coupled":
        raise AssemblyAnalysisScopeError(
            "Coupled assembly physics is not available: no qualified solver adapter consumes cross-board assembly entities."
        )
    if mode != "active_board_only":
        raise AssemblyAnalysisScopeError("Assembly analysis scope mode must be active_board_only or assembly_coupled.")
    assembly_raw = raw.get("assembly")
    if not isinstance(assembly_raw, Mapping):
        raise AssemblyAnalysisScopeError("Assembly analysis scope requires the retained AssemblyIR payload.")
    assembly = AssemblyIRV1.from_dict(assembly_raw)
    active_board_id = str(raw.get("active_board_id") or "").strip()
    active_design_id = str(raw.get("active_design_id") or "").strip()
    if not active_board_id or not active_design_id:
        raise AssemblyAnalysisScopeError("active_board_id and active_design_id are required for active-board-only analysis.")
    matches = [board for board in assembly.boards if board.id == active_board_id]
    if len(matches) != 1:
        raise AssemblyAnalysisScopeError(f"Active board {active_board_id!r} does not identify exactly one AssemblyIR board instance.")
    active_board = matches[0]
    if active_board.design_id != active_design_id:
        raise AssemblyAnalysisScopeError("The selected board design_id does not match active_design_id.")
    if design is not None and active_design_id not in _design_identities(design):
        raise AssemblyAnalysisScopeError("The submitted DesignIR identity does not match the selected AssemblyIR board instance.")

    ignored = {
        "boards": [board.id for board in assembly.boards if board.id != active_board_id],
        "harnesses": [item.id for item in assembly.harnesses],
        "connector_mappings": [item.id for item in assembly.connector_mappings],
        "rigid_flex_links": [item.id for item in assembly.rigid_flex_links],
        "parts": [item.id for item in assembly.parts],
        "thermal_contacts": [item.id for item in assembly.thermal_contacts],
        "electrical_bonds": [item.id for item in assembly.electrical_bonds],
    }
    assembly_dict = assembly.to_dict()
    normalized: Dict[str, Any] = {
        "contract": SCOPE_CONTRACT,
        "mode": mode,
        "assembly_id": assembly.assembly_id,
        "assembly_digest": _canonical_digest(assembly_dict),
        "active_board_id": active_board_id,
        "active_design_id": active_design_id,
        "assembly_coupling": False,
        "ignored_entities": ignored,
        "ignored_entity_counts": {key: len(value) for key, value in ignored.items()},
        "warning": "Only the selected board is solved; retained assembly entities are excluded from this analysis.",
    }
    manifest_digest = str(raw.get("project_manifest_digest") or "").strip()
    if manifest_digest:
        normalized["project_manifest_digest"] = manifest_digest
    normalized["scope_digest"] = _canonical_digest(normalized)
    return normalized


def scope_from_params(params: Mapping[str, Any], design: DesignIR | None = None) -> Dict[str, Any] | None:
    """Validate a supplied scope, rejecting partial assembly context."""

    raw = params.get("assembly_scope")
    if raw is None:
        if params.get("assembly") is not None:
            raise AssemblyAnalysisScopeError("AssemblyIR analysis requests require an explicit assembly_scope.")
        return None
    return validate_assembly_analysis_scope(raw, design)


def attach_scope_provenance(result: Dict[str, Any], scope: Dict[str, Any] | None) -> Dict[str, Any]:
    if scope is None:
        return result
    provenance = result.get("provenance")
    if not isinstance(provenance, dict):
        provenance = {}
    result["provenance"] = {**provenance, "assembly_analysis_scope": scope}
    return result


def write_case_scope(case_dir: str | Path, scope: Dict[str, Any] | None) -> None:
    if scope is None:
        return
    root = Path(case_dir).expanduser().resolve(strict=True)
    if root.is_symlink() or not root.is_dir():
        raise AssemblyAnalysisScopeError("Prepared case directory is not a safe directory.")
    path = root / CASE_SCOPE_FILENAME
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(scope, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n")


def validate_case_scope(case_dir: str | Path, scope: Dict[str, Any] | None) -> Dict[str, Any] | None:
    root = Path(case_dir).expanduser().resolve(strict=True)
    path = root / CASE_SCOPE_FILENAME
    if not path.exists():
        if scope is not None:
            raise AssemblyAnalysisScopeError("The prepared case is not bound to the supplied assembly scope.")
        return None
    if path.is_symlink() or not path.is_file():
        raise AssemblyAnalysisScopeError("The prepared case assembly-scope metadata is unsafe.")
    stored = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(stored, dict) or stored.get("contract") != SCOPE_CONTRACT:
        raise AssemblyAnalysisScopeError("The prepared case assembly-scope metadata is invalid.")
    if scope is None:
        raise AssemblyAnalysisScopeError("Running this prepared case requires its explicit assembly_scope.")
    if stored != scope:
        raise AssemblyAnalysisScopeError("The supplied assembly scope does not match the prepared case scope.")
    return stored
