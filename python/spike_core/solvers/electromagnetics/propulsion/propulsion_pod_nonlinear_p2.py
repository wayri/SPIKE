# SPDX-License-Identifier: Apache-2.0
"""Experimental supplied-law P2 magnetostatics; no actual-motor qualification.

See docs/validation/PROPULSION_POD_NONLINEAR_P2_20261023.md. A prepared linear
P2 mesh supplies unchanged geometry, linear tensor/PM laws and current loads.
Explicit region B-H replacements supersede its linear law entirely.
"""
import copy
import hashlib
import json
import math

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import splu

from ..machines.magnetic_fem import MagneticMaterial
from .propulsion_pod_magnetic_p2 import P2MagneticOperator, _require


def _json_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode('utf-8')).hexdigest()


def _arrays_digest(arrays):
    """Canonical named, shaped little-endian arrays; no large JSON expansion."""
    digest = hashlib.sha256()
    for name, value in sorted(arrays.items()):
        array = np.asarray(value)
        dtype = '<f8' if array.dtype.kind == 'f' else '<i8'
        array = np.ascontiguousarray(array, dtype=dtype)
        digest.update(json.dumps([name, list(array.shape), dtype], separators=(',', ':')).encode('utf-8'))
        digest.update(memoryview(array).cast('B'))
    return digest.hexdigest()


def _operator_digest(base):
    names = ('nodes_m', 'triangles', 'triangles_p2', 'edges', 'barycentric_gradients',
             'areas', 'nu', 'br', 'component_labels', '_boundary_edges', 'pm_load')
    arrays = {name: getattr(base, name) for name in names}
    arrays.update({'stiffness_data': base.stiffness.data, 'stiffness_indices': base.stiffness.indices,
                   'stiffness_indptr': base.stiffness.indptr})
    return _json_digest({'schema': 'spike/p2-wrapped-operator/v1', 'arrays': _arrays_digest(arrays),
                         'stiffness_shape': base.stiffness.shape, 'depth_m': base.depth,
                         'region_ids': base.region_ids, 'vertex_count': base.vertex_count,
                         'component_count': base.component_count, 'pm_reference_j': base.pm_reference_j})


def triangle_quadrature(order):
    """Positive product Gauss rule, normalized to triangle area."""
    _require(type(order) is int and 2 <= order <= 16, 'Quadrature order must be 2..16')
    x, w = np.polynomial.legendre.leggauss(order)
    x, w = (x+1)/2, w/2
    s, t = np.meshgrid(x, x, indexing='ij')
    weights = (2*s*w[:, None]*w[None, :]).ravel()
    return np.column_stack([(1-s).ravel(), (s*(1-t)).ravel(), (s*t).ravel()]), weights


