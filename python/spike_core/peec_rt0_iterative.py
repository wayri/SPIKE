# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Experimental matrix-free trace solve for the existing RT0 DC discretization.

Independent algebraic elimination, not a new physical model: M q = 1 u-lambda,
1.T q=s-Cj imply q=b(s-Cj)-H lambda, u=a(s-Cj)+b.T lambda,
where a=(1.T M^-1 1)^-1, b=a M^-1 1, H=M^-1-b b.T/a.
Assembling faces gives S lambda+G j=f and G.T lambda-D j=-h.
Eliminating barrels yields (S+G D^-1 G.T)lambda=f-G D^-1 h.
S is positive semidefinite; D=Rvia+C.T diag(a) C is positive definite.
One trace gauge makes the connected-component Schur positive definite.
Only local 3x3 inverses, a capped barrel block and a <=192-order coarse
preconditioner block are factored.

Coordinates and material units are inherited from peec_conforming_dc. M,D,a
are ohms, H,S are siemens, G,b,C dimensionless, traces/u volts, q/j amperes.
Symmetric multilevel or Jacobi CG may converge slowly on graded meshes;
iteration exhaustion is failure, never a partial accepted result. The public
assembly is still used (including its bounded sparse R/B storage), but there
is no sparse factorization or dense global Schur. This is not an OS RAM/time
limit: checks are cooperative before/after assembly and on each CG iteration.
The host must enforce process-tree resource limits for untrusted work.

