# SPDX-License-Identifier: Apache-2.0
"""Experimental three-known-standard reflection calibration and first-order UQ.

Original derivation and reviewed primary sources: docs/ONE_PORT_CALIBRATION.md.
Offline reference only; no worker registration or instrument qualification.
"""
from __future__ import annotations

import json
import math
from hashlib import sha256

import numpy as np

REQUEST = "spike/one-port-calibration-request/v1"
RESULT = "spike/one-port-calibration-result/v1"
MAX_FREQUENCIES = 16
MAX_BYTES = 8 * 1024 * 1024
MAX_CONDITION = 1e8
MAX_RESIDUAL = 1e-10
MIN_TRACKING = 1e-12
MIN_POLE_MARGIN = 1e-10
INPUTS = ("standard0.reflection", "standard1.reflection", "standard2.reflection",
          "standard0.measured", "standard1.measured", "standard2.measured", "dut.measured")


class OnePortCalibrationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = "ONE_PORT_CALIBRATION_" + code.upper()


def require(value, message, code="invalid_request"):
    if not value:
        raise OnePortCalibrationError(code, message)


def fields(value, names, label):
    require(isinstance(value, dict) and set(value) == set(names), "Invalid " + label + " fields")


def number(value):
    require(type(value) in (int, float), "Finite real scalar required")
    try:
        value = float(value)
    except OverflowError as error:
        raise OnePortCalibrationError("invalid_request", "Unrepresentable scalar") from error
    require(math.isfinite(value), "Nonfinite scalar")
    return value


def name(value, limit=512):
    require(isinstance(value, str) and value.strip() and len(value) <= limit,
            "Nonempty bounded identity/provenance required")


def input_basis(count):
    """Frequency-major interleaved real/imag ordering, dimension 14*count."""
    require(type(count) is int and 1 <= count <= MAX_FREQUENCIES, "Invalid frequency count")
    return [f"f{k}.{item}.{part}" for k in range(count) for item in INPUTS for part in ("real", "imag")]


def pairs(raw, count):
    require(isinstance(raw, list) and len(raw) == count, "Complex sample count differs")
    result = []
    for value in raw:
        fields(value, ("real", "imag"), "complex value")
        result.append(complex(number(value["real"]), number(value["imag"])))
    return np.asarray(result, dtype=complex)


def pair(value):
    return {"real": float(value.real), "imag": float(value.imag)}


def covariance(raw, size):
    """Admit explicit symmetric PSD matrices; no correlation/PSD repair."""
    require(isinstance(raw, list) and len(raw) == size and all(
        isinstance(row, list) and len(row) == size for row in raw), "Covariance dimension differs")
    matrix = np.asarray([[number(v) for v in row] for row in raw])
    require(np.array_equal(matrix, matrix.T), "Covariance must be exactly symmetric")
    diagonal = np.diag(matrix)
    require(np.all(diagonal >= 0), "Negative covariance diagonal", "invalid_covariance")
    active = diagonal > 0
    require(not np.any(matrix[~active, :] != 0), "Zero variance requires zero covariance row", "invalid_covariance")
    # Test a correlation-scaled matrix so a small invalid sub-block cannot
    # hide behind unrelated large variances. Never change the supplied matrix.
    if active.any():
        scale = np.sqrt(diagonal[active])
        correlation = matrix[np.ix_(active, active)] / scale[:, None] / scale[None, :]
        require(np.isfinite(correlation).all(), "Unrepresentable covariance scaling", "invalid_covariance")
        spectrum = np.linalg.eigvalsh(correlation)
        tolerance = 64 * np.finfo(float).eps * len(scale) * max(1., float(np.max(abs(spectrum))))
        require(float(spectrum[0]) >= -tolerance, "Covariance is not positive semidefinite", "invalid_covariance")
    return matrix


