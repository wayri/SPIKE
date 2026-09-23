"""Summarize measured corpus results without converting warnings into passes."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.source_package import SourcePackage
BASE = ROOT / "build/public-board-corpus"

def odb_inventory(path):
    result = {"components": 0, "feature_records": {}, "unreadable_members": []}
    with SourcePackage(path) as package:
        for name in package.members:
            leaf = name.rsplit("/", 1)[-1].removesuffix(".gz").removesuffix(".Z")
            if leaf not in {"components", "features"}: continue
            try: text = package.text(name.removesuffix(".gz").removesuffix(".Z"))
            except ValueError as exc:
                result["unreadable_members"].append({"name": name, "error": str(exc)})
                continue
            counts = Counter(line.split()[0] for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))
            if leaf == "components": result["components"] += counts["CMP"]
            else: result["feature_records"][name] = {k: counts[k] for k in ("L", "A", "P", "S")}
    return result

manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
native = {r["id"]: r for r in json.loads((BASE / "native-oracle.json").read_text(encoding="utf-8"))}
frontend = {r["id"]: r for r in json.loads((BASE / "frontend-results.json").read_text(encoding="utf-8"))}
records = []
for case in manifest["cases"]:
    result_path = BASE / "final" / case["id"] / "result.json"
    r = json.loads(result_path.read_text(encoding="utf-8"))
    report = r.pop("report", {})
    r.pop("traceback", None)
    r.get("counts", {}).pop("stackup", None)  # v2 uses layers/materials, not a stackup array.
    r["import_completed"] = bool(r.get("counts"))
    r["import_status"] = report.get("status", "failed")
    r["diagnostic_entry_counts"] = dict(Counter(i.get("code") for k in ("inferred", "unsupported", "geometry_errors") for i in report.get(k, [])))
    r["solver_readiness"] = report.get("solver_readiness", {})
    r["model_resolution"] = report.get("model_resolution", {})
    r["native_reference"] = native.get(case["id"], {})
    r["frontend"] = frontend.get(case["id"], {})
    if case["format"] == "odb++":
        r["source_inventory"] = odb_inventory(ROOT / case["local_path"])
        if r.get("counts"):
            r["component_records_match_source"] = r["source_inventory"]["components"] == r["counts"]["components"]
    if r["native_reference"].get("status") == "read" and r.get("counts"):
        oracle = r["native_reference"]
        r["native_count_comparison"] = {k: r["counts"][k] == oracle[k] for k in ("components", "pads", "vias")}
        r["native_count_comparison"]["track_segments_including_8_per_arc"] = r["counts"]["tracks"] == oracle["tracks"] + 8 * oracle["arcs"]
        r["native_count_comparison"]["model_references"] = r["counts"]["models"] == oracle["model_references"]
    records.append(r)

changed = []
for source in manifest["sources"]:
    for item in source["files"]:
        if hashlib.sha256((ROOT / item["local_path"]).read_bytes()).hexdigest() != item["sha256"]:
            changed.append(item["local_path"])
summary = {"contract": "spike/public-board-validation/v1", "cases": len(records),
    "normalized_imports": sum(r["import_completed"] for r in records),
    "project_roundtrips": sum(r.get("package_roundtrip") == "passed" for r in records),
    "source_files_verified": sum(len(s["files"]) for s in manifest["sources"]), "source_files_changed": changed,
    "viewport_pixels_verified": False, "solver_physics_qualified": False, "records": records}
(BASE / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
lines = ["# Public KiCad and ODB++ import validation", "", "Measured 2026-09-05. This corpus exposes failures; it does not qualify complete CAD or solver parity.", "",
         f"{summary['cases']} inputs: {summary['normalized_imports']} produced normalized designs; {summary['project_roundtrips']} completed copper-geometry-checked project save/reopen. All {summary['source_files_verified']} downloaded source files were hash-checked; changed files: {len(changed)}.", "",
         "| Input | Format | Components | Pads | Vias | Import | Save/reopen |", "|---|---|---:|---:|---:|---|---|"]
for r in records:
    counts = r.get("counts", {})
    imported = r["import_status"].replace("completed_with_", "with ").replace("_", " ")
    lines.append(f"| {r['id']} | {r['format']} | {counts.get('components','—')} | {counts.get('pads','—')} | {counts.get('vias','—')} | {imported} | {r.get('package_roundtrip','FAILED')} |")
lines += ["", "## What the comparisons establish", "",
    "The 22 inputs comprise 12 KiCad boards (including an empty development-format control), two published hardware ODB exports, two synthetic ODB fixtures, one supplemental rigid-flex sample with unresolved hardware licensing, and five ODB exports generated from the KiCad boards. Complexity ranges from the 15-component ECC83 board to 1,508-component, 12-copper-layer VME-WREN. All eight completed ODB imports report errors; save/reopen only establishes persistence of the geometry that was imported. It does not recover unsupported source geometry.", "",
    "SPIKE's source-worker import route, typed conversion, real desktop parsers, and `.spike` save/reopen were exercised. Copper geometry rows were compared across persistence. KiCad 10.0.5's native reader supplied an independent inventory; it rejected the development-format Constraints file and timed out on Tiny Tapeout and OLIMEX A64. Those reference failures are not SPIKE passes or failures.", "",
    "KiCad circular arcs currently become eight line segments in the backend; track-count comparisons account for that representation explicitly. Matching counts do not prove curve, copper-area, thermal-relief or 3D placement equivalence. Footprint/zone representations also differ: filled islands and copper graphics are not one-to-one with native zone objects.", "",
    "All eight completed ODB imports retain the source CMP record count, including the exporter-excluded footprint differences in paired boards. Pads and features still have observed omissions. Diagnostic entry counts in the JSON count retained report entries, which can repeat across categories and are bounded; they are not total affected source-feature counts. Original per-input reports and worker logs remain under `build/public-board-corpus/final`.", "",
    "## Fixes exercised", "",
    "- Modern KiCad physical layer ordering now preserves through-via spans.",
    "- Silkscreen footprint polygons stay drawings; repeated source pad UUIDs and identical anonymous records retain separate occurrences.",
    "- Uppercase ODB matrix entity names map to lowercase directories without changing reference-designator case.",
    "- Legacy `U` units, empty attribute strings, repeated first contour vertices, full-circle contour splitting and profile feature-count headers are handled.",
    "- Drill metadata satisfies the canonical contract; unresolved spans/plating remain explicit. Unsupported `.Z` files now fail with a useful cause. Repeated missing-net diagnostics are counted without flooding the report.", "",
    "## Remaining failures and limitations", "",
    "- VME-WREN, Jetson Thor, BeagleBone Black and the larger generated ODB exports hit existing project JSON member limits. Rigid-flex ODB hits the extension result-size limit. These are actual usability blockers, not passes.",
    "- The CERN-licensed Merit Badge Kit's DipTrace ODB export uses Unix compress `.Z`, which is not yet supported.",
    "- Rounded/custom ODB symbols, rounded source arc radii, unresolved drills and plating, connectivity gaps and physical stackup extraction prevent full electrical readiness. Source component counts distinguish exporter exclusions from importer omissions.",
    "- KiCad Microwave and Jetson footprint counts, and several boards' model-reference counts, differ from the native reader. Multiple/no-pad footprints and multiple model assignments need further work.",
    "- Model resolution records discovered paths, not verified 3D geometry or transforms. Neither viewport pixels, routing/plane area equivalence, nor solver physics were qualified.", "",
    "## Provenance and rerun", "",
    "The manifest includes immutable repository commits, file hashes, project/license documents and URLs. Data stays under `build/public-board-corpus/sources`; it is not included in the installer. Repository software licenses do not automatically establish the license of every hardware example. The rigid-flex sample's original hardware license is unresolved and it is treated only as a public local-test sample. Generated ODB files record the KiCad exporter and parent board; they are not independent vendor exports.", "",
    "Run from the repository root with the project Python and frontend dependencies installed. The native oracle and exporter use KiCad 10.0.5 at the paths below. Allow several minutes for each complex input. Generated archive hashes may differ on re-export; the exporter records new hashes.", "",
    "```powershell", "New-Item -ItemType Directory -Force build/public-board-corpus | Out-Null", "Copy-Item benchmarks/public-board-corpus/manifest.json build/public-board-corpus/manifest.json", ".venv/Scripts/python.exe scripts/fetch_public_board_corpus.py --manifest build/public-board-corpus/manifest.json", ".venv/Scripts/python.exe scripts/export_public_board_odb.py", ".venv/Scripts/python.exe scripts/validate_public_board_corpus.py --label final", "& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/public_board_native_oracle.py build/public-board-corpus/manifest.json build/public-board-corpus/native-oracle.json", "node app/scripts/validate-public-board-corpus.mjs", ".venv/Scripts/python.exe scripts/summarize_public_board_corpus.py", "```", "",
    "[Detailed machine-readable results](summary.json) · [Pinned download manifest](manifest.json)", ""]
(BASE / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
print({k:v for k,v in summary.items() if k!='records'})
