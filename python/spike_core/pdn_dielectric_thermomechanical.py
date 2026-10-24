# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Compose owned AC-loss, heat and elasticity solvers without new numerical laws.

Single RMS tone, steady temperatures, same indexed mesh and one-way small-strain
response only. Caller-provided field results/temperatures are never accepted.
Legacy child digest profiles are preserved rather than silently rewritten.
"""
from __future__ import annotations

import hashlib
import json
import math

from .assembly_tetra_structural import RESULT_CONTRACT as STRUCTURAL_RESULT, run_assembly_tetra_structural
from .assembly_tetra_thermal import RESULT_CONTRACT as THERMAL_RESULT
from .pdn_dielectric_thermal import RESULT_CONTRACT as ELECTROTHERMAL_RESULT, run_pdn_dielectric_thermal

REQUEST_CONTRACT = "spike/pdn-dielectric-thermomechanical-request/v1"
RESULT_CONTRACT = "spike/pdn-dielectric-thermomechanical-result/v1"
_REQUEST_LIMIT = 8 * 1024**2
_RESULT_LIMIT = 16 * 1024**2


class PdnDielectricThermomechanicalError(ValueError):
    """Stable failure code; no partial coupled success is published."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "PDN_DIELECTRIC_THERMOMECHANICAL_" + code


def _require(condition, message, code="INVALID_REQUEST"):
    if not condition:
        raise PdnDielectricThermomechanicalError(code, message)


def _snapshot(value, limit):
    chunks, size = [], 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False, allow_nan=False).iterencode(value):
            size += len(chunk.encode("utf-8"))
            _require(size <= limit, "Coupled JSON resource limit exceeded", "RESOURCE_LIMIT")
            chunks.append(chunk)
        return json.loads("".join(chunks))
    except PdnDielectricThermomechanicalError:
        raise
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        raise PdnDielectricThermomechanicalError("INVALID_JSON", "Finite JSON required") from error


