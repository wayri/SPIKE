"""Installed FreeCAD/OCC smoke for exact STEP package-shape extraction."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
import struct
from pathlib import Path

from python.spike_core.dependencies import dependency_status
from python.spike_core.mcad_package_shape import extract_step_package_shape
from python.spike_core.mcad_selector_preview import generate_selector_preview
from python.spike_core.mcad_tessellation import tessellate_step_to_glb
from python.spike_core.design_ir_v2_schema import canonical_uuid


def _freecad_executable() -> Path | None:
    record = next(
        (item for item in dependency_status()["dependencies"] if item.get("id") == "freecad"),
        {},
    )
    path = Path(str(record.get("path", "")))
    return path if record.get("status") == "ready" and path.is_file() else None


class McadPackageShapeFreeCadTests(unittest.TestCase):
    def test_installed_kernel_produces_repeatable_exact_box_topology(self):
        executable = _freecad_executable()
        if executable is None:
            self.skipTest("The optional locked FreeCAD runtime is unavailable.")
        with tempfile.TemporaryDirectory(prefix="spike-freecad-exact-smoke-") as directory:
            root = Path(directory)
            script = root / "make_box.py"
            source = root / "box.step"
            script.write_text(
                "import FreeCAD as App\n"
                "import Part\n"
                "from pathlib import Path\n"
                "document=App.newDocument('SPIKE_BOX_FIXTURE')\n"
                "feature=document.addObject('Part::Feature','Box')\n"
                "feature.Shape=Part.makeBox(10.0,20.0,30.0)\n"
                "feature.Placement.Base=App.Vector(23.0,40.0,50.0)\n"
                "document.recompute()\n"
                "Part.export([feature],str(Path(__file__).with_name('box.step')))\n"
                "App.closeDocument(document.Name)\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    str(executable), "--console",
                    "--user-cfg", str(root / "user.cfg"),
                    "--system-cfg", str(root / "system.cfg"),
                    str(script),
                ],
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", "replace")[-2000:])
            payload = source.read_bytes()
            first = extract_step_package_shape(payload, source_name="box.step", freecad_executable=executable)
            second = extract_step_package_shape(payload, source_name="box.step", freecad_executable=executable)
            self.assertEqual(first.freecad_version, "1.1.3")
            self.assertEqual(first.kernel_version, "7.8.1")
            self.assertEqual(first.artifact_sha256, second.artifact_sha256)
            self.assertEqual(first.entities, second.entities)
            self.assertGreaterEqual(sum(item["kind"] == "solid" for item in first.entities), 1)
            self.assertGreaterEqual(sum(item["kind"] == "face" for item in first.entities), 6)
            self.assertTrue(first.topology_ready)
            self.assertFalse(first.solver_ready)
            vertices = [item["geometry"]["origin_mm"] for item in first.entities if item["kind"] == "vertex"]
            self.assertEqual(len(vertices), 8)
            self.assertEqual({tuple(point) for point in vertices}, {
                (23.0, 40.0, 50.0), (33.0, 40.0, 50.0),
                (23.0, 60.0, 50.0), (33.0, 60.0, 50.0),
                (23.0, 40.0, 80.0), (33.0, 40.0, 80.0),
                (23.0, 60.0, 80.0), (33.0, 60.0, 80.0),
            })
            planes = [item["geometry"] for item in first.entities if item["kind"] == "face" and item["geometry"]["representation"] == "plane"]
            self.assertEqual(len(planes), 6)
            self.assertTrue(all(abs(sum(value * value for value in plane["direction"]) - 1.0) < 1e-12 for plane in planes))
            topology_ids = {
                (item["kind"], item["native_persistent_id"]): canonical_uuid(
                    "step", first.source_sha256, item["kind"], item["native_persistent_id"],
                )
                for item in first.entities
            }
            canonical_entities = [{
                "topology_id": topology_ids[(item["kind"], item["native_persistent_id"])],
                "kind": item["kind"],
                "native_persistent_id": item["native_persistent_id"],
                "fingerprint_sha256": item["fingerprint_sha256"],
                "support": {
                    "surface_kind": item["support"]["surface_kind"],
                    "curve_kind": item["support"]["curve_kind"],
                    "axis_topology_id": topology_ids.get(("axis", item["support"]["axis_native_persistent_id"])),
                },
                "geometry": item["geometry"],
            } for item in first.entities]
            preview = generate_selector_preview(
                first.artifact_bytes, shape_id="box-shape", source_sha256=first.source_sha256,
                entities=canonical_entities, freecad_executable=executable,
            )
            repeated_preview = generate_selector_preview(
                first.artifact_bytes, shape_id="box-shape", source_sha256=first.source_sha256,
                entities=canonical_entities, freecad_executable=executable,
            )
            self.assertEqual(preview.artifact_sha256, repeated_preview.artifact_sha256)
            self.assertGreaterEqual(preview.face_count, 6)
            self.assertGreaterEqual(preview.edge_count, 12)
            self.assertTrue(preview.visual_only)
            self.assertFalse(preview.solver_ready)
            visual = tessellate_step_to_glb(payload, source_name="box.step", freecad_executable=executable)
            json_length = struct.unpack_from("<I", visual.artifact_bytes, 12)[0]
            document = json.loads(visual.artifact_bytes[20:20 + json_length].decode("utf-8"))
            bounds = document["accessors"][0]
            for actual, expected in zip(bounds["min"], [0.023, 0.04, 0.05]):
                self.assertAlmostEqual(actual, expected, places=8)
            for actual, expected in zip(bounds["max"], [0.033, 0.06, 0.08]):
                self.assertAlmostEqual(actual, expected, places=8)


if __name__ == "__main__":
    unittest.main()
