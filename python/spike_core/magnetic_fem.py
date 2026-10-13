# SPDX-License-Identifier: Apache-2.0
"""Experimental planar P1 magnetostatics; see docs/MAGNETIC_FEM.md."""
from __future__ import annotations

import math
import warnings

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve

MU0 = 4 * math.pi * 1e-7
MAX_NODES = 100_000
MAX_ELEMENTS = 200_000


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value, name, positive=False):
    _require(type(value) in (int, float), name + " must be a real number")
    value = float(value)
    _require(math.isfinite(value) and (not positive or value > 0),
             name + " must be finite" + (" and positive" if positive else ""))
    return value


class MagneticMaterial:
    """Convex isotropic magnetic constitutive potential, referenced to B=0."""

    def __init__(self, data):
        _require(isinstance(data, dict), "Material must be an object")
        _require(set(data) <= {"relative_permeability", "mu_r", "bh_curve", "remanence_t", "conductivity_s_m"},
                 "Unknown material fields")
        data = dict(data)
        if "mu_r" in data:
            _require("relative_permeability" not in data, "Duplicate permeability fields")
            data["relative_permeability"] = data.pop("mu_r")
        if "conductivity_s_m" in data:
            _require(_number(data["conductivity_s_m"], "conductivity_s_m") >= 0, "Conductivity must be nonnegative")
        _require(("relative_permeability" in data) != ("bh_curve" in data),
                 "Specify exactly one magnetic material law")
        self.br = np.asarray(data.get("remanence_t", [0.0, 0.0]), dtype=float)
        _require(self.br.shape == (2,) and np.all(np.isfinite(self.br)),
                 "remanence_t must contain two finite values")
        self.mu = None
        if "relative_permeability" in data:
            self.mu = MU0 * _number(data["relative_permeability"], "relative_permeability", True)
            _require(math.isfinite(self.mu) and self.mu > 0, "Permeability outside numerical range")
        else:
            _require(not np.any(self.br), "Nonlinear remanence is unsupported")
            curve = np.asarray(data["bh_curve"], dtype=float)
            _require(curve.ndim == 2 and curve.shape[1] == 2 and 2 <= len(curve) <= 4096,
                     "bh_curve requires 2..4096 [B_t, H_a_per_m] pairs")
            _require(np.all(np.isfinite(curve)) and np.all(curve[0] == 0)
                     and np.all(np.diff(curve, axis=0) > 0),
                     "B-H must begin at zero and increase strictly in both columns")
            self.b, self.h = curve.T
            self.slopes = np.diff(self.h) / np.diff(self.b)
            self.integrals = np.r_[0.0, np.cumsum(np.diff(self.b) * (self.h[1:] + self.h[:-1]) / 2)]
            _require(np.all(np.isfinite(self.slopes)) and np.all(np.isfinite(self.integrals)),
                     "B-H law exceeds numerical range")

    def evaluate(self, vectors):
        """Return H, dH/dB, potential density and Legendre coenergy density."""
        b = np.asarray(vectors, dtype=float)
        magnitude = np.linalg.norm(b, axis=1)
        identity = np.broadcast_to(np.eye(2), (len(b), 2, 2))
        if self.mu is not None:
            h = (b - self.br) / self.mu
            tangent = identity / self.mu
            energy = (0.5 * np.sum(b * b, axis=1) - b @ self.br) / self.mu
        else:
            _require(np.all(magnitude <= self.b[-1] * (1 + 1e-13)),
                     "Field exceeds supplied B-H range; extrapolation is forbidden")
            magnitude = np.minimum(magnitude, self.b[-1])
            segment = np.clip(np.searchsorted(self.b, magnitude, side="right") - 1,
                              0, len(self.slopes) - 1)
            delta = magnitude - self.b[segment]
            hmag = self.h[segment] + self.slopes[segment] * delta
            secant = np.divide(hmag, magnitude, out=np.full(len(b), self.slopes[0]),
                               where=magnitude > 0)
            unit = np.divide(b, magnitude[:, None], out=np.zeros_like(b),
                             where=magnitude[:, None] > 0)
            h = secant[:, None] * b
            tangent = (secant[:, None, None] * identity
                       + (self.slopes[segment] - secant)[:, None, None]
                       * unit[:, :, None] * unit[:, None, :])
            energy = self.integrals[segment] + self.h[segment] * delta + 0.5 * self.slopes[segment] * delta**2
        coenergy = np.sum(h * b, axis=1) - energy
        _require(all(np.all(np.isfinite(v)) for v in (h, tangent, energy, coenergy)),
                 "Constitutive evaluation exceeds numerical range")
        return h, tangent, energy, coenergy


