# SPDX-License-Identifier: Apache-2.0
"""Original analytic RC and lifecycle oracles for generated native board objects."""
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from python.spikes.board_library import (
    ROOT, AnalogInput, BoardOutput, BoardLimits, FaultBinding, _definition, compile_board_library,
)
from python.spikes.fault_injection import FaultSite
from python.spikes.board_library_client import BoardLibrary
from python.spikes.netlist import parse_netlist

FIXTURE = ROOT / "examples" / "compiled_board"


def fixture():
    config = json.loads((FIXTURE / "pins.json").read_text())
    project = parse_netlist((FIXTURE / "rc_board.cir").read_text())
    return project, [AnalogInput(**p) for p in config["inputs"]], [BoardOutput(**p) for p in config["outputs"]], BoardLimits(**config["limits"])


class BoardDefinitionTests(unittest.TestCase):
    def test_deterministic_finite_resistance_driver(self):
        project, inputs, outputs, limits = fixture()
        source = _definition(project, inputs, outputs, limits)
        self.assertEqual(source, _definition(project, inputs, outputs, limits))
        self.assertIn('spikes_circuit_add_resistor(c,"SPIKES_BOARD_R0","SPIKES_BOARD_N0","dac",1000.0)', source)

    def test_invalid_pins_limits_and_unmodeled_features_rejected(self):
        project, inputs, outputs, limits = fixture()
        for value in (float("nan"), float("inf"), 0, -1, True):
            with self.assertRaises(ValueError):
                AnalogInput("dac", "dac", value, 0, 3.3)
        for value in (float("nan"), 0, -1, True):
            with self.assertRaises(ValueError):
                BoardLimits(max_step_s=value)
        for bad_inputs, bad_outputs in (
            ([replace(inputs[0], node="missing")], outputs),
            ([replace(inputs[0], node="0")], outputs),
            (inputs, [BoardOutput("bad", "current", "MISSING")]),
            (inputs, [BoardOutput("dac", "voltage", "adc")]),
        ):
            with self.assertRaises(ValueError):
                _definition(project, bad_inputs, bad_outputs, limits)
        pulse = parse_netlist("V1 a 0 PULSE(0 1 0 1u 1u 1m 2m)\nR1 a 0 1k\n.tran 1u 2m\n.end", native_extensions=True)
        with self.assertRaisesRegex(ValueError, "constant"):
            _definition(pulse, [], [BoardOutput("v", "voltage", "a")], limits)
        diode = parse_netlist("V1 a 0 1\nD1 a 0 DTEST\n.model DTEST D(IS=1e-12)\n.op\n.end")
        self.assertIn("spikes_circuit_add_diode", _definition(
            diode, [], [BoardOutput("v", "voltage", "a")], limits))
        with self.assertRaisesRegex(ValueError, "temperature"):
            _definition(replace(project, temperature_c=40), inputs, outputs, limits)

    def test_bad_name_cannot_inject_compiler_source(self):
        with self.assertRaises(ValueError):
            AnalogInput('x";system("bad")', "dac", 1000, 0, 3.3)

    def test_explicit_shunt_and_nmos_fault_bindings_are_generated(self):
        project = parse_netlist("V1 d 0 5\nV2 g 0 3\nM1 d g 0 0 MOD W=10u L=1u\n"
                                ".model MOD NMOS(LEVEL=1 VTO=1 KP=1m)\n.op\n.end")
        sites = [
            FaultBinding(FaultSite("ds_short", "FDS", "resistance_ohm", 1e12, 1e-3, 1e12,
                                   "externally driven finite drain-source shunt"), "d", "0"),
            FaultBinding(FaultSite("shifted_vto", "M1", "threshold_voltage_v", 1.0, -10.0, 10.0,
                                   "externally driven NMOS Level-1 threshold shift")),
        ]
        source = _definition(project, [], [BoardOutput("drain", "voltage", "d")], BoardLimits(), sites)
        self.assertIn("spikes_circuit_add_mosfet_level1", source)
        self.assertIn('spikes_circuit_add_resistor(c,"FDS","d","0",1000000000000.0)', source)
        self.assertIn('"shifted_vto","M1",FaultParameter::Threshold', source)

    def test_fault_bindings_reject_unknown_kind_invalid_topology_and_nonfinite(self):
        project, inputs, outputs, limits = fixture()
        with self.assertRaisesRegex(ValueError, "unsupported fault parameter"):
            FaultSite("bad", "R1", "capacitance_f", 1, 0, 2, "unsupported")
        with self.assertRaisesRegex(ValueError, "finite"):
            FaultSite("bad", "R1", "resistance_ohm", float("nan"), 1e-6, 1e15, "bad")
        missing = FaultBinding(FaultSite("short", "FS", "resistance_ohm", 1e12, 1e-3, 1e12,
                                         "explicit shunt"), "adc", "missing")
        with self.assertRaisesRegex(ValueError, "distinct existing shunt nodes"):
            _definition(project, inputs, outputs, limits, [missing])
        wrong = FaultBinding(FaultSite("vto", "R1", "threshold_voltage_v", 1, -1, 2,
                                       "threshold shift"))
        with self.assertRaisesRegex(ValueError, "NMOS"):
            _definition(project, inputs, outputs, limits, [wrong])


