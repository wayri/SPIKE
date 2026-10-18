# SPDX-License-Identifier: Apache-2.0
"""Explicit sampled two-port fixture removal at one common real reference.

Original derivation, b=S*a with S[receiver,source]: solving the second row
for a_left gives [a_left,b_left]=T*[b_right,a_right], with
T=[[1/S21,-S22/S21],[S11/S21,S12-S11*S22/S21]]. At each connected interface,
one network's incident wave is its neighbour's outgoing wave, so
T_measured=T_left*T_DUT*T_right. Two linear solves remove the fixtures;
neither an inverse nor a pseudoinverse is formed. Converting T_DUT back to S
and rebuilding its chain independently checks reconstruction of the measured
chain. This representation requires nonzero forward transmission and an
explicit orientation; no reversal, renormalization or interpolation is inferred.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

import numpy as np

REQUEST_CONTRACT = "spike/two-port-deembedding-request/v1"
RESULT_CONTRACT = "spike/two-port-deembedding-result/v1"
_MAX_FREQUENCIES = 4096
_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_TRANSMISSION_FLOOR = 1e-12
_CHAIN_PIVOT_FLOOR = 1e-12
_MAX_CONDITION = 1e8
_MAX_RESIDUAL = 1e-10


class SParameterDeembeddingError(ValueError):
    """Structured rejection without repaired data or partially returned sweep."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_DEEMBEDDING_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SParameterDeembeddingError(code, message)


def _record(value, fields, name):
    _require(isinstance(value, dict) and set(value) == set(fields), f"Invalid {name} fields")


def _number(value, name):
    _require(type(value) in (int, float), f"{name} must be a finite number")
    try:
        result = float(value)
    except OverflowError as error:
        raise SParameterDeembeddingError("invalid_request", f"Unrepresentable {name}") from error
    _require(math.isfinite(result), f"Nonfinite {name}")
    return result


def _name(value, name):
    _require(isinstance(value, str) and value.strip() and len(value) <= 80, f"Invalid bounded {name}")


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _digest(value):
    return sha256(_json(value)).hexdigest()


def _snapshot(request):
    chunks, size = [], 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).iterencode(request):
            size += len(chunk.encode("utf-8"))
            _require(size <= _MAX_REQUEST_BYTES, "Deembedding request exceeds 8 MiB", "resource_limit")
            chunks.append(chunk)
        return json.loads("".join(chunks)), size
    except SParameterDeembeddingError:
        raise
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        raise SParameterDeembeddingError("invalid_request", f"Invalid finite JSON: {error}") from error


def _network(raw, label, poll):
    _record(raw, {"id", "port_names", "reference_impedance_ohm", "frequencies_hz", "s_parameters"}, label)
    _name(raw["id"], f"{label} id")
    names = raw["port_names"]
    _require(isinstance(names, list) and len(names) == 2, "Exactly two ordered port names required")
    for name in names:
        _name(name, "port name")
    _require(names[0] != names[1], "Port names must be unique")
    _require(_number(raw["reference_impedance_ohm"], "reference impedance") > 0, "Positive real reference required")
    frequencies = raw["frequencies_hz"]
    _require(isinstance(frequencies, list) and 1 <= len(frequencies) <= _MAX_FREQUENCIES,
             "Provide 1..4096 supplied frequencies", "resource_limit")
    values = [_number(f, "frequency") for f in frequencies]
    _require(values[0] >= 0 and all(b > a for a, b in zip(values, values[1:])), "Frequencies must be nonnegative and strictly increasing")
    samples = raw["s_parameters"]
    _require(isinstance(samples, list) and len(samples) == len(values), "Frequency and sample counts must match")
    matrices = []
    for index, sample in enumerate(samples):
        if index % 64 == 0:
            poll()
        _require(isinstance(sample, list) and len(sample) == 2
                 and all(isinstance(row, list) and len(row) == 2 for row in sample), "S samples must be 2 by 2")
        matrix = np.empty((2, 2), dtype=complex)
        for i in range(2):
            for j in range(2):
                pair = sample[i][j]
                _record(pair, {"real", "imag"}, "complex scalar")
                matrix[i, j] = complex(_number(pair["real"], "S real"), _number(pair["imag"], "S imaginary"))
        _require(abs(matrix[1, 0]) >= _TRANSMISSION_FLOOR,
                 f"{label} S21 is below the explicit 1e-12 chain representation floor", "representation_limit")
        matrices.append(matrix)
    return matrices


def _chain(s):
    s11, s12, s21, s22 = s[0, 0], s[0, 1], s[1, 0], s[1, 1]
    result = np.array([[1 / s21, -s22 / s21], [s11 / s21, s12 - s11 * s22 / s21]])
    _require(np.isfinite(result).all(), "Nonfinite wave-chain coefficients", "numerical_failure")
    return result


def _scattering(chain):
    pivot = chain[0, 0]
    _require(np.isfinite(chain).all() and abs(pivot) >= _CHAIN_PIVOT_FLOOR,
             "Derived T00 is nonfinite or below the explicit 1e-12 conversion floor", "representation_limit")
    result = np.array([[chain[1, 0] / pivot, chain[1, 1] - chain[1, 0] * chain[0, 1] / pivot],
                       [1 / pivot, -chain[0, 1] / pivot]])
    _require(np.isfinite(result).all(), "Nonfinite derived scattering coefficients", "numerical_failure")
    return result


