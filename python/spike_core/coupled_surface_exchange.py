# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded conservative exchange across a caller-supplied surface overlap map.

This module performs no CAD intersection, normal inference, solver stepping, or
coupling iteration.  It only applies an admitted sparse overlap operator in a
common Cartesian frame.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections.abc import Callable, Mapping
from fractions import Fraction
from typing import Any

from .multiboard_identity import canonical_json_digest


REQUEST_CONTRACT = "spike/coupled-surface-exchange-request/v1"
RESULT_CONTRACT = "spike/coupled-surface-exchange-result/v1"
MAX_CONTROL_BYTES = 8 * 1024 * 1024
MAX_TOTAL_FACES = 512
MAX_OVERLAPS = 8192
MIN_AREA_M2 = sys.float_info.min
_COVERAGE_REL_TOL = 1.0e-12
_DIGEST = re.compile(r"[0-9a-f]{64}")
_CONTEXT_KEYS = {
    "quantity", "normal_relation", "units", "source_patch",
    "destination_patch", "overlaps",
}
_REQUEST_REQUIRED = {
    "contract", "transfer_id", "quantity", "normal_relation", "units",
    "source_patch", "destination_patch", "overlaps", "context_digest",
    "source_values",
}
_REQUEST_OPTIONAL = {"destination_values", "destination_value_unit"}


def _fail(code: str, detail: str) -> None:
    raise ValueError(f"{code}: {detail}")


def _keys(value: Any, required: set[str], optional: set[str] | None = None,
          *, code: str = "COUPLED_SURFACE_FIELDS") -> None:
    optional = optional or set()
    if not isinstance(value, dict):
        _fail(code, "expected an object")
    actual = set(value)
    if not required <= actual or actual - required - optional:
        _fail(code, "unexpected or missing fields")


def _text(value: Any, label: str) -> str:
    if (not isinstance(value, str) or value != value.strip() or not value
            or len(value) > 256):
        _fail("COUPLED_SURFACE_ID", f"{label} must be a bounded nonempty string")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        _fail("COUPLED_SURFACE_DIGEST", f"{label} must be a lowercase SHA-256 digest")
    return value


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        _fail("COUPLED_SURFACE_NUMBER", f"{label} must be a finite number, not bool/text")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"COUPLED_SURFACE_NUMBER: {label} is outside finite floating-point range") from exc
    if not math.isfinite(result) or (positive and result <= 0.0):
        qualifier = "positive " if positive else ""
        _fail("COUPLED_SURFACE_NUMBER", f"{label} must be a finite {qualifier}number")
    return result


def _area(value: Any, label: str) -> float:
    result = _number(value, label, positive=True)
    if result < MIN_AREA_M2:
        _fail("COUPLED_SURFACE_AREA_RANGE",
              f"{label} must be at least the minimum normal binary64 area {MIN_AREA_M2} m2")
    return result


def _same_area(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=_COVERAGE_REL_TOL, abs_tol=0.0)


def _check_cancel(cancel_check: Callable[[], Any] | None) -> None:
    if cancel_check is None:
        return
    try:
        cancelled = cancel_check()
    except Exception as exc:
        _fail("COUPLED_SURFACE_CANCEL_CHECK", str(exc))
    if cancelled:
        _fail("COUPLED_SURFACE_CANCELLED", "surface exchange cancelled")


def _bounded_json(value: Any) -> None:
    try:
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("COUPLED_SURFACE_JSON: finite JSON data required") from exc
    if len(encoded) > MAX_CONTROL_BYTES:
        _fail("COUPLED_SURFACE_RESOURCE", "control payload exceeds 8 MiB")


def _frame(value: Any, label: str) -> dict[str, Any]:
    _keys(value, {"id", "rank", "handedness"})
    frame_id = _text(value["id"], f"{label} frame id")
    if type(value["rank"]) is not int or value["rank"] != 3:
        _fail("COUPLED_SURFACE_FRAME", f"{label} frame rank must be integer 3")
    if value["handedness"] != "right":
        _fail("COUPLED_SURFACE_FRAME", f"{label} frame must be right-handed")
    return {"id": frame_id, "rank": 3, "handedness": "right"}


