# SPDX-License-Identifier: Apache-2.0
import math
import unittest
import numpy as np
from python.spike_core.magnetic_machine_study import maxwell_stress_integral, run_magnetic_machine
from python.spike_core.magnetic_fem import MU0


class MagneticMachineStudyTests(unittest.TestCase):
    def test_piecewise_stress_is_exact_and_subdivision_order_invariant(self):
        nodes = np.array([[-1.,-1.],[0.,-1.],[1.,-1.],[-1.,1.],[0.,1.],[1.,1.]])
        triangles = np.array([[0,1,4],[0,4,3],[1,2,5],[1,5,4]])
        field = np.array([[.1,0],[.1,0],[.2,0],[.2,0]])
        contour = np.array([[-.75,-.4],[.75,-.4],[.75,.6],[-.75,.6],[-.75,-.4]])
        expected = .02*(.2**2-.1**2)/(2*MU0)
        baseline = maxwell_stress_integral(nodes,triangles,field,["air"]*4,contour,.02)
        self.assertAlmostEqual(baseline["force_x_n"],expected,delta=1e-10)
        self.assertAlmostEqual(baseline["force_y_n"],0,delta=1e-10)
        self.assertAlmostEqual(baseline["torque_n_m"],-.1*expected,delta=1e-10)
        samples = [start+(end-start)*t for start,end in zip(contour[:-1],contour[1:])
                   for t in np.arange(7)/7]
        subdivided = np.array([*samples,samples[0]])
        order = [3,1,2,0]
        repeated = maxwell_stress_integral(nodes,triangles[order],field[order],["air"]*4,subdivided,.02)
        for key in ("force_x_n","force_y_n","torque_n_m"):
            self.assertAlmostEqual(repeated[key],baseline[key],delta=1e-10)
        uniform = maxwell_stress_integral(nodes,triangles,np.tile([.1,.2],(4,1)),["air"]*4,contour,.02)
        for key in ("force_x_n","force_y_n","torque_n_m"):
            self.assertAlmostEqual(uniform[key],0,delta=1e-10)

    def test_stress_force_and_torque_match_lorentz_force_arm(self):
        # Original oracle: infinite z-current at x=.2 in uniform Bx, F=I z cross B.
        x = np.linspace(-1, 1, 101)
        nodes = np.array([(a, b) for b in x for a in x])
        triangles = []
        for j in range(100):
            for i in range(100):
                n = j*101+i
                triangles.extend(((n,n+1,n+102),(n,n+102,n+101)))
        triangles = np.asarray(triangles)
        c = nodes[triangles].mean(axis=1)-[.2,0]
        r2 = np.sum(c*c,axis=1)
        r2[r2 < 1e-20] = 1e-20
        current, applied, depth = 10., .3, .04
        b = MU0*current/(2*math.pi)*np.column_stack((-c[:,1],c[:,0]))/r2[:,None]+[applied,0]
        angles = np.linspace(0,2*math.pi,2049)
        contour = np.column_stack((.2+.5*np.cos(angles),.5*np.sin(angles)))
        contour[-1] = contour[0]
        result = maxwell_stress_integral(nodes,triangles,b,["air"]*len(triangles),contour,depth)
        self.assertAlmostEqual(result["force_y_n"],current*applied*depth,delta=.001)
        self.assertAlmostEqual(result["force_x_n"],0,delta=.001)
        self.assertAlmostEqual(result["torque_n_m"],.2*current*applied*depth,delta=.0004)

    def test_real_field_result_and_malformed_rejection(self):
        request = {"contract":"spike/magnetic-machine-study/v1","model":"pm_rotor"}
        result = run_magnetic_machine(request)
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator
        root = Path(__file__).resolve().parents[2]
        result_schema = json.loads((root/"schemas/magnetic-machine-study-result-v1.schema.json").read_text())
        Draft202012Validator(result_schema).validate(result)
        request_schema = json.loads((root/"schemas/magnetic-machine-study-v1.schema.json").read_text())
        validator = Draft202012Validator(request_schema)
        for case in ("planar_pm_fem.json","planar_solenoid_fem.json"):
            validator.validate(json.loads((root/"examples/em_machines"/case).read_text()))
        self.assertEqual(result["contract"],"spike/magnetic-machine-study-result/v1")
        self.assertGreater(result["summary"]["max_b_t"],0)
        self.assertFalse(result["production_qualified"])
        self.assertEqual(len(result["field"]["element_b_t"]),len(result["field"]["triangles"]))
        self.assertEqual(result["field"]["joule_loss_status"],"not_solved")
        for extra in ({"unexpected":1},{"model":"bad"},{"mesh_edge_m":False},
                      {"motion":{},"transient":{}},{"geometry":{"steel_bh_curve":[[0,0],[1,100]]}}):
            with self.assertRaises(ValueError):
                run_magnetic_machine({**request,**extra})

    def test_static_zero_source_has_no_motion(self):
        result = run_magnetic_machine({"contract":"spike/magnetic-machine-study/v1","model":"pm_rotor",
            "current_density_a_m2":0,"remanence_t":0,"mesh_edge_m":.004,
            "motion":{"duration_s":.002,"time_step_s":.001,"mass_or_inertia":.01,
                      "damping":0,"external_load":0,"initial_velocity":0}})
        self.assertEqual(result["histories"]["position"],[0.,0.,0.])
        self.assertEqual(result["histories"]["velocity"],[0.,0.,0.])

    def test_worker_routes_and_reports_failure(self):
        from python.spike_core.service_simulation_handlers import handle_simulation_request
        result = handle_simulation_request("run_magnetic_machine",{"request":{}},assembly_scope={},solver_registry=None)
        self.assertFalse(result["ok"])
        from python.spike_core.cli import build_parser
        args = build_parser().parse_args(["magnetic-machine","--request","study.json"])
        self.assertEqual(args.command,"magnetic-machine")

    def test_stationary_pm_splits_disconnected_conductors_and_retains_heat(self):
        from python.spike_core.machine_geometry import build_pm_machine_mesh
        mesh = build_pm_machine_mesh(target_edge_m=.004)
        properties = {key:{"k_w_m_k":10,"rho_kg_m3":1000,"cp_j_kg_k":1000} for key in mesh["materials"]}
        request = {"contract":"spike/magnetic-machine-study/v1","model":"pm_rotor","mesh_edge_m":.004,
            "transient":{"time_step_s":.001,"steps":1,"thermal_materials":properties,
                "initial_temperature_k":300,"ambient_temperature_k":300,"convection_h_w_m2_k":0,
                "initial_field":"zero","region_loss_density_w_m3":{"winding_pos":1000}}}
        result = run_magnetic_machine(request)
        coupled = result["coupled"]
        self.assertTrue(any("__conductor_" in key for key in coupled["conductor_region_lineage"]))
        self.assertGreater(coupled["history"][-1]["joule_loss_w"],0)
        self.assertGreater(coupled["history"][-1]["max_temperature_k"],300)
        self.assertEqual(len(coupled["history"][-1]["temperature_k"]),len(result["field"]["nodes_m"]))
        self.assertLess(abs(coupled["final_thermal_result"]["heat_audit"]["balance_residual_j"]),1e-8)
        self.assertEqual(result["summary_state"],"final_stationary_transient")
        self.assertEqual(result["field_time_s"],.001)
        self.assertAlmostEqual(result["summary"]["max_b_t"],
            float(np.max(np.linalg.norm(result["field"]["element_b_t"],axis=1))))

    def test_contour_cannot_cross_steel_between_air_midpoints(self):
        axis = np.linspace(0,1,11)
        nodes = np.array([(x,y) for y in axis for x in axis])
        triangles = []
        for j in range(10):
            for i in range(10):
                n = j*11+i
                triangles.extend(((n,n+1,n+12),(n,n+12,n+11)))
        triangles = np.asarray(triangles)
        centers = nodes[triangles].mean(axis=1)
        regions = ["steel" if .15 < p[0] < .25 and p[1] < .15 else "air" for p in centers]
        field = np.ones((len(triangles),2))
        contour = [[.1,.1],[.9,.1],[.9,.9],[.1,.9],[.1,.1]]
        with self.assertRaisesRegex(ValueError,"non-air"):
            maxwell_stress_integral(nodes,triangles,field,regions,contour,.02)
        intersecting = [[0,0],[2,2],[0,2],[2,0],[3,0],[3,3],[0,3],[0,0]]
        with self.assertRaisesRegex(ValueError,"simple"):
            maxwell_stress_integral(nodes,triangles,field,regions,intersecting,.02)


if __name__ == "__main__":
    unittest.main()
