# SPDX-License-Identifier: Apache-2.0
"""Experimental coherent cascade of supplied scalar RLGC sections.

Independent composition: leaf outgoing power waves b=W*a, where W is the
block diagonal matrix of the actual S03 section networks. Ideal equal-reference
junctions exchange adjacent outgoing/incident waves: a=C*b+U*a_external.
Solving (I-C*W)*X=U for both external basis drives gives a=X*a_external and
S_external=(W*X)[external_rows,:]. No transfer-matrix division or inferred
renormalization is needed. Actual S04 field solves receive those local drives.
At each connection V_left=V_right, I_into_left+I_into_right=0, and the signed
terminal powers cancel. Integrated section heat is summed once per section.

Foundation: Staelin, Electromagnetics and Applications (2011), MIT OCW,
chapter 8 sections 8.1.2 and 8.3.1: interface continuity and lossy phasor
telegrapher laws. Original independently authored composition, with no external
implementation used. A model interface is ideal; bend/launch physics is absent.
"""
from __future__ import annotations

import math

import numpy as np

from .rlgc_line_network import RLGCLineNetworkError, build_rlgc_line_network
from .rlgc_line_fields import RLGCLineFieldsError, _prepare as _prepare_fields, run_rlgc_line_fields
from .sparameter_sampling import SParameterSamplingError, _digest, _json, _snapshot

REQUEST_CONTRACT = "spike/rlgc-line-cascade-request/v1"
RESULT_CONTRACT = "spike/rlgc-line-cascade-result/v1"
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_WORK = 100_000_000
_MAX_CONDITION = 1e8
_SOLVE_TOLERANCE = 1e-10
_JUNCTION_TOLERANCE = 1e-9
_POWER_TOLERANCE = 1e-10


