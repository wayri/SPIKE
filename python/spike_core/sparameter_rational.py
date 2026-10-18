# SPDX-License-Identifier: Apache-2.0
"""Real rational S fit at explicitly supplied stable real poles.

Original formulation: S(s)=D+sum_k R_k*p_k/(s+p_k), with real D,R_k.
At s=j*2*pi*f, stacking real and imaginary design rows gives one real
least-squares problem for all receiver/source entries. Unit column 2-norms
condition the coefficient solve without modifying its objective. Full rank,
bounded condition, normal-equation optimality and actual complex sample
errors are checked separately; rank truncation is never accepted as success.

The proper realization x_k'=-p_k*x_k+p_k*a, b=D*a+sum R_k*x_k is causal
and internally stable for supplied p_k>0. That construction does not prove
the source causal, passive, or accurately represented outside its fit grid.
For real omega, |p/(j*omega+p)|<=1, so ||D||F+sum||R_k||F bounds ||S||2
conservatively. A bound greater than one is inconclusive, not a rejection.
"""
from __future__ import annotations

import json
import math

import numpy as np

from . import sparameter_sampling as sampling

REQUEST_CONTRACT = "spike/sparameter-rational-fit-request/v1"
RESULT_CONTRACT = "spike/sparameter-rational-fit-result/v1"
_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_SOURCE_ENTRIES = 131072
_MAX_WORK = 100_000_000
_MAX_CONDITION = 1e10


