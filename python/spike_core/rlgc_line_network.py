# SPDX-License-Identifier: Apache-2.0
"""Experimental uniform, scalar, sampled RLGC line in real-reference power waves.

Independent formulation from the telegrapher equations with exp(+j*w*t):
z=R+j*w*L and y=G+j*w*C per metre. With current directed left-to-right,
[V_left, I_left] = exp([[0,z],[y,0]]*length) [V_right, I_right].
Normalize voltage/current by the common real port reference and define
a=z*length/Zref, b=y*length*Zref, u=sqrt(a)*sqrt(b). The normalized chain is
[[cosh(u), a*sinh(u)/u], [b*sinh(u)/u, cosh(u)]]. Its determinant is one.
Multiplying its scattering conversion by exp(-u) gives the bounded formula
used below. A zero a or b at DC is an exact series/shunt limit, not 0/0.

Foundation: Staelin, Electromagnetics and Applications (2011), MIT OCW,
chapter 8 section 8.3.1, equations 8.3.1--8.3.12. This is independently
authored code, with no external implementation used. Constant scalar L/C
and supplied nonnegative R/G samples describe an assumed uniform line;
there is no geometry extraction, frequency interpolation or causal fitting.
"""
from __future__ import annotations

import math

import numpy as np

from .sparameter_sampling import SParameterSamplingError, _digest, _json, _snapshot

REQUEST_CONTRACT = "spike/rlgc-line-network-request/v1"
RESULT_CONTRACT = "spike/rlgc-line-network-result/v1"
_MAX_SAMPLES = 1024
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_ATTENUATION = 350.0
_MAX_PHASE = 1e6
_PASSIVITY_TOLERANCE = 1e-9
_RECIPROCITY_TOLERANCE = 1e-10


