# SPDX-License-Identifier: Apache-2.0
"""Offline, explicitly mapped removal of a supplied coupled 2N-port fixture.

Original block-wave derivation and scope: docs/MULTIPORT_DEEMBEDDING.md.
Shared sampled-network admission preserves the existing real-reference convention.
"""
from __future__ import annotations

import math
import numpy as np

from . import sparameter_sampling as admission

REQUEST_CONTRACT = "spike/multiport-deembedding-request/v1"
RESULT_CONTRACT = "spike/multiport-deembedding-result/v1"
MAX_CONDITION = 1e8
MAX_RESIDUAL = 1e-10
MIN_TRANSMISSION = 1e-12


class MultiportDeembeddingError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = "MULTIPORT_DEEMBEDDING_" + code.upper()


def require(condition, message, code="invalid_request"):
    if not condition:
        raise MultiportDeembeddingError(code, message)


def network(raw, poll):
    admission._record(raw, {"id", "port_names", "reference_impedance_ohm",
                            "frequencies_hz", "s_parameters"}, "network")
    admission._name(raw["id"], "network ID")
    names = raw["port_names"]
    require(isinstance(names, list) and 1 <= len(names) <= 16,
            "Supply 1..16 unique named ports", "resource_limit")
    for name in names:
        admission._name(name, "port name")
    require(len(set(names)) == len(names), "Duplicate port name")
    require(admission._number(raw["reference_impedance_ohm"], "reference impedance") > 0,
            "Positive common real reference required")
    frequencies = admission._grid(raw["frequencies_hz"], "source frequencies")
    # Distinct JSON integers must also remain distinct in numerical frequency space.
    values = [float(f) for f in frequencies]
    require(all(b > a for a, b in zip(values, values[1:])), "Unresolved frequency grid")
    records = raw["s_parameters"]
    require(isinstance(records, list) and len(records) == len(frequencies), "Sample count mismatch")
    require(len(frequencies) * len(names)**2 <= 131072,
            "Network exceeds 131072 complex entries", "resource_limit")
    matrices = []
    for frequency, record in zip(frequencies, records):
        poll()
        matrices.append(admission._matrix(record, len(names), dc=frequency == 0))
    return matrices


def norm(matrix):
    value = float(np.linalg.norm(matrix))
    require(math.isfinite(value), "Nonfinite norm", "numerical_failure")
    return value


def condition(matrix, label, *, transmission=False):
    singular = np.linalg.svd(matrix, compute_uv=False)
    require(np.isfinite(singular).all() and singular[-1] > 0,
            f"Singular {label}", "ill_conditioned")
    if transmission:
        require(singular[-1] >= MIN_TRANSMISSION,
                f"{label} minimum singular value below 1e-12", "representation_limit")
    value = float(singular[0] / singular[-1])
    require(math.isfinite(value) and value <= MAX_CONDITION,
            f"{label} condition exceeds 1e8", "ill_conditioned")
    return value


def solve(matrix, rhs):
    result = np.linalg.solve(matrix, rhs)
    residual = norm(matrix @ result - rhs) / max(
        norm(matrix) * norm(result) + norm(rhs), np.finfo(float).tiny)
    require(residual <= MAX_RESIDUAL, "Solve backward residual exceeds 1e-10", "numerical_failure")
    return result, residual


def remove(measured, fixture, external, internal):
    ee = fixture[np.ix_(external, external)]
    ei = fixture[np.ix_(external, internal)]
    ie = fixture[np.ix_(internal, external)]
    ii = fixture[np.ix_(internal, internal)]
    ce = condition(ei, "outward fixture transmission", transmission=True)
    ci = condition(ie, "inward fixture transmission", transmission=True)
    require(ce * ci <= MAX_CONDITION, "Fixture transmission condition product exceeds 1e8", "ill_conditioned")
    first, r1 = solve(ei, measured - ee)
    # Right solve uses transpose, never conjugate transpose.
    xt, r2 = solve(ie.T, first.T)
    x = xt.T
    identity = np.eye(len(external))
    recovery = identity + x @ ii
    cr = condition(recovery, "DUT recovery")
    dut, r3 = solve(recovery, x)
    feedback = identity - ii @ dut
    cf = condition(feedback, "reconnection feedback")
    incident, r4 = solve(feedback, ie)
    reconstructed = ee + ei @ dut @ incident
    # Absolute floor for zero measurements; scale does not conceal cancellation.
    residual = norm(reconstructed - measured) / max(1., norm(measured))
    require(residual <= MAX_RESIDUAL, "Measured-wave reconstruction exceeds 1e-10", "numerical_failure")
    return dut, {"transmission_condition_product": ce * ci,
                 "outward_condition": ce, "inward_condition": ci,
                 "recovery_condition": cr, "feedback_condition": cf,
                 "max_solve_backward_residual": max(r1, r2, r3, r4),
                 "reconstruction_residual": residual,
                 "sampled_smax": float(np.linalg.svd(dut, compute_uv=False)[0])}


