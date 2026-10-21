# SPDX-License-Identifier: Apache-2.0
"""Experimental supplied scalar RLGC star, with coherent fields and owned heat.

Independent derivation: RMS V=sqrt(r)*(a+b), I_into=(a-b)/sqrt(r).
Common junction voltage and sum(I_into)=0 give a=J*b, J=2/m*11^T-I.
J is symmetric orthogonal: the ideal junction stores and dissipates no energy.
Place J on each leg's right-terminal block; left terminals are external.
For actual S03 leaf matrix W solve (I-C*W)*X=U, then S=(W*X)[left,:].
Actual S04 children receive X*a_external and retain the distributed heat.

Source: independently authored from Staelin, Electromagnetics and Applications
(2011), chapter 8 sections 8.1.2 (pp232,234), 8.3.1 (pp249-251), MIT OCW.
No external implementation used; no physical junction geometry is inferred.
"""
from __future__ import annotations

import math

import numpy as np

from .rlgc_line_network import RLGCLineNetworkError, build_rlgc_line_network
from .rlgc_line_fields import RLGCLineFieldsError, _prepare as _prepare_fields, run_rlgc_line_fields
from .sparameter_sampling import SParameterSamplingError, _digest, _json, _snapshot

REQUEST_CONTRACT = "spike/rlgc-line-junction-request/v1"
RESULT_CONTRACT = "spike/rlgc-line-junction-result/v1"
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_WORK = 100_000_000
_MAX_CONDITION = 1e8
_SOLVE_TOLERANCE = 1e-10
_JUNCTION_TOLERANCE = 1e-9
_POWER_TOLERANCE = 1e-10