def solve(matrix, rhs):
    answer = np.linalg.solve(matrix, rhs)
    residual = float(np.linalg.norm(matrix @ answer - rhs) / max(
        np.linalg.norm(matrix) * np.linalg.norm(answer) + np.linalg.norm(rhs), np.finfo(float).tiny))
    require(np.isfinite(answer).all() and residual <= MAX_RESIDUAL,
            "Calibration solve backward residual exceeds 1e-10", "numerical_failure")
    return answer, residual


def sample(g, m, md):
    matrix = np.column_stack((np.ones(3), g, m*g))
    cond = float(np.linalg.cond(matrix))
    require(math.isfinite(cond) and cond <= MAX_CONDITION,
            "Calibration standards singular or condition exceeds 1e8", "ill_conditioned")
    q, residual = solve(matrix, m)
    d, b, s = q
    t = b + d*s
    require(abs(t) >= MIN_TRACKING, "Reflection tracking below 1e-12", "representation_limit")
    den = b + s*md
    pole_margin = float(abs(den) / max(abs(b) + abs(s*md), abs(t), np.finfo(float).tiny))
    require(pole_margin >= MIN_POLE_MARGIN, "DUT inverse calibration near a pole", "representation_limit")
    corrected = (md-d) / den
    denominators = 1-s*np.r_[g, corrected]
    forward_margin = float(np.min(abs(denominators) / np.maximum(1., abs(s*np.r_[g, corrected]))))
    require(forward_margin >= MIN_POLE_MARGIN, "Forward calibration near a pole", "representation_limit")
    reconstructed = d + t*np.r_[g, corrected]/denominators
    reconstruction = float(np.linalg.norm(reconstructed-np.r_[m, md]) / max(1., float(np.linalg.norm(np.r_[m, md]))))
    require(reconstruction <= MAX_RESIDUAL, "Calibration reconstruction exceeds 1e-10", "numerical_failure")
    # Differentiate A*q=m, including uncertainty in BOTH A and m.
    rhs = np.zeros((3, 7), dtype=complex)
    for i in range(3):
        rhs[i, i] = -(b+s*m[i])
        rhs[i, 3+i] = 1-s*g[i]
    dq, sensitivity_residual = solve(matrix, rhs)
    derivative = -np.array([1, corrected, md*corrected]) @ dq
    derivative[6] += 1-s*corrected
    derivative /= den
    require(np.isfinite(derivative).all(), "Nonfinite sensitivity", "numerical_failure")
    return corrected, (d, t, s), derivative, {
        "calibration_condition": cond, "solve_backward_residual": residual,
        "sensitivity_backward_residual": sensitivity_residual,
        "reconstruction_residual": reconstruction, "inverse_pole_margin": pole_margin,
        "forward_pole_margin": forward_margin}