def deembed_multiport(request, *, cancel_check=None):
    """Derive a separate sampled DUT; no calibration, interpolation or repair."""
    require(cancel_check is None or callable(cancel_check), "Cancellation hook must be callable")

    def poll():
        if cancel_check is not None:
            try:
                stopped = cancel_check()
            except Exception as error:
                raise MultiportDeembeddingError("cancel_check_failed", str(error)) from error
            require(not stopped, "Multiport deembedding cancelled", "cancelled")

    poll()
    try:
        frozen, size = admission._snapshot(request)
        admission._record(frozen, {"contract", "measured", "fixture", "external_ports", "dut_ports"}, "request")
        require(frozen["contract"] == REQUEST_CONTRACT, "Unsupported multiport contract")
        measured, fixture = frozen["measured"], frozen["fixture"]
        # Reject resource/shape mismatches before allocating complex matrices.
        require(isinstance(measured, dict) and isinstance(fixture, dict), "Networks must be objects")
        names = measured.get("port_names")
        require(isinstance(names, list) and 1 <= len(names) <= 8, "DUT requires 1..8 ports", "resource_limit")
        fixture_names = fixture.get("port_names")
        require(isinstance(fixture_names, list) and len(fixture_names) == 2 * len(names), "Fixture requires 2N ports")
        frequencies = measured.get("frequencies_hz")
        require(isinstance(frequencies, list), "Measured frequency grid must be a list")
        require(3 * size + 4096 * len(frequencies) + 65536 <= 16 * 1024 * 1024,
                "Estimated output exceeds 16 MiB", "resource_limit")
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            measured_matrices = network(measured, poll)
            fixture_matrices = network(fixture, poll)
            require(measured["id"] != fixture["id"], "Source IDs must differ")
            require(measured["reference_impedance_ohm"] == fixture["reference_impedance_ohm"]
                    and measured["frequencies_hz"] == fixture["frequencies_hz"], "Exact grids and references required")
            external, internal = frozen["external_ports"], frozen["dut_ports"]
            require(isinstance(external, list) and isinstance(internal, list)
                    and external == names and len(internal) == len(names), "Explicit ordered external/DUT maps required")
            require(all(isinstance(p, str) for p in internal)
                    and len(set(external + internal)) == len(fixture_names)
                    and set(external + internal) == set(fixture_names), "Maps must partition every fixture port exactly once")
            ei = [fixture_names.index(p) for p in external]
            ii = [fixture_names.index(p) for p in internal]
            samples, diagnostics = [], []
            for frequency, m, f in zip(measured["frequencies_hz"], measured_matrices, fixture_matrices):
                poll()
                dut, diagnostic = remove(m, f, ei, ii)
                samples.append([[{"real": float(v.real), "imag": float(v.imag)} for v in row] for row in dut])
                diagnostics.append({"frequency_hz": frequency, **diagnostic})
            digest = admission._digest(frozen)
            result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                      "input_digest": digest, "source_request": frozen,
                      "derived_network": {"id": "deembedded-" + digest[:20], "port_names": internal,
                                          "reference_impedance_ohm": measured["reference_impedance_ohm"],
                                          "frequencies_hz": measured["frequencies_hz"], "s_parameters": samples},
                      "diagnostics": diagnostics,
                      "limitations": ["Supplied coupled fixture algebra only; calibration and measurement uncertainty unqualified",
                                      "Exact supplied grids and common positive real power-wave reference; no renormalization",
                                      "No passivity repair, causal-source inference, transient qualification or geometry extraction",
                                      "Experimental supplied-model transform; calibration, full-family and release qualification remain open"]}
            require(len(admission._json(result)) <= 16 * 1024 * 1024, "Output exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except MultiportDeembeddingError:
        raise
    except admission.SParameterSamplingError as error:
        raise MultiportDeembeddingError("invalid_request", str(error)) from error
    except (ValueError, TypeError, KeyError, OverflowError, ArithmeticError, np.linalg.LinAlgError) as error:
        raise MultiportDeembeddingError("numerical_failure", str(error)) from error
