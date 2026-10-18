# SPDX-License-Identifier: Apache-2.0
"""Evaluate explicitly supplied decap operating corners on a passive PDN.

Each supplied capacitor becomes the existing core's series R-L-C decap
element. Its impedance is R+j*w*L+1/(j*w*C); the core alone owns topology
expansion and multiport solution. All candidate capacitors coexist in each
corner. Bias and temperature label supplied values, never infer a component
law. Target comparison uses |Z_pp|/target_p at exactly the requested samples;
it does not bound unsampled resonances, optimize parts, or qualify a board.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math

from .pdn_network import (
    PdnNetworkError, RESULT_CONTRACT as NETWORK_RESULT, _array, _name,
    _number, _provenance, _record, evaluate_pdn_network, validate_pdn_network,
)

REQUEST_CONTRACT = "spike/pdn-decap-corners-request/v1"
RESULT_CONTRACT = "spike/pdn-decap-corners-result/v1"
_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_DENSE_WORK = 100_000_000


class PdnDecapCornersError(ValueError):
    """Structured refusal; failed corners never publish partial success."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "PDN_DECAP_CORNERS_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise PdnDecapCornersError(code, message)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _digest(value):
    return sha256(_json(value)).hexdigest()


def _snapshot(request):
    chunks, size = [], 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).iterencode(request):
            size += len(chunk.encode("utf-8"))
            _require(size <= _MAX_REQUEST_BYTES, "Corner request exceeds 8 MiB", "resource_limit")
            chunks.append(chunk)
        return json.loads("".join(chunks)), size
    except PdnDecapCornersError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise PdnDecapCornersError("invalid_request", f"Invalid finite JSON: {error}") from error


def _prepare(request, size, poll):
    _record(request, {"contract", "base_request", "capacitors", "corners", "target_impedance_ohm_by_port"}, "corner request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported decap corner contract")
    base = request["base_request"]
    _require(isinstance(base, dict) and "load_transient" in base and base["load_transient"] is None,
             "Base network must explicitly disable load_transient")
    validate_pdn_network(base)
    poll()
    corners = _array(request["corners"], "corners", 1, 16)
    corner_ids = []
    for corner in corners:
        _record(corner, {"id", "bias_voltage_v", "temperature_k"}, "corner")
        identity = _name(corner["id"], "corner.id")
        _require(identity not in corner_ids, "Duplicate corner ID")
        corner_ids.append(identity)
        _number(corner["bias_voltage_v"], "bias voltage")
        _number(corner["temperature_k"], "temperature", positive=True)
    ports = [port["id"] for port in base["ports"]]
    targets = _record(request["target_impedance_ohm_by_port"], set(ports), "targets")
    for target in targets.values():
        _number(target, "target impedance", positive=True)
    capacitors = _array(request["capacitors"], "capacitors", 1, 16)
    cap_ids, values = set(), []
    known_nodes = set(base["nodes"]) | {base["reference"]}
    for capacitor in capacitors:
        _record(capacitor, {"id", "positive", "negative", "provenance", "corners"}, "capacitor")
        identity = _name(capacitor["id"], "capacitor.id")
        _require(identity not in cap_ids, "Duplicate capacitor ID")
        cap_ids.add(identity)
        positive, negative = capacitor["positive"], capacitor["negative"]
        _require(isinstance(positive, str) and isinstance(negative, str)
                 and positive in known_nodes and negative in known_nodes and positive != negative,
                 "Capacitor endpoints must be distinct known base nodes")
        _provenance(capacitor["provenance"], "capacitor provenance")
        table = {}
        for value in _array(capacitor["corners"], "capacitor corners", len(corners), len(corners)):
            _record(value, {"corner_id", "capacitance_f", "esr_ohm", "esl_h"}, "capacitor corner")
            corner_id = _name(value["corner_id"], "capacitor corner ID")
            _require(corner_id in corner_ids and corner_id not in table, "Each capacitor must supply every corner exactly once")
            _number(value["capacitance_f"], "capacitance", positive=True)
            _number(value["esr_ohm"], "ESR")
            _number(value["esl_h"], "ESL")
            table[corner_id] = value
        values.append(table)
    # Reserve every caller-visible namespace, even though core element IDs and
    # nodes are separate. Generated IDs never alias a caller's identity.
    occupied = known_nodes | set(ports) | cap_ids | {e["id"] for e in base["elements"]}
    element_ids = []
    for index in range(len(capacitors)):
        prefix, suffix = f"decap-corner-{index}", 0
        identity = prefix
        while identity in occupied:
            suffix += 1
            identity = f"{prefix}-{suffix}"
        occupied.add(identity)
        element_ids.append(identity)
    prepared, work, estimate = [], 0, 4 * size + 65536
    for corner in corners:
        poll()
        generated, mapping = deepcopy(base), []
        for capacitor, table, element_id in zip(capacitors, values, element_ids):
            physical = {k: v for k, v in table[corner["id"]].items() if k != "corner_id"}
            generated["elements"].append({"id": element_id, "type": "decap", "positive": capacitor["positive"],
                "negative": capacitor["negative"], "provenance": capacitor["provenance"], **physical})
            mapping.append({"capacitor_id": capacitor["id"], "element_id": element_id,
                            "provenance": capacitor["provenance"], **physical})
        admitted = validate_pdn_network(generated)
        work += admitted["frequency_count"] * admitted["unknowns"]**3
        _require(work <= _MAX_DENSE_WORK, "Aggregate corner dense work exceeds 100 million units", "resource_limit")
        # Complex matrix/transfer entries plus per-port sample maps and caller
        # identifiers are reserved before any numerical corner is solved.
        p, n = len(ports), len(base["nodes"])
        names = sum(len(_json(v)) for v in base["nodes"] + ports)
        estimate += (2 * len(_json(generated)) + 2 * len(_json(mapping)) + 8192
                     + admitted["frequency_count"] * (96 * (p*p + n*p) + 512 * p + 4 * names + 1024))
        _require(estimate <= _MAX_RESULT_BYTES, "Estimated corner response exceeds 16 MiB", "resource_limit")
        prepared.append((corner, generated, mapping))
    return base, ports, targets, prepared, work, estimate