def _patch(value: Any, label: str) -> tuple[dict[str, Any], dict[str, float]]:
    _keys(value, {"participant_id", "patch_id", "geometry_digest", "frame", "faces"})
    participant_id = _text(value["participant_id"], f"{label} participant")
    patch_id = _text(value["patch_id"], f"{label} patch")
    geometry_digest = _digest(value["geometry_digest"], f"{label} geometry")
    frame = _frame(value["frame"], label)
    faces = value["faces"]
    if not isinstance(faces, list) or not faces:
        _fail("COUPLED_SURFACE_FACE", f"{label} faces must be a nonempty array")
    by_id: dict[str, float] = {}
    normalized_faces = []
    for face in faces:
        _keys(face, {"id", "area_m2"})
        face_id = _text(face["id"], f"{label} face id")
        if face_id in by_id:
            _fail("COUPLED_SURFACE_FACE", f"duplicate {label} face {face_id}")
        area = _area(face["area_m2"], f"{label} face {face_id} area")
        by_id[face_id] = area
        normalized_faces.append({"id": face_id, "area_m2": area})
    normalized_faces.sort(key=lambda item: item["id"])
    return ({"participant_id": participant_id, "patch_id": patch_id,
             "geometry_digest": geometry_digest, "frame": frame,
             "faces": normalized_faces}, by_id)


def _units(value: Any, quantity: str) -> dict[str, str]:
    _keys(value, {"length", "area", "source_intensive", "destination_integrated"})
    expected = ({"length": "m", "area": "m2", "source_intensive": "W/m2",
                 "destination_integrated": "W"} if quantity == "heat_flux" else
                {"length": "m", "area": "m2", "source_intensive": "N/m2",
                 "destination_integrated": "N"})
    if value != expected:
        _fail("COUPLED_SURFACE_UNITS", f"{quantity} requires exact SI units {expected}")
    return expected


