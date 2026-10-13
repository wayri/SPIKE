# SPDX-License-Identifier: Apache-2.0
"""Regression coverage for the opt-in compact project-open transport."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.contracts import SpiDeR
from python.spike_core.normalized_source_codec import (
    NORMALIZED_SOURCE_WRAPPER,
    decode_normalized_source,
)
from python.spike_core.project_package import PackageReadResult
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.spider_v2 import SpiDeRV2


def _minimal_design() -> dict:
    return SpiDeRV2.from_v1(SpiDeR(
        design_id="compact-transport",
        name="Compact transport",
        source_format="neutral",
        layers=[{"id": 0, "name": "F.Cu"}],
        nets=[{"id": 1, "name": "VCC"}],
        metadata={"source_sha256": "c" * 64, "retained_marker": [1, 2, 3]},
    )).to_dict()


def _open(path: Path, opened: PackageReadResult, *, compact_canonical_design: bool) -> dict:
    params = {
        "path": str(path),
        "defer_artifacts": True,
        "compact_normalized_source": True,
    }
    if compact_canonical_design:
        params["compact_canonical_design"] = True
    with patch("python.spike_core.service_project_handlers.read_project", return_value=opened):
        response = handle_project_request(
            "read_project_package",
            params,
            request_id="compact-transport-test",
            application_version="test",
        )
    if not response or not response.get("ok"):
        raise AssertionError(response)
    return response["result"]


class ProjectOpenCompactTransportTests(unittest.TestCase):
    def test_opt_in_canonical_wrapper_is_lossless_and_preserves_project_envelope(self):
        retained_study = {
            "contract": "spike/test-retained-study/v1",
            "cases": [{"id": "nominal", "frequency_hz": 1_000_000}],
            "future": {"review_state": "retained"},
        }
        legacy_project = {
            "format": "spike-project-package/v2",
            "project": {"id": "compact-project", "name": "Compact project"},
            "design": {"source_format": "neutral", "source_board": ""},
            "analysis": {"retained_study": retained_study},
        }
        opened = PackageReadResult(
            manifest={"manifest_payload_sha256": "a" * 64, "profile": "workspace"},
            payload={
                "project": legacy_project["project"],
                # A real package read has already crossed JSON and therefore
                # contains lists rather than Python-only tuple values.
                "design_ir": json.loads(json.dumps(_minimal_design())),
                "extensions": {"legacy": legacy_project},
            },
        )
        existing_path = Path(__file__)
        default = _open(existing_path, opened, compact_canonical_design=False)
        compact = _open(existing_path, opened, compact_canonical_design=True)

        default_design = default["canonical"]["design_ir"]
        wrapper = compact["canonical"]["design_ir"]
        self.assertIsInstance(default_design, dict)
        self.assertEqual(wrapper["contract"], NORMALIZED_SOURCE_WRAPPER)
        self.assertEqual(json.loads(decode_normalized_source(wrapper)), default_design)
        self.assertEqual(compact["canonical"].keys(), default["canonical"].keys())
        self.assertEqual(compact["manifest"], default["manifest"])
        self.assertEqual(compact["project"], default["project"])
        self.assertEqual(default["project"]["analysis"]["retained_study"], retained_study)


if __name__ == "__main__":
    unittest.main()
