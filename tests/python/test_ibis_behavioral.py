# SPDX-License-Identifier: Apache-2.0
"""Original arithmetic IBIS oracles and fail-closed compiler contract checks."""
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from python.spike_core.solvers.signal_integrity.receivers.ibis_behavioral import compile_ibis_behavioral
from python.spike_core.solvers.signal_integrity.receivers.ibis_behavioral_tables import calibrate, endpoint, currents, replay
from python.spike_core.solvers.signal_integrity.receivers import ibis_behavioral_execution as execution

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/si/ibis_driver_receiver"


def request():
    return json.loads((EXAMPLE / "request.json").read_text())


class BehavioralCompilerTests(unittest.TestCase):
    def assertUnsupported(self, value):
        compiled = compile_ibis_behavioral(value)
        self.assertEqual(compiled["status"], "unsupported", compiled)
        self.assertTrue(compiled["diagnostics"])
        self.assertNotIn("netlist", compiled)
        self.assertNotIn("netlist_sha256", compiled)

    def test_original_source_is_retained_and_compilation_is_deterministic(self):
        value = request()
        self.assertEqual(value["driver"]["text"], (EXAMPLE / "original_cmos.ibs").read_text())
        with patch.object(execution, "supervise_process", side_effect=AssertionError("compile launched native code")):
            a, b = compile_ibis_behavioral(value), compile_ibis_behavioral(value)
        self.assertEqual(a, b)
        self.assertEqual(a["status"], "ready", a)
        self.assertEqual(a["netlist_sha256"], sha256(a["netlist"].encode("ascii")).hexdigest())
        self.assertEqual(a["endpoints"]["driver"]["source_sha256"], sha256(value["driver"]["text"].encode()).hexdigest())
        self.assertEqual(a["model_status"], "experimental")
        self.assertFalse(a["production_qualified"])
        self.assertFalse(a["calibration"]["external_fixture_replay_executed"])

    def test_two_fixture_kcl_recovers_independent_arithmetic_weights(self):
        selected = endpoint(request()["driver"], "driver")
        rising = calibrate(selected, [0, 1])
        falling = calibrate(selected, [2, 3])
        for calibration, expected in ((rising, [0, 0, .5, 1, 1]), (falling, [1, 1, .5, 0, 0])):
            for (_, ku, kd), oracle in zip(calibration["weights"], expected):
                self.assertAlmostEqual(ku, oracle, places=13)
                self.assertAlmostEqual(kd, 1 - oracle, places=13)
            self.assertLess(calibration["replay_current_residual_a_max"], 1e-15)
        self.assertEqual(currents(selected, .25)[:2], [-.015, .005])

    def test_nonzero_capacitance_current_enters_reconstruction(self):
        binding = request()["driver"]
        binding["text"] = binding["text"].replace("C_comp 0 0 0", "C_comp 1p 1p 1p")
        for old, new in (("1n ", "1u "), ("2n ", "2u "), ("3n ", "3u "), ("4n ", "4u ")):
            binding["text"] = binding["text"].replace(old, new)
        selected = endpoint(binding, "driver")
        reconstruction = calibrate(selected, [0, 1])
        # At the central knot: v=f/2, f'=.5/us. KCL adds R*C*f'/2 to kpu.
        self.assertAlmostEqual(reconstruction["weights"][2][1], .5 + 50 * 1e-12 * .5 * .5e6, places=12)
        self.assertAlmostEqual(reconstruction["weights"][2][2], .5 - 50 * 1e-12 * .5 * .5e6, places=12)

    def test_weights_are_not_clipped_or_forced_to_binary_endpoints(self):
        selected = endpoint(request()["driver"], "driver")
        for index, waveform in enumerate(selected["model"]["waveforms"]):
            fractions = [0, 0, .5, 1, 1] if index < 2 else [1, 1, .5, 0, 0]
            load_v = index % 2
            for row, fraction in zip(waveform["values"], fractions):
                ku = -.2 + 1.4 * fraction
                row[1:] = [(ku + load_v) / 2.2] * 3
        reconstructed = calibrate(selected, [0, 1])["weights"]
        self.assertAlmostEqual(reconstructed[0][1], -.2)
        self.assertAlmostEqual(reconstructed[0][2], 1.4)
        self.assertAlmostEqual(reconstructed[-1][1], 1.2)
        self.assertAlmostEqual(reconstructed[-1][2], 0)

    def test_direct_derivative_defect_rejects_opposite_small_kcl_residuals(self):
        selected = endpoint(request()["driver"], "driver")
        selected["capacitance"] = 1
        # Both +/-0.75uA individual replay residuals pass 1uA; their 1.5uA
        # derivative mismatch must still fail the separate defect screen.
        load = {"points": [(0, 0), (1, -.75e-6)], "derivative": [(0, .75e-6), (1, .75e-6)],
                "resistance": 1e12, "voltage": 0}
        with self.assertRaisesRegex(ValueError, "derivative-defect"):
            replay(selected, [load], [(0, 0, 0), (1, 0, 0)])

    def test_capacitance_and_package_corners_are_independent(self):
        value = request()
        value["receiver"]["capacitance_corner"] = "max"
        value["receiver"]["package_corner"] = "min"
        compiled = compile_ibis_behavioral(value)
        self.assertEqual(compiled["status"], "ready", compiled)
        retained = compiled["endpoints"]["receiver"]
        self.assertEqual(retained["capacitance_f"], 2e-12)
        self.assertEqual(retained["package_rlc"], [.05, .5e-9, .25e-12])
        self.assertEqual(retained["corner"], "typ")

    def test_explicit_references_change_axes_without_rectifying_signed_current(self):
        value = request()["driver"]
        value["text"] = value["text"].replace("[Pullup]", "[Pullup Reference] 1 1 1\n[Pulldown Reference] 0 0 0\n[Pullup]")
        selected = endpoint(value, "driver")
        self.assertEqual(currents(selected, .25)[:2], [-.015, .005])

    def test_original_scalar_pin_overrides_all_package_corners(self):
        value = request()
        value["driver"]["text"] = value["driver"]["text"].replace("1 TX OriginalDriver NA NA NA", "1 TX OriginalDriver 0.7 3n 4p")
        value["driver"]["package_corner"] = "max"
        compiled = compile_ibis_behavioral(value)
        self.assertEqual(compiled["status"], "ready", compiled)
        for actual, expected in zip(compiled["endpoints"]["driver"]["package_rlc"], [.7, 3e-9, 4e-12]):
            self.assertAlmostEqual(actual, expected, delta=max(abs(expected) * 1e-14, 1e-30))

    def test_request_limits_unknown_fields_and_nonfinite_values_fail_closed(self):
        for mutate in (
            lambda r: r.update(extra=True),
            lambda r: r["analysis"].update(time_step_s=float("nan")),
            lambda r: r["analysis"].update(stop_time_s=.002),
            lambda r: r["analysis"].update(time_step_s=1e-15),
            lambda r: r["driver"].update(corner="best"),
            lambda r: r["driver"].pop("package_corner"),
            lambda r: r["interconnect"].update(kind="coupled_line"),
            lambda r: r["stimulus"]["transitions"][0].update(waveform_indices=[True, 1]),
            lambda r: r["stimulus"]["transitions"][0].update(waveform_indices=[0, 0]),
            lambda r: r["stimulus"]["transitions"][0].update(waveform_indices=[2, 3]),
            lambda r: r["stimulus"]["transitions"][1].update(time_s=2e-9),
            lambda r: r["stimulus"]["transitions"][1].update(time_s=14e-9),
        ):
            value = request()
            mutate(value)
            with self.subTest(value=value["analysis"]):
                self.assertUnsupported(value)

    def test_unsupported_electrical_extensions_and_fixture_loads_fail_closed(self):
        for replacement in (
            ("[Voltage Range]", "[C Comp Model] ignored\n[Voltage Range]"),
            ("R_fixture 50", "R_fixture 50\nC_fixture 1p"),
            ("R_fixture 50", "R_fixture 50\nUnknown_fixture 1"),
            ("Model_type 3-state", "Model_type Output_ECL"),
            ("C_comp 0 0 0", "C_comp 0 NA 0"),
            ("[Pullup]", "[Driver Schedule] ignored\n[Pullup]"),
        ):
            value = request()
            value["driver"]["corner"] = "min"
            value["driver"]["capacitance_corner"] = "min"
            value["driver"]["text"] = value["driver"]["text"].replace(*replacement)
            with self.subTest(replacement=replacement):
                self.assertUnsupported(value)

    def test_singular_weak_and_time_misaligned_fixtures_fail_closed(self):
        for replacement in (
            ("V_fixture 1\nV_fixture_min 1\nV_fixture_max 1", "V_fixture 0\nV_fixture_min 0\nV_fixture_max 0"),
            ("0.04", "0.00000000004"),
            ("4n 1 1 1", "5n 1 1 1"),
            ("2n 0.25 0.25 0.25", "2n 4 4 4"),
        ):
            value = request()
            value["driver"]["text"] = value["driver"]["text"].replace(*replacement)
            self.assertUnsupported(value)

    def test_falling_endpoint_corruption_and_capacitance_replay_failure_rejected(self):
        value = request()
        value["driver"]["text"] = value["driver"]["text"].replace("C_comp 0 0 0", "C_comp 1u 1u 1u")
        self.assertUnsupported(value)
        value = request()
        prefix, falling = value["driver"]["text"].split("[Falling Waveform]", 1)
        value["driver"]["text"] = prefix + "[Falling Waveform]" + falling.replace("0.5 0.5 0.5", "0.4 0.4 0.4")
        self.assertUnsupported(value)

    def test_static_z_and_resistor_interconnect_are_explicit(self):
        value = request()
        value["stimulus"] = {"initial_state": "z", "transitions": []}
        value["interconnect"] = {"kind": "series_resistor", "resistance_ohm": 25}
        compiled = compile_ibis_behavioral(value)
        self.assertEqual(compiled["status"], "ready", compiled)
        self.assertIn("Rchannel channel_in receiver_pad 25", compiled["netlist"])
        value["stimulus"]["transitions"] = [{"time_s": 1e-9, "state": "high", "waveform_indices": [0, 1]}]
        self.assertUnsupported(value)

    def test_source_names_cannot_inject_netlist_directives(self):
        value = request()
        value["driver"]["name"] = "x\n.control\nshell malicious\n.endc"
        compiled = compile_ibis_behavioral(value)
        self.assertEqual(compiled["status"], "ready", compiled)
        self.assertNotIn("malicious", compiled["netlist"])
        self.assertNotIn(".control", compiled["netlist"])


