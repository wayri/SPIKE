# SPDX-License-Identifier: Apache-2.0

import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from python.spikes.contracts import AnalysisDirective, CircuitProject, ProbeDescriptor
from python.spikes.native_runner import _populate, run_native_project
from python.spikes.netlist import NetlistParseError, parse_netlist
from python.spikes.runner import native_request, run_project


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = Path(os.environ.get(
    "SPIKES_TEST_NATIVE_LIBRARY",
    ROOT / "build-spikes-faults-20261010" / "Release" / "spikes_c_api.dll",
))
NGSPICE = ROOT / "runtime" / "external" / "Spice64" / "bin" / "ngspice_con.exe"

RC_BODY = """* transient-control RC
V1 in 0 1
R1 in out 1k
C1 out 0 1u
{tran}
.end
"""


class TransientControlContractTests(unittest.TestCase):
    def test_full_form_and_old_contract_round_trip(self):
        project = parse_netlist(RC_BODY.format(tran=".tran 100u 1m 400u 20u UIC"))
        analysis = project.analysis
        self.assertAlmostEqual(analysis.time_step_s, 100.0e-6)
        self.assertAlmostEqual(analysis.stop_time_s, 1.0e-3)
        self.assertAlmostEqual(analysis.start_time_s, 400.0e-6)
        self.assertAlmostEqual(analysis.maximum_time_step_s, 20.0e-6)
        self.assertTrue(analysis.use_initial_conditions)
        self.assertEqual(
            CircuitProject.from_dict(json.loads(json.dumps(project.to_dict()))),
            project,
        )

        restored_old = AnalysisDirective.from_dict({
            "mode": "transient",
            "time_step_s": 100.0e-6,
            "stop_time_s": 1.0e-3,
            "use_initial_conditions": False,
        })
        self.assertEqual(restored_old.start_time_s, 0.0)
        self.assertIsNone(restored_old.maximum_time_step_s)

    def test_native_request_separates_output_and_integration_controls(self):
        project = parse_netlist(RC_BODY.format(tran=".tran 100u 1m 400u 30u"))
        analysis = native_request(project)["analysis"]
        self.assertAlmostEqual(analysis["output_time_step_s"], 100.0e-6)
        self.assertAlmostEqual(analysis["output_start_time_s"], 400.0e-6)
        self.assertAlmostEqual(analysis["maximum_time_step_s"], 30.0e-6)
        self.assertLessEqual(analysis["time_step_s"], 30.0e-6)
        self.assertEqual(analysis["integration_points"], 35)

    def test_invalid_ordered_or_unbounded_controls_fail_before_allocation(self):
        invalid = (
            ".tran 1u 10u 10u",
            ".tran 1u 10u 11u",
            ".tran 1u 10u -1u",
            ".tran 1u 10u 2u 0",
            ".tran 1u 10u 2u -1u",
            ".tran 1 1e300 0 1e-300",
            ".tran 1u 10u 2u UIC 1u",
        )
        for directive in invalid:
            with self.subTest(directive=directive), self.assertRaises(NetlistParseError):
                parse_netlist(RC_BODY.format(tran=directive))

    def test_rolling_capture_bypasses_history_cap_but_not_step_work_cap(self):
        long_run = RC_BODY.format(tran=".tran 1n 1")
        with self.assertRaises(NetlistParseError):
            parse_netlist(long_run)
        self.assertEqual(
            parse_netlist(long_run, transient_capture="rolling").analysis.stop_time_s,
            1.0,
        )
        stepped = long_run.replace(
            "R1 in out 1k",
            ".param load=1k\n.step param load list 1k 2k\nR1 in out {load}",
        )
        with self.assertRaisesRegex(NetlistParseError, "STEP expansion"):
            parse_netlist(stepped, transient_capture="rolling")


class TransientControlReferenceTests(unittest.TestCase):
    def _run(self, directive):
        return run_project(parse_netlist(
            RC_BODY.format(tran=directive),
            probes=(ProbeDescriptor.parse("V(out)"),),
        )).to_dict()

    def test_tstart_retains_evolved_state_instead_of_reinitializing(self):
        full = self._run(".tran 100u 1m 0 20u")
        window = self._run(".tran 100u 1m 400u 20u")
        self.assertEqual(window["data"]["time_s"], full["data"]["time_s"][4:])
        self.assertEqual(
            window["probes"]["V(out)"]["values"],
            full["probes"]["V(out)"]["values"][4:],
        )
        self.assertGreater(window["probes"]["V(out)"]["values"][0], 0.3)
        self.assertEqual(
            window["provenance"]["transient_controls"]["integration_origin_s"],
            0.0,
        )

    def test_tmax_is_an_integration_bound_and_tstop_is_always_returned(self):
        result = self._run(".tran 300u 1m 200u 70u")
        expected_times = [200.0e-6, 500.0e-6, 800.0e-6, 1.0e-3]
        self.assertEqual(len(result["data"]["time_s"]), len(expected_times))
        for actual, expected in zip(result["data"]["time_s"], expected_times, strict=True):
            self.assertAlmostEqual(actual, expected)
        self.assertLessEqual(result["diagnostics"]["effective_integration_step_s"], 70.0e-6)
        self.assertGreater(result["diagnostics"]["integration_points"], len(result["data"]["time_s"]))
        self.assertTrue(result["provenance"]["transient_controls"]["final_stop_included"])

    def test_two_argument_default_preserves_fixed_step_regression(self):
        result = self._run(".tran 100u 1m")
        self.assertEqual(len(result["data"]["time_s"]), 11)
        self.assertAlmostEqual(result["diagnostics"]["effective_integration_step_s"], 100.0e-6)
        self.assertAlmostEqual(result["probes"]["V(out)"]["values"][0], 1.0 / 11.0)

    def test_fine_tmax_resolves_a_delayed_analytic_source(self):
        deck = """* delayed source against an RC load
V1 in 0 EXP(0 1 250u 25u 10m 1m)
R1 in out 1k
C1 out 0 100n
.tran 1m 2m 0 50u
.end
"""
        project = parse_netlist(
            deck,
            probes=(ProbeDescriptor.parse("V(out)"),),
            native_extensions=True,
        )
        result = run_project(project).to_dict()
        self.assertGreater(result["probes"]["V(out)"]["values"][1], 0.95)
        self.assertLessEqual(result["diagnostics"]["effective_integration_step_s"], 50.0e-6)

        class CapturingCircuit:
            def __init__(self):
                self.points = ()

            def add_pwl_voltage_source(self, _name, _positive, _negative, points):
                self.points = tuple(points)

            def add_resistor(self, *_args):
                pass

            def add_capacitor(self, *_args, **_kwargs):
                pass

        circuit = CapturingCircuit()
        _populate(circuit, project)
        self.assertEqual(len(circuit.points), result["diagnostics"]["integration_points"])
        self.assertTrue(any(math.isclose(time_s, 250.0e-6) for time_s, _ in circuit.points))


