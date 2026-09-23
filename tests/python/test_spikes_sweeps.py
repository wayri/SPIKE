import contextlib
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from python.spikes.cli import EXIT_OK, main
from python.spikes.contracts import ProbeDescriptor
from python.spikes.netlist import parse_netlist
from python.spikes.sweeps import (
    CORNER_SWEEP_CONTRACT,
    MONTE_CARLO_CONTRACT,
    TEMPERATURE_SWEEP_CONTRACT,
    RelativeVariation,
    TemperatureCoefficient,
    run_corner_sweep,
    run_monte_carlo,
    run_temperature_sweep,
)


DIVIDER = """.title sweep divider
V1 in 0 10
R1 in out 1k
R2 out 0 1k
.op
.end
"""


class SweepAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.project = parse_netlist(DIVIDER, probes=(ProbeDescriptor.parse("V(out)"),))

    def test_temperature_applies_explicit_linear_coefficient(self):
        result = run_temperature_sweep(
            self.project,
            0.0,
            10.0,
            10.0,
            (TemperatureCoefficient("R1", 0.01),),
            reference_c=0.0,
        )
        self.assertEqual(result["contract"], TEMPERATURE_SWEEP_CONTRACT)
        self.assertEqual(result["provenance"]["nonlinear_temperature_physics"], False)
        self.assertEqual(result["provenance"]["self_heating"], False)
        values = [case["result"]["probes"]["V(out)"]["value"] for case in result["cases"]]
        self.assertAlmostEqual(values[0], 5.0)
        self.assertAlmostEqual(values[1], 10.0 / 2.1)

    def test_monte_carlo_is_seeded_reproducible_and_digest_mapped(self):
        variations = (RelativeVariation("R1", 0.1), RelativeVariation("R2", 0.05))
        first = run_monte_carlo(self.project, variations, samples=5, seed=1234)
        replay = run_monte_carlo(self.project, variations, samples=5, seed=1234)
        changed = run_monte_carlo(self.project, variations, samples=5, seed=1235)
        self.assertEqual(first, replay)
        self.assertNotEqual(first["cases"][0]["relative_deviations"], changed["cases"][0]["relative_deviations"])
        self.assertEqual(first["contract"], MONTE_CARLO_CONTRACT)
        self.assertEqual(first["analysis"]["random_mapping"], "sha256-counter-uniform/v1")

    def test_corner_order_and_cartesian_coverage_are_stable(self):
        result = run_corner_sweep(
            self.project,
            (RelativeVariation("R1", 0.1), RelativeVariation("R2", 0.2)),
        )
        self.assertEqual(result["contract"], CORNER_SWEEP_CONTRACT)
        self.assertEqual(len(result["cases"]), 4)
        self.assertEqual(result["cases"][0]["corner"], {"R1": "low", "R2": "low"})
        self.assertEqual(result["cases"][1]["corner"], {"R1": "high", "R2": "low"})
        self.assertEqual(result["cases"][3]["corner"], {"R1": "high", "R2": "high"})

    def test_invalid_temperature_value_and_zero_nominal_variation_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "nonpositive"):
            run_temperature_sweep(
                self.project,
                200.0,
                200.0,
                1.0,
                (TemperatureCoefficient("R1", -0.01),),
                reference_c=0.0,
            )
        zero_source = parse_netlist("V1 out 0 0\nR1 out 0 1k\n.op\n")
        with self.assertRaisesRegex(ValueError, "nonzero nominal"):
            run_monte_carlo(
                zero_source,
                (RelativeVariation("V1", 0.1),),
                samples=2,
                seed=1,
            )


class SweepCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "divider.cir"
        self.path.write_text(DIVIDER, encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def invoke(*arguments: str):
        output = StringIO()
        with contextlib.redirect_stdout(output):
            code = main(arguments)
        return code, json.loads(output.getvalue())

    def test_temperature_monte_carlo_and_corner_commands_execute(self):
        code, temperature = self.invoke(
            "temp-sweep", str(self.path), "--start-c", "0", "--stop-c", "10",
            "--step-c", "10", "--reference-c", "0", "--tempco", "R1=0.01",
            "--probe", "V(out)",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(temperature["contract"], TEMPERATURE_SWEEP_CONTRACT)
        code, monte_carlo = self.invoke(
            "monte-carlo", str(self.path), "--vary", "R1=0.1", "--samples", "3",
            "--seed", "7", "--probe", "V(out)",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(monte_carlo["contract"], MONTE_CARLO_CONTRACT)
        code, corners = self.invoke(
            "corner-sweep", str(self.path), "--vary", "R1=0.1", "--vary", "R2=0.1",
            "--probe", "V(out)",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(corners["contract"], CORNER_SWEEP_CONTRACT)


if __name__ == "__main__":
    unittest.main()
