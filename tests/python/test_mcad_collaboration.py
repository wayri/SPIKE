"""Session identity, non-destructive feedback, admission and installed FreeCAD tests."""
import copy
import base64
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from python.spike_core.assembly_frames import IDENTITY, resolve_world
from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import AssemblyIRV1, AssemblyPart, BoardInstance, DesignIRV2
from python.spike_core.design_ir_v2_schema import CoordinateFrame
from python.spike_core.mcad_session_contract import FEEDBACK, HEADER, digest, loads, validate
from python.spike_core.mcad_tessellation import _freecad_path, McadTessellationError
from python.spike_core.mcad_importer import import_mcad_artifact
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.sparselizard_process import run_adapter_process

ROOT = Path(__file__).resolve().parents[2]


def fixture(path):
    ring = {"role": "outer", "start_mm": [0, 0], "segments": [{"kind": "line", "end_mm": p} for p in [[10,0],[10,10],[0,10],[0,0]]]}
    design = DesignIRV2.from_v1(DesignIR(design_id="board", name="Board", source_format="neutral",
        layers=[{"id": 0, "name": "F.Cu"}], stackup=[{"name": "Core", "type": "dielectric", "thickness_mm": 1.6}],
        metadata={"source_sha256": "a"*64, "board_outline_rings": [ring]})).to_dict()
    t = list(IDENTITY); t[3] = 20
    group = AssemblyPart(id="group", name="Housing", part_type="subassembly", frame=CoordinateFrame(frame_id="group-frame", parent_frame_id="assembly"))
    boards = [BoardInstance(id="a", name="A", design_id=design["design_id"], frame=CoordinateFrame(frame_id="a-frame", parent_frame_id="group-frame")),
              BoardInstance(id="b", name="B", design_id=design["design_id"], frame=CoordinateFrame(frame_id="b-frame", parent_frame_id="assembly", transform=tuple(t)))]
    assembly = AssemblyIRV1(assembly_id="assembly-id", name="Two boards", boards=boards, parts=[group])
    return write_spike_package(path, {"project": {"id": "project-id", "name": "Collaboration"}, "design_ir": design,
        "assembly_ir": assembly.to_dict(), "analyses": {"latest_result": {"temperature": 300}, "setup": "preserved"},
        "results": {"old": 42}, "extensions": {"legacy": {"analysis": {"latest_result": {"temperature": 300}, "result_history": [1]},
            "thermal": {"scenario": {"ambient": 298, "result": {"temperature": 300}}}}}})


def request(path, method, **extras):
    return handle_project_request(method, {"project_path": str(path),
        "expected_manifest_payload_sha256": read_project(path).manifest["manifest_payload_sha256"], **extras}, request_id=1, application_version="test")


def feedback(session):
    return {"contract": FEEDBACK, **{k: session[k] for k in HEADER}, "measurements": [],
            "objects": [{k: copy.deepcopy(o[k]) for k in ("id", "name", "transform")} for o in session["objects"]]}


class CollaborationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "project.spike"
        fixture(self.path)
        response = request(self.path, "export_mcad_session")
        self.assertTrue(response["ok"], response)
        self.session = response["result"]

    def test_portable_validator_is_identical(self):
        self.assertEqual((ROOT / "python/spike_core/mcad_session_contract.py").read_bytes(),
                         (ROOT / "integrations/freecad/SPIKEWorkbench/spike_freecad/session_contract.py").read_bytes())

    def test_export_preserves_hierarchy_geometry_and_source(self):
        rows = {o["id"]: o for o in self.session["objects"]}
        self.assertEqual(rows["a"]["parent_id"], "group")
        self.assertEqual(rows["a"]["geometry"]["height_mm"], 1.6)
        before = self.path.read_bytes()
        request(self.path, "export_mcad_session")
        self.assertEqual(before, self.path.read_bytes())

    def test_review_apply_repeat_and_result_archiving(self):
        old = read_project(self.path, include_members=True)
        f = feedback(self.session)
        f["objects"][0]["transform"][11] = 5
        f["objects"][0]["name"] = "Renamed"
        f["measurements"] = [{"object_a_id": "a", "object_b_id": "b", "distance_mm": 10, "overlap_volume_mm3": 0}]
        preview = request(self.path, "preview_mcad_feedback", feedback=f)
        self.assertTrue(preview["ok"], preview)
        self.assertEqual(len(preview["result"]["changes"]), 1)
        done = request(self.path, "apply_mcad_feedback", feedback=f, reviewed_feedback_sha256=preview["result"]["feedback_sha256"])
        self.assertTrue(done["ok"], done)
        new = read_project(self.path)
        self.assertEqual(old.payload["design_ir"], new.payload["design_ir"])
        self.assertEqual(new.payload["assembly_ir"]["boards"][0]["frame"]["transform"][11], 5)
        self.assertIsNone(new.payload["analyses"]["latest_result"])
        self.assertEqual(new.payload["analyses"]["setup"], "preserved")
        self.assertIsNone(new.payload["extensions"]["legacy"]["thermal"]["scenario"]["result"])
        self.assertEqual(new.payload["extensions"]["spike.mcad-collaboration"]["previous_states"][0]["results"], {"old": 42})
        before = self.path.read_bytes()
        repeated = request(self.path, "apply_mcad_feedback", feedback=f, reviewed_feedback_sha256=digest(f))
        self.assertTrue(repeated["ok"], repeated)
        self.assertTrue(repeated["result"]["no_op"])
        self.assertEqual(before, self.path.read_bytes())

    def test_rejected_changes_leave_package_untouched(self):
        for mutate in (lambda f: f.update(project_id="other"), lambda f: f.update(baseline_assembly_sha256="0"*64),
                       lambda f: f.update(baseline_designs_sha256="0"*64), lambda f: f["objects"].pop(),
                       lambda f: f["objects"][0]["transform"].__setitem__(0, 2),
                       lambda f: f["objects"][0]["transform"].__setitem__(3, float("nan")),
                       lambda f: f["objects"][0].update(parent_id="b")):
            f = feedback(self.session); mutate(f)
            before = self.path.read_bytes()
            result = request(self.path, "apply_mcad_feedback", feedback=f, reviewed_feedback_sha256="0"*64)
            self.assertFalse(result["ok"])
            self.assertEqual(before, self.path.read_bytes())
            preview = request(self.path, "preview_mcad_feedback", feedback=f)
            self.assertFalse(preview["ok"])

    def test_noop_and_changed_review(self):
        f = feedback(self.session)
        before = self.path.read_bytes()
        result = request(self.path, "apply_mcad_feedback", feedback=f, reviewed_feedback_sha256=digest(f))
        self.assertTrue(result["ok"], result)
        self.assertEqual(before, self.path.read_bytes())
        reviewed = digest(f)
        f["objects"][0]["name"] = "Changed after review"
        self.assertFalse(request(self.path, "apply_mcad_feedback", feedback=f, reviewed_feedback_sha256=reviewed)["ok"])

    def test_contract_rejects_duplicate_keys_cycles_missing_assets(self):
        with self.assertRaises(ValueError): loads('{"contract":1,"contract":2}')
        for mutate in (lambda s: s["objects"][0].update(parent_id="a"),
                       lambda s: s["objects"][0].update(geometry={"type":"step", "asset_sha256":"0"*64}),
                       lambda s: s.update(macro="run anything"),
                       lambda s: s["objects"].append(copy.deepcopy(s["objects"][0]))):
            session = copy.deepcopy(self.session); mutate(session)
            with self.assertRaises(ValueError): validate(session)

    def test_schemas_and_duplicate_feedback_json(self):
        from jsonschema import Draft202012Validator
        for name, value in (("mcad-session-v1", self.session), ("mcad-feedback-v1", feedback(self.session))):
            schema_path = ROOT / "schemas" / (name + ".schema.json")
            schema = json.loads(schema_path.read_text())
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(value)
            self.assertEqual(schema_path.read_bytes(), (ROOT / "integrations/freecad/SPIKEWorkbench/Resources/schemas" / schema_path.name).read_bytes())
        result = request(self.path, "preview_mcad_feedback", feedback_json='{"contract":1,"contract":2}')
        self.assertFalse(result["ok"])

    def test_part_placement_policy_cannot_be_bypassed(self):
        opened = read_project(self.path, include_members=True)
        payload = copy.deepcopy(opened.payload)
        payload["assembly_ir"]["parts"][0]["placement_policy"] = {
            "contract": "spike/assembly-placement-policy/v1", "translation_snap_mm": 5, "rotation_snap_deg": None}
        write_spike_package(self.path, payload, preserved_members=opened.members)
        f = feedback(request(self.path, "export_mcad_session")["result"])
        next(o for o in f["objects"] if o["id"] == "group")["transform"][3] = 1
        self.assertFalse(request(self.path, "preview_mcad_feedback", feedback=f)["ok"])

    def test_retained_step_bytes_are_embedded_with_verified_identity(self):
        step = Path(self.temp.name) / "part.step"
        step.write_text("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;")
        imported = import_mcad_artifact(step)
        opened = read_project(self.path, include_members=True)
        payload = copy.deepcopy(opened.payload)
        payload["assembly_ir"]["parts"].append(asdict(imported.part))
        payload["models"] = {"contract": "spike/model-index/v1", "models": [asdict(imported.model)]}
        write_spike_package(self.path, payload, preserved_members=opened.members, model_artifacts={imported.artifact_name: imported.artifact_bytes})
        result = request(self.path, "export_mcad_session")
        self.assertTrue(result["ok"], result)
        self.assertEqual(base64.b64decode(result["result"]["assets"][imported.model.digest]["data_base64"]), step.read_bytes())

    def test_a_second_session_is_stale_after_first_feedback(self):
        f = feedback(self.session); f["objects"][0]["transform"][3] = 2
        done = request(self.path, "apply_mcad_feedback", feedback=f, reviewed_feedback_sha256=digest(f))
        self.assertTrue(done["ok"], done)
        other = feedback(self.session); other["objects"][1]["transform"][3] = 15
        self.assertFalse(request(self.path, "preview_mcad_feedback", feedback=other)["ok"])

    def test_real_freecad_roundtrip_clearance_save_reopen_and_edit_rejection(self):
        try: executable = _freecad_path()
        except McadTessellationError as exc: self.skipTest(str(exc))
        root = Path(self.temp.name)
        (root / "session.json").write_text(json.dumps(self.session), encoding="utf-8")
        script = f'''
import sys, json, base64, hashlib
sys.path.insert(0, {str(ROOT / 'integrations/freecad/SPIKEWorkbench')!r})
import FreeCAD as App
import Part
from spike_freecad.collaboration import import_session, build_feedback, measure_clearance, write_feedback, session_root
doc = App.newDocument("Collaboration")
session = json.load(open("session.json"))
# Exercise embedded STEP solids as well as generated board outlines.
Part.makeBox(10,10,1.6).exportStep("fixture.step")
step_bytes = open("fixture.step","rb").read()
sha = hashlib.sha256(step_bytes).hexdigest()
session["assets"][sha] = {{"type":"step","data_base64":base64.b64encode(step_bytes).decode()}}
next(o for o in session["objects"] if o["id"] == "b")["geometry"] = {{"type":"step","asset_sha256":sha}}
root = import_session(doc, session)
by_id = {{o.SPIKEOccurrenceId:o for o in doc.Objects if hasattr(o,"SPIKEOccurrenceId")}}
assert abs(measure_clearance(doc, root, [by_id["a"],by_id["b"]])["distance_mm"] - 10) < 1e-7
assert len(build_feedback(doc, root)["measurements"]) == 1
by_id["b"].Placement.Base.x = 5
doc.recompute()
assert not build_feedback(doc, root)["measurements"]
assert abs(measure_clearance(doc, root, [by_id["a"],by_id["b"]])["overlap_volume_mm3"] - 80) < 1e-6
by_id["group"].Placement = App.Placement(App.Vector(3,4,5), App.Rotation(App.Vector(0,0,1), 90))
by_id["a"].Label = "A moved in FreeCAD"
doc.recompute()
doc.saveAs("collaboration.FCStd")
App.closeDocument(doc.Name)
doc = App.openDocument("collaboration.FCStd")
root = session_root(doc)
good = build_feedback(doc, root)
write_feedback("feedback.json", good)
by_id = {{o.SPIKEOccurrenceId:o for o in doc.Objects if hasattr(o,"SPIKEOccurrenceId")}}
feature = doc.getObject(by_id["a"].SPIKEGeometryName)
feature.Placement.Base.z = 2
try:
    build_feedback(doc,root)
    raise AssertionError("Changed geometry placement accepted")
except ValueError: pass
feature.Placement.Base.z = 0
original_shape = feature.Shape.copy()
feature.Shape = Part.makeBox(12,10,1.6)
try:
    build_feedback(doc,root)
    raise AssertionError("Changed solid accepted")
except ValueError: pass
feature.Shape = original_shape
by_id["b"].addObject(by_id["a"])
try:
    build_feedback(doc,root)
    raise AssertionError("Reparenting accepted")
except ValueError: pass
open("verified.json","w").write(json.dumps({{"passed":True}}))
App.closeDocument(doc.Name)
'''
        (root / "verify.py").write_text(script, encoding="utf-8")
        result = run_adapter_process([str(executable), "--console", "--user-cfg", str(root / "user.cfg"), "--system-cfg", str(root / "system.cfg")],
            cwd=root, timeout_s=60, memory_limit_mb=2048, output_limit_bytes=32*1024**2, stream_limit_bytes=1024**2,
            stdin_payload=b"exec(compile(open('verify.py',encoding='utf-8').read(),'verify.py','exec'))\nraise SystemExit(0)\n")
        self.assertTrue((root / "verified.json").is_file(), str(result)[-7000:])
        f = loads((root / "feedback.json").read_text())
        done = request(self.path, "apply_mcad_feedback", feedback=f, reviewed_feedback_sha256=digest(f))
        self.assertTrue(done["ok"], done)
        assembly = AssemblyIRV1.from_dict(read_project(self.path).payload["assembly_ir"])
        transform = resolve_world(assembly, assembly.boards[0].frame)
        for i,v in [(3,3),(7,4),(11,5)]: self.assertAlmostEqual(transform[i], v)


if __name__ == "__main__": unittest.main()
