# SPDX-License-Identifier: Apache-2.0
"""Behavioral invariants for the bounded project-open projection fast path."""

from __future__ import annotations

import copy
import unittest

from python.spike_core.contracts import SpiDeR, ValidationIssue
from python.spike_core.service_project import frontend_project_payload
from python.spike_core.spider_v2 import SpiDeRV2


class ProjectLoadingPerformanceTests(unittest.TestCase):
    def test_v1_projection_is_exact_and_detached_with_future_metadata(self):
        legacy = SpiDeR(
            design_id="projection-fast-path",
            name="Projection fast path",
            source_format="neutral",
            layers=[{"id": 1, "name": "F.Cu", "future": {"color": [1, 2, 3]}}],
            nets=[{"id": 2, "name": "VCC"}],
            issues=[ValidationIssue(
                code="future-warning", severity="warning", message="retained",
                suggestion="keep future issue fields",
            )],
            metadata={"future": {"nested": [{"identity": "retained"}]}},
        )
        canonical = SpiDeRV2.from_v1(legacy).to_dict()
        expected = SpiDeRV2.from_dict(canonical).to_v1(
            allow_unprojected_arcs=True,
        ).to_dict()
        source_before = copy.deepcopy(canonical)

        projected = frontend_project_payload({
            "project": {"name": "projection"},
            "design_ir": canonical,
        })

        self.assertEqual(projected["design"], expected)
        self.assertEqual(canonical, source_before)
        self.assertIsInstance(projected["design"]["issues"][0], dict)
        projected["design"]["layers"][0]["future"]["color"].append(4)
        projected["design"]["metadata"]["future"]["nested"][0]["identity"] = "changed"
        self.assertEqual(canonical, source_before)


if __name__ == "__main__":
    unittest.main()
