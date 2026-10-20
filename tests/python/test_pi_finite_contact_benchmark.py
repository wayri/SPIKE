# SPDX-License-Identifier: Apache-2.0
"""Executed finite-contact ladders and independently integrated work oracle."""
from copy import deepcopy
import json
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from scripts.benchmark_pi_finite_contact import (
    CASES, FIXED, ROOT, TARGETS, assess, reference, run_benchmark, validate_report,
)


class FiniteContactBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_benchmark()

    def test_all_four_actual_three_level_ladders(self):
        validate_report(self.report)
        self.assertEqual(len(self.report["cases"]), 4)
        for case in self.report["cases"]:
            self.assertEqual([r["target_mm"] for r in case["levels"]], list(TARGETS))
            counts = [r["result"]["triangle_count"] for r in case["levels"]]
            self.assertTrue(all(a < b for a, b in zip(counts, counts[1:])))

    def test_reference_against_independent_gauss_integration(self):
        # Integrate the exact conservative current, without the closed-form R.
        x, weights = np.polynomial.legendre.leggauss(5)
        for case in CASES:
            integral = 0.
            for left, right in ((0., .5), (.5, 1.5), (1.5, 2.)):
                points = left+(x+1)*(right-left)/2
                sheet_current = np.minimum(np.minimum(points/.5, (2-points)/.5), 1.)
                integral += np.dot(weights, sheet_current**2)*(right-left)/2
            loss = integral/(case["conductivity_s_m"]*.035e-3)
            self.assertAlmostEqual(loss/reference(case)["resistance_ohm"], 1., places=14)
            self.assertAlmostEqual(reference(case)["p95_a_mm2"], 1/.035)

    def test_solved_rotation_conductivity_and_inactive_volume(self):
        actual = {c["fixture"]["id"]: c["levels"][-1]["result"] for c in self.report["cases"]}
        base = actual["base"]
        self.assertLess(abs(actual["rotated"]["resistance_ohm"]/base["resistance_ohm"]-1), 1e-10)
        self.assertLess(abs(actual["double_conductivity"]["resistance_ohm"]*2/base["resistance_ohm"]-1), 1e-10)
        self.assertAlmostEqual(actual["inactive_island"]["current_density_observable"]["undriven_planar_volume_mm3"], .0175)
        self.assertFalse(base["production_qualified"])

    def test_forged_pass_cannot_hide_bad_finest_solution(self):
        report = deepcopy(self.report)
        level = report["cases"][0]["levels"][-1]
        level["result"]["resistance_ohm"] *= 1.1
        # Preserve raw work consistency to isolate analytical acceptance.
        level["result"]["dissipation_w_at_one_ampere"] *= 1.1
        level["result"]["current_density_observable"]["planar_dissipation_w"] *= 1.1
        decision = assess(CASES[0], report["cases"][0]["levels"])
        self.assertEqual(decision["status"], "failed")
        with self.assertRaises(ValueError):
            validate_report(report)

    def test_identity_volume_status_and_nan_forgeries_rejected(self):
        for mutate in (
            lambda r: r["limits"].__setitem__("resistance_relative", .5),
            lambda r: r["cases"][0]["fixture"].__setitem__("conductivity_s_m", 1.),
            lambda r: r["cases"][0]["reference"].__setitem__("resistance_ohm", 1.),
            lambda r: r["cases"][0]["levels"].reverse(),
            lambda r: r["cases"][0]["levels"].pop(),
            lambda r: r["cases"][0]["levels"][0]["contacts"][0].__setitem__("area_mm2", 1.),
            lambda r: r["cases"][0]["levels"][0]["contacts"][0].__setitem__("node", float("nan")),
            lambda r: r["cases"][0]["levels"][0]["result"].__setitem__("triangle_count", float("nan")),
            lambda r: r["cases"][0]["levels"][0]["result"].__setitem__("production_qualified", True),
            lambda r: r["cases"][0]["levels"][0]["result"].__setitem__("relative_residual", float("nan")),
            lambda r: r["cases"][0]["levels"][0]["result"]["current_density_observable"].__setitem__("physical_planar_volume_mm3", .01),
            lambda r: r["cases"][0]["levels"][0]["result"]["current_density_observable"]["p95"].__setitem__("converged", False),
        ):
            report = deepcopy(self.report)
            mutate(report)
            with self.assertRaises(ValueError):
                validate_report(report)

    def test_raw_terminal_work_cannot_be_hidden_by_saved_diagnostic(self):
        report = deepcopy(self.report)
        report["cases"][0]["levels"][0]["result"]["resistance_ohm"] *= 2
        with self.assertRaisesRegex(ValueError, "raw terminal-work"):
            assess(CASES[0], report["cases"][0]["levels"])

    def test_precision_geometry_audit_cannot_be_omitted_or_relaxed(self):
        for key, value in (("grid_mm", 1e-6), ("formal_roundoff_certificate", True)):
            report = deepcopy(self.report)
            report["cases"][1]["levels"][0]["geometry_audit"][0]["precision_geometry"][key] = value
            with self.assertRaises(ValueError):
                validate_report(report)
        report = deepcopy(self.report)
        support = report["cases"][1]["levels"][0]["geometry_audit"][0]["precision_geometry"]["copper"]
        support["area_budget_mm2"] = 1.
        with self.assertRaises(ValueError):
            validate_report(report)

    def test_all_levels_retain_raw_conservation_and_heat_gates(self):
        for key, value in (("maximum_cell_kcl_error_a", 1e-7),
                           ("maximum_face_kcl_error_a", -1.),
                           ("relative_energy_error", 1e-6),
                           ("dissipation_w_at_one_ampere", 0.)):
            report = deepcopy(self.report)
            report["cases"][0]["levels"][0]["result"][key] = value
            with self.assertRaises(ValueError):
                validate_report(report)

    def test_actual_cli_saved_report_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as directory:
            from pathlib import Path
            path = Path(directory)/"benchmark.json"
            command = [sys.executable, str(ROOT/"scripts/benchmark_pi_finite_contact.py"), "--output", str(path)]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(first.returncode, 0, first.stderr)
            validate_report(json.loads(path.read_text()))
            before = path.read_bytes()
            repeated = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(path.read_bytes(), before)

    def test_rotated_polygon_overlay_remains_explicitly_rejected(self):
        # A retained unsupported path, never counted as a successful solve.
        from shapely.affinity import rotate
        from shapely.geometry import box
        from python.spike_core.dc_triangle_partition import partition_polygon_groups
        from python.spike_core.peec_conforming_dc import solve_hybridized_conforming_dc
        rotate_shape = lambda shape: rotate(shape, .61, origin=(0, 0), use_radians=True)
        groups = {("F.Cu", "N"): {"geometry": rotate_shape(box(0, 0, 2, 1)),
                  "thickness_mm": .035, "conductivity_s_m": 5.8e7, "z_mm": 0.}}
        contacts = [{"id": name, "layer": "F.Cu", "net": "N", "geometry": rotate_shape(shape)}
                    for name, shape in zip(("source", "load"), (box(0, 0, .5, 1), box(1.5, 0, 2, 1)))]
        mesh = partition_polygon_groups(groups, contacts, target_mm=.5)
        with self.assertRaisesRegex(ValueError, "reversed, degenerate or ill-shaped"):
            solve_hybridized_conforming_dc(mesh, 0, 1, include_density=True)


if __name__ == "__main__":
    unittest.main()
