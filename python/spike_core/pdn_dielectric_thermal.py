# SPDX-License-Identifier: Apache-2.0
"""One-way retained dielectric AC loss into the existing steady thermal solve.

Original RMS exp(+j*omega*t) power derivation: combine coherent complex basis
fields first, E_e=sum_j E_ej V_j. Then q_e=Re(E_e^H D_e E_e), where
D_e=sigma_e I + omega tan(delta)_e epsilon_e, in W/m^3. There is no factor
1/2 and no sum of independent-port losses: coherent cross terms are retained.
The independent port check is Re(V^H Y V)=sum_e volume_e*q_e. Conventional
complex power is conjugated, but its real dissipation is identical.

The thermal owner receives explicit cell sources on the identical canonical
mesh, with independently supplied thermal conductivity and boundary conditions.
No temperature feedback, inferred material mapping, prior field-result trust,
mesh transfer, transient heating or measured/production qualification is added.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Callable

import numpy as np

from .assembly_tetra_thermal import RESULT_CONTRACT as THERMAL_RESULT, run_assembly_tetra_thermal
from .assembly_tetra_thermal_validation import AssemblyTetraThermalError, validate_request as validate_thermal
from .pdn_dielectric_ac import (
    PdnDielectricAcError, RESULT_CONTRACT as AC_RESULT, extract_pdn_dielectric_ac,
)

REQUEST_CONTRACT = "spike/pdn-dielectric-thermal-request/v1"
RESULT_CONTRACT = "spike/pdn-dielectric-thermal-result/v1"
_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_MAX_RESULT_BYTES = 16 * 1024 * 1024


class PdnDielectricThermalError(ValueError):
    """Structured refusal; failed/cancelled coupled studies publish no result."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "PDN_DIELECTRIC_THERMAL_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise PdnDielectricThermalError(code, message)


def _keys(value, fields, name, code="invalid_request"):
    _require(isinstance(value, dict) and set(value) == set(fields), f"Invalid {name} fields", code)


def _number(value, name, *, positive=False, code="invalid_request"):
    _require(type(value) in (float, int), f"{name} must be a finite scalar", code)
    try:
        result = float(value)
    except OverflowError as error:
        raise PdnDielectricThermalError(code, f"Unrepresentable {name}") from error
    _require(math.isfinite(result) and (not positive or result > 0), f"Invalid {name}", code)
    return result


def _complex(value, name, code="invalid_request"):
    _keys(value, {"real", "imag"}, name, code)
    return complex(_number(value["real"], name, code=code), _number(value["imag"], name, code=code))


def _complex_array(raw, shape, name):
    if not shape:
        return _complex(raw, name, "numerical_failure")
    _require(isinstance(raw, list) and len(raw) == shape[0], f"Invalid returned {name} dimensions", "numerical_failure")
    return np.array([_complex_array(row, shape[1:], name) for row in raw], dtype=complex)


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _snapshot(request):
    chunks, size = [], 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False).iterencode(request):
            size += len(chunk.encode())
            _require(size <= _MAX_REQUEST_BYTES, "Coupled request exceeds 8 MiB", "resource_limit")
            chunks.append(chunk)
        return json.loads("".join(chunks))
    except PdnDielectricThermalError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise PdnDielectricThermalError("invalid_request", f"Invalid finite JSON: {error}") from error


