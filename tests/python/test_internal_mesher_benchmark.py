# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent contract, isolation and geometry checks for the mesher benchmark."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_internal_mesher import (
    GMSH_API,
    GMSH_DLL,
    GMSH_PIN,
    _isolated,
    _oriented_cells,
    _sha_file,
    capture_baseline,
    fixture_corpus,
    fixture_manifest,
    run_benchmark,
    validate_tetrahedralization,
    worker,
)


EXPECTED_FIXTURES = {
    "generic_8": "7453bee85ad01d2be8af15f9881c35e4e284d7f4beb7aacbea320f7c0c140dd2",
    "generic_32": "2842fd43896f2c901ddf8fe9aa463a270e18fc72d0ea74e8505ac13febb5c26a",
    "generic_64": "ee9a681de19c42607f6cc1569cdc84481cdcc1927d6305cd27f6a4d716e7b1c4",
    "generic_128": "26a9ef81d38181aea1122e2737b53ff3877e45f3fae35a9f822153e44a80c2a3",
    "cube_lattice_cospherical": "494d9b5f44547a268e744fa3e862b305f2a574fba093c8b854d10513c967bdbd",
    "thin_conditioned": "ca80de12fe4a8d1e227aa4ad2327e10c582fea438d911fc76932cb3c0ea14618",
}


