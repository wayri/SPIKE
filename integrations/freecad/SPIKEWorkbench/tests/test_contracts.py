"""Tests that run with stock Python; FreeCAD is not required."""

import json
import runpy
import sys
import tempfile
import types
import unittest
from pathlib import Path


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKBENCH_ROOT))

from spike_freecad.constants import GEOMETRY_CONTRACT, MECHANICAL_CONTRACT  # noqa: E402
from spike_freecad.contracts import (  # noqa: E402
    ContractError,
    load_geometry_exchange,
    load_mechanical_exchange,
    validate_geometry_exchange,
    validate_mechanical_exchange,
    write_mechanical_exchange,
)


class GeometryContractTests(unittest.TestCase):
    def setUp(self):
        self.example_path = WORKBENCH_ROOT / "examples" / "example-geometry-exchange.json"
        self.example = json.loads(self.example_path.read_text(encoding="utf-8"))

    def test_example_geometry_is_valid(self):
        parsed = load_geometry_exchange(self.example_path)
        self.assertEqual(parsed["contract"], GEOMETRY_CONTRACT)
        self.assertEqual(len(parsed["objects"]), 4)

    def test_wrong_version_is_rejected(self):
        self.example["schema_version"] = 2
        with self.assertRaisesRegex(ContractError, "only schema version 1"):
            validate_geometry_exchange(self.example)

    def test_unknown_field_is_rejected(self):
        self.example["execute"] = "anything"
        with self.assertRaisesRegex(ContractError, "unsupported keys: execute"):
            validate_geometry_exchange(self.example)

    def test_unknown_primitive_is_rejected(self):
        self.example["objects"][0]["primitive"] = {
            "type": "python",
            "source": "print('must never run')",
        }
        with self.assertRaisesRegex(ContractError, "unsupported primitive"):
            validate_geometry_exchange(self.example)

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text(
                '{"contract":"one","contract":"two"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ContractError, "duplicate JSON key"):
                load_geometry_exchange(path)


class MechanicalContractTests(unittest.TestCase):
    def _payload(self):
        return {
            "contract": MECHANICAL_CONTRACT,
            "schema_version": 1,
            "units": "mm",
            "coordinate_system": {
                "handedness": "right",
                "up_axis": "Z",
                "origin": [0.0, 0.0, 0.0],
            },
            "generator": {
                "name": "contract test",
                "version": "1",
                "freecad_version": "not-required",
            },
            "generated_at": "2026-08-09T00:00:00Z",
            "source_document": {"name": "Doc", "label": "Document"},
            "objects": [
                {
                    "id": "freecad/Box",
                    "name": "Box",
                    "role": "keepout",
                    "representation": "axis_aligned_bounding_box",
                    "primitive": {
                        "type": "box",
                        "origin": [1.0, 2.0, 3.0],
                        "size": [4.0, 5.0, 6.0],
                    },
                    "source": {
                        "freecad_name": "Box",
                        "freecad_type_id": "Part::Feature",
                    },
                    "metadata": {"purpose": "clearance"},
                }
            ],
        }

    def test_mechanical_exchange_round_trip(self):
        payload = self._payload()
        validate_mechanical_exchange(payload)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "mechanical.json"
            written = write_mechanical_exchange(destination, payload)
            loaded = load_mechanical_exchange(written)
        self.assertEqual(loaded["objects"][0]["role"], "keepout")

    def test_non_aabb_representation_is_rejected(self):
        payload = self._payload()
        payload["objects"][0]["representation"] = "exact_brep"
        with self.assertRaisesRegex(ContractError, "axis_aligned_bounding_box"):
            validate_mechanical_exchange(payload)


class WorkbenchLoaderTests(unittest.TestCase):
    def test_init_gui_registers_an_external_workbench(self):
        class FakeWorkbench:
            pass

        fake_gui = types.ModuleType("FreeCADGui")
        fake_gui.registered = []
        fake_gui.addWorkbench = fake_gui.registered.append
        previous = sys.modules.get("FreeCADGui")
        sys.modules["FreeCADGui"] = fake_gui
        try:
            runpy.run_path(
                str(WORKBENCH_ROOT / "InitGui.py"),
                init_globals={"Workbench": FakeWorkbench},
            )
        finally:
            if previous is None:
                del sys.modules["FreeCADGui"]
            else:
                sys.modules["FreeCADGui"] = previous
        self.assertEqual(len(fake_gui.registered), 1)
        self.assertEqual(fake_gui.registered[0].MenuText, "SPIKE ECAD/MCAD")
        self.assertEqual(fake_gui.registered[0].GetClassName(), "Gui::PythonWorkbench")


if __name__ == "__main__":
    unittest.main()
