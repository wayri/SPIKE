# SPDX-License-Identifier: Apache-2.0
"""Independent synthetic numerical oracles; no hardware qualification."""
from dataclasses import replace
import json
import math
import unittest

from python.spikes.battery import (
    BatteryModel, BatteryState, CHEMISTRIES, generic_model, ocv, simulate,
)


class BatteryTests(unittest.TestCase):
    def ideal(self, **changes):
        return replace(BatteryModel(), ocv_soc_v=((0, 4), (1, 4)),
                       r0_ohm=0, r1_ohm=0, **changes)

    def test_coulomb_count_and_terminal_energy(self):
        result = simulate(self.ideal(), [0, 360], 1)
        final = result["samples"][-1]
        self.assertAlmostEqual(final["soc"], .4, places=13)
        self.assertAlmostEqual(final["terminal_energy_j"], 1440, places=10)
        self.assertEqual(final["generated_heat_j"], 0)
        self.assertAlmostEqual(final["throughput_ah"], .1)
        self.assertAlmostEqual(final["equivalent_full_cycles"], .05)
        self.assertEqual(final["temperature_k"], 298.15)

    def test_charge_and_discharge_efficiencies(self):
        model = self.ideal(charge_efficiency=.8, discharge_efficiency=.9)
        result = simulate(model, [0, 360, 720], [1, -1])
        self.assertAlmostEqual(result["samples"][1]["soc"], .5-.1/.9, places=13)
        self.assertAlmostEqual(result["final_state"]["soc"], .5-.1/.9+.08, places=13)
        self.assertAlmostEqual(result["samples"][-1]["terminal_energy_j"], 0, places=10)

    def test_rc_analytic_pulse_rest_and_energy_balance(self):
        model = replace(self.ideal(), r0_ohm=.1, r1_ohm=.2, c1_f=50)
        result = simulate(model, [0, 10, 20], [1, 0], max_step_s=10)
        first, last = result["samples"][1:]
        expected_vp = .2*(1-math.exp(-1))
        self.assertAlmostEqual(first["polarization_v"], expected_vp, places=14)
        self.assertAlmostEqual(last["polarization_v"], expected_vp*math.exp(-1), places=14)
        self.assertAlmostEqual(first["voltage_v"], 4-expected_vp, places=14)  # right-hand rest
        # Source energy = output + resistor heat + capacitor stored energy.
        stored = .5*50*last["polarization_v"]**2
        self.assertAlmostEqual(last["terminal_energy_j"]+last["generated_heat_j"]+stored, 40, places=11)

    def test_tiny_rc_step_nonnegative_loss(self):
        model = replace(self.ideal(), r1_ohm=1, c1_f=1e8)
        result = simulate(model, [0, 1e-3], 1)
        final = result["samples"][-1]
        self.assertGreater(final["generated_heat_j"], 0)
        self.assertAlmostEqual(final["polarization_v"], 1e-11, delta=1e-21)
        self.assertAlmostEqual(final["generated_heat_j"], 1e-25/3, delta=1e-35)

    def test_lumped_thermal_analytic_heating_and_cooling(self):
        model = replace(self.ideal(), r0_ohm=1, thermal_capacity_j_k=10,
                        thermal_resistance_k_w=2)
        result = simulate(model, [0, 20, 40], [2, 0], max_step_s=20)
        rise = 8*(1-math.exp(-1))
        self.assertAlmostEqual(result["samples"][1]["temperature_k"], 298.15+rise, places=12)
        self.assertAlmostEqual(result["samples"][2]["temperature_k"], 298.15+rise*math.exp(-1), places=12)

    def test_self_discharge_and_zero_current_polarization_relaxation(self):
        model = self.ideal(self_discharge_per_day=.1)
        final = simulate(model, [0, 86400], 0, max_step_s=3600)["final_state"]
        self.assertAlmostEqual(final["soc"], .5*math.exp(-.1), places=13)
        self.assertEqual(final["throughput_ah"], 0)

    def test_aging_calendar_and_cycle_rates_and_capacity_feedback(self):
        model = self.ideal(calendar_capacity_loss_per_day=.001,
                           cycle_capacity_loss_per_efc=.02,
                           calendar_resistance_growth_per_day=.002,
                           cycle_resistance_growth_per_efc=.04)
        result = simulate(model, [0, 360, 720], [1, -1], max_step_s=10)
        final = result["samples"][-1]
        loss = .001*720/86400+.02*.1
        self.assertAlmostEqual(final["capacity_soh"], 1-loss, places=12)
        self.assertAlmostEqual(final["resistance_growth"], 1+2*loss, places=12)
        self.assertLess(result["samples"][2]["capacity_ah"], result["samples"][1]["capacity_ah"])
        self.assertEqual(result["model_status"], "approximate_unqualified")

    def test_entropic_heat_sign_and_temperature_voltage(self):
        model = self.ideal(ocv_temperature_coefficient_v_k=.001)
        self.assertAlmostEqual(ocv(model, .5, 300), 4+.001*(300-298.15))
        discharge = simulate(model, [0, 1], 1)["samples"][-1]
        charge = simulate(model, [0, 1], -1)["samples"][-1]
        self.assertLess(discharge["temperature_k"], 298.15)
        self.assertGreater(charge["temperature_k"], 298.15)

    def test_ocv_interpolation_and_immutable_table(self):
        table = [[0, 2], [.5, 3], [1, 5]]
        model = BatteryModel(ocv_soc_v=table)
        table[0][1] = 100
        self.assertEqual(ocv(model, .25, 298.15), 2.5)
        self.assertEqual(ocv(model, .75, 298.15), 4)
        self.assertEqual(ocv(model, 1, 298.15), 5)

    def test_chemistry_catalog_is_explicitly_synthetic(self):
        self.assertGreaterEqual(len(CHEMISTRIES), 25)
        for identifier in CHEMISTRIES:
            model = generic_model(identifier)
            result = simulate(model, [0, 1], 0)
            self.assertIn("Synthetic", model.evidence_note)
            self.assertIn("not universal", result["limitations"][1])
            self.assertEqual(model.ocv_soc_v, BatteryModel().ocv_soc_v)
        with self.assertRaisesRegex(ValueError, "primary"):
            simulate(generic_model("alkaline"), [0, 1], -1)

    def test_invalid_parameters_states_and_tables(self):
        for kwargs in ({"nominal_capacity_ah": 0}, {"c1_f": -1}, {"r0_ohm": -1},
                       {"thermal_capacity_j_k": float("nan")}, {"max_current_a": True},
                       {"charge_efficiency": 1.1}, {"discharge_efficiency": 0},
                       {"chemistry": "not_a_chemistry"}, {"chemistry": []},
                       {"rechargeable": 1}, {"evidence_note": ""},
                       {"ocv_soc_v": [(0, 3), (0, 4), (1, 5)]},
                       {"ocv_soc_v": [(.1, 3), (1, 4)]},
                       {"ocv_soc_v": [(0, 3), (1, float("inf"))]},
                       {"min_temperature_k": 300}, {"calendar_capacity_loss_per_day": -.1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BatteryModel(**kwargs)
        for kwargs in ({"soc": -.1}, {"soc": 1.1}, {"soc": True},
                       {"temperature_k": 0}, {"polarization_v": float("nan")},
                       {"resistance_growth": .9}, {"capacity_soh": 0}, {"elapsed_s": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BatteryState(**kwargs)

    def test_no_soc_clipping_and_original_state_unchanged(self):
        state = BatteryState(soc=.1)
        with self.assertRaisesRegex(ValueError, "empty/full"):
            simulate(self.ideal(), [0, 1000], 1, initial_state=state)
        self.assertEqual(state.soc, .1)
        with self.assertRaisesRegex(ValueError, "empty/full"):
            simulate(self.ideal(), [0, 1], -1, initial_state=BatteryState(soc=1))

    def test_profiles_domains_and_resource_bounds(self):
        model = self.ideal()
        for times, current, extra in (([0, 0], 1, {}), ([1, 0], 1, {}),
                                     ([0, 1], [], {}), ([0, 1], 11, {}),
                                     ([0, float("inf")], 0, {}),
                                     ([0, 1], 0, {"ambient_k": 500}),
                                     ([0, 1], 0, {"max_step_s": 0}),
                                     ([0, 1e8], 0, {"max_step_s": 1}),
                                     ([0, 1], 0, {"initial_state": BatteryState(temperature_k=100)})):
            with self.subTest(times=times, current=current, extra=extra), self.assertRaises(ValueError):
                simulate(model, times, current, **extra)
        with self.assertRaisesRegex(ValueError, "reversal"):
            simulate(replace(model, r0_ohm=5), [0, 1], 1)
        with self.assertRaisesRegex(ValueError, "polarization"):
            simulate(model, [0, 1], 0, initial_state=BatteryState(polarization_v=.1))
        with self.assertRaisesRegex(ValueError, "SOH"):
            simulate(replace(model, calendar_capacity_loss_per_day=100), [0, 3600], 0)

    def test_serializable_replay_and_restart(self):
        model = BatteryModel()
        first = simulate(model, [0, 10], 1)
        json.dumps(first, allow_nan=False)
        second = simulate(model, [10, 20], 1, initial_state=BatteryState(**first["final_state"]))
        full = simulate(model, [0, 20], 1)
        self.assertEqual(second["final_state"], full["final_state"])
        self.assertEqual(first, simulate(model, [0, 10], 1))

    def test_coupled_temperature_aging_step_refinement(self):
        model = replace(BatteryModel(), r0_ohm=.4, r1_ohm=.2,
                        thermal_capacity_j_k=5, thermal_resistance_k_w=2,
                        resistance_temperature_coefficient_per_k=.04,
                        calendar_capacity_loss_per_day=.1,
                        aging_activation_temperature_k=3000)
        def result(step):
            return simulate(model, [0, 100], 2, max_step_s=step)["final_state"]
        reference, coarse, medium, fine = (result(step) for step in (.025, 2, 1, .5))
        for field in ("temperature_k", "capacity_soh", "soc"):
            errors = [abs(value[field]-reference[field]) for value in (coarse, medium, fine)]
            self.assertGreater(errors[0], errors[1])
            self.assertGreater(errors[1], errors[2])
            self.assertLess(errors[2], errors[0]*.35)


if __name__ == "__main__":
    unittest.main()
