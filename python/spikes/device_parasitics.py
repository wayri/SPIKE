# SPDX-License-Identifier: Apache-2.0
"""Inert, family-agnostic semiconductor package-parasitic composition.

This module writes a SPICE subcircuit around an already named core
subcircuit.  It does not parse, load, or execute the core or its dependencies,
and it contains no semiconductor-family assumptions or numerical solver.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

import numpy as np


CONTRACT = "spikes/device-parasitics/v1"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}", re.ASCII)
_PIN_KEYS = frozenset({"resistance_ohm", "inductance_h"})
_PAIR_KEYS = frozenset({"pins", "capacitance_f", "leakage_resistance_ohm"})
_COUPLING_KEYS = frozenset({"pins", "coupling_coefficient"})
_LIMITATIONS = (
    "Generic unqualified constant lumped package parasitics; no manufacturer or process qualification.",
    "No voltage-dependent charge or capacitance is inferred.",
    "No self-heating, electrothermal feedback, or temperature dependence is inferred.",
    "No reverse-recovery, avalanche, switching-loss, or distributed electromagnetic behavior is inferred.",
    "The supplied core subcircuit and dependencies are not inspected, loaded, or executed by composition.",
    "R, L, C, leakage, and exact zero-volt links use existing owned native primitives when the returned deck is explicitly parsed and run through native_runner.",
    "Mutual terms use standard SPICE K syntax; the current owned parser/native runner does not execute K elements.",
)


def _identifier(label: str, value: Any) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be an ASCII identifier of at most 64 characters")
    return value


def _number(label: str, value: Any, *, maximum: float, zero_allowed: bool = True) -> float:
    if isinstance(value, (bool, str, bytes)):
        raise ValueError(f"{label} must be a finite SI number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite SI number") from exc
    minimum = 0.0 if zero_allowed else math.nextafter(0.0, 1.0)
    if not math.isfinite(number) or number < minimum or number > maximum:
        relation = "nonnegative" if zero_allowed else "positive"
        raise ValueError(f"{label} must be finite, {relation}, and at most {maximum:g}")
    return number


def _sequence(label: str, value: Any) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be a sequence")
    return value


def _pin_pair(
    label: str,
    value: Any,
    pin_lookup: Mapping[str, str],
) -> tuple[str, str]:
    values = _sequence(label, value)
    if len(values) != 2 or not all(isinstance(pin, str) for pin in values):
        raise ValueError(f"{label} must contain exactly two pin names")
    try:
        first, second = (pin_lookup[pin.casefold()] for pin in values)
    except KeyError as exc:
        raise ValueError(f"{label} references an unknown pin") from exc
    if first.casefold() == second.casefold():
        raise ValueError(f"{label} must reference two different pins")
    return first, second


def _entries(label: str, values: Any) -> Sequence[Any]:
    if values is None:
        return ()
    return _sequence(label, values)


def _normalise_pin_parasitics(
    pins: tuple[str, ...],
    values: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, dict[str, float]]:
    if values is None:
        values = {}
    if not isinstance(values, Mapping):
        raise ValueError("pin_parasitics must be a mapping keyed by pin name")
    pin_lookup = {pin.casefold(): pin for pin in pins}
    supplied: dict[str, Mapping[str, Any]] = {}
    for raw_pin, raw_config in values.items():
        if not isinstance(raw_pin, str) or raw_pin.casefold() not in pin_lookup:
            raise ValueError("pin_parasitics references an unknown pin")
        pin = pin_lookup[raw_pin.casefold()]
        if pin in supplied:
            raise ValueError(f"pin_parasitics duplicates pin {pin}")
        if not isinstance(raw_config, Mapping):
            raise ValueError(f"pin_parasitics[{pin}] must be a mapping")
        unknown = set(raw_config) - _PIN_KEYS
        if unknown:
            raise ValueError(
                f"pin_parasitics[{pin}] has unknown fields: {', '.join(sorted(map(str, unknown)))}"
            )
        supplied[pin] = raw_config
    resolved: dict[str, dict[str, float]] = {}
    for pin in pins:
        raw = supplied.get(pin, {})
        resolved[pin] = {
            "resistance_ohm": _number(
                f"pin_parasitics[{pin}].resistance_ohm",
                raw.get("resistance_ohm", 0.0), maximum=1.0e15,
            ),
            "inductance_h": _number(
                f"pin_parasitics[{pin}].inductance_h",
                raw.get("inductance_h", 0.0), maximum=1.0e3,
            ),
        }
    return resolved


def _normalise_between_pins(
    values: Any,
    pin_lookup: Mapping[str, str],
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    seen: set[frozenset[str]] = set()
    for index, raw in enumerate(_entries("between_pin_parasitics", values)):
        if not isinstance(raw, Mapping):
            raise ValueError(f"between_pin_parasitics[{index}] must be a mapping")
        unknown = set(raw) - _PAIR_KEYS
        if unknown:
            raise ValueError(
                f"between_pin_parasitics[{index}] has unknown fields: "
                f"{', '.join(sorted(map(str, unknown)))}"
            )
        if "pins" not in raw:
            raise ValueError(f"between_pin_parasitics[{index}].pins is required")
        pair = _pin_pair(f"between_pin_parasitics[{index}].pins", raw["pins"], pin_lookup)
        identity = frozenset(pin.casefold() for pin in pair)
        if identity in seen:
            raise ValueError("between_pin_parasitics contains a duplicate unordered pin pair")
        seen.add(identity)
        capacitance = _number(
            f"between_pin_parasitics[{index}].capacitance_f",
            raw.get("capacitance_f", 0.0), maximum=1.0,
        )
        leakage = _number(
            f"between_pin_parasitics[{index}].leakage_resistance_ohm",
            raw.get("leakage_resistance_ohm", 0.0), maximum=1.0e18,
        )
        if capacitance != 0.0 or leakage != 0.0:
            resolved.append({
                "pins": list(pair),
                "capacitance_f": capacitance,
                "leakage_resistance_ohm": leakage,
            })
    return resolved


def _normalise_couplings(
    values: Any,
    pin_lookup: Mapping[str, str],
    pin_parasitics: Mapping[str, Mapping[str, float]],
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    seen: set[frozenset[str]] = set()
    for index, raw in enumerate(_entries("mutual_couplings", values)):
        if not isinstance(raw, Mapping):
            raise ValueError(f"mutual_couplings[{index}] must be a mapping")
        unknown = set(raw) - _COUPLING_KEYS
        if unknown:
            raise ValueError(
                f"mutual_couplings[{index}] has unknown fields: {', '.join(sorted(map(str, unknown)))}"
            )
        if "pins" not in raw or "coupling_coefficient" not in raw:
            raise ValueError(f"mutual_couplings[{index}] requires pins and coupling_coefficient")
        pair = _pin_pair(f"mutual_couplings[{index}].pins", raw["pins"], pin_lookup)
        identity = frozenset(pin.casefold() for pin in pair)
        if identity in seen:
            raise ValueError("mutual_couplings contains a duplicate unordered pin pair")
        seen.add(identity)
        raw_coefficient = raw["coupling_coefficient"]
        if isinstance(raw_coefficient, (bool, str, bytes)):
            raise ValueError(
                f"mutual_couplings[{index}].coupling_coefficient must be a finite number with magnitude less than 1"
            )
        try:
            coefficient = float(raw_coefficient)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"mutual_couplings[{index}].coupling_coefficient must be a finite number with magnitude less than 1"
            ) from exc
        if not math.isfinite(coefficient) or abs(coefficient) >= 1.0:
            raise ValueError(
                f"mutual_couplings[{index}].coupling_coefficient must be a finite number with magnitude less than 1"
            )
        if coefficient == 0.0:
            continue
        if any(pin_parasitics[pin]["inductance_h"] <= 0.0 for pin in pair):
            raise ValueError("mutual_couplings requires positive inductance_h on both pins")
        resolved.append({"pins": list(pair), "coupling_coefficient": coefficient})
    return resolved


def _inductance_matrix(
    pins: tuple[str, ...],
    pin_parasitics: Mapping[str, Mapping[str, float]],
    couplings: Sequence[Mapping[str, Any]],
) -> tuple[list[list[float]], float]:
    indices = {pin: index for index, pin in enumerate(pins)}
    matrix = np.zeros((len(pins), len(pins)), dtype=float)
    for pin, index in indices.items():
        matrix[index, index] = pin_parasitics[pin]["inductance_h"]
    for coupling in couplings:
        first, second = coupling["pins"]
        first_index, second_index = indices[first], indices[second]
        mutual = coupling["coupling_coefficient"] * math.sqrt(
            matrix[first_index, first_index] * matrix[second_index, second_index]
        )
        matrix[first_index, second_index] = mutual
        matrix[second_index, first_index] = mutual
    try:
        eigenvalues = np.linalg.eigvalsh(matrix)
    except np.linalg.LinAlgError as exc:  # pragma: no cover - finite bounded matrix
        raise ValueError("inductance matrix passivity validation failed") from exc
    minimum = float(eigenvalues[0])
    scale = float(np.max(np.diag(matrix)))
    tolerance = 64.0 * np.finfo(float).eps * max(1, len(pins)) * scale
    if minimum < -tolerance:
        raise ValueError("mutual_couplings produce a non-positive-semidefinite inductance matrix")
    return matrix.tolist(), minimum


def _dependencies(value: Any) -> list[str]:
    if value is None:
        return []
    entries = _sequence("core_dependencies", value)
    if len(entries) > 256:
        raise ValueError("core_dependencies may contain at most 256 inert entries")
    result: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, str):
            raise ValueError(f"core_dependencies[{index}] must be text")
        if len(entry.encode("utf-8")) > 8 * 1024 * 1024:
            raise ValueError(f"core_dependencies[{index}] exceeds 8 MiB")
        result.append(entry)
    return result


def compose_device_parasitics(
    core_subckt: str,
    pins: Sequence[str],
    *,
    pin_parasitics: Mapping[str, Mapping[str, Any]] | None = None,
    between_pin_parasitics: Sequence[Mapping[str, Any]] | None = None,
    mutual_couplings: Sequence[Mapping[str, Any]] | None = None,
    core_dependencies: Sequence[str] | None = None,
    name: str = "SPK_DEVICE_PACKAGE",
) -> dict[str, Any]:
    """Compose an inert package wrapper around ``core_subckt``.

    ``pins`` is the exact ordered interface of both the wrapper and core.
    Per-pin R/L elements lie in series with a private core-side node.
    Constant C and leakage R elements join those core-side nodes.  Zero shunt
    values disappear; a pin with no series term receives one exact 0 V link.

    ``core_dependencies`` is copied into the result for provenance only.  It
    is deliberately never appended to ``source`` or otherwise interpreted.
    """
    wrapper_name = _identifier("name", name)
    core_name = _identifier("core_subckt", core_subckt)
    if wrapper_name.casefold() == core_name.casefold():
        raise ValueError("name and core_subckt must be different identifiers")
    pin_values = _sequence("pins", pins)
    if not 1 <= len(pin_values) <= 64:
        raise ValueError("pins must contain from 1 through 64 ordered pins")
    ordered_pins = tuple(_identifier(f"pins[{index}]", pin) for index, pin in enumerate(pin_values))
    if any(pin == "0" for pin in ordered_pins):
        raise ValueError("node 0 cannot be a subcircuit pin")
    if len({pin.casefold() for pin in ordered_pins}) != len(ordered_pins):
        raise ValueError("pins must be unique ignoring case")

    pin_lookup = {pin.casefold(): pin for pin in ordered_pins}
    resolved_pins = _normalise_pin_parasitics(ordered_pins, pin_parasitics)
    resolved_pairs = _normalise_between_pins(between_pin_parasitics, pin_lookup)
    resolved_couplings = _normalise_couplings(mutual_couplings, pin_lookup, resolved_pins)
    matrix, minimum_eigenvalue = _inductance_matrix(
        ordered_pins, resolved_pins, resolved_couplings
    )
    dependencies = _dependencies(core_dependencies)

    used_nodes = {pin.casefold() for pin in ordered_pins}

    def private_node(stem: str, index: int) -> str:
        candidate = f"__SPK_{stem}_{index}"
        suffix = 0
        while candidate.casefold() in used_nodes:
            suffix += 1
            candidate = f"__SPK_{stem}_{index}_{suffix}"
        used_nodes.add(candidate.casefold())
        return candidate

    core_nodes = [private_node("CORE", index) for index in range(1, len(ordered_pins) + 1)]
    lines = [
        "* Original SPIKE generic unqualified constant package-parasitic wrapper",
        f".subckt {wrapper_name} {' '.join(ordered_pins)}",
    ]
    inductor_labels: dict[str, str] = {}
    for index, (pin, core_node) in enumerate(zip(ordered_pins, core_nodes, strict=True), start=1):
        resistance = resolved_pins[pin]["resistance_ohm"]
        inductance = resolved_pins[pin]["inductance_h"]
        if resistance and inductance:
            series_node = private_node("SER", index)
            lines.append(f"RPKG{index} {pin} {series_node} {resistance:.17g}")
            lines.append(f"LPKG{index} {series_node} {core_node} {inductance:.17g}")
            inductor_labels[pin] = f"LPKG{index}"
        elif resistance:
            lines.append(f"RPKG{index} {pin} {core_node} {resistance:.17g}")
        elif inductance:
            lines.append(f"LPKG{index} {pin} {core_node} {inductance:.17g}")
            inductor_labels[pin] = f"LPKG{index}"
        else:
            lines.append(f"VPKG{index} {pin} {core_node} 0")

    core_nodes_by_pin = dict(zip(ordered_pins, core_nodes, strict=True))
    for index, pair in enumerate(resolved_pairs, start=1):
        first, second = pair["pins"]
        nodes = f"{core_nodes_by_pin[first]} {core_nodes_by_pin[second]}"
        if pair["capacitance_f"]:
            lines.append(f"CPKG{index} {nodes} {pair['capacitance_f']:.17g}")
        if pair["leakage_resistance_ohm"]:
            lines.append(f"RLEAK{index} {nodes} {pair['leakage_resistance_ohm']:.17g}")
    for index, coupling in enumerate(resolved_couplings, start=1):
        first, second = coupling["pins"]
        lines.append(
            f"KPKG{index} {inductor_labels[first]} {inductor_labels[second]} "
            f"{coupling['coupling_coefficient']:.17g}"
        )
    lines.append(f"XCORE {' '.join(core_nodes)} {core_name}")
    lines.append(f".ends {wrapper_name}")

    resolved = {
        "pins": deepcopy(resolved_pins),
        "between_pin_parasitics": deepcopy(resolved_pairs),
        "mutual_couplings": deepcopy(resolved_couplings),
        "inductance_matrix_h": matrix,
        "minimum_inductance_eigenvalue_h": minimum_eigenvalue,
    }
    return {
        "contract": CONTRACT,
        "name": wrapper_name,
        "core_subckt": core_name,
        "pins": list(ordered_pins),
        "source": "\n".join(lines) + "\n",
        "core_dependencies": deepcopy(dependencies),
        "resolved_config": resolved,
        "model_status": "generic_unqualified",
        "backend": "native_primitives",
        "limitations": list(_LIMITATIONS),
    }


# A short name is useful when the module is imported directly.  Keep one
# implementation so both entry points have identical validation semantics.
compose = compose_device_parasitics


__all__ = ["CONTRACT", "compose", "compose_device_parasitics"]
