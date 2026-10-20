# SPDX-License-Identifier: Apache-2.0
"""Explicit part operating-limit comparisons; no rating or solver-field inference."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

PART_LIMIT_REPORT = "spike/part-limit-report/v1"
MAX_PART_LIMITS = 20_000
UNITS = {"voltage": {"V"}, "current": {"A"}, "temperature": {"degC", "K"},
         "power": {"W"}, "stress": {"Pa", "MPa"}, "frequency": {"Hz"}}
KEYS = {"id", "occurrence_id", "component_id", "label", "quantity", "unit", "lower", "upper",
        "reference", "value", "rating_source", "measurement_source", "evidence_status"}


def _number(value: Any, name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{name} must be a finite decimal or null")
    if isinstance(value, str) and len(value) > 64:
        raise ValueError(f"{name} exceeds the decimal text limit")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{name} must be a finite decimal or null") from None
    if not number.is_finite() or len(number.as_tuple().digits) > 18 or (number and abs(number.adjusted()) > 30):
        raise ValueError(f"{name} must be finite, at most 18 significant digits and exponent within ±30")
    return number


def _text(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


def evaluate_part_limits(part_limits: Any, component_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate captured scalar observations against supplied inclusive limits.

    Percentages measure excursion from an explicit reference toward the bound
    in that direction. Temperatures therefore use an allowed rise, never an
    absolute Celsius ratio. PASS applies only to the declared checks and inputs.
    """
    if not isinstance(part_limits, list) or len(part_limits) > MAX_PART_LIMITS:
        raise ValueError(f"part_limits must be an array with at most {MAX_PART_LIMITS} rules")
    components = {(row["occurrence_id"], row["component_id"]): row for row in component_rows}
    fitted = {key for key, row in components.items() if not row.get("dnp", False)}
    covered: set[tuple[str, str]] = set()
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for index, rule in enumerate(part_limits):
        prefix = f"part_limits[{index}]"
        if not isinstance(rule, dict) or set(rule) != KEYS:
            raise ValueError(f"{prefix} requires exactly the documented rule fields")
        for name in ("id", "occurrence_id", "component_id", "label", "quantity", "unit"):
            if not isinstance(rule[name], str) or not rule[name].strip() or len(rule[name]) > 256:
                raise ValueError(f"{prefix}.{name} requires a nonempty string of at most 256 characters")
        if rule["id"] in seen:
            raise ValueError(f"duplicate part-limit rule id: {rule['id']}")
        seen.add(rule["id"])
        key = (rule["occurrence_id"], rule["component_id"])
        if key not in components:
            raise ValueError(f"part-limit target does not exist: {key[0]}/{key[1]}")
        if rule["unit"] not in UNITS.get(rule["quantity"], set()):
            raise ValueError(f"{prefix} quantity/unit pair is unsupported")
        for name in ("rating_source", "measurement_source"):
            if not isinstance(rule[name], str) or len(rule[name]) > 2000:
                raise ValueError(f"{prefix}.{name} must be text of at most 2000 characters")
        if rule["evidence_status"] not in {"reviewed", "unreviewed"}:
            raise ValueError(f"{prefix}.evidence_status must be reviewed or unreviewed")
        lower, upper, reference, value = (_number(rule[name], f"{prefix}.{name}")
                                          for name in ("lower", "upper", "reference", "value"))
        if lower is not None and upper is not None and lower >= upper:
            raise ValueError(f"{prefix} lower must be smaller than upper")
        if reference is not None and ((lower is not None and reference <= lower)
                                      or (upper is not None and reference >= upper)):
            raise ValueError(f"{prefix} reference must be strictly inside its declared bounds")
        if rule["quantity"] == "temperature":
            absolute_zero = Decimal("-273.15") if rule["unit"] == "degC" else Decimal(0)
            if any(number is not None and number < absolute_zero for number in (lower, upper, reference, value)):
                raise ValueError(f"{prefix} temperature is below absolute zero")
        missing = []
        if lower is None and upper is None:
            missing.append("No operating limit supplied")
        if value is None:
            missing.append("No observation supplied")
        if not rule["rating_source"].strip():
            missing.append("Rating source/operating conditions missing")
        if not rule["measurement_source"].strip():
            missing.append("Observation source/case missing")
        if rule["evidence_status"] != "reviewed":
            missing.append("Observation not reviewed")
        comparison = "UNKNOWN"
        if value is not None and (lower is not None or upper is not None):
            comparison = "FAIL" if ((lower is not None and value < lower)
                                     or (upper is not None and value > upper)) else "PASS"
        stress = headroom = None
        with localcontext() as context:
            context.prec = 80
            if value is not None and reference is not None:
                if value >= reference and upper is not None:
                    stress = max(Decimal(0), (value - reference) / (upper - reference) * 100)
                elif value < reference and lower is not None:
                    stress = max(Decimal(0), (reference - value) / (reference - lower) * 100)
                elif lower is not None or upper is not None:
                    stress = Decimal(0)  # Excursion away from a one-sided bound.
                if stress is not None:
                    stress = stress.quantize(Decimal("0.000001"))
                    headroom = Decimal(100) - stress
            row = {**rule, "reference_designator": components[key].get("reference", ""),
                   "lower": _text(lower), "upper": _text(upper), "reference": _text(reference), "value": _text(value),
                   "comparison_status": comparison, "status": "UNKNOWN" if missing else comparison,
                   "stress_percent": _text(stress), "headroom_percent": _text(headroom),
                   "percentage_note": "Explicit-reference allowance utilization" if reference is not None else "Reference missing; percentages unavailable",
                   "notes": missing}
        if key not in fitted:
            row["status"] = "NOT_APPLICABLE"
            row["notes"] = ["Part is not populated"]
        else:
            covered.add(key)
        rows.append(row)
    counts = {status: sum(row["status"] == status for row in rows)
              for status in ("PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE")}
    unchecked = [{"occurrence_id": key[0], "component_id": key[1],
                  "reference": components[key].get("reference", "")} for key in sorted(fitted - covered)]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["occurrence_id"], row["component_id"]), []).append(row)
    part_summary = []
    for key, checks in sorted(grouped.items()):
        statuses = {row["status"] for row in checks}
        status = ("NOT_APPLICABLE" if key not in fitted else "FAIL" if "FAIL" in statuses
                  else "UNKNOWN" if "UNKNOWN" in statuses else "PASS")
        complete_percentages = all(row["stress_percent"] is not None for row in checks) and status in {"PASS", "FAIL"}
        with localcontext() as context:
            context.prec = 80
            worst = max(Decimal(row["stress_percent"]) for row in checks) if complete_percentages else None
            part_summary.append({"occurrence_id": key[0], "component_id": key[1],
                                 "reference": components[key].get("reference", ""), "status": status,
                                 "declared_checks": len(checks), "stress_percent": _text(worst),
                                 "headroom_percent": _text(Decimal(100) - worst) if worst is not None else None})
    overall = "FAIL" if counts["FAIL"] else "INCOMPLETE" if counts["UNKNOWN"] or unchecked or not covered else "PASS"
    return {"contract": PART_LIMIT_REPORT, "overall_status": overall, "counts": counts, "rows": rows,
            "unchecked_components": unchecked, "fitted_components": len(fitted),
            "covered_components": len(covered), "part_summary": part_summary,
            "statement": "Captured-input operating-limit checks only. PASS covers declared rules, not all possible failure modes, datasheet qualification, native DRC or hardware safety. No ratings, pin loads, field extrema or solver validity were inferred."}
