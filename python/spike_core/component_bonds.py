"""UI-independent component-to-PCB solder bond definitions and inference.

Primitives are normalized dictionaries with an ``id``, ``x``, ``y``, and a
``net`` (or ``net_name``).  Copper primitives also provide ``layer``; accepted
top/bottom names are ``top``/``bottom`` and KiCad's ``F.Cu``/``B.Cu``.
Coordinates are millimetres.  The module deliberately models primitives as
points: polygon contact extraction belongs to the board importer, not here.
"""

from __future__ import annotations

from math import hypot, isfinite
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


COMPONENT_BONDS_CONTRACT = "spike/component-bonds/v1"
DEFAULT_SEARCH_DISTANCE_MM = 0.25
DEFAULT_COPPER_SEARCH_DISTANCE_MM = 0.5
MAX_SEARCH_DISTANCE_MM = 10.0
MAX_PRIMITIVES = 10_000

SOLDER_DEFAULTS: Dict[str, float] = {
    "electrical_resistance_ohm": 0.001,
    "electrical_inductance_h": 1.0e-9,
    "thermal_resistance_k_per_w": 20.0,
    "thermal_conductance_w_per_k": 0.05,
}

_SIDE_BY_LAYER = {
    "top": "top",
    "f.cu": "top",
    "front": "top",
    "bottom": "bottom",
    "b.cu": "bottom",
    "back": "bottom",
}


def bond_defaults(overrides: Optional[Mapping[str, Any]] = None) -> Dict[str, float]:
    """Return validated solder properties, optionally replacing known defaults.

    Unknown properties and non-positive values are rejected so a malformed
    analysis request cannot silently produce a physically meaningless bond.
    """
    result = dict(SOLDER_DEFAULTS)
    for key, value in (overrides or {}).items():
        if key not in result:
            raise ValueError("Unknown solder property: %s" % key)
        value = _finite_number(value, "solder.%s" % key)
        if value <= 0.0:
            raise ValueError("solder.%s must be positive" % key)
        result[key] = value
    return result


