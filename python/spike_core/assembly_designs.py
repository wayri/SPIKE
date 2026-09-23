"""Canonical multi-design ownership for AssemblyIR board instances."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .design_ir_v2 import DesignIRV2
from .assembly_scale import MAX_BOARDS, design_scale, supported_scale_error


ASSEMBLY_DESIGNS_V1 = "spike/assembly-designs/v1"
MAX_ASSEMBLY_DESIGNS = MAX_BOARDS


class AssemblyDesignError(ValueError):
    """Raised when retained DesignIR records do not own the assembly boards."""


def canonicalize_assembly_designs(raw: Any, active_design: Any, assembly_ir: Any) -> Dict[str, Any]:
    """Validate the optional complete DesignIR set used by an assembly."""

    if raw in (None, {}):
        if not isinstance(assembly_ir, Mapping):
            return {}
        try:
            active = DesignIRV2.from_dict(active_design).to_dict()
        except (TypeError, ValueError) as exc:
            raise AssemblyDesignError(f"The active assembly DesignIR is invalid: {exc}") from exc
        boards = assembly_ir.get("boards", [])
        if not isinstance(boards, list) or len(boards) > MAX_BOARDS:
            raise AssemblyDesignError(f"AssemblyIR supports at most {MAX_BOARDS} board instances.")
        referenced = {str(board.get("design_id", "")) for board in boards if isinstance(board, Mapping)}
        # Legacy packages can carry assembly references without a retained
        # multi-design member.  Scale-admit the active design only when it is
        # the design actually instantiated; a retained set is required for
        # complete multi-design validation below.
        if referenced != {active["design_id"]}:
            return {}
        try:
            scale_error = supported_scale_error(design_scale(active))
        except ValueError as exc:
            raise AssemblyDesignError(f"The active Assembly DesignIR has invalid declared dimensions: {exc}") from exc
        if scale_error is not None:
            raise AssemblyDesignError(f"The active Assembly DesignIR {scale_error}.")
        return {}
    if not isinstance(raw, Mapping) or set(raw) != {"contract", "active_design_id", "designs"}:
        raise AssemblyDesignError("Assembly designs must contain exactly contract, active_design_id, and designs.")
    if raw.get("contract") != ASSEMBLY_DESIGNS_V1:
        raise AssemblyDesignError("Assembly designs contract is unsupported or missing.")
    if not isinstance(active_design, Mapping):
        raise AssemblyDesignError("Assembly designs require an active DesignIR v2 record.")
    try:
        active = DesignIRV2.from_dict(active_design).to_dict()
    except (TypeError, ValueError) as exc:
        raise AssemblyDesignError(f"The active assembly DesignIR is invalid: {exc}") from exc
    active_id = raw.get("active_design_id")
    if not isinstance(active_id, str) or active_id != active["design_id"]:
        raise AssemblyDesignError("Assembly designs active_design_id must match design/design-ir.json.")
    designs_raw = raw.get("designs")
    if not isinstance(designs_raw, list) or not designs_raw or len(designs_raw) > MAX_ASSEMBLY_DESIGNS:
        raise AssemblyDesignError(f"Assembly designs must retain 1 through {MAX_ASSEMBLY_DESIGNS} DesignIR records.")
    designs = []
    by_id: Dict[str, Dict[str, Any]] = {}
    for position, item in enumerate(designs_raw):
        try:
            design = DesignIRV2.from_dict(item).to_dict()
        except (TypeError, ValueError) as exc:
            raise AssemblyDesignError(f"Assembly DesignIR {position} is invalid: {exc}") from exc
        identity = design["design_id"]
        if identity in by_id:
            raise AssemblyDesignError(f"Assembly DesignIR identity is duplicated: {identity}")
        try:
            scale_error = supported_scale_error(design_scale(design))
        except ValueError as exc:
            raise AssemblyDesignError(f"Assembly DesignIR {identity} has invalid declared dimensions: {exc}") from exc
        if scale_error is not None:
            raise AssemblyDesignError(f"Assembly DesignIR {identity} {scale_error}.")
        by_id[identity] = design
        designs.append(design)
    if by_id.get(active_id) != active:
        raise AssemblyDesignError("Assembly designs must contain the exact active DesignIR record.")
    if isinstance(assembly_ir, Mapping):
        boards = assembly_ir.get("boards", [])
        if isinstance(boards, list) and len(boards) > MAX_BOARDS:
            raise AssemblyDesignError(f"AssemblyIR supports at most {MAX_BOARDS} board instances.")
        referenced = {
            str(board.get("design_id", ""))
            for board in boards if isinstance(board, Mapping)
        }
        missing = sorted(referenced - set(by_id))
        if missing:
            raise AssemblyDesignError(f"AssemblyIR board instances reference unretained DesignIR identities: {', '.join(missing[:5])}")
    return {"contract": ASSEMBLY_DESIGNS_V1, "active_design_id": active_id, "designs": designs}
