# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""The frozen field-equivalence gate must reject invalid or changed data."""
import unittest
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from scripts.verify_packaged_ac_cht_refinement import ROOT, compare, verify


class PackagedAcChtComparisonTests(unittest.TestCase):
    def test_nested_physical_values_and_exact_identities(self):
        compare({"experimental": True, "field": [1., 2.], "label": "K"},
                {"experimental": True, "field": [1.+1e-12, 2.], "label": "K"})

    def test_shape_identity_nonfinite_and_tolerance_rejections(self):
        for expected, actual in (([1.], [1., 2.]), ({"a": 1.}, {"b": 1.}),
                                 (1., True), (True, 1), (None, 0), ("K", "C"),
                                 (1., 1.+1e-6), (1., float("nan")),
                                 (float("inf"), float("inf"))):
            with self.subTest(expected=expected, actual=actual), self.assertRaises(ValueError):
                compare(expected, actual)

    def test_changed_reference_during_replay_cannot_publish_passing_report(self):
        # Synthetic transport metadata only; no claim of numerical qualification.
        temp = ROOT / ".local" / "test-temp"
        temp.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp) as directory:
            root = Path(directory)
            worker = root / "worker"
            worker.write_bytes(b"inert fixture, never executed")
            expected = {"contract": "test", "model_status": "experimental",
                        "production_qualified": False, "input_digest_sha256": "test",
                        "mesh_digest_sha256": "test", "cell_power_w": [1.],
                        "deposited_series_resistor_power_w": 1.,
                        "outside_series_resistor_power_w": 0., "unclassified_em_network_power_w": 0.,
                        "ac": {"samples": [1.]}, "cht": {"status": "completed", "fields": [1.],
                        "diagnostics": {"energy": {"cell_energy_relative_defect": 0.,
                                                   "global_energy_relative_defect": 0.}}}}
            artifacts = {}
            families = {}
            for family in ("conduction_limit", "tangential_shear"):
                families[family] = {"passed": True, "observed_orders": [2., 2.],
                    "levels": [{"n": n, "relative_rise_l2_error": error}
                               for n, error in ((1, .4), (2, .1), (4, .025))]}
                for n in (1, 2, 4):
                    for prefix, value in (("request", {}), ("result", expected)):
                        path = root / f"{prefix}-{family}-n{n}.json"
                        path.write_text(json.dumps(value), encoding="utf-8")
                        artifacts[path.name] = sha256(path.read_bytes()).hexdigest()
            (root / "report.json").write_text(json.dumps({"status": "passed",
                "sources_unchanged": True, "production_qualified": False, "families": families,
                "gates": {"minimum_order": .8, "maximum_finest_relative_rise_l2": .05},
                "artifacts_sha256": artifacts}), encoding="utf-8")
            calls = []
            def response(*args):
                calls.append(1)
                if len(calls) == 6:
                    (root / "request-conduction_limit-n1.json").write_text("changed", encoding="utf-8")
                return {"result": expected}
            with patch("scripts.verify_packaged_ac_cht_refinement._request", side_effect=response):
                with self.assertRaisesRegex(ValueError, "changed during verification"):
                    verify(worker, root, root / "output")
            self.assertEqual(len(calls), 6)
            self.assertFalse((root / "output" / "report.json").exists())