class RLGCLineCascadeError(ValueError):
    """Atomic malformed-input, resource, conditioning or conservation failure."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "RLGC_LINE_CASCADE_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise RLGCLineCascadeError(code, message)


def _record(value, fields, name):
    _require(isinstance(value, dict) and set(value) == set(fields), f"Invalid {name} fields")


def _complex(value):
    return np.complex128(complex(value["real"], value["imag"]))


def _pair(value):
    _require(np.isfinite(value), "Nonfinite complex result", "numerical_failure")
    return {"real": float(value.real), "imag": float(value.imag)}


def _power(waves):
    return np.sum(waves.real * waves.real + waves.imag * waves.imag)


def _child_request(section, excitations):
    return {"contract": "spike/rlgc-line-fields-request/v1", "line_request": section["line_request"],
            "excitations": excitations, "probes": section["probes"]}


def _prepare(request, poll):
    _record(request, {"contract", "sections", "excitations"}, "RLGC cascade request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported RLGC cascade contract")
    sections = request["sections"]
    _require(isinstance(sections, list) and 1 <= len(sections) <= 8, "Provide 1..8 ordered sections", "resource_limit")
    names, first_grid, first_reference = [], None, None
    for section in sections:
        poll()
        _record(section, {"id", "line_request", "probes"}, "section")
        name = section["id"]
        _require(isinstance(name, str) and name.strip() and len(name) <= 80, "Section id must contain 1..80 characters")
        names.append(name)
        # Reuse S04 admission before JSON coercion, without running a solver.
        _prepare_fields(_child_request(section, request["excitations"]), poll)
        line = section["line_request"]
        grid = [sample["frequency_hz"] for sample in line["samples"]]
        if first_grid is None:
            first_grid, first_reference = grid, line["reference_impedance_ohm"]
        _require(grid == first_grid, "Every section must have exactly the same positive frequency grid")
        _require(line["reference_impedance_ohm"] == first_reference, "Every section must have the same real reference; no renormalization")
    _require(len(set(names)) == len(names), "Section ids must be unique")


def _connection_matrices(count):
    connection, injection = np.zeros((2 * count, 2 * count)), np.zeros((2 * count, 2))
    injection[0, 0], injection[-1, 1] = 1., 1.
    for section in range(count - 1):
        right, left = 2 * section + 1, 2 * section + 2
        connection[right, left] = connection[left, right] = 1.
    return connection, injection


def _solve_connection(networks, index, connection, injection, incident):
    count = len(networks)
    leaf = np.zeros((2 * count, 2 * count), dtype=complex)
    for section, network in enumerate(networks):
        leaf[2 * section:2 * section + 2, 2 * section:2 * section + 2] = np.array(
            [[_complex(value) for value in row] for row in network["s_parameters"][index]])
    system = np.eye(2 * count) - connection @ leaf
    condition = float(np.linalg.cond(system))
    _require(math.isfinite(condition) and condition <= _MAX_CONDITION,
             "Connection condition exceeds 1e8", "ill_conditioned")
    basis = np.linalg.solve(system, injection)
    local = basis @ incident
    for actual, rhs in ((basis, injection), (local, injection @ incident)):
        residual = np.linalg.norm(system @ actual - rhs)
        scale = np.linalg.norm(system) * np.linalg.norm(actual) + np.linalg.norm(rhs)
        _require(np.isfinite(actual).all() and math.isfinite(float(residual)) and residual <= _SOLVE_TOLERANCE * scale,
                 "Connection solve residual exceeds relative 1e-10", "numerical_failure")
    scattering = (leaf @ basis)[[0, 2 * count - 1], :]
    _require(np.isfinite(scattering).all(), "Nonfinite cascade scattering matrix", "numerical_failure")
    singular_max = float(np.linalg.svd(scattering, compute_uv=False)[0])
    _require(math.isfinite(singular_max) and singular_max <= 1 + 1e-9,
             "Cascade violates sampled passivity tolerance 1e-9", "numerical_failure")
    _require(abs(scattering[0, 1] - scattering[1, 0]) <= 1e-10,
             "Cascade violates reciprocity tolerance 1e-10", "numerical_failure")
    return scattering, local, condition


def _ledger(frequency, index, sections, child_results, incident, scattering, reference):
    outgoing = scattering @ incident
    incident_power, output_power = _power(incident), _power(outgoing)
    net_input = incident_power - output_power
    child_points = [child["points"][index] for child in child_results]
    conductor = np.sum([np.float64(point["power_balance"]["conductor_loss_w"]) for point in child_points])
    dielectric = np.sum([np.float64(point["power_balance"]["dielectric_loss_w"]) for point in child_points])
    total, residual = conductor + dielectric, net_input - (conductor + dielectric)
    terminal_input = (np.float64(child_points[0]["boundary_values"]["left"]["input_power_w"])
                      + np.float64(child_points[-1]["boundary_values"]["right"]["input_power_w"]))
    tolerance = _POWER_TOLERANCE * max(incident_power, total, abs(net_input), abs(terminal_input))
    _require(all(math.isfinite(float(value)) for value in (net_input, conductor, dielectric, residual))
             and conductor >= 0 and dielectric >= 0 and net_input >= -tolerance
             and abs(residual) <= tolerance and abs(net_input - terminal_input) <= tolerance,
             "Global section loss ledger fails relative 1e-10 power balance", "numerical_failure")
    junctions = []
    wave_scale = np.sqrt(incident_power)
    for position in range(len(sections) - 1):
        left = child_points[position]["boundary_values"]["right"]
        right = child_points[position + 1]["boundary_values"]["left"]
        vl, vr = _complex(left["voltage_v"]), _complex(right["voltage_v"])
        il, ir = _complex(left["current_into_line_a"]), _complex(right["current_into_line_a"])
        voltage_residual, current_residual = vl - vr, il + ir
        power_residual = np.float64(left["input_power_w"]) + np.float64(right["input_power_w"])
        voltage_scale = max(abs(vl), abs(vr), np.sqrt(reference) * wave_scale)
        current_scale = max(abs(il), abs(ir), wave_scale / np.sqrt(reference))
        power_scale = max(incident_power, abs(left["input_power_w"]), abs(right["input_power_w"]))
        _require(np.isfinite(voltage_residual) and np.isfinite(current_residual) and np.isfinite(power_residual)
                 and abs(voltage_residual) <= _JUNCTION_TOLERANCE * voltage_scale
                 and abs(current_residual) <= _JUNCTION_TOLERANCE * current_scale
                 and abs(power_residual) <= _POWER_TOLERANCE * power_scale,
                 "Junction voltage, current or signed power continuity failed", "numerical_failure")
        junctions.append({"left_section_id": sections[position]["id"], "right_section_id": sections[position + 1]["id"],
                          "voltage_residual_v": _pair(voltage_residual), "current_residual_a": _pair(current_residual),
                          "power_residual_w": float(power_residual)})
    return {"frequency_hz": frequency,
            "power_balance": {"net_input_w": float(net_input), "conductor_loss_w": float(conductor),
                              "dielectric_loss_w": float(dielectric), "total_loss_w": float(total), "residual_w": float(residual)},
            "junctions": junctions}


def run_rlgc_line_cascade(request, *, cancel_check=None):
    """Return a sampled network, actual child fields and conservative heat ledger."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise RLGCLineCascadeError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "RLGC cascade calculation cancelled", "cancelled")

    try:
        poll()
        _prepare(request, poll)
        frozen, size = _snapshot(request)
        _prepare(frozen, poll)
        sections, excitations = frozen["sections"], frozen["excitations"]
        count, samples = len(sections), len(excitations)
        probe_count = sum(len(section["probes"]) for section in sections)
        estimate = 5 * size + samples * (4096 + 4096 * count + 1536 * probe_count) + 65536
        _require(estimate <= _MAX_RESULT_BYTES, "Estimated nested cascade response exceeds 16 MiB", "resource_limit")
        _require(samples * ((2 * count)**3 + 64 * count + 32 * probe_count) <= _MAX_WORK,
                 "Estimated combined cascade work exceeds 100 million units", "resource_limit")
        networks = []
        for section in sections:
            poll()
            networks.append(build_rlgc_line_network(section["line_request"], cancel_check=cancel_check)["network"])
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            connection, injection = _connection_matrices(count)
            drives, matrices, external_drives, max_condition = [[] for _ in sections], [], [], 0.
            for index, excitation in enumerate(excitations):
                poll()
                incident = np.array([_complex(excitation["incident_left"]), _complex(excitation["incident_right"])])
                matrix, local, condition = _solve_connection(networks, index, connection, injection, incident)
                matrices.append(matrix)
                external_drives.append(incident)
                max_condition = max(max_condition, condition)
                for position in range(count):
                    drives[position].append({"frequency_hz": excitation["frequency_hz"],
                                             "incident_left": _pair(local[2 * position]), "incident_right": _pair(local[2 * position + 1])})
            children = []
            for section, local_drives in zip(sections, drives):
                poll()
                children.append(run_rlgc_line_fields(_child_request(section, local_drives), cancel_check=cancel_check))
            reference = np.float64(networks[0]["reference_impedance_ohm"])
            points = []
            for index, (excitation, matrix, incident) in enumerate(zip(excitations, matrices, external_drives)):
                poll()
                points.append(_ledger(excitation["frequency_hz"], index, sections, children, incident, matrix, reference))
            digest = _digest(frozen)
            result = {
                "contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                "input_digest": digest, "source_request": frozen,
                "network": {"id": "rlgc-cascade-" + digest[:20], "port_names": ["left", "right"],
                            "reference_impedance_ohm": networks[0]["reference_impedance_ohm"],
                            "frequencies_hz": list(networks[0]["frequencies_hz"]),
                            "s_parameters": [[[_pair(value) for value in row] for row in matrix] for matrix in matrices]},
                "sections": [{"id": section["id"], "result": child} for section, child in zip(sections, children)],
                "points": points,
                "diagnostics": {"sample_count": samples, "section_count": count,
                                "maximum_power_balance_residual_w": max(abs(point["power_balance"]["residual_w"]) for point in points),
                                "maximum_junction_power_residual_w": max((abs(junction["power_residual_w"]) for point in points for junction in point["junctions"]), default=0.),
                                "maximum_connection_condition_number": max_condition},
                "limitations": [
                    "Ordered supplied scalar RLGC sections with ideal zero-length common-reference junctions; no branches",
                    "Actual S03 networks and S04 RMS fields are reused; each section owns its integrated conductor and dielectric loss",
                    "All sections use exactly the same positive frequency grid and real reference; no DC or automatic renormalization",
                    "Junction voltage is continuous, inward currents oppose and signed powers cancel; raw residuals are retained",
                    "No geometry extraction, bend/launch/discontinuity parasitics, coupled conductors, thermal deposition or transient qualification",
                    "At most 8 sections, 1024 frequencies and 32 probes per section subject to combined 8 MiB input/16 MiB output limits",
                    "Connection condition at most 1e8, relative solve residual 1e-10, junction V/I tolerance 1e-9 and power tolerance 1e-10",
                    "Underlying S03/S04 propagation and representability bounds apply to every section; no clipping or residual redistribution",
                    "Synthetic verification only; experimental and not production qualified",
                ],
            }
            _require(len(_json(result)) <= _MAX_RESULT_BYTES, "Cascade response exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except RLGCLineCascadeError:
        raise
    except (RLGCLineNetworkError, RLGCLineFieldsError, SParameterSamplingError) as error:
        for prefix in ("RLGC_LINE_NETWORK_", "RLGC_LINE_FIELDS_", "SPARAMETER_SAMPLING_"):
            if error.code.startswith(prefix):
                raise RLGCLineCascadeError(error.code.removeprefix(prefix), str(error)) from error
        raise
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise RLGCLineCascadeError("numerical_failure", f"RLGC cascade numerical failure: {error}") from error
