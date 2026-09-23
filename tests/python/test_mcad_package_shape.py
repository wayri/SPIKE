"""Bounded exact STEP package-shape adapter regressions."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.mcad_package_shape import (
    McadPackageShapeError,
    StepPackageShapePolicy,
    extract_step_package_shape,
)


STEP = b"ISO-10303-21;\nHEADER;ENDSEC;DATA;ENDSEC;END-ISO-10303-21;\n"
BREP = b"DBRep_DrawableShape\nCASCADE Topology V3, (c) Open Cascade\nfixture"


class McadPackageShapeTests(unittest.TestCase):
    def test_policy_and_step_envelope_fail_before_dispatch(self):
        with self.assertRaises(ValueError):
            StepPackageShapePolicy(max_entities=500_001)
        with self.assertRaises(ValueError):
            StepPackageShapePolicy(timeout_s=301)
        with self.assertRaisesRegex(McadPackageShapeError, "ISO-10303-21"):
            extract_step_package_shape(b"not step")

    def test_exact_brep_and_selector_inventory_are_independently_checked(self):
        axis_fingerprint = hashlib.sha256(b"axis").hexdigest()
        face_fingerprint = hashlib.sha256(b"face").hexdigest()

        def fake_run(command, **kwargs):
            output = kwargs["cwd"] / "output.spkshape"
            report = kwargs["cwd"] / "report.json"
            self.assertEqual((kwargs["cwd"] / "source.step").read_bytes(), STEP)
            self.assertEqual(kwargs["memory_limit_mb"], 4096)
            self.assertIn(b"scope['extract']", kwargs["stdin_payload"])
            output.write_bytes(BREP)
            report.write_text(json.dumps({
                "contract": "spike/freecad-step-package-shape-report/v2",
                "source_sha256": hashlib.sha256(STEP).hexdigest(),
                "artifact_sha256": hashlib.sha256(BREP).hexdigest(),
                "kernel_id": "freecad-occ", "kernel_version": "7.8.1", "freecad_version": "1.1.3",
                "shape_count": 1, "entity_count": 2,
                "entities": [
                    {"native_persistent_id": f"axis:{axis_fingerprint}", "kind": "axis", "fingerprint_sha256": axis_fingerprint, "support": {"surface_kind": None, "curve_kind": None, "axis_native_persistent_id": None}, "geometry": {"contract": "spike/package-shape-selector-geometry/v1", "coordinate_space": "shape_local_mm", "representation": "axis", "origin_mm": [0, 0, 0], "direction": [0, 0, 1], "radius_mm": None}},
                    {"native_persistent_id": f"face:{face_fingerprint}:0", "kind": "face", "fingerprint_sha256": face_fingerprint, "support": {"surface_kind": "cylinder", "curve_kind": None, "axis_native_persistent_id": f"axis:{axis_fingerprint}"}, "geometry": {"contract": "spike/package-shape-selector-geometry/v1", "coordinate_space": "shape_local_mm", "representation": "unsupported", "origin_mm": None, "direction": None, "radius_mm": None}},
                ],
                "topology_ready": True, "solver_ready": False,
            }), encoding="utf-8")
            return {"return_code": 0, "stdout": "", "stderr": "", "memory_limit_enforced": True}

        with patch("python.spike_core.mcad_package_shape._freecad_path", return_value=Path(__file__)), patch(
            "python.spike_core.mcad_package_shape.run_adapter_process", side_effect=fake_run,
        ):
            result = extract_step_package_shape(STEP, source_name="housing.step")
        self.assertTrue(result.topology_ready)
        self.assertFalse(result.solver_ready)
        self.assertEqual(result.kernel_version, "7.8.1")
        self.assertEqual(result.entity_count, 2)
        self.assertEqual(result.entities[0]["geometry"]["representation"], "axis")
        self.assertRegex(result.artifact_name, r"^housing-[0-9a-f]{12}-[0-9a-f]{12}\.spkshape$")

    def test_bad_brep_or_digest_identity_fails_closed(self):
        def fake_run(command, **kwargs):
            (kwargs["cwd"] / "output.spkshape").write_bytes(b"not brep")
            (kwargs["cwd"] / "report.json").write_text("{}", encoding="utf-8")
            return {"return_code": 0, "stdout": "", "stderr": ""}

        with patch("python.spike_core.mcad_package_shape._freecad_path", return_value=Path(__file__)), patch(
            "python.spike_core.mcad_package_shape.run_adapter_process", side_effect=fake_run,
        ):
            with self.assertRaisesRegex(McadPackageShapeError, "Open CASCADE BREP"):
                extract_step_package_shape(STEP)

    def test_geometry_descriptor_validation_fails_closed(self):
        from python.spike_core.package_shape_geometry import PackageShapeGeometryError, canonicalize_selector_geometry

        valid = {"contract": "spike/package-shape-selector-geometry/v1", "coordinate_space": "shape_local_mm", "representation": "line", "origin_mm": [1, 2, 3], "direction": [1, 0, 0], "radius_mm": None}
        self.assertEqual(canonicalize_selector_geometry(valid, "edge", "edge")["origin_mm"], [1.0, 2.0, 3.0])
        for invalid in ({**valid, "direction": [2, 0, 0]}, {**valid, "origin_mm": [float("nan"), 0, 0]}, {**valid, "representation": "circle"}, {**valid, "extra": None}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(PackageShapeGeometryError):
                    canonicalize_selector_geometry(invalid, "edge", "edge")


if __name__ == "__main__":
    unittest.main()
