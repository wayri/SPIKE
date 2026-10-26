# SPDX-License-Identifier: Apache-2.0
"""Original sampled passive terminal reduction with explicit load admittance.

For retained p and eliminated q, auxiliary KCL is
    (Yqq + YL) Vq = -Yqp Vp.
Hence U=-(Yqq+YL)^-1 Yqp, Yred=Ypp+Ypq U. No transpose replaces Yqp:
nonreciprocal passive sources are admitted. With T restoring original node
order, T^H Y T + U^H YL U = Yred verifies the admittance power form V^H I.
Conventional RMS complex power is its conjugate; real dissipation is equal.
Hermitian dissipative PSD is checked without clipping or symmetry repair.

These independently authored equations are applied only at supplied samples.
Sampled passivity is neither broadband causality nor a transient macromodel.
No external implementation, fixture or source code was consulted.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Callable

import numpy as np

from .pdn_network import PdnNetworkError, _solve_linear

REQUEST_CONTRACT = "spike/pdn-admittance-reduction-request/v1"
RESULT_CONTRACT = "spike/pdn-admittance-reduction-result/v1"
_MAX_NODES = 32
_MAX_FREQUENCIES = 512
_MAX_MATRIX_ENTRIES = 262144
_MAX_DENSE_WORK = 100_000_000
_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_PASSIVITY_RELATIVE_TOLERANCE = 1e-10


class PdnAdmittanceReductionError(ValueError):
    """Malformed, active, singular or bounded-resource sampled reduction."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "PDN_ADMITTANCE_REDUCTION_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise PdnAdmittanceReductionError(code, message)


def _keys(value, fields, name):
    _require(isinstance(value, dict) and set(value) == set(fields), f"Unknown or missing {name} fields")


def _name(value, name, limit=80):
    _require(isinstance(value, str) and 0 < len(value) <= limit and value.strip()
             and not any(ord(c) < 32 or ord(c) == 127 for c in value), f"Invalid {name}")
    return value


def _number(value, name, positive=False):
    _require(type(value) in (int, float), f"{name} must be a finite scalar")
    try:
        result = float(value)
    except OverflowError as error:
        raise PdnAdmittanceReductionError("invalid_request", f"Unrepresentable {name}") from error
    _require(math.isfinite(result) and (not positive or result > 0), f"Invalid finite {name}")
    return result


def _digest_value(value, name):
    _require(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value),
             f"{name} must be a lowercase SHA-256")
    return value


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _snapshot(request):
    chunks, size = [], 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False).iterencode(request):
            size += len(chunk.encode())
            _require(size <= _MAX_REQUEST_BYTES, "Reduction request exceeds 8 MiB", "resource_limit")
            chunks.append(chunk)
        return json.loads("".join(chunks))
    except PdnAdmittanceReductionError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise PdnAdmittanceReductionError("invalid_request", f"Invalid finite JSON: {error}") from error


def _matrices(raw, count, size, name):
    _require(isinstance(raw, list) and len(raw) == count, f"{name} must match the frequency count")
    result = np.empty((count, size, size), dtype=complex)
    for f, matrix in enumerate(raw):
        _require(isinstance(matrix, list) and len(matrix) == size, f"Invalid {name} row count")
        for i, row in enumerate(matrix):
            _require(isinstance(row, list) and len(row) == size, f"Invalid {name} column count")
            for j, value in enumerate(row):
                _keys(value, {"real", "imag"}, f"{name} complex value")
                result[f, i, j] = complex(_number(value["real"], "real admittance"),
                                           _number(value["imag"], "imaginary admittance"))
    return result


def _source(source):
    _keys(source, {"nodes", "reference_node", "frequencies_hz", "admittance_s", "model_status",
                   "source_id", "context_digest"}, "source")
    nodes = source["nodes"]
    _require(isinstance(nodes, list) and 2 <= len(nodes) <= _MAX_NODES,
             "Source requires 2..32 non-reference nodes", "resource_limit")
    for node in nodes:
        _name(node, "source node")
    _require(len(set(nodes)) == len(nodes), "Duplicate source node")
    reference = _name(source["reference_node"], "reference node")
    _require(reference not in nodes, "Reference must be distinct from source nodes")
    _name(source["source_id"], "source ID", 256)
    _digest_value(source["context_digest"], "context_digest")
    _require(source["model_status"] in ("approximate", "experimental"), "Unsupported source model status")
    raw_frequencies = source["frequencies_hz"]
    _require(isinstance(raw_frequencies, list) and 1 <= len(raw_frequencies) <= _MAX_FREQUENCIES,
             "Provide 1..512 supplied frequencies", "resource_limit")
    frequencies = [_number(f, "frequency_hz", positive=True) for f in raw_frequencies]
    _require(all(b > a for a, b in zip(frequencies, frequencies[1:])), "Frequencies must increase strictly")
    _require(len(frequencies) * len(nodes)**2 <= _MAX_MATRIX_ENTRIES,
             "Source exceeds bounded matrix entries", "resource_limit")
    return nodes, frequencies, _matrices(source["admittance_s"], len(frequencies), len(nodes), "source admittance")


