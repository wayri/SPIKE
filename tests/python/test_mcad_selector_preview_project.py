"""Manifest-bound exact selector-preview package transaction regressions."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.assembly_package_shapes import selector_inventory_sha256
from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.mcad_selector_preview import SelectorPreviewResult
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.service_project_handlers import handle_project_request
from tests.python import test_assembly_package_shapes as package_shape_fixtures


class McadSelectorPreviewProjectTests(unittest.TestCase):
    def test_preview_generation_is_manifest_bound_transactional_and_replaceable(self):
        assembly, models, index, model_artifacts, shape_artifacts = package_shape_fixtures.AssemblyPackageShapeTests().fixture()
        shape = index["shapes"][0]
        design = DesignIRV2.from_v1(DesignIR(
            design_id="selector-preview", name="Selector preview", source_format="neutral",
            layers=[{"id": 0, "name": "F.Cu"}], metadata={"source_sha256": "9" * 64},
        ))
        payload = {
            "project": {"id": "selector-preview", "name": "Selector preview"},
            "design_ir": design.to_dict(), "assembly_ir": assembly,
            "models": models, "assembly_package_shapes": index,
        }

        def outcome(data: bytes) -> SelectorPreviewResult:
            digest = hashlib.sha256(data).hexdigest()
            return SelectorPreviewResult(
                source_sha256=shape["source_sha256"],
                topology_artifact_sha256=shape["topology_artifact_sha256"],
                selector_inventory_sha256=selector_inventory_sha256(shape["entities"]),
                artifact_name=f'{shape["shape_id"]}-{digest[:12]}.spkselect.glb',
                artifact_sha256=digest, artifact_bytes=data, freecad_version="1.1.3",
                linear_deflection_mm=0.1, face_count=1, edge_count=1, axis_count=1,
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview.spike"
            initial = write_spike_package(path, payload, model_artifacts=model_artifacts, package_shape_artifacts=shape_artifacts)
            first = outcome(b"first selector preview")
            with patch("python.spike_core.service_project_selector_preview.generate_selector_preview", return_value=first) as generate:
                response = handle_project_request(
                    "generate_mcad_selector_preview_in_project",
                    {"project_path": str(path), "expected_manifest_payload_sha256": initial["manifest_payload_sha256"], "shape_id": shape["shape_id"]},
                    request_id="preview-first", application_version="test",
                )
            self.assertTrue(response["ok"], response)
            generate.assert_called_once()
            opened = read_project(path, include_members=True)
            preview = opened.payload["assembly_package_shapes"]["shapes"][0]["selector_preview"]
            first_member = preview["artifact_uri"].removeprefix("package:")
            self.assertEqual(opened.members[first_member], first.artifact_bytes)
            self.assertTrue(preview["visual_only"])
            self.assertFalse(preview["solver_ready"])
            self.assertEqual(opened.payload["audit"][-1]["event"], "mcad_package_shape_selector_preview_generated")

            stale = handle_project_request(
                "generate_mcad_selector_preview_in_project",
                {"project_path": str(path), "expected_manifest_payload_sha256": initial["manifest_payload_sha256"], "shape_id": shape["shape_id"]},
                request_id="preview-stale", application_version="test",
            )
            self.assertFalse(stale["ok"])
            self.assertIn("changed since it was verified", str(stale))

            second = outcome(b"second selector preview")
            with patch("python.spike_core.service_project_selector_preview.generate_selector_preview", return_value=second):
                replaced = handle_project_request(
                    "generate_mcad_selector_preview_in_project",
                    {"project_path": str(path), "expected_manifest_payload_sha256": opened.manifest["manifest_payload_sha256"], "shape_id": shape["shape_id"]},
                    request_id="preview-second", application_version="test",
                )
            self.assertTrue(replaced["ok"], replaced)
            reopened = read_project(path, include_members=True)
            replacement_preview = reopened.payload["assembly_package_shapes"]["shapes"][0]["selector_preview"]
            replacement_member = replacement_preview["artifact_uri"].removeprefix("package:")
            self.assertNotIn(first_member, reopened.members)
            self.assertEqual(reopened.members[replacement_member], second.artifact_bytes)

            forbidden = handle_project_request(
                "generate_mcad_selector_preview_in_project",
                {"project_path": str(path), "expected_manifest_payload_sha256": reopened.manifest["manifest_payload_sha256"], "shape_id": shape["shape_id"], "artifact_uri": "package:anything"},
                request_id="preview-forbidden", application_version="test",
            )
            self.assertFalse(forbidden["ok"])
            self.assertIn("exactly", str(forbidden))


if __name__ == "__main__":
    unittest.main()