@unittest.skipUnless(os.environ.get("SPIKES_BOARD_ENGINE"), "Set SPIKES_BOARD_ENGINE and use a C++ developer environment")
class CompiledBoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = ROOT / "build" / "compiled-board-tests"
        root.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix="verification-", dir=root)
        if os.name == "nt":
            cls.temp._finalizer.detach()
        cls.work = Path(cls.temp.name)
        cls.engine = Path(os.environ["SPIKES_BOARD_ENGINE"]).resolve()
        cls.project, cls.inputs, cls.outputs, cls.limits = fixture()
        cls.manifest = compile_board_library(cls.project, cls.work / "board", name="rc_board",
            inputs=cls.inputs, outputs=cls.outputs, limits=cls.limits, engine_library=cls.engine)
        cls.library = BoardLibrary(cls.manifest, engine_library=cls.engine)

    @classmethod
    def tearDownClass(cls):
        # Windows keeps loaded DLL files mapped until this Python process exits.
        if os.name != "nt":
            cls.temp.cleanup()
        else:
            cls.temp._finalizer.detach()

    def test_rc_oracle_drop_current_and_independent_instances(self):
        with self.library.create() as board, self.library.create() as idle:
            board.drive("dac", 3.3)
            for n in range(1, 1001):
                board.step(1e-5)
                if n in (1, 10, 100, 1000):
                    expected = 1.65 * (1 - (1 + 1e-5 / 0.001)**(-n))
                    self.assertAlmostEqual(board.read("adc"), expected, delta=2e-9)
            self.assertAlmostEqual(board.read("adc"), 1.65, delta=1e-4)
            self.assertAlmostEqual(board.read("pin_voltage"), (3.3 + board.read("adc"))/2, delta=2e-9)
            self.assertAlmostEqual(board.read("load_current"), board.read("adc")/2000, delta=1e-12)
            self.assertAlmostEqual(board.read("drive_current"), (3.3-board.read("adc"))/2000, delta=1e-12)
            self.assertLess(board.residual(), 1e-8)
            self.assertEqual(idle.position(), (0, 0))
            idle.step(1e-5)
            self.assertEqual(idle.read("adc"), 0)

    def test_checkpoint_restores_time_source_and_history_reset_clears_checkpoint(self):
        with self.library.create() as board:
            board.drive("dac", 3.3)
            for _ in range(31): board.step(1e-5)
            board.save()
            before = board.position()
            for _ in range(17): board.step(1e-5)
            expected = board.read("adc")
            board.drive("dac", 0)
            board.step(1e-5)
            board.restore()
            self.assertEqual(board.position(), before)
            for _ in range(17): board.step(1e-5)
            self.assertAlmostEqual(board.read("adc"), expected, delta=1e-12)
            board.reset()
            self.assertEqual(board.position(), (0, 0))
            with self.assertRaisesRegex(RuntimeError, "No checkpoint"):
                board.restore()
            board.step(1e-5)
            self.assertEqual(board.read("adc"), 0)

    def test_time_step_refinement_against_continuous_solution(self):
        errors = []
        exact = 1.65 * (1 - math.exp(-1))
        for dt, count in ((1e-5, 100), (5e-6, 200)):
            with self.library.create() as board:
                board.drive("dac", 3.3)
                for _ in range(count): board.step(dt)
                errors.append(abs(board.read("adc")-exact))
        self.assertLess(errors[0], 0.0031)
        self.assertLess(errors[1], errors[0]*0.51)

    def test_horizon_and_step_count_are_enforced(self):
        for name, limits in (("step_bound", replace(self.limits, max_steps=2)),
                             ("time_bound", replace(self.limits, stop_time_s=2e-5))):
            manifest = compile_board_library(self.project, self.work / name, name=name,
                inputs=self.inputs, outputs=self.outputs, limits=limits, engine_library=self.engine)
            library = BoardLibrary(manifest, engine_library=self.engine)
            with library.create() as board:
                board.drive("dac", 3.3)
                board.step(1e-5)
                board.step(1e-5)
                before = board.position(), board.read("adc")
                with self.assertRaisesRegex(RuntimeError, "bounds"):
                    board.step(1e-5)
                self.assertEqual((board.position(), board.read("adc")), before)

    def test_rejected_input_and_step_do_not_mutate_state(self):
        with self.library.create() as board:
            board.drive("dac", 1.2)
            board.step(1e-5)
            before = board.position(), board.read("adc")
            for value in (float("nan"), float("inf"), -0.1, 3.4):
                with self.assertRaises(RuntimeError): board.drive("dac", value)
            for value in (float("nan"), float("inf"), 0, -1, 1e-20, 1.1e-5):
                with self.assertRaises(RuntimeError): board.step(value)
            with self.assertRaises(RuntimeError): board.drive("unknown", 1)
            with self.assertRaises(RuntimeError): board.read("unknown")
            self.assertEqual((board.position(), board.read("adc")), before)
            board.step(1e-5)
            self.assertAlmostEqual(board.read("adc"), 0.6*(1-(1.01)**-2), delta=1e-12)
        with self.assertRaisesRegex(RuntimeError, "closed"): board.step(1e-5)

    def test_manifest_tampering_rejected_before_load(self):
        altered = self.work / "tampered"
        shutil.copytree(self.manifest.parent, altered)
        (altered / "board_definition.inc").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            BoardLibrary(altered / "manifest.json", engine_library=self.engine)
        record = json.loads(self.manifest.read_text())
        record["files_sha256"]["../outside"] = "0"*64
        bad = self.manifest.parent / "bad_manifest.json"
        bad.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "direct children"):
            BoardLibrary(bad, engine_library=self.engine)
        with self.assertRaisesRegex(ValueError, "Engine does not match"):
            BoardLibrary(self.manifest, engine_library=self.manifest)

    def test_singular_step_rolls_back_and_reports_failure(self):
        project = parse_netlist("R1 a b 1k\nR2 c 0 1k\n.op\n.end")
        manifest = compile_board_library(project, self.work / "singular", name="singular",
            inputs=[], outputs=[BoardOutput("floating", "voltage", "a")],
            limits=self.limits, engine_library=self.engine)
        library = BoardLibrary(manifest, engine_library=self.engine)
        with library.create() as board:
            before = board.position()
            with self.assertRaises(RuntimeError): board.step(1e-5)
            self.assertEqual(board.position(), before)
            board.reset()
            self.assertEqual(board.position(), before)

    def test_build_output_is_not_overwritten(self):
        with self.assertRaises(FileExistsError):
            compile_board_library(self.project, self.manifest.parent, name="rc_board",
                inputs=self.inputs, outputs=self.outputs, limits=self.limits, engine_library=self.engine)

    def test_actual_cpp_firmware_consumer(self):
        package = self.manifest.parent
        exe = self.work / ("firmware.exe" if os.name == "nt" else "firmware")
        if os.name == "nt":
            command = [shutil.which("cl.exe"), "/nologo", "/std:c++20", "/EHsc", "/MD", f"/I{package}",
                       str(FIXTURE / "firmware.cpp"), str(package / "rc_board.lib"), f"/Fe:{exe}"]
        else:
            command = [shutil.which("c++"), "-std=c++20", f"-I{package}", str(FIXTURE / "firmware.cpp"),
                       str(package / "rc_board.so"), f"-Wl,-rpath,{package}", "-o", str(exe)]
        subprocess.run(command, cwd=self.work, check=True, capture_output=True, timeout=120)
        env = dict(os.environ)
        env["PATH"] = str(package)+os.pathsep+str(self.engine.parent)+os.pathsep+env.get("PATH", "")
        result = subprocess.run([str(exe)], cwd=self.work, env=env, check=True, capture_output=True, text=True, timeout=30)
        values = dict(item.split("=") for item in result.stdout.split())
        self.assertAlmostEqual(float(values["adc_voltage_v"]), 1.65, delta=0.001)
        self.assertAlmostEqual(float(values["pin_voltage_v"]), 2.475, delta=0.001)
        self.assertIn(int(values["adc12"]), (2047, 2048))
        self.assertAlmostEqual(float(values["threshold_time_s"]), -0.001*math.log(1-1/1.65), delta=2e-5)
        self.assertEqual(float(values["independent_time_s"]), 0)


if __name__ == "__main__":
    unittest.main()
