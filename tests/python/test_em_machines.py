# SPDX-License-Identifier: Apache-2.0
"""Independent analytical and matrix-exponential EM machine checks."""
import copy
import json
import math
import unittest

import numpy as np
from scipy.linalg import expm

from python.spike_core.em_machines import MAX_STEPS, run_machine


def motor(**updates):
    result = {
        "model": "pm_dc_motor", "resistance_ohm": 2.0, "inductance_h": 0.02,
        "coupling_constant": 0.1, "inertia_kg_m2": 0.002,
        "damping_n_m_s_per_rad": 0.003, "shaft_torque_n_m": -0.01,
        "initial_current_a": 0.2, "initial_speed_rad_s": 2.0,
        "initial_angle_rad": 0.3, "duration_s": 0.2, "time_step_s": 0.001,
        "voltage_v": 12.0,
    }
    result.update(updates)
    return result


def generator(**updates):
    result = motor(model="pm_dc_generator", shaft_torque_n_m=0.2,
                   initial_current_a=0.0, initial_speed_rad_s=40.0)
    del result["voltage_v"]
    result["load_resistance_ohm"] = 8.0
    result.update(updates)
    return result


def magnet(**updates):
    result = {
        "model": "electromagnet", "turns": 200, "current_a": 1.2,
        "resistance_ohm": 3.0, "core_length_m": 0.1,
        "core_area_m2": 1e-4, "core_relative_permeability": 2000.0,
        "gap_length_m": 0.002, "gap_area_m2": 1.2e-4,
    }
    result.update(updates)
    return result


def exact_rotating(p):
    # Independent physical-coordinate affine matrix exponential, including angle.
    r, l, k, j, b = (p[key] for key in (
        "resistance_ohm", "inductance_h", "coupling_constant", "inertia_kg_m2",
        "damping_n_m_s_per_rad"))
    r += p.get("load_resistance_ohm", 0)
    matrix = np.array([
        [-r/l, -k/l, 0, p.get("voltage_v", 0)/l],
        [k/j, -b/j, 0, p["shaft_torque_n_m"]/j],
        [0, 1, 0, 0], [0, 0, 0, 0],
    ], dtype=float)
    initial = [p["initial_current_a"], p["initial_speed_rad_s"], p["initial_angle_rad"], 1]
    return (expm(matrix * p["duration_s"]) @ initial)[:3]


