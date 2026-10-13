# SPDX-License-Identifier: Apache-2.0
"""Original topology, admission and analytical native integration checks."""

import math
import os
from pathlib import Path
import unittest

from python.spikes.lumped_physics_parts import build, catalog
from python.spikes.native_abi import load_native_library
from python.spikes.native_runner import _populate
from python.spikes.netlist import parse_netlist


LIBRARY = os.environ.get("SPIKES_TEST_LIBRARY", os.environ.get("SPIKES_NATIVE_LIBRARY", ""))


def project(kind, wiring, parameters=None):
    part = build(kind, parameters)
    return parse_netlist(part["source"] + wiring + "\n.op\n", native_extensions=True)


class LumpedPhysicsPartsTests(unittest.TestCase):
    def test_catalog_is_independent_and_all_parts_parse(self):
        descriptors = catalog()
        self.assertEqual(len(descriptors), 5)
        for item in descriptors:
            part = build(item["id"])
            nodes = " ".join(f"n{i}" for i in range(len(part["pins"])))
            parsed = project(item["id"], f"X1 {nodes} SPK_LUMPED\nVREF n0 0 0")
            self.assertTrue(parsed.elements)
            self.assertEqual(part["model_status"], "generic_unqualified")
            self.assertEqual(part["backend"], "native")
            self.assertNotIn(".control", part["source"])
        descriptors[0]["defaults"]["threshold_voltage_v"] = 99
        descriptors[0]["limitations"].clear()
        self.assertEqual(catalog()[0]["defaults"]["threshold_voltage_v"], 1.)
        self.assertTrue(catalog()[0]["limitations"])

    def test_exact_exposed_topology(self):
        nmos = project("nmos4", "X1 d g s bulk SPK_LUMPED\nVREF bulk 0 0")
        core = next(e for e in nmos.elements if e.kind == "nmos_level1")
        self.assertEqual(core.semiconductor_nodes, ("d", "g", "s", "x1:bulk"))
        diodes = [e for e in nmos.elements if e.kind == "diode"]
        self.assertEqual([(e.positive_node, e.negative_node) for e in diodes], [("x1:bulk", "d"), ("x1:bulk", "s")])
        npn = project("npn4", "X1 c b e sub SPK_LUMPED\nVREF sub 0 0")
        core = next(e for e in npn.elements if e.kind == "npn_ebers_moll")
        self.assertEqual(core.semiconductor_nodes, ("c", "b", "e"))
        diode = next(e for e in npn.elements if e.kind == "diode")
        self.assertEqual((diode.positive_node, diode.negative_node), ("x1:substrate", "c"))

    def test_zero_optional_capacitances_are_omitted(self):
        part = build("nmos4", {"cgb_f": 0, "cbd_f": 0, "cbs_f": 0})
        self.assertNotIn("\nC", part["source"])
        self.assertIn("VLINK MID OUT 0", build("feedthrough_capacitor3", {"series_inductance_h": 0})["source"])

    def test_input_rejection(self):
        for bad in (True, "1e-3", None, float("inf"), float("nan"), -1, 1e20):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build("resistor3", {"resistance_ohm": bad})
        for kind in (None, [], "pmos4", "pnp4"):
            with self.assertRaises(ValueError):
                build(kind)
        for name in ("x\nV1 a 0 1", "has space", "0bad", "x" * 65):
            with self.assertRaises(ValueError):
                build("nmos4", name=name)
        with self.assertRaises(ValueError):
            build("npn4", {"process": 1})
        with self.assertRaises(ValueError):
            build("nmos4", [])

    def test_instance_scoped_models_do_not_collide(self):
        a = build("nmos4", {"threshold_voltage_v": 1}, name="A")
        b = build("nmos4", {"threshold_voltage_v": 2}, name="B")
        parsed = parse_netlist(a["source"] + b["source"] + "X1 d g 0 0 A\nX2 d g 0 0 B\n.op\n", native_extensions=True)
        thresholds = [dict(e.semiconductor_parameters)["threshold_voltage_v"]
                      for e in parsed.elements if e.kind == "nmos_level1"]
        self.assertEqual(thresholds, [1, 2])


