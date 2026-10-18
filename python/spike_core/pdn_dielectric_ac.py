# SPDX-License-Identifier: Apache-2.0
"""Bounded experimental complex P1 fields in a retained finite dielectric.

Original weak-form derivation, independently authored without external source:
with RMS exp(+j*w*t) phasors, gamma = sigma I + w tan(delta) epsilon + j*w
epsilon. Integrating div(gamma grad(phi))=0 gives the complex symmetric local
matrix volume*grad(N)*gamma*grad(N). Electrode reactions are currents into
the dielectric. Unit-electrode fields P give Y=P.conj().T K P, including
the reference current. Independently integrating E.conj().T gamma E tests
the admittance power form V.conj().T I, with no factor 1/2 for RMS phasors.
This form has positive imaginary part for a capacitor; conventional complex
power V.T I.conj() is its conjugate and has identical real dissipation.
Spatially varying complex
gamma is solved at every requested frequency; lossless fields are not reused.

This is an electroquasistatic finite insulating-boundary model, not full-wave
PCB extraction. No geometry, electrode, return path, dispersion or measurement
qualification is inferred. Knowledgeable numerical review remains necessary.
"""
from __future__ import annotations

import json
import math
from typing import Callable

import numpy as np
from scipy.sparse import coo_matrix

from .assembly_tetra_thermal_validation import AssemblyTetraThermalError
from .pdn_electrostatic import (
    PdnElectrostaticError, REQUEST_CONTRACT as ELECTROSTATIC_CONTRACT,
    _admit, _digest, _electrode_reactions, _snapshot,
)
from .pdn_network import PdnNetworkError, _solve_linear

REQUEST_CONTRACT = "spike/pdn-dielectric-ac-request/v1"
RESULT_CONTRACT = "spike/pdn-dielectric-ac-result/v1"
_MAX_FREE = 128
_MAX_NODES = 1000
_MAX_CELLS = 2000
_MAX_FREQUENCIES = 128
_MAX_DENSE_WORK = 100_000_000
_MAX_RESULT_BYTES = 16 * 1024 * 1024


