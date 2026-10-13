# SPDX-License-Identifier: Apache-2.0
"""Adaptive-transient coverage for the owned native project runner."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from io import StringIO
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from python.spikes.cli import EXIT_INPUT, EXIT_OK, main
from python.spikes.netlist import parse_netlist
from python.spikes.native_runner import run_native_project


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIBRARY = ROOT / "build-peec-native" / "spikes_c_api.dll"
LIBRARY = Path(os.environ.get(
    "SPIKES_TEST_NATIVE_LIBRARY",
    os.environ.get(
        "SPIKES_NATIVE_LIBRARY",
        DEFAULT_LIBRARY,
    ),
))


class _FakeTransientResult:
    status = "converged"
    message = ""
    _times = (0.0, 0.04, 0.11, 0.2)
    _values = (0.0, 0.0, 1.0, 1.0)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    @property
    def point_count(self):
        return len(self._times)

    def diagnostics(self):
        return {"rejected_lte_steps": 2}

    def time(self, index):
        return self._times[index]

    def node_voltage(self, index, name):
        return 0.0 if name == "0" else self._values[index]

    def element_current(self, index, _name):
        return self._values[index]

    def element_power(self, index, _name):
        return self._values[index]


class _FakeCircuit:
    def __init__(self):
        self.transient_options = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def __getattr__(self, name):
        if name.startswith("add_"):
            return lambda *_args, **_kwargs: None
        raise AttributeError(name)

    def solve_transient(self, **options):
        self.transient_options = options
        return _FakeTransientResult()


class _FakeLibrary:
    def __init__(self):
        self.path = Path("fake-spikes.dll")
        self.native_circuit = _FakeCircuit()

    def circuit(self):
        return self.native_circuit


class AdaptiveRunnerForwardingTests(unittest.TestCase):
    def test_forwards_adaptive_controls_and_retains_requested_output_grid(self):
        project = parse_netlist(
            "V1 out 0 PWL(0 0 .11 1 .2 1)\n"
            "R1 out 0 1k\n"
            ".measure tran average AVG V(out) FROM=0 TO=.2\n"
            ".tran .1 .2\n",
            native_extensions=True,
        )
        library = _FakeLibrary()
        with patch("python.spikes.native_runner.load_native_library", return_value=library):
            result = run_native_project(
                project,
                library.path,
                integration_method="bdf2",
                maximum_steps=1234,
                adaptive_time_step=True,
                lte_absolute_tolerance=2.0e-7,
                lte_relative_tolerance=3.0e-4,
                minimum_time_step_s=4.0e-9,
                max_rejected_steps=55,
            )

        self.assertEqual(library.native_circuit.transient_options, {
            "time_step_s": 0.1,
            "stop_time_s": 0.2,
            "initialize_from_operating_point": True,
            "integration_method": "bdf2",
            "max_steps": 1234,
            "adaptive_time_step": True,
            "lte_absolute_tolerance": 2.0e-7,
            "lte_relative_tolerance": 3.0e-4,
            "minimum_time_step_s": 4.0e-9,
            "max_rejected_steps": 55,
        })
        self.assertEqual(result.data["time_s"], [0.0, 0.1, 0.2])
        self.assertEqual(result.diagnostics["points"], 3)
        self.assertEqual(result.diagnostics["integration_points"], 4)
        self.assertEqual(
            result.provenance["transient_controls"]["output_sampling"],
            "linear_from_adaptive_integration_grid",
        )
        self.assertEqual(
            result.provenance["transient_controls"]["minimum_time_step_s"],
            4.0e-9,
        )
        self.assertEqual(
            result.provenance["transient_controls"]["max_rejected_steps"], 55
        )
        # The time-weighted measurement is reduced from the four accepted
        # integration samples, not the three interpolated reporting samples.
        self.assertAlmostEqual(result.measurements["average"]["value"], 0.625)

    def test_preserves_native_adaptive_defaults(self):
        project = parse_netlist("V1 out 0 1\nR1 out 0 1k\n.tran .1 .2\n")
        library = _FakeLibrary()
        with patch("python.spikes.native_runner.load_native_library", return_value=library):
            run_native_project(project, library.path)
        options = library.native_circuit.transient_options
        self.assertFalse(options["adaptive_time_step"])
        self.assertEqual(options["lte_absolute_tolerance"], 1.0e-6)
        self.assertEqual(options["lte_relative_tolerance"], 1.0e-3)
        self.assertEqual(options["minimum_time_step_s"], 1.0e-15)
        self.assertEqual(options["max_rejected_steps"], 10_000)

    def test_rejects_malformed_or_inapplicable_adaptive_controls_before_loading(self):
        transient = parse_netlist("V1 out 0 1\nR1 out 0 1k\n.tran .1 .2\n")
        operating_point = parse_netlist("V1 out 0 1\nR1 out 0 1k\n.op\n")
        cases = (
            (transient, {"adaptive_time_step": "yes"}, "must be boolean"),
            (transient, {"adaptive_time_step": True, "lte_absolute_tolerance": math.nan}, "positive finite"),
            (transient, {"adaptive_time_step": True, "lte_relative_tolerance": 0.0}, "positive finite"),
            (transient, {"adaptive_time_step": True, "minimum_time_step_s": 1.0}, "effective integration step"),
            (transient, {"adaptive_time_step": True, "max_rejected_steps": 0}, "positive integer"),
            (transient, {"lte_absolute_tolerance": 2.0e-6}, "require adaptive_time_step=True"),
            (transient, {"adaptive_time_step": True, "integration_method": "backward_euler"}, "requires hybrid_trapezoidal or bdf2"),
            (operating_point, {"adaptive_time_step": True}, "require a transient analysis"),
        )
        for project, options, message in cases:
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, message):
                run_native_project(project, "missing-spikes.dll", **options)


@dataclass
class _CompletedResult:
    payload: dict

    def to_dict(self):
        return self.payload


class AdaptiveNativeCliTests(unittest.TestCase):
    def _run(self, source, *arguments):
        with tempfile.TemporaryDirectory() as temporary:
            netlist = Path(temporary) / "fixture.cir"
            netlist.write_text(source, encoding="utf-8")
            output = StringIO()
            with contextlib.redirect_stdout(output):
                code = main((
                    "native-run", str(netlist), "--library", "missing-spikes.dll",
                    *arguments,
                ))
        return code, json.loads(output.getvalue())

    def test_cli_forwards_all_adaptive_controls(self):
        completed = _CompletedResult({"status": "completed"})
        with patch(
            "python.spikes.native_runner.run_native_project", return_value=completed
        ) as run:
            code, payload = self._run(
                "V1 out 0 1\nR1 out 0 1k\n.tran .1 .2\n",
                "--method", "bdf2", "--adaptive",
                "--lte-absolute-tolerance", "2e-7",
                "--lte-relative-tolerance", "3e-4",
                "--minimum-time-step", "4e-9",
                "--max-rejected-steps", "55",
            )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(run.call_args.kwargs, {
            "integration_method": "bdf2",
            "adaptive_time_step": True,
            "lte_absolute_tolerance": 2.0e-7,
            "lte_relative_tolerance": 3.0e-4,
            "minimum_time_step_s": 4.0e-9,
            "max_rejected_steps": 55,
        })

    def test_cli_rejects_inapplicable_adaptive_choices(self):
        cases = (
            ("V1 out 0 1\nR1 out 0 1k\n.op\n", ("--adaptive",), "transient analysis"),
            ("V1 out 0 1\nR1 out 0 1k\n.tran .1 .2\n", ("--method", "be", "--adaptive"), "requires hybrid_trapezoidal or bdf2"),
            ("V1 out 0 1\nR1 out 0 1k\n.tran .1 .2\n", ("--lte-absolute-tolerance", "2e-6"), "require adaptive_time_step=True"),
            ("V1 out 0 1\nR1 out 0 1k\n.tran .1 .2\n", ("--adaptive", "--lte-relative-tolerance", "nan"), "positive finite"),
        )
        for source, arguments, message in cases:
            with self.subTest(arguments=arguments):
                code, payload = self._run(source, *arguments)
                self.assertEqual(code, EXIT_INPUT)
                self.assertIn(message, payload["issues"][0]["message"])


@unittest.skipUnless(LIBRARY.is_file(), "built SPIKES C ABI library is unavailable")
class AdaptiveRunnerNativeAccuracyTests(unittest.TestCase):
    def test_nonfinite_lte_failure_diagnostic_is_json_safe(self):
        from python.spikes.native_abi import load_native_library
        library = load_native_library(LIBRARY)
        with library.circuit() as circuit:
            circuit.add_voltage_source("V1", "out", "0", 1.0)
            circuit.add_resistor("R1", "out", "0", 1000.0)
            with circuit.solve_transient(time_step_s=1e-4, stop_time_s=2e-4) as result:
                query = library._library.spikes_transient_result_lte_diagnostics
                def infinite_estimate(*arguments):
                    code = query(*arguments)
                    arguments[2]._obj.value = math.inf
                    return code
                with patch.object(library._library, "spikes_transient_result_lte_diagnostics", infinite_estimate):
                    diagnostics = result.diagnostics()
                self.assertIsNone(diagnostics["last_lte_ratio"])
                self.assertFalse(diagnostics["last_lte_estimate_finite"])
                json.dumps(diagnostics, allow_nan=False)

    def test_adaptive_native_run_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as temporary:
            netlist = Path(temporary) / "rc.cir"
            netlist.write_text(
                "V1 in 0 1\nR1 in out 1k\nC1 out 0 1u\n.tran 200u 1m UIC\n",
                encoding="utf-8",
            )
            output = StringIO()
            with contextlib.redirect_stdout(output):
                code = main((
                    "native-run", str(netlist), "--library", str(LIBRARY),
                    "--method", "bdf2", "--adaptive",
                    "--minimum-time-step", "1e-9",
                    "--lte-absolute-tolerance", "1e-6",
                    "--lte-relative-tolerance", "1e-3",
                    "--max-rejected-steps", "1000",
                ))
        payload = json.loads(output.getvalue())
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["status"], "completed")
        controls = payload["provenance"]["transient_controls"]
        self.assertTrue(controls["adaptive_time_step"])
        self.assertEqual(controls["max_rejected_steps"], 1000)
        self.assertEqual(controls["output_sampling"], "linear_from_adaptive_integration_grid")

    def test_adaptive_bdf2_rc_accuracy_uses_fixed_reporting_grid(self):
        project = parse_netlist(
            "V1 in 0 1\nR1 in out 1k\nC1 out 0 1u\n.tran 200u 1m UIC\n"
        )
        result = run_native_project(
            project,
            LIBRARY,
            integration_method="bdf2",
            adaptive_time_step=True,
            minimum_time_step_s=1.0e-9,
            lte_absolute_tolerance=1.0e-6,
            lte_relative_tolerance=1.0e-3,
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.data["time_s"]), 6)
        for observed, expected in zip(
            result.data["time_s"],
            [0.0, 0.0002, 0.0004, 0.0006, 0.0008, 0.001],
            strict=True,
        ):
            self.assertAlmostEqual(observed, expected, delta=1.0e-15)
        self.assertGreater(result.diagnostics["integration_points"], 6)
        self.assertLess(
            abs(result.data["node_voltage_v"]["out"][-1] - (1.0 - math.exp(-1.0))),
            0.01,
        )

    def test_adaptive_switching_preserves_requested_samples_and_levels(self):
        project = parse_netlist(
            "Vs in 0 10\n"
            "Vg gate 0 PULSE(0 5 100u 10u 10u 100u 300u)\n"
            "S1 in out gate 0 1 1meg 2.5 100m\n"
            "Rload out 0 9\n"
            ".tran 50u 300u UIC\n",
            native_extensions=True,
        )
        result = run_native_project(
            project,
            LIBRARY,
            adaptive_time_step=True,
            minimum_time_step_s=1.0e-9,
            lte_absolute_tolerance=1.0e-6,
            lte_relative_tolerance=1.0e-3,
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.data["time_s"]), 7)
        for observed, expected in zip(
            result.data["time_s"],
            [0.0, 50e-6, 100e-6, 150e-6, 200e-6, 250e-6, 300e-6],
            strict=True,
        ):
            self.assertAlmostEqual(observed, expected, delta=1.0e-15)
        output = result.data["node_voltage_v"]["out"]
        expected_off_v = 10.0 * 9.0 / (1.0e6 + 9.0)
        self.assertAlmostEqual(output[1], expected_off_v, delta=2.0e-7)
        self.assertAlmostEqual(output[3], 9.0, delta=0.05)
        self.assertAlmostEqual(output[-1], expected_off_v, delta=2.0e-7)


if __name__ == "__main__":
    unittest.main()
