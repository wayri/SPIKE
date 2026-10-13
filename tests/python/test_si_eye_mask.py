# SPDX-License-Identifier: Apache-2.0
"""Original synthetic geometry fixtures; these are not protocol-standard masks."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from spike_core.si_eye_mask import evaluate_eye_mask, validate_eye_mask


def fixture():
    return {
        "schema": "spike/si-eye-mask/v1", "id": "synthetic-square", "name": "Synthetic square",
        "protocol": "test-only", "revision": "1",
        "source": {"locator": "tests/python/test_si_eye_mask.py", "clause": "independent unit square"},
        "voltage_unit": "V", "polygons": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
    }


def trace(*points):
    return [{"time_ui": x, "value": y} for x, y in points]


class EyeMaskTests(unittest.TestCase):
    def check_trace(self, points, expected, mask=None):
        result = evaluate_eye_mask(mask or fixture(), [trace(*points)], "V")
        self.assertEqual(result["status"], expected)
        self.assertEqual(result["passed"], expected == "pass")
        return result

    def test_interior_and_exterior(self):
        self.check_trace([(0.5, 0.5)], "fail")
        self.check_trace([(-1, 2), (2, 2)], "pass")

    def test_boundaries_and_vertices(self):
        for point in [(0, 0.5), (1, 0.5), (0.5, 0), (0.5, 1), (0, 0), (1, 1)]:
            with self.subTest(point=point):
                self.check_trace([point], "fail")

    def test_outside_endpoints_cross_interior(self):
        result = self.check_trace([(-1, 0.5), (2, 0.5)], "fail")
        self.assertEqual(result["point_hit_count"], 0)
        self.assertEqual(result["segment_hit_count"], 1)
        self.assertEqual(result["hit_count"], 1)

    def test_tangent_and_collinear_segments(self):
        self.check_trace([(-1, 1), (1, -1)], "fail")  # Touches only (0, 0).
        self.check_trace([(-1, 0), (2, 0)], "fail")
        self.check_trace([(-1, -0.001), (2, -0.001)], "pass")

    def test_exact_float_boundary_no_arbitrary_tolerance(self):
        self.check_trace([(0.5, -sys.float_info.min)], "pass")
        self.check_trace([(0.5, sys.float_info.min)], "fail")

    def test_no_connection_between_traces(self):
        result = evaluate_eye_mask(fixture(), [trace((-1, 0.5)), trace((2, 0.5))], "V")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["segment_hit_count"], 0)

    def test_wrapped_time_rejected(self):
        with self.assertRaisesRegex(ValueError, "split eye wraps"):
            self.check_trace([(2, 2), (-1, 2)], "pass")

    def test_multiple_polygons_and_no_duplicate_hits(self):
        mask = fixture()
        mask["polygons"].append([[2, 0], [3, 0], [3, 1], [2, 1]])
        self.check_trace([(2.5, 0.5)], "fail", mask)
        self.check_trace([(1.5, 0.5)], "pass", mask)
        mask["polygons"].append(copy.deepcopy(mask["polygons"][0]))
        self.assertEqual(self.check_trace([(0.5, 0.5)], "fail", mask)["hit_count"], 1)

    def test_concave_and_reversed_winding(self):
        mask = fixture()
        mask["polygons"] = [[[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2]]]
        for _ in range(2):
            self.check_trace([(1.5, 1.5)], "pass", mask)
            self.check_trace([(0.5, 1.5)], "fail", mask)
            mask["polygons"][0].reverse()

    def test_empty_and_malformed_evidence_rejected(self):
        for traces in [[], [[]], None, [[{}]], [[{"time_ui": 0, "value": float("nan")}]],
                       [[{"time_ui": True, "value": 2}]], [[{"time_ui": "0", "value": 2}]]]:
            with self.subTest(traces=traces), self.assertRaises(ValueError):
                evaluate_eye_mask(fixture(), traces, "V")

    def test_units_and_provenance(self):
        with self.assertRaisesRegex(ValueError, "match"):
            evaluate_eye_mask(fixture(), [trace((2, 2))], "normalized")
        mask = fixture()
        mask["voltage_unit"] = "normalized"
        result = evaluate_eye_mask(mask, [trace((2, 2))], "normalized", {"kind": "synthetic"})
        self.assertEqual(result["source"], mask["source"])
        self.assertEqual(result["evidence"], {"kind": "synthetic"})
        self.assertTrue(any("normative" in text for text in result["limitations"]))

    def test_malformed_masks(self):
        changes = [
            {"schema": "other"}, {"source": {"locator": "x"}}, {"revision": " "},
            {"voltage_unit": "mV"}, {"polygons": []},
            {"polygons": [[[0, 0], [1, 1], [2, 2]]]},
            {"polygons": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            {"polygons": [[[0, 0], [2, 2], [0, 2], [2, 0]]]},
            # Nonzero signed area but crossing edges.
            {"polygons": [[[0, 0], [3, 2], [0, 2], [2, 0]]]},
            {"polygons": [[[0, 0], [2, 0], [1, 0], [1, 1], [0, 1]]]},
            {"polygons": [[[0, 0], [1, 0], [1, float("inf")]]]},
            {"polygons": [[[0, 0], [1, 0], [1, "1"]]]},
            {"extra": "not admitted"},
        ]
        for change in changes:
            mask = fixture()
            mask.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_eye_mask(mask)

    def test_work_limits(self):
        with self.assertRaisesRegex(ValueError, "bounded"):
            evaluate_eye_mask(fixture(), [trace(*([(2, 2)] * 100001))], "V")
        mask = fixture()
        mask["polygons"] *= 17
        with self.assertRaises(ValueError):
            validate_eye_mask(mask)


if __name__ == "__main__":
    unittest.main()
