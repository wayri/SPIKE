# SPDX-License-Identifier: Apache-2.0
"""Synthetic protocol controllers with actual owned C++ finite-pad circuits.

No Renode, MCU binary, hardware peripheral, or physical SI/PI qualification.
Independent closed-form oracles: docs/validation/BIDIRECTIONAL_GPIO_BUS_20261020.md.
"""
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import unittest

from python.spikes.native_abi import load_native_library
from python.spikes.native_io_pad import PadProfile, PadState, add_pad, receive, set_pad

ROOT = Path(__file__).resolve().parents[4]
DLL = os.environ.get("SPIKES_TEST_NATIVE_LIBRARY", os.environ.get(
    "SPIKES_TEST_LIBRARY", str(ROOT / "build-spikes-io-pad-20261019/Release/spikes_c_api.dll")))
VDD = 3.3
LOW = PadState("open_drain", "low")
RELEASE = PadState("open_drain", "released")
PROFILE = replace(PadProfile(), high_strong_resistance_ohm=30,
                  low_strong_resistance_ohm=30, off_resistance_ohm=1e15)


class FirmwareBusExamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = load_native_library(DLL)
        cls.metrics = {}

    @classmethod
    def tearDownClass(cls):
        print("SYNTHETIC_BUS_METRICS " + json.dumps(cls.metrics, sort_keys=True))

    def advance(self, session, duration, step=25e-9):
        count = max(1, math.ceil(duration / step))
        for _ in range(count):
            self.assertTrue(session.step(duration / count), session.message)

    def level(self, session, node, previous="unknown"):
        value = receive(session, session.node_voltage(node),
                        session.node_voltage("vdd"), 0., previous=previous)
        self.assertNotEqual(value, "unknown", (node, session.node_voltage(node)))
        return value == "high"

    def test_rc_release_threshold_and_grid_refinement(self):
        errors = []
        for step in (2e-9, 1e-9, .5e-9):
            with self.lib.circuit() as circuit:
                circuit.add_voltage_source("V", "vdd", "0", VDD)
                circuit.add_resistor("RP", "vdd", "bus", 2200)
                circuit.add_capacitor("CB", "bus", "0", 100e-12)
                add_pad(circuit, "sink", "bus", "vdd", "0", PROFILE, LOW)
                with circuit.transient_session(initialize_from_operating_point=True,
                                               integration_method="radau_iia3") as session:
                    self.advance(session, step, step)
                    start, initial = session.time_s, session.node_voltage("bus")
                    set_pad(session, "sink", RELEASE)
                    self.assertEqual(session.node_voltage("bus"), initial)
                    # Four finite off branches: two to each rail.
                    conductance = 1 / 2200 + 4 / PROFILE.off_resistance_ohm
                    equilibrium = VDD * (1 / 2200 + 2 / PROFILE.off_resistance_ohm) / conductance
                    tau = 100e-12 / conductance
                    exact = tau * math.log((equilibrium - initial) / (equilibrium - .7 * VDD))
                    previous = False
                    for _ in range(math.ceil(1e-6 / step)):
                        self.advance(session, step, step)
                        t = session.time_s - start
                        reference = equilibrium + (initial - equilibrium) * math.exp(-t / tau)
                        self.assertAlmostEqual(session.node_voltage("bus"), reference,
                                               delta=1e-5 + .001 * abs(reference))
                        current = self.level(session, "bus", "high" if previous else "low")
                        if current:
                            # Sampled receiver observation; this is not a root localizer.
                            errors.append(t - exact)
                            self.assertGreaterEqual(t - exact, -1e-12)
                            self.assertLessEqual(t - exact, step + 1e-12)
                            break
                        previous = current
                    else:
                        self.fail("RC receiver did not cross")
        self.assertLessEqual(errors[-1], 2e-9)
        self.assertLessEqual(errors[-1], errors[0] + 1e-12)
        self.metrics["rc_sample_delays_ns"] = [e * 1e9 for e in errors]

    def test_i2c_finite_pad_byte_ack_nack_and_clock_stretch(self):
        # An original, explicitly synthetic target; all bus decisions read MNA.
        for acknowledge in (True, False):
            with self.subTest(acknowledge=acknowledge), self.lib.circuit() as circuit:
                circuit.add_voltage_source("V", "vdd", "0", VDD)
                for wire in ("sda", "scl"):
                    circuit.add_resistor("RP_" + wire, "vdd", wire, 2200)
                    circuit.add_capacitor("CB_" + wire, wire, "0", 100e-12)
                    for participant in ("controller", "target"):
                        add_pad(circuit, participant + "_" + wire, wire, "vdd", "0", PROFILE, RELEASE)
                with circuit.transient_session(initialize_from_operating_point=True,
                                               integration_method="radau_iia3") as session:
                    self.advance(session, 1e-6)
                    self.assertTrue(self.level(session, "sda"))
                    self.assertTrue(self.level(session, "scl"))
                    set_pad(session, "controller_sda", LOW)  # START.
                    self.advance(session, 1e-6)
                    self.assertFalse(self.level(session, "sda"))
                    self.assertTrue(self.level(session, "scl"))
                    decoded = 0
                    for bit in (int(value) for value in f"{0xA5:08b}"):
                        set_pad(session, "controller_scl", LOW)
                        set_pad(session, "controller_sda", RELEASE if bit else LOW)
                        self.advance(session, 2.5e-6)
                        set_pad(session, "controller_scl", RELEASE)
                        # Poll actual clock rather than treating release as high.
                        for _ in range(100):
                            self.advance(session, 25e-9)
                            if self.level(session, "scl", "low"):
                                break
                        else:
                            self.fail("I2C data clock did not rise")
                        decoded = (decoded << 1) | self.level(session, "sda")
                        self.advance(session, 2.5e-6)
                    self.assertEqual(decoded, 0xA5)
                    set_pad(session, "controller_scl", LOW)
                    set_pad(session, "controller_sda", RELEASE)
                    set_pad(session, "target_sda", LOW if acknowledge else RELEASE)
                    set_pad(session, "target_scl", LOW)
                    self.advance(session, 2.5e-6)
                    set_pad(session, "controller_scl", RELEASE)
                    # Target still sinks: wired-AND, not last writer wins.
                    self.advance(session, 2e-6)
                    self.assertFalse(self.level(session, "scl"))
                    self.assertLess(session.node_voltage("scl"), .05)
                    initial = session.node_voltage("scl")
                    start = session.time_s
                    set_pad(session, "target_scl", RELEASE)
                    for _ in range(100):
                        self.advance(session, 1e-8, 1e-8)
                        if self.level(session, "scl", "low"):
                            break
                    else:
                        self.fail("Stretched clock did not recover")
                    elapsed = session.time_s - start
                    exact = 2200 * 100e-12 * math.log((VDD - initial) / (.3 * VDD))
                    self.assertGreaterEqual(elapsed, exact - 1e-12)
                    self.assertLessEqual(elapsed - exact, 10e-9 + 1e-12)
                    self.assertEqual(not self.level(session, "sda"), acknowledge)
                    set_pad(session, "controller_scl", LOW)
                    self.advance(session, 1e-6)
                    set_pad(session, "target_sda", RELEASE)
                    set_pad(session, "controller_sda", LOW)
                    set_pad(session, "controller_scl", RELEASE)
                    self.advance(session, 1e-6)
                    set_pad(session, "controller_sda", RELEASE)  # STOP.
                    self.advance(session, 1e-6)
                    self.assertTrue(self.level(session, "sda"))
                    self.assertTrue(self.level(session, "scl"))
                    self.metrics["i2c_stretch_release_delay_ns"] = elapsed * 1e9

    def test_spi_mode_zero_synthetic_electrical_loopback_and_loading_failure(self):
        def exchange(capacitance):
            with self.lib.circuit() as circuit:
                circuit.add_voltage_source("V", "vdd", "0", VDD)
                for wire, initial in (("sck", False), ("mosi", False), ("miso", False), ("cs", True)):
                    add_pad(circuit, wire, wire, "vdd", "0", PROFILE,
                            PadState("push_pull", "high" if initial else "low"))
                    circuit.add_capacitor("C_" + wire, wire, "0",
                                          capacitance if wire == "miso" else 20e-12)
                with circuit.transient_session(initialize_from_operating_point=True,
                                               integration_method="radau_iia3") as session:
                    self.advance(session, 1e-6)
                    set_pad(session, "cs", PadState("push_pull", "low"))
                    self.advance(session, 1e-6)
                    self.assertFalse(self.level(session, "cs"))
                    result = 0
                    previous_miso = "low"
                    for bit in (int(value) for value in f"{0xA5:08b}"):
                        set_pad(session, "sck", PadState("push_pull", "low"))
                        set_pad(session, "mosi", PadState("push_pull", "high" if bit else "low"))
                        self.advance(session, .5e-6)
                        # Synthetic loopback target samples actual MOSI while SCK low.
                        sampled = self.level(session, "mosi")
                        set_pad(session, "miso", PadState("push_pull", "high" if sampled else "low"))
                        self.advance(session, .5e-6)
                        set_pad(session, "sck", PadState("push_pull", "high"))
                        self.advance(session, 25e-9)
                        self.assertTrue(self.level(session, "sck"))
                        sampled_miso = self.level(session, "miso", previous_miso)
                        previous_miso = "high" if sampled_miso else "low"
                        result = (result << 1) | sampled_miso
                        self.advance(session, .975e-6)
                    set_pad(session, "cs", PadState("push_pull", "high"))
                    self.advance(session, 1e-6)
                    self.assertTrue(self.level(session, "cs"))
                    return result
        self.assertEqual(exchange(20e-12), 0xA5)
        overloaded = exchange(1e-6)
        self.assertNotEqual(overloaded, 0xA5)
        self.metrics["spi_overloaded_byte"] = overloaded

    def test_rlc_ringing_analytic_refinement_and_energy(self):
        errors = []
        for step in (.1e-9, .05e-9, .025e-9):
            with self.lib.circuit() as circuit:
                circuit.add_voltage_source("V", "vdd", "0", VDD)
                profile = replace(PROFILE, high_strong_resistance_ohm=20)
                add_pad(circuit, "driver", "drive", "vdd", "0", profile, PadState("push_pull", "high"))
                circuit.add_inductor("L", "drive", "out", 100e-9)
                circuit.add_capacitor("C", "out", "0", 100e-12)
                with circuit.transient_session(integration_method="radau_iia3") as session:
                    alpha = 20 / (2 * 100e-9)
                    wd = math.sqrt(1 / (100e-9 * 100e-12) - alpha ** 2)
                    peak = (0., 0.)
                    maximum_error = 0.
                    supplied = dissipated = 0.
                    last_supply = last_loss = 0.
                    for index in range(1, round(120e-9 / step) + 1):
                        self.advance(session, step, step)
                        t = index * step
                        reference_v = VDD * (1 - math.exp(-alpha*t) * (
                            math.cos(wd*t) + alpha/wd*math.sin(wd*t)))
                        reference_i = VDD/(100e-9*wd)*math.exp(-alpha*t)*math.sin(wd*t)
                        voltage, current = session.node_voltage("out"), session.element_current("L")
                        maximum_error = max(maximum_error, abs(voltage - reference_v))
                        self.assertAlmostEqual(voltage, reference_v, delta=1e-5 + .001*abs(reference_v))
                        self.assertAlmostEqual(current, reference_i, delta=1e-8 + .001*abs(reference_i))
                        if voltage > peak[1]:
                            peak = (t, voltage)
                        power = -VDD * session.element_current("V")
                        loss = 20 * session.element_current("driver.io_pad.drive_high") ** 2
                        supplied += step * (last_supply + power) / 2
                        dissipated += step * (last_loss + loss) / 2
                        last_supply, last_loss = power, loss
                    energy = .5*100e-12*voltage**2 + .5*100e-9*current**2
                    residual = abs(supplied - dissipated - energy)
                    self.assertLessEqual(residual, max(1e-12, .002*max(supplied, dissipated, energy)))
                    self.assertAlmostEqual(peak[0], math.pi/wd, delta=.1e-9)
                    self.assertGreater(peak[1], VDD*1.3)
                    errors.append(maximum_error)
        self.assertLess(errors[-1], errors[0]/8)
        self.metrics["rlc_max_voltage_errors_v"] = errors
        self.metrics["rlc_finest_energy_residual_j"] = residual

    def test_pdn_load_step_and_decoupling_analytic_refinement(self):
        errors = []
        for step in (20e-9, 10e-9, 5e-9):
            with self.lib.circuit() as circuit:
                circuit.add_voltage_source("V", "source", "0", VDD)
                circuit.add_resistor("RS", "source", "vdd", .5)
                circuit.add_capacitor("C", "vdd", "0", 1e-6)
                circuit.add_current_source("LOAD", "vdd", "0", 0.)
                with circuit.transient_session(initialize_from_operating_point=True,
                                               integration_method="radau_iia3") as session:
                    self.advance(session, step, step)
                    session.set_source_value("LOAD", .02)
                    maximum_error = 0.
                    for index in range(1, round(5e-6/step) + 1):
                        self.advance(session, step, step)
                        t = index*step
                        droop = .01*(1-math.exp(-t/(.5e-6)))
                        reference_v = VDD-droop
                        reference_i = .02*(1-math.exp(-t/(.5e-6)))
                        maximum_error = max(maximum_error, abs(session.node_voltage("vdd")-reference_v))
                        self.assertAlmostEqual(session.node_voltage("vdd"), reference_v, delta=1e-5)
                        self.assertAlmostEqual(session.element_current("RS"), reference_i,
                                               delta=1e-8 + .001*abs(reference_i))
                        self.assertAlmostEqual(session.element_current("C"), reference_i-.02,
                                               delta=1e-8 + .001*abs(reference_i-.02))
                    errors.append(maximum_error)
        self.assertLess(errors[-1], errors[0]/8)
        with self.lib.circuit() as circuit:
            circuit.add_voltage_source("V", "source", "0", VDD)
            circuit.add_resistor("RS", "source", "vdd", .5)
            circuit.add_current_source("LOAD", "vdd", "0", .02)
            with circuit.transient_session() as session:
                self.advance(session, 1e-9, 1e-9)
                self.assertAlmostEqual(session.node_voltage("vdd"), 3.29, delta=1e-10)
        self.metrics["pdn_max_voltage_errors_v"] = errors

    def test_contention_finite_current_and_dissipation(self):
        with self.lib.circuit() as circuit:
            circuit.add_voltage_source("V", "vdd", "0", VDD)
            add_pad(circuit, "high", "bus", "vdd", "0",
                    replace(PROFILE, high_strong_resistance_ohm=40), PadState("push_pull", "high"))
            add_pad(circuit, "low", "bus", "vdd", "0",
                    replace(PROFILE, low_strong_resistance_ohm=60), PadState("push_pull", "low"))
            with circuit.transient_session(initialize_from_operating_point=True) as session:
                self.advance(session, 1e-9, 1e-9)
                self.assertAlmostEqual(session.node_voltage("bus"), 1.98, delta=1e-9)
                self.assertAlmostEqual(-session.element_current("V"), .033, delta=1e-10)
                loss = sum(resistance*session.element_current(name)**2 for name, resistance in (
                    ("high.io_pad.drive_high", 40), ("low.io_pad.drive_low", 60)))
                self.assertAlmostEqual(loss, VDD*.033, delta=1e-10)
                self.assertEqual(receive(session, session.node_voltage("bus"), VDD, 0), "unknown")
                set_pad(session, "low", PadState())
                self.advance(session, 1e-9, 1e-9)
                self.assertGreater(session.node_voltage("bus"), 3.29999)
                self.assertLess(abs(session.element_current("V")), 1e-10)


if __name__ == "__main__":
    unittest.main()
