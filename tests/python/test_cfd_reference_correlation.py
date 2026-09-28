# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import copy
import tempfile
from pathlib import Path
import unittest
from python.spike_core.cfd_reference_correlation import (
    NASA_CF_SHA256, REFERENCE_ID, admit_nasa_backstep_cf, _compare_admitted)


class MeasuredCorrelationTests(unittest.TestCase):
    def fixture(self):
        # Synthetic arithmetic fixture, never labeled experimental evidence.
        ref = {"reference_id": REFERENCE_ID, "source_sha256": NASA_CF_SHA256,
            "normalization": "fixture", "observations": [{"x_over_h": x, "cf": y, "published_error": .001}
                for x,y in [(0, -.001), (1, 0), (2, .001)]]}
        pred = {"reference_id": REFERENCE_ID, "reference_sha256": NASA_CF_SHA256,
            "solver_run_sha256": "a"*64, "reference_reynolds_h": 36000, "opposite_wall_angle_deg": 0,
            "normalization": "fixture", "x_over_h": [0,1,2], "cf": [0,.001,.002]}
        return ref, pred

    def test_error_math_not_production_approval(self):
        ref, pred = self.fixture()
        result = _compare_admitted(ref, pred, maximum_absolute_error=.002)
        self.assertAlmostEqual(result["rms_error"], .001)
        self.assertTrue(result["within_declared_budget"])
        self.assertFalse(result["production_qualified"])

    def test_reject_wrong_scope_and_missing_samples(self):
        ref, pred = self.fixture()
        for key, value in [("reference_reynolds_h", 50000), ("normalization", "other"),
                           ("solver_run_sha256", ""), ("cf", [0,float("nan"),1]), ("cf", [False,0,1]), ("x_over_h", [1,2,3])]:
            changed = copy.deepcopy(pred); changed[key] = value
            with self.assertRaises(ValueError):
                _compare_admitted(ref, changed, maximum_absolute_error=.002)

    def test_tampered_reference_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"cf.dat"
            path.write_text("0 0 .1\n1 1 .1\n2 2 .1\n")
            with self.assertRaisesRegex(ValueError, "digest"):
                admit_nasa_backstep_cf(path)