This clean-room implementation uses the repository's RT0 definition and
direct-solver oracle; no external implementation was consulted or copied.
It is not registered with a production plugin and does not qualify geometry,
contact refinement, magnetic/capacitive extraction or Marble AC accuracy.
The optional multilevel preconditioner improves manufactured coupons, but
has not solved the graded Marble .125 mm/depth-6 mesh within its budgets;
that mesh includes local mass condition numbers above 2e7. No automatic
fallback raises its storage caps or accepts its unconverged approximation.
"""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic

import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.sparse import bmat, coo_matrix, diags, eye
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import LinearOperator, cg

from .hybrid_mesh import HybridMesh
from .peec_conforming_dc import assemble_conforming_dc


def _multilevel_preconditioner(planar, coupling, solve_d, *, check_budget,
                              max_levels=12, max_nonzeros=4000000, coarse_limit=192):
    """Bounded symmetric smoothed aggregation, independently derived.

    Galerkin restriction retains the exact low-rank via term. Symmetric Jacobi
    pre/post smoothing uses a rigorous absolute row-sum spectral upper bound
    of diag(A)^-1 A, including the barrel correction, so the V-cycle is SPD.
    Coarse Cholesky is admitted only below coarse_limit, never sparse LU.
    Geometric contact errors are untouched. Storage caps are work-admission
    bounds, not allocator/OS memory guarantees.
    """
    levels, stored = [], 0
    for _ in range(max_levels):
        check_budget()
        n = planar.shape[0]
        stored += planar.nnz+coupling.nnz
        if stored > max_nonzeros:
            raise ValueError("RT0 multilevel nonzero budget exceeded")
        if n <= coarse_limit:
            dense = planar.toarray()+coupling@solve_d(coupling.T.toarray())
            coarse = cho_factor(np.asarray(dense), lower=True, check_finite=True)
            break
        diagonal = planar.diagonal().copy()
        # Bounded row blocks: no n-by-n dense correction is formed.
        for begin in range(0, n, coarse_limit):
            block = coupling[begin:begin+coarse_limit].toarray()
            diagonal[begin:begin+len(block)] += np.einsum("ij,ji->i", block, solve_d(block.T))
        if not np.isfinite(diagonal).all() or np.any(diagonal <= 0):
            raise ValueError("RT0 multilevel diagonal is not positive finite")
        groups = np.full(n, -1, dtype=np.int64)
        count = 0
        planar_diagonal = planar.diagonal()
        # Aggregates follow strong planar edges, never disconnected sheets.
        for i in range(n):
            if groups[i] >= 0:
                continue
            start, end = planar.indptr[i:i+2]
            neighbours = planar.indices[start:end]
            strength = np.abs(planar.data[start:end])/np.sqrt(planar_diagonal[i]*planar_diagonal[neighbours])
            strength[neighbours == i] = 0
            candidates = np.flatnonzero((groups[neighbours] < 0)
                & (strength >= .5*max(float(strength.max()), 1e-30)))
            chosen = candidates[np.argsort(strength[candidates])[-4:]]
            groups[i] = count
            groups[neighbours[chosen]] = count
            count += 1
        if count >= n:
            raise ValueError("RT0 multilevel coarsening stalled")
        tentative = coo_matrix((np.ones(n), (np.arange(n), groups)), shape=(n, count)).tocsr()
        bound = float(np.max(np.asarray(abs(planar).sum(axis=1)).ravel()/planar_diagonal))
        prolong = ((eye(n, format="csr")-(0.8/bound)*diags(1/planar_diagonal)@planar)@tentative).tocsr()
        # Limit interpolation width, not operator accuracy. Preserve each
        # row sum so sheet constants survive truncation on ungauged sheets.
        for row in range(n):
            lo, hi = prolong.indptr[row:row+2]
            if hi-lo > 4:
                values = prolong.data[lo:hi]
                total = float(values.sum())
                keep = np.argsort(np.abs(values))[-4:]
                kept = float(values[keep].sum())
                values[np.setdiff1d(np.arange(hi-lo), keep)] = 0
                if abs(kept) > 1e-15:
                    values *= total/kept
        prolong.eliminate_zeros()
        stored += prolong.nnz
        # Bound intermediate multiplication work before allocating Galerkin fill.
        # For A@P, each nonzero A[i,k] visits P[k,:]. Rowwise A/P counts
        # would undercount graded matrices with uneven column occupancy.
        work = int(np.dot(np.bincount(planar.indices, minlength=n),
                          np.diff(prolong.indptr)))
        if stored > max_nonzeros or work > 8*max_nonzeros:
            raise ValueError(f"RT0 multilevel Galerkin work budget exceeded: n={n}, stored={stored}, work={work}")
        intermediate = planar@prolong
        work = int(np.dot(np.diff(prolong.indptr), np.diff(intermediate.indptr)))
        if work > 8*max_nonzeros:
            raise ValueError(f"RT0 multilevel Galerkin work budget exceeded: n={n}, work={work}")
        row_bound = np.asarray(abs(planar).sum(axis=1)).ravel()
        if coupling.shape[1]:
            inverse_d_abs = abs(solve_d(np.eye(coupling.shape[1])))
            row_bound += abs(coupling)@(inverse_d_abs@np.asarray(abs(coupling).sum(axis=0)).ravel())
        damping = 0.8/float(np.max(row_bound/diagonal))
        levels.append((damping/diagonal, prolong, planar, coupling))
        if int(np.dot(np.diff(prolong.indptr), np.diff(coupling.indptr))) > 8*max_nonzeros:
            raise ValueError("RT0 multilevel coupling work budget exceeded")
        planar = (prolong.T@intermediate).tocsr()
        coupling = (prolong.T@coupling).tocsr()
    else:
        raise ValueError("RT0 multilevel depth budget exceeded")

    def cycle(rhs, index):
        if index == len(levels):
            return cho_solve(coarse, rhs, check_finite=False)
        weight, prolong, sparse, lowrank = levels[index]

        def apply_level(value):
            return sparse@value+lowrank@solve_d(lowrank.T@value)

        result = weight*rhs
        result += weight*(rhs-apply_level(result))
        result += prolong@cycle(prolong.T@(rhs-apply_level(result)), index+1)
        result += weight*(rhs-apply_level(result))
        result += weight*(rhs-apply_level(result))
        return result

    return lambda rhs: cycle(rhs, 0), {"preconditioner": "symmetric_smoothed_aggregation",
                   "preconditioner_levels": len(levels)+1,
                   "preconditioner_stored_nonzeros": stored,
                   "preconditioner_coarse_order": n}


def solve_iterative_conforming_dc(
    mesh: HybridMesh, source_node: int, load_node: int, *,
    max_unknowns: int = 150000, max_triangles: int = 150000,
    max_vias: int = 256, max_iterations: int = 10000,
    relative_tolerance: float = 1e-12, timeout_s: float = 120.0,
    cancelled: Callable[[], bool] | None = None, preconditioner_kind: str = "jacobi",
) -> dict:
    """Solve one-ampere finite-area-contact DC; reject unconverged outputs."""
    for name, value, upper in (("max_vias", max_vias, 1024),
                               ("max_iterations", max_iterations, 100000)):
        if type(value) is not int or not 1 <= value <= upper:
            raise ValueError(f"RT0 {name} budget must be an integer in 1..{upper}")
    if (not np.isfinite(relative_tolerance) or not 1e-14 <= relative_tolerance <= 1e-10
            or not np.isfinite(timeout_s) or not 0 < timeout_s <= 86400):
        raise ValueError("RT0 tolerance or cooperative timeout is invalid")
    if cancelled is not None and not callable(cancelled):
        raise ValueError("RT0 cancellation must be callable")
    if preconditioner_kind not in ("jacobi", "multilevel"):
        raise ValueError("RT0 preconditioner must be jacobi or multilevel")
    if source_node == load_node:
        raise ValueError("RT0 source and load must be distinct finite contacts")
    start = monotonic()

    def check_budget():
        if cancelled is not None and cancelled():
            raise ValueError("RT0 iterative solve cancelled")
        if monotonic()-start > timeout_s:
            raise ValueError("RT0 iterative cooperative timeout exceeded")

    check_budget()
    system = assemble_conforming_dc(mesh, max_unknowns=max_unknowns,
                                   hybridized=True, max_triangles=max_triangles)
    check_budget()
    if source_node not in system.contacts or load_node not in system.contacts:
        raise ValueError("RT0 port terminals must resolve to fixed finite contacts")
    nt, ne = len(system.triangles_mm), system.planar_edge_count
    graph = bmat([[None, abs(system.incidence)],
                  [abs(system.incidence.T), None]], format="csr")
    _, labels = connected_components(graph, directed=False)
    source, sw = system.contacts[source_node]
    sink, tw = system.contacts[load_node]
    component = labels[source[0]]
    if np.any(labels[np.r_[source, sink]] != component):
        raise ValueError("RT0 port contacts are disconnected")
    cells = np.flatnonzero(labels[:nt] == component)
    traces = np.flatnonzero(labels[nt:nt+ne] == component)
    vias = np.flatnonzero(labels[nt+ne:] == component)
    nv, ntrace = len(vias), len(traces)
    if nv > max_vias:
        raise ValueError(f"RT0 dense barrel-block budget exceeded: {nv} > {max_vias}")
    del graph, labels
    injection = np.zeros(nt)
    injection[source] += sw
    injection[sink] -= tw
    injection = injection[cells]
    if abs(float(injection.sum())) > 1e-12:
        raise ValueError("RT0 source and sink do not balance")
    remap = np.full(ne, -1, dtype=np.int64)
    remap[traces] = np.arange(ntrace)
    edges = remap[system.local_edges[cells]]
    if np.any(edges < 0):
        raise ValueError("RT0 component has unresolved traces")
    masses = system.local_resistance[cells]
    inverse = np.linalg.inv(masses)
    v = inverse.sum(axis=2)
    a = 1/v.sum(axis=1)
    b = v*a[:, None]
    local_h = inverse-v[:, :, None]*v[:, None, :]*a[:, None, None]
    for i in range(3):
        local_h[:, i, i] = -sum(local_h[:, i, j] for j in range(3) if j != i)
    c = system.incidence[cells][:, ne+vias].tocsr()
    via_r = system.resistance.diagonal()[ne+vias]
    # F/G are sparse incidence-like maps, not the dense global Schur.
    f_operator = coo_matrix((b.ravel(), (edges.ravel(),
        np.repeat(np.arange(len(cells)), 3))), shape=(ntrace, len(cells))).tocsr()
    g = (f_operator@c).tocsr()
    f = np.asarray(f_operator@injection)
    h = np.asarray(c.T@(a*injection))
    if nv:
        d = (diags(via_r)+c.T@diags(a)@c).toarray()
        try:
            factor = cho_factor(d, lower=True, check_finite=True)
        except (ValueError, np.linalg.LinAlgError) as error:
            raise ValueError("RT0 barrel block is not finite positive definite") from error

        def solve_d(rhs):
            return cho_solve(factor, rhs, check_finite=False)
    else:
        d = np.empty((0, 0))

        def solve_d(rhs):
            return np.zeros_like(rhs)

    def scatter(local):
        return np.bincount(edges.ravel(), weights=local.ravel(), minlength=ntrace)

    def apply_full(trace):
        local = np.einsum("tij,tj->ti", local_h, trace[edges])
        return scatter(local)+g@solve_d(g.T@trace)

    # A fixed trace is a voltage gauge only. Its current balance is checked
    # independently below; dropping its equation does not permit leakage.
    rhs = (f-g@solve_d(h))[1:]

    def matvec(value):
        return apply_full(np.r_[0.0, value])[1:]

    # Positive diagonal of S alone is a valid (inexact) SPD preconditioner.
    # Avoid forming diag(G D^-1 G.T), which needs potentially large temporaries.
    diagonal = scatter(np.diagonal(local_h, axis1=1, axis2=2))[1:]
    if not np.isfinite(diagonal).all() or np.any(diagonal <= 0):
        raise ValueError("RT0 trace preconditioner is not finite positive definite")
    operator = LinearOperator((ntrace-1, ntrace-1), matvec=matvec, dtype=float)
    preconditioner_info = {"preconditioner": "jacobi"}
    precondition = lambda x: x/diagonal
    if preconditioner_kind == "multilevel":
        rows = np.repeat(edges, 3, axis=1).ravel()
        cols = np.tile(edges, (1, 3)).ravel()
        planar = coo_matrix((local_h.ravel(), (rows, cols)), shape=(ntrace, ntrace)).tocsr()[1:, 1:]
        precondition, preconditioner_info = _multilevel_preconditioner(
            planar, g[1:], solve_d, check_budget=check_budget)
    preconditioner = LinearOperator(operator.shape, matvec=precondition, dtype=float)
    iterations = 0

    def callback(_):
        nonlocal iterations
        iterations += 1
        check_budget()

    check_budget()
    solution, status = cg(operator, rhs, M=preconditioner, rtol=relative_tolerance,
                          atol=0.0, maxiter=max_iterations, callback=callback)
    check_budget()
    if status != 0 or not np.isfinite(solution).all():
        remaining = float(np.linalg.norm(matvec(solution)-rhs)/max(np.linalg.norm(rhs), 1e-30))
        raise ValueError(f"RT0 iterative solve failed convergence: status={status}, iterations={iterations}, residual={remaining:g}")
    trace = np.r_[0.0, solution]
    barrel = solve_d(g.T@trace+h)
    local_source = injection-c@barrel
    flux = b*local_source[:, None]-np.einsum("tij,tj->ti", local_h, trace[edges])
    potential = a*local_source+np.einsum("ti,ti->t", b, trace[edges])
    residual = float(np.linalg.norm(matvec(solution)-rhs)/max(np.linalg.norm(rhs), 1e-30))
    cell_kcl = float(np.max(np.abs(flux.sum(axis=1)+c@barrel-injection)))
    face_kcl = float(np.max(np.abs(scatter(flux))))
    barrel_error = float(np.max(np.abs(via_r*barrel-c.T@potential))) if nv else 0.0
    resistance = float(injection@potential)
    loss = float(np.einsum("ti,tij,tj->", flux, masses, flux)+via_r@(barrel**2))
    energy_error = abs(loss-resistance)/max(abs(resistance), 1e-30)
    metrics = (residual, cell_kcl, face_kcl, barrel_error, resistance, loss, energy_error)
    if (not np.isfinite(metrics).all() or residual > 1e-9 or cell_kcl > 1e-8
            or face_kcl > 1e-8 or barrel_error > 1e-8*max(abs(resistance), 1e-30)
            or resistance <= 0 or energy_error > 1e-7):
        raise ValueError(f"RT0 iterative checks failed: residual={residual:g}, "
                         f"cell KCL={cell_kcl:g}, face KCL={face_kcl:g}, energy={energy_error:g}")
    return {"model_status": "experimental", "production_qualified": False,
        "method": "conforming_triangle_RT0_matrix_free_trace_CG_DC",
        "contact_model": "uniform finite-area current injection; area-average potential",
        "resistance_ohm": resistance, "dissipation_w_at_one_ampere": loss,
        "relative_residual": residual, "maximum_cell_kcl_error_a": cell_kcl,
        "maximum_face_kcl_error_a": face_kcl, "maximum_barrel_voltage_error_v": barrel_error,
        "relative_energy_error": energy_error, "iterations": iterations,
        "triangle_count": len(cells), "global_trace_count": ntrace,
        "via_current_unknown_count": nv, "dense_factor_order": nv,
        "max_iterations": max_iterations, "relative_tolerance": relative_tolerance,
        **preconditioner_info,
        "elapsed_s": monotonic()-start,
        "limitations": ["experimental DC only; no PEEC L/C or field qualification",
            "geometry/contact refinement requires independent convergence",
            "multilevel/Jacobi CG can stagnate; failure does not produce an accepted result",
            "assembly and single iterations are not preemptible; host must enforce OS resource limits"]}
