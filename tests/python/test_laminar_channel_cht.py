# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import copy
import json
import math
import unittest
import numpy as np
from python.spike_core.laminar_channel_cht import CONTRACT,solve_laminar_channel_cht


def fixture(nf=8,nx=8):
    return {"contract":CONTRACT,
        "geometry":{"length_m":.1,"fluid_height_m":.01,"width_m":.02,
                    "lower_wall_thickness_m":.002,"upper_wall_thickness_m":.002},
        "grid":{"nx":nx,"fluid_cells":nf,"lower_wall_cells":2,"upper_wall_cells":2},
        "fluid":{"density_kg_m3":1.2,"dynamic_viscosity_pa_s":1.8e-5,
                 "specific_heat_j_kgk":1005.,"conductivity_w_mk":.026},
        "walls":{"lower_conductivity_w_mk":2.,"upper_conductivity_w_mk":3.,
                 "lower_heat_w_m3":10000.,"upper_heat_w_m3":0.},
        "drive":{"pressure_gradient_pa_m":.1,"inlet_temperature_k":300.},
        "boundaries":{"lower":{"type":"adiabatic"},"upper":{"type":"adiabatic"}}}


class LaminarChannelChtTests(unittest.TestCase):
    def test_cli_example(self):
        from pathlib import Path
        import subprocess
        import sys
        import tempfile
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/"result.json"
            run=subprocess.run([sys.executable,str(root/"scripts/run_structured_solid_thermal.py"),
                "--request",str(root/"examples/thermal/laminar_channel_cht_request.json"),
                "--result",str(output)],capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stderr)
            result=json.loads(output.read_text())
            self.assertEqual(result["contract"],"spike/laminar-channel-cht-result/v1")
            self.assertFalse(result["qualification"]["production_qualified"])

    def test_poiseuille_profile_flow_convergence_and_pressure_work(self):
        errors=[]
        for nf in (4,8,16,32):
            request=fixture(nf)
            result=solve_laminar_channel_cht(request)
            self.assertEqual(result["status"],"completed",result)
            y=np.linspace(0,.01,nf+1)
            exact=.1/(2*1.8e-5)*y*(.01-y)
            self.assertLess(float(np.max(abs(exact-result["velocity_nodes_m_s"]))),1e-12)
            exact_flow=.02*.1*.01**3/(12*1.8e-5)
            errors.append(abs(result["flow_m3_s"]-exact_flow))
            self.assertAlmostEqual(result["flow_m3_s"],exact_flow*(1-1/nf**2),places=15)
            self.assertLess(abs(result["energy"]["pressure_work_w"]-result["energy"]["viscous_heat_w"]),1e-14)
        self.assertTrue(all(math.log2(a/b)>1.99 for a,b in zip(errors,errors[1:])))

    def test_heating_balances_advected_enthalpy_and_inlet_diffusion(self):
        request=fixture()
        before=copy.deepcopy(request)
        result=solve_laminar_channel_cht(request)
        self.assertEqual(result["status"],"completed",result)
        e=result["energy"]
        self.assertGreater(e["enthalpy_rise_w"],0)
        self.assertAlmostEqual(e["generated_w"]+e["inlet_conduction_w"],e["enthalpy_rise_w"],places=10)
        self.assertEqual(e["outward_w"],0.)
        self.assertEqual(request,before)
        self.assertFalse(result["qualification"]["production_qualified"])
        json.dumps(result,allow_nan=False)

    def test_isothermal_zero_flow(self):
        request=fixture()
        request["drive"]["pressure_gradient_pa_m"]=0.
        request["walls"]["lower_heat_w_m3"]=0.
        result=solve_laminar_channel_cht(request)
        self.assertEqual(result["status"],"completed",result)
        self.assertLess(max(abs(t-300) for t in result["temperature_k"]),1e-8)
        self.assertEqual(result["flow_m3_s"],0.)

    def test_conjugate_interfaces_match_independent_four_cell_system(self):
        request=fixture(nf=2,nx=1)
        request["grid"].update(lower_wall_cells=1,upper_wall_cells=1)
        request["drive"]["pressure_gradient_pa_m"]=0.
        request["boundaries"]={"lower":{"type":"temperature","temperature_k":310.},
                               "upper":{"type":"temperature","temperature_k":290.}}
        widths=[.002,.005,.005,.002]; conductivity=[2.,.026,.026,3.]
        area=.1*.02
        g=[area/(widths[j]/(2*conductivity[j])+widths[j+1]/(2*conductivity[j+1])) for j in range(3)]
        gb=2*2*area/.002; gt=2*3*area/.002; gi=2*.026*.005*.02/.1
        a=np.array([[gb+g[0],-g[0],0,0],[-g[0],g[0]+g[1]+gi,-g[1],0],
                    [0,-g[1],g[1]+g[2]+gi,-g[2]],[0,0,-g[2],g[2]+gt]])
        b=np.array([gb*310+10000*.002*area,gi*300,gi*300,gt*290])
        exact=np.linalg.solve(a,b)
        result=solve_laminar_channel_cht(request)
        self.assertEqual(result["status"],"completed",result)
        self.assertLess(float(np.max(abs(exact-result["temperature_k"]))),1e-9)
        self.assertAlmostEqual(result["interface_upward_heat_w"][0][0],g[0]*(exact[0]-exact[1]),places=10)
        self.assertAlmostEqual(result["interface_upward_heat_w"][1][0],g[2]*(exact[2]-exact[3]),places=10)

    def test_external_convection_and_temperature_boundaries(self):
        request=fixture()
        request["boundaries"]={"lower":{"type":"convection","ambient_temperature_k":290.,"coefficient_w_m2k":20.},
                               "upper":{"type":"temperature","temperature_k":305.}}
        result=solve_laminar_channel_cht(request)
        self.assertEqual(result["status"],"completed",result)
        self.assertLess(abs(result["energy"]["residual_w"]),1e-8)

    def test_reject_nonlaminar_invalid_and_unsupported(self):
        mutations=[lambda r:r["drive"].update(pressure_gradient_pa_m=1000.),
            lambda r:r["drive"].update(pressure_gradient_pa_m=-1.),
            lambda r:r["fluid"].update(dynamic_viscosity_pa_s="0.1"),
            lambda r:r["grid"].update(nx=True),lambda r:r["grid"].update(nx=256,fluid_cells=256),
            lambda r:r.update(turbulence="k-epsilon"),lambda r:r["boundaries"]["upper"].update(type="fan"),
            lambda r:r["boundaries"]["upper"].update(type=[]),
            lambda r:r["walls"].update(lower_heat_w_m3=1e200),
            lambda r:r["drive"].update(inlet_temperature_k=1e200)]
        for mutate in mutations:
            request=fixture();mutate(request)
            result=solve_laminar_channel_cht(request)
            self.assertEqual(result["status"],"blocked",result)
            self.assertEqual(result["temperature_k"],[])
            json.dumps(result,allow_nan=False)

    def test_cancellation_discards_field(self):
        result=solve_laminar_channel_cht(fixture(),cancel_check=lambda:True)
        self.assertEqual(result["status"],"cancelled")
        self.assertEqual(result["temperature_k"],[])

    def test_laminar_admission_is_independent_of_coarse_grid_flow_error(self):
        for nf in (2,4,8):
            request=fixture(nf=nf)
            request["drive"]["pressure_gradient_pa_m"]=4.
            self.assertEqual(solve_laminar_channel_cht(request)["status"],"blocked")

    def test_upwind_thermal_self_convergence(self):
        values=[]
        for nx in (32,64,128,256):
            request=fixture(nf=16,nx=nx)
            request["geometry"]["length_m"]=.001
            result=solve_laminar_channel_cht(request)
            self.assertEqual(result["status"],"completed",result)
            values.append(result["energy"]["enthalpy_rise_w"])
        differences=[abs(b-a) for a,b in zip(values,values[1:])]
        self.assertTrue(all(math.log2(a/b)>.85 for a,b in zip(differences,differences[1:])),values)


if __name__=="__main__":unittest.main()