def _tangent_batch_size(quadrature_points):
    """8 MiB modeled scratch, excluding full output and native workspace."""
    bytes_per_element = 4*quadrature_points*6*2*8 + 6*6*8
    return min(1024, max(1, (8*1024*1024)//bytes_per_element))


def _local_tangents(volume_weights, curl, tangent):
    """Batch only the unsummed element index; retain local/COO ordering."""
    elements, quadrature_points = volume_weights.shape
    result = np.empty((elements, 6, 6), dtype=float)
    batch = _tangent_batch_size(quadrature_points)
    for start in range(0, elements, batch):
        end = min(start+batch, elements)
        np.einsum('eq,eqia,eqab,eqjb->eij', volume_weights[start:end],
                  curl[start:end], tangent[start:end], curl[start:end],
                  optimize=True, out=result[start:end])
    return result


class NonlinearP2MagneticOperator:
    """Energy/residual/tangent assembly with immutable supplied-law snapshots.

    bh_curves maps existing region names to [B_t,H_a_per_m] pairs. Other
    regions retain their exact tensor permeability and fixed remanence. The
    prepared base must not be mutated while this adapter is in use.
    """
    def __init__(self, linear_operator, bh_curves, *, quadrature_order=4,
                 maximum_quadrature_points=2000000):
        _require(isinstance(linear_operator, P2MagneticOperator), 'Prepared P2 operator required')
        _require(isinstance(bh_curves, dict) and set(bh_curves) <= set(linear_operator.region_ids),
                 'B-H replacements must name existing regions')
        _require(type(maximum_quadrature_points) is int and 1 <= maximum_quadrature_points <= 2000000,
                 'Quadrature point budget must be 1..2000000')
        self.base = linear_operator
        self.barycentric, self.weights = triangle_quadrature(quadrature_order)
        self.quadrature_order = quadrature_order
        _require(len(self.weights)*len(self.base.triangles) <= maximum_quadrature_points,
                 'Nonlinear P2 quadrature point budget exceeded')
        self.materials = {}
        regions = np.asarray(self.base.region_ids)
        for region, curve in bh_curves.items():
            indices = np.flatnonzero(regions == region)
            _require(not np.any(self.base.br[indices]), 'Nonlinear replacement of remanence is forbidden')
            _require(np.asarray(curve).dtype.kind in 'iuf', 'Real B-H values required')
            material = MagneticMaterial({'bh_curve': np.array(curve, dtype=float, copy=True)})
            self.materials[region] = (indices, material)
        self.curl = self.base._curl(self.barycentric)
        self.vertex_curl = self.base._curl(np.eye(3))
        self.rows = np.repeat(self.base.triangles_p2, 6, axis=1).ravel()
        self.cols = np.tile(self.base.triangles_p2, (1, 6)).ravel()
        self.volume_weights = self.base.depth*self.base.areas[:, None]*self.weights
        self._base_object = self.base
        self._reference_digest = _operator_digest(self.base)
        first = {}
        for index, region in enumerate(self.base.region_ids):
            first.setdefault(region, index)
        laws = {}
        for region, index in sorted(first.items()):
            if region in self.materials:
                material = self.materials[region][1]
                laws[region] = {'law': 'supplied-isotropic-single-valued-piecewise-linear-bh',
                                'bh_curve': np.column_stack([material.b, material.h]).tolist(),
                                'curve_columns': ['B_t', 'H_a_per_m'],
                                'admitted_b_range_t': [0., float(material.b[-1])],
                                'extrapolation': 'forbidden', 'provenance': 'caller-supplied-unverified',
                                'material_qualified': False}
            else:
                laws[region] = {'law': 'supplied-linear-tensor-recoil',
                                'reluctivity_m_per_h': self.base.nu[index].tolist(),
                                'remanence_t': self.base.br[index].tolist(),
                                'energy_reference': 'half-(B-Br)-nu-(B-Br)',
                                'provenance': 'prepared-operator-supplied-unverified',
                                'material_qualified': False}
        self._constitutive_descriptor = {
            'schema': 'spike/nonlinear-p2-constitutive/v1', 'region_laws': laws,
            'stack_depth_m': self.base.depth, 'reference_operator_sha256': self._reference_digest,
            'quadrature': {'rule': 'positive-product-gauss-square-to-triangle',
                           'order': self.quadrature_order, 'barycentric': self.barycentric.tolist(),
                           'normalized_weights': self.weights.tolist()},
            'material_qualified': False, 'quadrature_converged': False}
        self.constitutive_sha256 = _json_digest(self._constitutive_descriptor)
        for array in (self.curl, self.vertex_curl, self.rows, self.cols, self.volume_weights,
                      self.barycentric, self.weights):
            array.setflags(write=False)
        for indices, material in self.materials.values():
            for array in (indices, material.b, material.h, material.slopes, material.integrals, material.br):
                array.setflags(write=False)
        self._state_digest = self._owned_state_digest()

    def _owned_state_digest(self):
        arrays = {name: getattr(self, name) for name in
                  ('curl', 'vertex_curl', 'rows', 'cols', 'volume_weights', 'barycentric', 'weights')}
        for name, (indices, material) in self.materials.items():
            _require(material.mu is None, 'Nonlinear P2 material law changed')
            arrays[name+'/indices'] = indices
            for field in ('b', 'h', 'slopes', 'integrals', 'br'):
                arrays[name+'/'+field] = getattr(material, field)
        return _arrays_digest(arrays)

    def validate_dependencies(self):
        """Guard at operation boundaries, never inside a coupled tangent matvec."""
        _require(self.base is self._base_object and _operator_digest(self.base) == self._reference_digest
                 and self._owned_state_digest() == self._state_digest
                 and self.quadrature_order == self._constitutive_descriptor['quadrature']['order']
                 and _json_digest(self._constitutive_descriptor) == self.constitutive_sha256,
                 'Nonlinear P2 dependencies changed; prepare a new operator and identity')

    def constitutive_identity(self):
        """Detached exact supplied-law description; source authenticity is not inferred."""
        self.validate_dependencies()
        return {'constitutive_sha256': self.constitutive_sha256,
                'constitutive_model': copy.deepcopy(self._constitutive_descriptor)}

    def assemble(self, potential_a_wb_per_m, current_density_a_per_m2=None):
        """Return NumPy fields, CSR tangent and SI energies for coupled assembly.

        Residual includes current source, PM H includes its own source exactly
        once. Do not add base.pm_load to this residual. Range is checked over
        whole elements, not just integration points. No field state is saved.
        """
        self.validate_dependencies()
        result = self._assemble_verified(potential_a_wb_per_m, current_density_a_per_m2)
        result.update(self.constitutive_identity())
        return result

    def energy_difference(self, initial, final):
        """Local polarized energy difference on the unchanged quadrature rule."""
        self.validate_dependencies()
        a, b = np.asarray(initial, float), np.asarray(final, float)
        _require(a.shape == b.shape == (len(self.base.nodes_m),)
                 and np.isfinite(np.r_[a, b]).all(), 'Finite aligned potential endpoints required')
        local = self.base.triangles_p2
        b0 = np.einsum('eqia,ei->eqa', self.curl, a[local])
        db = np.einsum('eqia,ei->eqa', self.curl, (b-a)[local])
        b1 = b0+db
        values = .5*np.einsum('eqa,eab,eqb->eq', db, self.base.nu,
                              2*b0+db-2*self.base.br[:, None, :])
        for indices, material in self.materials.values():
            for vector in (a, b):
                vertex = np.einsum('eqia,ei->eqa', self.vertex_curl[indices], vector[local[indices]])
                _require(np.all(np.linalg.norm(vertex, axis=2) <= material.b[-1]*(1+1e-13)),
                         'Field exceeds supplied B-H range; extrapolation is forbidden')
            r0 = np.linalg.norm(b0[indices], axis=2)
            r1 = np.linalg.norm(b1[indices], axis=2)
            denominator = r0+r1
            dr = np.divide(np.sum(db[indices]*(2*b0[indices]+db[indices]), axis=2),
                           denominator, out=np.zeros_like(r0), where=denominator>0)
            # Split only intervals crossing a supplied knot. The direct small
            # interval formula retains dr when rounded r0+dr would equal r0.
            lower = np.minimum(r0, r1); upper = np.maximum(r0, r1)
            integral = np.zeros_like(r0)
            segment = np.clip(np.searchsorted(material.b, r0, side='right')-1,
                              0, len(material.slopes)-1)
            segment = np.where((dr < 0) & (r0 == material.b[segment]) & (segment > 0),
                               segment-1, segment)
            for j, slope in enumerate(material.slopes):
                lo = np.maximum(lower, material.b[j]); hi = np.minimum(upper, material.b[j+1])
                width = np.maximum(hi-lo, 0.)
                same = (lower >= material.b[j]) & (upper <= material.b[j+1]) & (segment == j)
                width = np.where(same, np.abs(dr), width)
                integral += width*(material.h[j]+slope*((lo-material.b[j])+.5*width))
            values[indices] = np.sign(dr)*integral
        result = float(np.sum(self.volume_weights*values))
        _require(math.isfinite(result), 'Magnetic energy difference exceeds finite range')
        self.validate_dependencies()
        return result

    def _assemble_verified(self, potential_a_wb_per_m, current_density_a_per_m2=None):
        """Internal path inside a caller's entry/exit dependency-guarded operation."""
        a = np.asarray(potential_a_wb_per_m, dtype=float)
        _require(a.shape == (len(self.base.nodes_m),) and np.isfinite(a).all(),
                 'Finite P2 nodal potential required')
        local_a = a[self.base.triangles_p2]
        b = np.einsum('eqia,ei->eqa', self.curl, local_a)
        shifted = b-self.base.br[:, None, :]
        h = np.einsum('eab,eqb->eqa', self.base.nu, shifted)
        tangent = np.broadcast_to(self.base.nu[:, None], (*b.shape[:2], 2, 2)).copy()
        energy = .5*np.einsum('eqa,eqa->eq', shifted, h)
        vertex_b = np.einsum('eqia,ei->eqa', self.vertex_curl, local_a)
        for indices, material in self.materials.values():
            _require(np.all(np.linalg.norm(vertex_b[indices], axis=2) <= material.b[-1]*(1+1e-13)),
                     'Field exceeds supplied B-H range at element vertex; extrapolation is forbidden')
            hh, dd, ww, _ = material.evaluate(b[indices].reshape(-1, 2))
            shape = b[indices].shape[:2]
            h[indices] = hh.reshape(*shape, 2)
            tangent[indices] = dd.reshape(*shape, 2, 2)
            energy[indices] = ww.reshape(shape)
        load = self.base.source_load(current_density_a_per_m2)
        residual = -load.copy()
        local_r = np.einsum('eq,eqia,eqa->ei', self.volume_weights, self.curl, h)
        np.add.at(residual, self.base.triangles_p2.ravel(), local_r.ravel())
        local_k = _local_tangents(self.volume_weights, self.curl, tangent)
        stiffness = coo_matrix((local_k.ravel(), (self.rows, self.cols)),
                               shape=(len(a), len(a))).tocsr()
        total_energy = float(np.sum(self.volume_weights*energy))
        material_coenergy = float(np.sum(self.volume_weights*(np.sum(h*b, axis=2)-energy)))
        potential = total_energy-float(load@a)
        _require(all(np.isfinite(v).all() for v in (residual, stiffness.data, b, h, energy))
                 and all(math.isfinite(v) for v in (total_energy, material_coenergy, potential)),
                 'Nonlinear P2 assembly exceeds numerical range')
        return {'residual_a_m': residual, 'tangent_a_m2_per_wb': stiffness,
                'quadrature_b_t': b, 'quadrature_h_a_per_m': h,
                'quadrature_energy_j_per_m3': energy, 'magnetic_energy_j': total_energy,
                'magnetic_material_coenergy_j': material_coenergy,
                'current_source_coenergy_j': -potential, 'potential_j': potential,
                'pm_reference_j': self.base.pm_reference_j}

    @staticmethod
    def _linear_solve(matrix, rhs):
        try:
            factor = splu(matrix.tocsc())
        except RuntimeError as exc:
            raise ValueError('Nonlinear P2 tangent factorization failed') from exc
        _require(factor.L.nnz+factor.U.nnz <= 30000000, 'P2 factor memory budget exceeded')
        step = factor.solve(rhs)
        error = float(np.linalg.norm(matrix@step-rhs))
        _require(np.isfinite(step).all() and error <= 1e-12+1e-8*np.linalg.norm(rhs),
                 'Nonlinear P2 tangent linear residual failed')
        return step

    def solve(self, current_density_a_per_m2=None, *, dirichlet_a_wb_per_m,
              initial_a_wb_per_m=None, relative_tolerance=1e-9,
              absolute_tolerance_a_m=1e-10, maximum_iterations=60):
        """Bounded damped Newton; failed steps do not mutate caller state.

        Nonzero boundary data need a supplied feasible initial field or use the
        base stiffness harmonic extension as an initial guess only. The base
        linear material law is never used as the final nonlinear result.
        """
        self.validate_dependencies()
        for value in (relative_tolerance, absolute_tolerance_a_m):
            _require(type(value) in (int, float) and math.isfinite(value) and value > 0,
                     'Positive finite residual tolerances required')
        _require(relative_tolerance <= .01, 'Relative tolerance must be <= .01')
        _require(type(maximum_iterations) is int and 1 <= maximum_iterations <= 200,
                 'Maximum iterations must be 1..200')
        boundary = dirichlet_a_wb_per_m
        n = len(self.base.nodes_m)
        _require(isinstance(boundary, dict) and boundary
                 and all(type(k) is int and 0 <= k < n for k in boundary),
                 'Explicit valid P2 Dirichlet indices required')
        a = np.zeros(n) if initial_a_wb_per_m is None else np.array(initial_a_wb_per_m, dtype=float, copy=True)
        _require(a.shape == (n,) and np.isfinite(a).all(), 'Finite initial P2 potential required')
        for k, value in boundary.items():
            _require(type(value) in (int, float) and math.isfinite(value), 'Finite Dirichlet values required')
            a[k] = value
        fixed = np.array(sorted(boundary), dtype=int)
        _require(set(self.base.component_labels[fixed]) == set(range(self.base.component_count)),
                 'Every connected component needs a Dirichlet gauge')
        free = np.setdiff1d(np.arange(n), fixed)
        if initial_a_wb_per_m is None and len(free) and np.any(a[fixed]):
            k = self.base.stiffness
            a[free] = self._linear_solve(k[free][:, free], -(k@a)[free])
        state = self._assemble_verified(a, current_density_a_per_m2)
        history = [float(np.linalg.norm(state['residual_a_m'][free]))]
        threshold = absolute_tolerance_a_m+relative_tolerance*history[0]
        steps = []
        while history[-1] > threshold and len(steps) < maximum_iterations:
            residual = state['residual_a_m'][free]
            tangent = state['tangent_a_m2_per_wb'][free][:, free]
            delta = self._linear_solve(tangent, -residual)
            descent = float(residual@delta)
            _require(math.isfinite(descent) and descent < 0, 'Newton direction is not descent')
            alpha, accepted = 1., False
            for _ in range(48):
                trial_a = a.copy()
                trial_a[free] += alpha*delta
                try:
                    trial = self._assemble_verified(trial_a, current_density_a_per_m2)
                except ValueError as exc:
                    if 'B-H range' not in str(exc):
                        raise
                    alpha *= .5
                    continue
                norm = float(np.linalg.norm(trial['residual_a_m'][free]))
                rounding = 64*np.finfo(float).eps*max(abs(state['potential_j']), abs(trial['potential_j']), 1e-30)
                if trial['potential_j'] <= state['potential_j']+1e-4*alpha*descent+rounding or norm <= threshold:
                    a, state, accepted = trial_a, trial, True
                    history.append(norm)
                    steps.append(alpha)
                    break
                alpha *= .5
            _require(accepted, 'Nonlinear P2 Newton line search failed; check B-H range and conditioning')
        _require(history[-1] <= threshold, 'Nonlinear P2 Newton did not converge')
        return {'potential_a_wb_per_m': a, **state,
                **self.constitutive_identity(),
                'quadrature_barycentric': self.barycentric.copy(), 'quadrature_weights': self.weights.copy(),
                'dirichlet_reaction_a_m': {int(k): float(state['residual_a_m'][k]) for k in fixed},
                'diagnostics': {'converged': True, 'free_residual_a_m': history[-1],
                                'residual_threshold_a_m': threshold, 'residual_history_a_m': history,
                                'newton_step_lengths': steps, 'iterations': len(steps),
                                'quadrature_order': self.quadrature_order,
                                'quadrature_converged': False, 'material_qualified': False,
                                'production_qualified': False}}