def define_component_bond(
    pin: Mapping[str, Any],
    pad: Mapping[str, Any],
    copper: Optional[Mapping[str, Any]] = None,
    solder: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Create an explicit bond, rejecting a connection across known nets."""
    source = _primitive(pin, "pin", require_side=False)
    target = _primitive(pad, "pad", require_side=False)
    _require_same_net(source, target)
    copper_target = _primitive(copper, "copper", require_side=True) if copper else None
    if copper_target:
        _require_same_net(target, copper_target)
    return _bond(source, target, copper_target, "explicit", bond_defaults(solder), [])


def infer_component_bonds(
    pins: Iterable[Mapping[str, Any]],
    pads: Iterable[Mapping[str, Any]],
    copper: Iterable[Mapping[str, Any]] = (),
    config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Infer nearest same-net pad and copper bonds deterministically.

    A pin first selects its nearest same-net pad within ``search_distance_mm``.
    That pad then selects the nearest same-net copper independently for top and
    bottom within ``copper_search_distance_mm``.  Candidates on a different or
    missing net never become a connection; their presence is reported as a
    warning when no valid candidate exists.
    """
    options = _options(config)
    normalized_pins = _primitives(pins, "pin", False)
    normalized_pads = _primitives(pads, "pad", False)
    normalized_copper = _primitives(copper, "copper", True)
    bonds: List[Dict[str, Any]] = []
    warnings: List[Dict[str, str]] = []

    for pin in normalized_pins:
        nearby_pads = _within(pin, normalized_pads, options["search_distance_mm"])
        matching_pads = [item for item in nearby_pads if _same_net(pin, item)]
        if not matching_pads:
            code = "net_mismatch" if nearby_pads else "no_pad_within_distance"
            warnings.append(_warning(code, pin["id"], "No same-net pad was inferred for pin."))
            bonds.append(_bond(pin, None, None, code, options["solder"], [code]))
            continue
        pad = matching_pads[0]
        for side in ("top", "bottom"):
            nearby_copper = _within(pad, [item for item in normalized_copper if item["side"] == side], options["copper_search_distance_mm"])
            matching_copper = [item for item in nearby_copper if _same_net(pad, item)]
            if matching_copper:
                bonds.append(_bond(pin, pad, matching_copper[0], "inferred", options["solder"], []))
            else:
                code = "net_mismatch" if nearby_copper else "no_copper_within_distance"
                warnings.append(_warning(code, pin["id"], "No same-net %s copper was inferred for pad %s." % (side, pad["id"])))
                bonds.append(_bond(pin, pad, {"id": None, "side": side}, code, options["solder"], [code]))

    return {
        "contract": COMPONENT_BONDS_CONTRACT,
        "status": _result_status(bonds),
        "search_distance_mm": options["search_distance_mm"],
        "copper_search_distance_mm": options["copper_search_distance_mm"],
        "solder_defaults": options["solder"],
        "bonds": bonds,
        "warnings": warnings,
    }


def _options(config: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    config = config or {}
    allowed = {"search_distance_mm", "copper_search_distance_mm", "solder"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError("Unknown component bond option: %s" % sorted(unknown)[0])
    return {
        "search_distance_mm": _distance(config.get("search_distance_mm", DEFAULT_SEARCH_DISTANCE_MM), "search_distance_mm"),
        "copper_search_distance_mm": _distance(config.get("copper_search_distance_mm", DEFAULT_COPPER_SEARCH_DISTANCE_MM), "copper_search_distance_mm"),
        "solder": bond_defaults(config.get("solder")),
    }


def _primitives(values: Iterable[Mapping[str, Any]], kind: str, require_side: bool) -> List[Dict[str, Any]]:
    values = list(values)
    if len(values) > MAX_PRIMITIVES:
        raise ValueError("Too many %s primitives (maximum %d)" % (kind, MAX_PRIMITIVES))
    return [_primitive(value, kind, require_side) for value in values]


def _primitive(value: Mapping[str, Any], kind: str, require_side: bool) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("%s primitive must be a mapping" % kind)
    identifier = str(value.get("id", "")).strip()
    if not identifier:
        raise ValueError("%s primitive requires a non-empty id" % kind)
    net = str(value.get("net", value.get("net_name", ""))).strip()
    if not net:
        raise ValueError("%s primitive %s requires a non-empty net" % (kind, identifier))
    result = {"id": identifier, "net": net, "x": _finite_number(value.get("x"), "%s.x" % identifier), "y": _finite_number(value.get("y"), "%s.y" % identifier)}
    if require_side:
        side = _SIDE_BY_LAYER.get(str(value.get("layer", value.get("side", ""))).strip().lower())
        if side is None:
            raise ValueError("copper primitive %s requires a top/bottom copper layer" % identifier)
        result["side"] = side
    return result


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError("%s must be a finite number" % name)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s must be a finite number" % name) from None
    if not isfinite(number):
        raise ValueError("%s must be a finite number" % name)
    return number


def _distance(value: Any, name: str) -> float:
    value = _finite_number(value, name)
    if not 0.0 < value <= MAX_SEARCH_DISTANCE_MM:
        raise ValueError("%s must be > 0 and <= %s mm" % (name, MAX_SEARCH_DISTANCE_MM))
    return value


def _within(origin: Mapping[str, Any], candidates: Iterable[Mapping[str, Any]], limit: float) -> List[Dict[str, Any]]:
    matches: List[Tuple[float, str, Dict[str, Any]]] = []
    for candidate in candidates:
        distance = hypot(origin["x"] - candidate["x"], origin["y"] - candidate["y"])
        if distance <= limit:
            matches.append((distance, candidate["id"], dict(candidate, distance_mm=distance)))
    return [candidate for _, _, candidate in sorted(matches, key=lambda item: (item[0], item[1]))]


def _same_net(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return left["net"] == right["net"]


def _require_same_net(left: Mapping[str, Any], right: Mapping[str, Any]) -> None:
    if not _same_net(left, right):
        raise ValueError("Cannot create component bond across nets: %s != %s" % (left["net"], right["net"]))


def _bond(pin: Mapping[str, Any], pad: Optional[Mapping[str, Any]], copper: Optional[Mapping[str, Any]], status: str, solder: Mapping[str, float], warnings: List[str]) -> Dict[str, Any]:
    return {
        "pin_id": pin["id"], "pad_id": pad["id"] if pad else None,
        "copper_id": copper["id"] if copper else None,
        "side": copper.get("side") if copper else None,
        "net": pin["net"], "status": status, "solder": dict(solder), "warnings": list(warnings),
    }


def _warning(code: str, primitive_id: str, message: str) -> Dict[str, str]:
    return {"code": code, "primitive_id": primitive_id, "message": message}


def _result_status(bonds: List[Mapping[str, Any]]) -> str:
    statuses = {bond["status"] for bond in bonds}
    if not bonds:
        return "empty"
    if statuses == {"inferred"}:
        return "ready"
    if "inferred" in statuses:
        return "partial"
    return "unresolved"