class PdnDielectricAcError(ValueError):
    """Structured refusal without partially published frequency responses."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = "PDN_DIELECTRIC_AC_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise PdnDielectricAcError(code, message)


def _number(value, name, *, positive=False):
    _require(type(value) in (int, float), f"{name} must be a finite scalar")
    try:
        number = float(value)
    except OverflowError as error:
        raise PdnDielectricAcError("invalid_request", f"{name} is not representable") from error
    _require(math.isfinite(number) and (number > 0 if positive else number >= 0),
             f"{name} must be {'positive' if positive else 'nonnegative'} and finite")
    return number


def _pairs(array):
    values = np.asarray(array)
    if values.ndim == 0:
        return {"real": float(values.real), "imag": float(values.imag)}
    return [_pairs(row) for row in values]


def _finite_norm(array, label, *, positive=False):
    value = float(np.linalg.norm(array))
    _require(math.isfinite(value) and (not positive or value > 0),
             f"Unrepresentable {label} norm", "numerical_failure")
    return value


def _prepare(request):
    fields = {"contract", "mesh", "materials", "electrodes", "reference_electrode",
              "outer_boundary", "context_digest", "frequencies_hz"}
    _require(isinstance(request, dict) and set(request) == fields, "Unknown or missing dielectric AC fields")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported dielectric AC contract")
    frequencies = request["frequencies_hz"]
    _require(isinstance(frequencies, list) and 1 <= len(frequencies) <= _MAX_FREQUENCIES,
             "Provide 1..128 supplied frequencies", "resource_limit")
    frequencies = [_number(f, "frequency_hz", positive=True) for f in frequencies]
    _require(all(b > a for a, b in zip(frequencies, frequencies[1:])), "Frequencies must increase strictly")
    _require(all(math.isfinite(2 * math.pi * f) for f in frequencies), "Nonfinite angular frequency")
    mesh = request["mesh"]
    _require(isinstance(mesh, dict) and isinstance(mesh.get("vertices"), list)
             and isinstance(mesh.get("cells"), list), "Explicit retained dielectric mesh required")
    _require(4 <= len(mesh["vertices"]) <= _MAX_NODES and 1 <= len(mesh["cells"]) <= _MAX_CELLS,
             "Dielectric AC mesh exceeds 1000 nodes/2000 cells", "resource_limit")
    materials = request["materials"]
    _require(isinstance(materials, list) and 1 <= len(materials) <= _MAX_CELLS,
             "Invalid bounded material count", "resource_limit")
    translated, loss = [], {}
    for material in materials:
        _require(isinstance(material, dict) and set(material) == {
            "id", "permittivity_f_m", "conductivity_s_m", "loss_tangent"}, "Invalid dielectric material fields")
        identity = material["id"]
        _require(isinstance(identity, str) and identity not in loss, "Invalid or duplicate material identity")
        loss[identity] = (_number(material["conductivity_s_m"], "conductivity_s_m"),
                          _number(material["loss_tangent"], "loss_tangent"))
        translated.append({"id": identity, "permittivity_f_m": material["permittivity_f_m"]})
    geometry_request = {key: value for key, value in request.items() if key != "frequencies_hz"}
    geometry_request.update(contract=ELECTROSTATIC_CONTRACT, materials=translated)
    data = _admit(geometry_request)
    electrodes = request["electrodes"]
    reference = next(e for e in electrodes if e["id"] == request["reference_electrode"])
    signals = [e for e in electrodes if e is not reference]
    fixed = np.array(sorted({v for e in electrodes for v in e["vertices"]}), dtype=int)
    free = np.setdiff1d(np.arange(len(data["xyz"])), fixed)
    _require(len(free) <= _MAX_FREE, "Dielectric AC exceeds 128 free unknowns", "resource_limit")
    work = len(frequencies) * max(1, len(free))**3
    _require(work <= _MAX_DENSE_WORK, "Dielectric AC dense work exceeds 100 million cubic units", "resource_limit")
    # Every complex scalar is exported with named real/imaginary fields.
    # Reserve 96 bytes per value plus per-cell/list/diagnostic and lineage
    # overhead. Each electrode lineage may repeat source identities, so also
    # reserve an input-sized metadata block per electrode plus top-level
    # metadata copies. A final exact JSON-size gate complements this bound.
    values = len(signals) * (len(data["xyz"]) + 3 * len(data["cells"]) + len(electrodes) + 2 * len(signals))
    envelope = (len(frequencies) * (96 * values + 32 * len(data["cells"]) + 8192)
                + (len(electrodes) + 3) * len(json.dumps(request, ensure_ascii=False).encode("utf-8")) + 65536)
    _require(envelope <= _MAX_RESULT_BYTES, "Estimated dielectric AC response exceeds 16 MiB", "resource_limit")
    return data, loss, frequencies, reference, signals, fixed, free, work


def extract_pdn_dielectric_ac(request, *, cancel_check: Callable[[], bool] | None = None):
    """Return complex terminal admittance, P1 fields and checked power evidence.

    Every basis sets one signal electrode to 1 V RMS and all other electrodes
    to zero. Positive electrode currents enter the retained dielectric. Nodes
    follow input electrode order excluding the explicit reference. The caller's
    request is snapshotted; cancellation/failure returns no partial result.
    """
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise PdnDielectricAcError("cancel_check_failed", f"Cancellation check failed: {error}") from error
            _require(not cancelled, "Dielectric AC execution cancelled", "cancelled")

    poll()
    try:
        frozen = _snapshot(request)
        poll()
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _extract(frozen, poll)
    except PdnDielectricAcError:
        raise
    except (PdnElectrostaticError, AssemblyTetraThermalError) as error:
        raise PdnDielectricAcError("invalid_request", f"Dielectric geometry/material admission failed: {error}") from error
    except PdnNetworkError as error:
        code = "conditioning_failure" if error.code == "PDN_SINGULAR_NETWORK" else "numerical_failure"
        raise PdnDielectricAcError(code, str(error)) from error
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError) as error:
        raise PdnDielectricAcError("numerical_failure", f"Dielectric AC numerical failure: {error}") from error


def _extract(request, poll):
    data, loss, frequencies, reference, signals, fixed, free, work = _prepare(request)
    poll()
    n, cells = len(data["xyz"]), data["cells"]
    electrodes = request["electrodes"]
    signal_rows = [electrodes.index(e) for e in signals]
    ac = []
    for frequency in frequencies:
        poll()
        omega = 2 * math.pi * frequency
        gamma = {identity: sigma * np.eye(3) + (omega * tangent + 1j * omega) * data["tensors"][identity]
                 for identity, (sigma, tangent) in loss.items()}
        rows, columns, coefficients = [], [], []
        for index, (cell, (volume, gradients)) in enumerate(zip(cells, data["geometry"])):
            if index % 64 == 0:
                poll()
            local = volume * gradients @ gamma[cell["material_id"]] @ gradients.T
            for i, row in enumerate(cell["vertices"]):
                for j, column in enumerate(cell["vertices"]):
                    rows.append(row); columns.append(column); coefficients.append(local[i, j])
        matrix = coo_matrix((coefficients, (rows, columns)), shape=(n, n)).tocsr()
        _require(np.isfinite(matrix.data).all(), "Nonfinite dielectric operator", "numerical_failure")
        _finite_norm(matrix.data, "dielectric operator", positive=True)
        potentials = np.zeros((n, len(signals)), dtype=complex)
        for index, electrode in enumerate(signals):
            potentials[electrode["vertices"], index] = 1.
        residual, backward_error, condition = 0., 0., 1.
        if len(free):
            operator = matrix[free][:, free].toarray()
            rhs = -(matrix[free][:, fixed] @ potentials[fixed])
            rhs_norm = _finite_norm(rhs, "free-node excitation")
            poll()
            solution, backward_error, condition = _solve_linear(operator, rhs, f"dielectric AC {frequency} Hz")
            potentials[free] = solution
            residual = _finite_norm(operator @ solution - rhs, "free-node residual") / max(rhs_norm, np.finfo(float).tiny)
            _require(math.isfinite(residual) and residual <= 1e-9,
                     "Dielectric free-node residual exceeds tolerance", "numerical_failure")
        currents, reactions = _electrode_reactions(matrix, potentials, electrodes)
        _require(np.isfinite(currents).all() and np.isfinite(reactions).all(),
                 "Nonfinite electrode currents", "numerical_failure")
        admittance = currents[signal_rows]
        fields = np.empty((len(cells), 3, len(signals)), dtype=complex)
        power_matrix = np.zeros_like(admittance)
        for index, (cell, (volume, gradients)) in enumerate(zip(cells, data["geometry"])):
            if index % 64 == 0:
                poll()
            field = -gradients.T @ potentials[cell["vertices"]]
            fields[index] = field
            power_matrix += volume * field.conj().T @ gamma[cell["material_id"]] @ field
        scale = _finite_norm(admittance, "admittance", positive=True)
        power_error = _finite_norm(admittance - power_matrix, "power identity") / scale
        reciprocity = _finite_norm(admittance - admittance.T, "reciprocity") / scale
        balance = float(np.max(np.abs(np.sum(currents, axis=0))) /
                        max(float(np.max(np.sum(np.abs(currents), axis=0))), np.finfo(float).tiny))
        _require(power_error <= 1e-9, "Electrode and integrated field complex power disagree", "numerical_failure")
        _require(reciprocity <= 1e-9, "Dielectric reciprocity check failed", "numerical_failure")
        _require(balance <= 1e-9, "Electrode current conservation failed", "numerical_failure")
        dissipative = (admittance + admittance.conj().T) / 2
        minimum = float(np.linalg.eigvalsh(dissipative)[0])
        tolerance = 256 * np.finfo(float).eps * scale + 1e-10 * _finite_norm(dissipative, "dissipative admittance")
        _require(all(math.isfinite(value) for value in (minimum, tolerance, backward_error, condition)),
                 "Nonfinite dielectric numerical diagnostics", "numerical_failure")
        _require(minimum >= -tolerance, "Nonpassive dielectric terminal response", "nonpassive_response")
        ac.append({"frequency_hz": frequency, "admittance_s": _pairs(admittance),
                   "basis_node_potential_v": _pairs(potentials),
                   "basis_cell_electric_field_v_m": _pairs(fields),
                   "electrode_basis_current_a": {e["id"]: _pairs(currents[i]) for i, e in enumerate(electrodes)},
                   "field_power_matrix_s": _pairs(power_matrix),
                   "diagnostics": {"free_relative_residual": residual, "relative_backward_error": backward_error,
                                   "equilibrated_free_condition_number": condition,
                                   "relative_power_identity_error": power_error, "relative_reciprocity_error": reciprocity,
                                   "relative_current_balance_error": balance,
                                   "minimum_dissipative_eigenvalue_s": minimum, "passivity_tolerance_s": tolerance}})
    poll()
    lineage = [{**electrode, "dielectric_source_object_ids": sorted({
        source for cell in cells if set(electrode["vertices"]) & set(cell["vertices"])
        for source in cell["source_object_ids"]})} for electrode in electrodes]
    result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
              "model": "retained_dielectric_p1_complex_admittance", "nodes": [e["node"] for e in signals],
              "electrodes": electrodes, "reference_electrode": reference, "outer_boundary": "insulating",
              "electrode_lineage": lineage, "mesh_lineage": request["mesh"]["object_map"],
              "context_digest": request["context_digest"], "mesh_digest": _digest(request["mesh"]),
              "input_digest": _digest(request), "ac": ac,
              "diagnostics": {"nodes": n, "cells": len(cells), "free_nodes": len(free),
                              "estimated_dense_cubic_work": work,
                              "max_element_jacobian_condition": data["max_condition"]},
              "limitations": ["Finite retained conforming dielectric and insulating outer boundary only; no open/infinite boundary",
                              "Electroquasistatic RMS exp(+j*omega*t); no magnetic induction, propagation or radiation",
                              "Supplied constant permittivity, isotropic conductivity and loss tangent only; no inferred material dispersion",
                              "Zero-thickness equipotential electrode sheets; no electrode resistance or automatic PCB extraction",
                              "P1 geometry-specific refinement and independent/measured correlation remain required; no production qualification"]}
    try:
        encoded = json.dumps(result, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, OverflowError) as error:
        raise PdnDielectricAcError("numerical_failure", f"Result is not finite JSON: {error}") from error
    _require(len(encoded) <= _MAX_RESULT_BYTES, "Dielectric AC response exceeds 16 MiB", "resource_limit")
    return result
