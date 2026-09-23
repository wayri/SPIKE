"""Transactional exact STEP package-shape project regressions."""

from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.design_ir_v2_schema import canonical_uuid
from python.spike_core.mcad_package_shape import StepPackageShapeResult
from python.spike_core.mcad_tessellation import StepTessellationResult
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.service_project_handlers import handle_project_request


STEP = b"ISO-10303-21;\nHEADER;ENDSEC;DATA;ENDSEC;END-ISO-10303-21;\n"


def _glb_bytes() -> bytes:
    document = {"asset": {"version": "2.0"}, "scenes": [{}]}
    body = json.dumps(document, separators=(",", ":")).encode("utf-8")
    body += b" " * ((-len(body)) % 4)
    return struct.pack("<4sII", b"glTF", 2, 20 + len(body)) + struct.pack("<II", len(body), 0x4E4F534A) + body


def _shape_result(artifact_name: str, artifact: bytes) -> StepPackageShapeResult:
    axis_fingerprint = hashlib.sha256(b"axis-z").hexdigest()
    face_fingerprint = hashlib.sha256(b"cylinder-face").hexdigest()
    axis_id = f"axis:{axis_fingerprint}"
    return StepPackageShapeResult(
        source_sha256=hashlib.sha256(STEP).hexdigest(),
        artifact_name=artifact_name,
        artifact_sha256=hashlib.sha256(artifact).hexdigest(),
        artifact_bytes=artifact,
        kernel_id="freecad-occ",
        kernel_version="7.8.1",
        freecad_version="1.1.3",
        shape_count=1,
        entity_count=2,
        entities=(
            {
                "native_persistent_id": axis_id,
                "kind": "axis",
                "fingerprint_sha256": axis_fingerprint,
                "support": {"surface_kind": None, "curve_kind": None, "axis_native_persistent_id": None},
                "geometry": {"contract": "spike/package-shape-selector-geometry/v1", "coordinate_space": "shape_local_mm", "representation": "axis", "origin_mm": [0, 0, 0], "direction": [0, 0, 1], "radius_mm": None},
            },
            {
                "native_persistent_id": f"face:{face_fingerprint}:0",
                "kind": "face",
                "fingerprint_sha256": face_fingerprint,
                "support": {"surface_kind": "cylinder", "curve_kind": None, "axis_native_persistent_id": axis_id},
                "geometry": {"contract": "spike/package-shape-selector-geometry/v1", "coordinate_space": "shape_local_mm", "representation": "unsupported", "origin_mm": None, "direction": None, "radius_mm": None},
            },
        ),
    )


class McadPackageShapeProjectTests(unittest.TestCase):
    def test_retained_step_extracts_transactionally_after_visual_tessellation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "assembly.spike"
            source_path = root / "case.step"
            source_path.write_bytes(STEP)
            design = DesignIRV2.from_v1(DesignIR(
                design_id="exact-shape", name="Exact shape", source_format="neutral",
                layers=[{"id": 0, "name": "F.Cu"}], metadata={"source_sha256": "5" * 64},
            ))
            write_spike_package(project_path, {"project": {"id": "exact"}, "design_ir": design.to_dict()})
            attached = handle_project_request(
                "attach_mcad_part_to_project",
                {"project_path": str(project_path), "source_path": str(source_path), "name": "Case"},
                request_id="attach", application_version="test",
            )
            self.assertTrue(attached["ok"], attached)
            part_id = attached["result"]["part"]["id"]
            source_model_id = attached["result"]["model"]["id"]
            visual = _glb_bytes()
            visual_result = StepTessellationResult(
                source_sha256=hashlib.sha256(STEP).hexdigest(), artifact_name="case-visual.glb",
                artifact_sha256=hashlib.sha256(visual).hexdigest(), artifact_bytes=visual,
                freecad_version="1.1.3", shape_count=1, vertex_count=8, triangle_count=12,
                linear_deflection_mm=0.1,
            )
            with patch("python.spike_core.service_project_handlers.tessellate_step_to_glb", return_value=visual_result):
                tessellated = handle_project_request(
                    "tessellate_mcad_part_in_project",
                    {
                        "project_path": str(project_path), "part_id": part_id,
                        "expected_manifest_payload_sha256": attached["result"]["manifest"]["manifest_payload_sha256"],
                    },
                    request_id="tessellate", application_version="test",
                )
            self.assertTrue(tessellated["ok"], tessellated)

            artifact_a = b"DBRep_DrawableShape\nCASCADE Topology V3\nexact-a"
            first_outcome = _shape_result("case-exact-a.spkshape", artifact_a)
            expected = tessellated["result"]["manifest"]["manifest_payload_sha256"]
            with patch("python.spike_core.service_project_handlers.extract_step_package_shape", return_value=first_outcome):
                extracted = handle_project_request(
                    "extract_mcad_package_shape_in_project",
                    {
                        "project_path": str(project_path), "part_id": part_id,
                        "expected_manifest_payload_sha256": expected,
                    },
                    request_id="extract", application_version="test",
                )
            self.assertTrue(extracted["ok"], extracted)
            self.assertEqual(extracted["result"]["source_model_id"], source_model_id)
            self.assertTrue(extracted["result"]["topology_ready"])
            self.assertFalse(extracted["result"]["solver_ready"])

            opened = read_project(project_path, include_members=True)
            shape = opened.payload["assembly_package_shapes"]["shapes"][0]
            expected_shape_id = canonical_uuid(
                "step", hashlib.sha256(STEP).hexdigest(), "package-shape", source_model_id,
            )
            self.assertEqual(shape["shape_id"], expected_shape_id)
            self.assertEqual(shape["source_model_id"], source_model_id)
            self.assertEqual(opened.members["geometry/package-shapes/case-exact-a.spkshape"], artifact_a)
            self.assertEqual(opened.payload["audit"][-1]["event"], "mcad_package_shape_extracted")

            with patch("python.spike_core.service_project_handlers.extract_step_package_shape", return_value=first_outcome):
                stale = handle_project_request(
                    "extract_mcad_package_shape_in_project",
                    {
                        "project_path": str(project_path), "part_id": part_id,
                        "expected_manifest_payload_sha256": expected,
                    },
                    request_id="stale", application_version="test",
                )
            self.assertFalse(stale["ok"])
            self.assertIn("changed since it was verified", str(stale))

            artifact_b = b"DBRep_DrawableShape\nCASCADE Topology V3\nexact-b"
            second_outcome = _shape_result("case-exact-b.spkshape", artifact_b)
            with patch("python.spike_core.service_project_handlers.extract_step_package_shape", return_value=second_outcome):
                replaced = handle_project_request(
                    "extract_mcad_package_shape_in_project",
                    {
                        "project_path": str(project_path), "part_id": part_id,
                        "expected_manifest_payload_sha256": opened.manifest["manifest_payload_sha256"],
                    },
                    request_id="replace", application_version="test",
                )
            self.assertTrue(replaced["ok"], replaced)
            reopened = read_project(project_path, include_members=True)
            self.assertNotIn("geometry/package-shapes/case-exact-a.spkshape", reopened.members)
            self.assertEqual(reopened.members["geometry/package-shapes/case-exact-b.spkshape"], artifact_b)
            self.assertEqual(len(reopened.payload["assembly_package_shapes"]["shapes"]), 1)


if __name__ == "__main__":
    unittest.main()
