import math
import unittest

from python.spike_core.electrothermal_sharing import (
    DiodeInstance,
    DiodeParameters,
    ElectrothermalInputError,
    MismatchSpec,
    ParallelDiodeScenario,
    RunawayLimits,
    ThermalParameters,
    sample_diode_instances,
    simulate_parallel_diodes,
)


class ElectrothermalSharingReferenceTests(unittest.TestCase):
    def base_instance(self) -> DiodeInstance:
        return DiodeInstance(
            DiodeParameters("base", saturation_current_a=1e-12, ideality_factor=1.6, series_resistance_ohm=0.01),
            ThermalParameters(resistance_k_per_w=18.0, capacitance_j_per_k=0.08, initial_temperature_k=300.15),
        )

    def scenario(self, instances, **overrides) -> ParallelDiodeScenario:
        values = {
            "instances": tuple(instances),
            "total_current_a": 8.0,
            "duration_s": 0.1,
            "time_step_s": 0.002,
            "ambient_temperature_k": 300.15,
            "limits": RunawayLimits(
                warning_temperature_k=360.0,
                trip_temperature_k=390.0,
                warning_current_share=0.7,
                trip_current_share=0.9,
            ),
        }
        values.update(overrides)
        return ParallelDiodeScenario(**values)

    def test_exact_match_remains_electrically_and_thermally_balanced(self):
        instances = sample_diode_instances(self.base_instance(), 2, seed=81, exact_matched=True)
        result = simulate_parallel_diodes(self.scenario(instances))

        self.assertEqual(result.model_status, "reference_qualification_only")
        self.assertEqual(result.termination, "completed")
        self.assertAlmostEqual(result.final.currents_a[0], result.final.currents_a[1], places=12)
        self.assertAlmostEqual(result.final.temperatures_k[0], result.final.temperatures_k[1], places=12)
        self.assertFalse(any("current_share" in event.kind or "temperature" in event.kind for event in result.events))

    def test_seeded_mismatch_is_reproducible_and_not_hidden(self):
        mismatch = MismatchSpec(
            saturation_current_sigma_fraction=0.08,
            ideality_sigma_fraction=0.015,
            series_resistance_sigma_fraction=0.1,
        )
        first = sample_diode_instances(self.base_instance(), 4, seed=1234, mismatch=mismatch)
        second = sample_diode_instances(self.base_instance(), 4, seed=1234, mismatch=mismatch)
        different = sample_diode_instances(self.base_instance(), 4, seed=1235, mismatch=mismatch)

        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertNotEqual(first[0].electrical.saturation_current_a, first[1].electrical.saturation_current_a)

        nominal = sample_diode_instances(self.base_instance(), 2, seed=1, mismatch=MismatchSpec())
        self.assertEqual(nominal[0].electrical.saturation_current_a, nominal[1].electrical.saturation_current_a)

    def test_explicit_vf_mismatch_causes_current_hogging_and_thermal_divergence(self):
        low_vf = DiodeInstance(
            DiodeParameters("D_low_vf", saturation_current_a=4e-12, ideality_factor=1.52, series_resistance_ohm=0.006),
            ThermalParameters(resistance_k_per_w=45.0, capacitance_j_per_k=0.025, initial_temperature_k=301.0),
        )
        high_vf = DiodeInstance(
            DiodeParameters("D_high_vf", saturation_current_a=7e-13, ideality_factor=1.68, series_resistance_ohm=0.02),
            ThermalParameters(resistance_k_per_w=45.0, capacitance_j_per_k=0.025, initial_temperature_k=300.0),
        )
        result = simulate_parallel_diodes(
            self.scenario((low_vf, high_vf), duration_s=0.25, time_step_s=0.001, stop_on_trip=False)
        )

        self.assertGreater(result.final.current_shares[0], result.samples[0].current_shares[0])
        self.assertGreater(result.final.current_shares[0], 0.8)
        self.assertGreater(result.final.temperatures_k[0], result.final.temperatures_k[1] + 10.0)
        self.assertTrue(any(event.kind == "current_share_warning" for event in result.events))

    def test_mutual_thermal_coupling_reduces_temperature_separation(self):
        instances = (
            DiodeInstance(
                DiodeParameters("D1", saturation_current_a=3e-12, ideality_factor=1.55, series_resistance_ohm=0.008),
                ThermalParameters(30.0, 0.04, 301.0),
            ),
            DiodeInstance(
                DiodeParameters("D2", saturation_current_a=8e-13, ideality_factor=1.66, series_resistance_ohm=0.018),
                ThermalParameters(30.0, 0.04, 300.0),
            ),
        )
        uncoupled = simulate_parallel_diodes(self.scenario(instances, duration_s=0.15, stop_on_trip=False))
        coupled = simulate_parallel_diodes(
            self.scenario(
                instances,
                duration_s=0.15,
                stop_on_trip=False,
                mutual_thermal_conductance_w_per_k=((0.0, 0.15), (0.15, 0.0)),
            )
        )

        uncoupled_delta = abs(uncoupled.final.temperatures_k[0] - uncoupled.final.temperatures_k[1])
        coupled_delta = abs(coupled.final.temperatures_k[0] - coupled.final.temperatures_k[1])
        self.assertLess(coupled_delta, uncoupled_delta)

    def test_warning_and_trip_events_stop_the_reference_run(self):
        hot = DiodeInstance(
            DiodeParameters("D_hot", saturation_current_a=8e-12, ideality_factor=1.45, series_resistance_ohm=0.002),
            ThermalParameters(resistance_k_per_w=100.0, capacitance_j_per_k=0.01, initial_temperature_k=305.0),
        )
        cold = DiodeInstance(
            DiodeParameters("D_cold", saturation_current_a=2e-13, ideality_factor=1.9, series_resistance_ohm=0.03),
            ThermalParameters(resistance_k_per_w=100.0, capacitance_j_per_k=0.01, initial_temperature_k=300.0),
        )
        limits = RunawayLimits(
            warning_temperature_k=315.0,
            trip_temperature_k=330.0,
            warning_current_share=0.65,
            trip_current_share=0.92,
        )
        result = simulate_parallel_diodes(
            self.scenario((hot, cold), duration_s=1.0, time_step_s=0.0005, limits=limits)
        )

        self.assertEqual(result.termination, "tripped")
        self.assertLess(result.final.time_s, 1.0)
        severities = {event.severity for event in result.events}
        self.assertIn("warning", severities)
        self.assertIn("trip", severities)
        event_times = [event.time_s for event in result.events]
        self.assertTrue(all(math.isfinite(value) for value in event_times))

    def test_invalid_inputs_are_blocked_before_execution(self):
        instances = sample_diode_instances(self.base_instance(), 2, seed=1, exact_matched=True)
        invalid_cases = (
            self.scenario(instances, total_current_a=0.0),
            self.scenario(instances, time_step_s=float("nan")),
            self.scenario(instances, mutual_thermal_conductance_w_per_k=((0.0, 0.1), (0.2, 0.0))),
            self.scenario(
                instances,
                limits=RunawayLimits(
                    warning_temperature_k=400.0,
                    trip_temperature_k=390.0,
                    warning_current_share=0.7,
                    trip_current_share=0.9,
                ),
            ),
        )
        for scenario in invalid_cases:
            with self.subTest(scenario=scenario):
                with self.assertRaises(ElectrothermalInputError):
                    simulate_parallel_diodes(scenario)


if __name__ == "__main__":
    unittest.main()