class PlanarMagneticOperator:
    """Prepared mesh and material operator; no time-dependent state is retained."""

    def __init__(self, nodes_m, triangles, region_ids, materials, current_density_a_per_m2=None):
        self.nodes = np.asarray(nodes_m, dtype=float)
        raw = np.asarray(triangles)
        _require(self.nodes.ndim == 2 and self.nodes.shape[1] == 2
                 and 3 <= len(self.nodes) <= MAX_NODES and np.all(np.isfinite(self.nodes)),
                 "nodes_m must be finite bounded Nx2 SI coordinates")
        _require(raw.ndim == 2 and raw.shape[1] == 3 and 1 <= len(raw) <= MAX_ELEMENTS
                 and raw.dtype.kind in "iu", "triangles must be bounded integer Mx3 indices")
        _require(np.all(raw >= 0) and np.all(raw < len(self.nodes)), "Triangle index outside mesh")
        self.triangles = raw.astype(np.int64)
        _require(len(np.unique(np.sort(self.triangles, axis=1), axis=0)) == len(raw),
                 "Duplicate triangles")
        _require(len(np.unique(raw)) == len(self.nodes), "Unused nodes are not admitted")
        _require(isinstance(region_ids, (list, tuple)) and len(region_ids) == len(raw)
                 and all(isinstance(v, str) and v for v in region_ids),
                 "One nonempty string region ID per triangle is required")
        _require(isinstance(materials, dict) and set(region_ids) == set(materials),
                 "Materials must match mesh region IDs exactly")
        self.groups = {key: np.flatnonzero(np.asarray(region_ids) == key) for key in materials}
        self.materials = {key: MagneticMaterial(value) for key, value in materials.items()}
        self.region_ids = list(region_ids)
        p = self.nodes[self.triangles]
        edge1, edge2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
        determinant = edge1[:, 0] * edge2[:, 1] - edge1[:, 1] * edge2[:, 0]
        scale2 = np.maximum(np.sum(edge1**2, axis=1), np.sum(edge2**2, axis=1))
        _require(np.all(np.abs(determinant) > 1e-12 * scale2),
                 "Degenerate or excessively ill-conditioned triangles")
        self.areas = np.abs(determinant) / 2
        gradients = np.stack((np.stack((p[:, 1, 1]-p[:, 2, 1], p[:, 2, 0]-p[:, 1, 0]), axis=1),
                              np.stack((p[:, 2, 1]-p[:, 0, 1], p[:, 0, 0]-p[:, 2, 0]), axis=1),
                              np.stack((p[:, 0, 1]-p[:, 1, 1], p[:, 1, 0]-p[:, 0, 0]), axis=1)), axis=1)
        gradients /= determinant[:, None, None]
        self.curl = np.stack((gradients[:, :, 1], -gradients[:, :, 0]), axis=2)
        sources = {} if current_density_a_per_m2 is None else current_density_a_per_m2
        if isinstance(sources, dict):
            _require(set(sources) <= set(materials), "Unknown current region")
            self.jz = np.array([_number(sources.get(key, 0.0), "Jz") for key in region_ids])
        else:
            _require(isinstance(sources, (list, tuple)) and len(sources) == len(raw), "One Jz value per element required")
            self.jz = np.array([_number(value, "Jz") for value in sources])
        self.load = np.zeros(len(self.nodes))
        np.add.at(self.load, self.triangles.ravel(),
                  np.repeat(self.areas * self.jz / 3, 3))
        self.rows = np.repeat(self.triangles, 3, axis=1).ravel()
        self.cols = np.tile(self.triangles, (1, 3)).ravel()

    def evaluate(self, a):
        b = np.einsum("eik,ei->ek", self.curl, a[self.triangles])
        h, tangent = np.empty_like(b), np.empty((len(b), 2, 2))
        energy, coenergy = np.empty(len(b)), np.empty(len(b))
        for key, indices in self.groups.items():
            h[indices], tangent[indices], energy[indices], coenergy[indices] = self.materials[key].evaluate(b[indices])
        residual = -self.load.copy()
        np.add.at(residual, self.triangles.ravel(),
                  (self.areas[:, None] * np.einsum("eik,ek->ei", self.curl, h)).ravel())
        local = self.areas[:, None, None] * np.einsum("eik,ekl,ejl->eij", self.curl, tangent, self.curl)
        jacobian = coo_matrix((local.ravel(), (self.rows, self.cols)),
                              shape=(len(a), len(a))).tocsr()
        potential = float(self.areas @ energy - self.load @ a)
        _require(np.all(np.isfinite(residual)) and np.all(np.isfinite(jacobian.data))
                 and math.isfinite(potential), "Magnetic operator exceeds numerical range")
        return residual, jacobian, b, h, energy, coenergy, potential


