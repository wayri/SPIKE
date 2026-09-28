# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import copy
import json
import math
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from python.spike_core.transient_diode_field import CONTRACT, solve_transient_diode_field


def fixture(steps=10, duration=10.):
    return {"contract": CONTRACT, "thermal": {
        "contract": "spike/structured-solid-thermal-request/v1",
        "grid": {"shape": [1,1,1], "spacing_m": 1.},
        "materials": [{"id": "solid", "thermal_conductivity_w_mk": .05,
                       "density_kg_m3": 2., "specific_heat_j_kgk": 1.}],
        "material_ids": ["solid"], "heat_generation_w_m3": 0.,
        "boundaries": {a+b: ({"type": "temperature", "temperature_k": 300.} if a+b == "x_min"
                              else {"type": "adiabatic"}) for a in "xyz" for b in ("_min", "_max")},
        "study": {"type": "transient", "initial_temperature_k": 300.,
                  "time_step_s": duration/steps, "steps": steps, "output_stride": steps}},
        "devices": [{"id": "D1", "model": {"saturation_current_a": 1e-12, "ideality_factor": 1.,
                    "series_resistance_ohm": .02, "reference_temperature_k": 300.,
                    "bandgap_ev": 0., "saturation_temperature_exponent": 0.},
                    "cells": [0], "weights": [1.], "current_a": [.5]*steps}]}


