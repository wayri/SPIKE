import json
import hashlib
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path

from python.spike_core.assembly_exchange import import_exchange, read_exchange
from python.spike_core.assembly_frames import IDENTITY, resolve_world
from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import AssemblyIRV1, DesignIRV2
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.service_project_handlers import handle_project_request


def design():
    return DesignIRV2.from_v1(DesignIR(design_id="board", name="Board", source_format="neutral", layers=[{"id": 0, "name": "F.Cu"}], metadata={"source_sha256": "a" * 64})).to_dict()


def bundle(path, *, bad_parent=False):
    transform = list(IDENTITY)
    transform[3] = 2
    manifest = {"contract": "spike/assembly-exchange/v1", "name": "External", "units": "inch", "source_cad": "fixture", "occurrences": [
        {"id": "group", "kind": "group", "transform": transform},
        {"id": "board", "kind": "board", "parent_id": "missing" if bad_parent else "group", "asset": "board.json"},
        {"id": "base", "kind": "part", "parent_id": "group", "asset": "base.step"},
        {"id": "lid", "kind": "part", "parent_id": "group", "asset": "base.step", "transform": transform},
    ]}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("assembly.json", json.dumps(manifest))
        z.writestr("board.json", json.dumps(design()))
        z.writestr("base.step", "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;")


class AssemblyExchangeTests(unittest.TestCase):
    def test_units_hierarchy_repeated_part_instances_and_original_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "assembly.spikeassembly"
            bundle(path)
            result = import_exchange(path)
            assembly = AssemblyIRV1.from_dict(result["assembly"])
            self.assertEqual(len(assembly.boards), 1)
            self.assertEqual(len(assembly.parts), 3)
            self.assertEqual(len(result["models"]), 1)
            base, lid = assembly.parts[1:]
            self.assertNotEqual(base.id, lid.id)
            self.assertEqual(base.model_id, lid.model_id)
            self.assertAlmostEqual(resolve_world(assembly, base.frame)[3], 50.8)
            self.assertAlmostEqual(resolve_world(assembly, lid.frame)[3], 101.6)
            self.assertEqual(result["assembly"], import_exchange(path)["assembly"])
            self.assertTrue(next(iter(result["model_artifacts"].values())).startswith(b"ISO-10303-21"))

    def test_import_roundtrip_and_stale_manifest_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            source, project = Path(d) / "assembly.spikeassembly", Path(d) / "project.spike"
            bundle(source)
            initial = write_spike_package(project, {"project": {"id": "p", "name": "P"}, "design_ir": design()})
            original_design = read_project(project).payload["design_ir"]
            params = {"project_path": str(project), "source_path": str(source), "expected_manifest_payload_sha256": initial["manifest_payload_sha256"]}
            response = handle_project_request("import_into_assembly_project", params, request_id=1, application_version="test")
            self.assertTrue(response["ok"], response)
            loaded = read_project(project, include_members=True)
            self.assertEqual(len(loaded.payload["assembly_ir"]["boards"]), 2)
            self.assertEqual(len(loaded.payload["assembly_ir"]["parts"]), 3)
            self.assertEqual(loaded.payload["design_ir"], original_design)
            self.assertTrue(any(n.startswith("models/artifacts/") for n in loaded.members))
            before = project.read_bytes()
            rejected = handle_project_request("import_into_assembly_project", params, request_id=2, application_version="test")
            self.assertFalse(rejected["ok"])
            self.assertEqual(project.read_bytes(), before)

    def test_invalid_hierarchy_and_archive_paths(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "bad.spikeassembly"
            bundle(source, bad_parent=True)
            with self.assertRaisesRegex(ValueError, "unknown parent"): import_exchange(source)
            with zipfile.ZipFile(source, "w") as z:
                z.writestr("../host.step", "bad")
            with self.assertRaisesRegex(ValueError, "unsafe"): read_exchange(source)

    def test_native_board_import_retains_electrical_design_and_source(self):
        with tempfile.TemporaryDirectory() as d:
            source, project = Path(d) / "extra.kicad_pcb", Path(d) / "project.spike"
            source.write_text('(kicad_pcb (version 20240108) (generator pcbnew) (general (thickness 1.6)) (layers (0 "F.Cu" signal) (31 "B.Cu" signal)) (net 0 "") (net 1 "VCC"))', encoding="utf-8")
            initial = write_spike_package(project, {"project": {"id": "p", "name": "P"}, "design_ir": design()})
            response = handle_project_request("import_into_assembly_project", {"project_path": str(project), "source_path": str(source), "expected_manifest_payload_sha256": initial["manifest_payload_sha256"]}, request_id=3, application_version="test")
            self.assertTrue(response["ok"], response)
            loaded = read_project(project, include_members=True)
            self.assertEqual(len(loaded.payload["assembly_designs"]["designs"]), 2)
            self.assertIn(source.read_bytes(), loaded.members.values())
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            imported = next(d for d in loaded.payload["assembly_designs"]["designs"] if d["source"]["source_digest"] == digest)
            self.assertEqual(imported["source"]["artifact_path"], f"package:sources/{digest}.kicad_pcb")

    def test_native_board_source_identity_mismatch_keeps_original_package(self):
        with tempfile.TemporaryDirectory() as d:
            source, project = Path(d) / "changing.kicad_pcb", Path(d) / "project.spike"
            source.write_bytes(b"captured board bytes")
            initial = write_spike_package(project, {"project": {"id": "p", "name": "P"}, "design_ir": design()})
            before = project.read_bytes()
            with patch("python.spike_core.service_assembly_import.import_design", return_value={"design": design(), "report": {}}):
                result = handle_project_request("import_into_assembly_project", {"project_path": str(project), "source_path": str(source), "expected_manifest_payload_sha256": initial["manifest_payload_sha256"]}, request_id=4, application_version="test")
            self.assertFalse(result["ok"])
            self.assertIn("source changed", result["error"])
            self.assertEqual(project.read_bytes(), before)

    def test_exchange_embedded_native_board_uses_package_source_uri(self):
        with tempfile.TemporaryDirectory() as d:
            source, project = Path(d) / "native.spikeassembly", Path(d) / "project.spike"
            board_bytes = b'(kicad_pcb (version 20240108) (generator pcbnew) (general (thickness 1.6)) (layers (0 "F.Cu" signal) (31 "B.Cu" signal)) (net 0 ""))'
            manifest = {"contract": "spike/assembly-exchange/v1", "occurrences": [{"id": "board", "kind": "board", "asset": "assets/controller.kicad_pcb"}]}
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("assembly.json", json.dumps(manifest))
                archive.writestr("assets/controller.kicad_pcb", board_bytes)
            initial = write_spike_package(project, {"project": {"id": "p", "name": "P"}, "design_ir": design()})
            response = handle_project_request("import_into_assembly_project", {"project_path": str(project), "source_path": str(source), "expected_manifest_payload_sha256": initial["manifest_payload_sha256"]}, request_id=5, application_version="test")
            self.assertTrue(response["ok"], response)
            loaded = read_project(project, include_members=True)
            imported = next(item for item in loaded.payload["assembly_designs"]["designs"] if item["source"]["source_format"] == "kicad")
            self.assertEqual(loaded.members[imported["source"]["artifact_path"].removeprefix("package:")], board_bytes)


if __name__ == "__main__": unittest.main()
