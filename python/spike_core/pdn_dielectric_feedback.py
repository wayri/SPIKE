# SPDX-License-Identifier: Apache-2.0
"""Bounded conductivity-only fixed-point feedback around retained AC heating.

Original derivation: each tetrahedron uses the mean of its four nodal
temperatures in sigma=sigma_ref*(1+alpha*(Tmean-Tref)). A complete coherent
RMS electrical/thermal solve defines F(T). Closure tests ||F(T)-T||_inf,
not the relaxed update r*(F(T)-T). The next iterate alone is underrelaxed.
Both the material-evaluation state T and the actual returned thermal F(T)
are retained, so a lagged or strongly damped state cannot claim closure.
Permittivity, loss tangent and thermal conductivity remain fixed. This is
an experimental steady fixed point, not a stability or uniqueness proof.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math

import numpy as np

from . import pdn_dielectric_thermal as coupled
from .pdn_dielectric_ac import PdnDielectricAcError, _prepare as prepare_ac
from .pdn_electrostatic import PdnElectrostaticError
from .assembly_tetra_thermal_validation import AssemblyTetraThermalError

REQUEST_CONTRACT = "spike/pdn-dielectric-feedback-request/v1"
RESULT_CONTRACT = "spike/pdn-dielectric-feedback-result/v1"
_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_TOTAL_WORK = 1_000_000_000


class PdnDielectricFeedbackError(ValueError):
    """Failed admission, iteration or cancellation publishes no partial result."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "PDN_DIELECTRIC_FEEDBACK_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise PdnDielectricFeedbackError(code, message)


def _keys(value, fields, name):
    _require(isinstance(value, dict) and set(value) == set(fields), f"Invalid {name} fields")


def _number(value, name, code="invalid_request"):
    _require(type(value) in (int, float), f"{name} must be a finite scalar", code)
    try:
        result = float(value)
    except OverflowError as error:
        raise PdnDielectricFeedbackError(code, f"Unrepresentable {name}") from error
    _require(math.isfinite(result), f"Nonfinite {name}", code)
    return result


def _snapshot(request):
    chunks, size = [], 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False).iterencode(request):
            size += len(chunk.encode())
            _require(size <= _MAX_REQUEST_BYTES, "Feedback request exceeds 8 MiB", "resource_limit")
            chunks.append(chunk)
        return json.loads("".join(chunks)), size
    except PdnDielectricFeedbackError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise PdnDielectricFeedbackError("invalid_request", f"Invalid finite JSON: {error}") from error


