import contextlib
import json
import math
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from python.spikes.cli import EXIT_OK, main
from python.spikes.contracts import CircuitProject
from python.spikes.netlist import NetlistParseError, parse_netlist
from python.spikes.runner import run_project


class StepElaborationTests(unittest.TestCase):
    def test_nested_linear_steps_are_deterministic_and_round_trip(self):
        project = parse_netlist(""".param resistance=1k supply=1
.step param resistance 1k 2k 1k
.step param supply 1 3 1
V1 in 0 {supply}
R1 in out {resistance}
R2 out 0 1k
.measure op midpoint FIND V(out)
.op
""")
        self.assertEqual(len(project.step_variants), 6)
        self.assertEqual(
            [variant.parameters for variant in project.step_variants],
            [
                (("resistance", 1000.0), ("supply", 1.0)),
                (("resistance", 1000.0), ("supply", 2.0)),
                (("resistance", 1000.0), ("supply", 3.0)),
                (("resistance", 2000.0), ("supply", 1.0)),
                (("resistance", 2000.0), ("supply", 2.0)),
                (("resistance", 2000.0), ("supply", 3.0)),
            ],
        )
        restored = CircuitProject.from_dict(json.loads(json.dumps(project.to_dict())))
        self.assertEqual(restored, project)

        result = run_project(project).to_dict()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["diagnostics"]["ordering"], "leftmost_axis_outermost")
        self.assertEqual(len(result["data"]["points"]), 6)
        measured = result["measurements"]["midpoint"]["by_step"]
        self.assertAlmostEqual(measured[0]["result"]["value"], 0.5)
        self.assertAlmostEqual(measured[-1]["result"]["value"], 1.0)

    def test_step_limits_and_invalid_axes_fail_closed(self):
        invalid = (
            ".step param absent 1 2 1\nV1 a 0 1\nR1 a 0 1k\n.op\n",
            ".param p=1\n.step param p 1 2 0\nV1 a 0 1\nR1 a 0 1k\n.op\n",
            ".param p=1\n.step param p 1 2 -1\nV1 a 0 1\nR1 a 0 1k\n.op\n",
            ".param p=1\n.step list p 1 2\nV1 a 0 1\nR1 a 0 1k\n.op\n",
        )
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(NetlistParseError):
                parse_netlist(source)
        source = ".param p=1\n.step param p 1 3 1\nV1 a 0 1\nR1 a 0 1k\n.op\n"
        with mock.patch("python.spikes.netlist.MAX_STEP_VARIANTS", 2):
            with self.assertRaisesRegex(NetlistParseError, "exceeds 2"):
                parse_netlist(source)


class MeasurementTests(unittest.TestCase):
    def test_dc_reductions_window_and_find_interpolation(self):
        result = run_project(parse_netlist("""V1 in 0 0
R1 in out 1k
R2 out 0 1k
.measure dc vmax MAX V(out) FROM=1 TO=3
.measure dc vmin MIN V(out) FROM=1 TO=3
.measure dc vavg AVG V(out) FROM=1 TO=3
.measure dc vrms RMS V(out) FROM=1 TO=3
.measure dc vfind FIND V(out) AT=2.5
.dc V1 0 4 1
""")).to_dict()
        measures = result["measurements"]
        self.assertEqual(result["status"], "completed")
        self.assertEqual(measures["vmax"]["value"], 1.5)
        self.assertEqual(measures["vmin"]["value"], 0.5)
        self.assertEqual(measures["vavg"]["value"], 1.0)
        self.assertAlmostEqual(measures["vrms"]["value"], math.sqrt((0.25 + 1 + 2.25) / 3))
        self.assertEqual(measures["vfind"]["value"], 1.25)
        self.assertEqual(measures["vfind"]["interpolation"], "linear")

    def test_find_interpolates_a_descending_dc_axis(self):
        result = run_project(parse_netlist("""V1 in 0 4
R1 in out 1k
R2 out 0 1k
.measure dc vfind FIND V(out) AT=2.5
.dc V1 4 0 -1
""")).to_dict()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["measurements"]["vfind"]["value"], 1.25)

    def test_transient_measurement_and_empty_window_failure_are_explicit(self):
        result = run_project(parse_netlist("""V1 in 0 1
R1 in out 1k
C1 out 0 1u
.measure tran peak MAX V(out) FROM=200u TO=1m
.measure tran average AVG V(out) FROM=200u TO=1m
.measure tran point FIND V(out) AT=550u
.measure tran absent MIN V(out) FROM=2m TO=3m
.tran 100u 1m
""")).to_dict()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["measurements"]["peak"]["status"], "completed")
        self.assertEqual(result["measurements"]["average"]["sample_count"], 9)
        self.assertEqual(result["measurements"]["point"]["interpolation"], "linear")
        self.assertEqual(result["measurements"]["absent"]["status"], "failed")
        self.assertEqual(
            result["measurements"]["absent"]["issue"]["code"],
            "SPIKES_MEASURE_FAILED",
        )

    def test_measurement_contract_rejects_mismatch_and_invalid_options(self):
        invalid = (
            "V1 a 0 1\nR1 a 0 1k\n.measure tran x MAX V(a)\n.op\n",
            "V1 a 0 1\nR1 a 0 1k\n.measure op x FIND V(a) AT=1\n.op\n",
            "V1 a 0 1\nR1 a 0 1k\n.measure op x MEDIAN V(a)\n.op\n",
            "V1 a 0 1\nR1 a 0 1k\n.measure op x MAX V(missing)\n.op\n",
            "V1 a 0 1\nR1 a 0 1k\n.measure dc x MAX V(a) FROM=1\n.dc V1 0 1 1\n",
        )
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(NetlistParseError):
                parse_netlist(source)

    def test_measurement_count_is_bounded(self):
        source = "V1 a 0 1\nR1 a 0 1k\n.measure op x MAX V(a)\n.op\n"
        with mock.patch("python.spikes.netlist.MAX_MEASUREMENTS", 0):
            with self.assertRaisesRegex(NetlistParseError, "More than 0"):
                parse_netlist(source)

    def test_cli_run_emits_step_and_measure_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stepped.cir"
            path.write_text(
                ".param r=1k\n.step param r 1k 2k 1k\n"
                "V1 in 0 2\nR1 in out {r}\nR2 out 0 1k\n"
                ".measure op output FIND V(out)\n.op\n",
                encoding="utf-8",
            )
            output = StringIO()
            with contextlib.redirect_stdout(output):
                code = main(("run", str(path)))
            payload = json.loads(output.getvalue())
            self.assertEqual(code, EXIT_OK)
            self.assertEqual(payload["diagnostics"]["step_variants"], 2)
            self.assertEqual(len(payload["measurements"]["output"]["by_step"]), 2)


if __name__ == "__main__":
    unittest.main()
