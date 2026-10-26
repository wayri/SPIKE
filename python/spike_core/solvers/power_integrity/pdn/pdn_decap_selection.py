# SPDX-License-Identifier: Apache-2.0
"""Exhaustive, bounded BOM-constrained choice among supplied decap options.

This orchestration adds no circuit model: each constraint-admissible nonempty
population is evaluated by the existing supplied-corner service. Exhaustive
enumeration proves the stated lexicographic choice only within the supplied
sites/options, operating corners and frequency samples. It cannot establish
an optimum over unlisted parts, placements or unsampled frequency peaks.
Money is integer minor units; no currency conversion or procurement inference.
"""
from __future__ import annotations

import itertools
import json
import math

from . import pdn_decap_corners as corner_service
from .pdn_network import PdnNetworkError, _array, _name, _record, validate_pdn_network

REQUEST_CONTRACT = "spike/pdn-decap-selection-request/v1"
RESULT_CONTRACT = "spike/pdn-decap-selection-result/v1"
_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_DENSE_WORK = 100_000_000
_MAX_CONFIGURATIONS = 256


class PdnDecapSelectionError(ValueError):
    """Invalid domains, exhausted resources or numerical failure yield no winner."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "PDN_DECAP_SELECTION_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise PdnDecapSelectionError(code, message)


def _integer(value, name):
    _require(type(value) is int and value >= 0, f"{name} must be a nonnegative integer")
    return value


def _snapshot(request):
    chunks, size = [], 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).iterencode(request):
            size += len(chunk.encode("utf-8"))
            _require(size <= _MAX_REQUEST_BYTES, "Selection request exceeds 8 MiB", "resource_limit")
            chunks.append(chunk)
        return json.loads("".join(chunks)), size
    except PdnDecapSelectionError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise PdnDecapSelectionError("invalid_request", f"Invalid finite JSON: {error}") from error


def _corner_request(request, capacitors):
    return {"contract": corner_service.REQUEST_CONTRACT, "base_request": request["base_request"],
            "corners": request["corners"], "target_impedance_ohm_by_port": request["target_impedance_ohm_by_port"],
            "capacitors": capacitors}


def _admit_corner(request, poll):
    # The corner owner admits physical records, topology, all supplied corner
    # mappings, expanded MNA size and its output envelope without solving.
    return corner_service._prepare(request, len(corner_service._json(request)), poll)


def _domain(request, poll):
    _record(request, {"contract", "base_request", "corners", "target_impedance_ohm_by_port", "sites",
                      "inventory", "budget_minor", "max_capacitors"}, "selection request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported decap selection contract")
    _integer(request["budget_minor"], "budget_minor")
    _require(1 <= _integer(request["max_capacitors"], "max_capacitors") <= 8, "max_capacitors must be 1..8")
    base = request["base_request"]
    validate_pdn_network(base)
    sites = _array(request["sites"], "sites", 1, 8)
    site_ids, option_sets, parts, count = set(), [], {}, 1
    for site in sites:
        _record(site, {"id", "positive", "negative", "options"}, "site")
        identity = _name(site["id"], "site.id")
        _require(identity not in site_ids, "Duplicate site ID")
        site_ids.add(identity)
        options = _array(site["options"], "site options", 1, 4)
        count *= len(options) + 1
        _require(count - 1 <= _MAX_CONFIGURATIONS, "More than 256 nonempty configurations", "resource_limit")
        option_ids = set()
        for option in options:
            _record(option, {"id", "part_id", "unit_cost_minor", "provenance", "corners"}, "option")
            option_id = _name(option["id"], "option.id")
            _require(option_id not in option_ids, "Duplicate option ID within site")
            option_ids.add(option_id)
            _name(option["part_id"], "part_id")
            _integer(option["unit_cost_minor"], "unit_cost_minor")
        option_sets.append(options)
    occupied = (set(base["nodes"]) | {base["reference"]} | {e["id"] for e in base["elements"]}
                | {p["id"] for p in base["ports"]} | site_ids
                | {o[key] for options in option_sets for o in options for key in ("id", "part_id")})
    cap_options = []
    for index, (site, options) in enumerate(zip(sites, option_sets)):
        prefix, suffix = f"selection-site-{index}", 0
        identity = prefix
        while identity in occupied:
            suffix += 1
            identity = f"{prefix}-{suffix}"
        occupied.add(identity)
        caps = []
        for option in options:
            poll()
            cap = {"id": identity, "positive": site["positive"], "negative": site["negative"],
                   "provenance": option["provenance"], "corners": option["corners"]}
            _admit_corner(_corner_request(request, [cap]), poll)
            # Corner table order and site/option names do not change a part's
            # physical identity. Numeric equality treats 1 and 1.0 alike.
            definition = {"unit_cost_minor": option["unit_cost_minor"], "provenance": option["provenance"],
                          "corners": {row["corner_id"]: row for row in option["corners"]}}
            part_id = option["part_id"]
            _require(part_id not in parts or parts[part_id] == definition, "Inconsistent definition for repeated part_id")
            parts[part_id] = definition
            caps.append(cap)
        cap_options.append(caps)
    inventory = {}
    for record in _array(request["inventory"], "inventory", 1, 32):
        _record(record, {"part_id", "max_quantity"}, "inventory record")
        part_id = _name(record["part_id"], "inventory part_id")
        _require(part_id not in inventory, "Duplicate inventory part_id")
        inventory[part_id] = _integer(record["max_quantity"], "max_quantity")
    _require(set(inventory) == set(parts), "Inventory must contain exactly all option part IDs")
    return sites, option_sets, cap_options, inventory


def _prepare(request, size, poll):
    sites, option_sets, cap_options, inventory = _domain(request, poll)
    summaries, jobs, work, maximum_corner_bytes = [], [], 0, 0
    for choice in itertools.product(*(range(-1, len(options)) for options in option_sets)):
        if all(index == -1 for index in choice):
            continue
        poll()
        selected, capacitors, quantities, cost = [], [], {}, 0
        for site, options, caps, index in zip(sites, option_sets, cap_options, choice):
            if index == -1:
                continue
            option = options[index]
            part = option["part_id"]
            selected.append({"site_id": site["id"], "option_id": option["id"], "part_id": part})
            capacitors.append(caps[index])
            quantities[part] = quantities.get(part, 0) + 1
            cost += option["unit_cost_minor"]
        violations = []
        if cost > request["budget_minor"]:
            violations.append("budget_exceeded")
        if len(capacitors) > request["max_capacitors"]:
            violations.append("capacitor_count_exceeded")
        violations.extend(f"inventory_exceeded:{part}" for part in inventory if quantities.get(part, 0) > inventory[part])
        summary = {"id": f"configuration-{len(summaries) + 1}", "selection": selected, "cost_minor": cost,
                   "capacitor_count": len(capacitors), "part_quantities": quantities,
                   "status": "constraint_rejected" if violations else "evaluated", "constraint_violations": violations,
                   "meets_target": None, "worst_case": None}
        summaries.append(summary)
        if not violations:
            generated = _corner_request(request, capacitors)
            admitted = _admit_corner(generated, poll)
            work += admitted[-2]
            _require(work <= _MAX_DENSE_WORK, "Aggregate selection dense work exceeds 100 million units", "resource_limit")
            maximum_corner_bytes = max(maximum_corner_bytes, admitted[-1])
            jobs.append((len(summaries) - 1, generated))
    _require(jobs, "No nonempty configuration satisfies inventory, budget and capacitor count", "no_feasible_configuration")
    # Keep compact summaries for every population and only one full winner.
    estimate = 4 * size + len(corner_service._json(summaries)) + 1024 * len(summaries) + maximum_corner_bytes + 65536
    _require(estimate <= _MAX_RESULT_BYTES, "Estimated selection response exceeds 16 MiB", "resource_limit")
    return summaries, jobs, work, estimate


def run_pdn_decap_selection(request, *, cancel_check=None):
    """Exhaust the admitted supplied domain before returning a selected result."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise PdnDecapSelectionError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "Decap selection cancelled", "cancelled")

    poll()
    frozen, size = _snapshot(request)
    try:
        summaries, jobs, work, estimate = _prepare(frozen, size, poll)
        best_key, selected_result, selected_id = None, None, None
        for index, generated in jobs:
            poll()
            actual = corner_service.run_pdn_decap_corners(generated, cancel_check=cancel_check)
            poll()
            _require(isinstance(actual, dict) and actual.get("contract") == corner_service.RESULT_CONTRACT
                     and actual.get("model_status") == "experimental" and actual.get("production_qualified") is False
                     and actual.get("input_digest") == corner_service._digest(generated),
                     "Unexpected corner result identity", "numerical_failure")
            worst = actual.get("worst_case")
            ratio = worst.get("target_ratio") if isinstance(worst, dict) else None
            _require(type(ratio) in (int, float) and math.isfinite(ratio) and ratio >= 0
                     and type(actual.get("meets_target")) is bool and actual["meets_target"] == (ratio <= 1),
                     "Invalid returned target assessment", "numerical_failure")
            summary = summaries[index]
            summary.update(meets_target=actual["meets_target"], worst_case=worst)
            cost, count = summary["cost_minor"], summary["capacitor_count"]
            key = ((0, cost, ratio, count, index) if actual["meets_target"] else (1, ratio, cost, count, index))
            if best_key is None or key < best_key:
                best_key, selected_result, selected_id = key, actual, summary["id"]
        result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                  "input_digest": corner_service._digest(frozen), "base_input_digest": corner_service._digest(frozen["base_request"]),
                  **{key: frozen[key] for key in ("base_request", "corners", "target_impedance_ohm_by_port", "sites",
                                                 "inventory", "budget_minor", "max_capacitors")},
                  "selected_id": selected_id, "selected_result": selected_result, "configurations": summaries,
                  "meets_target": selected_result["meets_target"],
                  "diagnostics": {"configuration_count": len(summaries), "evaluated_count": len(jobs),
                                  "constraint_rejected_count": len(summaries) - len(jobs),
                                  "estimated_dense_work": work, "estimated_result_bytes": estimate},
                  "limitations": ["Exhaustive choice only among the supplied nonempty site/option populations; not a global component or layout optimum",
                                  "Only supplied operating corners and sampled positive frequencies; unsampled impedance peaks are unbounded",
                                  "Integer minor-unit costs and quantities are supplied constraints, not verified inventory or procurement prices",
                                  "Each admissible configuration uses the existing fixed linear RLC corner model; no inferred bias or thermal laws",
                                  "No measured-board or production qualification; numerical failures and cancellation return no partial winner"]}
        _require(len(corner_service._json(result)) <= _MAX_RESULT_BYTES, "Selection response exceeds 16 MiB", "resource_limit")
        poll()
        return result
    except PdnDecapSelectionError:
        raise
    except corner_service.PdnDecapCornersError as error:
        raise PdnDecapSelectionError(error.code.removeprefix("PDN_DECAP_CORNERS_"), str(error)) from error
    except PdnNetworkError as error:
        raise PdnDecapSelectionError(error.code.removeprefix("PDN_"), str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError) as error:
        raise PdnDecapSelectionError("numerical_failure", f"Unrepresentable selection result: {error}") from error