def _prepare(request):
    _keys(request, {"contract", "electrical_request", "drive", "thermal_request"}, "coupled request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported dielectric thermal contract")
    electrical, thermal, drive = request["electrical_request"], request["thermal_request"], request["drive"]
    _require(isinstance(electrical, dict) and isinstance(thermal, dict), "Explicit electrical and thermal requests required")
    _keys(drive, {"frequency_hz", "voltages_v"}, "drive")
    frequency = _number(drive["frequency_hz"], "drive frequency", positive=True)
    frequencies = electrical.get("frequencies_hz")
    _require(isinstance(frequencies, list) and len(frequencies) == 1
             and _number(frequencies[0], "electrical frequency", positive=True) == frequency,
             "Electrical request must contain exactly the single coherent drive frequency")
    mesh = electrical.get("mesh")
    _require(isinstance(mesh, dict) and isinstance(mesh.get("vertices"), list)
             and isinstance(mesh.get("cells"), list), "Retained electrical mesh required")
    _require(4 <= len(mesh["vertices"]) <= 1000 and 1 <= len(mesh["cells"]) <= 2000,
             "Coupled dielectric mesh exceeds 1000 nodes/2000 cells", "resource_limit")
    mesh_digest = _digest(mesh)
    _require(isinstance(thermal.get("mesh"), dict) and _digest(thermal["mesh"]) == mesh_digest,
             "Electrical and thermal canonical mesh digests must be identical")
    sources = thermal.get("heat_sources_w_m3", {})
    _require(isinstance(sources, dict) and not sources, "Thermal heat sources must be absent or empty; double counting is not admitted")
    electrodes = electrical.get("electrodes")
    _require(isinstance(electrodes, list) and 2 <= len(electrodes) <= 16
             and all(isinstance(e, dict) and isinstance(e.get("id"), str) and isinstance(e.get("node"), str)
                     for e in electrodes), "Explicit named electrical electrodes required")
    signals = [e["node"] for e in electrodes if e["id"] != electrical.get("reference_electrode")]
    _require(len(signals) == len(electrodes) - 1 and len(set(signals)) == len(signals), "Invalid signal/reference electrode identities")
    voltages = drive["voltages_v"]
    _require(isinstance(voltages, dict) and set(voltages) == set(signals),
             "Drive must map every signal node exactly once; reference voltage is implicitly zero")
    voltage = np.array([_complex(voltages[node], "drive voltage") for node in signals])
    # Conservatively reserve repeated cell IDs/ownership and the nested thermal
    # result before either solve. The exact serialized response is checked too.
    estimate = (8 * len(json.dumps(request, ensure_ascii=False).encode("utf-8"))
                + 2048 * len(mesh["cells"]) + 256 * len(mesh["vertices"]) + 65536)
    _require(estimate <= _MAX_RESULT_BYTES, "Estimated coupled response exceeds 16 MiB", "resource_limit")
    try:
        thermal_data = validate_thermal(thermal)
    except AssemblyTetraThermalError as error:
        raise PdnDielectricThermalError("invalid_request", f"Thermal admission failed: {error}") from error
    return electrical, thermal, frequency, signals, voltage, mesh_digest, thermal_data


def run_pdn_dielectric_thermal(request, *, cancel_check: Callable[[], bool] | None = None):
    """Rerun coherent AC fields and hand their checked volumetric loss to heat.

    Cancellation is polled within AC and around thermal execution. The existing
    thermal solver has no internal callback; a cancellation during that solve
    discards its completed result before this function can publish success.
    """
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise PdnDielectricThermalError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "Coupled dielectric thermal execution cancelled", "cancelled")

    poll()
    frozen = _snapshot(request)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _run(frozen, poll, cancel_check)
    except PdnDielectricThermalError:
        raise
    except PdnDielectricAcError as error:
        raise PdnDielectricThermalError(error.code.removeprefix("PDN_DIELECTRIC_AC_").lower(), str(error)) from error
    except AssemblyTetraThermalError as error:
        raise PdnDielectricThermalError("thermal_failure", str(error)) from error
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError) as error:
        raise PdnDielectricThermalError("numerical_failure", f"Coupled numerical failure: {error}") from error


