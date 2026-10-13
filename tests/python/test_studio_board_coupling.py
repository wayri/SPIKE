# SPDX-License-Identifier: Apache-2.0
"""Original synthetic analytical/native oracles for bounded Studio coupling."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch
from python.spike_core.studio_board_coupling import run_studio_board_cosimulation, validate_studio_board_cosimulation
from python.spike_core.studio_board_coupling_contract import REQUEST
from python.spike_core.service_studio_board_coupling import prepare_studio_board_context, handle_studio_board_cosimulation_request


def request(mode="transient", dt=.1, alpha=0.):
    return {"contract":REQUEST,"board_revision":"fixture","mode":mode,
      "netlist":"Synthetic current-fed resistor\nI1 0 p 1\nRR1 p 0 2\n"+(f".tran {dt/10} 1\n" if mode=="transient" else ".op\n")+".end\n",
      "bindings":[{"element_id":"RR1","component_id":"r1","thermal_node_id":"body","reference_temperature_k":300.,"temperature_coefficient_per_k":alpha}],
      "thermal":{"ambient_temperature_k":300.,"nodes":[{"id":"body","capacitance_j_per_k":2.,"initial_temperature_k":300.,"minimum_temperature_k":290.,"maximum_temperature_k":400.}],
                 "links":[{"id":"cool","from_id":"body","to_id":"ambient","resistance_k_per_w":1.}]},
      "controls":{"window_s":dt,"electrical_step_s":dt/10,"stop_time_s":1.,"maximum_iterations":40,"temperature_tolerance_k":1e-9,"power_tolerance_w":1e-9,"balance_tolerance_w":1e-8,"relaxation":1.,"time_limit_s":120.}}


class AdmissionTests(unittest.TestCase):
    def test_missing_model_and_mapping_fail_closed(self):
        for mutate in (lambda r:r["bindings"].clear(),lambda r:r["thermal"]["links"].clear(),lambda r:r["controls"].update(relaxation=0.),lambda r:r.update(netlist="x\nD1 p 0 dm\n.model dm D(IS=1e-12)\n.op\n.end")):
            r=request();mutate(r)
            self.assertEqual(validate_studio_board_cosimulation(r)["status"],"rejected")
    def test_sweeps_waveforms_and_native_resistance_bounds(self):
        r=request();r["netlist"]=r["netlist"].replace("I1 0 p 1", "I1 0 p PULSE(0 1 0 0 0 .01 .1)")
        self.assertEqual(validate_studio_board_cosimulation(r)["status"],"rejected")
        r=request();r["netlist"]=r["netlist"].replace("RR1 p 0 2", "RR1 p 0 1e-7")
        self.assertEqual(validate_studio_board_cosimulation(r)["status"],"rejected")
        r=request();r["netlist"]=r["netlist"].replace(".end", ".step param RVAL list 1 2\\n.end".replace("\\n","\n"))
        self.assertEqual(validate_studio_board_cosimulation(r)["status"],"rejected")
    def test_geometry_must_match_nominal_and_expansion_positive(self):
        r=request();r["bindings"][0]["geometry"]={"length_m":.01,"width_m":.001,"thickness_m":.0001,"resistivity_ohm_m":2e-5,"expansion_per_k":.001}
        self.assertEqual(validate_studio_board_cosimulation(r)["status"],"accepted")
        r["bindings"][0]["geometry"]["resistivity_ohm_m"]=1e-8
        self.assertEqual(validate_studio_board_cosimulation(r)["status"],"rejected")
    def test_board_revision_and_alias(self):
        design={"components":[{"id":"r1","reference":"R1"},{"id":"r2","reference":"R2"}]}
        context=prepare_studio_board_context(design)
        r=request();r["board_revision"]=context["board_revision"]
        call=lambda:handle_studio_board_cosimulation_request("validate_studio_board_cosimulation",{"design":design,"request":r})
        self.assertEqual(call()["result"]["status"],"accepted")
        r["bindings"][0]["component_id"]="r2"
        self.assertFalse(call()["ok"])
        r["bindings"][0]["component_id"]="r1";r["board_revision"]="stale"
        self.assertEqual(call()["result"]["status"],"rejected")


class NativeBenchmarks(unittest.TestCase):
    def run_case(self,r,**kwargs):
        before=deepcopy(r)
        result=run_studio_board_cosimulation(r,**kwargs)
        self.assertEqual(result["status"],"completed",result)
        self.assertEqual(r,before)
        return result
    def test_constant_power_be_and_continuous_refinement(self):
        errors=[]
        for dt in (.2,.1,.05):
            result=self.run_case(request(dt=dt))
            t=result["frames"][-1]["temperature_k"]["body"]
            self.assertAlmostEqual(t,300+2*(1-(1+dt/2)**(-round(1/dt))),places=9)
            errors.append(abs(t-(300+2*(1-math.exp(-.5)))))
        self.assertLess(errors[1],.55*errors[0]);self.assertLess(errors[2],.55*errors[1])
    def test_transient_temperature_feedback_and_energy_ledger(self):
        r=request(alpha=.01)
        result=self.run_case(r)
        rise=0.
        for frame in result["frames"]:
            rise=(rise+.1)/(1+.1*(1-.02)/2)
            self.assertAlmostEqual(frame["temperature_k"]["body"],300+rise,places=7)
            energy=frame["energy"]
            self.assertAlmostEqual(energy["source_j"],energy["resistor_heat_j"]+energy["storage_change_j"]+energy["be_numerical_dissipation_j"],places=10)
    def test_timeout_publishes_no_unaccepted_frame(self):
        r=request();r["controls"]["time_limit_s"]=1e-12
        with patch("python.spike_core.studio_board_coupling.time.monotonic",side_effect=[0.,1.]):
            result=run_studio_board_cosimulation(r)
        self.assertEqual(result["status"],"timed_out",result)
        self.assertEqual(result["frames"],[])
    def test_steady_feedback_closed_form(self):
        result=self.run_case(request("steady_state",alpha=.01))
        self.assertAlmostEqual(result["frames"][-1]["temperature_k"]["body"],300+2/(1-.02),places=7)
    def test_real_electrical_rc_state_survives_window_replay(self):
        r=request(dt=.1)
        r["netlist"]="Synthetic RC\nV1 p 0 1\nRR1 p q 2\nC1 q 0 1\n.tran .01 1 UIC\n.end\n"
        result=self.run_case(r)
        v=result["frames"][-1]["electrical"]["node_voltage_v"]["q"]
        self.assertAlmostEqual(v,1-(1+.01/2)**-100,places=10)
        self.assertLess(abs(v-(1-math.exp(-.5))),.002)
    def test_ordinary_tran_initializes_from_operating_point(self):
        r=request();r["netlist"]="Synthetic RC\nV1 p 0 1\nRR1 p q 2\nC1 q 0 1\n.tran .01 1\n.end\n"
        result=self.run_case(r)
        self.assertAlmostEqual(result["frames"][-1]["electrical"]["node_voltage_v"]["q"],1.,places=10)
    def test_divider_op_is_frozen_across_temperature_iterations(self):
        r=request(alpha=.01)
        r["netlist"]="Divider RC\nV1 p 0 2\nRR1 p q 2\nRR2 q 0 2\nC1 q 0 1\n.tran .01 1\n.end\n"
        second=deepcopy(r["bindings"][0]);second.update(element_id="RR2",component_id="r2",temperature_coefficient_per_k=0.)
        r["bindings"].append(second)
        result=self.run_case(r)
        self.assertAlmostEqual(result["frames"][0]["energy"]["initial_stored_j"]["C1"],.5,places=12)
        self.assertLess(result["frames"][-1]["electrical"]["node_voltage_v"]["q"],1.)
    def test_narrow_pulse_heat_is_not_lost_between_samples(self):
        r=request();r["controls"]["electrical_step_s"]=.1
        r["netlist"]="Pulse heat\nI1 0 p PULSE(0 1 .025 .005 .005 .01 1)\nRR1 p 0 2\n.tran .1 1\n.end\n"
        coarse=self.run_case(r)
        self.assertAlmostEqual(sum(f["energy"]["resistor_heat_j"] for f in coarse["frames"]),.03,places=10)
        r["controls"]["electrical_step_s"]=.0001
        fine=self.run_case(r)
        exact=2*(.01+(.005+.005)/3)
        self.assertLess(abs(sum(f["energy"]["resistor_heat_j"] for f in fine["frames"])-exact),2e-6)
    def test_nonuniform_pwl_energy_and_replay(self):
        r=request();r["controls"]["electrical_step_s"]=.1
        r["netlist"]="PWL heat\nI1 0 p PWL(0 0 .023 0 .031 1 .047 0 1 0)\nRR1 p 0 2\n.tran .1 1\n.end\n"
        result=self.run_case(r)
        self.assertAlmostEqual(sum(f["energy"]["resistor_heat_j"] for f in result["frames"]),2*.008,places=10)
        self.assertEqual(result["accepted_history_sha256"],self.run_case(r)["accepted_history_sha256"])
    def test_geometry_feedback_closed_form(self):
        r=request("steady_state")
        r["bindings"][0]["geometry"]={"length_m":.01,"width_m":.001,"thickness_m":.0001,"resistivity_ohm_m":2e-5,"expansion_per_k":.001}
        frame=self.run_case(r)["frames"][-1]
        rise=(-1+math.sqrt(1+.008))/.002
        self.assertAlmostEqual(frame["temperature_k"]["body"],300+rise,places=7)
        self.assertAlmostEqual(frame["geometry"]["RR1"]["length_m"],.01*(1+.001*rise),places=10)
    def test_cancel_retains_only_accepted_windows(self):
        r=request();frames=[]
        result=run_studio_board_cosimulation(r,progress=frames.append,cancel_check=lambda:len(frames)>=2)
        self.assertEqual(result["status"],"cancelled")
        self.assertEqual(result["frames"],frames)
        self.assertEqual(len(frames),2)
    def test_unrelaxed_nonconvergence_does_not_publish(self):
        r=request("steady_state",alpha=.04);r["controls"]["maximum_iterations"]=2
        result=run_studio_board_cosimulation(r)
        self.assertEqual(result["status"],"failed_to_converge",result)
        self.assertEqual(result["frames"],[])

if __name__=="__main__":unittest.main()