@unittest.skipUnless(LIBRARY and Path(LIBRARY).is_file(), "Set SPIKES_TEST_LIBRARY to the current native library")
class NativeLumpedPhysicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = load_native_library(LIBRARY)

    def circuit(self, kind, wiring, parameters=None):
        circuit = self.library.circuit()
        self.addCleanup(circuit.close)
        _populate(circuit, project(kind, wiring, parameters))
        return circuit

    def test_body_junction_current_and_terminal_kcl(self):
        c = self.circuit("nmos4", "X1 d g s b SPK_LUMPED\nVD d 0 0\nVG g 0 0\nVS s 0 0\nVB b 0 .5")
        with c.solve_operating_point() as r:
            self.assertEqual(r.status, "converged")
            diode = 1e-14 * math.expm1(.5 / (8.617333262145e-5 * 300.15))
            self.assertAlmostEqual(-r.element_current("VB"), 2 * diode, delta=1e-11)
            self.assertAlmostEqual(r.element_current("VD"), diode, delta=1e-11)
            self.assertAlmostEqual(sum(r.element_current(v) for v in ("VD", "VG", "VS", "VB")), 0, delta=1e-12)

    def test_npn_substrate_junction_current(self):
        c = self.circuit("npn4", "X1 c b e sub SPK_LUMPED\nVC c 0 0\nVB b 0 0\nVE e 0 0\nVS sub 0 .5")
        with c.solve_operating_point() as r:
            self.assertEqual(r.status, "converged")
            diode = 1e-14 * math.expm1(.5 / (8.617333262145e-5 * 300.15))
            self.assertAlmostEqual(-r.element_current("VS"), diode, delta=1e-11)
            self.assertAlmostEqual(r.element_current("VC"), diode, delta=1e-11)
            self.assertAlmostEqual(sum(r.element_current(v) for v in ("VC", "VB", "VE", "VS")), 0, delta=1e-12)

    def test_body_threshold_retained(self):
        currents = []
        for bulk in (0., -1.):
            c = self.circuit("nmos4", f"X1 d g 0 bulk SPK_LUMPED\nVD d 0 4\nVG g 0 3\nVB bulk 0 {bulk}")
            with c.solve_operating_point() as r:
                self.assertEqual(r.status, "converged")
                threshold = 1 + .4 * (math.sqrt(.6 - bulk) - math.sqrt(.6))
                expected = .0005 * (3 - threshold) ** 2 * 1.04 + 4e-12
                currents.append(-r.element_current("VD"))
                self.assertAlmostEqual(currents[-1], expected, delta=1e-10)
        self.assertLess(currents[1], currents[0])

    def test_resistor_substrate_dc_oracle(self):
        c = self.circuit("resistor3", "X1 p 0 sub SPK_LUMPED\nVP p 0 1\nVS sub 0 0", {"substrate_leakage_resistance_ohm": 1000})
        with c.solve_operating_point() as r:
            self.assertEqual(r.status, "converged")
            self.assertAlmostEqual(-r.element_current("VP"), .0012, delta=1e-12)
            self.assertAlmostEqual(r.element_current("VS"), .0004, delta=1e-12)

    def test_feedthrough_dc_and_kelvin_sense_oracles(self):
        c = self.circuit("feedthrough_capacitor3", "X1 p out 0 SPK_LUMPED\nV1 p 0 1\nRLOAD out 0 1")
        with c.solve_operating_point() as r:
            self.assertEqual(r.status, "converged")
            self.assertAlmostEqual(r.node_voltage("out"), 1 / 1.01, delta=1e-10)
        c = self.circuit("kelvin_shunt4", "X1 p 0 sp sn SPK_LUMPED\nV1 p 0 1")
        with c.solve_operating_point() as r:
            self.assertEqual(r.status, "converged")
            self.assertAlmostEqual(r.node_voltage("sp") - r.node_voltage("sn"), .01 / .012, delta=1e-10)

    def test_feedthrough_backward_euler_charge_recurrence(self):
        c = self.circuit("feedthrough_capacitor3", "X1 p out 0 SPK_LUMPED\nV1 p 0 PULSE(0 1 0 1u 1u 2u 5u)",
                         {"series_resistance_ohm": 1000, "series_inductance_h": 0, "capacitance_f": 1e-9})
        with c.solve_transient(time_step_s=1e-7, stop_time_s=1e-6) as r:
            self.assertEqual(r.status, "converged")
            previous, previous_time = 0., 0.
            for index in range(1, r.point_count):
                t = r.time(index)
                ratio = 1e-6 / (t - previous_time)
                expected = (t / 1e-6 + ratio * previous) / (1 + ratio)
                self.assertAlmostEqual(r.node_voltage(index, "out"), expected, delta=1e-9)
                previous, previous_time = expected, t

    def test_core_and_bulk_charge_be_bdf2_and_hybrid_rejection(self):
        c = self.circuit("nmos4", "X1 d g 0 0 SPK_LUMPED\nVD d 0 0\nVG g 0 PULSE(0 1 0 1u 1u 2u 5u)",
                         {"cgs_f": 1e-9, "cgd_f": 0, "cgb_f": 2e-9})
        for method in ("backward_euler", "bdf2"):
            with c.solve_transient(time_step_s=1e-7, stop_time_s=1e-6, integration_method=method) as r:
                self.assertEqual(r.status, "converged")
                for index in range(1, r.point_count):
                    self.assertAlmostEqual(r.element_current(index, "VG"), -.003, delta=1e-10)
        with c.solve_transient(time_step_s=1e-7, stop_time_s=1e-6, integration_method="hybrid_trapezoidal") as r:
            self.assertNotEqual(r.status, "converged")
            self.assertIn("requires backward Euler or BDF2", r.message)


if __name__ == "__main__":
    unittest.main()