class SParameterRationalError(ValueError):
    """Admission or numerical refusal without a partial or repaired model."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_RATIONAL_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SParameterRationalError(code, message)


def _snapshot(request):
    chunks, size = [], 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).iterencode(request):
            size += len(chunk.encode("utf-8"))
            _require(size <= _MAX_REQUEST_BYTES, "Rational fit request exceeds 8 MiB", "resource_limit")
            chunks.append(chunk)
        return json.loads("".join(chunks)), size
    except SParameterRationalError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise SParameterRationalError("invalid_request", f"Invalid finite JSON: {error}") from error


def _norm(array):
    """Scaled Frobenius/vector norm; reject unrepresentable final magnitude."""
    _require(np.isfinite(array).all(), "Nonfinite norm input", "numerical_failure")
    scale = float(np.max(np.abs(array), initial=0))
    value = 0. if scale == 0 else scale * float(np.linalg.norm(array / scale))
    _require(math.isfinite(value), "Unrepresentable numerical norm", "numerical_failure")
    return value


def _prepare(request, size, poll):
    sampling._record(request, {"contract", "source", "pole_rates_rad_s", "max_absolute_error"}, "rational fit request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported rational fit contract")
    tolerance = sampling._number(request["max_absolute_error"], "max_absolute_error")
    _require(tolerance > 0, "Positive absolute sample error limit required")
    raw_poles = request["pole_rates_rad_s"]
    _require(isinstance(raw_poles, list) and 1 <= len(raw_poles) <= 16, "Provide 1..16 explicit pole rates", "resource_limit")
    poles = [sampling._number(value, "pole rate") for value in raw_poles]
    _require(all(value > 0 for value in poles) and len(set(poles)) == len(poles), "Pole rates must be unique positive real values")
    source = request["source"]
    sampling._record(source, {"id", "port_names", "reference_impedance_ohm", "frequencies_hz", "s_parameters"}, "source network")
    sampling._name(source["id"], "source id")
    names = source["port_names"]
    _require(isinstance(names, list) and 1 <= len(names) <= 8, "Provide 1..8 named ports", "resource_limit")
    for name in names:
        sampling._name(name, "port name")
    _require(len(set(names)) == len(names), "Duplicate port name")
    _require(sampling._number(source["reference_impedance_ohm"], "reference impedance") > 0, "Positive common real reference required")
    raw_frequencies = source["frequencies_hz"]
    _require(isinstance(raw_frequencies, list) and 2 <= len(raw_frequencies) <= 2048, "Provide 2..2048 source frequencies", "resource_limit")
    frequencies = sampling._grid(raw_frequencies, "source frequencies")
    n, m, columns = len(names), 2 * len(frequencies), len(poles) + 1
    _require(len(frequencies) * n*n <= _MAX_SOURCE_ENTRIES, "Source exceeds 131072 matrix entries", "resource_limit")
    work = m * columns**2 + m * columns * n*n
    _require(work <= _MAX_WORK, "Estimated real least-squares work exceeds 100 million units", "resource_limit")
    _require(m >= columns, "Insufficient real observations for full column rank", "rank_deficient")
    estimate = 3 * size + 96 * len(frequencies) * n*n + 64 * columns * n*n + 65536
    _require(estimate <= _MAX_RESULT_BYTES, "Estimated rational response exceeds 16 MiB", "resource_limit")
    records = source["s_parameters"]
    _require(isinstance(records, list) and len(records) == len(frequencies), "Source sample count differs from frequency grid")
    matrices = []
    for index, (frequency, record) in enumerate(zip(frequencies, records)):
        if index % 64 == 0:
            poll()
        matrices.append(sampling._matrix(record, n, dc=frequency == 0))
    float_frequencies = np.asarray(frequencies, dtype=float)
    _require(np.all(np.diff(float_frequencies) > 0),
             "Frequency grid collapses under floating-point representation", "numerical_failure")
    return source, float_frequencies, np.asarray(poles), np.asarray(matrices), tolerance


def _fit(frequencies, poles, matrices, tolerance, poll):
    count, n, _ = matrices.shape
    omega = 2 * math.pi * frequencies
    _require(np.isfinite(omega).all(), "Nonfinite angular frequency", "numerical_failure")
    design = np.column_stack((np.ones(count), poles[None, :] / (poles[None, :] + 1j * omega[:, None])))
    observations = matrices.reshape(count, n*n)
    a, b = np.vstack((design.real, design.imag)), np.vstack((observations.real, observations.imag))
    scales = np.array([_norm(a[:, i]) for i in range(a.shape[1])])
    _require(np.all(scales > 0), "Zero design column norm", "rank_deficient")
    equilibrated = a / scales[None, :]
    poll()
    solution, _, rank, singular_values = np.linalg.lstsq(equilibrated, b, rcond=None)
    poll()
    _require(rank == a.shape[1] and len(singular_values) == a.shape[1],
             "Rational design lacks full rank; truncated solutions are not accepted", "rank_deficient")
    _require(np.isfinite(singular_values).all() and singular_values[-1] > 0,
             "Invalid least-squares singular values", "numerical_failure")
    condition = float(singular_values[0] / singular_values[-1])
    _require(math.isfinite(condition) and condition <= _MAX_CONDITION,
             "Equilibrated rational design condition exceeds 1e10", "ill_conditioned")
    coefficients = solution / scales[:, None]
    _require(np.isfinite(coefficients).all(), "Nonfinite fitted coefficients", "numerical_failure")
    real_residual = a @ coefficients - b
    numerator = _norm(a.T @ real_residual)
    norm_a = _norm(a)
    denominator = norm_a * (norm_a * _norm(coefficients) + _norm(b))
    _require(math.isfinite(denominator), "Unrepresentable optimality scale", "numerical_failure")
    optimality = numerator / denominator if denominator > 0 else (0. if numerator == 0 else math.inf)
    _require(math.isfinite(optimality) and optimality <= 1e-10,
             "Least-squares optimality residual exceeds 1e-10", "numerical_failure")
    reconstructed = (design @ coefficients).reshape(count, n, n)
    error = reconstructed - matrices
    maximum = float(np.max(np.abs(error)))
    rms = _norm(error) / math.sqrt(count * n*n)
    _require(math.isfinite(maximum) and maximum <= tolerance,
             "Actual complex sample error exceeds requested max_absolute_error", "error_limit")
    coefficients = coefficients.reshape(len(poles) + 1, n, n)
    bound = math.fsum(_norm(matrix) for matrix in coefficients)
    _require(math.isfinite(bound), "Nonfinite conservative passivity bound", "numerical_failure")
    smax = 0.
    for index, matrix in enumerate(reconstructed):
        if index % 64 == 0:
            poll()
        value = float(np.linalg.svd(matrix, compute_uv=False)[0])
        _require(math.isfinite(value), "Nonfinite sampled singular value", "numerical_failure")
        smax = max(smax, value)
    diagnostics = {"max_absolute_error": maximum, "rms_complex_error": rms, "equilibrated_condition": condition,
                   "least_squares_optimality_residual": optimality, "sampled_smax_max": smax,
                   "conservative_passivity_bound": bound}
    return coefficients, reconstructed, diagnostics


def fit_sparameter_rational(request, *, cancel_check=None):
    """Fit real residues/direct term at caller-supplied stable real poles."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise SParameterRationalError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "Rational fitting cancelled", "cancelled")

    poll()
    frozen, size = _snapshot(request)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            source, frequencies, poles, matrices, tolerance = _prepare(frozen, size, poll)
            coefficients, reconstructed, diagnostics = _fit(frequencies, poles, matrices, tolerance, poll)
            digest = sampling._digest(frozen)
            records = [[[ {"real": float(value.real), "imag": float(value.imag)} for value in row] for row in matrix] for matrix in reconstructed]
            result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                      "input_digest": digest, "source": {"id": source["id"], "input_digest": sampling._digest(source), "network": source},
                      "pole_rates_rad_s": frozen["pole_rates_rad_s"], "max_absolute_error": frozen["max_absolute_error"],
                      "model": {"direct": coefficients[0].tolist(), "residues": coefficients[1:].tolist(),
                                "realization": "x_k_prime=-p_k*x_k+p_k*a; b=D*a+sum(R_k*x_k)",
                                "stability": "strictly_stable_supplied_real_poles", "causality": "proper_real_rational_by_construction"},
                      "reconstructed_network": {"id": "rational-" + digest[:20], "port_names": list(source["port_names"]),
                                                "reference_impedance_ohm": source["reference_impedance_ohm"],
                                                "frequencies_hz": list(source["frequencies_hz"]), "s_parameters": records},
                      "diagnostics": diagnostics,
                      "limitations": ["Real direct term and residues at explicitly supplied stable real poles; no automatic pole relocation or general complex-pole fitting",
                                      "Sample reconstruction and least-squares acceptance do not establish source causality or out-of-grid accuracy",
                                      "Active and nonreciprocal models are retained without passivity repair; a conservative passivity bound above one is inconclusive",
                                      "Stable proper realization describes only the fitted model, not the measured source or an arbitrary external interconnection",
                                      "Distinct frequencies must remain distinct in floating-point arithmetic; collapsed grids are rejected",
                                      "Explicit common-real-reference receiver/source power-wave convention; no calibration, renormalization or production qualification",
                                      "Cancellation is checked around the bounded least-squares call; no partial model is published"]}
            _require(len(sampling._json(result)) <= _MAX_RESULT_BYTES, "Rational fit response exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except SParameterRationalError:
        raise
    except sampling.SParameterSamplingError as error:
        raise SParameterRationalError(error.code.removeprefix("SPARAMETER_SAMPLING_"), str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise SParameterRationalError("numerical_failure", f"Rational fitting numerical failure: {error}") from error
