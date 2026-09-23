"""Exercise the real discovered FreeCAD STEP-to-GLB visual adapter."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.dependencies import dependency_status
from python.spike_core.mcad_tessellation import tessellate_step_to_glb


def main() -> int:
    dependency = next(item for item in dependency_status()["dependencies"] if item["id"] == "freecad")
    if dependency["status"] != "ready" or not dependency["path"]:
        raise RuntimeError("FreeCADCmd is unavailable; the optional real-converter smoke cannot run.")
    with tempfile.TemporaryDirectory(prefix="spike-freecad-qualification-") as directory:
        root = Path(directory)
        generator = root / "make_step.FCMacro"
        step = root / "box.step"
        generator.write_text(
            "import sys\nimport FreeCAD as App\nimport Part\n"
            "doc=App.newDocument('SPIKE_FIXTURE')\n"
            "box=doc.addObject('Part::Box','Box')\n"
            "box.Length=10\nbox.Width=7\nbox.Height=3\ndoc.recompute()\n"
            "Part.export([box],sys.argv[1])\nApp.closeDocument(doc.Name)\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [dependency["path"], "-c"],
            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            input=(f"import sys\nsys.argv=['make_step.FCMacro',{str(step)!r}]\n"
                   f"exec(compile(open({str(generator)!r},encoding='utf-8').read(),{str(generator)!r},'exec'))\n"
                   "raise SystemExit(0)\n").encode("utf-8"),
            timeout=60, check=False, shell=False,
        )
        if completed.returncode != 0 or not step.is_file():
            raise RuntimeError((completed.stderr or completed.stdout).decode("utf-8", errors="replace")[-4000:])
        result = tessellate_step_to_glb(step.read_bytes(), source_name=step.name)
        print(json.dumps({**result.to_dict(), "artifact_bytes": len(result.artifact_bytes)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
