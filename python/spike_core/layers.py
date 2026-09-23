"""Ordered PCB layer and partial-stackup normalization helpers."""

from __future__ import annotations

from typing import Dict, List, Tuple

from .contracts import DesignIR


DEFAULT_COPPER_THICKNESS_MM = 0.035
DEFAULT_BOARD_THICKNESS_MM = 1.6


def ordered_copper_layer_names(design: DesignIR) -> List[str]:
    table_names: List[str] = []
    for item in design.layers:
        name = str(item.get("name", "")).strip('"')
        layer_type = str(item.get("type", item.get("kind", ""))).lower()
        if name.endswith(".Cu") or layer_type in {"signal", "power", "mixed", "jumper"}:
            table_names.append(name)
    stackup_names: List[str] = []
    for item in design.stackup:
        name = str(item.get("name", "")).strip('"')
        if name.endswith(".Cu") or str(item.get("type", "")).lower() == "copper":
            stackup_names.append(name)
    table_names = list(dict.fromkeys(name for name in table_names if name))
    stackup_names = list(dict.fromkeys(name for name in stackup_names if name))
    if table_names and all(name in stackup_names for name in table_names):
        names = stackup_names + [name for name in table_names if name not in stackup_names]
    else:
        names = table_names + [name for name in stackup_names if name not in table_names]
    return list(dict.fromkeys(name for name in names if name))


def copper_stack_profile(
    design: DesignIR,
    default_thickness_mm: float = DEFAULT_COPPER_THICKNESS_MM,
) -> Tuple[List[str], Dict[str, float], Dict[str, float]]:
    """Return all copper layers even when KiCad's material stackup is partial."""

    names = ordered_copper_layer_names(design)
    if not names:
        return [], {}, {}

    z_by_layer: Dict[str, float] = {}
    thickness_by_layer: Dict[str, float] = {}
    cursor = 0.0
    for item in design.stackup:
        name = str(item.get("name", "")).strip('"')
        thickness = max(float(item.get("thickness") or item.get("thickness_mm") or 0), 0.0)
        if name in names and (
            name.endswith(".Cu") or str(item.get("type", "")).lower() == "copper"
        ):
            resolved_thickness = thickness or default_thickness_mm
            thickness_by_layer[name] = resolved_thickness
            z_by_layer[name] = cursor - resolved_thickness / 2
        cursor -= thickness

    for name in names:
        thickness_by_layer.setdefault(name, default_thickness_mm)

    known = sorted((names.index(name), z) for name, z in z_by_layer.items())
    fallback_spacing = max(abs(cursor), DEFAULT_BOARD_THICKNESS_MM) / max(len(names) - 1, 1)
    for index, name in enumerate(names):
        if name in z_by_layer:
            continue
        before = next(
            ((known_index, z) for known_index, z in reversed(known) if known_index < index),
            None,
        )
        after = next(
            ((known_index, z) for known_index, z in known if known_index > index),
            None,
        )
        if before and after:
            ratio = (index - before[0]) / (after[0] - before[0])
            z_by_layer[name] = before[1] + (after[1] - before[1]) * ratio
        elif before:
            spacing = fallback_spacing
            if len(known) >= 2:
                left, right = known[-2], known[-1]
                spacing = abs((right[1] - left[1]) / max(right[0] - left[0], 1))
            z_by_layer[name] = before[1] - spacing * (index - before[0])
        elif after:
            spacing = fallback_spacing
            if len(known) >= 2:
                left, right = known[0], known[1]
                spacing = abs((right[1] - left[1]) / max(right[0] - left[0], 1))
            z_by_layer[name] = after[1] + spacing * (after[0] - index)
        else:
            z_by_layer[name] = -index * fallback_spacing

    return names, z_by_layer, thickness_by_layer
