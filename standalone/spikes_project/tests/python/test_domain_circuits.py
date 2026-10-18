# SPDX-License-Identifier: Apache-2.0
"""Executable analytical checks for the standalone domain-circuit examples."""

import csv
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[2]
EXAMPLES = PROJECT / "examples" / "domain-circuits"
REPOSITORY = PROJECT.parents[1]


def _ngspice():
    configured = os.environ.get("SPIKES_TEST_NGSPICE")
    candidates = [Path(configured)] if configured else []
    candidates.append(REPOSITORY / "runtime" / "external" / "Spice64" / "bin" / "ngspice_con.exe")
    located = shutil.which("ngspice_con") or shutil.which("ngspice")
    if located:
        candidates.append(Path(located))
    return next((path for path in candidates if path.is_file()), None)


def _run(name):
    executable = _ngspice()
    if executable is None:
        raise unittest.SkipTest("ngspice executable is unavailable")
    source = EXAMPLES / name
    scratch = REPOSITORY / ".tmp-tests"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as folder:
        work = Path(folder)
        deck = work / source.name
        shutil.copyfile(source, deck)
        completed = subprocess.run(
            [str(executable), "-b", "-o", "ngspice.log", deck.name],
            cwd=work, capture_output=True, text=True, timeout=20, check=False,
        )
        log = (work / "ngspice.log").read_text(encoding="utf-8", errors="replace")
        if completed.returncode:
            raise AssertionError(f"ngspice failed for {name}:\n{log[-2000:]}")
        output = work / f"{source.stem}.csv"
        if not output.is_file():
            raise AssertionError(f"ngspice did not produce {output.name}:\n{log[-2000:]}")
        with output.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream, delimiter=" ", skipinitialspace=True))
    header = [item for item in rows[0] if item]
    values = [[float(item) for item in row if item] for row in rows[1:] if row]
    return header, values


class DomainCircuitTests(unittest.TestCase):
    def test_all_decks_declare_ngspice_analysis_and_csv_output(self):
        expected = {
            "rf_series_resonance.cir": ".ac ",
            "highspeed_matched_interconnect.cir": ".tran ",
            "precision_bridge_ideal_amplifier.cir": ".op",
            "pwm_buck_ideal_switch.cir": ".tran ",
            "hv_rc_divider.cir": ".tran ",
            "low_voltage_high_current_path.cir": ".tran ",
        }
        self.assertEqual({path.name for path in EXAMPLES.glob("*.cir")}, set(expected))
        for name, analysis in expected.items():
            text = (EXAMPLES / name).read_text(encoding="ascii")
            self.assertIn(analysis, text.lower())
            self.assertIn("wrdata ", text.lower())

    def test_rf_series_resonance_matches_lc_oracle(self):
        _, rows = _run("rf_series_resonance.cir")
        frequency, magnitude = max(rows, key=lambda row: row[1])[:2]
        expected = 1 / (2 * math.pi * math.sqrt(1e-6 * 25.3303e-12))
        self.assertAlmostEqual(frequency / expected, 1.0, delta=0.006)
        self.assertAlmostEqual(magnitude, 1.0, delta=0.01)

    def test_matched_interconnect_has_half_amplitude_after_delay(self):
        _, rows = _run("highspeed_matched_interconnect.cir")
        before = min(rows, key=lambda row: abs(row[0] - 5e-9))[2]
        after = min(rows, key=lambda row: abs(row[0] - 8e-9))[2]
        self.assertLess(before, 0.05)
        self.assertAlmostEqual(after, 0.5, delta=0.02)

    def test_precision_bridge_matches_resistor_and_ideal_gain_oracle(self):
        _, rows = _run("precision_bridge_ideal_amplifier.cir")
        bridge_p, bridge_n, output = rows[-1][1:4]
        expected_p = 5 * 10010 / (10000 + 10010)
        self.assertAlmostEqual(bridge_p, expected_p, delta=1e-7)
        self.assertAlmostEqual(bridge_n, 2.5, delta=1e-7)
        self.assertAlmostEqual(output, 100 * (expected_p - 2.5), delta=1e-5)

    def test_pwm_buck_settles_near_ideal_duty_ratio(self):
        _, rows = _run("pwm_buck_ideal_switch.cir")
        tail = [row[1] for row in rows if row[0] >= 2.5e-3]
        mean = sum(tail) / len(tail)
        self.assertAlmostEqual(mean, 12 * 0.4, delta=0.25)
        self.assertLess(max(tail) - min(tail), 0.25)

    def test_hv_divider_matches_first_order_step(self):
        _, rows = _run("hv_rc_divider.cir")
        time, voltage = min(rows, key=lambda row: abs(row[0] - 9e-3))[:2]
        expected = 100 * (1 - math.exp(-time / 9e-3))
        self.assertAlmostEqual(voltage, expected, delta=0.2)
        self.assertAlmostEqual(rows[-1][1], 100.0, delta=0.5)

    def test_high_current_path_reaches_dc_limit(self):
        _, rows = _run("low_voltage_high_current_path.cir")
        voltage, current = rows[-1][1:3]
        self.assertAlmostEqual(current, 12 / 0.12, delta=0.1)
        self.assertAlmostEqual(voltage, 10.0, delta=0.02)


if __name__ == "__main__":
    unittest.main()
