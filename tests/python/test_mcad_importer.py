from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from python.spike_core.importers import ImportPolicy
from python.spike_core.mcad_importer import McadImportError, import_mcad_artifact


def glb_bytes(document: dict) -> bytes:
    payload = json.dumps(document, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    length = 12 + 8 + len(payload)
    return struct.pack("<4sII", b"glTF", 2, length) + struct.pack("<II", len(payload), 0x4E4F534A) + payload


class McadImporterTests(unittest.TestCase):
    def test_step_import_is_deterministic_and_explicit_about_tessellation(self):
        step = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.step"
            path.write_bytes(step)
            first = import_mcad_artifact(path)
            second = import_mcad_artifact(path)

        self.assertEqual(first.part.id, second.part.id)
        self.assertEqual(first.model.id, second.model.id)
        self.assertEqual(first.artifact_bytes, step)
        self.assertEqual(first.report.solver_readiness["assembly_visualization"]["state"], "requires_tessellation")
        self.assertEqual(first.report.solver_readiness["multiphysics"]["state"], "unsupported")
        self.assertTrue(first.model.uri.startswith("package:models/artifacts/"))

    def test_embedded_gltf_and_valid_glb_are_accepted(self):
        document = {
            "asset": {"version": "2.0", "generator": "fixture"},
            "buffers": [{"uri": "data:application/octet-stream;base64,AA==", "byteLength": 1}],
            "scenes": [{}],
            "nodes": [{}],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gltf = root / "part.gltf"
            glb = root / "part.glb"
            gltf.write_text(json.dumps(document), encoding="utf-8")
            glb.write_bytes(glb_bytes(document))
            gltf_outcome = import_mcad_artifact(gltf)
            glb_outcome = import_mcad_artifact(glb)

        self.assertEqual(gltf_outcome.report.source_format, "gltf")
        self.assertEqual(glb_outcome.report.source_format, "glb")
        self.assertEqual(gltf_outcome.report.solver_readiness["assembly_visualization"]["state"], "available")

    def test_external_gltf_resources_and_invalid_glb_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gltf = root / "external.gltf"
            gltf.write_text(json.dumps({
                "asset": {"version": "2.0"},
                "buffers": [{"uri": "../outside.bin", "byteLength": 4}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(McadImportError, "external resources"):
                import_mcad_artifact(gltf)
            invalid = root / "invalid.glb"
            invalid.write_bytes(b"glTF" + b"\x00" * 20)
            with self.assertRaisesRegex(McadImportError, "header, version, or declared length"):
                import_mcad_artifact(invalid)

    def test_unsupported_empty_and_over_budget_sources_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unsupported = root / "model.obj"
            unsupported.write_text("o fixture", encoding="ascii")
            with self.assertRaisesRegex(McadImportError, "Supported MCAD"):
                import_mcad_artifact(unsupported)
            empty = root / "empty.step"
            empty.write_bytes(b"")
            with self.assertRaisesRegex(McadImportError, "empty"):
                import_mcad_artifact(empty)
            large = root / "large.step"
            large.write_bytes(b"ISO-10303-21;END-ISO-10303-21;")
            with self.assertRaisesRegex(McadImportError, "configured limit"):
                import_mcad_artifact(large, policy=ImportPolicy(max_source_bytes=8))


if __name__ == "__main__":
    unittest.main()