class InternalMesherBenchmarkTests(unittest.TestCase):
    def test_original_corpus_is_reproducible_and_pinned(self):
        first = fixture_corpus()
        second = fixture_corpus()
        self.assertEqual(first, second)
        self.assertEqual({item["id"]: item["points_sha256"] for item in first},
                         EXPECTED_FIXTURES)
        self.assertEqual([len(item["points"]) for item in first[:4]], [8, 32, 64, 128])
        self.assertEqual(first[4]["kind"], "integer_lattice_cube_corners")
        self.assertEqual(first[5]["expected"], "reported_status")
        self.assertEqual(fixture_manifest()["corpus_sha256"],
                         "ecfb58a3f29e88481e4356632ce3a4d8b5b2a63d164906c0a968ccce504d3ae2")

    def test_independent_geometry_audit_accepts_a_tetrahedron(self):
        points = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                  [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        cells = _oriented_cells(points, [[0, 1, 2, 3]])
        audit = validate_tetrahedralization(points, points, cells)
        self.assertEqual(audit["status"], "passed")
        self.assertAlmostEqual(audit["tetra_volume"], 1.0 / 6.0)
        self.assertAlmostEqual(audit["quality_mean_ratio"]["min"], 0.8399473665965821)
        self.assertEqual(audit["validation_ns"] >= audit["convex_hull_oracle_ns"], True)

    def test_geometry_audit_rejects_omitted_tiny_duplicate_and_same_side_cells(self):
        points = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                  [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.2, 0.2, 0.2]]
        with self.assertRaisesRegex(ValueError, "not all original"):
            validate_tetrahedralization(points, points, _oriented_cells(points, [[0, 1, 2, 3]]))
        tiny = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0], [0.0, 0.0, 1e-18]]
        with self.assertRaisesRegex(ValueError, "tiny"):
            validate_tetrahedralization(tiny, tiny, _oriented_cells(tiny, [[0, 1, 2, 3]]))
        tetra = points[:4]
        cell = _oriented_cells(tetra, [[0, 1, 2, 3]])[0]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_tetrahedralization(tetra, tetra, [cell, cell, cell])
        overlapping = tetra + [[0.1, 0.1, 2.0]]
        same_side = _oriented_cells(overlapping, [[0, 1, 2, 3], [0, 1, 2, 4]])
        with self.assertRaisesRegex(ValueError, "same side"):
            validate_tetrahedralization(overlapping, overlapping, same_side)

    def test_geometry_audit_rejects_disconnected_cell_adjacency(self):
        first = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                 [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        second = [[point[0] + 3.0, point[1], point[2]] for point in first]
        points = first + second
        cells = _oriented_cells(points, [[0, 1, 2, 3], [4, 5, 6, 7]])
        with self.assertRaisesRegex(ValueError, "adjacency is disconnected"):
            validate_tetrahedralization(points, points, cells)

    def test_kernel_and_fullrun_are_separate_and_geometrically_identical(self):
        points = fixture_corpus()[1]["points"]
        kernel = worker({"backend": "internal_kernel", "points": points,
                         "samples": 3, "warmups": 1})
        fullrun = worker({"backend": "internal_fullrun", "points": points,
                          "samples": 3, "warmups": 1})
        self.assertEqual(kernel["status"], "completed")
        self.assertEqual(fullrun["status"], "completed")
        self.assertEqual(kernel["result"]["snapshot"], fullrun["result"]["snapshot"])
        self.assertEqual(len(kernel["generation_samples_ns"]), 3)
        self.assertNotEqual(kernel["runtime_version"], fullrun["runtime_version"])
        if sys.platform == "win32":
            memory = kernel["memory"]
            self.assertIn("peak_working_set_bytes", memory["after_samples"])
            self.assertIn("peak_pagefile_usage_bytes", memory["after_samples"])
            self.assertIn("current_private_usage_bytes", memory["after_samples"])
            self.assertIn("observed_post_call_private_growth_bytes", memory)

    def test_subprocess_drains_large_output_and_has_finite_timeout(self):
        points = fixture_corpus()[2]["points"]
        result = _isolated({"backend": "internal_kernel", "points": points,
                            "samples": 3, "warmups": 1}, timeout_s=20)
        self.assertEqual(result["status"], "completed", result.get("error"))
        self.assertEqual(len(result["result"]["vertices"]), 64)
        self.assertGreater(len(json.dumps(result["result"])), 32768)
        if sys.platform == "win32":
            after = result["memory"]["after_samples"]
            self.assertIn("peak_working_set_bytes", after)
            self.assertIn("peak_pagefile_usage_bytes", after)

    def test_thin_conditioned_failure_is_an_explicit_row_status(self):
        points = fixture_corpus()[-1]["points"]
        for backend in ("internal_kernel", "internal_fullrun"):
            result = _isolated({"backend": backend, "points": points,
                                "samples": 3, "warmups": 1}, timeout_s=20)
            self.assertEqual(result["status"], "failed")
            self.assertIn("no complete 3D tetrahedralization", result["error"])

    def test_scipy_is_a_black_box_with_separate_postrun_audit(self):
        points = fixture_corpus()[0]["points"]
        result = _isolated({"backend": "scipy_qhull", "points": points,
                            "samples": 3, "warmups": 1}, timeout_s=20)
        self.assertEqual(result["status"], "completed", result.get("error"))
        audit = validate_tetrahedralization(points, result["result"]["vertices"],
                                            result["result"]["cells"])
        self.assertEqual(audit["status"], "passed")

    def test_external_invalidity_is_reported_without_failing_internal_status(self):
        points = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                  [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        fixture = {"id": "synthetic", "expected": "success", "points": points,
                   "points_sha256": "0" * 64}
        valid_cells = _oriented_cells(points, [[0, 1, 2, 3]])
        def isolated(payload, _timeout):
            cells = valid_cells if payload["backend"] == "internal_kernel" else []
            return {"status": "completed", "result": {"vertices": points, "cells": cells,
                                                        "snapshot": {"cells": cells}}}
        with patch("scripts.benchmark_internal_mesher.fixture_corpus", return_value=[fixture]), \
             patch("scripts.benchmark_internal_mesher.fixture_manifest", return_value={}), \
             patch("scripts.benchmark_internal_mesher._isolated", side_effect=isolated):
            result = run_benchmark(samples=3, warmups=1, timeout_s=5,
                                   backends=("internal_kernel", "gmsh_4_15_2"))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["internal_status"], "passed")
        self.assertEqual(result["comparison_status"], "completed_with_reported_failures")
        self.assertTrue(result["backend_summary"]["internal_kernel"]["expected_success_cases_valid"])
        self.assertFalse(result["backend_summary"]["gmsh_4_15_2"]["expected_success_cases_valid"])

    @unittest.skipUnless(GMSH_API.is_file() and GMSH_DLL.is_file(),
                         "optional separately installed Gmsh unavailable")
    def test_pinned_gmsh_raw_api_is_black_box_and_audited(self):
        if any(_sha_file(Path(path)) != digest for path, digest in GMSH_PIN.items()):
            self.skipTest("optional Gmsh entry artifacts differ from repository pins")
        points = fixture_corpus()[0]["points"]
        result = _isolated({"backend": "gmsh_4_15_2", "points": points,
                            "samples": 3, "warmups": 1}, timeout_s=20)
        self.assertEqual(result["status"], "completed", result.get("error"))
        self.assertIn(result["backend_metadata"]["public_api"],
                      ("gmsh.algorithm.tetrahedralize", "gmsh.model.mesh.tetrahedralize"))
        audit = validate_tetrahedralization(points, result["result"]["vertices"],
                                            result["result"]["cells"])
        self.assertEqual(audit["status"], "passed")

    def test_baseline_capture_refuses_to_overwrite_evidence(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            (root / "baseline-internal-preoptimization.json").write_text("preserve")
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                capture_baseline(root)
            self.assertEqual((root / "baseline-internal-preoptimization.json").read_text(),
                             "preserve")


if __name__ == "__main__":
    unittest.main()