class BehavioralExecutionBoundaryTests(unittest.TestCase):
    def test_strict_raw_probe_and_time_admission(self):
        names = ["time", *execution.PROBES]
        lines = ["Title: Original fixture", "Date: synthetic", "Plotname: Transient Analysis", "Flags: real",
                 "No. Variables: 6", "No. Points: 2", "Variables:"]
        lines.extend(f"\t{i}\t{name}\t{'time' if i == 0 else 'voltage'}" for i, name in enumerate(names))
        lines.append("Values:")
        lines.extend(["0 0", "0", "0", "0", "0", "0", "1 1.5e-8", "1", "1", "1", "1", "0"])
        text = "\n".join(lines) + "\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.raw"
            path.write_text(text, encoding="ascii")
            parsed = execution._read_raw(path, 15e-9)
            self.assertEqual(parsed["time_s"], [0, 15e-9])
            self.assertEqual(set(parsed["probes"]), set(execution.PROBES.values()))
            for corrupted in (text.replace("0 0\n", "0 1e-12\n"), text.replace("Flags: real", "Flags: complex"),
                              text.replace("1 1.5e-8", "1 0"), text + "0\n", text.replace("1 1.5e-8", "1 nan"),
                              text.replace("v(receiver_pad)", "v(unrequested)")):
                path.write_text(corrupted, encoding="ascii")
                with self.assertRaises(ValueError):
                    execution._read_raw(path, 15e-9)

    def test_execution_is_opt_in(self):
        with self.assertRaisesRegex(ValueError, "explicit"):
            execution.run_ibis_behavioral(request(), executable="unused", executable_sha256="0" * 64)

    def test_execution_digest_admission_cannot_be_omitted(self):
        for digest in (None, "", "0" * 63, "A" * 64, True):
            with self.subTest(digest=digest), patch.object(execution, "supervise_process") as supervised:
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    execution.run_ibis_behavioral(request(), executable="unused", executable_sha256=digest,
                                                   execution_requested=True)
                supervised.assert_not_called()

    def test_runtime_identity_inspection_does_not_launch(self):
        with patch.object(execution, "_identity", return_value=(Path("unused"), "a" * 64)), \
                patch.object(execution, "supervise_process", side_effect=AssertionError("inspection launched")):
            result = execution.inspect_ibis_behavioral_runtime("unused")
        self.assertEqual(result["status"], "available")
        self.assertFalse(result["executed"])

    def test_supervisor_initialization_failure_is_not_retried(self):
        with patch.object(execution, "_identity", return_value=(Path("unused"), "a" * 64)), \
                patch.object(execution, "supervise_process", side_effect=execution.SupervisorInitializationError("fixture", 30, 512)) as supervised:
            result = execution.run_ibis_behavioral(request(), executable="unused", executable_sha256="a" * 64,
                                                   execution_requested=True)
        self.assertEqual(supervised.call_count, 1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["diagnostics"][0]["code"], "IBIS_SUPERVISOR_INITIALIZATION_FAILED")

    def test_out_of_domain_solver_continuation_output_is_rejected(self):
        outcome = SimpleNamespace(os_enforcement="fixture", elapsed_seconds=0, returncode=0, status="completed")
        parsed = {"time_s": [0, 15e-9], "probes": {"driver_die_v": [0, 4], "receiver_die_v": [0, 0]}}
        with patch.object(execution, "_identity", return_value=(Path("unused"), "a" * 64)), \
                patch.object(execution, "supervise_process", return_value=outcome), patch.object(execution, "_read_raw", return_value=parsed):
            result = execution.run_ibis_behavioral(request(), executable="unused", executable_sha256="a" * 64,
                                                   execution_requested=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["time_s"], [])
        self.assertIn("source domain", result["diagnostics"][0]["message"])


if __name__ == "__main__":
    unittest.main()