def solve_magnetostatic(*, nodes_m, triangles, region_ids, materials, stack_depth_m,
                       dirichlet_a_wb_per_m, current_density_a_per_m2=None,
                       relative_tolerance=1e-9, absolute_tolerance_a=1e-10,
                       maximum_iterations=60):
    """Solve planar Az with explicit essential boundaries; raises on nonconvergence."""
    depth = _number(stack_depth_m, "stack_depth_m", True)
    rtol = _number(relative_tolerance, "relative_tolerance", True)
    atol = _number(absolute_tolerance_a, "absolute_tolerance_a", True)
    _require(rtol <= 0.01, "relative_tolerance must be <= 0.01")
    _require(type(maximum_iterations) is int and 1 <= maximum_iterations <= 200,
             "maximum_iterations must be 1..200")
    op = PlanarMagneticOperator(nodes_m, triangles, region_ids, materials, current_density_a_per_m2)
    n = len(op.nodes)
    boundary = dirichlet_a_wb_per_m
    _require(isinstance(boundary, dict) and boundary, "Explicit Dirichlet values are required")
    _require(all(type(i) is int and 0 <= i < n for i in boundary),
             "Dirichlet keys must be valid integer node indices")
    a = np.zeros(n)
    for i, value in boundary.items():
        a[i] = _number(value, "Dirichlet Az")
    fixed = np.array(sorted(boundary), dtype=int)
    free = np.setdiff1d(np.arange(n), fixed)
    # Every connected mesh component requires its own essential gauge.
    from scipy.sparse.csgraph import connected_components
    graph = coo_matrix((np.ones(len(op.rows)), (op.rows, op.cols)), shape=(n, n)).tocsr()
    count, labels = connected_components(graph, directed=False)
    _require(set(labels[fixed]) == set(range(count)), "Each connected component requires a Dirichlet gauge")
    # A harmonic linear start avoids artificial boundary-layer B-H overshoot
    # caused by zero interior values with nonzero prescribed boundary values.
    if len(free):
        local = op.areas[:, None, None] * np.einsum("eik,ejk->eij", op.curl, op.curl)
        laplace = coo_matrix((local.ravel(), (op.rows, op.cols)), shape=(n, n)).tocsr()
        with warnings.catch_warnings():
            warnings.simplefilter("error", MatrixRankWarning)
            a[free] = spsolve(laplace[free][:, free], -(laplace @ a)[free])
        _require(np.all(np.isfinite(a)), "Initial harmonic solve failed")
    state = op.evaluate(a)
    initial = float(np.linalg.norm(state[0][free]))
    threshold = atol + rtol * initial
    history = [initial]
    converged = initial <= threshold
    for _ in range(maximum_iterations):
        if converged:
            break
        residual, tangent = state[:2]
        with warnings.catch_warnings():
            warnings.simplefilter("error", MatrixRankWarning)
            step = spsolve(tangent[free][:, free], -residual[free])
        _require(np.all(np.isfinite(step)), "Newton linear solve failed")
        descent = float(residual[free] @ step)
        _require(descent < 0, "Newton direction is not a descent direction")
        accepted = False
        alpha = 1.0
        for _ in range(48):
            candidate = a.copy()
            candidate[free] += alpha * step
            try:
                trial = op.evaluate(candidate)
            except ValueError as exc:
                if "B-H range" not in str(exc):
                    raise
                alpha *= 0.5
                continue
            trial_norm = float(np.linalg.norm(trial[0][free]))
            rounding = 64 * np.finfo(float).eps * max(abs(state[6]), abs(trial[6]), 1e-30)
            if (trial[6] <= state[6] + 1e-4 * alpha * descent + rounding
                    or trial_norm <= threshold):
                a, state, accepted = candidate, trial, True
                break
            alpha *= 0.5
        _require(accepted, "Magnetic Newton line search failed (check B-H range and conditioning)")
        history.append(float(np.linalg.norm(state[0][free])))
        converged = history[-1] <= threshold
    _require(converged, "Magnetic Newton did not converge")
    residual, _, b, h, energy, coenergy, _ = state
    total_energy = float(depth * (op.areas @ energy))
    total_coenergy = float(depth * (op.areas @ coenergy))
    _require(math.isfinite(total_energy) and math.isfinite(total_coenergy),
             "Integrated magnetic energy exceeds numerical range")
    return {
        "contract": "spike/planar-magnetostatic-result/v1",
        "model_status": "experimental", "production_qualified": False,
        "formulation": "planar_2d_p1_az", "stack_depth_m": depth,
        "potential_a_wb_per_m": a.tolist(), "element_b_t": b.tolist(),
        "element_h_a_per_m": h.tolist(), "element_area_m2": op.areas.tolist(),
        "element_region_ids": op.region_ids,
        "element_magnetic_energy_density_j_per_m3": energy.tolist(),
        "element_magnetic_coenergy_density_j_per_m3": coenergy.tolist(),
        "magnetic_energy_j": total_energy, "magnetic_coenergy_j": total_coenergy,
        "dirichlet_reaction_a": {int(i): float(residual[i]) for i in fixed},
        "convergence": {"converged": True, "iterations": len(history)-1,
                        "residual_norm_a": history[-1], "residual_limit_a": threshold,
                        "residual_history_a": history},
        "joule_loss_w": None, "joule_loss_status": "not_solved",
        "energy_reference": "constitutive potential w(B=0)=0; ideal PM potential may be negative",
        "limitations": [
            "Planar magnetostatics with supplied mesh and piecewise constant sources; no axisymmetry or 3D end effects.",
            "No eddy currents, hysteresis, thermal feedback, motion, force or torque extraction.",
            "Remanence is supported only with linear recoil permeability; total PM-system stored energy is not established.",
            "Residual convergence does not establish mesh, air-boundary or measured accuracy.",
        ],
    }



