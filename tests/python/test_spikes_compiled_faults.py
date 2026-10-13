# SPDX-License-Identifier: Apache-2.0
"""Actual compiled-board fault equivalence, state, and rejection checks."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from examples.compiled_board_faults.build_and_run import load_fixture, native_value
from python.spikes.board_library import AnalogInput, BoardLimits, BoardOutput, ROOT, compile_board_library
from python.spikes.board_library_client import BoardLibrary
from python.spikes.netlist import parse_netlist


@unittest.skipUnless(os.environ.get("SPIKES_BOARD_ENGINE"),
                     "Set SPIKES_BOARD_ENGINE and use a C++ developer environment")
class CompiledFaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.here, cls.config, cls.project, cls.faults = load_fixture()
        root = ROOT / "build" / "compiled-board-fault-tests"
        root.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix="verification-", dir=root)
        if os.name == "nt":
            cls.temp._finalizer.detach()
        cls.work = Path(cls.temp.name)
        cls.engine = Path(os.environ["SPIKES_BOARD_ENGINE"]).resolve()
        cls.manifest = compile_board_library(cls.project, cls.work / "board", name=cls.config["name"],
            inputs=[AnalogInput(**p) for p in cls.config["inputs"]],
            outputs=[BoardOutput(**p) for p in cls.config["outputs"]],
            limits=BoardLimits(**cls.config["limits"]), engine_library=cls.engine, faults=cls.faults)
        cls.library = BoardLibrary(cls.manifest, engine_library=cls.engine)

    @classmethod
    def tearDownClass(cls):
        if os.name != "nt":
            cls.temp.cleanup()

    def test_manifest_and_generated_descriptors_are_exact(self):
        record = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(record["board_abi"], 1)
        self.assertEqual(record["features"], ["fault_injection_v1"])
        self.assertEqual(set(self.library.fault_sites), {
            "gate_source_shunt", "drain_source_shunt", "shifted_vto"})
        self.assertEqual(self.library.fault_sites["drain_source_shunt"].element_id, "FDS")
        with self.assertRaises(TypeError):
            self.library.fault_sites["other"] = self.library.fault_sites["shifted_vto"]

    def test_fault_package_reports_missing_symbols_before_board_load(self):
        class Function:
            restype = None
            def __call__(self):
                return 1
        class OldEngine:
            spikes_abi_version = Function()
        with patch("python.spikes.board_library_client.ctypes.CDLL", return_value=OldEngine()) as loader:
            with self.assertRaisesRegex(ValueError, "lacks required.*set_resistance.*set_mosfet_threshold"):
                BoardLibrary(self.manifest, engine_library=self.engine)
        self.assertEqual(loader.call_count, 1)

    def test_normal_and_faults_match_direct_native_internal_sessions(self):
        scenarios = ((None, None), ("gate_source_shunt", 0.01),
                     ("drain_source_shunt", 0.01), ("drain_source_shunt", 10.0),
                     ("shifted_vto", 6.0))
        with self.library.create() as board:
            values = {}
            for fault, value in scenarios:
                board.reset()
                if fault is not None:
                    board.inject_fault(fault, value)
                board.step(1e-6)
                compiled = board.read("drain_v")
                native = native_value(self.engine, self.project, self.faults, fault, value)
                self.assertAlmostEqual(compiled, native, delta=1e-10)
                values[(fault, value)] = compiled
        normal = values[(None, None)]
        self.assertGreater(values[("gate_source_shunt", 0.01)], 4.9)
        self.assertLess(values[("drain_source_shunt", 0.01)], 0.01)
        self.assertGreater(values[("drain_source_shunt", 10.0)], values[("drain_source_shunt", 0.01)])
        self.assertLess(values[("drain_source_shunt", 10.0)], normal)
        self.assertGreater(values[("shifted_vto", 6.0)], 4.9)

    def test_static_diode_matches_independent_shockley_oracle(self):
        project = parse_netlist("V1 a 0 0.5\nD1 a 0 DM\n.model DM D(IS=1e-12 N=1 TNOM=27)\n.op\n.end")
        limits = BoardLimits(min_step_s=1e-9, max_step_s=1e-6, stop_time_s=2e-6,
                             max_steps=2, absolute_tolerance=1e-12, relative_tolerance=1e-9)
        manifest = compile_board_library(project, self.work / "diode", name="diode_board",
            inputs=[], outputs=[BoardOutput("diode_a", "current", "D1")], limits=limits,
            engine_library=self.engine)
        with BoardLibrary(manifest, engine_library=self.engine).create() as board:
            board.step(1e-6)
            solved = board.read("diode_a")
        thermal_voltage = 8.617333262145e-5 * 300.15
        expected = 1e-12 * math.expm1(0.5 / thermal_voltage)
        self.assertAlmostEqual(solved, expected, delta=expected * 2e-12)

    def test_fault_checkpoint_reset_clear_and_object_isolation(self):
        with self.library.create() as board, self.library.create() as independent:
            board.step(1e-6); board.save()
            independent.step(1e-6)
            board.inject_fault("gate_source_shunt", 0.01); board.step(1e-6)
            self.assertGreater(board.read("drain_v"), 4.9)
            self.assertLess(independent.read("drain_v"), 4.9)
            board.restore(); board.step(1e-6)
            independent.step(1e-6)
            self.assertAlmostEqual(board.read("drain_v"), independent.read("drain_v"), delta=1e-10)
            board.inject_fault("shifted_vto", 6.0); board.clear_fault("shifted_vto"); board.step(1e-6)
            independent.step(1e-6)
            self.assertAlmostEqual(board.read("drain_v"), independent.read("drain_v"), delta=1e-10)
            board.inject_fault("gate_source_shunt", 0.01); board.inject_fault("shifted_vto", 6.0)
            board.clear_all(); board.step(1e-6); independent.step(1e-6)
            self.assertAlmostEqual(board.read("drain_v"), independent.read("drain_v"), delta=1e-10)
            board.reset()
            self.assertEqual(board.position(), (0.0, 0))
            with self.assertRaisesRegex(RuntimeError, "No checkpoint"):
                board.restore()

    def test_invalid_fault_requests_do_not_mutate(self):
        with self.library.create() as board, self.library.create() as reference:
            board.step(1e-6); reference.step(1e-6)
            before = board.position(), board.read("drain_v")
            for name, value in (("missing", 1), ("gate_source_shunt", float("nan")),
                                ("gate_source_shunt", 1e-9), ("shifted_vto", 11.0)):
                with self.assertRaises((ValueError, RuntimeError)):
                    board.inject_fault(name, value)
                self.assertEqual(board.position(), before[0])
                self.assertEqual(board.read("drain_v"), before[1])
            with self.assertRaises(ValueError):
                board.clear_fault("missing")
            board.step(1e-6); reference.step(1e-6)
            self.assertAlmostEqual(board.read("drain_v"), reference.read("drain_v"), delta=1e-10)


if __name__ == "__main__":
    unittest.main()