def _prepare(request, size):
    _keys(request, {"contract", "base_request", "conductivity_laws", "iteration"}, "feedback request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported feedback contract")
    options = request["iteration"]
    _keys(options, {"initial_temperature_k", "max_iterations", "relaxation", "temperature_tolerance_k",
                    "power_relative_tolerance"}, "iteration")
    initial = _number(options["initial_temperature_k"], "initial temperature")
    relaxation = _number(options["relaxation"], "relaxation")
    tolerance = _number(options["temperature_tolerance_k"], "temperature tolerance")
    power_tolerance = _number(options["power_relative_tolerance"], "power tolerance")
    limit = options["max_iterations"]
    _require(type(limit) is int and 1 <= limit <= 100, "Provide 1..100 iterations")
    _require(initial > 0 and 0 < relaxation <= 1, "Positive initial temperature and relaxation in (0,1] required")
    _require(1e-10 <= tolerance <= 1 and 1e-12 <= power_tolerance <= .01,
             "Temperature tolerance must be 1e-10..1 K; power tolerance 1e-12..0.01")
    base = request["base_request"]
    electrical, thermal, _, _, _, mesh_digest, data = coupled._prepare(base)
    ac_data = prepare_ac(electrical)
    cells = data["cells"]
    used = {cell["material_id"] for cell in cells}
    raw_laws = request["conductivity_laws"]
    _require(isinstance(raw_laws, list) and len(raw_laws) == len(used), "Exactly one law per used electrical material required")
    laws = {}
    for law in raw_laws:
        _keys(law, {"material_id", "reference_temperature_k", "temperature_coefficient_per_k", "temperature_range_k"}, "conductivity law")
        identity = law["material_id"]
        _require(isinstance(identity, str) and identity in used and identity not in laws, "Unknown or duplicate material law")
        reference = _number(law["reference_temperature_k"], "reference temperature")
        alpha = _number(law["temperature_coefficient_per_k"], "temperature coefficient")
        interval = law["temperature_range_k"]
        _require(isinstance(interval, list) and len(interval) == 2, "Explicit material temperature interval required")
        low, high = [_number(v, "temperature range") for v in interval]
        _require(0 < low < high and low <= reference <= high and low <= initial <= high,
                 "Reference and initial temperatures must lie in each positive material range")
        multipliers = [1 + alpha * (value - reference) for value in (low, high)]
        _require(all(math.isfinite(v) and v > 0 for v in multipliers), "Conductivity multiplier must be positive throughout supplied range")
        laws[identity] = (reference, alpha, low, high)
    # Upper work proxy includes dense AC, bounded thermal Krylov matvecs and
    # repeated geometry audits. Radiation, when supplied, reserves all Newton
    # iterations. This is a conservative admission budget, not a timing promise.
    n = len(data["xyz"])
    thermal_steps = min(100000, max(1000, 20 * n))
    nonlinear = 81 if data["radiation"] else 1
    work = limit * (ac_data[-1] + nonlinear * thermal_steps * data["matrix_entry_budget"] + 32 * len(cells)**2)
    _require(work <= _MAX_TOTAL_WORK, "Estimated repeated solve work exceeds one billion units", "resource_limit")
    # Reserve one final coupled result, material lineage/state and compact
    # history, never every intermediate field or thermal result.
    estimate = 12 * size + 4096 * len(cells) + 512 * n + 1024 * limit + 131072
    _require(estimate <= _MAX_RESULT_BYTES, "Estimated feedback response exceeds 16 MiB", "resource_limit")
    return base, cells, laws, n, mesh_digest, work


def _check_range(temperatures, cells, laws):
    _require(np.isfinite(temperatures).all(), "Nonfinite iterate temperature", "numerical_failure")
    for cell in cells:
        _, _, low, high = laws[cell["material_id"]]
        values = temperatures[cell["vertices"]]
        _require(np.all(values >= low) and np.all(values <= high),
                 f"Cell {cell['id']} nodal temperatures leave material law range", "temperature_range")


def _generated(base, cells, laws, temperatures):
    generated = deepcopy(base)
    electrical, thermal = generated["electrical_request"], generated["thermal_request"]
    originals = {m["id"]: m for m in electrical["materials"]}
    thermal_originals = {m["id"]: m for m in thermal["materials"]}
    electrical["materials"], thermal["materials"], states = [], [], []
    for index, cell in enumerate(cells):
        identity = f"feedback-cell-{index}"
        original = cell["material_id"]
        reference, alpha, _, _ = laws[original]
        mean = float(np.mean(temperatures[cell["vertices"]]))
        sigma = originals[original]["conductivity_s_m"] * (1 + alpha * (mean - reference))
        _require(math.isfinite(sigma) and sigma >= 0, "Unrepresentable cell conductivity", "numerical_failure")
        electrical["materials"].append({**originals[original], "id": identity, "conductivity_s_m": sigma})
        thermal["materials"].append({**thermal_originals[original], "id": identity})
        electrical["mesh"]["cells"][index]["material_id"] = identity
        thermal["mesh"]["cells"][index]["material_id"] = identity
        states.append({"cell_id": cell["id"], "original_material_id": original, "generated_material_id": identity,
                       "source_object_ids": cell["source_object_ids"], "mean_temperature_k": mean, "conductivity_s_m": sigma})
    return generated, states


