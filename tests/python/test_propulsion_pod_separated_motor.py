# SPDX-License-Identifier: Apache-2.0
"""Analytic fixture, not native motor or hardware qualification."""
import math
import unittest
import numpy as np
from scipy.linalg import block_diag
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_separated_motor import SeparatedMotor


def fixture():
    N=12; phi=np.arange(N)*2*math.pi/N
    ring=lambda r: np.column_stack([r*np.cos(phi),r*np.sin(phi)])
    rotor_nodes=np.vstack([[0.,0.],ring(1.)])
    rotor_tri=[[0,1+j,1+(j+1)%N] for j in range(N)]
    stator_nodes=np.vstack([ring(2.),ring(3.)]); stator_tri=[]
    for j in range(N):
        k=(j+1)%N
        stator_tri.extend([[j,k,N+k],[j,N+k,N+j]])
    def domain(nodes,tri,interface,outer,radius,br):
        chi=np.zeros((len(tri),3))
        for j,row in enumerate(tri):
            x=np.mean(nodes[row],axis=0)
            chi[j]=[x[0],x[1],-x[0]-x[1]]
        return dict(nodes_m=nodes.tolist(),triangles=tri,solver_region_ids=['m']*len(tri),
            materials={'m':{'mu_r':2.,'remanence_t':br}},winding_chi_per_m2=chi.tolist(),
            interface_vertex_ids=interface,outer_boundary_vertex_ids=outer,interface_radius_m=radius)
    return dict(rotor_interface_radius_m=1.,stator_interface_radius_m=2.,
        rotor=domain(rotor_nodes,rotor_tri,list(range(1,N+1)),[],1.,[.2,.1]),
        stator=domain(stator_nodes,stator_tri,list(range(N)),list(range(N,2*N)),2.,[0.,0.]),
        source_sha256='analytic-fixture',geometry_sha256='analytic-fixture',
        straight_chord_radial_error_bound_m=2*(1-math.cos(math.pi/N)))


class SeparatedMotorTests(unittest.TestCase):
    def test_condensation_matches_independent_full_variational_solve(self):
        motor=SeparatedMotor(fixture(),stack_depth_m=.01,maximum_mode=3)
        theta=.23; currents=np.array([1.2,-.8,-.4]);z=np.r_[1.,currents]
        transforms=[];loads=[]; count=2*motor.gap.size
        # Full unknowns: both Fourier traces, then ALL interior P2 DOFs.
        total=count+len(motor.rotor.interior)+len(motor.stator.interior)
        K=np.zeros((total,total));f=np.zeros(total);offset=count
        for j,domain in enumerate((motor.rotor,motor.stator)):
            T=np.zeros((len(domain.op.nodes_m),total))
            T[domain.boundary,j*motor.gap.size:(j+1)*motor.gap.size]=domain.V
            T[domain.interior,offset+np.arange(len(domain.interior))]=1
            offset+=len(domain.interior)
            source=domain.op.pm_load
            chi=np.asarray(fixture()['rotor' if j==0 else 'stator']['winding_chi_per_m2'])
            source=source+domain.op.source_load(chi@currents)
            K+=T.T@(domain.op.stiffness@T);f+=T.T@source;transforms.append(T)
        K[:count,:count]+=motor.gap.matrices(theta)[0]
        u=np.linalg.solve(K,f)
        expected=.5*f@u-motor.reference
        actual=motor.evaluate(currents,theta,include_field=True)
        self.assertAlmostEqual(actual['coenergy_j'],expected,places=11)
        for name,T in zip(('rotor','stator'),transforms):
            np.testing.assert_allclose(actual['local_domain_potential_wb_per_m'][name],T@u,atol=1e-16)
        eps=1e-5
        torque_fd=(motor.evaluate(currents,theta+eps)['coenergy_j']-motor.evaluate(currents,theta-eps)['coenergy_j'])/(2*eps)
        self.assertAlmostEqual(actual['torque_n_m'],torque_fd,places=9)
        for j in range(3):
            step=np.eye(3)[j]*.01
            flux_fd=(motor.evaluate(currents+step,theta)['coenergy_j']-motor.evaluate(currents-step,theta)['coenergy_j'])/.02
            self.assertAlmostEqual(actual['flux_linkage_wb_turn'][j],flux_fd,places=10)
        self.assertGreater(np.linalg.norm(motor.R[1:,1:]),0.)

    def test_missing_global_gauge_rejected(self):
        d=fixture();d['stator']['outer_boundary_vertex_ids']=[]
        with self.assertRaisesRegex(ValueError,'actual fixed outer gauge'):SeparatedMotor(d)

    def test_nested_cutoff_reuses_same_variational_space_without_refitting(self):
        high=SeparatedMotor(fixture(),stack_depth_m=.01,maximum_mode=3)
        high.evaluate([.8,-.5,-.3],.13)
        restricted=high.restrict_modes(1)
        direct=SeparatedMotor(fixture(),stack_depth_m=.01,maximum_mode=1)
        for angle in (.13,.49):
            actual=restricted.evaluate([.8,-.5,-.3],angle,include_field=True)
            expected=direct.evaluate([.8,-.5,-.3],angle,include_field=True)
            self.assertAlmostEqual(actual['torque_n_m'],expected['torque_n_m'],places=12)
            self.assertAlmostEqual(actual['coenergy_j'],expected['coenergy_j'],places=12)
            for name in ('rotor','stator'):
                np.testing.assert_allclose(actual['local_domain_potential_wb_per_m'][name],expected['local_domain_potential_wb_per_m'][name],atol=1e-16)
        self.assertEqual(high.gap.maximum_mode,3)
        self.assertIs(restricted.rotor.factor,high.rotor.factor)
        with self.assertRaisesRegex(ValueError,'Cannot extend'):high.restrict_modes(4)
        basis=restricted.basis_potentials(.13)
        field=restricted.evaluate([.8,-.5,-.3],.13,include_field=True)
        for name in ('rotor','stator'):
            np.testing.assert_allclose(basis[name]@np.array([1.,.8,-.5,-.3]),field['local_domain_potential_wb_per_m'][name],atol=1e-16)
        with self.assertRaises(ValueError):restricted.linear_ports(True)


if __name__=='__main__':unittest.main()
