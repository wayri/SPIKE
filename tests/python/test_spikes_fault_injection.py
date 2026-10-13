# SPDX-License-Identifier: Apache-2.0
"""Independent equations exercised against the explicitly selected real DLL."""
import math
import os
from pathlib import Path
import unittest

from python.spikes.fault_injection import FaultSite, apply_fault, reset_fault
from python.spikes.native_abi import NativeABIError, load_native_library

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = Path(os.environ.get("SPIKES_TEST_NATIVE_LIBRARY", ROOT / "build-spikes-current-vs18-20260906/Release/spikes_c_api.dll"))


class FaultSiteTests(unittest.TestCase):
    def test_descriptor_rejects_invalid_contract(self):
        for values in (("resistance_ohm", 0, 0, 100), ("other", 1, 1, 10),
                       ("threshold_voltage_v", 1, -101, 100)):
            with self.assertRaises(ValueError):
                FaultSite("fault", "R1", *values, "parameter approximation")


@unittest.skipUnless(LIBRARY.is_file(), "real SPIKES DLL unavailable")
class NativeFaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = load_native_library(LIBRARY)
        if not cls.library.session_fault_parameters_available:
            raise AssertionError("selected DLL does not contain fault setters; rebuild it")

    def rc(self):
        circuit = self.library.circuit()
        self.addCleanup(circuit.close)
        circuit.add_voltage_source("V1", "in", "0", 1)
        circuit.add_resistor("R1", "in", "out", 1000)
        circuit.add_capacitor("C1", "out", "0", 1e-6)
        return circuit

    def test_piecewise_rc_and_checkpoint_restores_parameter_source_and_state(self):
        with self.rc().transient_session() as session:
            baseline = session.checkpoint()
            self.addCleanup(baseline.close)
            dt = 1e-6
            for _ in range(100):
                self.assertTrue(session.step(dt), session.message)
            before = session.node_voltage("out")
            self.assertAlmostEqual(before, 1 - math.exp(-0.1), delta=5e-5)
            session.set_resistance("R1", 2000)
            self.assertEqual(session.node_voltage("out"), before)
            fault = session.checkpoint()
            self.addCleanup(fault.close)
            for _ in range(100):
                self.assertTrue(session.step(dt), session.message)
            expected = 1 - (1 - before) * math.exp(-0.05)
            self.assertAlmostEqual(session.node_voltage("out"), expected, delta=2e-5)
            replay = session.node_voltage("out")
            session.set_source_value("V1", -3)
            session.set_resistance("R1", 100)
            session.restore(fault)
            for _ in range(100):
                self.assertTrue(session.step(dt))
            self.assertEqual(session.node_voltage("out"), replay)
            session.restore(baseline)
            self.assertEqual(session.position, (0, 0))
            self.assertTrue(session.step(dt))
            self.assertAlmostEqual(session.node_voltage("out"), 1 / 1001, places=13)

    def test_discontinuity_restarts_high_order_methods_and_preserves_voltage(self):
        for method in ("hybrid_trapezoidal", "bdf2"):
            with self.subTest(method=method), self.rc().transient_session(integration_method=method) as s:
                for _ in range(4):
                    self.assertTrue(s.step(1e-4))
                prior = s.node_voltage("out")
                s.set_resistance("R1", 2000)
                self.assertEqual(prior, s.node_voltage("out"))
                self.assertTrue(s.step(1e-4))
                self.assertAlmostEqual(s.node_voltage("out"), (prior + 0.05) / 1.05, places=12)

    def test_invalid_parameters_and_unsupported_devices_do_not_mutate(self):
        with self.rc().transient_session() as s:
            self.assertTrue(s.step(1e-4))
            prior = s.node_voltage("out")
            for value in (-1, 0, 1e-7, 1e16, math.nan, math.inf):
                # Exercise the C ABI too, bypassing Python finite validation.
                code = self.library._library.spikes_transient_session_set_resistance(s._handle, b"R1", value)
                self.assertNotEqual(code, 0)
            for name in ("C1", "V1", "missing"):
                with self.assertRaises(NativeABIError):
                    s.set_resistance(name, 2000)
            with self.assertRaises(NativeABIError):
                s.set_mosfet_threshold("R1", 2)
            self.assertEqual(s.position, (1e-4, 1))
            self.assertEqual(s.node_voltage("out"), prior)
            self.assertTrue(s.step(1e-4))
            self.assertAlmostEqual(s.node_voltage("out"), (prior + 0.1) / 1.1, places=12)

    def test_nmos_threshold_current_equation_and_checkpoint(self):
        with self.library.circuit() as c:
            c.add_voltage_source("Vd", "d", "0", 5)
            c.add_voltage_source("Vg", "g", "0", 3)
            c.add_mosfet_level1("M1", "d", "g", "0", "0", transconductance_a_per_v2=0.001)
            with c.transient_session() as s:
                self.assertTrue(s.step(1e-5), s.message)
                healthy = s.checkpoint()
                self.addCleanup(healthy.close)
                old = s.element_current("M1")
                site = FaultSite("oxide_shift", "M1", "threshold_voltage_v", 1, -10, 10, "threshold-shift approximation")
                apply_fault(s, site, 2)
                self.assertEqual(s.element_current("M1"), old)
                self.assertTrue(s.step(1e-5), s.message)
                shifted = s.element_current("M1")
                self.assertLess(shifted, old)
                self.assertAlmostEqual(old, 0.5 * 0.001 * 2**2 + 5e-12, places=10)
                self.assertAlmostEqual(shifted, 0.5 * 0.001 + 5e-12, places=10)
                for value in (-101, 101, math.nan, math.inf):
                    code = self.library._library.spikes_transient_session_set_mosfet_threshold(s._handle, b"M1", value)
                    self.assertNotEqual(code, 0)
                self.assertTrue(s.step(1e-5))
                self.assertAlmostEqual(s.element_current("M1"), shifted, places=13)
                reset_fault(s, site)
                self.assertTrue(s.step(1e-5))
                self.assertAlmostEqual(s.element_current("M1"), old, places=13)
                s.restore(healthy)
                self.assertTrue(s.step(1e-5))
                self.assertAlmostEqual(s.element_current("M1"), old, places=13)

    def test_failed_step_preserves_accepted_state_and_pending_fault(self):
        with self.rc().transient_session() as s:
            self.assertTrue(s.step(1e-4))
            s.set_resistance("R1", 1e-6)
            prior, position = s.node_voltage("out"), s.position
            s.set_source_value("V1", 1e308)
            self.assertFalse(s.step(1e-4))
            self.assertEqual(s.node_voltage("out"), prior)
            self.assertEqual(s.position, position)
            s.set_source_value("V1", 1)
            self.assertTrue(s.step(1e-4), s.message)
            self.assertAlmostEqual(s.node_voltage("out"), (prior + 1e8) / (1 + 1e8), places=12)

    def test_finite_gate_and_drain_bridges_are_explicit_resistor_sites(self):
        with self.library.circuit() as c:
            c.add_voltage_source("Vd", "rail", "0", 5)
            c.add_resistor("Rd", "rail", "d", 100)
            c.add_voltage_source("Vg", "drive", "0", 3)
            c.add_resistor("Rg", "drive", "g", 1000)
            c.add_resistor("GS", "g", "0", 1e12)
            c.add_resistor("DS", "d", "0", 1e12)
            c.add_mosfet_level1("M1", "d", "g", "0", "0")
            with c.transient_session() as s:
                self.assertTrue(s.step(1e-5))
                healthy_current = s.element_current("M1")
                gs = FaultSite("gate_short", "GS", "resistance_ohm", 1e12, 1, 1e12, "finite gate-source bridge")
                apply_fault(s, gs, 10)
                self.assertTrue(s.step(1e-5))
                self.assertAlmostEqual(s.node_voltage("g"), 3 * 10 / 1010, places=10)
                self.assertLess(s.element_current("M1"), healthy_current / 100)
                ds = FaultSite("body_diode_short", "DS", "resistance_ohm", 1e12, 1, 1e12, "finite drain-source bridge approximating body-diode short")
                apply_fault(s, ds, 10)
                self.assertTrue(s.step(1e-5))
                self.assertAlmostEqual(s.node_voltage("d"), 5 * 10 / 110, places=8)

    def test_dynamic_diode_hidden_charge_survives_resistance_change(self):
        # At fixed zero junction voltage, Ijunction=0 and Cj contributes zero.
        # dq/dt=-q/tau; BE gives q[n]=q0/(1+h/tau)**n, Id=-q/tau.
        with self.library.circuit() as c:
            c.add_voltage_source("V1", "d", "0", 0)
            c.add_resistor("R1", "d", "0", 1000)
            c.add_dynamic_diode("D1", "d", "0", transit_time_s=1e-6,
                                junction_capacitance_f=0, initial_stored_charge_c=1e-9)
            with c.transient_session() as s:
                for index in range(1, 7):
                    if index == 4:
                        prior = s.element_current("D1")
                        s.set_resistance("R1", 2000)
                        self.assertEqual(s.element_current("D1"), prior)
                    self.assertTrue(s.step(1e-7), s.message)
                    self.assertAlmostEqual(s.element_current("D1"), -0.001 / 1.1**index, places=12)

    def test_inductor_current_continues_across_resistance_change(self):
        with self.library.circuit() as c:
            c.add_voltage_source("V1", "in", "0", 1)
            c.add_resistor("R1", "in", "out", 10)
            c.add_inductor("L1", "out", "0", 1e-3)
            with c.transient_session() as s:
                self.assertTrue(s.step(1e-5))
                previous = s.element_current("L1")
                s.set_resistance("R1", 20)
                self.assertEqual(s.element_current("L1"), previous)
                self.assertTrue(s.step(1e-5))
                self.assertAlmostEqual(s.element_current("L1"), (previous + 0.01) / 1.2, places=12)


if __name__ == "__main__":
    unittest.main()
