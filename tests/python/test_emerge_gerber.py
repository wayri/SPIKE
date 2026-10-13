# SPDX-License-Identifier: Apache-2.0
"""Native EMerge Gerber retention, admission, loader wiring and unit fixtures."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np

from extensions.emerge_suite.extension import execute, _probe_executable
from extensions.emerge_suite.gerber_case import compile_gerber
from extensions.emerge_suite.gerber_source import (
    MAX_FILE_BYTES, design_from_source, normalize_gerber_source,
)
from extensions.emerge_suite.mesh_capture import capture_mesh
from extensions.emerge_suite.mesh_extension import design_digest
from extensions.emerge_suite.runner import run_case
from extensions.emerge_suite.script_builder import generate_script
from python.spike_core.extensions import ExtensionRegistry
from python.spike_core.importers import ImporterRegistry


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "emerge_gerber"


def gerber_source(*, drills=None):
    mm = (FIXTURES / "mm_dark_clear.gbr").read_text(encoding="utf-8")
    inch = (FIXTURES / "inch_flash_trace.gbr").read_text(encoding="utf-8")
    return {
        "contract": "spike/emerge-gerber-source/v1", "name": "Native RF artwork",
        "bounds_mm": [0, 0, 100, 20],
        "layers": [
            {"name": "F.Cu", "file_name": "rf-top.gbr", "content": mm},
            {"name": "B.Cu", "file_name": "return-bottom.gbr", "content": inch},
        ],
        "dielectrics": [{"thickness_mm": 1.0, "epsilon_r": 4.2, "loss_tangent": .02}],
        "ports": [{"id": "P1", "x_mm": 20, "y_mm": 10, "width_mm": 1,
                   "signal_layer": "F.Cu", "return_layer": "B.Cu"}],
        "resolution_mm": .01, "drills": drills or [],
    }


def parameters():
    return {"geometry_source": "gerber", "frequency_start_hz": 1e9,
            "frequency_stop_hz": 2e9, "frequency_points": 2,
            "mesh_resolution_mm": .5}


def public_mesh():
    return types.SimpleNamespace(
        nodes=np.asarray([[0., .001, 0., 0.], [0., 0., .001, 0.], [0., 0., 0., .001]]),
        tets=np.asarray([[0], [1], [2], [3]]),
        tris=np.asarray([[0, 0, 0, 1], [1, 1, 2, 2], [2, 3, 3, 3]]),
        vtag_to_tet={1: np.asarray([0])}, ftag_to_tri={2: np.arange(4)})


class EMergeGerberTests(unittest.TestCase):
    def test_conductor_and_roughness_loss_requests_fail_closed(self):
        design = design_from_source(gerber_source()).to_dict()
        for request in ({"include_conductor_loss": True},
                        {"surface_impedance_ohm": .01},
                        {"roughness_rms_um": 1.0}):
            with self.subTest(request=request):
                with self.assertRaisesRegex(ValueError, "zero-thickness PEC copper"):
                    compile_gerber(design, {**parameters(), **request})

    def test_project_save_open_retains_artwork_and_current_materials(self):
        from python.spike_core.normalized_source_codec import decode_normalized_source
        from python.spike_core.service_project_handlers import handle_project_request

        source = gerber_source()
        snapshot = execute({"contract": "spike/extension/v1", "contribution_id": "emerge-gerber-import",
                            "context": {"parameters": {"source": source}}})["data"]["snapshot"]
        snapshot["design"]["stackup"][1]["epsilon_r"] = 5.1
        project = {"format": "spike-project-package/v2", "project": {"name": "native artwork"},
                   "design": {"source_file": "native.spike-design.json", "source_format": "spike-normalized",
                              "source_board": json.dumps(snapshot)}, "analysis": {}}
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "native.spike")
            saved = handle_project_request("write_project_package", {"path": path, "snapshot": project},
                                           request_id="gerber-save", application_version="test")
            self.assertTrue(saved["ok"], saved)
            opened = handle_project_request("read_project_package", {"path": path},
                                            request_id="gerber-open", application_version="test")
            self.assertTrue(opened["ok"], opened)
        restored = json.loads(decode_normalized_source(opened["result"]["project"]["design"]["source_board"]))
        retained = restored["design"]["metadata"]["emerge_gerber_source"]
        self.assertEqual(retained["layers"][0]["content"], source["layers"][0]["content"])
        self.assertEqual(retained["dielectrics"][0]["epsilon_r"], 4.2)
        self.assertEqual(compile_gerber(restored["design"], parameters())["dielectric_layers"][0]["epsilon_r"], 5.1)

    def test_application_import_preserves_sources_hashes_and_neutral_projection(self):
        request = {"contract": "spike/extension/v1", "contribution_id": "emerge-gerber-import",
                   "context": {"parameters": {"source": gerber_source()}}}
        result = execute(request)
        snapshot = result["data"]["snapshot"]
        self.assertEqual(snapshot["contract"], "spike/design-snapshot/v1")
        self.assertEqual(snapshot["design"]["source_format"], "emerge-gerber")
        self.assertEqual(result["data"]["setup"]["geometry_source"], "gerber")
        retained = snapshot["canonical_design"]["metadata"]["emerge_gerber_source"]
        self.assertEqual(retained["layers"][0]["content"], gerber_source()["layers"][0]["content"])
        self.assertEqual(len(retained["layers"][0]["sha256"]), 64)
        self.assertEqual(snapshot["canonical_design"]["tracks"], [])
        self.assertEqual(snapshot["canonical_design"]["pads"], [])
        self.assertEqual(snapshot["canonical_design"]["zones"], [])
        changed_source = gerber_source()
        changed_source["ports"][0]["x_mm"] = 21
        changed_design = design_from_source(changed_source).to_dict()
        self.assertNotEqual(snapshot["design"]["design_id"], changed_design["design_id"])
        self.assertNotEqual(snapshot["design"]["layers"][0]["id"], changed_design["layers"][0]["id"])
        self.assertEqual(snapshot["canonical_design"]["source"]["artifact_path"], "")
        self.assertTrue(any(issue["code"] == "EMERGE_GERBER_MANUAL_PORTS"
                            for issue in snapshot["design"]["issues"]))
        self.assertTrue(snapshot["report"]["solver_readiness"]["emerge_native_gerber"]["ready"])

    def test_manifest_application_and_registered_file_importer_use_process_boundary(self):
        registry = ExtensionRegistry()
        diagnostics = registry.discover([ROOT / "extensions"], trusted_roots=[ROOT / "extensions"])
        self.assertTrue(any(row["id"] == "spike.emerge-suite" and row["status"] == "loaded"
                            for row in diagnostics))
        result = registry.invoke("spike.emerge-suite", "emerge-gerber-import",
                                 {"parameters": {"source": gerber_source()}})
        self.assertEqual(result["data"]["snapshot"]["design"]["source_format"], "emerge-gerber")
        with tempfile.TemporaryDirectory(prefix="spike-gerber-test-") as directory:
            path = Path(directory) / "fixture.spike-gerber.json"
            path.write_text(json.dumps(gerber_source()), encoding="utf-8")
            importers = ImporterRegistry(registry.design_importers())
            outcome = importers.import_outcome(str(path), "emerge-gerber")
        self.assertEqual(outcome.design.source.source_format, "emerge-gerber")
        self.assertEqual(outcome.design.metadata["emerge_gerber_source"]["name"], "Native RF artwork")

    def test_case_and_script_bind_native_sources_and_assumptions(self):
        design = design_from_source(gerber_source()).to_dict()
        case = compile_gerber(design, parameters())
        self.assertEqual(case["source_format"], "emerge-gerber")
        self.assertEqual(case["polygons"], [])
        self.assertEqual(case["native_gerber_layers"][1]["content"],
                         gerber_source()["layers"][1]["content"])
        self.assertEqual(case["ports"][0]["height_mm"], 1.0)
        self.assertEqual(case["port_mapping"][0]["mapping_status"],
                         "manual_unverified_source_annotation")
        design["stackup"][1]["epsilon_r"] = 5.1
        edited = compile_gerber(design, parameters())
        self.assertEqual(edited["dielectric_layers"][0]["epsilon_r"], 5.1)
        self.assertEqual(edited["material_assignment_source"], "current_spiDeR_stackup")
        generated = generate_script(case, radiation_requested=False, mesh_only=True)
        self.assertIn("FileBasedPCB", generated["script"])
        self.assertIn("rf-top.gbr", generated["script"])
        altered = gerber_source()
        altered["dielectrics"][0]["epsilon_r"] = 4.3
        changed = generate_script(compile_gerber(design_from_source(altered).to_dict(), parameters()),
                                  radiation_requested=False, mesh_only=True)
        self.assertNotEqual(generated["case_sha256"], changed["case_sha256"])
        with self.assertRaisesRegex(ValueError, "does not match"):
            compile_gerber(design, {**parameters(), "geometry_source": "board"})

    def test_surrounding_geometry_is_admitted_and_retained(self):
        design = design_from_source(gerber_source()).to_dict()
        surrounding = {"contract": "spike/emerge-surroundings/v1", "objects": [{
            "kind": "dielectric_box", "name": "Cover", "origin_mm": [0, 0, .5],
            "size_mm": [20, 10, 1], "epsilon_r": 2.8,
        }]}
        case = compile_gerber(design, {**parameters(), "surrounding_geometry": surrounding})
        self.assertEqual(case["surrounding_geometry"][0]["name"], "Cover")
        self.assertEqual(case["surrounding_geometry"][0]["epsilon_r"], 2.8)
        self.assertIn("dielectric_surroundings", case["geometry_status"])
        bad = json.loads(json.dumps(surrounding))
        bad["objects"][0]["origin_mm"][2] = .1
        with self.assertRaisesRegex(ValueError, "at least 0.5 mm"):
            compile_gerber(design, {**parameters(), "surrounding_geometry": bad})

    def test_malformed_bounds_ports_stackup_and_budgets_fail_closed(self):
        mutations = []
        source = gerber_source(); source["bounds_mm"] = [0, 0, 0, 1]; mutations.append(source)
        source = gerber_source(); source["ports"][0]["return_layer"] = "F.Cu"; mutations.append(source)
        source = gerber_source(); source["dielectrics"] = []; mutations.append(source)
        source = gerber_source(); source["layers"][0]["content"] = "X" * (MAX_FILE_BYTES + 1); mutations.append(source)
        source = gerber_source(); source["layers"][0]["file_name"] = "../escape.gbr"; mutations.append(source)
        for unsafe in (r"folder\escape.gbr", "stream:gbr", "CON.gbr", "trailing.gbr.",
                       "trailing.gbr ", "line\nbreak.gbr"):
            source = gerber_source(); source["layers"][0]["file_name"] = unsafe; mutations.append(source)
        for source in mutations:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    normalize_gerber_source(source)
        with self.assertRaisesRegex(ValueError, "Excellon"):
            compile_gerber(design_from_source(gerber_source(drills=[
                {"file_name": "board.drl", "content": "M48\nM30\n"}])).to_dict(), parameters())

    def test_portable_unicode_filename_is_retained_exactly(self):
        source = gerber_source()
        source["layers"][0]["file_name"] = "RF board (été)-F_Cu.gbr"
        normalized = normalize_gerber_source(source)
        self.assertEqual(normalized["layers"][0]["file_name"], "RF board (été)-F_Cu.gbr")
        for reserved in ("CON .gbr", "COM¹.gbr", "LPT³.gbr"):
            source = gerber_source()
            source["layers"][0]["file_name"] = reserved
            with self.assertRaisesRegex(ValueError, "reserved Windows device"):
                normalize_gerber_source(source)

    def test_runner_materializes_exact_files_and_calls_native_loader(self):
        calls = []
        expected = {row["file_name"]: row["content"] for row in gerber_source()["layers"]}

        class PCB:
            def __init__(self, *args, **kwargs): calls.append(("pcb", kwargs))
            def layer_from_file(self, layer, filename, **kwargs):
                path = Path(filename)
                self.assert_source(path.name, path.read_text(encoding="utf-8"), expected)
                calls.append(("layer", layer, path.name, kwargs))
                return f"surface-{layer}"
            @staticmethod
            def assert_source(name, content, sources):
                if content != sources[name]:
                    raise AssertionError("runner changed retained Gerber bytes")
            def set_bounds(self, *args): calls.append(("bounds", args))
            def generate_pcb(self, **kwargs): calls.append(("generate", kwargs))

        class Simulation:
            mesh = public_mesh()
            mw = types.SimpleNamespace(set_frequency_range=lambda *args: None)
            mesher = types.SimpleNamespace(
                set_boundary_size=lambda *args: calls.append(("size", args)),
                set_face_size=lambda *args: None)
            def __init__(self, name): pass
            def commit_geometry(self): calls.append(("commit",))
            def generate_mesh(self): calls.append(("mesh",))

        class Air:
            def background(self): return self

        class Box:
            def __init__(self, *args, **kwargs): pass
            def set_material(self, value): pass

        em = types.SimpleNamespace(
            __version__="3.0.0a19", Simulation=Simulation,
            Material=lambda *args, **kwargs: object(), lib=types.SimpleNamespace(PEC="PEC"),
            geo=types.SimpleNamespace(
                PCBNew=lambda *args, **kwargs: self.fail("polygon PCB path used"),
                Box=Box, Plate=lambda *args: "plate", open_region=lambda *args: Air()))
        gerber_module = types.ModuleType("emerge.beta.gerber")
        gerber_module.FileBasedPCB = PCB
        case = compile_gerber(design_from_source(gerber_source()).to_dict(), parameters())
        with patch.dict(sys.modules, {"emerge.beta.gerber": gerber_module}):
            result = run_case(case, em, radiation=False, mesh_only=True)
        self.assertEqual(result["native_gerber_layer_count"], 2)
        self.assertEqual([call[1] for call in calls if call[0] == "layer"], [1, 0])
        self.assertEqual([call[3]["res_mm"] for call in calls if call[0] == "layer"], [.01, .01])
        self.assertEqual(sum(call[0] == "size" for call in calls), 2)
        self.assertLess(calls.index(("commit",)), calls.index(("mesh",)))

    def test_analysis_result_discloses_native_source_and_manual_ports(self):
        design = design_from_source(gerber_source()).to_dict()
        request = {"contract": "spike/extension/v1", "request_id": "gerber-si",
                   "contribution_id": "emerge-si", "context": {
                       "design": design, "design_binding": design_digest(design),
                       "parameters": parameters()}}
        raw = {"engine_version": "3.0.0a19", "native_gerber_layer_count": 2,
               "s_parameters": {"frequencies_hz": [1e9, 2e9], "ports": ["P1"],
                                "reference_impedance_ohm": 50,
                                "values": [[[[.1, 0]]], [[[.2, 0]]]]}}
        result = execute(request, backend=lambda *args, **kwargs: raw)["data"]["analysis_result"]
        codes = {row["code"] for row in result["issues"]}
        self.assertIn("EMERGE_GERBER_MANUAL_PORTS", codes)
        self.assertNotIn("EMERGE_COPPER_FRAGMENTATION_DISABLED", codes)
        provenance = result["provenance"]
        self.assertEqual(provenance["native_gerber_source_sha256"],
                         design["metadata"]["emerge_gerber_source_sha256"])
        self.assertEqual(provenance["material_assignment_source"], "current_spiDeR_stackup")

    def test_probe_keeps_core_available_when_optional_gerber_dependency_is_missing(self):
        checks = {name: True for name in ("pcb_layer_polygons", "pcb_geometry", "microwave_sweep",
                                          "microwave_boundaries", "mesh_generation", "mesh_sizing",
                                          "mesh_export")}
        checks["gerber_loader"] = False
        metadata = {"version": "3.0.0a19", "api_checks": checks,
                    "gerber_reason": "Install emerge[gerber] in the selected solver Python environment."}
        process = types.SimpleNamespace(returncode=0,
            stdout=(json.dumps(metadata) + "\n").encode(), stderr=b"")
        with patch("extensions.emerge_suite.extension.subprocess.run", return_value=process):
            result = _probe_executable(Path(__file__))
        self.assertTrue(result["available"])
        self.assertFalse(result["gerber_available"])
        self.assertNotIn("native_gerber_geometry", result["capabilities"])
        self.assertIn("emerge[gerber]", result["gerber_reason"])

    @unittest.skipUnless((ROOT / ".venv-emerge3" / "Scripts" / "python.exe").is_file() and
                         (ROOT / ".local" / "gerber-api-deps" / "pygerber").is_dir(),
                         "optional EMerge 3 plus Gerber dependencies")
    def test_real_filebasedpcb_loads_units_clear_region_and_native_mesh(self):
        executable = ROOT / ".venv-emerge3" / "Scripts" / "python.exe"
        code = r'''
import json, sys
import emerge as em
sys.path.insert(0, sys.argv[1])
import gmsh
from emerge.beta.gerber import FileBasedPCB
rows = []
for index, filename in enumerate(sys.argv[2:4]):
    model = em.Simulation('SPIKE_gerber_fixture_' + str(index))
    pcb = FileBasedPCB(1.0, unit=.001, layers=2)
    pcb.layer_from_file(1, filename, res_mm=.01)
    surfaces = gmsh.model.getEntities(2)
    bounds = [gmsh.model.getBoundingBox(*entity) for entity in surfaces]
    boundaries = [len(gmsh.model.getBoundary([entity], oriented=False)) for entity in surfaces]
    rows.append({'bounds': bounds, 'boundaries': boundaries})
sys.path.insert(0, sys.argv[4])
from pathlib import Path
from extensions.emerge_suite.gerber_source import design_from_source
from extensions.emerge_suite.gerber_case import compile_gerber
from extensions.emerge_suite.runner import run_case
content = Path(sys.argv[2]).read_text(encoding='utf-8')
source = {'contract':'spike/emerge-gerber-source/v1','name':'mesh fixture','bounds_mm':[0,0,10,6],
 'layers':[{'name':'F.Cu','file_name':'top.gbr','content':content},
           {'name':'B.Cu','file_name':'bottom.gbr','content':content}],
 'dielectrics':[{'thickness_mm':1,'epsilon_r':4.2,'loss_tangent':.02}],
 'ports':[{'id':'P1','x_mm':2,'y_mm':2,'width_mm':1,'signal_layer':'F.Cu','return_layer':'B.Cu'}],
 'resolution_mm':.05}
case = compile_gerber(design_from_source(source).to_dict(),
 {'geometry_source':'gerber','frequency_start_hz':1e9,'frequency_stop_hz':2e9,
  'frequency_points':2,'mesh_resolution_mm':2})
mesh_result = run_case(case, em, radiation=False, mesh_only=True)
print(json.dumps({'loads': rows, 'mesh': {'nodes': mesh_result['mesh']['node_count'],
 'tetrahedra': mesh_result['mesh']['tetrahedron_count'],
 'layers': mesh_result['native_gerber_layer_count']}}))
'''
        process = subprocess.run(
            [str(executable), "-I", "-X", "utf8", "-c", code,
             str(ROOT / ".local" / "gerber-api-deps"),
             str(FIXTURES / "mm_dark_clear.gbr"), str(FIXTURES / "inch_flash_trace.gbr"),
             str(ROOT)],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, shell=False)
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors="replace"))
        payload = json.loads(process.stdout.decode("utf-8").splitlines()[-1])
        rows = payload["loads"]
        mm_bounds = rows[0]["bounds"][0]
        self.assertAlmostEqual(mm_bounds[3] - mm_bounds[0], .01, places=5)
        self.assertAlmostEqual(mm_bounds[4] - mm_bounds[1], .006, places=5)
        self.assertGreaterEqual(rows[0]["boundaries"][0], 5)  # outer region plus clear-hole boundary
        inch_bounds = rows[1]["bounds"][0]
        self.assertAlmostEqual(inch_bounds[3] - inch_bounds[0], 3.02 * .0254, places=4)
        self.assertEqual(payload["mesh"]["layers"], 2)
        self.assertGreater(payload["mesh"]["nodes"], 100)
        self.assertGreater(payload["mesh"]["tetrahedra"], 500)


if __name__ == "__main__":
    unittest.main()