class RLGCLineNetworkError(ValueError):
    """Structured admission/numerical failure; never returns a partial sweep."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "RLGC_LINE_NETWORK_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise RLGCLineNetworkError(code, message)


def _record(value, fields, name):
    _require(isinstance(value, dict) and set(value) == set(fields), f"Invalid {name} fields")


def _number(value, name, *, positive=False):
    _require(type(value) in (int, float), f"{name} must be a finite nonboolean scalar")
    try:
        number = float(value)
    except OverflowError as error:
        raise RLGCLineNetworkError("invalid_request", f"Unrepresentable {name}") from error
    _require(math.isfinite(number), f"Nonfinite {name}")
    _require(number > 0 if positive else number >= 0, f"Invalid sign or zero for {name}")
    return np.float64(number)


def _prepare(request, poll):
    _record(request, {"contract", "length_m", "reference_impedance_ohm", "inductance_h_per_m",
                      "capacitance_f_per_m", "samples"}, "RLGC line request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported RLGC line contract")
    length, reference, inductance, capacitance = (
        _number(request[name], name, positive=True)
        for name in ("length_m", "reference_impedance_ohm", "inductance_h_per_m", "capacitance_f_per_m"))
    samples = request["samples"]
    _require(isinstance(samples, list) and 1 <= len(samples) <= _MAX_SAMPLES,
             "Provide 1..1024 supplied RLGC samples", "resource_limit")
    previous = -1.
    for index, sample in enumerate(samples):
        if index % 64 == 0:
            poll()
        _record(sample, {"frequency_hz", "resistance_ohm_per_m", "conductance_s_per_m"}, "RLGC sample")
        frequency = _number(sample["frequency_hz"], "frequency_hz")
        _number(sample["resistance_ohm_per_m"], "resistance_ohm_per_m")
        _number(sample["conductance_s_per_m"], "conductance_s_per_m")
        _require(frequency > previous, "Frequencies must remain strictly increasing in floating-point arithmetic")
        previous = frequency
    return length, reference, inductance, capacitance


def _sample_matrix(sample, length, reference, inductance, capacitance):
    omega = np.float64(sample["frequency_hz"]) * (2 * np.pi)
    a = np.complex128(complex(sample["resistance_ohm_per_m"], omega * inductance)) * length / reference
    b = np.complex128(complex(sample["conductance_s_per_m"], omega * capacitance)) * length * reference
    _require(np.isfinite(a) and np.isfinite(b), "Nonfinite normalized line coefficients", "numerical_failure")
    if a == 0 or b == 0:
        _require(sample["frequency_hz"] == 0, "Positive-frequency line coefficient collapsed to zero", "numerical_failure")
        denominator = 2 + a + b
        reflection, transmission = (a - b) / denominator, 2 / denominator
    else:
        # For sqrt(a)=p+j*q and sqrt(b)=r+j*s, direct pr-qs loses
        # weak attenuation at large phase. Since p-q=Re(a)/(p+q) and
        # r-s=Re(b)/(r+s), pr-qs=(p-q)r+q(r-s) is a positive sum.
        # This also avoids forming a*b and keeps lossless attenuation zero.
        root_a, root_b = np.sqrt(a), np.sqrt(b)
        attenuation = (a.real * (root_b.real / (root_a.real + root_a.imag))
                       + b.real * (root_a.imag / (root_b.real + root_b.imag)))
        phase = root_a.real * root_b.imag + root_a.imag * root_b.real
        u = np.complex128(complex(attenuation, phase))
        _require(np.isfinite(u) and u != 0 and u.real >= 0 and u.imag >= 0,
                 "Unrepresentable passive propagation constant", "numerical_failure")
        _require(u.real <= _MAX_ATTENUATION and u.imag <= _MAX_PHASE,
                 "Propagation exceeds 350 nepers attenuation or 1e6 radians phase", "representation_limit")
        q = np.exp(-u)
        # expm1 retains short-line terms that 1-exp(-2*u) would cancel.
        h = -np.expm1(-2 * u) / (2 * u)
        diagonal = 1 + q * q
        offdiagonal = (a + b) * h
        denominator = diagonal + offdiagonal
        _require(abs(denominator) > 1e-12 * (abs(diagonal) + abs(offdiagonal)),
                 "Ill-conditioned scattering denominator", "numerical_failure")
        reflection = (a - b) * h / denominator
        transmission = 2 * q / denominator
    matrix = np.array([[reflection, transmission], [transmission, reflection]], dtype=complex)
    _require(np.isfinite(matrix).all() and transmission != 0,
             "Nonfinite or underflowed line scattering data", "numerical_failure")
    return matrix


def build_rlgc_line_network(request, *, cancel_check=None):
    """Build supplied RLGC samples as an equal-reference reciprocal two-port."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise RLGCLineNetworkError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "RLGC line calculation cancelled", "cancelled")

    poll()
    # Check original Python types before JSON can coerce a tuple into a list.
    _prepare(request, poll)
    try:
        frozen, _ = _snapshot(request)
    except SParameterSamplingError as error:
        code = error.code.removeprefix("SPARAMETER_SAMPLING_")
        raise RLGCLineNetworkError(code, str(error)) from error
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            length, reference, inductance, capacitance = _prepare(frozen, poll)
            records, max_excess, max_reciprocity = [], 0., 0.
            for sample in frozen["samples"]:
                poll()
                matrix = _sample_matrix(sample, length, reference, inductance, capacitance)
                singular_max = float(np.linalg.svd(matrix, compute_uv=False)[0])
                excess = max(0., singular_max - 1.)
                reciprocity = float(abs(matrix[0, 1] - matrix[1, 0]))
                _require(math.isfinite(singular_max) and excess <= _PASSIVITY_TOLERANCE,
                         "Sample fails the 1e-9 passivity tolerance", "numerical_failure")
                _require(reciprocity <= _RECIPROCITY_TOLERANCE,
                         "Sample fails the 1e-10 reciprocity tolerance", "numerical_failure")
                max_excess, max_reciprocity = max(max_excess, excess), max(max_reciprocity, reciprocity)
                records.append([[{"real": float(value.real), "imag": float(value.imag)} for value in row] for row in matrix])
            digest = _digest(frozen)
            result = {
                "contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                "input_digest": digest, "source_request": frozen,
                "network": {"id": "rlgc-line-" + digest[:20], "port_names": ["left", "right"],
                            "reference_impedance_ohm": frozen["reference_impedance_ohm"],
                            "frequencies_hz": [sample["frequency_hz"] for sample in frozen["samples"]],
                            "s_parameters": records},
                "diagnostics": {"sample_count": len(records), "maximum_passivity_excess": max_excess,
                                "maximum_reciprocity_error": max_reciprocity},
                "limitations": [
                    "Uniform uncoupled scalar line with supplied constant positive L/C and sampled nonnegative R/G per metre",
                    "Common positive real power-wave reference; S[receiver,source], ordered left/right terminals",
                    "No geometry extraction, skin/proximity inference, coupled conductors, radiation or arbitrary modal validity",
                    "No frequency interpolation, broadband causality certification, causal fitting or transient qualification",
                    "At most 1024 samples; propagation limited to 350 nepers attenuation and 1e6 radians phase",
                    "Floating-point underflow, overflow and ill-conditioned conversion fail closed; no clipping or regularization",
                    "Sampled passivity tolerance 1e-9 and reciprocity tolerance 1e-10 are numerical checks, not physical validation",
                    "Synthetic verification only; experimental and not production qualified",
                ],
            }
            _require(len(_json(result)) <= _MAX_RESULT_BYTES, "RLGC line response exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except RLGCLineNetworkError:
        raise
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise RLGCLineNetworkError("numerical_failure", f"RLGC line numerical failure: {error}") from error
