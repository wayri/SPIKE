# SPDX-License-Identifier: Apache-2.0
"""Conforming linear-material P2 Az; experimental, no hardware qualification.

See docs/validation/PROPULSION_POD_MAGNETIC_P2_DERIVATION_20261023.md.
Straight geometry, constant region SPD permeability/remanence and element Jz.
Prepared stiffness and boundary factorization support repeated source solves.
"""
import math
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import splu

MU0 = 4 * math.pi * 1e-7
EDGES = ((0, 1), (0, 2), (1, 2))
QUADRATURE = np.array([[2/3, 1/6, 1/6], [1/6, 2/3, 1/6], [1/6, 1/6, 2/3]])


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def shape_values(barycentric):
    """Qx6 nodal values: vertices then edges01,02,12."""
    l = np.asarray(barycentric, dtype=float)
    _require(l.ndim == 2 and l.shape[1] == 3 and np.isfinite(l).all()
             and np.max(np.abs(l.sum(axis=1)-1)) < 1e-12
             and np.min(l) >= -1e-13, 'Finite triangle barycentric points required')
    return np.column_stack([*(l[:, i]*(2*l[:, i]-1) for i in range(3)),
                            *(4*l[:, i]*l[:, j] for i, j in EDGES)])


class P2MagneticOperator:
    """Prepared straight-triangle operator, SI units and explicit Dirichlet DOFs.

    Material keys: mu_r OR permeability_h_m (scalar or SPD2x2), optional
    remanence_t. A solve reuses its LU when the fixed DOF indices are unchanged.
    No saturation, eddy currents, 3D end turns or geometry qualification.
    """
    def __init__(self, nodes_m, triangles, region_ids, materials, stack_depth_m=1.,
                 *, maximum_triangles=200000, maximum_nodes=500000):
        _require(type(maximum_triangles) is int and 1 <= maximum_triangles <= 200000
                 and type(maximum_nodes) is int and 3 <= maximum_nodes <= 600000,
                 'Explicit bounded mesh budgets required')
        _require(type(stack_depth_m) in (int, float) and math.isfinite(stack_depth_m)
                 and stack_depth_m > 0, 'Positive finite axial depth required')
        self.depth = float(stack_depth_m)
        vertices = np.array(nodes_m, dtype=float, copy=True)
        raw = np.asarray(triangles)
        _require(vertices.ndim == 2 and vertices.shape[1] == 2 and 3 <= len(vertices) <= maximum_nodes
                 and np.isfinite(vertices).all(), 'Finite bounded planar vertices required')
        _require(raw.ndim == 2 and raw.shape[1] == 3 and raw.dtype.kind in 'iu'
                 and 1 <= len(raw) <= maximum_triangles and np.all(raw >= 0)
                 and np.all(raw < len(vertices)), 'Bounded integer triangle indices required')
        tri = raw.astype(np.int64, copy=True)
        _require(len(np.unique(np.sort(tri, axis=1), axis=0)) == len(tri)
                 and len(np.unique(tri)) == len(vertices), 'Duplicate triangles or unused vertices')
        _require(isinstance(region_ids, (list, tuple)) and len(region_ids) == len(tri)
                 and all(isinstance(v, str) and v for v in region_ids)
                 and isinstance(materials, dict) and set(region_ids) == set(materials),
                 'Exact nonempty region/material identity required')
        p = vertices[tri]
        e1, e2 = p[:, 1]-p[:, 0], p[:, 2]-p[:, 0]
        det = e1[:, 0]*e2[:, 1]-e1[:, 1]*e2[:, 0]
        scale = np.maximum(np.sum(e1*e1, axis=1), np.sum(e2*e2, axis=1))
        _require(np.isfinite(det).all() and np.all(abs(det) > 1e-12*scale),
                 'Degenerate or ill-conditioned triangles')
        self.areas = abs(det)/2
        self.barycentric_gradients = np.stack([
            np.stack([p[:, 1, 1]-p[:, 2, 1], p[:, 2, 0]-p[:, 1, 0]], axis=1),
            np.stack([p[:, 2, 1]-p[:, 0, 1], p[:, 0, 0]-p[:, 2, 0]], axis=1),
            np.stack([p[:, 0, 1]-p[:, 1, 1], p[:, 1, 0]-p[:, 0, 0]], axis=1)], axis=1)/det[:, None, None]
        edges = np.sort(tri[:, EDGES].reshape(-1, 2), axis=1)
        unique, inverse, counts = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
        _require(np.max(counts) <= 2, 'Nonmanifold triangle edge')
        _require(len(vertices)+len(unique) <= maximum_nodes, 'P2 node budget exceeded')
        self.vertex_count = len(vertices)
        self.edges = unique
        self._boundary_edges = counts == 1
        self.nodes_m = np.vstack([vertices, vertices[unique].mean(axis=1)])
        self.triangles = tri
        self.triangles_p2 = np.column_stack([tri, self.vertex_count+inverse.reshape(-1, 3)])
        self.region_ids = list(region_ids)
        self.nu = np.empty((len(tri), 2, 2)); self.br = np.empty((len(tri), 2))
        region_array = np.asarray(region_ids)
        for name, material in materials.items():
            _require(isinstance(material, dict) and set(material) <= {'mu_r', 'permeability_h_m', 'remanence_t'}
                     and (('mu_r' in material) != ('permeability_h_m' in material)),
                     'Explicit linear permeability and optional remanence only')
            if 'mu_r' in material:
                _require(type(material['mu_r']) in (int, float), 'Real scalar relative permeability required')
            if 'permeability_h_m' in material:
                _require(np.asarray(material['permeability_h_m']).dtype.kind != 'b', 'Boolean permeability is not a physical value')
            if 'remanence_t' in material:
                _require(np.asarray(material['remanence_t']).dtype.kind != 'b', 'Boolean remanence is not a physical value')
            permeability = np.asarray(material.get('permeability_h_m', MU0*material.get('mu_r', 0.)), dtype=float)
            if permeability.ndim == 0:
                permeability = np.eye(2)*permeability
            _require(permeability.shape == (2, 2) and np.isfinite(permeability).all()
                     and np.allclose(permeability, permeability.T, rtol=1e-13, atol=0),
                     'Finite symmetric permeability required')
            eigen = np.linalg.eigvalsh(permeability)
            _require(eigen[0] > 0 and eigen[-1]/eigen[0] <= 1e10, 'SPD permeability required')
            br = np.asarray(material.get('remanence_t', [0., 0.]), dtype=float)
            _require(br.shape == (2,) and np.isfinite(br).all(), 'Finite planar remanence required')
            mask = region_array == name
            self.nu[mask] = np.linalg.inv(permeability); self.br[mask] = br
        curl = self._curl(QUADRATURE)
        local = self.depth*self.areas[:, None, None]/3*np.einsum('eqia,eab,eqjb->eij', curl, self.nu, curl)
        rows = np.repeat(self.triangles_p2, 6, axis=1).ravel()
        cols = np.tile(self.triangles_p2, (1, 6)).ravel()
        self.stiffness = coo_matrix((local.ravel(), (rows, cols)), shape=(len(self.nodes_m),)*2).tocsr()
        pm_local = self.depth*self.areas[:, None]/3*np.einsum('eqia,eab,eb->ei', curl, self.nu, self.br)
        self.pm_load = np.zeros(len(self.nodes_m))
        np.add.at(self.pm_load, self.triangles_p2.ravel(), pm_local.ravel())
        self.pm_reference_j = float(.5*self.depth*np.einsum('e,ea,eab,eb->', self.areas, self.br, self.nu, self.br))
        _require(np.isfinite(self.stiffness.data).all() and np.isfinite(self.pm_load).all()
                 and math.isfinite(self.pm_reference_j), 'Magnetic assembly exceeds numerical range')
        graph = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=self.stiffness.shape).tocsr()
        self.component_count, self.component_labels = connected_components(graph, directed=False)
        self._fixed_key = None; self._factor = None; self.factorization_count = 0

    def boundary_dofs(self, vertex_ids):
        """Extend fixed original boundary vertices to topological boundary edges.

        Interior chords joining two boundary vertices are deliberately excluded.
        Other explicitly fixed midside DOFs may be supplied directly to solve.
        """
        ids = np.asarray(list(vertex_ids))
        _require(ids.ndim == 1 and ids.dtype.kind in 'iu' and len(ids) > 0
                 and np.all(ids >= 0) and np.all(ids < self.vertex_count), 'Original fixed vertices required')
        selected = np.zeros(self.vertex_count, dtype=bool); selected[ids] = True
        middle = np.flatnonzero(self._boundary_edges & np.all(selected[self.edges], axis=1))+self.vertex_count
        return np.unique(np.r_[ids, middle]).tolist()

    def _curl(self, barycentric):
        l = np.asarray(barycentric, dtype=float)
        shape_values(l)  # shared admission, including barycentric sum
        g = self.barycentric_gradients
        grad = np.stack([*((4*l[:, i]-1)[None, :, None]*g[:, None, i, :] for i in range(3)),
                         *(4*(l[:, i][None, :, None]*g[:, None, j, :]+l[:, j][None, :, None]*g[:, None, i, :]) for i, j in EDGES)], axis=2)
        return np.stack([grad[..., 1], -grad[..., 0]], axis=-1)

    def source_load(self, current_density_a_per_m2=None):
        """Depth-weighted integral J Ni; constant element J, vertex integrals0."""
        if current_density_a_per_m2 is None:
            j = np.zeros(len(self.triangles))
        elif isinstance(current_density_a_per_m2, dict):
            _require(set(current_density_a_per_m2) <= set(self.region_ids), 'Unknown source region')
            j = np.asarray([current_density_a_per_m2.get(k, 0.) for k in self.region_ids], dtype=float)
        else:
            j = np.asarray(current_density_a_per_m2, dtype=float)
        _require(j.shape == (len(self.triangles),) and np.isfinite(j).all(), 'Finite elementwise Jz required')
        load = np.zeros(len(self.nodes_m))
        np.add.at(load, self.triangles_p2[:, 3:].ravel(), np.repeat(self.depth*self.areas*j/3, 3))
        _require(np.isfinite(load).all(), 'Current load exceeds numerical range')
        return load

    def evaluate_b(self, potential, barycentric=QUADRATURE):
        a = np.asarray(potential, dtype=float)
        _require(a.shape == (len(self.nodes_m),) and np.isfinite(a).all(), 'Finite P2 nodal potential required')
        return np.einsum('eqia,ei->eqa', self._curl(barycentric), a[self.triangles_p2])

    def solve(self, current_density_a_per_m2=None, *, dirichlet_a_wb_per_m):
        boundary = dirichlet_a_wb_per_m
        _require(isinstance(boundary, dict) and boundary and all(type(k) is int and 0 <= k < len(self.nodes_m) for k in boundary),
                 'Explicit valid P2 Dirichlet indices required')
        a = np.zeros(len(self.nodes_m))
        for k, value in boundary.items():
            _require(type(value) in (int, float) and math.isfinite(value), 'Finite Dirichlet values required')
            a[k] = value
        fixed = np.array(sorted(boundary), dtype=int); key = tuple(fixed)
        _require(set(self.component_labels[fixed]) == set(range(self.component_count)), 'Every connected component needs a Dirichlet gauge')
        free = np.setdiff1d(np.arange(len(a)), fixed)
        load = self.pm_load+self.source_load(current_density_a_per_m2)
        rhs = (load-self.stiffness@a)[free]
        reused = key == self._fixed_key
        if len(free):
            if not reused:
                factor = splu(self.stiffness[free][:, free].tocsc())
                _require(factor.L.nnz+factor.U.nnz <= 30000000, 'P2 factor memory budget exceeded')
                self._factor = factor; self._fixed_key = key; self.factorization_count += 1
            a[free] = self._factor.solve(rhs)
        residual = self.stiffness@a-load
        error = float(np.linalg.norm(residual[free])); scale = max(float(np.linalg.norm(rhs)), 1e-30)
        _require(np.isfinite(a).all() and error <= 1e-10+1e-9*scale, 'P2 magnetic linear residual failed')
        B = self.evaluate_b(a); shifted = B-self.br[:, None, :]
        energy = float(.5*self.depth/3*np.einsum('e,eqa,eab,eqb->', self.areas, shifted, self.nu, shifted))
        current_load = load-self.pm_load
        coenergy = float(a@current_load-energy)
        _require(math.isfinite(energy) and math.isfinite(coenergy), 'P2 magnetic energy exceeds numerical range')
        return {'potential_a_wb_per_m': a.tolist(), 'quadrature_b_t': B.tolist(),
                'quadrature_barycentric': QUADRATURE.tolist(), 'magnetic_energy_j': energy,
                'current_source_coenergy_j': coenergy, 'pm_reference_j': self.pm_reference_j,
                'diagnostics': {'converged': True, 'free_residual_a_m': error,
                                'relative_free_residual': error/scale, 'factorization_reused': reused,
                                'factorization_count': self.factorization_count, 'p2_nodes': len(a),
                                'triangles': len(self.triangles), 'production_qualified': False}}
