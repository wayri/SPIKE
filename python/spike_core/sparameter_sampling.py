# SPDX-License-Identifier: Apache-2.0
"""Explicit Cartesian-linear resampling of supplied real-reference S data.

For f in [f0,f1], w=(f-f0)/(f1-f0) and S(f)=(1-w)S0+w*S1 entrywise.
The receiver/source order and common real-reference power-wave convention
b=S*a are unchanged. These are convex weights, so exact passive endpoint
matrices remain contractions by the spectral-norm triangle inequality.
This interpolation does not certify a physical broadband or causal model.
A real DC matrix is either retained from the source or explicitly supplied;
no extrapolation, phase unwrapping, clipping or inferred DC is performed.
"""
from __future__ import annotations

from bisect import bisect_left
from copy import deepcopy
from hashlib import sha256
import json
import math

import numpy as np

REQUEST_CONTRACT = "spike/sparameter-resampling-request/v1"
RESULT_CONTRACT = "spike/sparameter-resampling-result/v1"
_MAX_FREQUENCIES = 4096
_MAX_MATRIX_ENTRIES = 262144
_MAX_SVD_WORK = 100_000_000
_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_MAX_RESULT_BYTES = 16 * 1024 * 1024


class SParameterSamplingError(ValueError):
    """Strict admission and numerical failures return no partial resampling."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_SAMPLING_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SParameterSamplingError(code, message)


def _record(value, fields, name):
    _require(isinstance(value, dict) and set(value) == set(fields), f"Invalid {name} fields")


def _number(value, name):
    _require(type(value) in (int, float), f"{name} must be a finite scalar")
    try:
        number = float(value)
    except OverflowError as error:
        raise SParameterSamplingError("invalid_request", f"Unrepresentable {name}") from error
    _require(math.isfinite(number), f"Nonfinite {name}")
    return number


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
            _require(size <= _MAX_REQUEST_BYTES, "Resampling request exceeds 8 MiB", "resource_limit")
            chunks.append(chunk)
        return json.loads("".join(chunks)), size
    except SParameterSamplingError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise SParameterSamplingError("invalid_request", f"Invalid finite JSON: {error}") from error


def _grid(value, name):
    _require(isinstance(value, list) and 1 <= len(value) <= _MAX_FREQUENCIES,
             f"{name} must contain 1..4096 supplied frequencies", "resource_limit")
    for frequency in value:
        _require(_number(frequency, name) >= 0, "Negative frequency is unsupported")
    # Preserve exact JSON numeric comparisons and copied frequency records;
    # converting integers to floats here could collapse distinct samples.
    _require(all(b > a for a, b in zip(value, value[1:])), "Frequencies must increase strictly")
    return value


def _matrix(value, n, *, dc=False):
    _require(isinstance(value, list) and len(value) == n
             and all(isinstance(row, list) and len(row) == n for row in value), "S matrix must cover every named port")
    result = np.empty((n, n), dtype=complex)
    for i, row in enumerate(value):
        for j, pair in enumerate(row):
            _record(pair, {"real", "imag"}, "complex scalar")
            real, imag = _number(pair["real"], "S real"), _number(pair["imag"], "S imaginary")
            _require(not dc or pair["imag"] == 0, "DC S matrix must be exactly real; no clipping")
            result[i, j] = complex(real, imag)
    return result


def _prepare(request, size, poll):
    _record(request, {"contract", "source", "target_frequencies_hz", "dc_policy"}, "resampling request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported resampling contract")
    source = request["source"]
    _record(source, {"id", "port_names", "reference_impedance_ohm", "frequencies_hz", "s_parameters"}, "source network")
    _name(source["id"], "network id")
    names = source["port_names"]
    _require(isinstance(names, list) and 1 <= len(names) <= 16, "Provide 1..16 named ports", "resource_limit")
    for name in names:
        _name(name, "port name")
    _require(len(set(names)) == len(names), "Duplicate port name")
    _require(_number(source["reference_impedance_ohm"], "reference impedance") > 0, "Positive common real reference required")
    frequencies = _grid(source["frequencies_hz"], "source frequencies")
    targets = _grid(request["target_frequencies_hz"], "target frequencies")
    n = len(names)
    _require((len(frequencies) + len(targets)) * n*n <= _MAX_MATRIX_ENTRIES,
             "Combined source and target matrix entries exceed 262144", "resource_limit")
    _require(len(targets) * n**3 <= _MAX_SVD_WORK, "Estimated target SVD work exceeds 100 million units", "resource_limit")
    estimate = 3 * size + len(targets) * (96 * n*n + 1024) + 65536
    _require(estimate <= _MAX_RESULT_BYTES, "Estimated resampling response exceeds 16 MiB", "resource_limit")
    records = source["s_parameters"]
    _require(isinstance(records, list) and len(records) == len(frequencies), "Source sample count differs from frequency grid")
    matrices = []
    for index, (frequency, record) in enumerate(zip(frequencies, records)):
        if index % 64 == 0:
            poll()
        matrices.append(_matrix(record, n, dc=frequency == 0))
    policy = request["dc_policy"]
    _require(isinstance(policy, dict) and policy.get("mode") in ("require_source", "supplied"), "Explicit supported DC policy required")
    supplied = policy["mode"] == "supplied"
    _record(policy, {"mode", "s_parameters"} if supplied else {"mode"}, "DC policy")
    if supplied:
        _require(frequencies[0] > 0, "Supplied DC cannot override an existing source DC sample")
        matrices = [_matrix(policy["s_parameters"], n, dc=True)] + matrices
        records = [policy["s_parameters"]] + records
        frequencies = [0.] + frequencies
    _require(targets[0] >= frequencies[0] and targets[-1] <= frequencies[-1],
             "All target frequencies must lie within explicit source/DC support; extrapolation is unsupported", "outside_support")
    return source, targets, frequencies, records, matrices, supplied


def resample_sparameter_network(request, *, cancel_check=None):
    """Return a separate sampled artifact and explicit per-target interpolation map."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise SParameterSamplingError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "S-parameter resampling cancelled", "cancelled")

    poll()
    frozen, size = _snapshot(request)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            source, targets, frequencies, records, matrices, supplied = _prepare(frozen, size, poll)
            samples, diagnostics = [], []
            for frequency in targets:
                poll()
                upper = bisect_left(frequencies, frequency)
                if frequencies[upper] == frequency:
                    lower_frequency = upper_frequency = frequencies[upper]
                    weight = 0.
                    matrix = matrices[upper]
                    record = deepcopy(records[upper])
                    kind = "supplied_dc" if supplied and upper == 0 else "source_sample"
                else:
                    lower_frequency, upper_frequency = frequencies[upper - 1], frequencies[upper]
                    distance, span = frequency - lower_frequency, upper_frequency - lower_frequency
                    _require(math.isfinite(distance) and math.isfinite(span) and 0 < distance < span,
                             "Interior frequency interval collapses at arithmetic precision", "numerical_failure")
                    weight = distance / span
                    _require(math.isfinite(weight) and 0 < weight < 1,
                             "Interior frequency fraction is not representable without endpoint collapse", "numerical_failure")
                    # Convex form avoids overflow from subtracting large
                    # opposite-sign complex endpoint values.
                    matrix = (1 - weight) * matrices[upper - 1] + weight * matrices[upper]
                    _require(np.isfinite(matrix).all(), "Nonfinite interpolated matrix", "numerical_failure")
                    record = [[{"real": float(v.real), "imag": float(v.imag)} for v in row] for row in matrix]
                    kind = "linear_interpolation"
                smax = float(np.linalg.svd(matrix, compute_uv=False)[0])
                _require(math.isfinite(smax), "Nonfinite resampled singular value", "numerical_failure")
                samples.append(record)
                diagnostics.append({"frequency_hz": frequency, "kind": kind, "lower_frequency_hz": lower_frequency,
                                    "upper_frequency_hz": upper_frequency, "weight_upper": weight, "smax": smax})
            digest = _digest(frozen)
            result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                      "input_digest": digest, "source": {"id": source["id"], "input_digest": _digest(source), "network": source},
                      "dc_policy": frozen["dc_policy"], "interpolation_method": "cartesian_linear",
                      "derived_network": {"id": "resampled-" + digest[:20], "port_names": list(source["port_names"]),
                                          "reference_impedance_ohm": source["reference_impedance_ohm"],
                                          "frequencies_hz": targets, "s_parameters": samples},
                      "diagnostics": diagnostics,
                      "limitations": ["Explicit Cartesian-linear interpolation of supplied receiver/source power-wave S matrices at a common real reference",
                                      "Exact source samples are copied; DC must be an exactly real source or explicitly supplied matrix",
                                      "No extrapolation, inferred DC, phase unwrapping, renormalization or passivity repair",
                                      "Active and nonreciprocal samples remain valid; smax is a sampled diagnostic, not broadband passivity or causality qualification",
                                      "Interpolation refinement checks do not qualify time-domain transforms, measurement accuracy or production use"]}
            _require(len(_json(result)) <= _MAX_RESULT_BYTES, "Resampling response exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except SParameterSamplingError:
        raise
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise SParameterSamplingError("numerical_failure", f"Resampling numerical failure: {error}") from error