def solve_eddy_current_step(*, nodes_m, triangles, region_ids, materials, stack_depth_m,
                           dirichlet_a_wb_per_m, previous_a_wb_per_m, time_step_s,
                           current_density_a_per_m2=None, relative_tolerance=1e-9,
                           absolute_tolerance_a=1e-9, maximum_iterations=60):
    """Backward Euler on fixed conductors, zero net induced current per region.

    Each conductive region is one electrically isolated axial current circuit.
    This is not a moving-conductor or arbitrary 3D electric-potential model.
    """
    from scipy.sparse import bmat, diags
    from scipy.sparse.csgraph import connected_components
    depth = _number(stack_depth_m, "stack_depth_m", True)
    dt = _number(time_step_s, "time_step_s", True)
    rtol = _number(relative_tolerance, "relative_tolerance", True)
    atol = _number(absolute_tolerance_a, "absolute_tolerance_a", True)
    _require(rtol <= 0.01, "relative_tolerance must be <= 0.01")
    _require(type(maximum_iterations) is int and 1 <= maximum_iterations <= 200,
             "maximum_iterations must be 1..200")
    op = PlanarMagneticOperator(nodes_m, triangles, region_ids, materials, current_density_a_per_m2)
    n, ne = len(op.nodes), len(op.triangles)
    old = np.asarray(previous_a_wb_per_m, dtype=float)
    _require(old.shape == (n,) and np.all(np.isfinite(old)), "Previous Az must match mesh nodes")
    boundary = dirichlet_a_wb_per_m
    _require(isinstance(boundary, dict) and boundary
             and all(type(i) is int and 0 <= i < n for i in boundary),
             "Explicit valid integer-index Dirichlet values are required")
    fixed = np.array(sorted(boundary), dtype=int)
    free = np.setdiff1d(np.arange(n), fixed)
    graph = coo_matrix((np.ones(len(op.rows)), (op.rows, op.cols)), shape=(n, n)).tocsr()
    count, labels = connected_components(graph, directed=False)
    _require(set(labels[fixed]) == set(range(count)), "Each connected component requires a Dirichlet gauge")
    sigma = np.array([_number(materials[key].get("conductivity_s_m", 0.0), "conductivity_s_m")
                      for key in region_ids])
    conducting = [key for key in op.groups if materials[key].get("conductivity_s_m", 0) > 0]
    _require(conducting and len(conducting) <= 1024, "Need 1..1024 conductive circuit regions")
    # Each region is electrically one isolated conductor: reject disconnected
    # region meshes rather than silently joining separate pieces through Ez.
    for key in conducting:
        tri = op.triangles[op.groups[key]]
        vertices = np.unique(tri)
        rows = np.repeat(tri, 3, axis=1).ravel()
        cols = np.tile(tri, (1, 3)).ravel()
        subgraph = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n)).tocsr()
        parts, _ = connected_components(subgraph[vertices][:, vertices], directed=False)
        _require(parts == 1, "Disconnected conductors require separate region IDs")
    region_index = {key: i for i, key in enumerate(conducting)}
    local_mass = sigma[:, None, None] * op.areas[:, None, None] * (np.ones((3, 3)) + np.eye(3)) / 12
    mass = coo_matrix((local_mass.ravel(), (op.rows, op.cols)), shape=(n, n)).tocsr()
    cr, cc, cv = [], [], []
    conductance = np.zeros(len(conducting))
    for key, k in region_index.items():
        elements = op.groups[key]
        weights = sigma[elements] * op.areas[elements]
        conductance[k] = weights.sum()
        cr.extend(op.triangles[elements].ravel())
        cc.extend([k] * (3 * len(elements)))
        cv.extend(np.repeat(weights / 3, 3))
    coupling = coo_matrix((cv, (cr, cc)), shape=(n, len(conducting))).tocsr()
    _require(np.all(np.isfinite(conductance)) and np.all(conductance > 0)
             and np.all(np.isfinite(mass.data)), "Conductivity assembly exceeds numerical range")
    a = old.copy()
    for i, value in boundary.items():
        a[i] = _number(value, "Dirichlet Az")
    eta = np.asarray(coupling.T @ (a-old)) / conductance
    previous = op.evaluate(old)

    def evaluate(current, offset):
        field = op.evaluate(current)
        delta = current-old
        electric = mass @ delta - coupling @ offset
        constraint = -coupling.T @ delta + conductance * offset
        residual_a = field[0] + electric / dt
        residual = np.r_[residual_a[free], constraint/dt]
        potential = field[6] + float(delta @ (mass @ delta)
                    - 2 * delta @ (coupling @ offset) + conductance @ offset**2) / (2*dt)
        _require(np.all(np.isfinite(residual)) and math.isfinite(potential),
                 "Eddy step exceeds numerical range")
        return field, residual_a, residual, potential

    state = evaluate(a, eta)
    threshold = atol + rtol * float(np.linalg.norm(state[2]))
    history = [float(np.linalg.norm(state[2]))]
    for _ in range(maximum_iterations):
        if history[-1] <= threshold:
            break
        matrix = bmat([[(state[0][1]+mass/dt)[free][:, free], -coupling[free]/dt],
                       [-coupling[free].T/dt, diags(conductance/dt)]], format="csr")
        with warnings.catch_warnings():
            warnings.simplefilter("error", MatrixRankWarning)
            step = spsolve(matrix, -state[2])
        _require(np.all(np.isfinite(step)), "Eddy Newton linear solve failed")
        descent = float(state[2] @ step)
        _require(descent < 0, "Eddy Newton direction is not a descent direction")
        alpha, accepted = 1.0, False
        for _ in range(48):
            trial_a, trial_eta = a.copy(), eta + alpha*step[len(free):]
            trial_a[free] += alpha*step[:len(free)]
            try:
                trial = evaluate(trial_a, trial_eta)
            except ValueError as exc:
                if "B-H range" not in str(exc):
                    raise
                alpha *= 0.5
                continue
            rounding = 64*np.finfo(float).eps*max(abs(state[3]),abs(trial[3]),1e-30)
            if (trial[3] <= state[3]+1e-4*alpha*descent+rounding
                    or np.linalg.norm(trial[2]) <= threshold):
                a, eta, state, accepted = trial_a, trial_eta, trial, True
                break
            alpha *= 0.5
        _require(accepted, "Eddy Newton line search failed")
        history.append(float(np.linalg.norm(state[2])))
    _require(history[-1] <= threshold, "Eddy Newton did not converge")
    field, reactions = state[:2]
    ez_offset = {key: float(eta[k]/dt) for key,k in region_index.items()}
    element_e = -(a-old)[op.triangles]/dt
    for key,k in region_index.items():
        element_e[op.groups[key]] += eta[k]/dt
    joule = depth*sigma*op.areas*(np.sum(element_e**2,axis=1)+np.sum(element_e,axis=1)**2)/12
    induced_j = sigma*element_e.mean(axis=1)
    net_current = {key:float(op.areas[op.groups[key]] @ induced_j[op.groups[key]]) for key in conducting}
    change = depth*float(op.areas @ (field[4]-previous[4]))
    bregman = depth*float(op.areas @ (previous[4]-field[4]
                    + np.sum(field[3]*(field[2]-previous[2]),axis=1)))
    input_work = depth*float((a-old)@op.load+(a-old)[fixed]@reactions[fixed])
    dissipation = float(joule.sum())*dt
    balance = input_work-change-dissipation-bregman
    _require(np.all(np.isfinite(joule)) and np.all(joule >= 0)
             and all(math.isfinite(v) for v in (change,bregman,input_work,balance)),
             "Eddy loss or energy audit exceeds numerical range")
    total_energy = depth*float(op.areas @ field[4])
    total_coenergy = depth*float(op.areas @ field[5])
    _require(math.isfinite(total_energy) and math.isfinite(total_coenergy),
             "Integrated eddy magnetic energy exceeds numerical range")
    return {
        "contract":"spike/planar-eddy-step-result/v1", "model_status":"experimental",
        "production_qualified":False, "formulation":"planar_2d_p1_az_backward_euler",
        "potential_a_wb_per_m":a.tolist(), "element_b_t":field[2].tolist(),
        "element_h_a_per_m":field[3].tolist(), "element_area_m2":op.areas.tolist(),
        "element_region_ids":op.region_ids, "stack_depth_m":depth, "time_step_s":dt,
        "element_magnetic_energy_density_j_per_m3":field[4].tolist(),
        "element_magnetic_coenergy_density_j_per_m3":field[5].tolist(),
        "magnetic_energy_j":total_energy,
        "magnetic_coenergy_j":total_coenergy,
        "element_electric_field_z_nodal_v_per_m":element_e.tolist(),
        "element_induced_current_density_z_a_per_m2":induced_j.tolist(),
        "region_electric_offset_v_per_m":ez_offset, "region_net_induced_current_a":net_current,
        "element_joule_loss_w":joule.tolist(), "joule_loss_w":float(joule.sum()),
        "joule_loss_status":"solved_fixed_conductor",
        "energy_audit":{"magnetic_energy_change_j":change, "joule_energy_j":dissipation,
                        "backward_euler_numerical_dissipation_j":bregman,
                        "source_and_boundary_work_j":input_work, "balance_residual_j":balance},
        "convergence":{"converged":True,"iterations":len(history)-1,
                       "residual_norm_a":history[-1],"residual_limit_a":threshold,
                       "residual_history_a":history},
        "limitations":["Fixed mesh and conductors only; no v cross B or moving-interface terms.",
                       "Each conductive region is one isolated axial circuit with zero net induced current.",
                       "Piecewise-constant conductivity; no thermal, hysteresis or 3D end-current solution.",
                       "Backward Euler numerical dissipation is reported separately from Joule heat.",
                       "Mesh, timestep, boundary convergence and independent measurement remain required."],
    }
