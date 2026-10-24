# SPDX-License-Identifier: Apache-2.0
"""Experimental static P2 domains joined by a rotating Fourier vacuum gap.

One quadratic coenergy governs flux and torque at every angle. Straight trace
geometry, Fourier truncation and substituted materials need separate refinement
and hardware validation; this module does not confer those qualifications.
"""
import copy
import math
import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.sparse.linalg import splu
from .propulsion_pod_annular_gap import AnnularGap
from .propulsion_pod_magnetic_p2 import P2MagneticOperator
from .propulsion_pod_real_motor_domains import p2_interface_trace
from .propulsion_pod_field_preview import magnetic_preview


class _Domain:
    def __init__(self, domain, gap, depth):
        self.op = op = P2MagneticOperator(domain['nodes_m'], domain['triangles'],
            domain['solver_region_ids'], domain['materials'], depth)
        trace = p2_interface_trace(op, domain)
        self.boundary = b = np.asarray(trace['dof_ids'], int)
        self.V = V = gap.trace_basis(trace['angles_rad'])
        singular = np.linalg.svd(V, compute_uv=False)
        if V.shape[1] >= V.shape[0] or singular[-1] < singular[0]*1e-10:
            raise ValueError('Fourier trace must be independently resolved and full rank')
        outer = op.boundary_dofs(domain['outer_boundary_vertex_ids']) if domain['outer_boundary_vertex_ids'] else np.array([], int)
        if np.intersect1d(b, outer).size:
            raise ValueError('Interface and fixed outer trace overlap')
        fixed = np.r_[b, outer]
        if set(op.component_labels[fixed]) != set(range(op.component_count)):
            raise ValueError('Unanchored static magnetic component')
        self.interior = i = np.setdiff1d(np.arange(len(op.nodes_m)), fixed)
        K = op.stiffness
        self.Kib = K[i][:, b].tocsc()
        Kbi = self.Kib.T
        self.factor = splu(K[i][:, i].tocsc())
        chi = np.asarray(domain['winding_chi_per_m2'], float)
        if chi.shape != (len(op.triangles), 3) or not np.isfinite(chi).all():
            raise ValueError('Three finite winding source columns required')
        F = np.column_stack([op.pm_load, *(op.source_load(chi[:, j]) for j in range(3))])
        self.Xf = self.factor.solve(F[i])
        self.R = F[i].T @ self.Xf
        self.G = V.T @ (F[b] - Kbi @ self.Xf)
        S = V.T @ (K[b][:, b] @ V)
        # Bounded right-hand-side batches avoid retaining an interior x modes array.
        for lo in range(0, V.shape[1], 24):
            hi = min(lo+24, V.shape[1])
            S[:, lo:hi] -= V.T @ (Kbi @ self.factor.solve(self.Kib @ V[:, lo:hi]))
        asymmetry = np.linalg.norm(S-S.T)/max(np.linalg.norm(S), 1e-300)
        if not np.isfinite(S).all() or asymmetry > 1e-9:
            raise ValueError('Condensed domain failed reciprocity')
        self.S = (S+S.T)/2
        self.trace = trace
        self.region_ids = list(domain.get('region_ids',domain['solver_region_ids']))
        self.reciprocity_error = float(asymmetry)

    def recover(self, coefficients, currents):
        A = np.zeros(len(self.op.nodes_m))
        A[self.boundary] = self.V @ coefficients
        A[self.interior] = self.Xf @ np.r_[1., currents] - self.factor.solve(self.Kib @ A[self.boundary])
        return A


