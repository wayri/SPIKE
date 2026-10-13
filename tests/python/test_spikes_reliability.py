# SPDX-License-Identifier: Apache-2.0
import json
import math
import unittest

from python.spikes.reliability import (
    BathtubHazard, WeibullHazard, arrhenius_acceleration, failure_delay_hours, report,
)
from python.spikes.environment_faults import Exposure, ParameterResponse, apply_combined_response
from python.spikes.fault_injection import FaultSite


class ReliabilityTests(unittest.TestCase):
    def test_fit_probability_and_quantile_in_device_hours(self):
        hazard = BathtubHazard(100)
        expected = -math.expm1(-100e-9*8760)
        self.assertAlmostEqual(hazard.probability(300, 8760), expected, delta=1e-16)
        self.assertAlmostEqual(failure_delay_hours(hazard, age_hours=100,
            quantile=0.5, horizon_hours=1e8), math.log(2)/100e-9, delta=1e-7)
        self.assertIsNone(failure_delay_hours(hazard, age_hours=0, quantile=0.5, horizon_hours=1))
        self.assertGreater(hazard.probability(1e20, 1e-10), 0)

    def test_bathtub_has_decreasing_early_and_increasing_wearout(self):
        hazard = BathtubHazard(10, WeibullHazard(0.5, 1e4), WeibullHazard(3, 1e4))
        rates = [hazard.rate_per_hour(t) for t in (1, 1000, 1e5)]
        self.assertGreater(rates[0], rates[1])
        self.assertGreater(rates[2], rates[1])
        # Independent antiderivative of the two power-law rates + constant term.
        expected = (20/1e4)**0.5-(10/1e4)**0.5 + (20/1e4)**3-(10/1e4)**3 + 10e-9*10
        self.assertAlmostEqual(hazard.cumulative_increment(10, 10), expected, delta=2e-17)
        self.assertAlmostEqual(hazard.probability(10, 10), -math.expm1(-expected), delta=2e-17)
        record = report(hazard, 0, 1)
        self.assertIsNone(record["hazard_per_hour"])
        self.assertIn("singular", record["unavailable_reason"])
        json.dumps(record, allow_nan=False)

    def test_cumulative_increment_composition_and_tiny_duration(self):
        term = WeibullHazard(2, 10)
        self.assertAlmostEqual(term.increment(3, 2), (25-9)/100, delta=1e-15)
        self.assertAlmostEqual(term.increment(3, 7), term.increment(3, 2)+term.increment(5, 5), delta=1e-15)
        # Subtraction of two full cumulative powers would lose this entirely.
        self.assertAlmostEqual(term.increment(1e12, 1e-6), 2e4, delta=1e-8)
        self.assertAlmostEqual(WeibullHazard(2, 1).increment(1e308, 1e-308), 2, delta=2e-12)
        self.assertAlmostEqual(WeibullHazard(0.5, 1e300).increment(1e-300, 1e300), 1, delta=2e-13)

    def test_conditional_inverse_matches_hazard_not_restart_at_birth(self):
        hazard = BathtubHazard(20, WeibullHazard(0.6, 100), WeibullHazard(3, 1000), 2)
        for age, quantile in ((0, 0.25), (500, 0.75), (10, 1e-30)):
            delay = failure_delay_hours(hazard, age_hours=age, quantile=quantile, horizon_hours=1e5)
            self.assertIsNotNone(delay)
            self.assertAlmostEqual(hazard.probability(age, delay)/quantile, 1, delta=1e-12)
            self.assertEqual(delay, failure_delay_hours(hazard, age_hours=age, quantile=quantile, horizon_hours=1e5))

    def test_large_shape_and_multiplier_do_not_break_small_interval_math(self):
        self.assertAlmostEqual(WeibullHazard(1e18, 1).increment(1, 1e-17), math.expm1(10), delta=2e-9)
        self.assertAlmostEqual(WeibullHazard(1e-20, 1).increment(1, 1), math.expm1(1e-20*math.log(2)), delta=1e-34)
        self.assertAlmostEqual(BathtubHazard(1e-315, multiplier=1e20).cumulative_increment(0, 1e308),
            1e4, delta=1e-3)  # The decimal subnormal FIT input itself is rounded.
        term = WeibullHazard(2, 1e150, weight=1e-100)
        self.assertAlmostEqual(BathtubHazard(0, wear_out=term, multiplier=1e300).cumulative_increment(0, 1),
            1e-100, delta=1e-112)

    def test_arrhenius_equal_temperature_and_supplied_acceleration(self):
        self.assertEqual(arrhenius_acceleration(300, 300, 0.7), 1)
        af = arrhenius_acceleration(400, 300, 0.7)
        self.assertGreater(af, 1)
        self.assertAlmostEqual(af*arrhenius_acceleration(300, 400, 0.7), 1, delta=1e-15)
        base, accelerated = BathtubHazard(100), BathtubHazard(100, multiplier=af)
        self.assertGreater(accelerated.probability(0, 100), base.probability(0, 100))

    def test_invalid_boolean_nonfinite_and_shapes_rejected(self):
        for value in (True, float("nan"), float("inf"), -1):
            with self.assertRaises(ValueError): BathtubHazard(value)
            with self.assertRaises(ValueError): Exposure(value)
        with self.assertRaises(ValueError): BathtubHazard(1, early_life=WeibullHazard(2, 1))
        with self.assertRaises(ValueError): BathtubHazard(1, wear_out=WeibullHazard(0.5, 1))
        for value in (0, 1, True, float("nan")):
            with self.assertRaises(ValueError): failure_delay_hours(BathtubHazard(1), age_hours=0, quantile=value, horizon_hours=1)