def _norm(array):
    maximum = float(np.max(np.abs(array), initial=0.))
    _require(math.isfinite(maximum), "Nonfinite matrix magnitude", "numerical_failure")
    result = maximum * float(np.linalg.norm(array / maximum)) if maximum else 0.
    _require(math.isfinite(result), "Unrepresentable matrix norm", "numerical_failure")
    return result


def _passivity(matrix, name):
    scale = _norm(matrix)
    normalized = matrix / scale if scale else matrix
    dissipative = (normalized + normalized.conj().T) * .5
    eigenvalue = float(np.linalg.eigvalsh(dissipative)[0])
    _require(math.isfinite(eigenvalue) and eigenvalue >= -_PASSIVITY_RELATIVE_TOLERANCE,
             f"{name} is not passive at a supplied frequency", "nonpassive_response")
    return {"minimum_dissipative_eigenvalue_s": eigenvalue * scale,
            "passivity_tolerance_s": _PASSIVITY_RELATIVE_TOLERANCE * scale,
            "matrix_norm_s": scale}


def _pairs(matrix):
    return [[{"real": float(value.real), "imag": float(value.imag)} for value in row] for row in matrix]


def reduce_pdn_admittance(request, *, cancel_check: Callable[[], bool] | None = None):
    """Reduce explicitly ordered auxiliary ports at exact supplied frequencies.

    Termination admittance uses the eliminated-node order and source reference.
    Zero termination means a floating auxiliary port. Its voltage is solved,
    never clamped or discarded. Failure/cancellation publishes no partial sweep.
    """
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise PdnAdmittanceReductionError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "Admittance reduction cancelled", "cancelled")

    poll()
    frozen = _snapshot(request)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _reduce(frozen, poll)
    except PdnAdmittanceReductionError:
        raise
    except PdnNetworkError as error:
        code = "conditioning_failure" if error.code == "PDN_SINGULAR_NETWORK" else "numerical_failure"
        raise PdnAdmittanceReductionError(code, str(error)) from error
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError) as error:
        raise PdnAdmittanceReductionError("numerical_failure", f"Admittance reduction failed: {error}") from error


