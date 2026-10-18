# SPDX-License-Identifier: Apache-2.0
"""Independent planar thermal conservation, field, and coupling oracles."""
import unittest
import numpy as np
from python.spike_core.magnetic_fem import MU0
from python.spike_core.magnetic_thermal import solve_thermal_step,simulate_magnetic_thermal


def grid(n):
    nodes=[[i/n,j/n] for j in range(n+1) for i in range(n+1)]
    triangles=[]
    for j in range(n):
        for i in range(n):
            a=j*(n+1)+i
            triangles.extend([[a,a+1,a+n+2],[a,a+n+2,a+n+1]])
    return nodes,triangles


def thermal_request(n=4):
    nodes,triangles=grid(n)
    return dict(nodes_m=nodes,triangles=triangles,region_ids=["solid"]*len(triangles),
                materials={"solid":{"k_w_m_k":2.0,"rho_kg_m3":3.0,"cp_j_kg_k":4.0}},
                stack_depth_m=.3,previous_temperature_k=[300.0]*len(nodes),
                time_step_s=.2,element_power_w=[0.0]*len(triangles))


class MagneticThermalTests(unittest.TestCase):
    def test_uniform_adiabatic_heat_storage_and_deposition(self):
        for lumped in (False,True):
            q=thermal_request(5)
            q["element_power_w"]=[6.0/len(q["triangles"])]*len(q["triangles"])
            q["lumped_capacity"]=lumped
            r=solve_thermal_step(**q)
            expected=300+6*.2/(3*4*.3)
            np.testing.assert_allclose(r["temperature_k"],expected,atol=2e-12)
            self.assertAlmostEqual(r["heat_audit"]["stored_energy_change_j"],1.2,places=11)
            self.assertLess(abs(r["heat_audit"]["balance_residual_j"]),1e-11)
            self.assertAlmostEqual(sum(r["nodal_heat_capacity_j_per_k"]),3.6,places=12)

    def test_slab_convection_exact_steady_field_and_boundary_work(self):
        n=6
        q=thermal_request(n)
        # L=1, k=2, h=4: q''=100/(1/2+1/4)=400/3 W/m2.
        exact=[400-(200/3)*x for x,y in q["nodes_m"]]
        q["previous_temperature_k"]=exact
        q["dirichlet_temperature_k"]={i:400.0 for i,(x,y) in enumerate(q["nodes_m"]) if x==0}
        q["convection_edges"]=[{"nodes":[j*(n+1)+n,(j+1)*(n+1)+n],
                                "h_w_m2_k":4.0,"ambient_temperature_k":300.0} for j in range(n)]
        result=solve_thermal_step(**q)
        np.testing.assert_allclose(result["temperature_k"],exact,atol=2e-12)
        audit=result["heat_audit"]
        expected=(400/3)*q["stack_depth_m"]*q["time_step_s"]
        self.assertAlmostEqual(audit["convection_energy_out_j"],expected,places=10)
        self.assertAlmostEqual(audit["prescribed_temperature_energy_in_j"],expected,places=10)
        self.assertLess(abs(audit["stored_energy_change_j"]),1e-11)
        self.assertLess(abs(audit["balance_residual_j"]),1e-11)

    def test_thermal_fourier_spatial_refinement(self):
        errors=[]
        for n in (4,8,16):
            q=thermal_request(n)
            q["materials"]={"solid":{"k_w_m_k":1.0,"rho_kg_m3":1.0,"cp_j_kg_k":1.0}}
            p=np.asarray(q["nodes_m"])
            mode=np.sin(np.pi*p[:,0])*np.sin(np.pi*p[:,1])
            q["previous_temperature_k"]=(300+mode).tolist()
            q["time_step_s"]=.01
            q["dirichlet_temperature_k"]={i:300.0 for i,(x,y) in enumerate(p) if x in (0,1) or y in (0,1)}
            result=solve_thermal_step(**q)
            exact=300+mode/(1+2*np.pi**2*.01)
            errors.append(float(np.sqrt(np.mean((np.asarray(result["temperature_k"])-exact)**2))))
        self.assertTrue(all(a/b>3 for a,b in zip(errors[:-1],errors[1:])),errors)

    def test_thermal_backward_euler_independent_eigenmode_time_refinement(self):
        from scipy.linalg import eigh
        q=thermal_request(4)
        p=np.asarray(q["nodes_m"]); n=len(p)
        k=np.zeros((n,n)); m=np.zeros((n,n))
        for tri in q["triangles"]:
            interpolation=np.column_stack((np.ones(3),p[tri]))
            area=abs(np.linalg.det(interpolation))/2
            grad=np.linalg.inv(interpolation)[1:,:]
            k[np.ix_(tri,tri)]+=.3*2*area*(grad.T@grad)
            m[np.ix_(tri,tri)]+=.3*12*area*(np.ones((3,3))+np.eye(3))/12
        fixed={i:300.0 for i,(x,y) in enumerate(p) if x in (0,1) or y in (0,1)}
        free=[i for i in range(n) if i not in fixed]
        values,vectors=eigh(k[np.ix_(free,free)],m[np.ix_(free,free)])
        initial=np.zeros(n); initial[free]=vectors[:,0]
        q["dirichlet_temperature_k"]=fixed
        errors=[]
        for count in (2,4,8):
            dt=.3/count; temperature=300+initial
            q["time_step_s"]=dt
            for _ in range(count):
                q["previous_temperature_k"]=temperature.tolist()
                temperature=np.asarray(solve_thermal_step(**q)["temperature_k"])
            np.testing.assert_allclose(temperature,300+initial/(1+dt*values[0])**count,atol=1e-11)
            errors.append(float(np.linalg.norm(temperature-(300+initial*np.exp(-values[0]*.3)))))
        self.assertTrue(all(1.7<a/b<2.1 for a,b in zip(errors[:-1],errors[1:])),errors)

    def test_thermal_admission_rejects_interior_convection_and_negative_heat(self):
        q=thermal_request()
        q["convection_edges"]=[{"nodes":[0,6],"h_w_m2_k":5.0,"ambient_temperature_k":300.0}]
        with self.assertRaisesRegex(ValueError,"exterior"):
            solve_thermal_step(**q)
        q.pop("convection_edges")
        q["element_power_w"][0]=-1
        with self.assertRaisesRegex(ValueError,"nonnegative"):
            solve_thermal_step(**q)

    def coupled_request(self):
        q=thermal_request(4)
        nodes=q["nodes_m"]; triangles=q["triangles"]
        return dict(nodes_m=nodes,triangles=triangles,region_ids=q["region_ids"],
                    magnetic_materials={"solid":{"mu_r":1/MU0,"conductivity_s_m":1.0}},
                    thermal_materials=q["materials"],stack_depth_m=q["stack_depth_m"],
                    dirichlet_a_wb_per_m={i:0.0 for i,(x,y) in enumerate(nodes) if x in (0,1) or y in (0,1)},
                    initial_a_wb_per_m=[0.0]*len(nodes),initial_temperature_k=[300.0]*len(nodes),
                    time_step_s=.1,steps=3,
                    conductivity_temperature_coefficients={"solid":{"alpha_per_k":.1,"reference_temperature_k":300.0}})

    def test_winding_heat_feedback_analytic_regional_conductivity(self):
        q=self.coupled_request()
        q["winding_element_loss_w"]=[3.6/len(q["triangles"])]*len(q["triangles"])
        result=simulate_magnetic_thermal(**q)
        for index,row in enumerate(result["step_audits"]):
            self.assertAlmostEqual(row["conductivity_s_m"]["solid"],1/(1+.1*(.1*index)),places=12)
            self.assertEqual(row["eddy_joule_energy_j"],0)
            self.assertAlmostEqual(row["thermal"]["stored_energy_change_j"],.36,places=11)
        np.testing.assert_allclose(result["final_thermal_result"]["temperature_k"],300.3,atol=2e-12)

    def test_actual_eddy_loss_deposition_and_feedback(self):
        q=self.coupled_request()
        p=np.asarray(q["nodes_m"])
        q["initial_a_wb_per_m"]=(np.sin(2*np.pi*p[:,0])*np.sin(np.pi*p[:,1])).tolist()
        q["time_step_s"]=.01
        result=simulate_magnetic_thermal(**q)
        cumulative=0
        for row in result["step_audits"]:
            self.assertGreater(row["eddy_joule_energy_j"],0)
            self.assertAlmostEqual(row["thermal"]["input_energy_j"],row["eddy_joule_energy_j"],places=12)
            self.assertLess(abs(row["thermal"]["balance_residual_j"]),1e-11)
            cumulative+=row["eddy_joule_energy_j"]
        temperature=np.asarray(result["final_thermal_result"]["temperature_k"])
        capacity=np.asarray(result["final_thermal_result"]["nodal_heat_capacity_j_per_k"])
        self.assertAlmostEqual(float(capacity@(temperature-300)),cumulative,places=10)
        self.assertLess(result["step_audits"][1]["conductivity_s_m"]["solid"],1)
        self.assertEqual(len(result["history"]),4)

    def test_coupling_timestep_refinement(self):
        q=self.coupled_request()
        p=np.asarray(q["nodes_m"])
        q["initial_a_wb_per_m"]=(np.sin(2*np.pi*p[:,0])*np.sin(np.pi*p[:,1])).tolist()
        outputs=[]
        for steps in (4,8,16,64):
            q["steps"]=steps
            q["time_step_s"]=.02/steps
            q["snapshot_stride"]=steps
            result=simulate_magnetic_thermal(**q)
            outputs.append(np.r_[result["final_magnetic_result"]["potential_a_wb_per_m"],
                                  np.asarray(result["final_thermal_result"]["temperature_k"])-300])
        errors=[np.linalg.norm(value-outputs[-1]) for value in outputs[:-1]]
        self.assertTrue(all(a/b>1.7 for a,b in zip(errors[:-1],errors[1:])),errors)

    def test_coupling_rejects_invalid_feedback_and_resource_request(self):
        q=self.coupled_request()
        q["conductivity_temperature_coefficients"]["solid"]["reference_temperature_k"]=400
        with self.assertRaisesRegex(ValueError,"denominator"):
            simulate_magnetic_thermal(**q)
        q=self.coupled_request(); q["steps"]=1001
        with self.assertRaisesRegex(ValueError,"steps"):
            simulate_magnetic_thermal(**q)


if __name__=="__main__":
    unittest.main()