@unittest.skipUnless(
    LIBRARY.is_file() and LIBRARY.stat().st_size > 0,
    "specified owned SPIKES C ABI library is unavailable",
)
class TransientControlOwnedNativeTests(unittest.TestCase):
    def test_default_nondivisible_grid_preserves_native_step_and_final_stop(self):
        result = run_native_project(
            parse_netlist(
                RC_BODY.format(tran=".tran 300u 1m"),
                probes=(ProbeDescriptor.parse("V(out)"),),
            ),
            LIBRARY,
            integration_method="backward_euler",
        ).to_dict()
        expected = [0.0, 300.0e-6, 600.0e-6, 900.0e-6, 1.0e-3]
        self.assertEqual(len(result["data"]["time_s"]), len(expected))
        for actual, reference in zip(result["data"]["time_s"], expected, strict=True):
            self.assertAlmostEqual(actual, reference)
        self.assertAlmostEqual(
            result["diagnostics"]["effective_integration_step_s"], 300.0e-6
        )

    def test_loaded_dll_integrates_from_zero_and_retains_requested_window(self):
        probes = (ProbeDescriptor.parse("V(out)"),)
        full = run_native_project(
            parse_netlist(RC_BODY.format(tran=".tran 100u 1m 0 20u"), probes=probes),
            LIBRARY,
            integration_method="backward_euler",
        ).to_dict()
        window = run_native_project(
            parse_netlist(RC_BODY.format(tran=".tran 100u 1m 400u 20u"), probes=probes),
            LIBRARY,
            integration_method="backward_euler",
        ).to_dict()
        self.assertEqual(window["status"], "completed")
        self.assertEqual(window["data"]["time_s"], full["data"]["time_s"][4:])
        self.assertEqual(
            window["probes"]["V(out)"]["values"],
            full["probes"]["V(out)"]["values"][4:],
        )
        self.assertLessEqual(window["diagnostics"]["effective_integration_step_s"], 20.0e-6)
        self.assertTrue(Path(window["provenance"]["library"]).samefile(LIBRARY))


@unittest.skipUnless(NGSPICE.is_file(), "bundled Windows ngspice executable is unavailable")
class TransientControlNgspiceReferenceTests(unittest.TestCase):
    def test_rc_start_window_and_maximum_step_against_installed_ngspice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "controls.csv"
            deck = root / "controls.cir"
            deck.write_text(
                f"""* ngspice transient-control reference
V1 in 0 PULSE(0 1 100u 1u 1u 10m 20m)
R1 in out 1k
C1 out 0 1u
.tran 100u 1m 400u 20u
.control
set wr_singlescale
set wr_vecnames
run
wrdata {output.as_posix()} time v(out)
quit
.endc
.end
""",
                encoding="ascii",
            )
            completed = subprocess.run(
                [str(NGSPICE), "-b", str(deck)],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30.0,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            rows = []
            for line in output.read_text(encoding="ascii").splitlines()[1:]:
                fields = line.split()
                if len(fields) >= 2:
                    rows.append((float(fields[0]), float(fields[-1])))
            self.assertTrue(rows)
            self.assertGreaterEqual(rows[0][0], 400.0e-6 - 1.0e-12)
            self.assertAlmostEqual(rows[-1][0], 1.0e-3, delta=1.0e-12)

            internal_deck = """* internal transient-control reference
V1 in 0 PULSE(0 1 100u 1u 1u 10m 20m)
R1 in out 1k
C1 out 0 1u
.tran 100u 1m 400u 20u
.end
"""
            internal = run_project(parse_netlist(
                internal_deck,
                probes=(ProbeDescriptor.parse("V(out)"),),
                native_extensions=True,
            )).to_dict()
            self.assertAlmostEqual(
                internal["probes"]["V(out)"]["values"][0],
                rows[0][1],
                delta=0.03,
            )


if __name__ == "__main__":
    unittest.main()
