"""Canonical multi-design ownership for AssemblyIR board instances."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Mapping

from .spider_v2 import SpiDeRV2
from .assembly_scale import MAX_BOARDS, design_scale, supported_scale_error


ASSEMBLY_DESIGNS_V1 = "spike/assembly-designs/v1"
MAX_ASSEMBLY_DESIGNS = MAX_BOARDS


class AssemblyDesignError(ValueError):
    """Raised when retained SpiDeR records do not own the assembly boards."""


def _same_active_design(left: Any, right: Any) -> bool:
    """Compare duplicate active records across JSON/in-memory frame encoding."""

    if left == right:
        return True
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    if {key: value for key, value in left.items() if key != "frame"} != {
        key: value for key, value in right.items() if key != "frame"
    }:
        return False
    left_frame = left.get("frame")
    right_frame = right.get("frame")
    if not isinstance(left_frame, Mapping) or not isinstance(right_frame, Mapping):
        return left_frame == right_frame
    normalized_left = dict(left_frame)
    normalized_right = dict(right_frame)
    normalized_left["transform"] = tuple(normalized_left.get("transform", ()))
    normalized_right["transform"] = tuple(normalized_right.get("transform", ()))
    return normalized_left == normalized_right


def canonicalize_assembly_designs(
    raw: Any,
    active_design: Any,
    assembly_ir: Any,
    *,
    validated_active: SpiDeRV2 | None = None,
) -> Dict[str, Any]:
    """Validate the optional complete SpiDeR set used by an assembly."""

    if raw in (None, {}):
        if not isinstance(assembly_ir, Mapping):
            return {}
        try:
            active_record = validated_active or SpiDeRV2.from_dict(active_design)
            active = active_record.to_dict()
        except (TypeError, ValueError) as exc:
            raise AssemblyDesignError(f"The active assembly SpiDeR is invalid: {exc}") from exc
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
            raise AssemblyDesignError(f"The active Assembly SpiDeR has invalid declared dimensions: {exc}") from exc
        if scale_error is not None:
            raise AssemblyDesignError(f"The active Assembly SpiDeR {scale_error}.")
        return {}
    if not isinstance(raw, Mapping) or set(raw) != {"contract", "active_design_id", "designs"}:
        raise AssemblyDesignError("Assembly designs must contain exactly contract, active_design_id, and designs.")
    if raw.get("contract") != ASSEMBLY_DESIGNS_V1:
        raise AssemblyDesignError("Assembly designs contract is unsupported or missing.")
    if not isinstance(active_design, Mapping):
        raise AssemblyDesignError("Assembly designs require an active SpiDeR v2 record.")
    try:
        active_record = validated_active or SpiDeRV2.from_dict(active_design)
    except (TypeError, ValueError) as exc:
        raise AssemblyDesignError(f"The active assembly SpiDeR is invalid: {exc}") from exc
    active_id = raw.get("active_design_id")
    if not isinstance(active_id, str) or active_id != active_record.design_id:
        raise AssemblyDesignError("Assembly designs active_design_id must match design/design-ir.json.")
    designs_raw = raw.get("designs")
    if not isinstance(designs_raw, list) or not designs_raw or len(designs_raw) > MAX_ASSEMBLY_DESIGNS:
        raise AssemblyDesignError(f"Assembly designs must retain 1 through {MAX_ASSEMBLY_DESIGNS} SpiDeR records.")
    designs = []
    by_id: Dict[str, Dict[str, Any]] = {}
    active_matched = False
    for position, item in enumerate(designs_raw):
        # The active design is stored both as design/design-ir.json and in the
        # retained set.  When the raw records are exactly equal, reuse the
        # already validated record instead of hydrating and expanding tens of
        # megabytes of entities a second time.
        if _same_active_design(item, active_design):
            active_matched = True
            design = dict(item)
            # JSON stores the frame matrix as an array while CoordinateFrame's
            # canonical in-memory form is a tuple.  Normalize this small record
            # without expanding every design entity through dataclasses.asdict.
            design["frame"] = asdict(active_record.frame)
        else:
            try:
                design = SpiDeRV2.from_dict(item).to_dict()
            except (TypeError, ValueError) as exc:
                raise AssemblyDesignError(f"Assembly SpiDeR {position} is invalid: {exc}") from exc
        identity = design["design_id"]
        if identity in by_id:
            raise AssemblyDesignError(f"Assembly SpiDeR identity is duplicated: {identity}")
        try:
            scale_error = supported_scale_error(design_scale(design))
        except ValueError as exc:
            raise AssemblyDesignError(f"Assembly SpiDeR {identity} has invalid declared dimensions: {exc}") from exc
        if scale_error is not None:
            raise AssemblyDesignError(f"Assembly SpiDeR {identity} {scale_error}.")
        by_id[identity] = design
        designs.append(design)
    if not active_matched or active_id not in by_id:
        raise AssemblyDesignError("Assembly designs must contain the exact active SpiDeR record.")
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
            raise AssemblyDesignError(f"AssemblyIR board instances reference unretained SpiDeR identities: {', '.join(missing[:5])}")
    return {"contract": ASSEMBLY_DESIGNS_V1, "active_design_id": active_id, "designs": designs}
