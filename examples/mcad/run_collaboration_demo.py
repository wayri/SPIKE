"""Create a synthetic two-board project/session and an optional editable FCStd."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.assembly_frames import IDENTITY
from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import AssemblyIRV1, BoardInstance, DesignIRV2
from python.spike_core.design_ir_v2_schema import CoordinateFrame
from python.spike_core.project_package import write_spike_package
from python.spike_core.service_mcad_collaboration import export_mcad_session

parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
parser.add_argument("--freecad", action="store_true", help="Also create an editable FCStd using installed FreeCADCmd")
args = parser.parse_args()
output = Path(args.output).resolve()
if output.exists(): raise SystemExit("Choose a new output directory.")
output.mkdir(parents=True)
ring = {"role": "outer", "start_mm": [0,0], "segments": [{"kind":"line", "end_mm": p} for p in [[70,0],[70,40],[0,40],[0,0]]]}
design = DesignIRV2.from_v1(DesignIR(design_id="demo-board", name="Synthetic board", source_format="neutral",
    layers=[{"id":0,"name":"F.Cu"}], stackup=[{"name":"Core","type":"dielectric","thickness_mm":1.6}],
    metadata={"board_outline_rings":[ring], "purpose":"Synthetic geometry-only collaboration example; no populated circuit or solver qualification"})).to_dict()
boards = []
for index in range(2):
    placement = list(IDENTITY); placement[3] = index * 85
    ident = f"board-{index+1}"
    boards.append(BoardInstance(id=ident, name=f"Board {index+1}", design_id=design["design_id"],
        frame=CoordinateFrame(frame_id=ident+"-frame", parent_frame_id="assembly", transform=tuple(placement))))
assembly = AssemblyIRV1(assembly_id="collaboration-demo", name="Two-board placement demo", boards=boards)
project = output / "two-boards.spike"
manifest = write_spike_package(project, {"project":{"id":"collaboration-demo-project","name":"Two boards"},
    "design_ir":design, "assembly_ir":assembly.to_dict()})
session = export_mcad_session({"project_path":str(project), "expected_manifest_payload_sha256":manifest["manifest_payload_sha256"]}, application_version="example")
(output / "two-boards-session.json").write_text(json.dumps(session, indent=2), encoding="utf-8")
if args.freecad:
    from python.spike_core.mcad_tessellation import _freecad_path
    from python.spike_core.sparselizard_process import run_adapter_process
    script = f'''import sys, json
sys.path.insert(0, {str(ROOT / 'integrations/freecad/SPIKEWorkbench')!r})
import FreeCAD as App
from spike_freecad.collaboration import import_session, build_feedback, measure_clearance, write_feedback
doc = App.newDocument("SPIKE_Collaboration_Demo")
root = import_session(doc, json.load(open("two-boards-session.json")))
objects = [o for o in doc.Objects if hasattr(o,"SPIKEOccurrenceId")]
measure_clearance(doc,root,objects)
doc.saveAs("two-boards.FCStd")
write_feedback("two-boards-feedback.json",build_feedback(doc,root))
App.closeDocument(doc.Name)
'''
    (output / "prepare.py").write_text(script, encoding="utf-8")
    result = run_adapter_process([str(_freecad_path()), "--console", "--user-cfg", str(output/"user.cfg"), "--system-cfg", str(output/"system.cfg")],
        cwd=output, timeout_s=60, memory_limit_mb=2048, output_limit_bytes=32*1024**2, stream_limit_bytes=1024**2,
        stdin_payload=b"exec(compile(open('prepare.py',encoding='utf-8').read(),'prepare.py','exec'))\nraise SystemExit(0)\n")
    if not (output / "two-boards-feedback.json").is_file(): raise RuntimeError(str(result))
print(output)