def _norm(matrix):
    value = float(np.linalg.norm(matrix))
    _require(math.isfinite(value), "Unrepresentable chain norm", "numerical_failure")
    return value


def _remove(measured, left, right):
    condition_left, condition_right = float(np.linalg.cond(left)), float(np.linalg.cond(right))
    _require(all(math.isfinite(c) and c <= _MAX_CONDITION for c in (condition_left, condition_right)),
             "Singular or ill-conditioned fixture chain", "ill_conditioned")
    amplification = condition_left * condition_right
    _require(math.isfinite(amplification) and amplification <= _MAX_CONDITION,
             "Fixture condition product exceeds 1e8", "ill_conditioned")
    intermediate = np.linalg.solve(left, measured)
    # X*right=intermediate is right.T*X.T=intermediate.T, not a conjugate
    # transpose. This distinction matters for complex nonreciprocal fixtures.
    derived = np.linalg.solve(right.T, intermediate.T).T
    scattering = _scattering(derived)
    reconstructed = left @ _chain(scattering) @ right
    residual = _norm(reconstructed - measured) / max(_norm(measured), np.finfo(float).tiny)
    _require(math.isfinite(residual) and residual <= _MAX_RESIDUAL,
             "Measured-chain reconstruction residual exceeds 1e-10", "numerical_failure")
    smax = float(np.linalg.svd(scattering, compute_uv=False)[0])
    _require(math.isfinite(smax), "Nonfinite derived singular value", "numerical_failure")
    diagnostics = {"condition_left": condition_left, "condition_right": condition_right,
                   "condition_product": amplification, "reconstruction_residual": residual, "smax": smax}
    return scattering, diagnostics


def deembed_two_port(request, *, cancel_check=None):
    """Remove explicitly oriented fixtures without changing the sampled grid."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise SParameterDeembeddingError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "Two-port deembedding cancelled", "cancelled")

    poll()
    frozen, size = _snapshot(request)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            _record(frozen, {"contract", "measured", "left_fixture", "right_fixture"}, "request")
            _require(frozen["contract"] == REQUEST_CONTRACT, "Unsupported two-port deembedding contract")
            labels = ("measured", "left_fixture", "right_fixture")
            matrices = [_network(frozen[key], key, poll) for key in labels]
            measured, left, right = [frozen[key] for key in labels]
            _require(len({network["id"] for network in (measured, left, right)}) == 3, "Source IDs must be distinct")
            _require(all(network["reference_impedance_ohm"] == measured["reference_impedance_ohm"]
                         and network["frequencies_hz"] == measured["frequencies_hz"] for network in (left, right)),
                     "Exact equal grids and a common scalar reference are required")
            names = [left["port_names"][1], right["port_names"][0]]
            _require(measured["port_names"][0] == left["port_names"][0]
                     and measured["port_names"][1] == right["port_names"][1] and names[0] != names[1],
                     "Fixture orientation and named interfaces must match explicitly")
            estimate = 3 * size + 1024 * len(measured["frequencies_hz"]) + 65536
            _require(estimate <= _MAX_RESULT_BYTES, "Estimated deembedding response exceeds 16 MiB", "resource_limit")
            responses, diagnostics = [], []
            for index, frequency in enumerate(measured["frequencies_hz"]):
                poll()
                s, evidence = _remove(*[_chain(array[index]) for array in matrices])
                responses.append([[{"real": float(v.real), "imag": float(v.imag)} for v in row] for row in s])
                diagnostics.append({"frequency_hz": frequency, **evidence})
            digest = _digest(frozen)
            result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                      "input_digest": digest,
                      "sources": {key: {"id": frozen[key]["id"], "input_digest": _digest(frozen[key]), "network": frozen[key]} for key in labels},
                      "derived_network": {"id": "deembedded-" + digest[:20], "port_names": names,
                                          "reference_impedance_ohm": measured["reference_impedance_ohm"],
                                          "frequencies_hz": measured["frequencies_hz"], "s_parameters": responses},
                      "diagnostics": diagnostics,
                      "limitations": ["Explicit receiver/source power-wave S convention at one common positive real reference",
                                      "Only the supplied orientation and equal sampled grids; no flipping, interpolation or renormalization",
                                      "Source |S21| and derived |T00| must be at least 1e-12; no clipping or pseudoinverse",
                                      "Individual dimensionless fixture 2-norm conditions and their product must not exceed 1e8",
                                      "Active and nonreciprocal DUTs are retained; smax is diagnostic, not a passivity repair or causality claim",
                                      "Synthetic numerical acceptance does not establish measurement calibration accuracy or production qualification"]}
            _require(len(_json(result)) <= _MAX_RESULT_BYTES, "Deembedding response exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except SParameterDeembeddingError:
        raise
    except (FloatingPointError, OverflowError, ValueError, TypeError, np.linalg.LinAlgError) as error:
        raise SParameterDeembeddingError("numerical_failure", f"Deembedding numerical failure: {error}") from error
