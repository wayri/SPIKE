import math
import os
from pathlib import Path
import unittest

from python.spikes import DMM, SpectrumAnalyzer, native_transient_waveform
from python.spikes.native_abi import NativeABIError, load_native_library


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = Path(os.environ.get(
    "SPIKES_TEST_NATIVE_LIBRARY",
    ROOT / "build-peec-native" / "spikes_c_api.dll",
))


@unittest.skipUnless(LIBRARY.is_file(), "built SPIKES C ABI library is unavailable")
class SpikesNativeABITests(unittest.TestCase):
    def setUp(self):
        self.library = load_native_library(LIBRARY)

    def test_owned_kernel_solves_voltage_divider_and_exposes_diagnostics(self):
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("V1", "in", "0", 10.0)
            circuit.add_resistor("R1", "in", "out", 1000.0)
            circuit.add_resistor("R2", "out", "0", 1000.0)
            with circuit.solve_operating_point() as result:
                self.assertEqual(result.status, "converged")
                self.assertAlmostEqual(result.node_voltage("out"), 5.0)
                self.assertAlmostEqual(result.element_power("R1"), 0.025)
                self.assertEqual(result.diagnostics()["matrix_order"], 3)

    def test_diode_and_native_failures_cross_the_boundary_safely(self):
        with self.library.circuit() as circuit:
            circuit.add_current_source("I1", "0", "junction", 1.0e-3)
            circuit.add_diode("D1", "junction", "0", saturation_current_a=1.0e-12)
            with circuit.solve_operating_point() as result:
                self.assertEqual(result.status, "converged")
                self.assertTrue(0.5 < result.node_voltage("junction") < 0.6)
                with self.assertRaises(NativeABIError):
                    result.node_voltage("missing")

    def test_native_level1_mosfet_solves_four_terminal_dc(self):
        if not self.library.mosfet_level1_available:
            self.skipTest("loaded native library predates MOSFET Level-1")
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("Vs", "rail", "0", 10.0)
            circuit.add_voltage_source("Vg", "gate", "0", 5.0)
            circuit.add_resistor("Rload", "rail", "drain", 1000.0)
            circuit.add_mosfet_level1(
                "M1", "drain", "gate", "0", "0",
                transconductance_a_per_v2=1.0e-2,
                channel_length_modulation_per_v=0.02,
                body_effect_sqrt_v=0.4,
            )
            with circuit.solve_operating_point() as result:
                self.assertEqual(result.status, "converged")
                self.assertGreater(result.node_voltage("drain"), 0.0)
                self.assertLess(result.node_voltage("drain"), 0.5)
                self.assertAlmostEqual(
                    result.element_current("M1"),
                    result.element_current("Rload"), places=8,
                )

    def test_native_ebers_moll_bjt_solves_three_terminal_dc(self):
        if not self.library.bjt_ebers_moll_available:
            self.skipTest("loaded native library predates Ebers-Moll BJT")
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("Vcc", "rail", "0", 5.0)
            circuit.add_voltage_source("Vb", "base", "0", 0.70)
            circuit.add_resistor("Rc", "rail", "collector", 1000.0)
            circuit.add_bjt_ebers_moll(
                "Q1", "collector", "base", "0",
                saturation_current_a=1.0e-15,
                forward_alpha=0.99,
                reverse_alpha=0.5,
            )
            with circuit.solve_operating_point() as result:
                self.assertEqual(result.status, "converged")
                self.assertGreater(result.node_voltage("collector"), 3.0)
                self.assertLess(result.node_voltage("collector"), 5.0)
                self.assertAlmostEqual(
                    result.element_current("Q1"),
                    result.element_current("Rc"), places=8,
                )

    def test_native_wbg_fet_solves_coupled_electrothermal_dc(self):
        if not self.library.wbg_fet_electrothermal_available:
            self.skipTest("loaded native library predates electrothermal WBG FET")
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("Vd", "drain", "0", 10.0)
            circuit.add_voltage_source("Vg", "gate", "0", 5.0)
            circuit.add_wbg_fet_electrothermal(
                "QW1", "drain", "gate", "0", "0", "tj_rise",
                technology="sic_mosfet",
                transconductance_a_per_v2=0.1,
                thermal_resistance_k_per_w=2.0,
            )
            with circuit.solve_operating_point() as result:
                self.assertEqual(result.status, "converged")
                rise = result.node_voltage("tj_rise")
                power = result.element_power("QW1")
                self.assertGreater(rise, 0.0)
                self.assertAlmostEqual(rise, 2.0 * power, places=7)
                self.assertGreater(result.element_current("QW1"), 0.0)
        with self.library.circuit() as circuit:
            with self.assertRaisesRegex(ValueError, "technology"):
                circuit.add_wbg_fet_electrothermal(
                    "Qbad", "d", "g", "0", "0", "tj",
                    technology="diamond",
                )
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("Vd", "drain", "0", 10.0)
            circuit.add_voltage_source("Vg", "gate", "0", 5.0)
            circuit.add_wbg_fet_electrothermal(
                "QW1", "drain", "gate", "0", "0", "tj_rise"
            )
            with circuit.solve_transient(
                time_step_s=1.0e-9,
                stop_time_s=10.0e-9,
                initialize_from_operating_point=False,
                integration_method="bdf2",
            ) as result:
                self.assertEqual(result.status, "converged")
                self.assertEqual(result.point_count, 10)
                self.assertGreater(result.node_voltage(9, "tj_rise"), 0.0)
                self.assertTrue(math.isfinite(result.element_current(9, "QW1")))
                diagnostics = result.diagnostics()
                self.assertGreater(diagnostics["total_newton_iterations"], 0)
            with circuit.solve_transient(
                time_step_s=1.0e-9,
                stop_time_s=10.0e-9,
                initialize_from_operating_point=False,
                integration_method="hybrid_trapezoidal",
            ) as result:
                self.assertEqual(result.status, "numerical_failure")
                self.assertIn("require backward Euler or BDF2", result.message)

    def test_configurable_cg_solver_is_native_and_fails_closed_on_mna(self):
        self.assertTrue(self.library.linear_solver_options_available)
        with self.library.circuit() as circuit:
            circuit.add_current_source("I1", "0", "out", 1.0e-3)
            circuit.add_resistor("R1", "out", "0", 1000.0)
            with circuit.solve_operating_point(
                linear_solver="conjugate_gradient", linear_threads=2
            ) as result:
                self.assertEqual(result.status, "converged")
                self.assertAlmostEqual(result.node_voltage("out"), 1.0)
                diagnostics = result.diagnostics()
                self.assertEqual(diagnostics["linear_solver"], "conjugate_gradient")
                self.assertEqual(diagnostics["linear_iterations"], 1)
                self.assertEqual(diagnostics["linear_threads"], 2)
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("V1", "out", "0", 1.0)
            circuit.add_resistor("R1", "out", "0", 1.0)
            with circuit.solve_operating_point(
                linear_solver="conjugate_gradient"
            ) as result:
                self.assertEqual(result.status, "numerical_failure")
                self.assertIn("positive-definite", result.message)
            with circuit.solve_operating_point(
                linear_solver="gmres", linear_threads=2
            ) as result:
                self.assertEqual(result.status, "converged")
                self.assertAlmostEqual(result.node_voltage("out"), 1.0)
                diagnostics = result.diagnostics()
                self.assertEqual(diagnostics["linear_solver"], "gmres")
                self.assertGreater(diagnostics["linear_iterations"], 0)
                self.assertEqual(diagnostics["linear_threads"], 2)

    def test_sparse_lu_and_ilu_gmres_are_exposed_with_sparse_diagnostics(self):
        for method in ("sparse_lu", "ilu_gmres", "sparse_qr"):
            with self.subTest(method=method), self.library.circuit() as circuit:
                circuit.add_voltage_source("V1", "in", "0", 10.0)
                circuit.add_resistor("R1", "in", "out", 1000.0)
                circuit.add_resistor("R2", "out", "0", 1000.0)
                with circuit.solve_operating_point(linear_solver=method) as result:
                    self.assertEqual(result.status, "converged")
                    self.assertAlmostEqual(result.node_voltage("out"), 5.0)
                    diagnostics = result.diagnostics()
                    self.assertEqual(diagnostics["linear_solver"], method)
                    self.assertGreater(diagnostics["matrix_nonzeros"], 0)
                    self.assertLess(diagnostics["matrix_nonzeros"], 9)
                    self.assertGreaterEqual(
                        diagnostics["numeric_factorizations"], 1
                    )
        with self.assertRaisesRegex(ValueError, "sparse_lu"):
            with self.library.circuit() as circuit:
                circuit.solve_operating_point(linear_solver="not-a-solver")

    def test_python_and_native_lifetimes_and_values_fail_closed(self):
        circuit = self.library.circuit()
        with self.assertRaises(ValueError):
            circuit.add_resistor("R1", "a", "0", math.inf)
        with self.assertRaises(NativeABIError):
            circuit.add_resistor("R1", "a", "0", 0.0)
        circuit.close()
        with self.assertRaises(NativeABIError):
            circuit.solve_operating_point()

    def test_owned_transient_api_exposes_rc_waveform_and_bounds(self):
        self.assertTrue(self.library.transient_available)
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("V1", "in", "0", 1.0)
            circuit.add_resistor("R1", "in", "out", 1000.0)
            circuit.add_capacitor("C1", "out", "0", 1.0e-6)
            with circuit.solve_transient(
                time_step_s=1.0e-4,
                stop_time_s=1.0e-3,
                initialize_from_operating_point=False,
            ) as result:
                self.assertEqual(result.status, "converged")
                self.assertEqual(result.point_count, 10)
                self.assertAlmostEqual(result.time(9), 1.0e-3)
                expected = 1.0 - (1.0 / 1.1) ** 10
                self.assertAlmostEqual(result.node_voltage(9, "out"), expected)
                diagnostics = result.diagnostics()
                self.assertEqual(diagnostics["completed_steps"], 10)
                self.assertEqual(diagnostics["matrix_factorizations"], 1)
                self.assertEqual(diagnostics["factorization_reuses"], 9)
                self.assertEqual(diagnostics["backward_euler_steps"], 10)
                self.assertEqual(diagnostics["trapezoidal_steps"], 0)
                waveform = native_transient_waveform(result, quantity="voltage", target="out")
                self.assertEqual(len(waveform.samples), 10)
                self.assertGreater(DMM().rms(waveform).value, 0.0)
                self.assertTrue(SpectrumAnalyzer().analyze(waveform).frequency_hz)
                with self.assertRaises(NativeABIError):
                    result.time(10)

    def test_native_dynamic_diode_exposes_reverse_recovery_tail(self):
        if not self.library.dynamic_diode_available:
            self.skipTest("loaded native library predates dynamic diodes")
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("Vreverse", "rail", "0", -5.0)
            circuit.add_resistor("Rlimit", "rail", "anode", 10.0)
            circuit.add_dynamic_diode(
                "Drr", "anode", "0",
                transit_time_s=100.0e-9,
                junction_capacitance_f=0.0,
                initial_stored_charge_c=1.0e-9,
            )
            with circuit.solve_transient(
                time_step_s=1.0e-9,
                stop_time_s=300.0e-9,
                max_steps=1000,
                initialize_from_operating_point=False,
            ) as result:
                self.assertEqual(result.status, "converged")
                initial = result.element_current(0, "Drr")
                final = result.element_current(result.point_count - 1, "Drr")
                self.assertLess(initial, -8.0e-3)
                self.assertLess(final, 0.0)
                self.assertLess(abs(final), 0.08 * abs(initial))
                self.assertAlmostEqual(
                    result.element_current(0, "Rlimit"), initial, places=9
                )

    def test_native_electrothermal_resistor_heats_and_derates(self):
        if not self.library.electrothermal_resistor_available:
            self.skipTest("loaded native library predates electrothermal resistors")
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("Vheat", "rail", "0", 10.0)
            circuit.add_electrothermal_resistor(
                "Rth", "rail", "0", "temp",
                resistance_ohm=10.0,
                temperature_coefficient_per_k=1.0e-2,
                thermal_resistance_k_per_w=1.0,
                thermal_capacitance_j_per_k=1.0e-2,
                minimum_temperature_k=250.0,
            )
            with circuit.solve_transient(
                time_step_s=1.0e-3,
                stop_time_s=50.0e-3,
                max_steps=100,
                initialize_from_operating_point=False,
                integration_method="bdf2",
            ) as result:
                self.assertEqual(result.status, "converged")
                last = result.point_count - 1
                self.assertGreater(result.node_voltage(last, "temp"), 8.0)
                self.assertLess(
                    result.element_current(last, "Rth"),
                    result.element_current(0, "Rth"),
                )

    def test_native_saturating_inductor_accelerates_above_knee(self):
        if not self.library.saturating_inductor_available:
            self.skipTest("loaded native library predates saturating inductors")
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("V1", "drive", "0", 1.0)
            circuit.add_saturating_inductor(
                "Lsat", "drive", "0",
                unsaturated_inductance_h=1.0e-3,
                saturated_inductance_h=1.0e-4,
                saturation_current_a=0.1,
            )
            with circuit.solve_transient(
                time_step_s=10.0e-6,
                stop_time_s=1.0e-3,
                max_steps=200,
                initialize_from_operating_point=False,
                integration_method="bdf2",
            ) as result:
                self.assertEqual(result.status, "converged")
                final = result.element_current(result.point_count - 1, "Lsat")
                self.assertGreater(final, 8.5)
                self.assertLess(final, 9.5)

    def test_hybrid_trapezoidal_improves_smooth_rc_accuracy(self):
        self.assertTrue(self.library.integration_method_available)
        values = {}
        diagnostics = {}
        for method in ("backward_euler", "hybrid_trapezoidal"):
            with self.library.circuit() as circuit:
                circuit.add_voltage_source("V1", "in", "0", 1.0)
                circuit.add_resistor("R1", "in", "out", 1000.0)
                circuit.add_capacitor("C1", "out", "0", 1.0e-6)
                with circuit.solve_transient(
                    time_step_s=1.0e-4,
                    stop_time_s=1.0e-3,
                    initialize_from_operating_point=False,
                    integration_method=method,
                ) as result:
                    values[method] = result.node_voltage(9, "out")
                    diagnostics[method] = result.diagnostics()
        exact = 1.0 - math.exp(-1.0)
        self.assertLess(
            abs(values["hybrid_trapezoidal"] - exact),
            0.15 * abs(values["backward_euler"] - exact),
        )
        hybrid = diagnostics["hybrid_trapezoidal"]
        self.assertEqual(hybrid["backward_euler_steps"], 1)
        self.assertEqual(hybrid["trapezoidal_steps"], 9)
        self.assertEqual(hybrid["matrix_factorizations"], 2)
        self.assertEqual(hybrid["factorization_reuses"], 8)

    def test_bdf2_improves_rc_accuracy_and_persists_two_step_history(self):
        if not self.library.bdf2_available:
            self.skipTest("loaded native library predates BDF2")
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("V1", "in", "0", 1.0)
            circuit.add_resistor("R1", "in", "out", 1000.0)
            circuit.add_capacitor("C1", "out", "0", 1.0e-6)
            with circuit.solve_transient(
                time_step_s=1.0e-4,
                stop_time_s=1.0e-3,
                initialize_from_operating_point=False,
                integration_method="bdf2",
            ) as result:
                exact = 1.0 - math.exp(-1.0)
                self.assertLess(abs(result.node_voltage(9, "out") - exact), 0.01)
                diagnostics = result.diagnostics()
                self.assertEqual(diagnostics["backward_euler_steps"], 1)
                self.assertEqual(diagnostics["bdf2_steps"], 9)

            with circuit.transient_session(
                integration_method="bdf2"
            ) as session:
                for _ in range(4):
                    self.assertTrue(session.step(1.0e-4))
                diagnostics = session.diagnostics()
                self.assertEqual(diagnostics["backward_euler_steps"], 1)
                self.assertEqual(diagnostics["bdf2_steps"], 3)

    def test_adaptive_bdf2_rejects_and_refines_rc_steps(self):
        if not self.library.adaptive_transient_available:
            self.skipTest("loaded native library predates adaptive transient stepping")
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("V1", "in", "0", 1.0)
            circuit.add_resistor("R1", "in", "out", 1000.0)
            circuit.add_capacitor("C1", "out", "0", 1.0e-6)
            with circuit.solve_transient(
                time_step_s=1.0e-4,
                minimum_time_step_s=1.0e-8,
                stop_time_s=1.0e-3,
                initialize_from_operating_point=False,
                integration_method="bdf2",
                adaptive_time_step=True,
                lte_absolute_tolerance=1.0e-5,
                lte_relative_tolerance=1.0e-3,
            ) as result:
                exact = 1.0 - math.exp(-1.0)
                final_index = result.point_count - 1
                self.assertLess(
                    abs(result.node_voltage(final_index, "out") - exact), 0.01
                )
                diagnostics = result.diagnostics()
                self.assertGreater(diagnostics["rejected_lte_steps"], 0)
                self.assertGreater(diagnostics["embedded_lte_solves"], 0)
                self.assertLess(diagnostics["minimum_accepted_step_s"], 1.0e-4)
                self.assertLessEqual(diagnostics["maximum_accepted_step_s"], 1.0e-4)

    def test_large_linear_transient_uses_sparse_symbolic_reuse(self):
        if not self.library.sparse_lte_diagnostics_available:
            self.skipTest("loaded native library predates sparse transient diagnostics")
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("V1", "n0", "0", 1.0)
            for index in range(130):
                left = f"n{index}"
                right = f"n{index + 1}"
                circuit.add_resistor(f"R{index}", left, right, 10.0)
                circuit.add_capacitor(f"C{index}", right, "0", 1.0e-9)
            with circuit.solve_transient(
                time_step_s=1.0e-8,
                stop_time_s=2.5e-8,
                initialize_from_operating_point=False,
            ) as result:
                self.assertEqual(result.status, "converged")
                diagnostics = result.diagnostics()
                self.assertEqual(diagnostics["sparse_assemblies"], 3)
                self.assertEqual(diagnostics["sparse_symbolic_analyses"], 1)
                self.assertEqual(diagnostics["sparse_numeric_factorizations"], 2)
                self.assertEqual(diagnostics["partial_numeric_refactorizations"], 1)

    def test_native_pulse_and_pwl_sources_align_switching_edges(self):
        self.assertTrue(self.library.waveform_sources_available)
        with self.library.circuit() as circuit:
            circuit.add_pulse_voltage_source(
                "Vpwm", "gate", "0", initial_value=0.0, pulsed_value=5.0,
                delay_s=0.25, rise_time_s=0.1, fall_time_s=0.1,
                pulse_width_s=0.4, period_s=1.0,
            )
            circuit.add_resistor("R1", "gate", "0", 10.0)
            self.assertTrue(self.library.voltage_controlled_switch_available)
            circuit.add_voltage_source("Vs", "in", "0", 10.0)
            circuit.add_voltage_controlled_switch(
                "S1", "in", "out", "gate", "0", on_resistance_ohm=1.0,
                off_resistance_ohm=1.0e6, threshold_voltage_v=2.5,
                transition_voltage_v=0.1,
            )
            circuit.add_resistor("Rload", "out", "0", 10.0)
            with circuit.solve_transient(
                time_step_s=0.7, stop_time_s=0.9,
                initialize_from_operating_point=False,
            ) as result:
                times = [result.time(index) for index in range(result.point_count)]
                for edge in (0.25, 0.35, 0.75, 0.85):
                    self.assertTrue(any(abs(time - edge) < 2.0e-15 for time in times))
                high_index = next(
                    index for index, time in enumerate(times) if abs(time - 0.35) < 2.0e-15
                )
                self.assertAlmostEqual(
                    result.node_voltage(high_index, "out"), 10.0 * 10.0 / 11.0
                )

        with self.library.circuit() as circuit:
            circuit.add_pwl_voltage_source(
                "Vshape", "out", "0", ((0.2, 0.0), (0.5, 3.0), (0.9, 1.0))
            )
            circuit.add_resistor("R2", "out", "0", 2.0)
            with circuit.solve_transient(
                time_step_s=1.0, stop_time_s=1.0,
                initialize_from_operating_point=False,
            ) as result:
                self.assertAlmostEqual(result.time(1), 0.5)
                self.assertAlmostEqual(result.node_voltage(1, "out"), 3.0)

    def test_transient_python_options_and_dynamic_models_fail_closed(self):
        with self.library.circuit() as circuit:
            with self.assertRaises(NativeABIError):
                circuit.add_inductor("Lbad", "x", "0", 0.0)
            circuit.add_inductor("L1", "x", "0", 1.0e-3, initial_current_a=0.0)
            with self.assertRaises(ValueError):
                circuit.solve_transient(time_step_s=math.nan, stop_time_s=1.0)
            with self.assertRaises(ValueError):
                circuit.solve_transient(time_step_s=1.0e-6, stop_time_s=1.0, max_steps=0)
            with self.assertRaises(ValueError):
                circuit.solve_transient(
                    time_step_s=1.0e-6, stop_time_s=1.0,
                    integration_method="gear42",
                )

    def test_persistent_native_session_controls_state_and_replays_exactly(self):
        self.assertTrue(self.library.transient_session_available)
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("Vdrive", "in", "0", 0.0)
            circuit.add_resistor("R1", "in", "out", 1000.0)
            circuit.add_capacitor("C1", "out", "0", 1.0e-6)
            with circuit.transient_session() as session:
                with self.assertRaises(NativeABIError):
                    session.node_voltage("out")
                session.set_source_value("Vdrive", 1.0)
                expected = 0.0
                for _ in range(10):
                    self.assertTrue(session.step(1.0e-4))
                    expected = (expected + 0.1) / 1.1
                self.assertAlmostEqual(session.node_voltage("out"), expected)
                self.assertTrue(self.library.session_element_voltage_available)
                self.assertAlmostEqual(session.element_voltage("R1"), 1.0 - expected)
                self.assertAlmostEqual(session.time_s, 1.0e-3)
                self.assertEqual(session.step_index, 10)
                with session.checkpoint() as checkpoint:
                    session.set_source_value("Vdrive", -0.5)
                    for _ in range(5):
                        self.assertTrue(session.step(1.0e-4))
                    first = session.node_voltage("out")
                    session.restore(checkpoint)
                    session.set_source_value("Vdrive", -0.5)
                    for _ in range(5):
                        self.assertTrue(session.step(1.0e-4))
                    self.assertEqual(session.node_voltage("out"), first)
                diagnostics = session.diagnostics()
                self.assertEqual(diagnostics["completed_steps"], 15)
                self.assertEqual(diagnostics["matrix_factorizations"], 1)
                self.assertEqual(diagnostics["factorization_reuses"], 14)
                self.assertEqual(diagnostics["factorization_cache_entries"], 1)

    def test_persistent_hybrid_retains_and_replays_companion_history(self):
        with self.library.circuit() as circuit:
            circuit.add_voltage_source("Vdrive", "in", "0", 1.0)
            circuit.add_resistor("R1", "in", "out", 1000.0)
            circuit.add_capacitor("C1", "out", "0", 1.0e-6)
            with circuit.transient_session(
                integration_method="hybrid_trapezoidal"
            ) as session:
                for _ in range(5):
                    self.assertTrue(session.step(1.0e-4))
                with session.checkpoint() as checkpoint:
                    for _ in range(5):
                        self.assertTrue(session.step(1.0e-4))
                    replay = session.node_voltage("out")
                    session.restore(checkpoint)
                    for _ in range(5):
                        self.assertTrue(session.step(1.0e-4))
                    self.assertEqual(session.node_voltage("out"), replay)
                diagnostics = session.diagnostics()
                self.assertEqual(diagnostics["backward_euler_steps"], 1)
                self.assertEqual(diagnostics["trapezoidal_steps"], 9)
                self.assertEqual(diagnostics["matrix_factorizations"], 2)
                self.assertEqual(diagnostics["factorization_reuses"], 8)

    def test_persistent_session_tracks_global_waveform_time_and_rejects_foreign_checkpoint(self):
        with self.library.circuit() as waveform:
            waveform.add_pulse_voltage_source(
                "V1", "out", "0", initial_value=0.0, pulsed_value=5.0,
                delay_s=0.1, rise_time_s=0.1, pulse_width_s=0.2,
                fall_time_s=0.1, period_s=0.5,
            )
            waveform.add_resistor("R1", "out", "0", 1.0)
            with waveform.transient_session(
                integration_method="hybrid_trapezoidal"
            ) as session:
                self.assertTrue(session.step(0.35))
                self.assertAlmostEqual(session.node_voltage("out"), 5.0)
                self.assertTrue(session.step(0.20))
                self.assertAlmostEqual(session.node_voltage("out"), 0.0)
                self.assertTrue(session.step(0.10))
                self.assertAlmostEqual(session.node_voltage("out"), 2.5)
                diagnostics = session.diagnostics()
                self.assertGreaterEqual(diagnostics["backward_euler_steps"], 5)
                self.assertGreaterEqual(diagnostics["trapezoidal_steps"], 3)
                with self.assertRaises(NativeABIError):
                    session.set_source_value("V1", 1.0)

        with self.library.circuit() as waveform:
            waveform.add_pwl_voltage_source(
                "Vshape", "out", "0", ((0.2, 0.0), (0.5, 3.0), (0.9, 1.0))
            )
            waveform.add_resistor("R2", "out", "0", 2.0)
            with waveform.transient_session() as session:
                self.assertTrue(session.step(0.5))
                self.assertAlmostEqual(session.node_voltage("out"), 3.0)
                with session.checkpoint() as checkpoint:
                    self.assertTrue(session.step(0.4))
                    self.assertAlmostEqual(session.node_voltage("out"), 1.0)
                    session.restore(checkpoint)
                    self.assertTrue(session.step(0.2))
                    self.assertAlmostEqual(session.node_voltage("out"), 2.0)

        with self.library.circuit() as first_circuit, self.library.circuit() as second_circuit:
            for circuit in (first_circuit, second_circuit):
                circuit.add_voltage_source("V1", "out", "0", 1.0)
                circuit.add_resistor("R1", "out", "0", 1.0)
            with first_circuit.transient_session() as first, second_circuit.transient_session() as second:
                with first.checkpoint() as checkpoint:
                    with self.assertRaises(NativeABIError):
                        second.restore(checkpoint)


class SpikesNativeABILoadTests(unittest.TestCase):
    def test_loading_is_explicit_and_rejects_non_libraries(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            load_native_library(ROOT / "missing-spikes-library.dll")
        with self.assertRaises(ValueError):
            load_native_library(Path(__file__))


if __name__ == "__main__":
    unittest.main()
