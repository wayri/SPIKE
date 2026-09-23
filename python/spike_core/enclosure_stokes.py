# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Bounded 3-D staggered-grid creeping flow in closed, voxelized enclosures.

Solves -mu Laplacian(u) + grad(p) = f, div(u) = 0. Fluid-fluid
faces carry normal velocity; all other faces are impermeable. Missing
tangential stencil neighbors use odd ghost reflection (no slip). Geometry
is the supplied staircase voxel mask, not a fitted curved CAD boundary.
"""
from collections.abc import Mapping
import math
import warnings
import numpy as np
from scipy.sparse import lil_matrix, bmat
from scipy.sparse.linalg import spsolve, MatrixRankWarning

CONTRACT = "spike/enclosure-stokes/v1"
RESULT_CONTRACT = "spike/enclosure-stokes-result/v1"
MAX_CELLS = 4096


class EnclosureFlowError(ValueError):
    pass


def _number(value, name):
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError()
        return float(value)
    except (ValueError, OverflowError):
        raise EnclosureFlowError(f"{name} must be finite and positive") from None


def _parse(request):
    keys = {"contract", "shape", "spacing_m", "fluid_mask", "body_force_n_m3", "dynamic_viscosity_pa_s", "density_kg_m3"}
    if not isinstance(request, Mapping) or set(request) != keys or request["contract"] != CONTRACT:
        raise EnclosureFlowError("Invalid enclosure Stokes contract or fields")
    shape = request["shape"]
    if not isinstance(shape, (list, tuple)) or len(shape) != 3 or any(type(n) is not int or not 1 <= n <= 64 for n in shape) or math.prod(shape) > MAX_CELLS:
        raise EnclosureFlowError("shape requires three integers and at most 4096 cells")
    spacing = request["spacing_m"]
    if not isinstance(spacing, (list, tuple)) or len(spacing) != 3:
        raise EnclosureFlowError("spacing_m requires three values")
    spacing = np.array([_number(v, "spacing_m") for v in spacing])
    mu = _number(request["dynamic_viscosity_pa_s"], "viscosity")
    rho = _number(request["density_kg_m3"], "density")
    mask = np.asarray(request["fluid_mask"])
    if mask.shape != tuple(shape) or mask.dtype.kind != "b" or not mask.any():
        raise EnclosureFlowError("fluid_mask must be a nonempty Boolean voxel array")
    raw = np.asarray(request["body_force_n_m3"])
    if raw.shape != tuple(shape) + (3,) or raw.dtype.kind not in "iuf":
        raise EnclosureFlowError("body force requires a real three-vector per voxel")
    force = raw.astype(float)
    if not np.isfinite(force).all():
        raise EnclosureFlowError("body force must be finite")
    return tuple(shape), spacing, mask, force, mu, rho


def _assemble(shape, h, mask, force, mu, cancel_check):
    cells = [tuple(c) for c in np.argwhere(mask)]
    ids = {c: i for i, c in enumerate(cells)}
    faces = []
    for c in cells:
        for axis in range(3):
            other = list(c)
            other[axis] += 1
            other = tuple(other)
            if other in ids:
                faces.append((axis, c, other))
    face_ids = {(a, c): i for i, (a, c, _) in enumerate(faces)}
    n = len(faces)
    a = lil_matrix((n, n))
    d = lil_matrix((len(cells), n))
    rhs = np.zeros(n)
    adjacency = [[] for _ in cells]
    for i, (axis, c, other) in enumerate(faces):
        if cancel_check and cancel_check():
            raise InterruptedError()
        rhs[i] = (force[c][axis] + force[other][axis]) / 2
        d[ids[c], i] = 1 / h[axis]
        d[ids[other], i] = -1 / h[axis]
        adjacency[ids[c]].append(ids[other])
        adjacency[ids[other]].append(ids[c])
        for direction in range(3):
            coefficient = mu / h[direction] ** 2
            for sign in (-1, 1):
                neighbor = list(c)
                neighbor[direction] += sign
                j = face_ids.get((axis, tuple(neighbor)))
                if j is not None:
                    a[i, i] += coefficient
                    a[i, j] -= coefficient
                else:
                    a[i, i] += coefficient * (1 if direction == axis else 2)
    gauges, seen = [], set()
    for i in range(len(cells)):
        if i in seen:
            continue
        gauges.append(i)
        todo = [i]
        seen.add(i)
        while todo:
            for j in adjacency[todo.pop()]:
                if j not in seen:
                    seen.add(j)
                    todo.append(j)
    return cells, faces, a.tocsr(), d.tocsr(), rhs, gauges


def solve_enclosure_stokes(request, *, cancel_check=None):
    """Return JSON-compatible fields only after residual and creeping-flow admission.

    Closed stationary walls only: no inlet/outlet, turbulence, inertia,
    buoyancy feedback, thermal transport or moving walls. A spatially varying
    volumetric force may drive recirculation. Pressure gauge per component.
    Reynolds admission bounds reconstructed discrete velocity, not unresolved
    continuum peaks. Sparse factorization cannot be cancelled mid-call.
    """
    result = {"contract": RESULT_CONTRACT, "production_qualified": False,
              "scope": "closed_voxel_constant_property_creeping_flow"}
    try:
        if cancel_check and cancel_check():
            raise InterruptedError()
        shape, h, mask, force, mu, rho = _parse(request)
        with np.errstate(over="raise", divide="raise", invalid="raise"):
            cells, faces, a, d, rhs, gauges = _assemble(shape, h, mask, force, mu, cancel_check)
            alpha = mu / float(h.min()) ** 2
            length = float(h.min())
            active = [i for i in range(len(cells)) if i not in set(gauges)]
            dr = d[active] * length
            matrix = bmat([[a / alpha, -dr.T], [-dr, None]], format="csc")
            if matrix.shape[0]:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", MatrixRankWarning)
                    solution = spsolve(matrix, np.r_[rhs / alpha, np.zeros(len(active))])
            else:
                solution = np.zeros(0)
            if not np.isfinite(solution).all():
                raise EnclosureFlowError("Nonfinite flow solution")
            velocity = solution[:len(faces)]
            pressure = np.zeros(len(cells))
            pressure[active] = solution[len(faces):] * alpha * length
            momentum = a @ velocity - d.T @ pressure - rhs
            divergence = d @ velocity
            residual = float(np.linalg.norm(momentum) / max(np.linalg.norm(rhs), 1e-30))
            divergence_max = float(np.max(np.abs(divergence), initial=0))
            speed = float(np.max(np.abs(velocity), initial=0))
            reynolds = rho * math.sqrt(3) * speed * float(np.max(np.array(shape) * h)) / mu
            work = float(rhs @ velocity * np.prod(h))
            dissipation = float(velocity @ (a @ velocity) * np.prod(h))
            if not all(math.isfinite(v) for v in (residual, divergence_max, reynolds, work, dissipation)):
                raise EnclosureFlowError("Nonfinite flow diagnostics")
            velocity_scale = max(speed, float(np.max(np.abs(rhs), initial=0)) / alpha, 1e-30)
            if residual > 1e-8 or divergence_max > 1e-8 * velocity_scale / length:
                raise EnclosureFlowError("Flow residual or incompressibility check failed")
            if reynolds > .1:
                raise EnclosureFlowError("Reynolds bound exceeds 0.1: inertia requires a different solver")
            face_fields = []
            for axis in range(3):
                fs = list(shape)
                fs[axis] += 1
                face_fields.append(np.zeros(fs))
            for value, (axis, c, _) in zip(velocity, faces):
                index = list(c)
                index[axis] += 1
                face_fields[axis][tuple(index)] = value
            p = np.zeros(shape)
            for c, value in zip(cells, pressure):
                p[c] = value
        if cancel_check and cancel_check():
            raise InterruptedError()
        result.update(status="completed", fields={"face_velocity_m_s": [v.tolist() for v in face_fields],
            "pressure_pa": p.tolist()}, diagnostics={"momentum_relative_residual": residual,
            "maximum_divergence_s_inv": divergence_max, "reynolds_upper_bound": reynolds,
            "force_work_w": work, "viscous_dissipation_w": dissipation,
            "fluid_cells": len(cells), "velocity_unknowns": len(faces), "fluid_components": len(gauges)})
    except InterruptedError:
        result.update(status="cancelled", issues=[{"code": "CANCELLED", "message": "Enclosure flow cancelled"}])
    except (EnclosureFlowError, ValueError, TypeError, ArithmeticError, MatrixRankWarning) as exc:
        result.update(status="blocked", issues=[{"code": "ENCLOSURE_FLOW_REJECTED", "message": str(exc)}])
    return result
