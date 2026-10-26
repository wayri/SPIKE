# SPDX-License-Identifier: Apache-2.0
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.models import _stage_resolved_model_references, automatic_component_model_overrides


class ModelResolverStagingTests(unittest.TestCase):
    def test_exact_unassigned_footprint_gets_visual_only_identity_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "source.kicad_pcb"
            model = root / "Package_SO.3dshapes" / "SOIC-8.step"
            model.parent.mkdir()
            model.write_bytes(b"STEP")
            original = '(kicad_pcb (footprint "Package_SO:SOIC-8" (property "Reference" "U1") (at 4 5 90)))'
            board.write_text(original)
            resolved = {"status": "resolved_exact", "automatic_path": str(model), "candidates": []}
            with patch("python.spike_core.model_resolver_staging.resolve_model", return_value=resolved), patch(
                "python.spike_core.models.model_library_roots", return_value=[root]
            ):
                staged, substitutions = _stage_resolved_model_references(board, root / "out")
            source = staged.read_text()
            self.assertIn('(at 4 5 90)', source)
            self.assertIn('(offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0))', source)
            self.assertEqual(substitutions[0]["origin"], "local_fallback")
            self.assertEqual(substitutions[0]["visual_only"], "true")
            self.assertEqual(board.read_text(), original)

    def test_component_override_is_scoped_and_preserves_every_model_transform(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "source.kicad_pcb"
            replacement = root / "chosen.step"
            replacement.write_bytes(b"STEP")
            board.write_text(
                '(kicad_pcb '
                '(footprint "A:One" (property "Reference" "U1") '
                '(model "old-a.step" (offset (xyz 1 2 3)) (rotate (xyz 4 5 6))) '
                '(model "old-b.step" (scale (xyz 2 2 2)))) '
                '(footprint "A:Two" (property "Reference" "U2") (model "keep.step")))'
            )
            unresolved = {"status": "candidates", "automatic_path": None, "candidates": []}
            with patch("python.spike_core.model_resolver_staging.resolve_model", return_value=unresolved), patch(
                "python.spike_core.models.model_library_roots", return_value=[]
            ):
                staged, substitutions = _stage_resolved_model_references(
                    board, root / "out", component_model_overrides={"U1": str(replacement)}
                )
            source = staged.read_text()
            self.assertEqual(source.count(replacement.as_posix()), 2)
            self.assertIn('(offset (xyz 1 2 3)) (rotate (xyz 4 5 6))', source)
            self.assertIn('(scale (xyz 2 2 2))', source)
            self.assertIn('(model "keep.step")', source)
            self.assertEqual({item["component_reference"] for item in substitutions}, {"U1"})

    def test_existing_and_embedded_assignments_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / "local.step"
            local.write_bytes(b"STEP")
            board = root / "source.kicad_pcb"
            source = (
                '(kicad_pcb (footprint "A:One" (property "Reference" "U1") '
                '(model "${KIPRJMOD}/local.step") (model "kicad-embed://token")))'
            )
            board.write_text(source)
            with patch("python.spike_core.models.model_library_roots", return_value=[]), patch(
                "python.spike_core.model_resolver_staging.resolve_model"
            ) as resolve:
                staged, substitutions = _stage_resolved_model_references(board, root / "out")
            self.assertEqual(staged, board)
            self.assertEqual(substitutions, [])
            resolve.assert_not_called()

    def test_automatic_override_scan_ignores_assigned_and_unresolved_footprints(self):
        source = (
            '(kicad_pcb '
            '(footprint "Std:Exact" (property "Reference" "U1")) '
            '(footprint "Eagle:Odd" (property "Reference" "U2")) '
            '(footprint "Std:Assigned" (property "Reference" "U3") (model "kept.step")))'
        )
        responses = iter([
            {"status": "resolved_exact", "automatic_path": "C:/models/exact.step", "candidates": []},
            {"status": "candidates", "automatic_path": None, "candidates": [{"path": "C:/models/guess.step"}]},
        ])
        with patch("python.spike_core.model_resolver_staging.resolve_model", side_effect=responses):
            result = automatic_component_model_overrides(source)
        self.assertEqual(result, {"U1": "C:/models/exact.step"})

    def test_invalid_and_oversized_overrides_fail_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "source.kicad_pcb"
            board.write_text('(kicad_pcb (footprint "A:One" (property "Reference" "U1")))')
            invalid = root / "model.txt"
            invalid.write_text("no")
            with self.assertRaisesRegex(ValueError, "readable STEP or VRML"):
                _stage_resolved_model_references(board, root / "out", component_model_overrides={"U1": str(invalid)})
            large = root / "large.step"
            with large.open("wb") as stream:
                stream.truncate(64 * 1024 * 1024 + 1)
            with self.assertRaisesRegex(ValueError, "byte visual-export limit"):
                _stage_resolved_model_references(board, root / "out", component_model_overrides={"U1": str(large)})


if __name__ == "__main__":
    unittest.main()