class TransientDiodeFieldTests(unittest.TestCase):
    def test_cli_dispatches_example_without_promoting_qualification(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"result.json"
            run = subprocess.run([sys.executable, str(root/"scripts/run_structured_solid_thermal.py"),
                "--request", str(root/"examples/thermal/transient_diode_field_request.json"),
                "--result", str(output)], capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(output.read_text())
            self.assertEqual(result["contract"], "spike/transient-diode-field-result/v1")
            self.assertEqual(result["status"], "completed")
            self.assertFalse(result["qualification"]["production_qualified"])
            self.assertLess(abs(result["integrated_energy"]["residual_j"]), 1e-8)

    def test_implicit_linear_temperature_power_matches_exact_recurrence(self):
        request = fixture()
        request["thermal"]["study"]["output_stride"] = 1
        before = copy.deepcopy(request)
        result = solve_transient_diode_field(request)
        self.assertEqual(result["status"], "completed", result)
        a = .5 * 1.380649e-23 / 1.602176634e-19 * math.log1p(.5/1e-12)
        b = .5**2*.02
        # C=2 J/K, G=2*k=0.1 W/K, dt=1 s.
        exact = 300.
        for frame in result["frames"]:
            exact = (2*exact+.1*300+b)/(2+.1-a)
            self.assertLess(abs(frame["temperature_k"][0]-exact), 1e-8)
        self.assertLess(abs(result["temperature_k"][0]-exact), 1e-8)
        self.assertLess(abs(result["integrated_energy"]["residual_j"]), 1e-8)
        self.assertEqual(request, before)
        self.assertFalse(result["qualification"]["production_qualified"])
        json.dumps(result, allow_nan=False)

    def test_backward_euler_first_order_against_continuous_exact_solution(self):
        a = .5 * 1.380649e-23 / 1.602176634e-19 * math.log1p(.5/1e-12)
        equilibrium = (.1*300+.5**2*.02)/(.1-a)
        exact = equilibrium+(300-equilibrium)*math.exp(-(.1-a)*10/2)
        errors = []
        for steps in (10,20,40,80):
            result = solve_transient_diode_field(fixture(steps))
            self.assertEqual(result["status"], "completed", result)
            errors.append(abs(result["temperature_k"][0]-exact))
        self.assertTrue(all(math.log2(a/b) > .95 for a,b in zip(errors, errors[1:])), errors)

    def test_zero_drive_and_adiabatic_stored_energy(self):
        request = fixture(5)
        request["devices"][0]["current_a"] = [0.]*5
        request["thermal"]["boundaries"]["x_min"] = {"type": "adiabatic"}
        result = solve_transient_diode_field(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["temperature_k"], [300.])
        request["devices"][0]["current_a"] = [.1,.2,0.,.3,.1]
        result = solve_transient_diode_field(request)
        self.assertEqual(result["status"], "completed", result)
        energy = result["integrated_energy"]
        self.assertLess(abs(energy["device_heat_j"]-2*(result["temperature_k"][0]-300)), 1e-8)

    def test_two_cell_sampling_deposition_matches_dense_backward_euler(self):
        request = fixture(1, 1.)
        request["thermal"]["grid"] = {"shape": [2,1,1], "spacing_m": [.5,1.,1.]}
        request["thermal"]["material_ids"] = ["solid"]*2
        request["devices"][0].update(cells=[0,1], weights=[.25,.75])
        weights = np.array([.25,.75])
        a = .5 * 1.380649e-23 / 1.602176634e-19 * math.log1p(.5/1e-12)
        b = .5**2*.02
        # Half boundary G=.2, internal G=.1, capacity per cell=1.
        operator = np.array([[1.3,-.1],[-.1,1.1]])-a*np.outer(weights,weights)
        exact = np.linalg.solve(operator, np.array([360.,300.])+b*weights)
        result = solve_transient_diode_field(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertLess(float(np.max(abs(np.array(result["temperature_k"])-exact))), 1e-8)

    def test_realistic_temperature_law_passes_each_step(self):
        request = fixture(8)
        request["devices"][0]["model"].update(bandgap_ev=1.11, saturation_temperature_exponent=3.)
        result = solve_transient_diode_field(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertTrue(all(row["energy"]["passed"] for row in result["history"]))
        self.assertGreater(result["temperature_k"][0], 300)

    def test_no_partial_fields_on_cancel_or_late_failure(self):
        count = 0
        def cancelled():
            nonlocal count
            count += 1
            return count > 100
        request = fixture(10)
        result = solve_transient_diode_field(request, cancel_check=cancelled)
        self.assertEqual(result["status"], "cancelled", result)
        self.assertEqual(result["frames"], [])
        self.assertEqual(result["temperature_k"], [])
        request["devices"][0]["current_a"][-1] = 1e6
        result = solve_transient_diode_field(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertEqual(result["frames"], [])

    def test_unsaved_step_energy_failure_cannot_be_hidden(self):
        with patch("python.spike_core.transient_diode_field._energy", return_value={"passed": False}):
            result = solve_transient_diode_field(fixture())
        self.assertEqual(result["status"], "blocked", result)
        self.assertEqual(result["history"], [])

    def test_reject_unsupported_or_ambiguous_requests(self):
        for mutation in (
            lambda r: r.update(spice_netlist="ignored"),
            lambda r: r["devices"][0].update(current_a=[.5]),
            lambda r: r["devices"][0].update(weights=[.9]),
            lambda r: r["devices"][0].update(cells=[True]),
            lambda r: r["devices"][0]["current_a"].__setitem__(0,-.1),
            lambda r: r["devices"][0]["current_a"].__setitem__(0,".1"),
            lambda r: r["devices"][0]["model"].update(junction_capacitance_f=1e-9),
            lambda r: r.update(iteration={"max_iterations": 1}),
            lambda r: r.update(iteration={"max_iterations": 2, "relaxation": 1e-6}),
        ):
            request = fixture()
            mutation(request)
            result = solve_transient_diode_field(request)
            self.assertEqual(result["status"], "blocked", result)
            self.assertEqual(result["temperature_k"], [])

    def test_duration_and_energy_overflow_fail_closed(self):
        request = fixture()
        request["thermal"]["study"]["time_step_s"] = 1e308
        result = solve_transient_diode_field(request)
        self.assertEqual(result["status"], "blocked", result)
        request = fixture(1)
        # Exercise publication guard independently of the thermal solver:
        # finite accepted per-step powers can overflow when integrated.
        request["thermal"]["study"]["time_step_s"] = 1e308
        with patch("python.spike_core.transient_diode_field._energy", return_value={"passed": True,
                   "outward_boundary_power_w": 10., "storage_rate_w": 0.}):
            result = solve_transient_diode_field(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertEqual(result["frames"], [])
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
