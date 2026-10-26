# SPDX-License-Identifier: Apache-2.0
"""Independent rotating-NS continuum, linearisation and admission checks."""
import math
import unittest
import numpy as np
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd import RotatingNavierStokes, _Q, _W
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_rotor_cfd import SymmetricStokes
from python.spike_core.solvers.thermal_fluid.flow.cfd_tetra_mesh import admit_cfd_tetra_mesh
from tests.python.test_cfd_tetra_stokes import box_mesh
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_rotor_cfd_geometry import build_blade_mesh

class InertialOracles(unittest.TestCase):
 def test_degree_five_volume_quadrature(self):
  for a in range(6):
   for b in range(6-a):
    for c in range(6-a-b):
     for d in range(6-a-b-c):
      k=np.array([a,b,c,d]);expected=6*math.prod(math.factorial(int(i)) for i in k)/math.factorial(3+int(k.sum()))
      self.assertAlmostEqual(float(_W@np.prod(_Q**k,axis=1)),expected,places=14)
 def test_consistent_full_Newton_derivative(self):
  s=RotatingNavierStokes(box_mesh(2),.3,1.2);b=s.base
  rng=np.random.default_rng(814);u=rng.normal(0,.2,b.xyz.shape);du=rng.normal(0,.1,b.xyz.shape);omega=np.array([.2,-.1,.4]);origin=np.array([.3,.2,.1])
  c,j,_=s.operators(u,omega,origin);eps=1e-6
  cp,_,_=s.operators(u+eps*du,omega,origin,jacobian=False);cm,_,_=s.operators(u-eps*du,omega,origin,jacobian=False)
  fd=(cp@(u+eps*du).ravel()-cm@(u-eps*du).ravel())/(2*eps)
  self.assertLess(np.linalg.norm(fd-j@du.ravel())/np.linalg.norm(fd),1e-8)
 def test_exact_rotating_quadratic_inertial_solution(self):
  a=.2;mu=.3;rho=1.2;O=.4;beta=.1
  def velocity(name,x):return np.array([a*x[0]**2,-2*a*x[0]*x[1],0.])
  def force(x):
   X,Y,Z=x
   return np.array([rho*(2*a*a*X**3+4*a*O*X*Y)-2*mu*a+beta,rho*(2*a*a*X*X*Y+a*O*(3*X*X-2*Y*Y)),0.])
  s=RotatingNavierStokes(box_mesh(2),mu,rho);b=s.base;initial={'u':np.array([velocity('',x) for x in b.xyz]),'p':np.zeros(len(b.mesh['vertices']))}
  rng=np.random.default_rng(101);initial['u'].ravel()[b.free]+=rng.normal(0,.02,len(b.free))
  r=s.solve(velocity,[0,0,O],body_force=force,initial=initial)
  np.testing.assert_allclose(r['u'],[velocity('',x) for x in b.xyz],atol=1e-10)
  np.testing.assert_allclose(r['p'],beta*(b.mesh['vertices'][:,0]-.5),atol=1e-9)
  diag=r['diagnostics'];self.assertLess(diag['nonlinear_relative_residual'],1e-9);self.assertLess(diag['relative_energy_residual'],1e-9)
  self.assertAlmostEqual(diag['viscous_dissipation_w'],.08,places=10);self.assertAlmostEqual(diag['boundary_kinetic_flux_w'],.0048,places=10)
  self.assertGreater(len(diag['Newton_history']),2)
 def test_actual_no_slip_blade_low_density_Stokes_limit(self):
  m,_=build_blade_mesh();s=RotatingNavierStokes(m,1.,1e-7);velocity=lambda name,x:np.cross([1,0,0],x) if name=='rotor' else np.zeros(3)
  r=s.solve(velocity,[1,0,0]);st=s.base.solve(velocity)
  self.assertLess(np.linalg.norm(r['u']-st['u'])/np.linalg.norm(st['u']),1e-6)
  self.assertLess(r['diagnostics']['relative_energy_residual'],1e-8)
 def test_spatial_broadphase_exact_bruteforce_pair_equivalence(self):
  from python.spike_core.solvers.thermal_fluid.flow.cfd_tetra_intersections import _strict_aabb_pairs
  rng=np.random.default_rng(832);lo=rng.uniform(-10,10,(4200,3));hi=lo+rng.uniform(.001,.2,(4200,3))
  # Include strict-touching and fully coincident bounds explicitly.
  lo[1]=hi[0];hi[1]=lo[1]+.1;lo[2]=lo[0];hi[2]=hi[0]
  expected=[]
  for i in range(len(lo)):
   expected.extend((i,int(j)) for j in np.flatnonzero(np.all(hi[i]>lo[i+1:],axis=1)&np.all(hi[i+1:]>lo[i],axis=1))+i+1)
  self.assertEqual(list(_strict_aabb_pairs(lo,hi)),expected)
 def test_SUPG_full_symmetric_P2_strong_viscosity(self):
  from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_supg import assemble
  solver=RotatingNavierStokes(box_mesh(2),.3,1.2,supg=True,quadrature_order=6);u=np.zeros_like(solver.base.xyz);u[:,0]=solver.base.xyz[:,0]**2;p=np.zeros(len(solver.base.mesh['vertices']));x=solver.points[:,:,0];force=np.zeros_like(solver.points);force[:,:,0]=2*1.2*x**3-4*.3
  _,_,_,d=assemble(solver,u,p,np.zeros(3),np.zeros(3),force,jacobian=False)
  self.assertLess(d['strong_physical_momentum_L2_n_m3_times_m3_over2'],1e-11)
 def test_SUPG_full_velocity_pressure_and_tau_Jacobian(self):
  from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd_supg import assemble
  solver=RotatingNavierStokes(box_mesh(2),.3,1.2,supg=True);rng=np.random.default_rng(108);u=rng.normal(0,.2,solver.base.xyz.shape);p=rng.normal(0,.3,len(solver.base.mesh['vertices']));du=rng.normal(0,.1,u.shape);dp=rng.normal(0,.2,p.shape);body=np.zeros_like(solver.points);omega=np.array([.2,-.1,.4]);origin=np.zeros(3)
  _,ju,jp,_=assemble(solver,u,p,omega,origin,body);eps=1e-6;plus=assemble(solver,u+eps*du,p+eps*dp,omega,origin,body,jacobian=False)[0];minus=assemble(solver,u-eps*du,p-eps*dp,omega,origin,body,jacobian=False)[0];fd=(plus-minus)/(2*eps)
  self.assertLess(np.linalg.norm(fd-ju@du.ravel()-jp@dp)/np.linalg.norm(fd),1e-8)
 def test_SUPG_nonexact_rotating_cubic_MMS_refinement_and_work(self):
  a=.2;mu=.3;rho=1.2;O=.4;beta=.1;gamma=.07;errors=[]
  def velocity(name,x):return np.array([a*x[0]**3,-3*a*x[0]**2*x[1],0.])
  def force(x):
   X,Y,Z=x
   return np.array([rho*(3*a*a*X**5+6*a*O*X*X*Y)-6*mu*a*X+beta,rho*(3*a*a*X**4*Y+4*a*O*X**3-6*a*O*X*Y*Y)+6*mu*a*Y+2*gamma*Y,0.])
  for n in (2,4):
   solver=RotatingNavierStokes(box_mesh(n),mu,rho,supg=True,quadrature_order=6);r=solver.solve(velocity,[0,0,O],body_force=force);uq=np.einsum('qi,cia->cqa',solver.N,r['u'][solver.base.local]);x=solver.points;exact=np.stack([a*x[:,:,0]**3,-3*a*x[:,:,0]**2*x[:,:,1],np.zeros(x.shape[:2])],axis=2);pp=(solver.Q@r['p'][solver.base.mesh['cells']].T).T;ep=beta*(x[:,:,0]-.5)+gamma*(x[:,:,1]**2-1/3)
   errors.append([float(np.sqrt(np.sum(solver.weights*np.sum((uq-exact)**2,axis=2)))),float(np.sqrt(np.sum(solver.weights*(pp-ep)**2)))])
   self.assertLess(r['diagnostics']['relative_energy_residual'],1e-9)
   self.assertGreater(abs(r['diagnostics']['SUPG_power_w']),1e-8)
  self.assertLess(errors[1][0],errors[0][0]/4);self.assertLess(errors[1][1],errors[0][1]/4)
 def test_faceted_cylinder_side_interior_nodes_and_false_wall_rejection(self):
  from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_inertial_cfd import _admit_coaxial_outer
  axis=np.array([0.,1.,0.]);origin=np.array([0.,.01,0.]);R=.45;L=.45;vertices=[]
  for y in (-L,L):
   for j in range(8):
    angle=j*math.pi/4;vertices.append((origin+np.array([R*math.cos(angle),y,R*math.sin(angle)])).tolist())
  vertices.extend([(origin+np.array([0.,-L,0.])).tolist(),(origin+np.array([0.,L,0.])).tolist()]);triangles=[]
  for j in range(8):
   k=(j+1)%8;triangles.extend([[16,j,k],[17,8+j,8+k]]);centre=len(vertices);vertices.append(np.array(vertices)[[j,k,8+j,8+k]].mean(0).tolist());triangles.extend([[j,k,centre],[k,8+k,centre],[8+k,8+j,centre],[8+j,j,centre]])
  result=_admit_coaxial_outer(np.array(vertices),triangles,axis,origin,R,L)
  self.assertEqual(result['polygon_facets'],8)
  malformed=np.array(vertices);malformed[-1,0]*=.9
  with self.assertRaises(ValueError):_admit_coaxial_outer(malformed,triangles,axis,origin,R,L)
 def test_explicit_mesh_resource_extension_default_preserved(self):
  mesh=box_mesh(9)
  with self.assertRaises(ValueError):admit_cfd_tetra_mesh(mesh)
  self.assertEqual(len(admit_cfd_tetra_mesh(mesh,max_cells=5000)['cells']),4374)
  for invalid in (True,False,-1,0,65537,1.5,None):
   with self.assertRaises(ValueError):admit_cfd_tetra_mesh(box_mesh(1),max_cells=invalid)

if __name__=='__main__':unittest.main()
