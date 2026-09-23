import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.mcad_tessellation import StepTessellationResult
from python.spike_core.project_package import read_project, read_visual_model_artifacts, write_spike_package
from python.spike_core.service_project_handlers import handle_project_request


def glb_bytes() -> bytes:
    document = {"asset": {"version": "2.0"}, "scenes": [{}]}
    body = json.dumps(document, separators=(",", ":")).encode("utf-8")
    body += b" " * ((-len(body)) % 4)
    return struct.pack("<4sII", b"glTF", 2, 20 + len(body)) + struct.pack("<II", len(body), 0x4E4F534A) + body


class McadTessellationProjectTests(unittest.TestCase):
    def test_tessellation_retains_step_and_switches_only_part_visual_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "assembly.spike"
            source_path = root / "case.step"
            source = b"ISO-10303-21;\nHEADER;ENDSEC;DATA;ENDSEC;END-ISO-10303-21;\n"
            source_path.write_bytes(source)
            design = DesignIRV2.from_v1(DesignIR(
                design_id="step-visual", name="STEP visual", source_format="neutral",
                layers=[{"id": 0, "name": "F.Cu"}], metadata={"source_sha256": "4" * 64},
            ))
            write_spike_package(project_path, {"project": {"id": "visual"}, "design_ir": design.to_dict()})
            attached = handle_project_request(
                "attach_mcad_part_to_project",
                {"project_path": str(project_path), "source_path": str(source_path), "name": "Case"},
                request_id="attach", application_version="test",
            )
            self.assertTrue(attached["ok"], attached)
            part = attached["result"]["part"]
            source_model_id = attached["result"]["model"]["id"]
            visual = glb_bytes()
            fake = StepTessellationResult(
                source_sha256=hashlib.sha256(source).hexdigest(), artifact_name="case-visual.glb",
                artifact_sha256=hashlib.sha256(visual).hexdigest(), artifact_bytes=visual,
                freecad_version="1.1.3", shape_count=1, vertex_count=8, triangle_count=12,
                linear_deflection_mm=0.1,
            )
            with patch("python.spike_core.service_project_handlers.tessellate_step_to_glb", return_value=fake):
                converted = handle_project_request(
                    "tessellate_mcad_part_in_project",
                    {
                        "project_path": str(project_path), "part_id": part["id"],
                        "expected_manifest_payload_sha256": attached["result"]["manifest"]["manifest_payload_sha256"],
                    },
                    request_id="tessellate", application_version="test",
                )
            self.assertTrue(converted["ok"], converted)
            opened = read_project(project_path, include_members=True)
            models = {model["id"]: model for model in opened.payload["models"]["models"]}
            reopened_part = opened.payload["assembly_ir"]["parts"][0]
            derived_model_id = converted["result"]["derived_model"]["id"]
            self.assertIn(source_model_id, models)
            self.assertEqual(models[source_model_id]["model_type"], "step")
            self.assertEqual(models[derived_model_id]["model_type"], "glb")
            self.assertEqual(reopened_part["id"], part["id"])
            self.assertEqual(reopened_part["frame"], part["frame"])
            self.assertEqual(reopened_part["model_id"], derived_model_id)
            self.assertFalse(reopened_part["extensions"]["spike.mcad.tessellation"]["solver_ready"])
            self.assertTrue(any(name.endswith(".step") for name in opened.members))
            self.assertEqual(opened.members["models/artifacts/case-visual.glb"], visual)
            served = read_visual_model_artifacts(
                project_path, [derived_model_id],
                expected_manifest_payload_sha256=opened.manifest["manifest_payload_sha256"],
            )
            self.assertEqual(served[0]["artifact"], visual)
            self.assertEqual(opened.payload["audit"][-1]["event"], "mcad_part_tessellated")


if __name__ == "__main__":
    unittest.main()
