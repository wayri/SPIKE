"""Offline public-board import, source inventory and package round-trip checks."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = ROOT / "build/public-board-corpus"

def check(case, output):
    from python.spike_core.service_project_handlers import handle_project_request
    from python.spike_core.design_ir_v2 import DesignIRV2
    from python.spike_core.geometry_arrow import canonical_geometry_rows
    from python.spike_core.source_package import source_identity
    path = ROOT / case["local_path"]
    started = time.perf_counter()
    digest, size = source_identity(path) if path.is_dir() else (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size)
    record = {"id": case["id"], "path": case["local_path"], "format": case["format"],
              "sha256": digest, "bytes": size,
              "status": "failed", "stage": "import"}
    def request(method, params):
        response = handle_project_request(method, params, request_id="public-corpus", application_version="corpus-validation")
        if not response or not response.get("ok"): raise ValueError(json.dumps(response))
        return response["result"]
    try:
        imported = request("import_design_v2", {"path": str(path), "format_hint": case["format"],
            "options": case.get("options", {}), "include_snapshot": True})
        d = imported["design"]
        record.update(counts={k: len(d.get(k, [])) for k in ("components", "pads", "tracks", "arcs", "vias", "zones", "nets", "layers", "models")},
                      physical_layer_rows_with_thickness=sum(l.get("thickness_mm") is not None for l in d.get("layers", [])),
                      report=imported["report"], stage="roundtrip")
        (output / "import-report.json").write_text(json.dumps(imported["report"], indent=2), encoding="utf-8")
        if case["format"] == "odb++":
            snapshot_text = json.dumps(imported["snapshot"], ensure_ascii=False)
            (output / "board.spike-design.json").write_text(snapshot_text, encoding="utf-8")
            source_format, source_name = "spike-normalized", "board.spike-design.json"
        else:
            snapshot_text, source_format, source_name = path.read_text(encoding="utf-8-sig"), "kicad_pcb", path.name
        snapshot = {"format": "spike-project-package/v2", "project": {"name": case["id"]}, "analysis": {},
                    "design": {"source_format": source_format, "source_file": source_name, "source_board": snapshot_text}}
        saved = output / "roundtrip.spike"
        request("write_project_package", {"path": str(saved), "snapshot": snapshot, "generate_geometry_tables": True})
        opened = request("read_project_package", {"path": str(saved)})
        original_rows = canonical_geometry_rows(DesignIRV2.from_dict(d))
        reopened_rows = canonical_geometry_rows(DesignIRV2.from_dict(opened["canonical"]["design_ir"]))
        if original_rows != reopened_rows: raise ValueError("Canonical copper geometry changed across project round trip")
        if opened["project"]["design"]["source_board"] != snapshot_text:
            raise ValueError("Source board text changed across project round trip")
        record.update(status="imported", stage="complete", geometry_rows=len(original_rows), package_bytes=saved.stat().st_size,
                      package_roundtrip="passed", source_text_roundtrip=opened["project"]["design"]["source_board"] == snapshot_text)
    except Exception as exc:
        record.update(error=str(exc), traceback=traceback.format_exc(limit=5))
    record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    (output / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(case["id"], record["status"], record.get("counts", {}), record.get("error", "")[:300], flush=True)
    return record

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=BASE / "manifest.json")
    parser.add_argument("--case")
    parser.add_argument("--label", default="baseline")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases = manifest["cases"]
    if args.case:
        case = next(c for c in cases if c["id"] == args.case)
        output = BASE / args.label / case["id"]
        output.mkdir(parents=True, exist_ok=True)
        check(case, output)
        return
    results = []
    for case in cases:
        output = BASE / args.label / case["id"]
        output.mkdir(parents=True, exist_ok=True)
        with (output / "worker.log").open("w", encoding="utf-8") as stream:
            try:
                process = subprocess.run([sys.executable, __file__, "--manifest", str(args.manifest), "--case", case["id"], "--label", args.label],
                                         cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=300)
                if process.returncode: raise RuntimeError(f"Worker exited {process.returncode}")
                result = json.loads((output / "result.json").read_text(encoding="utf-8"))
            except Exception as exc:
                result = {"id": case["id"], "format": case["format"], "status": "failed", "stage": "process", "error": str(exc)}
                (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        results.append(result)
        print(case["id"], result["status"], result.get("counts", {}), result.get("error", "")[:180], flush=True)
        (BASE / args.label / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