def _reduce(request, poll):
    _keys(request, {"contract", "source", "retained_nodes", "eliminated_nodes", "termination_admittance_s"}, "request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported admittance reduction contract")
    source = request["source"]
    nodes, frequencies, matrices = _source(source)
    retained, eliminated = request["retained_nodes"], request["eliminated_nodes"]
    for partition in (retained, eliminated):
        _require(isinstance(partition, list) and 1 <= len(partition) < len(nodes), "Both ordered partitions must be nonempty")
        for name in partition:
            _name(name, "partition node")
    _require(len(retained) + len(eliminated) == len(nodes)
             and len(set(retained + eliminated)) == len(nodes) and set(retained + eliminated) == set(nodes),
             "Retained and eliminated nodes must exactly partition the source")
    n, p, q, count = len(nodes), len(retained), len(eliminated), len(frequencies)
    entries = count * (n*n + q*q)
    work = count * (2*n**3 + 2*q**3 + 2*p**3)
    _require(entries <= _MAX_MATRIX_ENTRIES, "Reduction exceeds bounded matrix entries", "resource_limit")
    _require(work <= _MAX_DENSE_WORK, "Reduction exceeds 100 million estimated cubic units", "resource_limit")
    _require(count * ((2*p*p + q*p + q*q) * 96 + 2048) + n * 1024 + 16384 <= _MAX_RESULT_BYTES,
             "Estimated reduction response exceeds 16 MiB", "resource_limit")
    terminations = _matrices(request["termination_admittance_s"], count, q, "termination admittance")
    retained_indices, eliminated_indices = [nodes.index(name) for name in retained], [nodes.index(name) for name in eliminated]
    reduced, auxiliaries, power_matrices, diagnostics = [], [], [], []
    for index, (frequency, matrix, termination) in enumerate(zip(frequencies, matrices, terminations)):
        poll()
        source_passivity, load_passivity = _passivity(matrix, "Source"), _passivity(termination, "Termination")
        yp = matrix[np.ix_(retained_indices, retained_indices)]
        ypq = matrix[np.ix_(retained_indices, eliminated_indices)]
        yqp = matrix[np.ix_(eliminated_indices, retained_indices)]
        system = matrix[np.ix_(eliminated_indices, eliminated_indices)] + termination
        solution, backward_error, condition = _solve_linear(system, yqp, f"admittance reduction {frequency} Hz")
        # Recompute the physical equation check independently of the helper's
        # reported residual, including when source/load scales differ greatly.
        equation_scale = max(_norm(system), _norm(yqp), np.finfo(float).tiny)
        scaled_system, scaled_rhs = system / equation_scale, yqp / equation_scale
        denominator = _norm(scaled_system) * _norm(solution) + _norm(scaled_rhs)
        _require(math.isfinite(denominator), "Unrepresentable equation residual scale", "numerical_failure")
        residual = _norm(scaled_system @ solution - scaled_rhs) / max(denominator, np.finfo(float).tiny)
        _require(residual <= 1e-10, "Auxiliary terminal equation residual exceeds tolerance", "numerical_failure")
        auxiliary = -solution
        y_reduced = yp + ypq @ auxiliary
        reduced_passivity = _passivity(y_reduced, "Reduced admittance")
        transform = np.zeros((n, p), dtype=complex)
        transform[retained_indices] = np.eye(p)
        transform[eliminated_indices] = auxiliary
        source_power = transform.conj().T @ matrix @ transform
        load_power = auxiliary.conj().T @ termination @ auxiliary
        power = source_power + load_power
        power_scale = max(_norm(y_reduced), _norm(source_power), _norm(load_power), np.finfo(float).tiny)
        power_error = _norm(y_reduced - power) / power_scale
        _require(power_error <= 1e-9, "Terminated field/circuit power identity failed", "numerical_failure")
        _require(all(math.isfinite(value) for value in (condition, backward_error, residual, power_error)),
                 "Nonfinite reduction diagnostics", "numerical_failure")
        reduced.append(_pairs(y_reduced)); auxiliaries.append(_pairs(auxiliary)); power_matrices.append(_pairs(power))
        diagnostics.append({"frequency_hz": frequency, "relative_equation_residual": residual,
                            "relative_backward_error": backward_error, "equilibrated_condition_number": condition,
                            "relative_power_identity_error": power_error, "source_passivity": source_passivity,
                            "termination_passivity": load_passivity, "reduced_passivity": reduced_passivity})
    poll()
    result = {"contract": RESULT_CONTRACT, "model_status": source["model_status"], "production_qualified": False,
              "nodes": retained, "retained_nodes": retained, "eliminated_nodes": eliminated, "source_nodes": nodes,
              "reference_node": source["reference_node"], "source_id": source["source_id"],
              "context_digest": source["context_digest"], "source_digest": _digest(source), "input_digest": _digest(request),
              "frequencies_hz": frequencies, "admittance_s": reduced, "auxiliary_voltage_basis": auxiliaries,
              "termination_admittance_s": request["termination_admittance_s"],
              "power_identity_matrix_s": power_matrices,
              "diagnostics": {"frequency_results": diagnostics, "estimated_dense_cubic_work": work, "matrix_entries": entries},
              "limitations": ["Only supplied positive frequency samples; no interpolation or resampling",
                              "Sampled passive admittance does not establish broadband causality, a realizable fit or transient stability",
                              "Explicit terminations share the source reference; no return-path or external circuit is inferred",
                              "Source approximation/experimental status is preserved; no production qualification or physical extraction accuracy claim"]}
    try:
        encoded = json.dumps(result, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as error:
        raise PdnAdmittanceReductionError("numerical_failure", f"Result is not finite JSON: {error}") from error
    _require(len(encoded) <= _MAX_RESULT_BYTES, "Reduction response exceeds 16 MiB", "resource_limit")
    return result


def dielectric_admittance_source(result):
    """Copy the sampled source from a declared experimental dielectric result.

    This adapter preserves its explicit reference and input/context lineage;
    it does not authenticate the original inputs or establish causal validity.
    Large field arrays are not copied into the compact terminal source.
    """
    _require(isinstance(result, dict) and result.get("contract") == "spike/pdn-dielectric-ac-result/v1",
             "Expected a finite-dielectric AC result")
    _require(result.get("model_status") == "experimental" and result.get("production_qualified") is False,
             "Dielectric source must remain experimental and unqualified")
    _digest_value(result.get("input_digest"), "dielectric input_digest")
    reference = result.get("reference_electrode")
    _require(isinstance(reference, dict) and "node" in reference, "Missing explicit dielectric reference node")
    samples = result.get("ac")
    _require(isinstance(samples, list) and 1 <= len(samples) <= _MAX_FREQUENCIES,
             "Invalid dielectric frequency sample count", "resource_limit")
    _require(all(isinstance(sample, dict) and "frequency_hz" in sample and "admittance_s" in sample for sample in samples),
             "Incomplete dielectric admittance samples")
    source = _snapshot({"nodes": result.get("nodes"), "reference_node": reference["node"],
                        "frequencies_hz": [sample["frequency_hz"] for sample in samples],
                        "admittance_s": [sample["admittance_s"] for sample in samples],
                        "model_status": "experimental", "source_id": result["input_digest"],
                        "context_digest": result.get("context_digest")})
    _source(source)
    return source
