# SPDX-License-Identifier: Apache-2.0
"""Independently authored exact-field and constitutive checks."""
import unittest
import numpy as np
from python.spike_core.magnetic_fem import (
    MU0, MagneticMaterial, PlanarMagneticOperator, solve_magnetostatic,
)


def square(n):
    nodes = [[i/n, j/n] for j in range(n+1) for i in range(n+1)]
    triangles = []
    for j in range(n):
        for i in range(n):
            a = j*(n+1)+i
            triangles.extend([[a,a+1,a+n+2],[a,a+n+2,a+n+1]])
    boundary = [k for k,(x,y) in enumerate(nodes) if x in (0,1) or y in (0,1)]
    return np.asarray(nodes), triangles, boundary


def request(n=4):
    nodes, triangles, boundary = square(n)
    return dict(nodes_m=nodes.tolist(), triangles=triangles,
                region_ids=["air"]*len(triangles),
                materials={"air":{"mu_r":1.0}}, stack_depth_m=0.3,
                dirichlet_a_wb_per_m={i:0.0 for i in boundary})


class MagneticFemTests(unittest.TestCase):
    def test_manufactured_poisson_field_mesh_convergence(self):
        errors = []
        for n in (4,8,16):
            q = request(n)
            nodes = np.asarray(q["nodes_m"])
            exact = nodes[:,0]*(1-nodes[:,0])+nodes[:,1]*(1-nodes[:,1])
            q["dirichlet_a_wb_per_m"] = {i:float(exact[i]) for i in q["dirichlet_a_wb_per_m"]}
            q["current_density_a_per_m2"] = {"air":4/MU0}
            r = solve_magnetostatic(**q)
            np.testing.assert_allclose(r["potential_a_wb_per_m"],exact,rtol=0,atol=2e-12)
            centers = nodes[np.asarray(q["triangles"])].mean(axis=1)
            exact_b = np.column_stack((1-2*centers[:,1],-1+2*centers[:,0]))
            errors.append(float(np.sqrt(np.sum(np.asarray(r["element_area_m2"])*
                                 np.sum((np.asarray(r["element_b_t"])-exact_b)**2,axis=1)))))
            self.assertTrue(r["convergence"]["converged"])
            self.assertIsNone(r["joule_loss_w"])
        np.testing.assert_allclose(np.asarray(errors[:-1])/errors[1:],[2,2],rtol=2e-10)

    def test_constant_permanent_magnet_field_and_potential_reference(self):
        q=request(5)
        br=np.array([0.3,-0.2])
        # Exact affine cancellation has ~1.5e-10 A residual at this field scale.
        q["absolute_tolerance_a"]=1e-9
        q["materials"]={"air":{"mu_r":1.05,"remanence_t":br.tolist(),"conductivity_s_m":7e5}}
        q["dirichlet_a_wb_per_m"]={i:float(br[0]*q["nodes_m"][i][1]-br[1]*q["nodes_m"][i][0])
                                   for i in q["dirichlet_a_wb_per_m"]}
        r=solve_magnetostatic(**q)
        np.testing.assert_allclose(r["element_b_t"],np.tile(br,(len(q["triangles"]),1)),atol=2e-15)
        np.testing.assert_allclose(r["element_h_a_per_m"],0,atol=2e-9)
        expected=-0.5*float(br@br)/(1.05*MU0)*q["stack_depth_m"]
        self.assertAlmostEqual(r["magnetic_energy_j"]/expected,1,places=12)
        self.assertAlmostEqual(r["magnetic_coenergy_j"]/(-expected),1,places=12)
        self.assertEqual(r["joule_loss_status"],"not_solved")

    def test_nonlinear_layered_exact_field_and_newton(self):
        q=request(8)
        nodes=np.asarray(q["nodes_m"])
        centers=nodes[np.asarray(q["triangles"])].mean(axis=1)
        q["region_ids"]=["lower" if y<0.5 else "upper" for x,y in centers]
        q["materials"]={"lower":{"bh_curve":[[0,0],[0.1,20],[0.4,260]]},
                        "upper":{"bh_curve":[[0,0],[0.1,50],[0.3,250]]}}
        exact=np.where(nodes[:,1]<=0.5,0.2*nodes[:,1],0.1+0.15*(nodes[:,1]-0.5))
        q["dirichlet_a_wb_per_m"]={i:float(exact[i]) for i in q["dirichlet_a_wb_per_m"]}
        r=solve_magnetostatic(**q)
        np.testing.assert_allclose(r["potential_a_wb_per_m"],exact,atol=1e-12)
        np.testing.assert_allclose(r["element_h_a_per_m"],np.tile([100,0],(len(centers),1)),atol=1e-8)
        self.assertGreater(r["convergence"]["iterations"],0)
        # Lower integral = 1 + 0.1*(20+100)/2 = 7 J/m3.
        # Upper integral = 2.5 + 0.05*(50+100)/2 = 6.25 J/m3.
        self.assertAlmostEqual(r["magnetic_energy_j"],0.3*0.5*(7+6.25),places=10)
        self.assertAlmostEqual(r["magnetic_coenergy_j"],0.3*0.5*((20-7)+(15-6.25)),places=10)

    def test_nonlinear_tangent_and_potential_derivative(self):
        law=MagneticMaterial({"bh_curve":[[0,0],[0.1,20],[0.5,1000]]})
        b=np.array([[0.19,0.08],[0.03,-0.04]])
        direction=np.array([[0.3,-0.8],[0.6,0.2]])
        h,tangent,w,c=law.evaluate(b)
        eps=1e-5
        hp,_,wp,_=law.evaluate(b+eps*direction)
        hm,_,wm,_=law.evaluate(b-eps*direction)
        np.testing.assert_allclose((hp-hm)/(2*eps),np.einsum("eij,ej->ei",tangent,direction),rtol=2e-9)
        np.testing.assert_allclose((wp-wm)/(2*eps),np.sum(h*direction,axis=1),rtol=2e-9)
        np.testing.assert_allclose(w+c,np.sum(h*b,axis=1),atol=1e-14)

    def test_per_element_source_orientation_and_depth(self):
        q=request()
        q["current_density_a_per_m2"]=[1000.0]*len(q["triangles"])
        a=solve_magnetostatic(**q)
        q["triangles"]=[list(reversed(t)) for t in q["triangles"]]
        q["stack_depth_m"]*=2
        b=solve_magnetostatic(**q)
        np.testing.assert_allclose(a["element_b_t"],b["element_b_t"],atol=1e-15)
        self.assertAlmostEqual(b["magnetic_energy_j"],2*a["magnetic_energy_j"],places=12)
        self.assertAlmostEqual(a["magnetic_energy_j"],a["magnetic_coenergy_j"],places=12)

    def test_reject_malformed_and_unsupported_models(self):
        for material in ({"mu_r":0},{"bh_curve":[[0,0],[0.2,10],[0.1,20]]},
                         {"bh_curve":[[0,0],[1,1]],"remanence_t":[1,0]}):
            q=request()
            q["materials"]={"air":material}
            with self.assertRaises(ValueError):
                solve_magnetostatic(**q)
        q=request()
        q["dirichlet_a_wb_per_m"]={}
        with self.assertRaisesRegex(ValueError,"Dirichlet"):
            solve_magnetostatic(**q)
        q=request()
        q["triangles"][0]=[0,0,1]
        with self.assertRaisesRegex(ValueError,"Degenerate"):
            solve_magnetostatic(**q)

    def test_bh_extrapolation_and_unconverged_output_withheld(self):
        q=request()
        q["materials"]={"air":{"bh_curve":[[0,0],[0.01,1]]}}
        q["current_density_a_per_m2"]={"air":1e6}
        q["maximum_iterations"]=2
        with self.assertRaises(ValueError):
            solve_magnetostatic(**q)

    def test_assembled_tangent_against_residual_difference(self):
        q=request()
        op=PlanarMagneticOperator(q["nodes_m"],q["triangles"],q["region_ids"],
                                 {"air":{"bh_curve":[[0,0],[0.1,20],[0.5,1000]]}})
        nodes=np.asarray(q["nodes_m"])
        a=0.15*nodes[:,1]+0.01*nodes[:,0]**2
        direction=np.sin(np.arange(len(a)))
        _,k,*_=op.evaluate(a)
        eps=1e-8
        difference=(op.evaluate(a+eps*direction)[0]-op.evaluate(a-eps*direction)[0])/(2*eps)
        np.testing.assert_allclose(difference,k@direction,rtol=1e-8,atol=2e-6)