def _validated_context(value: Mapping[str, Any],
                       cancel_check: Callable[[], Any] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("COUPLED_SURFACE_FIELDS", "request must be an object")
    unknown = set(value) - _REQUEST_REQUIRED - _REQUEST_OPTIONAL
    if unknown or not _CONTEXT_KEYS <= set(value):
        _fail("COUPLED_SURFACE_FIELDS", "unexpected or missing context fields")
    quantity = value["quantity"]
    if quantity not in ("heat_flux", "traction"):
        _fail("COUPLED_SURFACE_QUANTITY", "only heat_flux and traction are supported")
    if value["normal_relation"] != "opposite_outward_normals":
        _fail("COUPLED_SURFACE_NORMALS", "opposite_outward_normals must be explicit")
    units = _units(value["units"], quantity)
    source, source_areas = _patch(value["source_patch"], "source")
    destination, destination_areas = _patch(value["destination_patch"], "destination")
    if len(source_areas) + len(destination_areas) > MAX_TOTAL_FACES:
        _fail("COUPLED_SURFACE_RESOURCE", "source and destination exceed 512 total faces")
    if source["frame"] != destination["frame"]:
        _fail("COUPLED_SURFACE_FRAME", "source and destination must name the same frame")
    if ((source["participant_id"], source["patch_id"])
            == (destination["participant_id"], destination["patch_id"])):
        _fail("COUPLED_SURFACE_PATCH", "source and destination patch identities must differ")
    overlaps = value["overlaps"]
    if not isinstance(overlaps, list) or not overlaps or len(overlaps) > MAX_OVERLAPS:
        _fail("COUPLED_SURFACE_RESOURCE", "overlaps must contain 1..8192 triples")
    pairs: set[tuple[str, str]] = set()
    normalized_overlaps = []
    source_parts = {face_id: [] for face_id in source_areas}
    destination_parts = {face_id: [] for face_id in destination_areas}
    for index, overlap in enumerate(overlaps):
        if index % 256 == 0:
            _check_cancel(cancel_check)
        _keys(overlap, {"source_face_id", "destination_face_id", "area_m2"})
        source_id = _text(overlap["source_face_id"], "overlap source face")
        destination_id = _text(overlap["destination_face_id"], "overlap destination face")
        if source_id not in source_areas or destination_id not in destination_areas:
            _fail("COUPLED_SURFACE_OVERLAP", "overlap references an unknown face")
        pair = (source_id, destination_id)
        if pair in pairs:
            _fail("COUPLED_SURFACE_OVERLAP", "duplicate source/destination overlap pair")
        pairs.add(pair)
        area = _area(overlap["area_m2"], "overlap area")
        source_parts[source_id].append(area)
        destination_parts[destination_id].append(area)
        normalized_overlaps.append({"source_face_id": source_id,
                                    "destination_face_id": destination_id,
                                    "area_m2": area})
    source_coverage = {face_id: _finite_sum(parts, "source overlap coverage")
                       for face_id, parts in source_parts.items()}
    destination_coverage = {face_id: _finite_sum(parts, "destination overlap coverage")
                            for face_id, parts in destination_parts.items()}
    for face_id, area in source_areas.items():
        if not _same_area(source_coverage[face_id], area):
            _fail("COUPLED_SURFACE_COVERAGE", f"source face {face_id} is not exactly covered")
    for face_id, area in destination_areas.items():
        if not _same_area(destination_coverage[face_id], area):
            _fail("COUPLED_SURFACE_COVERAGE", f"destination face {face_id} is not exactly covered")
    normalized_overlaps.sort(key=lambda item: (item["source_face_id"], item["destination_face_id"]))
    canonical = {"contract": "spike/coupled-surface-exchange-context/v1",
                 "quantity": quantity, "normal_relation": value["normal_relation"],
                 "units": units, "source_patch": source,
                 "destination_patch": destination, "overlaps": normalized_overlaps}
    return {"canonical": canonical, "quantity": quantity, "units": units,
            "source": source, "destination": destination,
            "source_areas": source_areas, "destination_areas": destination_areas,
            "overlaps": normalized_overlaps,
            "source_coverage": source_coverage,
            "destination_coverage": destination_coverage}


def coupled_surface_context_digest(value: Mapping[str, Any]) -> str:
    """Return the canonical digest binding patch identities, geometry, units and map."""
    return canonical_json_digest(_validated_context(value)["canonical"])


def _field_values(raw: Any, areas: Mapping[str, float], quantity: str,
                  label: str) -> dict[str, float | list[float]]:
    if not isinstance(raw, list) or len(raw) != len(areas):
        _fail("COUPLED_SURFACE_VALUES", f"{label} must cover every face exactly once")
    result: dict[str, float | list[float]] = {}
    components = 1 if quantity == "heat_flux" else 3
    for item in raw:
        _keys(item, {"face_id", "value"})
        face_id = _text(item["face_id"], f"{label} face")
        if face_id not in areas or face_id in result:
            _fail("COUPLED_SURFACE_VALUES", f"{label} has an unknown or duplicate face")
        if components == 1:
            result[face_id] = _number(item["value"], f"{label} value")
        else:
            vector = item["value"]
            if not isinstance(vector, list) or len(vector) != 3:
                _fail("COUPLED_SURFACE_VALUES", f"{label} requires 3-vectors")
            result[face_id] = [_number(component, f"{label} vector component")
                               for component in vector]
    if set(result) != set(areas):
        _fail("COUPLED_SURFACE_VALUES", f"{label} face coverage is incomplete")
    return result


def _component(value: float | list[float], index: int) -> float:
    return value if isinstance(value, float) else value[index]


def _shape(values: list[float]) -> float | list[float]:
    return values[0] if len(values) == 1 else values


def _finite_sum(values: list[float], label: str) -> float:
    try:
        result = math.fsum(values)
    except OverflowError:
        # A large signed sum can overflow an intermediate even when cancellation
        # makes the final total representable. Binary floats are exact dyadic
        # rationals, so this bounded fallback recovers their exact sum.
        exact = sum((Fraction.from_float(value) for value in values), Fraction())
        if not exact:
            return 0.0
        try:
            result = float(exact)
        except OverflowError as exact_exc:
            raise ValueError(
                f"COUPLED_SURFACE_RANGE: {label} exceeds finite floating-point range") from exact_exc
        if result == 0.0:
            _fail("COUPLED_SURFACE_UNDERFLOW",
                  f"{label} has a nonzero exact sum below binary64 range")
    if not math.isfinite(result):
        _fail("COUPLED_SURFACE_RANGE", f"{label} exceeds finite floating-point range")
    return result


def _guarded_product(factors: tuple[float, ...], label: str) -> float:
    """Multiply finite factors without false intermediate overflow/underflow."""
    if any(factor == 0.0 for factor in factors):
        return 0.0
    mantissa = 1.0
    exponent = 0
    for factor in factors:
        part, part_exponent = math.frexp(factor)
        mantissa *= part
        exponent += part_exponent
    try:
        result = math.ldexp(mantissa, exponent)
    except OverflowError as exc:
        raise ValueError(
            f"COUPLED_SURFACE_RANGE: {label} product exceeds finite floating-point range") from exc
    if not math.isfinite(result):
        _fail("COUPLED_SURFACE_RANGE", f"{label} product exceeds finite floating-point range")
    if result == 0.0:
        _fail("COUPLED_SURFACE_UNDERFLOW",
              f"{label} has a nonzero exact product below binary64 range")
    return result


def _guarded_ratio_product(numerator: float, denominator: float, value: float,
                           label: str) -> float:
    """Evaluate (numerator / denominator) * value in one scaled operation."""
    if value == 0.0:
        return 0.0
    numerator_part, numerator_exponent = math.frexp(numerator)
    denominator_part, denominator_exponent = math.frexp(denominator)
    value_part, value_exponent = math.frexp(value)
    mantissa = (numerator_part / denominator_part) * value_part
    exponent = numerator_exponent - denominator_exponent + value_exponent
    try:
        result = math.ldexp(mantissa, exponent)
    except OverflowError as exc:
        raise ValueError(
            f"COUPLED_SURFACE_RANGE: {label} exceeds finite floating-point range") from exc
    if not math.isfinite(result):
        _fail("COUPLED_SURFACE_RANGE", f"{label} exceeds finite floating-point range")
    if result == 0.0:
        _fail("COUPLED_SURFACE_UNDERFLOW",
              f"{label} has a nonzero exact value below binary64 range")
    return result


def transfer_coupled_surface_exchange(
        request: Mapping[str, Any], *,
        cancel_check: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Apply one sparse conservative/adjoint exchange; return no partial result."""
    if cancel_check is not None and not callable(cancel_check):
        _fail("COUPLED_SURFACE_CANCEL_CHECK", "cancel_check must be callable")
    _check_cancel(cancel_check)
    _bounded_json(request)
    _keys(request, _REQUEST_REQUIRED, _REQUEST_OPTIONAL)
    if request["contract"] != REQUEST_CONTRACT:
        _fail("COUPLED_SURFACE_CONTRACT", "unsupported request contract")
    transfer_id = _text(request["transfer_id"], "transfer id")
    has_destination = "destination_values" in request
    if has_destination != ("destination_value_unit" in request):
        _fail("COUPLED_SURFACE_VALUES", "destination_values and destination_value_unit are a pair")
    context = _validated_context(request, cancel_check)
    expected_digest = canonical_json_digest(context["canonical"])
    if _digest(request["context_digest"], "context") != expected_digest:
        _fail("COUPLED_SURFACE_STALE", "context digest does not match patch geometry, units and overlaps")
    quantity = context["quantity"]
    source = _field_values(request["source_values"], context["source_areas"],
                           quantity, "source values")
    destination_field = None
    destination_unit = None
    if has_destination:
        destination_unit = request["destination_value_unit"]
        allowed = {"K"} if quantity == "heat_flux" else {"m", "m/s"}
        if destination_unit not in allowed:
            _fail("COUPLED_SURFACE_UNITS", f"destination field unit must be one of {sorted(allowed)}")
        destination_field = _field_values(request["destination_values"],
                                          context["destination_areas"], quantity,
                                          "destination values")
    components = 1 if quantity == "heat_flux" else 3
    destination_terms = {face_id: [[] for _ in range(components)]
                         for face_id in context["destination_areas"]}
    reverse_terms = ({face_id: [[] for _ in range(components)]
                      for face_id in context["source_areas"]}
                     if destination_field is not None else None)
    for index, overlap in enumerate(context["overlaps"]):
        if index % 256 == 0:
            _check_cancel(cancel_check)
        source_id = overlap["source_face_id"]
        destination_id = overlap["destination_face_id"]
        area = overlap["area_m2"]
        for component in range(components):
            # Both participants report outward action.  Opposed interface normals
            # therefore require an action/reaction minus sign at the destination.
            destination_terms[destination_id][component].append(
                -_guarded_product(
                    (area, _component(source[source_id], component)),
                    "destination integrated value"))
            if reverse_terms is not None and destination_field is not None:
                reverse_terms[source_id][component].append(
                    _guarded_ratio_product(
                        area, context["source_areas"][source_id],
                        _component(destination_field[destination_id], component),
                        "reverse mapped value"))
    destination = {}
    for face_id, terms in destination_terms.items():
        destination[face_id] = _shape([
            _finite_sum(component_terms, "destination integrated value")
            for component_terms in terms])
    mapped_source = None
    if reverse_terms is not None:
        mapped_source = {}
        for face_id, terms in reverse_terms.items():
            mapped_source[face_id] = _shape([
                _finite_sum(component_terms, "reverse mapped value")
                for component_terms in terms])
    source_total = []
    destination_total = []
    balance = []
    for component in range(components):
        source_component = _finite_sum([
            _guarded_product((area, _component(source[face_id], component)),
                             "source integrated value")
            for face_id, area in context["source_areas"].items()], "source total")
        destination_component = _finite_sum([
            _component(destination[face_id], component)
            for face_id in context["destination_areas"]], "destination total")
        source_total.append(source_component)
        destination_total.append(destination_component)
        balance.append(_finite_sum([source_component, destination_component], "global balance"))
    diagnostics: dict[str, Any] = {
        "source_outward_integrated_total": _shape(source_total),
        "destination_outward_integrated_total": _shape(destination_total),
        "raw_global_balance": _shape(balance),
        "maximum_absolute_balance": max(abs(value) for value in balance),
        "coverage": {
            "source_area_m2": _finite_sum(list(context["source_areas"].values()), "source area"),
            "destination_area_m2": _finite_sum(list(context["destination_areas"].values()), "destination area"),
            "overlap_area_m2": _finite_sum([item["area_m2"] for item in context["overlaps"]], "overlap area"),
            "source_maximum_absolute_defect_m2": max(
                abs(context["source_coverage"][face_id] - area)
                for face_id, area in context["source_areas"].items()),
            "destination_maximum_absolute_defect_m2": max(
                abs(context["destination_coverage"][face_id] - area)
                for face_id, area in context["destination_areas"].items()),
        },
    }
    if destination_field is not None and mapped_source is not None:
        source_pairing_terms = []
        destination_pairing_terms = []
        for source_id, area in context["source_areas"].items():
            for component in range(components):
                source_pairing_terms.append(
                    _guarded_product(
                        (area, _component(source[source_id], component),
                         _component(mapped_source[source_id], component)),
                        "source pairing"))
        for destination_id in context["destination_areas"]:
            for component in range(components):
                destination_pairing_terms.append(
                    _guarded_product(
                        (_component(destination[destination_id], component),
                         _component(destination_field[destination_id], component)),
                        "destination pairing"))
        source_pairing = _finite_sum(source_pairing_terms, "source pairing")
        destination_pairing = _finite_sum(destination_pairing_terms, "destination pairing")
        pairing_balance = _finite_sum([source_pairing, destination_pairing], "pairing balance")
        if quantity == "heat_flux":
            pairing_kind, pairing_unit = "thermal_bilinear_duality_not_physical_work", "W*K"
        elif destination_unit == "m/s":
            pairing_kind, pairing_unit = "virtual_power", "W"
        else:
            pairing_kind, pairing_unit = "virtual_work", "J"
        diagnostics["adjoint_pairing"] = {
            "kind": pairing_kind, "unit": pairing_unit,
            "source_pairing": source_pairing,
            "destination_pairing": destination_pairing,
            "raw_pairing_balance": pairing_balance,
            "absolute_pairing_defect": abs(pairing_balance),
        }
    destination_records = [{"face_id": face_id, "value": destination[face_id]}
                           for face_id in sorted(destination)]
    result: dict[str, Any] = {
        "contract": RESULT_CONTRACT, "transfer_id": transfer_id,
        "context_digest": expected_digest,
        "request_digest": canonical_json_digest(request),
        "quantity": quantity, "status": "experimental",
        "production_qualified": False,
        "normal_relation": "opposite_outward_normals",
        "sign_convention": "source outward positive; destination outward action/reaction is negative",
        "destination_integrated_values": destination_records,
        "diagnostics": diagnostics,
        "limitations": [
            "Caller-supplied overlap areas and geometry digests are not authenticated or reconstructed.",
            "This transfer is not a CFD, structural, thermal, FSI, time-integration, or coupling master.",
            "No interface moment, pressure-normal conversion, temperature continuity, or physical validation is claimed.",
        ],
    }
    if mapped_source is not None:
        result["mapped_source_values"] = [
            {"face_id": face_id, "value": mapped_source[face_id]}
            for face_id in sorted(mapped_source)]
        result["mapped_source_value_unit"] = destination_unit
    _check_cancel(cancel_check)
    _bounded_json(result)
    return result


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("COUPLED_SURFACE_JSON", f"duplicate object key {key}")
        result[key] = value
    return result


def parse_coupled_surface_exchange_json(
        payload: str | bytes, *,
        cancel_check: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Strictly decode a bounded JSON request and execute the surface exchange."""
    if isinstance(payload, str):
        size = len(payload.encode("utf-8"))
        raw: str | bytes = payload
    elif isinstance(payload, bytes):
        size = len(payload)
        raw = payload
    else:
        _fail("COUPLED_SURFACE_JSON", "payload must be UTF-8 text or bytes")
    if size > MAX_CONTROL_BYTES:
        _fail("COUPLED_SURFACE_RESOURCE", "control payload exceeds 8 MiB")

    def reject_constant(value: str) -> None:
        _fail("COUPLED_SURFACE_NUMBER", f"non-finite JSON number {value} is forbidden")

    try:
        decoded = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs,
                             parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("COUPLED_SURFACE_JSON: invalid bounded UTF-8 JSON") from exc
    return transfer_coupled_surface_exchange(decoded, cancel_check=cancel_check)