class MachineTests(unittest.TestCase):
    def test_motor_and_generator_converge_against_independent_exponential(self):
        for factory in (motor, generator):
            with self.subTest(model=factory()["model"]):
                errors = []
                p = factory(duration_s=0.08)
                exact = exact_rotating(p)
                scale = np.maximum(np.abs(exact), 1.0)
                for step in (0.004, 0.002, 0.001):
                    result = run_machine(dict(p, time_step_s=step))
                    actual = [result["summary"][key] for key in ("current_a", "speed_rad_s", "angle_rad")]
                    errors.append(np.linalg.norm((actual - exact) / scale))
                    self.assertLess(result["energy"]["relative_balance_residual"], 2e-12)
                self.assertGreater(errors[0]/errors[1], 3.5)
                self.assertGreater(errors[1]/errors[2], 3.5)
                self.assertLess(errors[2], 2e-4)

    def test_generator_opposes_rotation_and_dissipates_load_power(self):
        result = run_machine(generator())
        summary, energy = result["summary"], result["energy"]
        self.assertGreater(summary["speed_rad_s"], 0)
        self.assertLess(summary["torque_n_m"], 0)
        self.assertLess(summary["current_a"], 0)
        self.assertLess(summary["terminal_power_w"], 0)
        self.assertGreater(energy["load_energy_j"], 0)
        self.assertEqual(energy["terminal_electrical_work_j"], -energy["load_energy_j"])
        self.assertAlmostEqual(summary["terminal_voltage_v"], -8 * summary["current_a"])
        self.assertLess(abs(energy["balance_residual_j"]), 1e-12)

    def test_lossless_reciprocal_conversion_and_reversed_signs(self):
        p = motor(resistance_ohm=0, damping_n_m_s_per_rad=0, voltage_v=0,
                  shaft_torque_n_m=0, initial_current_a=0, initial_speed_rad_s=10)
        positive = run_machine(p)
        negative = run_machine(dict(p, initial_speed_rad_s=-10))
        for result in (positive, negative):
            energy = result["energy"]
            self.assertAlmostEqual(energy["initial_stored_energy_j"], energy["final_stored_energy_j"], places=12)
            self.assertLess(abs(energy["balance_residual_j"]), 1e-12)
        self.assertAlmostEqual(positive["summary"]["current_a"], -negative["summary"]["current_a"], places=12)
        self.assertAlmostEqual(positive["summary"]["speed_rad_s"], -negative["summary"]["speed_rad_s"], places=12)

    def test_uncoupled_rl_and_constant_acceleration(self):
        p = motor(coupling_constant=0, damping_n_m_s_per_rad=0, duration_s=0.1,
                  initial_current_a=0, shaft_torque_n_m=0.01, time_step_s=0.0001)
        result = run_machine(p)["summary"]
        exact_current = p["voltage_v"]/p["resistance_ohm"] * (1-math.exp(-p["resistance_ohm"]*p["duration_s"]/p["inductance_h"]))
        self.assertLess(abs(result["current_a"]-exact_current), 3e-8)
        accel = p["shaft_torque_n_m"]/p["inertia_kg_m2"]
        self.assertAlmostEqual(result["speed_rad_s"], 2 + accel*0.1, places=12)
        self.assertAlmostEqual(result["angle_rad"], 0.3 + 2*0.1 + 0.5*accel*0.1**2, places=12)

    def test_electromagnet_pressure_coenergy_and_current_scaling(self):
        p = magnet()
        result = run_machine(p)["summary"]
        mu0 = 4e-7*math.pi
        pressure_force = result["gap_flux_density_t"]**2*p["gap_area_m2"]/(2*mu0)
        self.assertAlmostEqual(result["gap_closing_force_n"], pressure_force, places=12)
        delta = p["gap_length_m"]*1e-4
        closed = run_machine(dict(p, gap_length_m=p["gap_length_m"]-delta))["summary"]["coenergy_j"]
        opened = run_machine(dict(p, gap_length_m=p["gap_length_m"]+delta))["summary"]["coenergy_j"]
        self.assertLess(abs((closed-opened)/(2*delta)/pressure_force-1), 2e-8)
        twice = run_machine(dict(p, current_a=2*p["current_a"]))["summary"]
        self.assertAlmostEqual(twice["gap_closing_force_n"], 4*pressure_force, places=12)
        reverse = run_machine(dict(p, current_a=-p["current_a"]))["summary"]
        self.assertEqual(reverse["gap_closing_force_n"], result["gap_closing_force_n"])
        self.assertEqual(reverse["flux_wb"], -result["flux_wb"])
        mmf_drop = result["core_flux_density_t"]*p["core_length_m"]/(mu0*p["core_relative_permeability"]) + result["gap_flux_density_t"]*p["gap_length_m"]/mu0
        self.assertAlmostEqual(mmf_drop, p["turns"]*p["current_a"], places=11)

    def test_source_binding_json_uniform_grid_and_no_mutation(self):
        p = motor(duration_s=1, time_step_s=0.3)
        original = copy.deepcopy(p)
        result = run_machine(p)
        self.assertEqual(p, original)
        self.assertEqual(result["histories"]["time_s"], [0, 0.25, 0.5, 0.75, 1])
        self.assertEqual(result["step_count"], 4)
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["model_status"], "experimental")
        self.assertEqual(len(result["request_sha256"]), 64)
        self.assertNotEqual(result["request_sha256"], run_machine(dict(p, voltage_v=10))["request_sha256"])
        json.dumps(result, allow_nan=False)

    def test_rejects_invalid_contracts_ranges_and_resource_requests(self):
        invalid = [None, [], {}, {"model": []}, motor(unexpected=1), motor(provenance=""),
                   motor(voltage_v=True), motor(voltage_v=float("inf")),
                   motor(voltage_v=10**400), motor(inductance_h=0), motor(inertia_kg_m2=-1),
                   motor(time_step_s=float("nan")), motor(duration_s=1, time_step_s=1/(MAX_STEPS+1)),
                   motor(resistance_ohm=1e9, inductance_h=1e-9, time_step_s=1, duration_s=1),
                   generator(load_resistance_ohm=-1), magnet(turns=2.5), magnet(turns=True),
                   magnet(gap_length_m=0), magnet(core_relative_permeability=0),
                   magnet(core_area_m2=1e-20)]
        missing = motor()
        del missing["inductance_h"]
        invalid.append(missing)
        for request in invalid:
            with self.subTest(request=str(request)[:100]), self.assertRaises(ValueError):
                run_machine(request)




class MachineIntegrationTests(unittest.TestCase):
    def test_worker_rejects_envelope_and_runs_source_bound_model(self):
        from python.spike_core.service_simulation_handlers import handle_simulation_request
        def call(params):
            return handle_simulation_request("run_em_machine", params, assembly_scope={}, solver_registry=None)
        self.assertFalse(call({"request": {}, "unexpected": 1})["ok"])
        self.assertFalse(call({"request": {"model": "unknown"}})["ok"])
        result = call({"request": generator()})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["request_sha256"], run_machine(generator())["request_sha256"])

    def test_cli_preserves_global_output_and_worker_route(self):
        from pathlib import Path
        from python.spike_core.cli import build_parser, dispatch
        args = build_parser().parse_args(["--output", "machine-result.json", "em-machine", "--request", "examples/em_machines/generator.json"])
        self.assertEqual(args.output, Path("machine-result.json"))
        result, code = dispatch(args)
        self.assertEqual(code, 0)
        self.assertEqual(result["model"], "pm_dc_generator")
        self.assertLess(result["summary"]["terminal_power_w"], 0)

if __name__ == "__main__":
    unittest.main()
