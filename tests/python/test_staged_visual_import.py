"""Staged desktop import keeps large CAD output within the transport budget."""
import json
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.models import (
    _stage_resolved_model_references,
    export_kicad_visual_bundle_path_payload,
    model_library_roots,
)


def glb_bytes():
    document = json.dumps({"asset": {"version": "2.0"}, "scene": 0, "scenes": [{}]}).encode()
    document += b" " * (-len(document) % 4)
    return struct.pack("<4sII", b"glTF", 2, 20 + len(document)) + struct.pack("<II", len(document), 0x4E4F534A) + document


class StagedVisualImportTests(unittest.TestCase):
    def test_each_stage_returns_only_its_artifacts_and_large_boards_use_native_copper(self):
        with tempfile.TemporaryDirectory() as directory:
            board = Path(directory) / "dense.kicad_pcb"
            board.write_text('(kicad_pcb (layers (0 "F.Cu" signal) (31 "B.Cu" signal)))' + ' ' * (8 * 1024 * 1024))
            commands = []

            def run(command, **_kwargs):
                commands.append(command)
                output = Path(command[command.index("--output") + 1])
                if "svg" in command:
                    for layer in ("F_Cu", "B_Cu"):
                        (output / f"dense-{layer}.svg").write_text('<svg viewBox="0 0 40 20"/>')
                else:
                    output.write_bytes(glb_bytes())
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with patch("python.spike_core.models.kicad_scene_capabilities", return_value={"available": True, "path": "kicad-cli"}), \
                    patch("python.spike_core.models.subprocess.run", side_effect=run), \
                    patch("python.spike_core.models.model_library_roots", return_value=[]):
                for stage in ("layout", "board", "components"):
                    commands.clear()
                    result = export_kicad_visual_bundle_path_payload(board, stage=stage)
                    self.assertEqual(set(result["scenes"]), set() if stage == "layout" else {stage})
                    self.assertEqual(len(result["layout"]["layers"]), 2 if stage == "layout" else 0)
                    self.assertEqual(len(commands), 1)
                    self.assertLess(result["artifact_bytes"], 4096)
                    if stage == "board":
                        self.assertFalse(result["quality"]["board_includes_copper"])
                        self.assertFalse(any(flag.startswith("--include-") for flag in commands[0]))

    def test_one_explicit_model_override_repairs_all_instances_without_editing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "source.kicad_pcb"
            reference = "${KIPRJMOD}/missing.wrl"
            original = '(kicad_pcb ' + f'(model "{reference}") ' * 8 + '(model "absent.step"))'
            board.write_text(original)
            replacement = root / "chosen.wrl"
            replacement.write_text("#VRML V2.0 utf8")
            replacement.with_suffix(".step").write_text("another file that was not selected")
            resolution = {}
            with patch("python.spike_core.models.model_library_roots", return_value=[]):
                staged, substitutions = _stage_resolved_model_references(board, root / "out", {reference: str(replacement)}, resolution)
            self.assertEqual(len(substitutions), 8)
            self.assertEqual(staged.read_text().count(replacement.as_posix()), 8)
            self.assertEqual(resolution["unresolved_model_paths"], ["absent.step"])
            self.assertEqual(board.read_text(), original)

    def test_missing_selected_replacement_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "source.kicad_pcb"
            board.write_text('(kicad_pcb (model "missing.step"))')
            with patch("python.spike_core.models.model_library_roots", return_value=[]):
                with self.assertRaisesRegex(ValueError, "readable STEP or VRML"):
                    _stage_resolved_model_references(board, root / "out", {"missing.step": str(root / "gone.step")})

    def test_legacy_and_future_kicad_model_roots_are_not_version_limited(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "legacy"
            future = root / "future"
            legacy.mkdir()
            future.mkdir()
            with patch.dict("os.environ", {
                "KICAD3DMOD": str(legacy),
                "KICAD12_3DMODEL_DIR": str(future),
            }):
                roots = model_library_roots()
            self.assertIn(legacy.resolve(), roots)
            self.assertIn(future.resolve(), roots)

    def test_legacy_kicad3dmod_reference_keeps_component_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "legacy"
            model = library / "Package.3dshapes" / "part.step"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"STEP")
            board = root / "fixture.kicad_pcb"
            board.write_text(
                '(kicad_pcb (footprint "Package" (at 12.5 7.25 90) '
                '(model "${KICAD3DMOD}/Package.3dshapes/part.step" '
                '(offset (xyz 1 2 3)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 45)))))'
            )
            with patch.dict("os.environ", {"KICAD3DMOD": str(library)}), patch(
                "python.spike_core.models.model_library_roots", return_value=[library]
            ):
                staged, substitutions = _stage_resolved_model_references(board, root / "output")
            source = staged.read_text()
            self.assertEqual(len(substitutions), 1)
            self.assertIn(model.as_posix(), source)
            self.assertIn('(at 12.5 7.25 90)', source)
            self.assertIn('(offset (xyz 1 2 3))', source)
            self.assertIn('(rotate (xyz 0 0 45))', source)