class RLGCLineJunctionError(ValueError):
    """Atomic malformed-input, resource, conditioning or conservation failure."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "RLGC_LINE_JUNCTION_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise RLGCLineJunctionError(code, message)


def _record(value, fields, name):
    _require(isinstance(value, dict) and set(value) == set(fields), f"Invalid {name} fields")


def _complex(value):
    return np.complex128(complex(value["real"], value["imag"]))


def _pair(value):
    _require(np.isfinite(value), "Nonfinite complex result", "numerical_failure")
    return {"real": float(value.real), "imag": float(value.imag)}


def _power(waves):
    return np.sum(waves.real * waves.real + waves.imag * waves.imag)


def _child_request(leg, excitations):
    return {"contract": "spike/rlgc-line-fields-request/v1", "line_request": leg["line_request"],
            "excitations": excitations, "probes": leg["probes"]}


def _prepare(request, poll):
    _record(request, {"contract", "legs", "excitations"}, "RLGC junction request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported RLGC junction contract")
    legs = request["legs"]
    _require(isinstance(legs, list) and 2 <= len(legs) <= 8, "Provide 2..8 legs", "resource_limit")
    excitations = request["excitations"]
    _require(isinstance(excitations, list) and 1 <= len(excitations) <= 1024,
             "Provide 1..1024 excitation samples", "resource_limit")
    for excitation in excitations:
        _record(excitation, {"frequency_hz", "incident_waves"}, "excitation")
        _require(isinstance(excitation["incident_waves"], list) and len(excitation["incident_waves"]) == len(legs),
                 "Incident vector must have one wave per ordered leg")
    names, first_grid, first_reference = [], None, None
    for position, leg in enumerate(legs):
        poll()
        _record(leg, {"id", "line_request", "probes"}, "leg")
        name = leg["id"]
        _require(isinstance(name, str) and name.strip() and len(name) <= 80, "Leg id must contain 1..80 characters")
        names.append(name)
        # Reuse S04 admission before JSON coercion, without running a solver.
        _prepare_fields(_child_request(leg, [{"frequency_hz": drive["frequency_hz"],
            "incident_left": drive["incident_waves"][position], "incident_right": {"real": 0., "imag": 0.}}
            for drive in excitations]), poll)
        line = leg["line_request"]
        grid = [sample["frequency_hz"] for sample in line["samples"]]
        if first_grid is None:
            first_grid, first_reference = grid, line["reference_impedance_ohm"]
        _require(grid == first_grid, "Every leg must have exactly the same positive frequency grid")
        _require(line["reference_impedance_ohm"] == first_reference, "Every leg must have the same real reference; no renormalization")
    _require(len(set(names)) == len(names), "Leg ids must be unique")


def _connection_matrices(count):
    connection = np.zeros((2 * count, 2 * count))
    injection = np.zeros((2 * count, count))
    connection[1::2, 1::2] = 2. / count - np.eye(count)
    injection[::2, :] = np.eye(count)
    return connection, injection


def _solve_connection(networks, index, connection, injection, incident):
    count = len(networks)
    leaf = np.zeros((2 * count, 2 * count), dtype=complex)
    for leg, network in enumerate(networks):
        leaf[2 * leg:2 * leg + 2, 2 * leg:2 * leg + 2] = np.array(
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
    scattering = (leaf @ basis)[::2, :]
    _require(np.isfinite(scattering).all(), "Nonfinite junction scattering matrix", "numerical_failure")
    singular_max = float(np.linalg.svd(scattering, compute_uv=False)[0])
    _require(math.isfinite(singular_max) and singular_max <= 1 + 1e-9,
             "Junction network violates sampled passivity tolerance 1e-9", "numerical_failure")
    _require(np.max(np.abs(scattering - scattering.T)) <= 1e-10,
             "Junction network violates reciprocity tolerance 1e-10", "numerical_failure")
    return scattering, local, leaf @ local, condition


def _ledger(frequency, index, children, incident, scattering, reference, local, outgoing_local):
    incident_power = _power(incident)
    net_input = incident_power - _power(scattering @ incident)
    points = [child["points"][index] for child in children]
    conductor = dielectric = terminal_input = np.float64(0.)
    voltages, currents, powers = [], [], []
    root, wave_scale = np.sqrt(reference), np.sqrt(incident_power)
    for leg, point in enumerate(points):
        _require(point["frequency_hz"] == frequency, "Child frequency changed", "numerical_failure")
        balance = point["power_balance"]
        c, d = np.float64(balance["conductor_loss_w"]), np.float64(balance["dielectric_loss_w"])
        _require(np.isfinite(c) and np.isfinite(d) and c >= 0 and d >= 0,
                 "Invalid owned child losses", "numerical_failure")
        conductor += c
        dielectric += d
        terminal_sum = np.float64(0.)
        for end, name in enumerate(("left", "right")):
            boundary = point["boundary_values"][name]
            v, i = _complex(boundary["voltage_v"]), _complex(boundary["current_into_line_a"])
            power = np.float64(boundary["input_power_w"])
            a, b = local[2 * leg + end], outgoing_local[2 * leg + end]
            expected_v, expected_i = root * (a + b), (a - b) / root
            scale = max(incident_power, abs(power), abs(v * np.conj(i)))
            _require(np.isfinite(v) and np.isfinite(i) and np.isfinite(power)
                     and abs(v - expected_v) <= _JUNCTION_TOLERANCE * max(abs(v), abs(expected_v), root * wave_scale)
                     and abs(i - expected_i) <= _JUNCTION_TOLERANCE * max(abs(i), abs(expected_i), wave_scale / root)
                     and abs(power - np.real(v * np.conj(i))) <= _POWER_TOLERANCE * scale,
                     "Child boundary disagrees with connected waves", "numerical_failure")
            terminal_sum += power
            if end == 0:
                terminal_input += power
            else:
                voltages.append(v)
                currents.append(i)
                powers.append(power)
        scale = max(incident_power, c + d, abs(terminal_sum))
        _require(balance["total_loss_w"] == c + d
                 and np.isfinite(balance["net_input_w"]) and np.isfinite(balance["residual_w"])
                 and abs(balance["net_input_w"] - terminal_sum) <= _POWER_TOLERANCE * scale
                 and balance["residual_w"] == balance["net_input_w"] - balance["total_loss_w"]
                 and abs(terminal_sum - c - d) <= _POWER_TOLERANCE * scale,
                 "Child loss ledger is inconsistent", "numerical_failure")
    total, residual = conductor + dielectric, net_input - (conductor + dielectric)
    tolerance = _POWER_TOLERANCE * max(incident_power, total, abs(net_input), abs(terminal_input))
    _require(all(math.isfinite(float(value)) for value in (net_input, total, residual))
             and net_input >= -tolerance and abs(residual) <= tolerance and abs(net_input - terminal_input) <= tolerance,
             "Global leg loss ledger fails relative 1e-10 power balance", "numerical_failure")
    voltage_residuals = np.array(voltages) - voltages[0]
    current_residual, power_residual = np.sum(currents), np.sum(powers)
    voltage_scale = max(max(abs(v) for v in voltages), root * wave_scale)
    current_scale = max(sum(abs(i) for i in currents), wave_scale / root)
    power_scale = max(incident_power, sum(abs(p) for p in powers))
    _require(np.isfinite(voltage_residuals).all() and np.isfinite(current_residual) and np.isfinite(power_residual)
             and np.max(np.abs(voltage_residuals)) <= _JUNCTION_TOLERANCE * voltage_scale
             and abs(current_residual) <= _JUNCTION_TOLERANCE * current_scale
             and abs(power_residual) <= _POWER_TOLERANCE * power_scale,
             "Junction common voltage, KCL or signed power continuity failed", "numerical_failure")
    return {"frequency_hz": frequency,
            "power_balance": {"net_input_w": float(net_input), "conductor_loss_w": float(conductor),
                              "dielectric_loss_w": float(dielectric), "total_loss_w": float(total), "residual_w": float(residual)},
            "junction": {"voltage_residuals_v": [_pair(v) for v in voltage_residuals],
                         "current_residual_a": _pair(current_residual), "power_residual_w": float(power_residual)}}


def run_rlgc_line_junction(request, *, cancel_check=None):
    """Return a sampled network, actual child fields and conservative heat ledger."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise RLGCLineJunctionError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "RLGC junction calculation cancelled", "cancelled")

    try:
        poll()
        _prepare(request, poll)
        frozen, size = _snapshot(request)
        _prepare(frozen, poll)
        legs, excitations = frozen["legs"], frozen["excitations"]
        count, samples = len(legs), len(excitations)
        probe_count = sum(len(leg["probes"]) for leg in legs)
        estimate = 5 * size + samples * (4096 + 4096 * count + 256 * count**2 + 1536 * probe_count) + 65536
        _require(estimate <= _MAX_RESULT_BYTES, "Estimated nested junction response exceeds 16 MiB", "resource_limit")
        _require(samples * ((2 * count)**3 + 8 * count**3 + 64 * count + 32 * probe_count) <= _MAX_WORK,
                 "Estimated combined junction work exceeds 100 million units", "resource_limit")
        networks = []
        for leg in legs:
            poll()
            networks.append(build_rlgc_line_network(leg["line_request"], cancel_check=cancel_check)["network"])
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            connection, injection = _connection_matrices(count)
            drives, matrices, external_drives, local_waves, max_condition = [[] for _ in legs], [], [], [], 0.
            for index, excitation in enumerate(excitations):
                poll()
                incident = np.array([_complex(wave) for wave in excitation["incident_waves"]])
                matrix, local, local_out, condition = _solve_connection(networks, index, connection, injection, incident)
                matrices.append(matrix)
                local_waves.append((local, local_out))
                external_drives.append(incident)
                max_condition = max(max_condition, condition)
                for position in range(count):
                    drives[position].append({"frequency_hz": excitation["frequency_hz"],
                                             "incident_left": _pair(local[2 * position]), "incident_right": _pair(local[2 * position + 1])})
            children = []
            for leg, local_drives in zip(legs, drives):
                poll()
                child_request = _child_request(leg, local_drives)
                child = run_rlgc_line_fields(child_request, cancel_check=cancel_check)
                _require(child["contract"] == "spike/rlgc-line-fields-result/v1"
                         and child["model_status"] == "experimental" and child["production_qualified"] is False
                         and child["source_request"] == child_request and child["input_digest"] == _digest(child_request)
                         and child["network"] == networks[len(children)] and len(child["points"]) == samples,
                         "Child provenance or network changed", "numerical_failure")
                children.append(child)
            reference = np.float64(networks[0]["reference_impedance_ohm"])
            points = []
            for index, (excitation, matrix, incident) in enumerate(zip(excitations, matrices, external_drives)):
                poll()
                points.append(_ledger(excitation["frequency_hz"], index, children, incident, matrix, reference, *local_waves[index]))
            digest = _digest(frozen)
            result = {
                "contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                "input_digest": digest, "source_request": frozen,
                "network": {"id": "rlgc-junction-" + digest[:20], "port_names": [leg["id"] for leg in legs],
                            "reference_impedance_ohm": networks[0]["reference_impedance_ohm"],
                            "frequencies_hz": list(networks[0]["frequencies_hz"]),
                            "s_parameters": [[[_pair(value) for value in row] for row in matrix] for matrix in matrices]},
                "legs": [{"id": leg["id"], "result": child} for leg, child in zip(legs, children)],
                "points": points,
                "diagnostics": {"sample_count": samples, "leg_count": count,
                                "maximum_power_balance_residual_w": max(abs(point["power_balance"]["residual_w"]) for point in points),
                                "maximum_junction_voltage_residual_v": max(abs(_complex(v)) for point in points for v in point["junction"]["voltage_residuals_v"]),
                                "maximum_junction_current_residual_a": max(abs(_complex(point["junction"]["current_residual_a"])) for point in points),
                                "maximum_junction_power_residual_w": max(abs(point["junction"]["power_residual_w"]) for point in points),
                                "maximum_connection_condition_number": max_condition},
                "limitations": [
                    "Supplied scalar RLGC star: left leg ends are external ports, all right ends meet one ideal common-reference node",
                    "Actual S03 networks and S04 RMS fields are reused; each leg owns its integrated conductor and dielectric loss",
                    "All legs use exactly the same positive frequency grid and real reference; no DC or automatic renormalization",
                    "Junction voltage is common, inward currents sum to zero and signed powers cancel; raw residuals are retained",
                    "No geometry extraction, bend/launch/discontinuity parasitics, coupled conductors, thermal deposition or transient qualification",
                    "At most 8 legs, 1024 frequencies and 32 probes per leg subject to combined 8 MiB input/16 MiB output limits",
                    "Connection condition at most 1e8, relative solve residual 1e-10, junction V/I tolerance 1e-9 and power tolerance 1e-10",
                    "Underlying S03/S04 propagation and representability bounds apply to every leg; no clipping or residual redistribution",
                    "Synthetic verification only; experimental and not production qualified",
                ],
            }
            _require(len(_json(result)) <= _MAX_RESULT_BYTES, "Junction response exceeds 16 MiB", "resource_limit")
            poll()
            return result
    except RLGCLineJunctionError:
        raise
    except (RLGCLineNetworkError, RLGCLineFieldsError, SParameterSamplingError) as error:
        for prefix in ("RLGC_LINE_NETWORK_", "RLGC_LINE_FIELDS_", "SPARAMETER_SAMPLING_"):
            if error.code.startswith(prefix):
                raise RLGCLineJunctionError(error.code.removeprefix(prefix), str(error)) from error
        raise
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise RLGCLineJunctionError("numerical_failure", f"RLGC junction numerical failure: {error}") from error
