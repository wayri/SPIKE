import math
import unittest
from dataclasses import FrozenInstanceError

from python.spikes.dynamic_devices import (
    DYNAMIC_DIODE_CONTRACT,
    DynamicDeviceModelError,
    DynamicDiodeModel,
    DynamicDiodeValidity,
    ReverseRecoveryState,
)


def central_difference(function, point, step):
    return (function(point + step) - function(point - step)) / (2.0 * step)


class DynamicDiodeModelTests(unittest.TestCase):
    def setUp(self):
        self.model = DynamicDiodeModel(
            saturation_current_a=2.0e-12,
            emission_coefficient=1.35,
            zero_bias_capacitance_f=18.0e-12,
            junction_potential_v=0.82,
            grading_coefficient=0.42,
            forward_depletion_coefficient=0.4,
            transit_time_s=32.0e-9,
            validity=DynamicDiodeValidity(
                minimum_voltage_v=-100.0,
                maximum_voltage_v=0.9,
                minimum_temperature_k=240.0,
                maximum_temperature_k=500.0,
                maximum_absolute_current_a=100.0,
                maximum_timestep_s=1.0e-3,
            ),
        )

    def test_contract_is_explicit_and_models_are_immutable(self):
        self.assertEqual(self.model.contract, DYNAMIC_DIODE_CONTRACT)
        with self.assertRaises(FrozenInstanceError):
            self.model.area = 2.0
        with self.assertRaises(FrozenInstanceError):
            ReverseRecoveryState().stored_charge_c = 1.0

    def test_shockley_current_has_exact_analytic_conductance(self):
        voltage = 0.48
        evaluation = self.model.evaluate(voltage, 300.15)
        numeric = central_difference(
            lambda value: self.model.evaluate(value, 300.15).current_a,
            voltage,
            1.0e-7,
        )
        self.assertGreater(evaluation.current_a, 0.0)
        self.assertAlmostEqual(evaluation.conductance_s, numeric, delta=abs(numeric) * 2.0e-9)
        self.assertAlmostEqual(
            evaluation.absorbed_power_w,
            voltage * evaluation.current_a,
            places=15,
        )

    def test_temperature_scaling_matches_declared_equation(self):
        nominal = self.model.saturation_current(300.15)
        hot = self.model.saturation_current(400.0)
        k_ev = 8.617333262145e-5
        ratio = 400.0 / self.model.nominal_temperature_k
        expected = (
            self.model.area
            * self.model.saturation_current_a
            * ratio ** self.model.saturation_current_exponent
            * math.exp(
                self.model.bandgap_ev
                / (self.model.emission_coefficient * k_ev)
                * (1.0 / self.model.nominal_temperature_k - 1.0 / 400.0)
            )
        )
        self.assertEqual(nominal, self.model.area * self.model.saturation_current_a)
        self.assertAlmostEqual(hot, expected, delta=expected * 1.0e-14)
        self.assertGreater(hot, nominal)

    def test_depletion_charge_derivative_matches_capacitance_on_both_branches(self):
        transition = (
            self.model.forward_depletion_coefficient * self.model.junction_potential_v
        )
        for voltage in (-5.0, 0.0, transition - 1.0e-5, transition + 1.0e-5, 0.7):
            _, capacitance = self.model.depletion_charge(voltage)
            numeric = central_difference(
                lambda value: self.model.depletion_charge(value)[0],
                voltage,
                1.0e-7,
            )
            self.assertAlmostEqual(capacitance, numeric, delta=max(1.0e-18, capacitance * 5.0e-8))

        q_left, c_left = self.model.depletion_charge(transition - 1.0e-10)
        q_right, c_right = self.model.depletion_charge(transition + 1.0e-10)
        self.assertAlmostEqual(q_left, q_right, delta=1.0e-19)
        self.assertAlmostEqual(c_left, c_right, delta=1.0e-19)

    def test_quasi_static_transport_charge_and_diffusion_capacitance(self):
        evaluation = self.model.evaluate(0.45, 300.15)
        self.assertAlmostEqual(
            evaluation.transport_charge_c,
            self.model.transit_time_s * evaluation.current_a,
            places=20,
        )
        self.assertAlmostEqual(
            evaluation.diffusion_capacitance_f,
            self.model.transit_time_s * evaluation.conductance_s,
            places=20,
        )
        self.assertEqual(
            evaluation.total_capacitance_f,
            evaluation.depletion_capacitance_f + evaluation.diffusion_capacitance_f,
        )

    def test_implicit_transport_state_converges_and_recovers_in_reverse(self):
        dt = 2.0e-9
        state = ReverseRecoveryState()
        forward = None
        for _ in range(1000):
            forward = self.model.advance(0.48, 0.48, 300.15, dt, state)
            state = forward.state
        assert forward is not None
        dc = self.model.evaluate(0.48, 300.15)
        target_charge = self.model.transit_time_s * dc.current_a
        self.assertAlmostEqual(state.stored_charge_c, target_charge, delta=target_charge * 1.0e-12)
        self.assertAlmostEqual(forward.transport_current_a, 0.0, delta=dc.current_a * 1.0e-12)

        recovery = self.model.advance(-5.0, 0.48, 300.15, dt, state)
        self.assertLess(recovery.transport_current_a, 0.0)
        self.assertLess(recovery.terminal_current_a, 0.0)
        self.assertLess(recovery.state.stored_charge_c, state.stored_charge_c)
        expected_charge = state.stored_charge_c / (1.0 + dt / self.model.transit_time_s)
        self.assertAlmostEqual(recovery.state.stored_charge_c, expected_charge, places=24)

    def test_transient_jacobian_matches_state_update_finite_difference(self):
        previous_state = ReverseRecoveryState(8.0e-12)
        voltage = 0.42
        result = self.model.advance(
            voltage, 0.39, 325.0, 4.0e-9, previous_state
        )
        numeric = central_difference(
            lambda value: self.model.advance(
                value, 0.39, 325.0, 4.0e-9, previous_state
            ).terminal_current_a,
            voltage,
            1.0e-7,
        )
        self.assertAlmostEqual(
            result.terminal_conductance_s,
            numeric,
            delta=max(1.0e-9, abs(numeric) * 2.0e-8),
        )

    def test_zero_transit_time_has_no_recovery_state(self):
        model = DynamicDiodeModel(
            zero_bias_capacitance_f=0.0,
            transit_time_s=0.0,
            validity=DynamicDiodeValidity(maximum_voltage_v=0.8),
        )
        result = model.advance(0.2, 0.1, 300.15, 1.0e-6)
        self.assertEqual(result.transport_current_a, 0.0)
        self.assertEqual(result.state.stored_charge_c, 0.0)
        self.assertAlmostEqual(result.terminal_current_a, result.conduction_current_a)

    def test_invalid_models_states_inputs_and_outputs_fail_closed(self):
        invalid_models = (
            {"saturation_current_a": 0.0},
            {"emission_coefficient": -1.0},
            {"area": float("nan")},
            {"grading_coefficient": 1.0},
            {"forward_depletion_coefficient": 1.0},
            {"transit_time_s": -1.0},
        )
        for values in invalid_models:
            with self.subTest(values=values), self.assertRaises(DynamicDeviceModelError):
                DynamicDiodeModel(**values)
        with self.assertRaises(DynamicDeviceModelError):
            ReverseRecoveryState(-1.0e-12)
        with self.assertRaisesRegex(DynamicDeviceModelError, "outside the qualified range"):
            self.model.evaluate(1.0, 300.15)
        with self.assertRaisesRegex(DynamicDeviceModelError, "outside the qualified range"):
            self.model.evaluate(0.0, 100.0)
        with self.assertRaisesRegex(DynamicDeviceModelError, "Timestep"):
            self.model.advance(0.0, 0.0, 300.15, 0.0)

        current_limited = DynamicDiodeModel(
            validity=DynamicDiodeValidity(
                maximum_voltage_v=0.8,
                maximum_absolute_current_a=1.0e-9,
            )
        )
        with self.assertRaisesRegex(DynamicDeviceModelError, "current"):
            current_limited.evaluate(0.5, 300.15)


if __name__ == "__main__":
    unittest.main()
