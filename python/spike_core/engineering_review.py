# SPDX-License-Identifier: Apache-2.0
"""Bounded, read-only engineering review and small analytical helpers.

This module consumes normalized SPIKE dictionaries.  It does not run native
DRC/ERC, infer manufacturer data, or modify a design.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import math
from typing import Any
from .part_limits import evaluate_part_limits


REVIEW_REQUEST = "spike/engineering-review-request/v1"
REVIEW_RESULT = "spike/engineering-review-result/v1"
QUICK_REQUEST = "spike/quick-engineering-tool-request/v1"
QUICK_RESULT = "spike/quick-engineering-tool-result/v1"
MAX_BOARDS = 30
MAX_COMPONENTS = 20_000
MAX_REQUEST_BYTES = 8 * 1024 * 1024
_OVERRIDE_KEYS = {
    "occurrence_id", "component_id", "unit_cost", "currency", "mass_g",
    "power_w", "dnp",
}


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _exact_keys(value: dict[str, Any], allowed: set[str], required: set[str], name: str) -> None:
    extra = set(value) - allowed
    missing = required - set(value)
    if extra or missing:
        details = []
        if extra:
            details.append(f"unknown keys: {', '.join(sorted(extra))}")
        if missing:
            details.append(f"missing keys: {', '.join(sorted(missing))}")
        raise ValueError(f"{name} has " + "; ".join(details))


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 256:
        raise ValueError(f"{name} must be a non-empty string of at most 256 characters")
    return value.strip()


def _decimal(value: Any, name: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError(f"{name} must be a decimal number")
    if isinstance(value, str) and len(value) > 64:
        raise ValueError(f"{name} decimal text must be at most 64 characters")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be a decimal number") from None
    digits = len(number.as_tuple().digits)
    if (not number.is_finite() or number < 0 or (positive and number == 0)
            or number.adjusted() < -30 or number.adjusted() > 30 or digits > 18):
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError(
            f"{name} must be finite and {qualifier}, with at most 18 significant digits "
            "and adjusted exponent from -30 through 30"
        )
    return number


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    with localcontext() as context:
        context.prec = 100
        return format(value.normalize(), "f")


def _explicit(component: dict[str, Any], *names: str, default: Any = "") -> Any:
    """Return an explicit normalized value without deriving or guessing one."""
    containers = [component]
    for key in ("properties", "metadata"):
        candidate = component.get(key)
        if isinstance(candidate, dict):
            containers.append(candidate)
    lowered = {name.lower() for name in names}
    for container in containers:
        for key, value in container.items():
            if str(key).lower() in lowered and value is not None:
                return value
    return default


def _canonical_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                             allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"request must contain canonical JSON values with finite numbers: {exc}") from None
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError(f"canonical request exceeds {MAX_REQUEST_BYTES} bytes")
    return encoded


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def review_engineering(request: Any) -> dict[str, Any]:
    request = _object(request, "request")
    request_digest = hashlib.sha256(_canonical_bytes(request)).hexdigest()
    _exact_keys(request, {"contract", "boards", "overrides", "part_limits"}, {"contract", "boards", "overrides"}, "request")
    if request["contract"] != REVIEW_REQUEST:
        raise ValueError(f"contract must be {REVIEW_REQUEST}")
    boards = request["boards"]
    overrides = request["overrides"]
    if not isinstance(boards, list) or not 1 <= len(boards) <= MAX_BOARDS:
        raise ValueError(f"boards must contain 1 to {MAX_BOARDS} entries")
    if not isinstance(overrides, list):
        raise ValueError("overrides must be an array")

    board_records: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []
    occurrence_ids: set[str] = set()
    component_keys: set[tuple[str, str]] = set()
    component_total = 0
    for index, raw_board in enumerate(boards):
        board = _object(raw_board, f"boards[{index}]")
        _exact_keys(board, {"occurrence_id", "design"}, {"occurrence_id", "design"}, f"boards[{index}]")
        occurrence_id = _identifier(board["occurrence_id"], f"boards[{index}].occurrence_id")
        if occurrence_id in occurrence_ids:
            raise ValueError(f"duplicate occurrence_id: {occurrence_id}")
        occurrence_ids.add(occurrence_id)
        design = _object(board["design"], f"boards[{index}].design")
        components = design.get("components", [])
        if not isinstance(components, list):
            raise ValueError(f"boards[{index}].design.components must be an array")
        component_total += len(components)
        if component_total > MAX_COMPONENTS:
            raise ValueError(f"component limit exceeds {MAX_COMPONENTS}")
        normalized_components = []
        for component_index, raw_component in enumerate(components):
            component = _object(raw_component, f"boards[{index}].design.components[{component_index}]")
            component_id = _identifier(component.get("id", component.get("component_id")),
                                       f"component {component_index} id")
            key = (occurrence_id, component_id)
            if key in component_keys:
                raise ValueError(f"duplicate component id in occurrence: {occurrence_id}/{component_id}")
            component_keys.add(key)
            normalized_components.append(component)
        board_records.append((occurrence_id, design, normalized_components))

    parsed_overrides: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw_override in enumerate(overrides):
        override = _object(raw_override, f"overrides[{index}]")
        _exact_keys(override, _OVERRIDE_KEYS, {"occurrence_id", "component_id"}, f"overrides[{index}]")
        if len(override) == 2:
            raise ValueError(f"overrides[{index}] must set at least one value")
        occurrence_id = _identifier(override["occurrence_id"], f"overrides[{index}].occurrence_id")
        component_id = _identifier(override["component_id"], f"overrides[{index}].component_id")
        key = (occurrence_id, component_id)
        if key not in component_keys:
            raise ValueError(f"override target does not exist: {occurrence_id}/{component_id}")
        if key in parsed_overrides:
            raise ValueError(f"duplicate override: {occurrence_id}/{component_id}")
        parsed = dict(override)
        for field in ("unit_cost", "mass_g", "power_w"):
            if field in parsed and parsed[field] is not None:
                parsed[field] = _decimal(parsed[field], f"overrides[{index}].{field}")
        if "currency" in parsed and parsed["currency"] is not None:
            parsed["currency"] = _identifier(parsed["currency"], f"overrides[{index}].currency").upper()
            if len(parsed["currency"]) != 3 or not parsed["currency"].isalpha():
                raise ValueError("currency must be an explicit three-letter code")
        if "unit_cost" in parsed and "currency" not in parsed:
            raise ValueError("unit_cost requires currency in the same override")
        if "currency" in parsed and "unit_cost" not in parsed:
            raise ValueError("currency requires unit_cost in the same override")
        if "unit_cost" in parsed and ((parsed["unit_cost"] is None) != (parsed["currency"] is None)):
            raise ValueError("unit_cost and currency must both be null or both have values")
        if "dnp" in parsed and not isinstance(parsed["dnp"], bool):
            raise ValueError("dnp must be boolean")
        parsed_overrides[key] = parsed

    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    references_by_occurrence: dict[str, Counter[str]] = {}
    for occurrence_id, design, components in board_records:
        reference_counts = Counter(str(_explicit(c, "reference", "ref", default="")).strip() for c in components)
        references_by_occurrence[occurrence_id] = reference_counts
        stackup = design.get("stackup")
        metadata = design.get("metadata")
        metadata_stackup = metadata.get("spike.v1.stackup") if isinstance(metadata, dict) else None
        if ((not isinstance(stackup, list) or not stackup)
                and (not isinstance(metadata_stackup, list) or not metadata_stackup)):
            findings.append({"code": "physical_stackup_absent", "severity": "warning",
                             "occurrence_id": occurrence_id,
                             "message": "No explicit physical stackup is present; stackup-dependent review is unavailable."})
        for component in components:
            component_id = str(component.get("id", component.get("component_id"))).strip()
            override = parsed_overrides.get((occurrence_id, component_id), {})
            reference = str(_explicit(component, "reference", "ref", default="")).strip()
            value = str(_explicit(component, "value", default="")).strip()
            footprint = str(_explicit(component, "footprint", "footprint_id", "package", "package_name", default="")).strip()
            mpn = str(_explicit(component, "mpn", "manufacturer_part_number", default="")).strip()
            explicit_dnp = _explicit(component, "dnp", "do_not_populate", default=False)
            dnp = override.get("dnp", explicit_dnp if isinstance(explicit_dnp, bool) else False)
            base_values: dict[str, Any] = {}
            for field in ("unit_cost", "mass_g", "power_w"):
                raw_value = _explicit(component, field, default=None)
                base_values[field] = None if raw_value is None else _decimal(
                    raw_value, f"component {occurrence_id}/{component_id} {field}"
                )
            raw_currency = _explicit(component, "currency", default=None)
            base_values["currency"] = None if raw_currency is None else _identifier(
                raw_currency, f"component {occurrence_id}/{component_id} currency"
            ).upper()
            if base_values["currency"] is not None and (len(base_values["currency"]) != 3
                    or not base_values["currency"].isalpha()):
                raise ValueError(f"component {occurrence_id}/{component_id} currency must be a three-letter code")
            if (base_values["unit_cost"] is None) != (base_values["currency"] is None):
                raise ValueError(f"component {occurrence_id}/{component_id} unit_cost and currency must both be declared")
            resolved = {field: override[field] if field in override else base_values[field]
                        for field in ("unit_cost", "currency", "mass_g", "power_w")}
            row = {"occurrence_id": occurrence_id, "component_id": component_id,
                   "reference": reference, "value": value, "footprint": footprint,
                   "mpn": mpn, "dnp": dnp,
                   "unit_cost": _decimal_text(resolved["unit_cost"]) if resolved["unit_cost"] is not None else None,
                   "currency": resolved["currency"],
                   "mass_g": _decimal_text(resolved["mass_g"]) if resolved["mass_g"] is not None else None,
                   "power_w": _decimal_text(resolved["power_w"]) if resolved["power_w"] is not None else None}
            rows.append(row)
            context = {"occurrence_id": occurrence_id, "component_id": component_id, "reference": reference}
            if not reference:
                findings.append({"code": "missing_reference", "severity": "error", **context,
                                 "message": "Component has no explicit reference."})
            if not mpn and not dnp:
                findings.append({"code": "missing_mpn", "severity": "warning", **context,
                                 "message": "Fitted component has no explicit manufacturer part number."})
            if not footprint:
                findings.append({"code": "missing_footprint", "severity": "warning", **context,
                                 "message": "Component has no explicit footprint."})
            if reference and reference_counts[reference] > 1:
                findings.append({"code": "duplicate_reference", "severity": "error", **context,
                                 "message": "Reference is duplicated within this board occurrence."})

    groups: dict[tuple[str, str, str, str, bool], dict[str, Any]] = {}
    for row in rows:
        key = (row["occurrence_id"], row["value"], row["footprint"], row["mpn"], row["dnp"])
        group = groups.setdefault(key, {"occurrence_id": row["occurrence_id"], "value": row["value"],
                                      "footprint": row["footprint"], "mpn": row["mpn"], "dnp": row["dnp"],
                                      "count": 0, "references": [], "_rows": []})
        group["count"] += 1
        group["references"].append(row["reference"])
        group["_rows"].append(row)

    grouped_bom = []
    with localcontext() as context:
        context.prec = 100
        for group in groups.values():
            group_rows = group.pop("_rows")
            active_rows = [] if group["dnp"] else group_rows
            cost_subtotals: defaultdict[str, Decimal] = defaultdict(Decimal)
            for row in active_rows:
                if row["unit_cost"] is not None:
                    cost_subtotals[row["currency"]] += Decimal(row["unit_cost"])
            group["coverage"] = {
                "cost": {"known_components": sum(row["unit_cost"] is not None for row in active_rows),
                         "unknown_components": sum(row["unit_cost"] is None for row in active_rows),
                         "subtotals_by_currency": {currency: _decimal_text(total)
                                                    for currency, total in sorted(cost_subtotals.items())}},
                "mass_g": {"known_components": sum(row["mass_g"] is not None for row in active_rows),
                           "unknown_components": sum(row["mass_g"] is None for row in active_rows),
                           "subtotal": _decimal_text(sum((Decimal(row["mass_g"]) for row in active_rows
                                                          if row["mass_g"] is not None), Decimal(0)))},
                "power_w": {"known_components": sum(row["power_w"] is not None for row in active_rows),
                            "unknown_components": sum(row["power_w"] is None for row in active_rows),
                            "subtotal": _decimal_text(sum((Decimal(row["power_w"]) for row in active_rows
                                                           if row["power_w"] is not None), Decimal(0)))},
            }
            grouped_bom.append(group)

    fitted = [row for row in rows if not row["dnp"]]
    with localcontext() as context:
        context.prec = 100
        currency_totals: defaultdict[str, Decimal] = defaultdict(Decimal)
        for row in fitted:
            if row["unit_cost"] is not None:
                currency_totals[row["currency"]] += Decimal(row["unit_cost"])
        def metric(name: str) -> dict[str, Any]:
            known = [row for row in fitted if row[name] is not None]
            return {"known_components": len(known), "unknown_components": len(fitted) - len(known),
                    "total": _decimal_text(sum((Decimal(row[name]) for row in known), Decimal(0)))}

        summary = {"boards": len(boards), "components": len(rows), "fitted_components": len(fitted),
                   "dnp_components": len(rows) - len(fitted),
                   "cost": {"known_components": sum(row["unit_cost"] is not None for row in fitted),
                            "unknown_components": sum(row["unit_cost"] is None for row in fitted),
                            "subtotals_by_currency": {key: _decimal_text(value) for key, value in sorted(currency_totals.items())}},
                   "mass_g": metric("mass_g"), "power_w": metric("power_w")}

    return {"contract": REVIEW_RESULT, "snapshot_sha256": request_digest,
            "part_limit_report": evaluate_part_limits(request.get("part_limits", []), rows),
            "limits": {"max_boards": MAX_BOARDS, "max_components": MAX_COMPONENTS},
            "component_rows": rows,
            "grouped_bom": sorted(grouped_bom, key=lambda g: (g["occurrence_id"], g["dnp"], g["value"], g["footprint"], g["mpn"])),
            "summary": summary,
            "readiness": {"findings": findings, "native_drc": "unknown", "erc": "unknown",
                          "manufacturing": "unknown", "mechanical": "unknown",
                          "statement": "Contextual diagnostics only; no native DRC, ERC, manufacturing, or mechanical pass is claimed."}}


def quick_engineering_tool(request: Any) -> dict[str, Any]:
    request = _object(request, "request")
    request_digest = hashlib.sha256(_canonical_bytes(request)).hexdigest()
    if request.get("contract") != QUICK_REQUEST:
        raise ValueError(f"contract must be {QUICK_REQUEST}")
    tool = request.get("tool")
    specs = {
        "resistor_divider": {"vin", "r_top_ohm", "r_bottom_ohm"},
        "rc_step": {"time_s", "r_ohm", "c_f", "vin"},
        "dc_trace_resistance": {"length_m", "width_m", "thickness_m", "resistivity_ohm_m"},
    }
    if tool not in specs:
        raise ValueError("tool must be resistor_divider, rc_step, or dc_trace_resistance")
    _exact_keys(request, {"contract", "tool", *specs[tool]}, {"contract", "tool", *specs[tool]}, "request")
    values = {name: _decimal(request[name], name) for name in specs[tool]}
    try:
        with localcontext() as context:
            context.prec = 100
            if tool == "resistor_divider":
                total_r = values["r_top_ohm"] + values["r_bottom_ohm"]
                if total_r == 0:
                    raise ValueError("divider total resistance must be positive")
                current = values["vin"] / total_r
                result = {"vout_v": values["vin"] * values["r_bottom_ohm"] / total_r,
                          "current_a": current, "top_power_w": current * current * values["r_top_ohm"],
                          "bottom_power_w": current * current * values["r_bottom_ohm"]}
                applicability = "Ideal unloaded passive divider at DC; source impedance, loading, tolerance, and temperature effects are excluded."
            elif tool == "rc_step":
                if values["r_ohm"] == 0 or values["c_f"] == 0:
                    raise ValueError("r_ohm and c_f must be positive")
                tau = values["r_ohm"] * values["c_f"]
                ratio = values["time_s"] / tau
                ratio_float = float(ratio)
                if not math.isfinite(ratio_float):
                    raise ValueError("time_s/(r_ohm*c_f) must produce a finite ratio")
                fraction_float = -math.expm1(-ratio_float)
                if not math.isfinite(fraction_float):
                    raise ValueError("RC step calculation must produce finite outputs")
                fraction = Decimal(str(fraction_float))
                result = {"tau_s": tau, "capacitor_voltage_v": values["vin"] * fraction,
                          "resistor_current_a": values["vin"] / values["r_ohm"] * (Decimal(1) - fraction)}
                applicability = "Ideal first-order RC charging from zero volts after a DC step; parasitics, leakage, tolerance, and source impedance are excluded."
            else:
                for name in ("width_m", "thickness_m", "resistivity_ohm_m"):
                    if values[name] == 0:
                        raise ValueError(f"{name} must be positive")
                result = {"resistance_ohm": values["resistivity_ohm_m"] * values["length_m"] /
                                              (values["width_m"] * values["thickness_m"])}
                applicability = "Uniform rectangular conductor at DC with supplied bulk resistivity; contacts, vias, spreading, plating variation, and temperature rise are excluded."
    except (InvalidOperation, OverflowError, ZeroDivisionError) as exc:
        raise ValueError(f"quick tool calculation is outside supported numeric bounds: {exc}") from None
    if any(not value.is_finite() for value in result.values()):
        raise ValueError("quick tool calculation must produce finite outputs")
    return {"contract": QUICK_RESULT, "request_sha256": request_digest, "tool": tool,
            "result": {name: _decimal_text(value) for name, value in result.items()},
            "units": {"vout_v": "V", "current_a": "A", "top_power_w": "W", "bottom_power_w": "W",
                      "tau_s": "s", "capacitor_voltage_v": "V", "resistor_current_a": "A", "resistance_ohm": "ohm"},
            "applicability": applicability}
