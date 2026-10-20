# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Experimental conservative CR/P0 tetrahedral creeping-flow kernel.

The constitutive operator is the BROKEN VECTOR LAPLACIAN, not symmetric
Newtonian stress. Natural data are (mu grad(u)-p I)n, called pseudo-traction.
See docs/validation/CFD_TETRA_STOKES_20261021.md for derivation and limits.
"""
from collections.abc import Mapping
import math
import numbers
import time

import numpy as np
from scipy.sparse import bmat, coo_matrix, diags
from scipy.sparse.linalg import LinearOperator, minres, onenormest, splu

from .cfd_tetra_mesh import admit_cfd_tetra_mesh


CONTRACT = "spike/cfd-tetra-stokes/v1"
RESULT_CONTRACT = "spike/cfd-tetra-stokes-result/v1"
MAX_REYNOLDS = .1
MAX_CONDITION = 1e10
MAX_FACTOR_NONZEROS = 8_000_000
MAX_DIRECT_UNKNOWNS = 4000
MAX_ITERATIONS_PER_INVERSE = 15_000
_KEYS = {"contract", "mesh", "dynamic_viscosity_pa_s", "density_kg_m3",
         "body_force_n_m3", "boundary_conditions", "controls"}


class CfdTetraStokesError(ValueError):
    """Unsupported, inconsistent, unresolved, or unrepresentable input."""


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise CfdTetraStokesError(f"{name} must be a positive finite real number")
    value = float(value)
    if not math.isfinite(value) or value <= 0.:
        raise CfdTetraStokesError(f"{name} must be a positive finite real number")
    return value


def _array(raw, shape, name):
    array = np.asarray(raw)
    if array.shape != shape or array.dtype.kind not in "iuf":
        raise CfdTetraStokesError(f"{name} must be a real numeric array with shape {shape}")
    result = array.astype(float, copy=True)
    if not np.isfinite(result).all():
        raise CfdTetraStokesError(f"{name} must be finite")
    return result


def _norm(values):
    values = np.asarray(values)
    scale = float(np.max(np.abs(values), initial=0.))
    return float(np.multiply(scale, np.sqrt(np.sum((values/scale)**2)))) if scale else 0.


def _power(left, right):
    return float(np.sum(np.multiply(left, right)))


def _relative(numerator, denominator):
    return numerator/denominator if denominator else (0. if numerator == 0. else math.inf)


def _boundary(mesh, raw):
    patches = mesh["boundary_patches"]
    if not isinstance(raw, Mapping) or set(raw) != set(patches):
        raise CfdTetraStokesError("every boundary patch requires exactly one condition")
    count = len(mesh["face_vertices"])
    prescribed = np.zeros(count, dtype=bool)
    velocity = np.zeros((count, 3))
    traction = np.zeros((count, 3))
    outlets = np.zeros(count, dtype=bool)
    for name, indices in patches.items():
        condition = raw[name]
        if not isinstance(condition, Mapping):
            raise CfdTetraStokesError(f"boundary condition {name} must be a mapping")
        if condition.get("kind") == "velocity_dirichlet":
            if set(condition) != {"kind", "face_average_velocity_m_s"}:
                raise CfdTetraStokesError("velocity Dirichlet condition has unknown or missing options")
            velocity[indices] = _array(condition["face_average_velocity_m_s"],
                                       (len(indices), 3), "face_average_velocity_m_s")
            prescribed[indices] = True
        elif condition.get("kind") == "pseudo_traction":
            if (set(condition) != {"kind", "face_average_pseudo_traction_pa", "reject_backflow"}
                    or condition["reject_backflow"] is not True):
                raise CfdTetraStokesError("pseudo-traction requires explicit reject_backflow=True")
            traction[indices] = _array(condition["face_average_pseudo_traction_pa"],
                                       (len(indices), 3), "face_average_pseudo_traction_pa")
            outlets[indices] = True
        else:
            raise CfdTetraStokesError("only velocity_dirichlet and pseudo_traction conditions are supported")
    gauges = []
    boundary = mesh["face_owners"][:, 1] == -1
    for component in mesh["components"]:
        surface = boundary & np.isin(mesh["face_owners"][:, 0], component)
        if not np.any(surface & prescribed):
            raise CfdTetraStokesError("each fluid component needs velocity Dirichlet anchoring")
        if not np.any(surface & outlets):
            gauges.append(int(component[0]))
            flux = np.sum(velocity[surface] * mesh["face_normals"][surface], axis=1)
            total = abs(_power(mesh["face_areas"][surface], flux))
            speed = max((math.hypot(*u) for u in velocity[surface]), default=0.)
            scale = float(np.multiply(speed, np.sum(mesh["face_areas"][surface])))
            if _relative(total, scale) > 1e-10:
                raise CfdTetraStokesError("closed component has incompatible prescribed net flux")
    return prescribed, velocity, traction, outlets, gauges


def _assemble(mesh, force, mu, check):
    face_count = len(mesh["face_vertices"])
    cells = len(mesh["cells"])
    rows, cols, values = [], [], []
    brows, bcols, bvalues = [], [], []
    load = np.zeros((face_count, 3))
    gradients = -3. * mesh["barycentric_gradients"]
    volumes = mesh["cell_volumes"]
    for c, faces in enumerate(mesh["cell_faces"]):
        if c % 64 == 0:
            check()
        gram = np.sum(gradients[c, :, None, :] * gradients[c, None, :, :], axis=2)
        stiffness = np.multiply(np.multiply(mu, volumes[c]), gram)
        local_force = np.multiply(volumes[c] / 4., force[c])
        for i, face in enumerate(faces):
            load[face] += local_force
            for d in range(3):
                brows.append(c)
                bcols.append(3*int(face)+d)
                # This is also V*grad(phi_i)_d, by the divergence theorem.
                bvalues.append(mesh["face_areas"][face] * mesh["cell_outward_normals"][c, i, d])
                for j, other in enumerate(faces):
                    rows.append(3*int(face)+d)
                    cols.append(3*int(other)+d)
                    values.append(stiffness[i, j])
    k = coo_matrix((values, (rows, cols)), shape=(3*face_count, 3*face_count)).tocsr()
    b = coo_matrix((bvalues, (brows, bcols)), shape=(cells, 3*face_count)).tocsr()
    k.eliminate_zeros()
    b.eliminate_zeros()
    if not np.isfinite(k.data).all() or not np.isfinite(b.data).all():
        raise CfdTetraStokesError("assembled operators are not finite")
    return k, b, load.ravel(), gradients


def _block_preconditioner(velocity_block, pressure_diagonal, gauge_count, check):
    """Apply a sparse-LU approximation to an SPD block inverse, not Cholesky."""
    nu = velocity_block.shape[0]
    pressure_diagonal = np.asarray(pressure_diagonal)
    if nu % 3 or np.any(pressure_diagonal <= 0.) or not np.isfinite(pressure_diagonal).all():
        raise CfdTetraStokesError("invalid positive block preconditioner")
    scalar = velocity_block[::3, ::3].tocsc()
    skew = scalar-scalar.T
    if np.max(np.abs(skew.data), initial=0.) > 64.*np.finfo(float).eps:
        raise CfdTetraStokesError("velocity preconditioner is not symmetric")
    check()
    factor = splu(scalar, permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.)
    check()
    nonzeros = factor.L.nnz+factor.U.nnz
    if nonzeros > MAX_FACTOR_NONZEROS:
        raise CfdTetraStokesError("sparse factor nonzero budget exceeded")
    if np.any(factor.U.diagonal() <= 0.):
        raise CfdTetraStokesError("velocity preconditioner has nonpositive pivots")
    npres = len(pressure_diagonal)

    def apply(raw):
        vector = np.asarray(raw).reshape(-1)
        result = np.empty_like(vector)
        result[:nu] = factor.solve(vector[:nu].reshape((-1, 3))).ravel()
        result[nu:nu+npres] = vector[nu:nu+npres]/pressure_diagonal
        result[nu+npres:] = vector[nu+npres:]
        if not np.isfinite(result).all():
            raise CfdTetraStokesError("nonfinite preconditioner application")
        return result

    size = nu+npres+gauge_count
    return LinearOperator((size, size), matvec=apply, rmatvec=apply, dtype=float), nonzeros


def _inverse_solver(matrix, check, *, velocity_block, pressure_diagonal, gauge_count):
    stats = {"linear_solver_backend": "sparse_lu", "inverse_iterations": 0,
             "inverse_applications": 0, "sparse_factor_nonzeros": 0}
    if matrix.shape[0] <= MAX_DIRECT_UNKNOWNS:
        lu = splu(matrix)
        check()
        stats["sparse_factor_nonzeros"] = lu.L.nnz + lu.U.nnz
        if stats["sparse_factor_nonzeros"] > MAX_FACTOR_NONZEROS:
            raise CfdTetraStokesError("sparse factor nonzero budget exceeded")
        return lu.solve, lambda x: lu.solve(x, trans="T"), stats
    stats["linear_solver_backend"] = "residual_checked_minres"
    operator = matrix.tocsr()
    preconditioner, nonzeros = _block_preconditioner(
        velocity_block, pressure_diagonal, gauge_count, check)
    stats["sparse_factor_nonzeros"] = nonzeros
    stats["preconditioner_kind"] = "scalar_velocity_sparse_lu_pressure_mass_unit_gauge"

    def solve(raw):
        right = np.asarray(raw)
        if right.ndim == 2:
            return np.column_stack([solve(right[:, j]) for j in range(right.shape[1])])
        stats["inverse_applications"] += 1
        scale = float(np.max(np.abs(right), initial=0.))
        if scale == 0.:
            return np.zeros_like(right)
        rhs = right / scale
        rhs_norm = _norm(rhs)
        solution, used = np.zeros_like(rhs), 0
        # MINRES uses its own stopping normalization. Accept only a separately
        # recomputed rhs-relative residual; restart on the actual residual.
        for _ in range(3):
            residual = rhs-operator @ solution
            if _relative(_norm(residual), rhs_norm) <= 1e-13:
                return solution * scale

            def callback(_iterate):
                nonlocal used
                used += 1
                stats["inverse_iterations"] += 1
                check()
                if used > MAX_ITERATIONS_PER_INVERSE:
                    raise CfdTetraStokesError("MINRES iteration budget exceeded")

            correction, info = minres(operator, residual, M=preconditioner,
                                      rtol=1e-14, maxiter=5000, callback=callback)
            if info < 0 or not np.isfinite(correction).all():
                raise CfdTetraStokesError("MINRES breakdown or nonfinite correction")
            solution += correction
        actual_residual = _relative(_norm(rhs-operator @ solution), rhs_norm)
        if actual_residual > 1e-13:
            raise CfdTetraStokesError(
                f"inverse MINRES actual residual {actual_residual:.6g} exceeds 1e-13")
        return solution * scale

    return solve, solve, stats


def _linear_solve(k, b, load, prescribed, velocity, gauges, check, *, volumes, components, mu):
    fixed = np.repeat(prescribed, 3)
    free = np.flatnonzero(~fixed)
    active = np.arange(b.shape[0])
    u = velocity.ravel().copy()
    pressure = np.zeros(b.shape[0])
    condition, residual = 1., 0.
    if not len(free):
        if len(gauges) != b.shape[0]:
            raise CfdTetraStokesError("pressure constraints have no free velocity degrees of freedom")
        return u, pressure, free, condition, residual, {
            "linear_solver_backend": "all_velocity_prescribed", "inverse_iterations": 0,
            "inverse_applications": 0, "sparse_factor_nonzeros": 0}
    kff = k[free][:, free]
    bf = b[active][:, free]
    diagonal = kff.diagonal()
    if np.any(diagonal <= 0.):
        raise CfdTetraStokesError("free velocity stiffness is not coercive")
    su = 1. / np.sqrt(diagonal)
    bs = bf @ diags(su)
    squared_rows = np.asarray(bs.multiply(bs).sum(axis=1)).ravel()
    if np.any(squared_rows <= 0.):
        raise CfdTetraStokesError("pressure constraint has no safely represented velocity coupling")
    sp = 1. / np.sqrt(squared_rows)
    coupling = diags(sp) @ bs
    velocity_block = diags(su) @ kff @ diags(su)
    gauge_components = [component for component in components if int(component[0]) in gauges]
    if gauge_components:
        grows, gcols, gvalues = [], [], []
        for j, component in enumerate(gauge_components):
            weights = sp[component] * volumes[component]
            weights /= _norm(weights)
            grows.extend(component)
            gcols.extend([j] * len(component))
            gvalues.extend(weights)
        gauge = coo_matrix((gvalues, (grows, gcols)),
                           shape=(b.shape[0], len(gauge_components))).tocsr()
        # A Lagrange multiplier enforces mean pressure, without deleting any
        # local mass equation or adding a pressure penalty to the PDE.
        matrix = bmat([[velocity_block, -coupling.T, None],
                       [-coupling, None, gauge], [None, gauge.T, None]], format="csc")
    else:
        matrix = bmat([[velocity_block, -coupling.T],
                       [-coupling, None]], format="csc")
    rhs = np.r_[su * (load - k @ u)[free], sp * (b @ u),
                np.zeros(len(gauge_components))]
    if not np.isfinite(matrix.data).all() or not np.isfinite(rhs).all():
        raise CfdTetraStokesError("scaled saddle system is not finite")
    check()
    solve, transpose_solve, stats = _inverse_solver(
        matrix, check, velocity_block=velocity_block,
        pressure_diagonal=sp*sp*volumes/mu, gauge_count=len(gauge_components))
    inverse = LinearOperator(matrix.shape, matvec=solve, matmat=solve,
                             rmatvec=transpose_solve, dtype=float)
    condition = float(np.max(np.asarray(abs(matrix).sum(axis=0)))) * float(onenormest(inverse, t=1))
    if not math.isfinite(condition) or condition > MAX_CONDITION:
        raise CfdTetraStokesError("scaled saddle condition estimate exceeds 1e10")
    solution = solve(rhs)
    if not np.isfinite(solution).all():
        raise CfdTetraStokesError("nonfinite sparse solution")
    residual = _relative(_norm(matrix @ solution-rhs), _norm(rhs))
    if not math.isfinite(residual) or residual > 1e-10:
        raise CfdTetraStokesError("scaled linear residual exceeds 1e-10")
    u[free] = su * solution[:len(free)]
    pressure[:] = sp * solution[len(free):len(free)+b.shape[0]]
    for component in gauge_components:
        pressure[component] -= pressure[int(component[0])]
    check()
    return u, pressure, free, condition, residual, stats


def _diagnostics(mesh, k, b, body, traction_load, gradients, mu, rho,
                 u, p, free, prescribed, outlets):
    face_u = u.reshape((-1, 3))
    local_u = face_u[mesh["cell_faces"]]
    # Affine vector-norm convexity makes the four vertex speeds an upper
    # bound everywhere within each tetrahedron (not just face averages).
    vertex_u = np.sum(local_u, axis=1)[:, None, :] - 3. * local_u
    speed = max((math.hypot(*value) for value in vertex_u.reshape((-1, 3))), default=0.)
    extent = np.max(mesh["vertices"], axis=0) - np.min(mesh["vertices"], axis=0)
    length = math.hypot(*extent)
    reynolds = float(np.divide(np.multiply(np.multiply(rho, speed), length), mu))
    if not math.isfinite(reynolds) or reynolds > MAX_REYNOLDS:
        raise CfdTetraStokesError("Reynolds upper bound exceeds creeping-flow admission of 0.1")
    flux = b @ u
    area_sum = np.sum(mesh["face_areas"][mesh["cell_faces"]], axis=1)
    denominator = np.multiply(speed, area_sum)
    scaled_mass = np.zeros_like(flux)
    nonzero = denominator > 0.
    scaled_mass[nonzero] = np.abs(flux[nonzero]) / denominator[nonzero]
    if np.any(flux[~nonzero] != 0.) or np.max(scaled_mass, initial=0.) > 1e-10:
        raise CfdTetraStokesError("cellwise conservative mass residual exceeds 1e-10")
    normal_speed = np.sum(face_u[outlets] * mesh["face_normals"][outlets], axis=1)
    maximum_backflow = max(0., -float(np.min(normal_speed, initial=0.)))
    if _relative(maximum_backflow, speed) > 1e-10:
        raise CfdTetraStokesError("pseudo-traction outlet has face-average backflow")
    load = body + traction_load
    pressure_force = b.T @ p
    equation_defect = k @ u - pressure_force - load
    fixed_u = np.where(np.repeat(prescribed, 3), u, 0.)
    # The free equation is Kff*uf - Bf.T*p = load_f-Kfd*gd.
    # Preserve those separate terms in its backward-error scale: K*u can
    # vanish for a nonzero affine harmonic solution and is not a valid scale.
    scale = max(_norm((k @ (u-fixed_u))[free]), _norm((k @ fixed_u)[free]),
                _norm(pressure_force[free]), _norm(load[free]))
    momentum = _relative(_norm(equation_defect[free]), scale)
    if momentum > 1e-10 or not math.isfinite(momentum):
        raise CfdTetraStokesError("unscaled momentum residual exceeds 1e-10")
    reaction = np.where(np.repeat(prescribed, 3), equation_defect, 0.)
    # Subtracting a reference face makes constant velocity gradients exactly
    # zero without cancelling large equal face values in a dot product.
    differences = local_u - local_u[:, :1, :]
    grad_u = np.sum(differences[:, :, :, None] * gradients[:, :, None, :], axis=1)
    dissipation = float(np.sum(np.multiply(mu * mesh["cell_volumes"],
                                          np.sum(np.multiply(grad_u, grad_u), axis=(1, 2)))))
    body_work, traction_work = _power(body, u), _power(traction_load, u)
    reaction_work, pressure_work = _power(reaction, u), -_power(pressure_force, u)
    energy_scale = max(abs(body_work)+abs(traction_work)+abs(reaction_work),
                       dissipation, float(np.multiply(_norm(u), _norm(load+reaction))))
    defect = _relative(abs(body_work+traction_work+reaction_work-dissipation-pressure_work), energy_scale)
    if not math.isfinite(defect) or defect > 1e-9:
        raise CfdTetraStokesError("broken-gradient power balance exceeds 1e-9")
    patch_fluxes = {
        name: _power(mesh["face_areas"][indices],
                     np.sum(face_u[indices]*mesh["face_normals"][indices], axis=1))
        for name, indices in mesh["boundary_patches"].items()
    }
    return {
        "reynolds_upper_bound": reynolds, "reynolds_length_m": length,
        "maximum_velocity_bound_m_s": speed,
        "maximum_local_mass_scaled_residual": float(np.max(scaled_mass, initial=0.)),
        "maximum_cell_flux_imbalance_m3_s": float(np.max(np.abs(flux), initial=0.)),
        "maximum_divergence_s_inv": float(np.max(np.abs(flux/mesh["cell_volumes"]), initial=0.)),
        "momentum_relative_residual": momentum,
        "viscous_broken_gradient_dissipation_w": dissipation,
        "body_force_work_w": body_work, "pseudo_traction_work_w": traction_work,
        "dirichlet_reaction_work_w": reaction_work, "pressure_work_w": pressure_work,
        "relative_energy_defect": defect, "boundary_patch_outward_flux_m3_s": patch_fluxes,
        "maximum_outlet_face_average_backflow_m_s": maximum_backflow,
    }, np.mean(local_u, axis=1), grad_u


def solve_cfd_tetra_stokes(request, *, cancel_check=None):
    """Solve only admitted creeping CR/P0 flow; failures never publish fields."""
    result = {
        "contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
        "operator": "broken_vector_laplacian_cr_p1_face_average_p0_pressure",
        "natural_boundary": "pseudo_traction_mu_grad_u_minus_pI_not_symmetric_stress",
        "limitations": [
            "Steady constant-property Stokes only; inertia, turbulence and CHT are unsupported.",
            "Only face-average velocity and flux are shared; pointwise traces can jump.",
            "Outlet rejection checks face-average backflow, not pointwise recirculation.",
            "Natural data are piecewise-constant pseudo-traction, not physical symmetric traction.",
        ],
    }
    try:
        if not isinstance(request, Mapping) or set(request) != _KEYS or request["contract"] != CONTRACT:
            raise CfdTetraStokesError("request contract or exact option set is invalid")
        controls = request["controls"]
        if not isinstance(controls, Mapping) or set(controls) - {"max_runtime_s"}:
            raise CfdTetraStokesError("controls supports only max_runtime_s")
        timeout = _number(controls.get("max_runtime_s", 30.), "max_runtime_s")
        if timeout > 60.:
            raise CfdTetraStokesError("max_runtime_s exceeds 60 seconds")
        deadline = time.monotonic() + timeout

        def check():
            if cancel_check and cancel_check():
                raise InterruptedError()
            if time.monotonic() >= deadline:
                raise CfdTetraStokesError("runtime budget exceeded")

        def admission_cancel():
            check()
            return False

        check()
        with np.errstate(over="raise", under="raise", invalid="raise", divide="raise"):
            mesh = admit_cfd_tetra_mesh(request["mesh"], cancel_check=admission_cancel)
            check()
            mu = _number(request["dynamic_viscosity_pa_s"], "dynamic_viscosity_pa_s")
            rho = _number(request["density_kg_m3"], "density_kg_m3")
            force = _array(request["body_force_n_m3"], (len(mesh["cells"]), 3), "body_force_n_m3")
            prescribed, boundary_u, traction, outlets, gauges = _boundary(mesh, request["boundary_conditions"])
            k, b, body, gradients = _assemble(mesh, force, mu, check)
            traction_load = np.multiply(mesh["face_areas"][:, None], traction).ravel()
            u, p, free, condition, residual, solver_stats = _linear_solve(
                k, b, body+traction_load, prescribed, boundary_u, gauges, check,
                volumes=mesh["cell_volumes"], components=mesh["components"], mu=mu)
            diagnostics, cell_u, grad_u = _diagnostics(
                mesh, k, b, body, traction_load, gradients, mu, rho, u, p, free, prescribed, outlets)
            diagnostics.update(scaled_linear_relative_residual=residual, scaled_condition_estimate=condition,
                               condition_estimate_kind="one_norm_estimate_with_residual_checked_inverse",
                               tetrahedra=len(mesh["cells"]),
                               faces=len(mesh["face_vertices"]), free_velocity_dofs=len(free),
                               pressure_gauge_cells=gauges, connected_components=len(mesh["components"]),
                               pressure_gauge_method="volume_mean_multiplier_then_reference_shift")
            diagnostics.update(solver_stats)
            check()
            result.update(status="completed", diagnostics=diagnostics, fields={
                "face_vertices": mesh["face_vertices"].tolist(),
                "face_average_velocity_m_s": u.reshape((-1, 3)).tolist(),
                "cell_velocity_m_s": cell_u.tolist(), "cell_pressure_pa": p.tolist(),
                "cell_velocity_gradient_s_inv": grad_u.tolist(),
            })
    except InterruptedError:
        result.update(status="cancelled", issues=[{"code": "CANCELLED", "message": "Tetra Stokes cancelled"}])
    except (ValueError, TypeError, ArithmeticError, RuntimeError) as exc:
        result.update(status="blocked", issues=[{"code": "CFD_TETRA_STOKES_REJECTED", "message": str(exc)}])
    return result
