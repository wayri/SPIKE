"""Independent transport/native checks for the bounded actual PWM path.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Yawar B (wayri) and SPIKE contributors.
"""
import copy
import json
import os
from pathlib import Path
import unittest
from python.spike_core.pwm_electrothermal import REQUEST, run_pwm_electrothermal, validate_pwm_electrothermal

ROOT = Path(__file__).resolve().parents[2]


class AdmissionTests(unittest.TestCase):
    def test_defaults_and_resource_budget(self):
        value = validate_pwm_electrothermal({"contract": REQUEST, "parameters": {}})
        self.assertEqual(value["status"], "accepted")
        self.assertEqual(value["parameters"]["cycles"], 400)
        self.assertLess(value["maximum_electrical_steps"], 200001)

    def test_strict_invalid_controls(self):
        for params in ({"cycles": True}, {"cycles": 1.5}, {"cycles": 10000},
                       {"maximum_step_s": 1e-9}, {"maximum_step_s": 1e-3},
                       {"input_voltage_v": 10**400}, {"controller_kp_per_v": float("nan")},
                       {"unknown": 1}, {"target_voltage_v": 20}):
            with self.subTest(params=params), self.assertRaisesRegex(ValueError, "PWM_"):
                validate_pwm_electrothermal({"contract": REQUEST, "parameters": params})
        with self.assertRaisesRegex(ValueError, "PWM_REQUEST"):
            validate_pwm_electrothermal({"contract": REQUEST, "parameters": {}, "dll": "untrusted"})

    def test_early_cancellation_before_loading_engine(self):
        with self.assertRaisesRegex(ValueError, "PWM_CANCELLED"):
            run_pwm_electrothermal({"contract": REQUEST, "parameters": {}}, cancel_check=lambda: True)


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # CI must opt into an actual local build; this is never a fake backend.
        path = os.environ.get("SPIKE_PWM_TEST_LIBRARY")
        if not path:
            raise unittest.SkipTest("set SPIKE_PWM_TEST_LIBRARY to run real native integration")
        from python.spikes.native_abi import load_native_library
        cls.library = load_native_library(Path(path))

    def request(self, **params):
        return {"contract": REQUEST, "parameters": {"cycles": 4, **params}}

    def run_case(self, raw=None, **kwargs):
        return run_pwm_electrothermal(raw or self.request(), library=self.library, **kwargs)

    def test_actual_native_schema_and_energy(self):
        import jsonschema
        raw = self.request()
        saved = copy.deepcopy(raw)
        result = self.run_case(raw)
        for name, value in (("request", raw), ("result", result)):
            schema = json.loads((ROOT / f"schemas/pwm-electrothermal-{name}-v1.schema.json").read_text())
            jsonschema.Draft202012Validator(schema).validate(value)
        self.assertEqual(raw, saved)
        self.assertEqual(result["status"], "completed")
        self.assertGreater(result["runtime"]["diagnostics"]["completed_steps"], 200)
        self.assertEqual(len(result["windows"]), 4)
        for key in ("electrical_balance_j", "thermal_balance_j"):
            self.assertLess(abs(result["energy"][key]), 1e-12)
        self.assertGreater(result["energy"]["switch_j"], 0)
        self.assertGreater(result["energy"]["be_numerical_dissipation_j"], 0)

    def test_cancel_commits_only_full_cycle_and_restart_replays(self):
        stop = [False]
        partial = self.run_case(cancel_check=lambda: stop[0],
                                progress=lambda event: stop.__setitem__(0, event["completed_cycles"] == 2))
        self.assertEqual(partial["status"], "cancelled")
        self.assertEqual(partial["checkpoint"]["completed_cycles"], 2)
        raw = self.request()
        raw["restart"] = partial["checkpoint"]
        resumed = self.run_case(raw)
        reference = self.run_case()
        self.assertTrue(resumed["restart"]["verified"])
        self.assertEqual(resumed["windows"], reference["windows"])
        self.assertEqual(resumed["energy"], reference["energy"])

    def test_mid_cycle_cancel_rolls_back_publication(self):
        calls = [0]
        def cancel():
            calls[0] += 1
            return calls[0] >= 10
        result = self.run_case(cancel_check=cancel)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["windows"], [])
        self.assertEqual(result["checkpoint"]["completed_cycles"], 0)
        self.assertEqual(result["energy"]["source_j"], 0)

    def test_tampered_restart_and_configuration_are_rejected(self):
        result = self.run_case()
        for field in ("state_sha256", "configuration_sha256", "library_sha256"):
            token = dict(result["checkpoint"])
            token[field] = "0"*64
            raw = self.request()
            raw["restart"] = token
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "PWM_CHECKPOINT"):
                self.run_case(raw)

    def test_native_matches_independent_switched_reference_benchmark(self):
        # Frozen native result is itself gated against independently implemented
        # switched RK4/refinement in test_spikes_pwm_electrothermal.cpp.
        result = self.run_case(self.request(cycles=400, maximum_step_s=1e-6))
        last = result["windows"][-1]
        self.assertAlmostEqual(last["output_voltage_v"], 4.970668714801, delta=2e-10)
        self.assertAlmostEqual(last["winding_temperature_k"], 300.5279726869421, delta=2e-10)
        self.assertLess(abs(result["energy"]["thermal_balance_j"]), 1e-12)


if __name__ == "__main__":
    unittest.main()
