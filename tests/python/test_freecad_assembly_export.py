"""Optional real-kernel test of external assembly export and STEP placement."""
import json
import tempfile
import unittest
from pathlib import Path

from python.spike_core.assembly_exchange import import_exchange
from python.spike_core.assembly_frames import resolve_world
from python.spike_core.design_ir_v2 import AssemblyIRV1
from python.spike_core.mcad_tessellation import _freecad_path, McadTessellationError
from python.spike_core.sparselizard_process import run_adapter_process


class FreeCADAssemblyExportTests(unittest.TestCase):
    def test_nested_shapes_are_exported_once_with_local_step_geometry(self):
        try:
            executable = _freecad_path()
        except McadTessellationError as exc:
            self.skipTest(str(exc))
        workbench = Path(__file__).resolve().parents[2] / "integrations/freecad/SPIKEWorkbench"
        with tempfile.TemporaryDirectory(prefix="spike-exchange-test-") as directory:
            root = Path(directory)
            script = f'''
import sys, json
sys.path.insert(0, {str(workbench)!r})
import FreeCAD as App
import Part
from spike_freecad.assembly_export import export_assembly
doc = App.newDocument("ExchangeTest")
group = doc.addObject("App::Part", "Housing")
group.Placement.Base = App.Vector(100, 20, 0)
base = doc.addObject("Part::Feature", "Base")
base.Shape = Part.makeBox(10, 20, 3)
group.addObject(base)
base.Placement.Base = App.Vector(5, 0, 7)
lid = doc.addObject("Part::Feature", "Lid")
lid.Shape = Part.makeBox(10, 20, 2)
group.addObject(lid)
lid.Placement.Base = App.Vector(5, 0, 17)
doc.recompute()
result = export_assembly(doc, [group, base], "assembly.spikeassembly")
assert base.Placement.Base.x == 5
import zipfile
with zipfile.ZipFile("assembly.spikeassembly") as z:
    manifest = json.loads(z.read("assembly.json"))
    z.extract("assets/Base.step", ".")
shape = Part.Shape()
shape.read("assets/Base.step")
assert abs(shape.BoundBox.XMin) < 1e-7, shape.BoundBox
assert abs(shape.BoundBox.ZMin) < 1e-7, shape.BoundBox
assert abs(shape.Volume - 600) < 1e-6
open("verified.json", "w").write(json.dumps(result))
App.closeDocument(doc.Name)
'''
            (root / "verify.py").write_text(script, encoding="utf-8")
            result = run_adapter_process([str(executable), "--console", "--user-cfg", str(root / "user.cfg"), "--system-cfg", str(root / "system.cfg")],
                cwd=root, timeout_s=60, memory_limit_mb=2048, output_limit_bytes=32 * 1024**2, stream_limit_bytes=1024**2,
                stdin_payload=b"exec(compile(open('verify.py',encoding='utf-8').read(),'verify.py','exec'))\nraise SystemExit(0)\n")
            self.assertTrue((root / "verified.json").is_file(), str(result)[-5000:])
            self.assertEqual(json.loads((root / "verified.json").read_text())["occurrences"], 3)
            imported = import_exchange(root / "assembly.spikeassembly")
            assembly = AssemblyIRV1.from_dict(imported["assembly"])
            base = next(p for p in assembly.parts if p.name == "Base")
            transform = resolve_world(assembly, base.frame)
            self.assertAlmostEqual(transform[3], 105)
            self.assertAlmostEqual(transform[7], 20)
            self.assertAlmostEqual(transform[11], 7)


if __name__ == "__main__": unittest.main()
