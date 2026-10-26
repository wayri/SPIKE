# SPDX-License-Identifier: Apache-2.0
"""Bounded nonlinear P2 rotor/stator with an analytic rotating Fourier gap.

Supplied constitutive laws only; no hardware, torque-refinement or controller
qualification. See validation/PROPULSION_POD_NONLINEAR_P2_20261023.md.
"""
import copy
import math
import time

import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.sparse.linalg import LinearOperator, cg
from scipy.sparse import issparse

from .propulsion_pod_magnetic_p2 import _require
from .propulsion_pod_nonlinear_p2 import NonlinearP2MagneticOperator, _arrays_digest, _json_digest
from .propulsion_pod_separated_motor import SeparatedMotor
from .propulsion_pod_modal_gap import ModalGap, METHOD as GAP_METHOD


def _readonly(array):
    result = np.array(array, dtype=float, copy=True)
    result.setflags(write=False)
    return result


class NonlinearSeparatedMotor:
    """Joint field solve using linear reference factors only as preconditioner.

    The prepared motor and both operators must remain unchanged during use.
    Explicit winding chi arrays are checked against the prepared source ports.
    Unknown order is [rotor interior, stator interior, rotor trace, stator trace].
    """
    def __init__(self, motor, rotor_operator, stator_operator, winding_chi_per_m2,
                 *, maximum_unknowns=500000, maximum_fourier_mode=255,
                 maximum_dense_reference_bytes=512*1024**2):
        _require(isinstance(motor, SeparatedMotor), 'Prepared separated motor required')
        _require(type(maximum_unknowns) is int and 1 <= maximum_unknowns <= 500000,
                 'Coupled unknown budget must be 1..500000')
        _require(type(maximum_fourier_mode) is int and 0 <= maximum_fourier_mode <= 1024,
                 'Nonlinear Fourier budget must be an integer in 0..1024')
        _require(motor.gap.maximum_mode <= maximum_fourier_mode,
                 'Nonlinear coupled Fourier mode budget exceeded (default 255)')
        _require(type(maximum_dense_reference_bytes) is int
                 and 1 <= maximum_dense_reference_bytes <= 512*1024**2,
                 'Dense reference byte budget must be 1..536870912')
        # H, a possible Cholesky copy, and a dense-equivalent workspace reserve.
        # This explicit array allowance is not an allocator-hard process bound.
        dense_reference_bytes = 3*8*(2*motor.gap.size)**2
        _require(dense_reference_bytes <= maximum_dense_reference_bytes,
                 'Dense reference preallocation byte budget exceeded')
        self._solver_options = {'gap_method': GAP_METHOD, 'maximum_unknowns': maximum_unknowns,
            'maximum_fourier_mode': maximum_fourier_mode,
            'maximum_dense_reference_bytes': maximum_dense_reference_bytes}
        self.solver_options_sha256 = _json_digest(self._solver_options)
        _require(isinstance(winding_chi_per_m2, dict) and set(winding_chi_per_m2) == {'rotor', 'stator'},
                 'Explicit rotor and stator winding source arrays required')
        self.motor = motor
        self.domains = (motor.rotor, motor.stator)
        self.operators = (rotor_operator, stator_operator)
        self.chi, self.loads = [], []
        self.interior_slices = []
        offset = 0
        for name, domain, op in zip(('rotor', 'stator'), self.domains, self.operators):
            _require(isinstance(op, NonlinearP2MagneticOperator) and op.base is domain.op,
                     'Nonlinear operator must wrap the exact prepared motor domain')
            chi = np.array(winding_chi_per_m2[name], dtype=float, copy=True)
            _require(chi.shape == (len(domain.op.triangles), 3) and np.isfinite(chi).all(),
                     'Three finite winding source columns required')
            loads = np.column_stack([domain.op.source_load(chi[:, j]) for j in range(3)])
            kii = domain.op.stiffness[domain.interior][:, domain.interior]
            interior_error = kii@domain.Xf[:, 1:]-loads[domain.interior]
            trace = domain.V.T@(loads[domain.boundary]-domain.Kib.T@domain.Xf[:, 1:])
            scale = np.maximum(np.maximum(np.linalg.norm(loads[domain.interior], axis=0),
                                          np.linalg.norm(trace, axis=0)), 1e-30)
            _require(np.all(np.linalg.norm(interior_error, axis=0) <= 1e-8*scale)
                     and np.all(np.linalg.norm(trace-domain.G[:, 1:], axis=0) <= 1e-8*scale),
                     'Winding sources differ from prepared motor identity')
            chi.setflags(write=False)
            loads.setflags(write=False)
            self.chi.append(chi)
            self.loads.append(loads)
            self.interior_slices.append(slice(offset, offset+len(domain.interior)))
            offset += len(domain.interior)
        self.trace_start = offset
        self.size = offset+2*motor.gap.size
        _require(self.size <= maximum_unknowns, 'Coupled unknown budget exceeded')
        self._factor_objects = tuple(domain.factor for domain in self.domains)
        arrays = {}
        for owner in (*self.domains, *(d.op for d in self.domains), *self.operators):
            for value in vars(owner).values():
                if isinstance(value, np.ndarray):arrays[id(value)] = value.nbytes
                elif issparse(value):
                    for part in (value.data, value.indices, value.indptr):arrays[id(part)] = part.nbytes
        self._resource_plan = {
            'dense_reference_allowance_bytes': dense_reference_bytes,
            'known_domain_trace_quadrature_array_bytes': sum(arrays.values()),
            'reference_factor_native_storage_entries': [int(d.factor.nnz) for d in self.domains],
            'joint_unknowns': self.size, 'joint_trace_coefficients': 2*motor.gap.size,
            'scope': 'explicit arrays; views may overlap; excludes native factor/workspace and assembly temporaries',
            'process_memory_bound_enforced_by_this_class': False}
        self._motor_state = self._dependency_digest()
        self._prepared_identity = {'source_sha256': motor.source_sha256,
                                   'geometry_sha256': motor.geometry_sha256,
                                   'spec_sha256': motor.spec_sha256}
        self._constitutive_model = {
            'schema': 'spike/nonlinear-separated-motor-constitutive/v1',
            'domains': {name: op.constitutive_identity() for name, op in
                        zip(('rotor', 'stator'), self.operators)},
            'prepared_linear_model_identity': copy.deepcopy(self._prepared_identity),
            'coupled_operator_sha256': self._motor_state,
            'source_kind': 'explicit-prepared-equivalent-winding-chi',
            'material_status': 'supplied-laws-unverified', 'physical_qualified': False}
        self.constitutive_sha256 = _json_digest(self._constitutive_model)

    def _dependency_digest(self):
        arrays = {}
        for j, domain in enumerate(self.domains):
            for name in ('V', 'S', 'interior', 'boundary', 'Xf', 'G'):
                arrays[str(j)+'/'+name] = getattr(domain, name)
            for name in ('data', 'indices', 'indptr'):
                arrays[str(j)+'/Kib/'+name] = getattr(domain.Kib, name)
            arrays[str(j)+'/chi'] = self.chi[j]
            arrays[str(j)+'/loads'] = self.loads[j]
        gap = self.motor.gap
        return _json_digest({'arrays': _arrays_digest(arrays),
                             'gap': {name: getattr(gap, name) for name in
                                     ('a', 'b', 'depth', 'maximum_mode', 'size', 'log_ratio', 'scale')},
                             'interior_slices': [[s.start, s.stop, s.step] for s in self.interior_slices],
                             'size': self.size, 'trace_start': self.trace_start,
                             'source_sha256': self.motor.source_sha256,
                             'geometry_sha256': self.motor.geometry_sha256,
                             'spec_sha256': self.motor.spec_sha256})

    def validate_dependencies(self):
        """Check once at evaluate entry/exit; never hash inside CG/line search."""
        _require(self.motor.rotor is self.domains[0] and self.motor.stator is self.domains[1]
                 and all(op.base is d.op and d.factor is factor for op, d, factor in
                         zip(self.operators, self.domains, self._factor_objects)),
                 'Coupled motor dependencies changed; prepare a new model and identity')
        for op in self.operators:
            op.validate_dependencies()
        _require(self._dependency_digest() == self._motor_state
                 and _json_digest(self._solver_options) == self.solver_options_sha256
                 and _json_digest(self._constitutive_model) == self.constitutive_sha256
                 and all(op.constitutive_sha256 == self._constitutive_model['domains'][name]['constitutive_sha256']
                         for name, op in zip(('rotor', 'stator'), self.operators)),
                 'Coupled motor dependencies changed; prepare a new model and identity')

    def _expand(self, unknown):
        arrays = []
        m = self.motor.gap.size
        for j, (domain, interior) in enumerate(zip(self.domains, self.interior_slices)):
            a = np.zeros(len(domain.op.nodes_m))
            a[domain.interior] = unknown[interior]
            a[domain.boundary] = domain.V@unknown[self.trace_start+j*m:self.trace_start+(j+1)*m]
            arrays.append(a)
        return arrays

    def _reduce(self, arrays):
        interior = [v[d.interior] for v, d in zip(arrays, self.domains)]
        traces = [d.V.T@v[d.boundary] for v, d in zip(arrays, self.domains)]
        return np.concatenate([*interior, *traces])

    def _preconditioner(self, gap, check_time):
        """Exact inverse of the unchanged linear reference, for arbitrary RHS."""
        m = self.motor.gap.size
        _require(3*8*(2*m)**2 <= self._solver_options['maximum_dense_reference_bytes'],
                 'Dense reference preallocation byte budget exceeded')
        schur = np.zeros((2*m, 2*m), order='F')
        schur[:m, :m] = self.domains[0].S
        schur[m:, m:] = self.domains[1].S
        gap.add_to_dense(schur)
        check_time()
        try:
            factor = cho_factor(schur, lower=True, overwrite_a=True)
        except np.linalg.LinAlgError as exc:
            raise ValueError('Coupled reference requires a positive gauged Schur matrix') from exc
        check_time()

        def apply(rhs):
            check_time()
            solved = [d.factor.solve(rhs[s]) for d, s in zip(self.domains, self.interior_slices)]
            reduced = rhs[self.trace_start:].copy()
            for j, (domain, vector) in enumerate(zip(self.domains, solved)):
                reduced[j*m:(j+1)*m] -= domain.V.T@(domain.Kib.T@vector)
            coefficients = cho_solve(factor, reduced)
            for j, domain in enumerate(self.domains):
                solved[j] -= domain.factor.solve(domain.Kib@(domain.V@coefficients[j*m:(j+1)*m]))
            result = np.concatenate([*solved, coefficients])
            _require(np.isfinite(result).all(), 'Coupled preconditioner exceeds numerical range')
            return result
        return LinearOperator((self.size, self.size), matvec=apply, dtype=float)

    def evaluate(self, currents_a, angle_rad, include_field=False, *, initial_unknowns=None,
                 relative_tolerance=1e-9, absolute_tolerance_a_m=1e-9,
                 maximum_iterations=60, maximum_cg_iterations=1000, maximum_seconds=60.,
                 include_sensitivities=False):
        """Solve a stationary field; return conservative current/shaft port data.

        Potential snapshots are detached read-only arrays. No previous result
        is retained or mutated. CPU budgets are checked between assemblies,
        factorization and CG operations, not inside a BLAS/SuperLU call.
        """
        _require(type(include_field) is bool, 'Field recovery flag must be boolean')
        _require(type(include_sensitivities) is bool, 'Sensitivity flag must be boolean')
        _require(type(angle_rad) in (int, float) and math.isfinite(angle_rad), 'Finite mechanical angle required')
        currents = np.asarray(currents_a, dtype=float)
        _require(currents.shape == (3,) and np.isfinite(currents).all(), 'Three finite physical phase currents required')
        for value in (relative_tolerance, absolute_tolerance_a_m, maximum_seconds):
            _require(type(value) in (int, float) and math.isfinite(value) and value > 0,
                     'Positive finite tolerances and time budget required')
        _require(relative_tolerance <= .01 and maximum_seconds <= 600,
                 'Tolerance/time budget exceeds allowed range')
        _require(type(maximum_iterations) is int and 1 <= maximum_iterations <= 200
                 and type(maximum_cg_iterations) is int and 1 <= maximum_cg_iterations <= 5000,
                 'Bounded Newton and CG iteration counts required')
        start = time.perf_counter()
        def check_time():
            _require(time.perf_counter()-start <= maximum_seconds, 'Nonlinear coupled solve time budget exceeded')
        self.validate_dependencies()
        check_time()
        unknown = np.zeros(self.size) if initial_unknowns is None else np.array(initial_unknowns, dtype=float, copy=True)
        _require(unknown.shape == (self.size,) and np.isfinite(unknown).all(), 'Finite aligned initial unknowns required')
        gap = ModalGap(self.motor.gap, angle_rad)
        preconditioner = self._preconditioner(gap, check_time)
        current_densities = [chi@currents for chi in self.chi]
        m = self.motor.gap.size

        def assemble(vector):
            check_time()
            potentials = self._expand(vector)
            states = [op._assemble_verified(a, j) for op, a, j in zip(self.operators, potentials, current_densities)]
            coefficients = vector[self.trace_start:]
            gap_energy = gap.energy_torque(coefficients)['vacuum_energy_j']
            residual = self._reduce([state['residual_a_m'] for state in states])
            residual[self.trace_start:] += gap.apply(coefficients)
            potential = sum(state['potential_j'] for state in states)+gap_energy
            _require(np.isfinite(residual).all() and math.isfinite(potential), 'Coupled assembly exceeds numerical range')
            check_time()
            return states, potentials, residual, potential, gap_energy

        state = assemble(unknown)
        history = [float(np.linalg.norm(state[2]))]
        threshold = absolute_tolerance_a_m+relative_tolerance*history[0]
        step_lengths, cg_counts, cg_residuals = [], [], []
        while history[-1] > threshold and len(step_lengths) < maximum_iterations:
            matrices = [s['tangent_a_m2_per_wb'] for s in state[0]]
            def matvec(vector):
                check_time()
                result = self._reduce([k@a for k, a in zip(matrices, self._expand(vector))])
                result[self.trace_start:] += gap.apply(vector[self.trace_start:])
                return result
            tangent = LinearOperator((self.size, self.size), matvec=matvec, dtype=float)
            count = [0]
            def callback(_):
                check_time()
                count[0] += 1
            rhs = -state[2]
            linear_atol = min(1e-12, .1*threshold)
            delta, info = cg(tangent, rhs, M=preconditioner, rtol=1e-10, atol=linear_atol,
                             maxiter=maximum_cg_iterations, callback=callback)
            error = float(np.linalg.norm(matvec(delta)-rhs))
            _require(info == 0 and np.isfinite(delta).all()
                     and error <= linear_atol+1e-9*np.linalg.norm(rhs),
                     'Coupled Newton CG failed actual residual gate')
            descent = float(state[2]@delta)
            _require(math.isfinite(descent) and descent < 0, 'Coupled Newton direction is not descent')
            accepted, alpha = False, 1.
            for _ in range(48):
                trial_unknown = unknown+alpha*delta
                try:
                    trial = assemble(trial_unknown)
                except ValueError as exc:
                    if 'B-H range' not in str(exc):
                        raise
                    alpha *= .5
                    continue
                norm = float(np.linalg.norm(trial[2]))
                rounding = 64*np.finfo(float).eps*max(abs(state[3]), abs(trial[3]), 1e-30)
                if trial[3] <= state[3]+1e-4*alpha*descent+rounding or norm <= threshold:
                    unknown, state, accepted = trial_unknown, trial, True
                    history.append(norm)
                    step_lengths.append(alpha)
                    cg_counts.append(count[0])
                    cg_residuals.append(error)
                    break
                alpha *= .5
            _require(accepted, 'Coupled nonlinear line search failed; check B-H range and conditioning')
        _require(history[-1] <= threshold, 'Coupled nonlinear Newton did not converge')
        coefficients = unknown[self.trace_start:]
        flux = sum(load.T@a for load, a in zip(self.loads, state[1]))
        energy = sum(s['magnetic_energy_j'] for s in state[0])+state[4]
        torque = gap.energy_torque(coefficients)['rotor_torque_n_m']
        coenergy = float(currents@flux-energy)
        _require(np.isfinite(np.r_[flux, energy, torque, coenergy]).all(), 'Coupled result exceeds numerical range')
        self.validate_dependencies()
        check_time()
        result = {'torque_n_m': torque, 'flux_linkage_wb_turn': flux.tolist(),
                  'coenergy_j': coenergy, 'magnetic_energy_j': float(energy), 'gap_energy_j': state[4],
                  'rotor_fourier_coefficients': _readonly(coefficients[:m]),
                  'stator_fourier_coefficients': _readonly(coefficients[m:]),
                  'unknown_potential_wb_per_m': _readonly(unknown),
                  'relative_residual': history[-1]/max(history[0], 1e-30),
                  'physical_qualified': False, 'production_qualified': False,
                  'source_sha256': self.motor.source_sha256, 'geometry_sha256': self.motor.geometry_sha256,
                  'prepared_linear_model_identity': copy.deepcopy(self._prepared_identity),
                  'constitutive_sha256': self.constitutive_sha256,
                  'constitutive_model': copy.deepcopy(self._constitutive_model),
                  'solver_options': copy.deepcopy(self._solver_options),
                  'solver_options_sha256': self.solver_options_sha256,
                  'resource_plan': copy.deepcopy(self._resource_plan),
                  'diagnostics': {'converged': True, 'residual_history_a_m': history,
                                  'residual_threshold_a_m': threshold, 'newton_step_lengths': step_lengths,
                                  'cg_iterations': cg_counts, 'cg_actual_residual_a_m': cg_residuals,
                                  'iterations': len(step_lengths), 'elapsed_seconds': time.perf_counter()-start,
                                  'fourier_maximum_mode': self.motor.gap.maximum_mode,
                                  'quadrature_converged': False, 'material_qualified': False}}
        if include_field:
            result['local_domain_potential_wb_per_m'] = {
                name: _readonly(a) for name, a in zip(('rotor', 'stator'), state[1])}
        if include_sensitivities:
            from .propulsion_pod_three_phase import STAR
            matrices = [s['tangent_a_m2_per_wb'] for s in state[0]]
            def action(vector):
                check_time()
                value = self._reduce([k@a for k, a in zip(matrices, self._expand(vector))])
                value[self.trace_start:] += gap.apply(vector[self.trace_start:])
                return value
            tangent = LinearOperator((self.size, self.size), matvec=action, dtype=float)
            loads = np.column_stack([self._reduce([f[:, j] for f in self.loads]) for j in range(3)])
            balanced = loads@STAR
            angle_rhs = np.zeros(self.size)
            angle_rhs[self.trace_start:] = -gap.angle_derivative_action(coefficients)
            solutions, errors = [], []
            for rhs in (*balanced.T, angle_rhs):
                solution, info = cg(tangent, rhs, M=preconditioner, rtol=1e-11,
                                    atol=1e-14, maxiter=maximum_cg_iterations)
                error = float(np.linalg.norm(action(solution)-rhs))
                _require(info == 0 and np.isfinite(solution).all()
                         and error <= 1e-14+1e-9*np.linalg.norm(rhs),
                         'Current tangent sensitivity failed actual residual gate')
                solutions.append(solution); errors.append(error)
            result['balanced_differential_inductance_h'] = balanced.T@np.column_stack(solutions[:2])
            result['phase_flux_angle_derivative_wb_turn_per_rad'] = loads.T@solutions[2]
            result['diagnostics']['sensitivity_actual_residuals_a_m'] = errors
            self.validate_dependencies(); check_time()
        return result

    def energy_flux_difference(self, initial_unknowns, initial_angle, final_unknowns, final_angle):
        """Same joint energy and three-phase flux increments without total subtraction."""
        self.validate_dependencies()
        a, b = np.asarray(initial_unknowns, float), np.asarray(final_unknowns, float)
        _require(a.shape == b.shape == (self.size,) and np.isfinite(np.r_[a, b]).all(),
                 'Finite aligned joint potential endpoints required')
        _require(all(type(t) in (int, float) and math.isfinite(t) for t in (initial_angle, final_angle)),
                 'Finite mechanical angle endpoints required')
        aa, bb = self._expand(a), self._expand(b)
        energy = sum(op.energy_difference(x, y) for op, x, y in zip(self.operators, aa, bb))
        gap = ModalGap(self.motor.gap, initial_angle)
        energy += gap.energy_difference(a[self.trace_start:], b[self.trace_start:], final_angle-initial_angle)
        flux = sum(f.T@v for f, v in zip(self.loads, self._expand(b-a)))
        self.validate_dependencies()
        return {'magnetic_energy_difference_j': float(energy), 'phase_flux_difference_wb_turn': flux}