def _samples(result, base, ports, targets, corner_id):
    _require(isinstance(result, dict) and result.get("contract") == NETWORK_RESULT
             and result.get("model_status") == "approximate" and result.get("reference") == base["reference"]
             and result.get("port_ids") == ports and result.get("load_transient") is None,
             "Unexpected network result identity", "numerical_failure")
    rows = result.get("ac")
    _require(isinstance(rows, list) and len(rows) == len(base["frequencies_hz"]), "Invalid frequency response count", "numerical_failure")
    samples, worst = [], None
    for row, frequency in zip(rows, base["frequencies_hz"]):
        _require(isinstance(row, dict) and row.get("frequency_hz") == frequency, "Frequency response mismatch", "numerical_failure")
        matrix = row.get("impedance_ohm")
        _require(isinstance(matrix, list) and len(matrix) == len(ports)
                 and all(isinstance(r, list) and len(r) == len(ports) for r in matrix), "Invalid impedance dimensions", "numerical_failure")
        magnitudes, ratios = {}, {}
        for i, port in enumerate(ports):
            pair = matrix[i][i]
            _require(isinstance(pair, dict) and set(pair) == {"real", "imag"}
                     and all(type(v) in (int, float) for v in pair.values()), "Invalid impedance scalar", "numerical_failure")
            magnitude = abs(complex(pair["real"], pair["imag"]))
            ratio = magnitude / targets[port]
            _require(math.isfinite(magnitude) and math.isfinite(ratio), "Nonfinite impedance magnitude or target ratio", "numerical_failure")
            magnitudes[port], ratios[port] = magnitude, ratio
            candidate = {"corner_id": corner_id, "port_id": port, "frequency_hz": frequency,
                         "impedance_magnitude_ohm": magnitude, "target_impedance_ohm": targets[port], "target_ratio": ratio}
            if worst is None or ratio > worst["target_ratio"]:
                worst = candidate
        samples.append({"frequency_hz": frequency, "impedance_magnitude_ohm_by_port": magnitudes,
                        "target_ratio_by_port": ratios, "meets_target": all(v <= 1 for v in ratios.values())})
    return samples, worst


def run_pdn_decap_corners(request, *, cancel_check=None):
    """Solve every supplied corner atomically; target failure remains valid data."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise PdnDecapCornersError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "Decap corner evaluation cancelled", "cancelled")

    poll()
    frozen, size = _snapshot(request)
    try:
        base, ports, targets, prepared, work, estimate = _prepare(frozen, size, poll)
        outputs, worst = [], None
        for corner, generated, mapping in prepared:
            poll()
            numerical = evaluate_pdn_network(generated, cancel_check=cancel_check)
            poll()
            samples, local_worst = _samples(numerical, base, ports, targets, corner["id"])
            outputs.append({"corner": corner, "generated_request": generated, "generated_input_digest": _digest(generated),
                            "element_mapping": mapping, "network_result": numerical, "samples": samples,
                            "meets_target": local_worst["target_ratio"] <= 1, "worst_case": local_worst})
            if worst is None or local_worst["target_ratio"] > worst["target_ratio"]:
                worst = local_worst
        result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                  "input_digest": _digest(frozen), "base_input_digest": _digest(base), "base_request": base,
                  "corner_ids": [c["id"] for c in frozen["corners"]], "port_ids": ports,
                  "frequencies_hz": base["frequencies_hz"], "target_impedance_ohm_by_port": targets,
                  "corners": outputs, "meets_target": worst["target_ratio"] <= 1, "worst_case": worst,
                  "diagnostics": {"estimated_dense_work": work, "estimated_result_bytes": estimate},
                  "limitations": ["Only supplied corner values; bias and temperature are labels, with no interpolation or inferred derating",
                                  "All decaps coexist as frequency-invariant series RLC elements in each explicit passive network",
                                  "Targets apply to diagonal driving-point impedance at supplied positive frequencies only; unsampled peaks are unbounded",
                                  "Worst case is greatest target ratio; exact ties use declared corner, frequency and port order",
                                  "No optimization, transient execution or measured-board/production qualification"]}
        _require(len(_json(result)) <= _MAX_RESULT_BYTES, "Corner response exceeds 16 MiB", "resource_limit")
        poll()
        return result
    except PdnDecapCornersError:
        raise
    except PdnNetworkError as error:
        raise PdnDecapCornersError(error.code.removeprefix("PDN_"), str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError) as error:
        raise PdnDecapCornersError("numerical_failure", f"Unrepresentable corner result: {error}") from error