class SeparatedMotor:
    """Linear constitutive motor; theta is mechanical radians, currents amperes."""
    def __init__(self, domains, stack_depth_m=.025, maximum_mode=127):
        if not domains['rotor']['outer_boundary_vertex_ids'] and not domains['stator']['outer_boundary_vertex_ids']:
            raise ValueError('Coupled magnetic domains require an actual fixed outer gauge')
        self.gap = AnnularGap(domains['rotor_interface_radius_m'],
            domains['stator_interface_radius_m'], stack_depth_m, maximum_mode)
        self.rotor = _Domain(domains['rotor'], self.gap, stack_depth_m)
        self.stator = _Domain(domains['stator'], self.gap, stack_depth_m)
        self.G = np.vstack([self.rotor.G, self.stator.G])
        self.R = self.rotor.R+self.stator.R
        self.reference = self.rotor.op.pm_reference_j+self.stator.op.pm_reference_j
        self.source_sha256 = domains['source_sha256']
        self.geometry_sha256 = domains['geometry_sha256']
        self.spec_sha256 = domains.get('spec_sha256')
        self.chord_error_m = domains['straight_chord_radial_error_bound_m']
        self._cached_angle=None;self._cached_ports=None

    def restrict_modes(self, maximum_mode):
        """Reuse exact static condensation for a nested lower Fourier space.

        This avoids remeshing or refactorizing during cutoff comparisons. The
        low-mode basis is literally the leading columns of the prepared basis.
        No high-mode coefficients are fitted into the restricted space.
        """
        gap=AnnularGap(self.gap.a,self.gap.b,self.gap.depth,maximum_mode)
        if maximum_mode>self.gap.maximum_mode:
            raise ValueError('Cannot extend a prepared Fourier space by restriction')
        out=copy.copy(self);out.gap=gap
        out._cached_angle=None;out._cached_ports=None
        for name in ('rotor','stator'):
            original=getattr(self,name);domain=copy.copy(original)
            domain.V=original.V[:,:gap.size]
            domain.S=original.S[:gap.size,:gap.size]
            domain.G=original.G[:gap.size]
            setattr(out,name,domain)
        out.G=np.vstack([out.rotor.G,out.stator.G])
        return out

    def _ports(self, angle):
        if type(angle) not in (int,float) or not math.isfinite(angle):
            raise ValueError('Finite mechanical angle required')
        if angle==self._cached_angle:return self._cached_ports
        K, derivative = self.gap.matrices(angle)
        m = self.gap.size
        K[:m, :m] += self.rotor.S
        K[m:, m:] += self.stator.S
        X = cho_solve(cho_factor(K, lower=True), self.G)
        residual = np.linalg.norm(K @ X-self.G)/max(np.linalg.norm(self.G), 1e-300)
        if not np.isfinite(X).all() or residual > 1e-8:
            raise ValueError('Coupled annular solve failed residual gate')
        M = self.G.T @ X+self.R
        D = -X.T @ derivative @ X
        result=((M+M.T)/2, (D+D.T)/2, X, float(residual))
        self._cached_angle=angle;self._cached_ports=result
        return result

    def basis_potentials(self, angle_rad):
        """Four source columns: PM-only, phase-A/B/C unit-current response.

        An actual field at currents i is A_basis @ [1,iA,iB,iC]. Only the
        first column contains PM excitation. These are full local P2 DOFs.
        """
        _,_,X,_=self._ports(angle_rad);out={}
        for j,(name,domain) in enumerate((('rotor',self.rotor),('stator',self.stator))):
            A=np.zeros((len(domain.op.nodes_m),4))
            A[domain.boundary]=domain.V@X[j*self.gap.size:(j+1)*self.gap.size]
            A[domain.interior]=domain.Xf-domain.factor.solve(domain.Kib@A[domain.boundary])
            out[name]=A
        return out

    def linear_ports(self, angle_rad):
        M, D, _, residual = self._ports(angle_rad)
        return {'inductance_h': M[1:, 1:].tolist(),
            'pm_flux_linkage_wb_turn': M[1:, 0].tolist(),
            'coenergy_zero_current_j': float(.5*M[0, 0]-self.reference),
            'inductance_derivative_h_per_rad': D[1:, 1:].tolist(),
            'pm_flux_derivative_wb_turn_per_rad': D[1:, 0].tolist(),
            'coenergy_zero_current_derivative_j_per_rad': float(.5*D[0, 0]),
            'solver_errors': {'relative_residual': residual},
            'mesh_diagnostics': {'fourier_maximum_mode': self.gap.maximum_mode,
                'straight_chord_radial_error_bound_m': self.chord_error_m},
            'source_sha256':self.source_sha256,'geometry_sha256':self.geometry_sha256,
            'spec_sha256':self.spec_sha256,
            'physical_qualified': False, 'production_qualified': False}

    def evaluate(self, currents_a, angle_rad, include_field=False):
        if type(include_field) is not bool:
            raise ValueError('Field recovery flag must be boolean')
        currents = np.asarray(currents_a, float)
        if currents.shape != (3,) or not np.isfinite(currents).all():
            raise ValueError('Three finite physical phase currents required')
        M, D, X, residual = self._ports(angle_rad)
        z = np.r_[1., currents]
        flux = M[1:] @ z
        coenergy = float(.5*z @ M @ z-self.reference)
        coefficients = X @ z
        if not np.isfinite(np.r_[flux, coenergy, .5*z @ D @ z, coefficients]).all():
            raise ValueError('Motor result exceeds finite numerical range')
        result = {'torque_n_m': float(.5*z @ D @ z),
            'flux_linkage_wb_turn': flux.tolist(), 'coenergy_j': coenergy,
            'magnetic_energy_j': float(currents @ flux-coenergy),
            'relative_residual': residual,
            'rotor_fourier_coefficients': coefficients[:self.gap.size].tolist(),
            'stator_fourier_coefficients': coefficients[self.gap.size:].tolist(),
            'physical_qualified': False}
        if include_field:
            result['local_domain_potential_wb_per_m'] = {
                'rotor': self.rotor.recover(coefficients[:self.gap.size], currents).tolist(),
                'stator': self.stator.recover(coefficients[self.gap.size:], currents).tolist()}
        return result

    def field_snapshot(self, currents_a, angle_rad, grid_nodes=49, gap_angular_nodes=257):
        """World-frame samples of this solved P2 field and analytic vacuum gap.

        Display patches are sampled source fields, not solver elements. No
        temporal interpolation or invented intermediate field is performed.
        """
        if type(gap_angular_nodes) is not int or not 17<=gap_angular_nodes<=1025:
            raise ValueError('Bounded gap angular display resolution required')
        result=self.evaluate(currents_a,angle_rad,include_field=True)
        c=np.cos(angle_rad);s=np.sin(angle_rad);rotation=np.array([[c,-s],[s,c]])
        previews={}
        for name,domain in (('rotor',self.rotor),('stator',self.stator)):
            op=domain.op;A=np.array(result['local_domain_potential_wb_per_m'][name])
            xy=op.nodes_m[:op.vertex_count].copy()
            B=op.evaluate_b(A,np.eye(3))
            if name=='rotor':xy=xy@rotation.T;B=B@rotation.T
            field={'nodes_m':xy.tolist(),'triangles':op.triangles.tolist(),
                'region_ids':domain.region_ids,'element_b_t':B.mean(axis=1).tolist(),
                'p2_barycentric_b_t':B.tolist()}
            previews[name]=magnetic_preview(field,grid_nodes)
        phi=np.arange(gap_angular_nodes)*2*np.pi/gap_angular_nodes
        radius=(self.gap.a+self.gap.b)/2
        gap=self.gap.field(result['rotor_fourier_coefficients'],result['stator_fourier_coefficients'],angle_rad,radius,phi)
        Br=gap['radial_b_t'];Bp=gap['azimuthal_b_t']
        return {'angle_rad':float(angle_rad),'currents_a':list(currents_a),
            'torque_n_m':result['torque_n_m'],'domains':previews,
            'gap':{'nodes_m':np.column_stack([radius*np.cos(phi),radius*np.sin(phi)]).tolist(),
                'b_t':np.column_stack([Br*np.cos(phi)-Bp*np.sin(phi),Br*np.sin(phi)+Bp*np.cos(phi)]).tolist(),
                'potential_a_wb_per_m':gap['potential_a_wb_per_m'].tolist(),
                'sampling':'analytic harmonic gap field at actual solved angle'},
            'world_frame':True,'physical_qualified':False,'source_sha256':self.source_sha256,
            'geometry_sha256':self.geometry_sha256}
