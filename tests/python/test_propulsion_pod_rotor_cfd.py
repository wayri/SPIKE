# SPDX-License-Identifier: Apache-2.0
"""Independent continuum oracles for the symmetric-stress P2/P1 owner."""
import itertools
import math
import unittest
import numpy as np
from python.spike_core.propulsion_pod_rotor_cfd import SymmetricStokes,evaluate,CONTRACT
from python.spike_core.propulsion_pod_rotor_cfd_geometry import build_blade_mesh
from tests.python.test_cfd_tetra_stokes import box_mesh


def ring_mesh(n):
    nr=n//6;nz=2;a=.01;b=.03;h=.02
    xyz=[];ids={}
    for i,j,k in itertools.product(range(nr+1),range(n),range(nz+1)):
        r=a+(b-a)*i/nr;t=2*math.pi*j/n;ids[i,j,k]=len(xyz);xyz.append([r*math.cos(t),r*math.sin(t),h*k/nz])
    cells=[]
    for base in itertools.product(range(nr),range(n),range(nz)):
        for order in itertools.permutations(range(3)):
            p=list(base);c=[ids[p[0],p[1]%n,p[2]]]
            for d in order:p[d]+=1;c.append(ids[p[0],p[1]%n,p[2]])
            if np.linalg.det((np.array(xyz)[c[1:]]-np.array(xyz)[c[0]]).T)<0:c[0],c[1]=c[1],c[0]
            cells.append(c)
    faces={}
    for c in cells:
        for f in itertools.combinations(c,3):f=tuple(sorted(f));faces[f]=faces.get(f,0)+1
    inner=set(ids[0,j,k] for j,k in itertools.product(range(n),range(nz+1)));patch={'inner':[],'other':[]}
    for f,count in faces.items():
        if count==1:patch['inner' if set(f)<=inner else 'other'].append(list(f))
    return {'contract':'spike/cfd-tetra-mesh/v1','units':'m','vertices':xyz,'cells':cells,'boundary_patches':patch}


def blade_spec(pitch=.2,refinement=1):
    m,_=build_blade_mesh(pitch_rad=pitch,refinement=refinement)
    return dict(contract=CONTRACT,mesh=m,rotor_patches=['rotor'],axis_unit=[1,0,0],origin_m=[0,0,0],dynamic_viscosity_pa_s=1.,density_kg_m3=1.)


class PhysicalOracles(unittest.TestCase):
    def test_affine_shear(self):
        s=SymmetricStokes(box_mesh(2),2.);r=s.solve(lambda n,x:np.array([3*x[1],0,0]))
        np.testing.assert_allclose(r['u'],np.c_[3*s.xyz[:,1],np.zeros((len(s.xyz),2))],atol=1e-12)
        self.assertAlmostEqual(r['diagnostics']['symmetric_viscous_dissipation_w'],18.,places=11)

    def test_rigid_rotation_zero_symmetric_stress(self):
        s=SymmetricStokes(box_mesh(2),1.);r=s.solve(lambda n,x:np.cross([0,0,1],x))
        self.assertLess(r['diagnostics']['symmetric_viscous_dissipation_w'],1e-24)
        self.assertLess(np.linalg.norm(r['reaction']),1e-12)

    def test_couette_recovered_traction_refinement(self):
        errors=[]
        a=.01;b=.03;h=.02;B=a*a*b*b/(b*b-a*a);A=-a*a/(b*b-a*a)
        def velocity(n,x):
            f=A+B/(x[0]**2+x[1]**2);return np.array([-f*x[1],f*x[0],0.])
        exact=4*math.pi*B*h
        for n in (12,24):
            s=SymmetricStokes(ring_mesh(n),1.);r=s.solve(velocity)
            recovered=s.recovered_surface(r,['inner'],np.zeros(3),np.array([0,0,1]))
            torque=np.array(recovered['moment_on_fluid_nm'])[2];errors.append(abs(torque-exact)/exact)
        print('Independent Couette relative traction errors:',errors)
        self.assertLess(errors[1],errors[0]);self.assertLess(errors[1],.25)

    def test_actual_blade_energy_zero_and_rejection(self):
        spec=blade_spec();r=evaluate(spec,1.)
        self.assertGreater(r['torque_nm'],0);self.assertGreater(abs(r['thrust_n']),0)
        self.assertLess(r['relative_shaft_power_residual'],1e-10)
        zero=evaluate(spec,0.);self.assertEqual(zero['torque_nm'],0);self.assertEqual(zero['power_w'],0)
        with self.assertRaises(ValueError):evaluate(spec,-1.)
        with self.assertRaises(ValueError):evaluate(spec,100.)

    def test_zero_pitch_and_reflected_pitch(self):
        positive=evaluate(blade_spec(.2),1.);negative=evaluate(blade_spec(-.2),1.)
        self.assertGreater(positive['thrust_n'],0);self.assertLess(negative['thrust_n'],0)
        self.assertFalse(positive['load_qualified'])
        zero=evaluate(blade_spec(0.),1.)
        # Structured tetra orientation has finite discretisation asymmetry; no
        # zero-thrust oracle is claimed on this unresolved coarse blade mesh.
        self.assertGreater(zero['torque_nm'],0)

    def test_blade_refinement_is_not_qualification(self):
        rows=[evaluate(blade_spec(refinement=n),1.) for n in (1,2)]
        print('Blade traction recovery gaps:',[r['traction_torque_recovery_relative_difference'] for r in rows])
        self.assertLess(rows[1]['traction_torque_recovery_relative_difference'],rows[0]['traction_torque_recovery_relative_difference'])
        # This benchmark remains explicitly unresolved, not an accepted air load.
        self.assertGreater(rows[1]['traction_torque_recovery_relative_difference'],.1)

if __name__=='__main__':unittest.main()


