"""Read-only independent inventory using the installed KiCad pcbnew reader."""
import json
from pathlib import Path
import sys
import subprocess
import pcbnew

root = Path(__file__).resolve().parents[1]
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
output = []
selected_id = sys.argv[3] if len(sys.argv) > 3 else None
if selected_id is None:
    for source in manifest["sources"]:
        if not any(i.get("role") == "board" and i["path"].endswith(".kicad_pcb") for i in source["files"]): continue
        target = Path(sys.argv[2]).with_name(source["id"] + "-native.json")
        try:
            run = subprocess.run([sys.executable, __file__, sys.argv[1], str(target), source["id"]],
                                 capture_output=True, text=True, timeout=90)
            if run.returncode: raise ValueError(run.stderr[-1000:])
            output.extend(json.loads(target.read_text(encoding="utf-8")))
        except Exception as exc:
            output.append({"id": source["id"], "status": "failed", "error": str(exc)})
        print(source["id"], output[-1]["status"], flush=True)
        Path(sys.argv[2]).write_text(json.dumps(output, indent=2), encoding="utf-8")
    raise SystemExit()
for source in manifest["sources"]:
    if source["id"] != selected_id: continue
    for item in source["files"]:
        if item.get("role") != "board" or not item["path"].endswith(".kicad_pcb"): continue
        try:
            board = pcbnew.LoadBoard(str(root / item["local_path"]))
            if board is None: raise ValueError("KiCad rejected the board")
            tracks = list(board.GetTracks())
            footprints = list(board.GetFootprints())
            bounds = board.GetBoardEdgesBoundingBox()
            output.append({"id": source["id"], "status": "read", "reader": pcbnew.GetBuildVersion(),
                "components": len(footprints), "pads": sum(len(list(fp.Pads())) for fp in footprints),
                "tracks": sum(t.GetClass() == "PCB_TRACK" for t in tracks),
                "arcs": sum(t.GetClass() == "PCB_ARC" for t in tracks),
                "vias": sum(t.GetClass() == "PCB_VIA" for t in tracks),
                "zones": len(list(board.Zones())), "nets": len(board.GetNetsByNetcode()) - 1,
                "copper_layers": board.GetCopperLayerCount(),
                "thickness_mm": pcbnew.ToMM(board.GetDesignSettings().GetBoardThickness()),
                "bounds_mm": [pcbnew.ToMM(v) for v in (bounds.GetX(), bounds.GetY(), bounds.GetRight(), bounds.GetBottom())],
                "model_references": sum(len(fp.Models()) for fp in footprints)})
        except Exception as exc: output.append({"id": source["id"], "status": "failed", "error": str(exc)})
        print(source["id"], output[-1]["status"], flush=True)
Path(sys.argv[2]).write_text(json.dumps(output, indent=2), encoding="utf-8")
