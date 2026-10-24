# SPDX-License-Identifier: Apache-2.0
"""Bounded direct supplied-law Legendre port; no actual-material admission.

See PROPULSION_POD_NONLINEAR_PORT_REVIEW_20261024.md for the independent
STAR duality, current/angle sensitivities and stable difference derivation.
"""
import copy
import hashlib
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
import numpy as np
from .propulsion_pod_magnetic_p2 import _require
from .propulsion_pod_nonlinear_p2 import _json_digest
from .propulsion_pod_nonlinear_motor import NonlinearSeparatedMotor
from .propulsion_pod_three_phase import STAR


class DirectNonlinearMagneticPort:
    """Immutable-model, limited cache and bounded per-operation reference port."""
    kind = 'direct-nonlinear-field-port/v1'
    def __init__(self, model, *, maximum_phase_current_a, end_turn_inductance_h=(0., 0., 0.),
                 maximum_seconds=60., maximum_field_solves=128, maximum_cache_bytes=64*1024**2,
                 inverse_absolute_tolerance_wb_turn=1e-13, inverse_relative_tolerance=1e-10):
        _require(isinstance(model, NonlinearSeparatedMotor), 'Prepared nonlinear coupled model required')
        numeric = (maximum_phase_current_a, maximum_seconds, inverse_absolute_tolerance_wb_turn,
                   inverse_relative_tolerance)
        _require(all(type(v) in (int, float) and np.isfinite(v) and v > 0 for v in numeric),
                 'Finite positive current, wall and inverse tolerance bounds required')
        _require(maximum_seconds <= 600 and inverse_absolute_tolerance_wb_turn <= 1e-10
                 and inverse_relative_tolerance <= 1e-6, 'Port tolerance/time budget exceeded')
        _require(type(maximum_field_solves) is int and 1 <= maximum_field_solves <= 1024,
                 'Field solve count must be 1..1024 per operation')
        _require(type(maximum_cache_bytes) is int and 1 <= maximum_cache_bytes <= 256*1024**2,
                 'Cache byte budget must be 1..268435456')
        end = np.asarray(end_turn_inductance_h, float)
        _require(end.shape == (3,) and np.isfinite(end).all() and np.all(end >= 0),
                 'Three supplied nonnegative end-turn inductances required')
        model.validate_dependencies()
        self.model = model
        self.max_current_a = float(maximum_phase_current_a)
        self.end = np.diag(end); self.end.setflags(write=False)
        self.D = STAR.T@self.end@STAR; self.D.setflags(write=False)
        self._options = dict(maximum_phase_current_a=self.max_current_a, maximum_seconds=float(maximum_seconds),
            maximum_field_solves=maximum_field_solves, maximum_cache_bytes=maximum_cache_bytes,
            inverse_absolute_tolerance_wb_turn=inverse_absolute_tolerance_wb_turn,
            inverse_relative_tolerance=inverse_relative_tolerance, end_turn_inductance_h=end.tolist())
        self._identity = {'contract':'spike/direct-supplied-law-magnetic-port/v1',
            'constitutive_sha256':model.constitutive_sha256,'solver_options_sha256':model.solver_options_sha256,
            'port_options':copy.deepcopy(self._options),'material_qualified':False}
        self._source_paths = tuple(Path(__file__).with_name(name) for name in
            ('propulsion_pod_nonlinear_port.py','propulsion_pod_nonlinear_motor.py',
             'propulsion_pod_nonlinear_p2.py','propulsion_pod_modal_gap.py','magnetic_fem.py',
             'propulsion_pod_annular_gap.py','propulsion_pod_magnetic_p2.py',
             'propulsion_pod_separated_motor.py','propulsion_pod_three_phase.py'))
        self._identity['implementation_sha256'] = self._source_hashes()
        self.source_sha256 = _json_digest(self._identity)
        self._cache = OrderedDict(); self._cache_bytes = 0
        self._run_deadline = float('inf'); self._deadline = float('inf')
        self.diagnostics = {'kind':'direct-supplied-law-field-port','material_qualified':False,
                            'field_load_qualified':False,'source_sha256':self.source_sha256}

    def _source_hashes(self):
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self._source_paths}

    @contextmanager
    def bounded_run(self, deadline_monotonic):
        """Restrict every operation to a caller's run deadline; nesting tightens.

        This synchronous resource scope is not part of constitutive identity.
        Both enclosing deadlines are restored even after a rejected operation.
        """
        _require(type(deadline_monotonic) in (int, float) and np.isfinite(deadline_monotonic),
                 'Finite monotonic run deadline required')
        previous_run, previous_operation = self._run_deadline, self._deadline
        deadline = min(previous_run, float(deadline_monotonic))
        _require(time.monotonic() < deadline, 'Direct port run deadline exceeded')
        self._run_deadline = deadline
        try:
            yield self
        finally:
            self._run_deadline, self._deadline = previous_run, previous_operation

    def _begin(self):
        now = time.monotonic()
        _require(now < self._run_deadline, 'Direct port run deadline exceeded')
        self._deadline = min(now+self._options['maximum_seconds'], self._run_deadline)
        self._count = 0
        self.model.validate_dependencies()
        _require(_json_digest(self._identity) == self.source_sha256
                 and self._identity['port_options'] == self._options
                 and self.model.constitutive_sha256 == self._identity['constitutive_sha256']
                 and self.model.solver_options_sha256 == self._identity['solver_options_sha256']
                 and self._source_hashes() == self._identity['implementation_sha256']
                 and np.array_equal(STAR, [[1.,0.],[0.,1.],[-1.,-1.]])
                 and self.max_current_a == self._options['maximum_phase_current_a']
                 and np.array_equal(np.diag(self.end), self._options['end_turn_inductance_h'])
                 and np.array_equal(self.end, np.diag(np.diag(self.end)))
                 and np.array_equal(self.D, STAR.T@self.end@STAR), 'Direct port dependencies changed')
        self._check()

    def _check(self):
        _require(time.monotonic() < min(self._deadline, self._run_deadline),
                 'Direct port wall budget exceeded')

    def _current(self, x):
        x = np.asarray(x, float)
        _require(x.shape == (2,) and np.isfinite(x).all() and max(abs(STAR@x)) <= self.max_current_a,
                 'Magnetic port phase-current envelope exceeded')
        return x

    def _state(self, x, theta):
        self._check(); x = self._current(x)
        _require(type(theta) in (int, float) and np.isfinite(theta), 'Finite mechanical angle required')
        key = (float(x[0]), float(x[1]), float(theta))
        if key in self._cache:
            self._cache.move_to_end(key); return self._cache[key]
        _require(self._count < self._options['maximum_field_solves'], 'Direct port field solve budget exceeded')
        _require(8*self.model.size+1280 <= self._options['maximum_cache_bytes'],
                 'Direct port state exceeds cache byte budget')
        self._count += 1
        result = self.model.evaluate((STAR@x).tolist(), theta, include_sensitivities=True,
            relative_tolerance=1e-11, absolute_tolerance_a_m=1e-11,
            maximum_seconds=min(600., self._deadline-time.monotonic()))
        M = result['balanced_differential_inductance_h']+self.D
        scale = max(float(np.linalg.norm(M)), 1e-30)
        _require(np.linalg.norm(M-M.T) <= 1e-8*scale, 'Differential winding reciprocity failed')
        eigen = np.linalg.eigvalsh((M+M.T)/2)
        _require(eigen[0] > 1e-14 and eigen[-1]/eigen[0] <= 1e8,
                 'Balanced differential inductance is not positive and conditioned')
        b = STAR.T@np.asarray(result['flux_linkage_wb_turn'])
        state = {'x':x.copy(),'theta':float(theta),'b':b,'q':b+self.D@x,'M':M,
            'z':result['unknown_potential_wb_per_m'],'U':result['magnetic_energy_j'],
            'torque':result['torque_n_m'],'phase_flux':np.asarray(result['flux_linkage_wb_turn'])+self.end@(STAR@x),
            'phase_angle':result['phase_flux_angle_derivative_wb_turn_per_rad']}
        for value in state.values():
            if isinstance(value, np.ndarray):value.setflags(write=False)
        size = sum(v.nbytes for v in state.values() if isinstance(v, np.ndarray))+1024
        _require(size <= self._options['maximum_cache_bytes'], 'Direct port state exceeds cache byte budget')
        while self._cache and self._cache_bytes+size > self._options['maximum_cache_bytes']:
            _, old = self._cache.popitem(last=False); self._cache_bytes -= old['_bytes']
        state['_bytes'] = size; self._cache[key] = state; self._cache_bytes += size
        self._check(); return state

    def _difference(self, a, b):
        self._check()
        out = self.model.energy_flux_difference(a['z'], a['theta'], b['z'], b['theta'])
        self._check()
        return out['magnetic_energy_difference_j'], STAR.T@out['phase_flux_difference_wb_turn']

    def _inverse(self, q, theta):
        q = np.asarray(q, float)
        _require(q.shape == (2,) and np.isfinite(q).all(), 'Two finite flux coordinates required')
        state = self._state(np.zeros(2), theta)
        tolerance = self._options['inverse_absolute_tolerance_wb_turn']+self._options['inverse_relative_tolerance']*np.linalg.norm(q)
        for _ in range(32):
            residual = state['q']-q
            if np.linalg.norm(residual) <= tolerance:return state, q-state['q']
            direction = np.linalg.solve(state['M'], -residual)
            descent = float(residual@direction)
            _require(np.isfinite(direction).all() and descent < 0, 'Legendre inverse is not descent')
            accepted = False
            for k in range(32):
                dx = direction*2.**(-k); trial_x = state['x']+dx
                if max(abs(STAR@trial_x)) > self.max_current_a:continue
                try:trial = self._state(trial_x, theta)
                except ValueError as error:
                    if 'B-H range' not in str(error):raise
                    continue
                du, db = self._difference(state, trial)
                change = .5*dx@(trial['b']+state['b'])+.5*(trial_x+state['x'])@db-du
                change += .5*dx@self.D@(trial_x+state['x'])-q@dx
                if change <= 1e-4*2.**(-k)*descent or np.linalg.norm(trial['q']-q) <= tolerance:
                    state = trial; accepted = True; break
            _require(accepted, 'Legendre inverse range or line search failed')
        raise ValueError('Legendre inverse iteration budget exceeded')

    def flux_coordinates(self, currents, theta):
        self._begin(); i = np.asarray(currents, float)
        _require(i.shape == (3,) and np.isfinite(i).all() and abs(i.sum()) <= 1e-10,
                 'Three balanced finite phase currents required')
        return self._state(i[:2], theta)['q'].tolist()

    def phase_flux_angle_derivative(self, currents, theta):
        self._begin(); i = np.asarray(currents, float)
        _require(i.shape == (3,) and np.isfinite(i).all() and abs(i.sum()) <= 1e-10,
                 'Three balanced finite phase currents required')
        return self._state(i[:2], theta)['phase_angle'].copy()

    def energy_gradient(self, q, theta):
        self._begin(); state, error = self._inverse(q, theta); x = state['x']
        return {'energy_j':float(state['U']+.5*x@self.D@x+x@error),
                'current_coordinates_a':x.tolist(),'torque_n_m':state['torque'],
                'flux_linkage_wb_turn':state['phase_flux'].tolist(),
                'inverse_residual_wb_turn':error.tolist(),'field_solves':self._count}

    def energy_difference(self, start, end):
        self._begin(); a, b = np.asarray(start, float), np.asarray(end, float)
        _require(a.shape == b.shape == (3,) and np.isfinite(np.r_[a,b]).all(),
                 'Finite flux/angle endpoints required')
        s0, e0 = self._inverse(a[:2], float(a[2])); s1, _ = self._inverse(b[:2], float(b[2]))
        du, db = self._difference(s0, s1); dx = s1['x']-s0['x']; sx = s1['x']+s0['x']
        de = (b[:2]-a[:2])-db-self.D@dx
        value = du+.5*dx@self.D@sx+.5*dx@(2*e0+de)+.5*sx@de
        _require(np.isfinite(value), 'Nonfinite Hamiltonian difference')
        return float(value)
