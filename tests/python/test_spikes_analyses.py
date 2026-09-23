import contextlib
import json
import math
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from python.spikes.analyses import (
    AC_RESULT_CONTRACT,
    FOURIER_RESULT_CONTRACT,
    TRANSFER_RESULT_CONTRACT,
    AcExcitation,
    AcSweep,
    reduce_fourier_result,
    run_ac_analysis,
    run_transfer_function,
)
from python.spikes.cli import EXIT_INPUT, EXIT_OK, main
from python.spikes.contracts import ProbeDescriptor, RESULT_CONTRACT
from python.spikes.netlist import parse_netlist


RC_OP = """.title AC low pass circuit
V1 in 0 0
R1 in out 1k
C1 out 0 1u
.op
.end
"""


class SpikesAcAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.corner_hz = 1.0 / (2.0 * math.pi * 1000.0 * 1.0e-6)
        self.probe = ProbeDescriptor.parse("V(out)")
        self.project = parse_netlist(RC_OP, probes=(self.probe,))

    def test_rc_corner_returns_complex_probe_and_explicit_provenance(self):
        result = run_ac_analysis(
            self.project,
            AcSweep(self.corner_hz, self.corner_hz, 1),
            AcExcitation("V1"),
        )
        self.assertEqual(result["contract"], AC_RESULT_CONTRACT)
        self.assertEqual(result["status"], "completed")
        response = result["probes"]["V(out)"]["values"]
        self.assertAlmostEqual(response["magnitude"][0], 1.0 / math.sqrt(2.0), places=10)
        self.assertAlmostEqual(response["phase_deg"][0], -45.0, places=9)
        self.assertFalse(result["provenance"]["ac_engine"]["owned_cpp_ac"])
        self.assertFalse(result["provenance"]["ac_engine"]["nonlinear_bias_linearization"])

    def test_transfer_divides_amplitude_and_phase_of_selected_source(self):
        result = run_transfer_function(
            self.project,
            AcSweep(self.corner_hz, self.corner_hz, 1),
            AcExcitation("V1", magnitude=2.0, phase_deg=30.0),
            self.probe,
        )
        self.assertEqual(result["contract"], TRANSFER_RESULT_CONTRACT)
        self.assertAlmostEqual(result["data"]["transfer"]["magnitude"][0], 1.0 / math.sqrt(2.0), places=10)
        self.assertAlmostEqual(result["data"]["transfer"]["phase_deg"][0], -45.0, places=9)
        self.assertEqual(result["data"]["unit"], "V/V")

    def test_missing_source_and_invalid_sweep_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            run_ac_analysis(self.project, AcSweep(1.0, 10.0, 3), AcExcitation("V404"))
        with self.assertRaisesRegex(ValueError, "stop frequency"):
            AcSweep(10.0, 1.0, 3)
        with self.assertRaisesRegex(ValueError, "65536"):
            AcSweep(1.0, 10.0, 65_537)
        power = ProbeDescriptor.parse("P(C1)")
        power_project = parse_netlist(RC_OP, probes=(power,))
        with self.assertRaisesRegex(ValueError, "not linear"):
            run_transfer_function(
                power_project,
                AcSweep(1.0, 10.0, 3),
                AcExcitation("V1"),
                power,
            )


class SpikesFourierReductionTests(unittest.TestCase):
    @staticmethod
    def transient_result() -> dict:
        fundamental = 16.0
        intervals = 256
        times = [index / intervals for index in range(intervals + 1)]
        samples = [
            1.25
            + 3.0 * math.cos(2.0 * math.pi * fundamental * time)
            + 0.3 * math.cos(4.0 * math.pi * fundamental * time + math.radians(30.0))
            for time in times
        ]
        return {
            "contract": RESULT_CONTRACT,
            "status": "completed",
            "model_status": "experimental",
            "analysis": {"mode": "transient", "time_step_s": 1.0 / intervals, "stop_time_s": 1.0},
            "data": {"time_s": times},
            "probes": {"V(out)": {"values": samples}},
            "diagnostics": {},
            "issues": [],
            "provenance": {},
        }

    def test_exact_cycle_dft_reports_dc_harmonics_and_thd(self):
        result = reduce_fourier_result(self.transient_result(), "V(out)", 16.0, 4)
        self.assertEqual(result["contract"], FOURIER_RESULT_CONTRACT)
        self.assertAlmostEqual(result["data"]["dc"], 1.25, places=11)
        self.assertAlmostEqual(result["data"]["components"][0]["amplitude"], 3.0, places=11)
        self.assertAlmostEqual(result["data"]["components"][1]["amplitude"], 0.3, places=11)
        self.assertAlmostEqual(result["data"]["components"][1]["phase_deg"], 30.0, places=9)
        self.assertAlmostEqual(result["data"]["thd"], 0.1, places=11)

    def test_nonintegral_capture_and_nyquist_violation_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "integral"):
            reduce_fourier_result(self.transient_result(), "V(out)", 16.25, 2)
        with self.assertRaisesRegex(ValueError, "Nyquist"):
            reduce_fourier_result(self.transient_result(), "V(out)", 16.0, 9)


class SpikesAnalysisCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.netlist = self.root / "rc.cir"
        self.netlist.write_text(RC_OP, encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def invoke(*arguments: str):
        output = StringIO()
        with contextlib.redirect_stdout(output):
            code = main(arguments)
        return code, json.loads(output.getvalue())

    def test_ac_and_transfer_commands_execute_without_ac_deck_syntax(self):
        corner = str(1.0 / (2.0 * math.pi * 1000.0 * 1.0e-6))
        common = (
            str(self.netlist), "--source", "V1", "--start-hz", corner,
            "--stop-hz", corner, "--points", "1",
        )
        code, ac = self.invoke("ac", *common, "--probe", "V(out)")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(ac["contract"], AC_RESULT_CONTRACT)
        code, transfer = self.invoke("transfer", *common, "--output-probe", "V(out)")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(transfer["contract"], TRANSFER_RESULT_CONTRACT)

    def test_fourier_command_reduces_result_file_and_protects_input(self):
        source = self.root / "transient.json"
        source.write_text(json.dumps(SpikesFourierReductionTests.transient_result()), encoding="utf-8")
        code, result = self.invoke(
            "fourier", str(source), "--probe", "V(out)",
            "--fundamental-hz", "16", "--harmonics", "4",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(result["contract"], FOURIER_RESULT_CONTRACT)
        code, error = self.invoke(
            "fourier", str(source), "--probe", "V(out)",
            "--fundamental-hz", "16", "-o", str(source),
        )
        self.assertEqual(code, EXIT_INPUT)
        self.assertIn("must not overwrite", error["issues"][0]["message"])


if __name__ == "__main__":
    unittest.main()