def calibrate_one_port(request, *, cancel_check=None):
    """Derive a separate calibrated one-port and explicitly first-order covariance."""
    require(cancel_check is None or callable(cancel_check), "Cancellation hook must be callable")

    def poll():
        if cancel_check is not None:
            try:
                stopped = cancel_check()
            except Exception as error:
                raise OnePortCalibrationError("cancel_check_failed", "Cancellation hook failed") from error
            require(not stopped, "Calibration cancelled", "cancelled")

    poll()
    try:
        # Bounded streaming snapshot, rather than allocating unbounded JSON.
        chunks, size = [], 0
        for chunk in json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False,
                                      separators=(",", ":")).iterencode(request):
            size += len(chunk.encode("utf-8"))
            require(size <= MAX_BYTES, "Request exceeds 8 MiB", "resource_limit")
            chunks.append(chunk)
        encoded = "".join(chunks).encode("utf-8")
        frozen = json.loads(encoded)
        fields(frozen, ("contract", "id", "port_name", "reference_impedance_ohm", "frequencies_hz",
                        "standards", "dut", "covariance"), "request")
        require(frozen["contract"] == REQUEST, "Unsupported calibration contract")
        name(frozen["id"]); name(frozen["port_name"], 80)
        require(number(frozen["reference_impedance_ohm"]) > 0, "Positive real reference required")
        grid = frozen["frequencies_hz"]
        require(isinstance(grid, list) and 1 <= len(grid) <= MAX_FREQUENCIES,
                "Supply 1..16 positive frequencies", "resource_limit")
        frequencies = [number(v) for v in grid]
        require(frequencies[0] > 0 and all(b > a for a, b in zip(frequencies, frequencies[1:])),
                "Positive strictly increasing resolvable frequencies required")
        count = len(grid)
        standards = frozen["standards"]
        require(isinstance(standards, list) and len(standards) == 3, "Exactly three known standards required")
        gs, ms, ids = [], [], []
        for standard in standards:
            fields(standard, ("id", "provenance", "reflection", "measured"), "standard")
            name(standard["id"]); name(standard["provenance"])
            ids.append(standard["id"])
            gs.append(pairs(standard["reflection"], count))
            ms.append(pairs(standard["measured"], count))
        dut = frozen["dut"]
        fields(dut, ("id", "provenance", "measured"), "DUT")
        name(dut["id"]); name(dut["provenance"])
        require(len(set(ids+[dut["id"]])) == 4, "Standard and DUT identities must be distinct")
        measured = pairs(dut["measured"], count)
        uncertainty = frozen["covariance"]
        fields(uncertainty, ("basis", "matrix", "provenance"), "covariance")
        name(uncertainty["provenance"])
        require(uncertainty["basis"] == input_basis(count), "Explicit covariance basis differs")
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            poll()
            cov = covariance(uncertainty["matrix"], 14*count)
            jacobian = np.zeros((2*count, 14*count))
            corrected, coefficients, diagnostics = [], [], []
            for k in range(count):
                poll()
                value, terms, derivative, diagnostic = sample(np.array(gs)[:, k], np.array(ms)[:, k], measured[k])
                corrected.append([[pair(value)]])
                coefficients.append(dict(zip(("directivity", "reflection_tracking", "source_match"), map(pair, terms))))
                diagnostics.append({"frequency_hz": grid[k], **diagnostic})
                for j, h in enumerate(derivative):
                    jacobian[2*k:2*k+2, 14*k+2*j:14*k+2*j+2] = [[h.real, -h.imag], [h.imag, h.real]]
            propagated = jacobian @ cov @ jacobian.T
            # Only remove multiplication roundoff asymmetry, never eigenvalue
            # clipping, covariance inflation, diagonalization or regularization.
            propagated = (propagated+propagated.T)/2
            covariance(propagated.tolist(), 2*count)
        digest = sha256(encoded).hexdigest()
        result = {"contract": RESULT, "model_status": "experimental", "production_qualified": False,
                  "measurement_qualified": False, "linearization_qualified": False,
                  "input_digest": digest, "source_request": frozen,
                  "derived_network": {"id": "calibrated-"+digest[:20], "port_names": [frozen["port_name"]],
                                      "reference_impedance_ohm": frozen["reference_impedance_ohm"],
                                      "frequencies_hz": list(grid), "s_parameters": corrected},
                  "coefficients": coefficients, "diagnostics": diagnostics,
                  "output_basis": [f"f{k}.dut.reflection.{part}" for k in range(count) for part in ("real", "imag")],
                  "covariance": propagated.tolist(), "sensitivity": jacobian.tolist(),
                  "uncertainty_method": "first_order_joint_real_covariance",
                  "limitations": ["Exactly three supplied known reflection standards; no fitted standard model or residual-based noise estimate",
                                  "Full supplied input covariance only; provenance text does not establish traceability or completeness",
                                  "First-order local propagation; nonlinear adequacy and distribution/coverage unqualified for this input",
                                  "Fixed known positive real impedance and frequencies; their uncertainty is not included",
                                  "Offline one-port reference only; no multiport calibration, fixture covariance coupling, worker/UI or measured qualification"]}
        require(len(json.dumps(result, allow_nan=False).encode("utf-8")) <= 16*1024*1024,
                "Result exceeds 16 MiB", "resource_limit")
        poll()
        return result
    except OnePortCalibrationError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, ArithmeticError, np.linalg.LinAlgError) as error:
        raise OnePortCalibrationError("numerical_failure", str(error)) from error