def _run(request, poll, cancel_check):
    electrical, thermal, frequency, nodes, voltage, mesh_digest, data = _prepare(request)
    poll()
    ac = extract_pdn_dielectric_ac(electrical, cancel_check=cancel_check)
    poll()
    _require(isinstance(ac, dict) and ac.get("contract") == AC_RESULT and ac.get("model_status") == "experimental"
             and ac.get("production_qualified") is False and ac.get("nodes") == nodes
             and ac.get("mesh_digest") == mesh_digest and ac.get("input_digest") == _digest(electrical)
             and ac.get("context_digest") == electrical.get("context_digest"),
             "Electrical result identity or source binding mismatch", "numerical_failure")
    responses = ac.get("ac")
    _require(isinstance(responses, list) and len(responses) == 1 and isinstance(responses[0], dict)
             and responses[0].get("frequency_hz") == frequency, "Electrical result frequency mismatch", "numerical_failure")
    response, cells = responses[0], data["cells"]
    fields = _complex_array(response.get("basis_cell_electric_field_v_m"), (len(cells), 3, len(nodes)), "basis fields")
    admittance = _complex_array(response.get("admittance_s"), (len(nodes), len(nodes)), "admittance")
    omega = 2 * math.pi * frequency
    dissipation = {}
    for material in electrical["materials"]:
        epsilon = np.asarray(material["permittivity_f_m"], dtype=float)
        if epsilon.ndim == 0:
            epsilon = float(epsilon) * np.eye(3)
        dissipation[material["id"]] = material["conductivity_s_m"] * np.eye(3) + omega * material["loss_tangent"] * epsilon
    sources, powers, lineage = {}, {}, []
    for index, (cell, (volume, _)) in enumerate(zip(cells, data["geometry"])):
        if index % 64 == 0:
            poll()
        field = fields[index] @ voltage
        density = float(np.vdot(field, dissipation[cell["material_id"]] @ field).real)
        power = volume * density
        _require(math.isfinite(density) and density >= 0 and math.isfinite(power),
                 "Nonfinite or negative dielectric heat density; no clipping is applied", "numerical_failure")
        sources[cell["id"]], powers[cell["id"]] = density, power
        lineage.append({"cell_id": cell["id"], "material_id": cell["material_id"], "source_object_ids": cell["source_object_ids"],
                        "volume_m3": volume})
    total = math.fsum(powers.values())
    currents = admittance @ voltage
    port_power = float(np.vdot(voltage, currents).real)
    apparent_scale = float(np.linalg.norm(voltage) * np.linalg.norm(currents))
    _require(all(math.isfinite(value) for value in (total, port_power, apparent_scale)),
             "Nonfinite integrated or terminal power", "numerical_failure")
    error = abs(total - port_power)
    loss_scale = max(total, abs(port_power), np.finfo(float).tiny)
    tolerance = 1e-9 * loss_scale + 256 * np.finfo(float).eps * apparent_scale
    _require(error <= tolerance, "Integrated dielectric loss and real terminal power disagree", "power_balance_failure")
    # Relative-to-loss remains explicit even at zero loss; the separate
    # absolute tolerance accounts for reactive-power roundoff without clipping.
    relative_error = error / loss_scale
    generated = {**thermal, "heat_sources_w_m3": sources}
    poll()
    thermal_result = run_assembly_tetra_thermal(generated)
    poll()
    _require(isinstance(thermal_result, dict) and thermal_result.get("contract") == THERMAL_RESULT
             and thermal_result.get("model_status") == "experimental" and thermal_result.get("production_qualified") is False,
             "Invalid thermal result status", "numerical_failure")
    temperatures = thermal_result.get("node_temperatures_k")
    _require(isinstance(temperatures, list) and len(temperatures) == len(data["xyz"]),
             "Thermal result node count mismatch", "numerical_failure")
    for temperature in temperatures:
        _require(_number(temperature, "temperature", code="numerical_failure") >= 0,
                 "Negative thermal temperature", "numerical_failure")
    heat_balance = thermal_result.get("heat_balance")
    _require(isinstance(heat_balance, dict), "Missing thermal heat balance", "numerical_failure")
    delivered = _number(heat_balance.get("source_w"), "thermal delivered heat", code="numerical_failure")
    _require(abs(delivered - total) <= 1e-10 * max(total, np.finfo(float).tiny),
             "Thermal source power differs from generated dielectric heat", "power_balance_failure")
    result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
              "coupling_mode": "one_way_no_temperature_feedback", "frequency_hz": frequency, "drive": request["drive"],
              "nodes": nodes, "reference_node": ac["reference_electrode"]["node"],
              "input_digest": _digest(request), "electrical_input_digest": ac["input_digest"],
              "thermal_input_digest": _digest(thermal), "generated_thermal_input_digest": _digest(generated),
              "mesh_digest": mesh_digest, "context_digest": ac["context_digest"],
              "heat_sources_w_m3": sources, "cell_power_w": powers, "cell_lineage": lineage,
              "total_dielectric_power_w": total, "port_power_w": port_power, "loss_relative_error": relative_error,
              "thermal_result": thermal_result, "electrical_diagnostics": response["diagnostics"],
              "diagnostics": {"loss_absolute_error_w": error, "loss_acceptance_tolerance_w": tolerance,
                              "apparent_power_scale_va": apparent_scale, "thermal_source_error_w": abs(delivered - total),
                              "nodes": len(data["xyz"]), "cells": len(cells)},
              "limitations": ["Single coherent RMS tone; finite retained electroquasistatic dielectric only",
                              "One-way constant-parameter heating; no temperature feedback or electrothermal iteration",
                              "Identical canonical mesh and material IDs required; electrical and thermal property values are supplied independently",
                              "Existing steady thermal boundary model only; no transient, airflow or inferred heat transfer",
                              "Cancellation is polled within AC and around thermal execution; thermal has no internal cancellation callback",
                              "Analytical and conservation checks do not establish measured-board accuracy or production qualification"]}
    try:
        encoded = json.dumps(result, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as error:
        raise PdnDielectricThermalError("numerical_failure", f"Result is not finite JSON: {error}") from error
    _require(len(encoded) <= _MAX_RESULT_BYTES, "Coupled response exceeds 16 MiB", "resource_limit")
    return result