def run_pdn_dielectric_feedback(request, *, cancel_check=None):
    """Return only a converged, range-admitted complete coupled fixed point."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise PdnDielectricFeedbackError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "Feedback execution cancelled", "cancelled")

    poll()
    frozen, size = _snapshot(request)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _run(frozen, size, poll, cancel_check)
    except PdnDielectricFeedbackError:
        raise
    except coupled.PdnDielectricThermalError as error:
        raise PdnDielectricFeedbackError(error.code.removeprefix("PDN_DIELECTRIC_THERMAL_"), str(error)) from error
    except PdnDielectricAcError as error:
        raise PdnDielectricFeedbackError(error.code.removeprefix("PDN_DIELECTRIC_AC_"), str(error)) from error
    except (AssemblyTetraThermalError, PdnElectrostaticError) as error:
        raise PdnDielectricFeedbackError("invalid_request", str(error)) from error
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError) as error:
        raise PdnDielectricFeedbackError("numerical_failure", f"Feedback numerical failure: {error}") from error


def _run(request, size, poll, cancel_check):
    base, cells, laws, n, mesh_digest, work = _prepare(request, size)
    options, history = request["iteration"], []
    operating = np.full(n, options["initial_temperature_k"], dtype=float)
    previous_power = None
    for iteration in range(1, options["max_iterations"] + 1):
        poll()
        _check_range(operating, cells, laws)
        generated, states = _generated(base, cells, laws, operating)
        last = coupled.run_pdn_dielectric_thermal(generated, cancel_check=cancel_check)
        poll()
        _require(isinstance(last, dict) and last.get("contract") == coupled.RESULT_CONTRACT
                 and last.get("model_status") == "experimental" and last.get("production_qualified") is False
                 and last.get("input_digest") == coupled._digest(generated),
                 "Invalid coupled result identity", "numerical_failure")
        thermal = last.get("thermal_result")
        raw = thermal.get("node_temperatures_k") if isinstance(thermal, dict) else None
        _require(isinstance(raw, list) and len(raw) == n and all(type(v) in (int, float) for v in raw),
                 "Invalid returned thermal state", "numerical_failure")
        target = np.array(raw, dtype=float)
        _check_range(target, cells, laws)
        power = _number(last.get("total_dielectric_power_w"), "returned dielectric power", "numerical_failure")
        _require(power >= 0, "Negative returned power", "numerical_failure")
        residual = float(np.max(np.abs(target - operating)))
        relative = None if previous_power is None else abs(power - previous_power) / max(power, previous_power, np.finfo(float).tiny)
        history.append({"iteration": iteration, "temperature_residual_k": residual, "power_relative_change": relative,
                        "total_dielectric_power_w": power, "minimum_temperature_k": float(target.min()),
                        "maximum_temperature_k": float(target.max())})
        if relative is not None and residual <= options["temperature_tolerance_k"] and relative <= options["power_relative_tolerance"]:
            result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                      "coupling_mode": "two_way_conductivity_temperature", "input_digest": coupled._digest(request),
                      "base_input_digest": coupled._digest(base), "original_mesh_digest": mesh_digest,
                      "generated_mesh_digest": last["mesh_digest"], "generated_input_digest": last["input_digest"],
                      "context_digest": last["context_digest"], "conductivity_laws": request["conductivity_laws"],
                      "iteration": options, "operating_temperature_k": operating.tolist(), "cell_material_state": states,
                      "last_coupled_result": last, "history": history,
                      "diagnostics": {"iterations": iteration, "temperature_residual_k": residual,
                                      "power_relative_change": relative, "estimated_total_work": work},
                      "limitations": ["Experimental steady fixed point; convergence does not prove uniqueness or physical stability",
                                      "Only scalar conductivity varies with cell mean nodal temperature; epsilon, loss tangent and thermal conductivity stay fixed",
                                      "Supplied material ranges are enforced on every cell node; no clipping or extrapolation",
                                      "Single coherent RMS tone and identical retained mesh; no transient or measured qualification",
                                      "Thermal cancellation is checked after its existing non-interruptible solve"]}
            try:
                encoded = json.dumps(result, allow_nan=False, separators=(",", ":")).encode()
            except (ValueError, TypeError, OverflowError) as error:
                raise PdnDielectricFeedbackError("numerical_failure", f"Invalid finite result: {error}") from error
            _require(len(encoded) <= _MAX_RESULT_BYTES, "Feedback response exceeds 16 MiB", "resource_limit")
            poll()
            return result
        previous_power = power
        operating = operating + options["relaxation"] * (target - operating)
    raise PdnDielectricFeedbackError("nonconvergence", "Raw temperature and power residuals did not converge within iteration limit")
