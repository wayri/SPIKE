"""Shared, bounded scale policy for retained AssemblyIR board designs.

The limits in this module are data-admission limits.  They make retained
project data and resource estimates predictable; they do not certify solver
accuracy, coupled SI/PI support, or visualization throughput.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import math
from typing import Any, Dict, Mapping


MAX_BOARDS = 30
MAX_COPPER_LAYERS = 32
MAX_BOARD_EXTENT_MM = 1_000.0
MAX_BOARD_AREA_MM2 = MAX_BOARD_EXTENT_MM ** 2
MAX_COMPONENTS_PER_BOARD = 20_000
MAX_NETS_PER_BOARD = 100_000
MAX_ASSEMBLY_PARTS = 100


def as_mapping(value: Any) -> Mapping[str, Any]:
    """Project an IR record to a mapping without accepting arbitrary objects."""

    if isinstance(value, Mapping):
        return value
    if hasattr(value, "to_dict"):
        candidate = value.to_dict()
        return candidate if isinstance(candidate, Mapping) else {}
    if is_dataclass(value):
        candidate = asdict(value)
        return candidate if isinstance(candidate, Mapping) else {}
    return {}


def _collection_count(value: Any) -> int:
    return len(value) if isinstance(value, (list, tuple)) else 0


def _finite_positive(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) and numeric > 0.0 else None


def _declared_board_size_mm(metadata: Mapping[str, Any]) -> tuple[float, float] | None:
    """Read the optional board envelope used by project-scale admission.

    The design contract keeps this import-derived envelope in metadata until a
    dedicated outline schema replaces it.  A supplied envelope must be a
    positive two-element ``board_size_mm`` value, or a four-element
    ``board_bounds_mm`` value expressed as xmin, ymin, xmax, ymax.
    """

    if "board_size_mm" in metadata:
        value = metadata["board_size_mm"]
        if isinstance(value, Mapping):
            width, height = value.get("width_mm"), value.get("height_mm")
        elif isinstance(value, (list, tuple)) and len(value) == 2:
            width, height = value
        else:
            raise ValueError("metadata.board_size_mm must contain positive width and height in mm.")
        width_value, height_value = _finite_positive(width), _finite_positive(height)
        if width_value is None or height_value is None:
            raise ValueError("metadata.board_size_mm must contain positive finite dimensions in mm.")
        return width_value, height_value
    if "board_bounds_mm" in metadata:
        value = metadata["board_bounds_mm"]
        if isinstance(value, Mapping):
            values = (value.get("min_x_mm"), value.get("min_y_mm"), value.get("max_x_mm"), value.get("max_y_mm"))
        elif isinstance(value, (list, tuple)) and len(value) == 4:
            values = tuple(value)
        else:
            raise ValueError("metadata.board_bounds_mm must contain xmin, ymin, xmax, and ymax in mm.")
        try:
            xmin, ymin, xmax, ymax = (float(item) for item in values)
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata.board_bounds_mm must contain finite numeric coordinates in mm.") from exc
        if not all(math.isfinite(item) for item in (xmin, ymin, xmax, ymax)):
            raise ValueError("metadata.board_bounds_mm must contain finite numeric coordinates in mm.")
        width, height = xmax - xmin, ymax - ymin
        if width <= 0.0 or height <= 0.0:
            raise ValueError("metadata.board_bounds_mm must have increasing x and y coordinates.")
        return width, height
    if "board_bbox" in metadata:
        value = metadata["board_bbox"]
        if not isinstance(value, Mapping):
            raise ValueError("metadata.board_bbox must contain min_x, min_y, max_x, and max_y in mm.")
        try:
            xmin, ymin, xmax, ymax = (float(value[key]) for key in ("min_x", "min_y", "max_x", "max_y"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("metadata.board_bbox must contain finite numeric coordinates in mm.") from exc
        if not all(math.isfinite(item) for item in (xmin, ymin, xmax, ymax)) or xmax <= xmin or ymax <= ymin:
            raise ValueError("metadata.board_bbox must have finite increasing x and y coordinates.")
        return xmax - xmin, ymax - ymin
    return None


def design_scale(raw: Any) -> Dict[str, Any]:
    """Return deterministic retained-design counts and its declared envelope."""

    design = as_mapping(raw)
    layers = design.get("layers")
    layer_items = layers if isinstance(layers, (list, tuple)) else ()
    copper_layers = sum(
        1 for layer in layer_items
        if str(as_mapping(layer).get("layer_type") or as_mapping(layer).get("type") or "").lower() == "copper"
        or str(as_mapping(layer).get("name") or "").lower().endswith(".cu")
    )
    primitive_keys = (
        "tracks", "arcs", "vias", "pads", "zones", "regions",
        "component_bonds", "connectors", "castellations",
    )
    board_size_mm = _declared_board_size_mm(as_mapping(design.get("metadata")))
    result: Dict[str, Any] = {
        "copper_layers": copper_layers,
        "primitives": sum(_collection_count(design.get(key)) for key in primitive_keys),
        "components": _collection_count(design.get("components")),
        "nets": _collection_count(design.get("nets")),
        "board_size_mm": list(board_size_mm) if board_size_mm is not None else None,
        "board_area_mm2": (board_size_mm[0] * board_size_mm[1]) if board_size_mm is not None else None,
    }
    return result


def supported_scale_error(scale: Mapping[str, Any]) -> str | None:
    """Return the first package-admission error for a board design, if any."""

    if int(scale.get("copper_layers", 0)) > MAX_COPPER_LAYERS:
        return f"has more than {MAX_COPPER_LAYERS} copper layers"
    if int(scale.get("components", 0)) > MAX_COMPONENTS_PER_BOARD:
        return f"has more than {MAX_COMPONENTS_PER_BOARD} components"
    if int(scale.get("nets", 0)) > MAX_NETS_PER_BOARD:
        return f"has more than {MAX_NETS_PER_BOARD} nets"
    size = scale.get("board_size_mm")
    if isinstance(size, (list, tuple)) and len(size) == 2:
        if float(size[0]) > MAX_BOARD_EXTENT_MM or float(size[1]) > MAX_BOARD_EXTENT_MM:
            return f"exceeds the {MAX_BOARD_EXTENT_MM:g} mm by {MAX_BOARD_EXTENT_MM:g} mm board envelope"
    return None