class EnvironmentTests(unittest.TestCase):
    def response(self, **changes):
        fields = dict(fault_site="vto", part_number="DEMO-NMOS-A", manufacturer="Synthetic",
            axis="dose_rad_si", reference=0, coefficient=-1e-5, baseline=2,
            minimum_exposure=0, maximum_exposure=1e5, parameter_unit="V",
            source_locator="original synthetic fixture", conditions="lot demo, stated bias and dose rate; no annealing",
            applicability_basis="what-if arithmetic; no physical qualification")
        return ParameterResponse(**(fields | changes))

    def test_dose_mapping_identity_and_unverified_status(self):
        response = self.response()
        result = response.evaluate(Exposure(300, dose_rad_si=1e4), part_number="demo-nmos-a", manufacturer="synthetic")
        self.assertEqual(result["value"], 1.9)
        self.assertEqual(result["model_status"], "unverified_scenario")
        for wrong in ("DEMO-NMOS", "DEMO-NMOS-B"):
            with self.assertRaisesRegex(ValueError, "different exact"):
                response.evaluate(Exposure(300), part_number=wrong, manufacturer="Synthetic")
        with self.assertRaisesRegex(ValueError, "outside"):
            response.evaluate(Exposure(300, dose_rad_si=2e5), part_number="DEMO-NMOS-A", manufacturer="Synthetic")

    def test_temperature_humidity_vibration_and_no_clamping(self):
        cases = (("temperature_k", 300, 400, 300, 0.01, Exposure(350), 10.5),
                 ("relative_humidity", 0, 1, 0, 2, Exposure(300, relative_humidity=0.5), 11),
                 ("vibration_rms_g", 0, 20, 0, 0.1, Exposure(300, vibration_rms_g=10), 11))
        for axis, lo, hi, ref, coefficient, exposure, expected in cases:
            response = self.response(axis=axis, minimum_exposure=lo, maximum_exposure=hi,
                reference=ref, baseline=10, coefficient=coefficient, parameter_unit="ohm")
            result = response.evaluate(exposure, part_number="DEMO-NMOS-A", manufacturer="Synthetic")
            self.assertAlmostEqual(result["value"], expected)
        with self.assertRaises(ValueError): Exposure(300, relative_humidity=2)
        with self.assertRaises(ValueError): self.response(axis="dose_rad_sio2")
        negative = self.response(coefficient=-10, parameter_unit="ohm")
        with self.assertRaisesRegex(ValueError, "invalid parameter"):
            negative.evaluate(Exposure(300, dose_rad_si=1), part_number="DEMO-NMOS-A", manufacturer="Synthetic")

    def test_apply_uses_same_named_fault_api_and_retains_evidence(self):
        class Target:
            changes = []
            fault_sites = {"vto": FaultSite("vto", "M1", "threshold_voltage_v", 2, -10, 10, "exposure")}
            def inject_fault(self, name, value): self.changes.append((name, value))
        target = Target()
        response = self.response(reviewed=True)
        result = response.apply(target, Exposure(300, dose_rad_si=100), part_number="DEMO-NMOS-A", manufacturer="Synthetic")
        self.assertEqual(target.changes, [("vto", 1.999)])
        self.assertEqual(result["source_locator"], response.source_locator)
        self.assertEqual(result["model_status"], "conditional_calibrated_mapping")

    def test_combined_stresses_add_deltas_without_repeated_damage_or_double_count(self):
        class Target:
            changes = []
            fault_sites = {"vto": FaultSite("vto", "M1", "threshold_voltage_v", 2, -10, 10, "exposure")}
            def inject_fault(self, name, value): self.changes.append((name, value))
        dose = self.response()
        temperature = self.response(axis="temperature_k", reference=300, minimum_exposure=250,
            maximum_exposure=400, coefficient=0.001)
        target = Target()
        exposure = Exposure(350, dose_rad_si=1e4)
        for _ in range(2):
            result = apply_combined_response(target, [dose, temperature], exposure,
                part_number="DEMO-NMOS-A", manufacturer="Synthetic")
            self.assertAlmostEqual(result["value"], 1.95)
        self.assertEqual(target.changes[0], target.changes[1])
        before = list(target.changes)
        with self.assertRaisesRegex(ValueError, "double-count"):
            apply_combined_response(target, [dose, dose], exposure,
                part_number="DEMO-NMOS-A", manufacturer="Synthetic")
        self.assertEqual(target.changes, before)

    def test_unit_and_baseline_mismatches_rejected_before_mutation(self):
        class Target:
            changes = []
            fault_sites = {"vto": FaultSite("vto", "M1", "threshold_voltage_v", 2, -10, 10, "exposure")}
            def inject_fault(self, name, value): self.changes.append((name, value))
        target = Target()
        for response in (self.response(parameter_unit="ohm"), self.response(baseline=1)):
            with self.assertRaisesRegex(ValueError, "conflicts"):
                response.apply(target, Exposure(300), part_number="DEMO-NMOS-A", manufacturer="Synthetic")
            with self.assertRaisesRegex(ValueError, "conflicts"):
                apply_combined_response(target, [response], Exposure(300), part_number="DEMO-NMOS-A", manufacturer="Synthetic")
        self.assertEqual(target.changes, [])


if __name__ == "__main__":
    unittest.main()
