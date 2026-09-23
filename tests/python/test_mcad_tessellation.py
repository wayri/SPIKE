import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.mcad_tessellation import (
    McadTessellationError,
    StepTessellationPolicy,
    tessellate_step_to_glb,
)


STEP_BYTES = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


def glb_bytes() -> bytes:
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": []}],
    }
    body = json.dumps(document, separators=(",", ":")).encode("utf-8")
    body += b" " * ((-len(body)) % 4)
    return struct.pack("<4sII", b"glTF", 2, 20 + len(body)) + struct.pack("<II", len(body), 0x4E4F534A) + body


class McadTessellationTests(unittest.TestCase):
    def test_policy_rejects_unbounded_requests(self):
        with self.assertRaises(ValueError):
            StepTessellationPolicy(timeout_s=301)
        with self.assertRaises(ValueError):
            StepTessellationPolicy(max_triangles=5_000_001)
        with self.assertRaises(ValueError):
            StepTessellationPolicy(linear_deflection_mm=float("nan"))

    def test_invalid_step_fails_before_process_dispatch(self):
        with self.assertRaisesRegex(McadTessellationError, "ISO-10303-21"):
            tessellate_step_to_glb(b"not step")

    def test_validated_visual_only_result_uses_fixed_temp_paths(self):
        artifact = glb_bytes()

        def fake_run(command, **kwargs):
            source = kwargs["cwd"] / "source.step"
            output = kwargs["cwd"] / "output.glb"
            report = kwargs["cwd"] / "report.json"
            self.assertEqual(source.parent, output.parent)
            self.assertEqual(output.name, "output.glb")
            self.assertEqual(report.name, "report.json")
            self.assertEqual(source.read_bytes(), STEP_BYTES)
            self.assertEqual(kwargs["timeout_s"], 300)
            self.assertEqual(kwargs["memory_limit_mb"], 2048)
            self.assertIn(b"scope['convert']", kwargs["stdin_payload"])
            output.write_bytes(artifact)
            report.write_text(json.dumps({
                "contract": "spike/freecad-step-tessellation-report/v1",
                "freecad_version": "1.1.0", "shape_count": 1,
                "vertex_count": 8, "triangle_count": 12,
                "visual_only": True, "solver_ready": False,
            }), encoding="utf-8")
            return {"return_code": 0, "stdout": "", "stderr": "", "memory_limit_enforced": True}

        with patch("python.spike_core.mcad_tessellation._freecad_path", return_value=Path(__file__)), patch(
            "python.spike_core.mcad_tessellation.run_adapter_process", side_effect=fake_run
        ):
            result = tessellate_step_to_glb(STEP_BYTES, source_name="housing.step")
        self.assertEqual(result.contract, "spike/mcad-step-tessellation/v1")
        self.assertTrue(result.visual_only)
        self.assertFalse(result.solver_ready)
        self.assertEqual(result.triangle_count, 12)
        self.assertRegex(result.artifact_name, r"^housing-[0-9a-f]{12}-[0-9a-f]{12}\.glb$")

    def test_nonzero_or_unqualified_report_fails_closed(self):
        with patch("python.spike_core.mcad_tessellation._freecad_path", return_value=Path(__file__)), patch(
            "python.spike_core.mcad_tessellation.run_adapter_process",
            return_value={"return_code": 2, "stdout": "", "stderr": "converter rejected shape"},
        ):
            with self.assertRaisesRegex(McadTessellationError, "converter rejected shape"):
                tessellate_step_to_glb(STEP_BYTES)


if __name__ == "__main__":
    unittest.main()