def _digest(value, *, ascii_escaped=False):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=ascii_escaped, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_pdn_dielectric_thermomechanical(request, *, cancel_check=None):
    """Rerun the field/heat solvers, then use their actual temperature in mechanics.

    Internal experimental API, no worker/UI registration or production promotion.
    Existing child solver resource/numerical gates remain authoritative. Thermal
    callback cancellation is checked around its blocking solve, not within it.
    """
    _require(cancel_check is None or callable(cancel_check), "Cancellation check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise PdnDielectricThermomechanicalError("CANCEL_CHECK_FAILED", str(error)) from error
            _require(not cancelled, "Coupled execution cancelled", "CANCELLED")

    poll()
    raw = _snapshot(request, _REQUEST_LIMIT)
    _require(isinstance(raw, dict) and set(raw) == {
        "contract", "electrothermal_request", "structural_request"}
        and raw["contract"] == REQUEST_CONTRACT, "Exact coupled request fields required")
    electrothermal, structural = raw["electrothermal_request"], raw["structural_request"]
    _require(isinstance(electrothermal, dict) and isinstance(structural, dict), "Solver requests required")
    electrical, thermal = electrothermal.get("electrical_request"), electrothermal.get("thermal_request")
    _require(isinstance(electrical, dict) and isinstance(thermal, dict), "Electrical/thermal requests required")
    mesh = structural.get("mesh")
    _require(isinstance(mesh, dict) and mesh == electrical.get("mesh") and mesh == thermal.get("mesh"),
             "Identical indexed mesh, units, materials and ownership required", "MESH_MISMATCH")
    # Equality alone allows 1 == True and 1 == 1.0: preserve exact serialized identity too.
    mesh_digest = _digest(mesh)
    _require(all(_digest(child["mesh"]) == mesh_digest for child in (electrical, thermal)),
             "Canonical mesh identity differs", "MESH_MISMATCH")
    _require("nodal_temperatures_k" in structural and structural["nodal_temperatures_k"] is None,
             "Temperatures must originate in the executed heat solve", "TEMPERATURE_SOURCE")
    context = electrical.get("context_digest")
    _require(isinstance(context, str) and context == structural.get("context_digest"),
             "Electrical and structural context identities differ", "CONTEXT_MISMATCH")
    original_structural_digest = _digest(structural)
    phase = "STRUCTURAL_PREFLIGHT"
    try:
        # Existing admission also rejects unsupported properties, rigid modes and
        # excessive work before the field/thermal execution; no preflight fields transfer.
        run_assembly_tetra_structural(structural, cancel_check=cancel_check)
        poll()
        phase = "ELECTROTHERMAL_FAILURE"
        coupled = run_pdn_dielectric_thermal(electrothermal, cancel_check=cancel_check)
        poll()
        _require(isinstance(coupled, dict) and coupled.get("contract") == ELECTROTHERMAL_RESULT
                 and coupled.get("model_status") == "experimental"
                 and coupled.get("production_qualified") is False
                 and coupled.get("input_digest") == _digest(electrothermal, ascii_escaped=True)
                 and coupled.get("mesh_digest") == _digest(mesh, ascii_escaped=True)
                 and coupled.get("context_digest") == context,
                 "Electrothermal result identity/status mismatch", "RESULT_IDENTITY")
        heat = coupled.get("thermal_result")
        _require(isinstance(heat, dict) and heat.get("contract") == THERMAL_RESULT
                 and heat.get("production_qualified") is False and heat.get("model_status") == "experimental",
                 "Thermal result status mismatch", "RESULT_IDENTITY")
        temperatures = heat.get("node_temperatures_k")
        _require(isinstance(temperatures, list) and len(temperatures) == len(mesh["vertices"])
                 and all(type(t) in (int, float) and math.isfinite(t) and t >= 0 for t in temperatures),
                 "Thermal result must cover finite nonnegative Kelvin nodes", "TEMPERATURE_SOURCE")
        generated = {**structural, "nodal_temperatures_k": {str(i): t for i, t in enumerate(temperatures)}}
        phase = "STRUCTURAL_FAILURE"
        mechanics = run_assembly_tetra_structural(generated, cancel_check=cancel_check)
        poll()
        _require(isinstance(mechanics, dict) and mechanics.get("contract") == STRUCTURAL_RESULT
                 and mechanics.get("production_qualified") is False and mechanics.get("model_status") == "experimental"
                 and mechanics.get("mesh_digest") == mesh_digest and mechanics.get("context_digest") == context
                 and mechanics.get("input_digest") == _digest(generated)
                 and mechanics.get("nodal_temperatures_k") == generated["nodal_temperatures_k"],
                 "Structural result identity/status mismatch", "RESULT_IDENTITY")
        result = {
            "contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
            "coupling_mode": "one_way_single_rms_tone_to_steady_heat_to_small_strain_elasticity",
            "input_digest": _digest(raw), "mesh_digest": mesh_digest, "context_digest": context,
            "original_structural_input_digest": original_structural_digest,
            "generated_structural_input_digest": _digest(generated),
            "transferred_temperature_digest": _digest(generated["nodal_temperatures_k"]),
            "digest_profiles": {"parent_and_structural": "sorted_compact_json_utf8_unescaped_unicode",
                                "legacy_electrothermal": "sorted_compact_json_utf8_ascii_escaped_unicode"},
            "electrothermal": coupled, "structural": mechanics,
            "limitations": [
                "Finite electroquasistatic dielectric at one coherent RMS tone; not arbitrary PCB/SI extraction",
                "No deformation/material feedback, transient, airflow, contact, plasticity, fatigue or dynamics",
                "Exactly identical retained mesh; supplied context is not independent CAD authentication",
                "Child solver gates and bounds unchanged; thermal callback cancellation is between subsolves",
                "Synthetic verification and coupled output do not establish measured or production qualification"],
        }
        poll()
        return _snapshot(result, _RESULT_LIMIT)
    except PdnDielectricThermomechanicalError:
        raise
    except (ValueError, RuntimeError, ArithmeticError) as error:
        source_code = str(getattr(error, "code", ""))
        for code in ("CANCEL_CHECK_FAILED", "CANCELLED", "RESOURCE_LIMIT"):
            if source_code.endswith("_" + code):
                raise PdnDielectricThermomechanicalError(code, str(error)) from error
        raise PdnDielectricThermomechanicalError(phase, str(error)) from error