class EddyCurrentTests(unittest.TestCase):
    def test_fourier_backward_euler_spatial_refinement(self):
        from python.spike_core.magnetic_fem import solve_eddy_current_step
        errors=[]
        for n in (4,8,16):
            q=request(n)
            nodes=np.asarray(q["nodes_m"])
            q["materials"]={"air":{"mu_r":1/MU0,"conductivity_s_m":1.0}}
            previous=np.sin(2*np.pi*nodes[:,0])*np.sin(np.pi*nodes[:,1])
            dt=0.01
            result=solve_eddy_current_step(**q,previous_a_wb_per_m=previous.tolist(),time_step_s=dt)
            expected=previous/(1+5*np.pi**2*dt)
            errors.append(float(np.sqrt(np.mean((np.asarray(result["potential_a_wb_per_m"])-expected)**2))))
            self.assertGreater(result["joule_loss_w"],0)
            self.assertLess(abs(result["region_net_induced_current_a"]["air"]),1e-12)
            audit=result["energy_audit"]
            self.assertGreaterEqual(audit["backward_euler_numerical_dissipation_j"],0)
            self.assertLess(abs(audit["balance_residual_j"]),1e-12)
        self.assertTrue(all(a/b>3 for a,b in zip(errors[:-1],errors[1:])),errors)

    def test_independent_semidiscrete_exponential_time_refinement(self):
        from scipy.linalg import eigh
        from python.spike_core.magnetic_fem import solve_eddy_current_step
        q=request(5)
        q["materials"]={"air":{"mu_r":1/MU0,"conductivity_s_m":1.0}}
        nodes=np.asarray(q["nodes_m"]); n=len(nodes)
        # Independently assemble scalar Laplace, P1 mass, and mean-current constraint.
        stiffness=np.zeros((n,n)); mass=np.zeros((n,n)); weights=np.zeros(n)
        for tri in q["triangles"]:
            p=nodes[tri]
            interpolation=np.column_stack((np.ones(3),p))
            area=abs(np.linalg.det(interpolation))/2
            gradients=np.linalg.inv(interpolation)[1:,:]
            stiffness[np.ix_(tri,tri)]+=area*(gradients.T@gradients)
            mass[np.ix_(tri,tri)]+=area*(np.eye(3)+np.ones((3,3)))/12
            weights[tri]+=area/3
        free=np.array([i for i in range(n) if i not in q["dirichlet_a_wb_per_m"]])
        reduced_mass=(mass-np.outer(weights,weights)/weights.sum())[np.ix_(free,free)]
        eigenvalues,eigenvectors=eigh(stiffness[np.ix_(free,free)],reduced_mass)
        initial=np.zeros(n); initial[free]=eigenvectors[:,0]
        duration=0.03; errors=[]
        for steps in (2,4,8):
            a=initial.copy(); dt=duration/steps
            for _ in range(steps):
                result=solve_eddy_current_step(**q,previous_a_wb_per_m=a.tolist(),time_step_s=dt)
                a=np.asarray(result["potential_a_wb_per_m"])
            exact_be=initial/(1+dt*eigenvalues[0])**steps
            np.testing.assert_allclose(a,exact_be,rtol=2e-12,atol=2e-12)
            exact=initial*np.exp(-eigenvalues[0]*duration)
            errors.append(float(np.linalg.norm(a-exact)))
        self.assertTrue(all(1.65<a/b<2.1 for a,b in zip(errors[:-1],errors[1:])),errors)

    def test_gauge_shift_has_no_induced_current_or_heat(self):
        from python.spike_core.magnetic_fem import solve_eddy_current_step
        q=request(4)
        q["materials"]={"air":{"mu_r":1.0,"conductivity_s_m":5e7}}
        old=[0.001*y for x,y in q["nodes_m"]]
        q["dirichlet_a_wb_per_m"]={i:old[i]+0.002 for i in q["dirichlet_a_wb_per_m"]}
        result=solve_eddy_current_step(**q,previous_a_wb_per_m=old,time_step_s=.01,
                                      absolute_tolerance_a=1e-7)
        np.testing.assert_allclose(result["potential_a_wb_per_m"],np.asarray(old)+.002,atol=1e-14)
        self.assertLess(result["joule_loss_w"],1e-20)
        self.assertAlmostEqual(result["region_electric_offset_v_per_m"]["air"],.2,places=11)

    def test_eddy_rejects_absent_conductivity_and_bad_state(self):
        from python.spike_core.magnetic_fem import solve_eddy_current_step
        q=request()
        with self.assertRaisesRegex(ValueError,"conductive"):
            solve_eddy_current_step(**q,previous_a_wb_per_m=[0.0]*len(q["nodes_m"]),time_step_s=.1)
        q["materials"]={"air":{"mu_r":1.0,"conductivity_s_m":1.0}}
        with self.assertRaisesRegex(ValueError,"Previous"):
            solve_eddy_current_step(**q,previous_a_wb_per_m=[0.0],time_step_s=.1)



if __name__ == "__main__":
    unittest.main()
