# SPDX-License-Identifier: Apache-2.0
"""Expand an authenticated retained multi-design project into 10/20-board memory fixtures."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core import __version__
from python.spike_core.project_package import PackageLimits, _source_member_name, read_project, write_spike_package
from python.spike_core.service_project import import_design
from python.spike_core.service_project_handlers import handle_project_request

DEFAULT_SOURCE = ROOT / "build/rpi-hat-acceptance-20261002/cm4io-sailor-hat.spike"
DEFAULT_OUTPUT = ROOT / "output/large-board-memory-benchmark/fixtures"
DEFAULT_MARBLE_SOURCE = ROOT / "app/.tmp/product-promo-capture/marble/Marble.kicad_pcb"


def frame(template: dict, index: int) -> dict:
    result = copy.deepcopy(template)
    transform = [1.0, 0.0, 0.0, float(index % 5) * 140.0,
                 0.0, 1.0, 0.0, float(index // 5) * 120.0,
                 0.0, 0.0, 1.0, 0.0,
                 0.0, 0.0, 0.0, 1.0]
    result["frame_id"] = f"memory-board-{index + 1}-frame"
    result["transform"] = transform
    return result


def prepare(source: Path, destination: Path, count: int, distinct: bool) -> dict:
    if count not in (10, 20):
        raise ValueError("Only the bounded 10 and 20 occurrence cases are supported.")
    loaded = read_project(source)
    assembly = loaded.payload.get("assembly_ir")
    designs = loaded.payload.get("assembly_designs", {}).get("designs", [])
    if not isinstance(assembly, dict) or len(assembly.get("boards", [])) < 1 or len(designs) < (2 if distinct else 1):
        raise ValueError("The source must be an authenticated retained assembly with the requested design diversity.")
    templates = assembly["boards"][:2 if distinct else 1]
    boards = []
    for index in range(count):
        template = templates[index % len(templates)]
        board = copy.deepcopy(template)
        board["id"] = f"memory-board-{index + 1}"
        board["name"] = f"{template.get('name', template['design_id'])} · memory {index + 1}"
        board["frame"] = frame(template.get("frame", {}), index)
        boards.append(board)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    response = handle_project_request("update_assembly_structure_in_project", {
        "project_path": str(destination),
        "expected_manifest_payload_sha256": loaded.manifest["manifest_payload_sha256"],
        "boards": boards,
        # Links in the two-board source refer to source occurrence IDs. They cannot be
        # truthfully duplicated without new endpoint mappings, so this render/memory
        # fixture keeps the real designs and intentionally has no electrical links.
        "harnesses": [], "connector_mappings": [], "rigid_flex_links": [],
    }, request_id=f"memory-{count}-{'distinct' if distinct else 'repeated'}", application_version="benchmark-preparation")
    if not response.get("ok"):
        destination.unlink(missing_ok=True)
        raise RuntimeError(response)
    reopened = read_project(destination)
    retained = reopened.payload["assembly_designs"]["designs"]
    result = {
        "path": str(destination.relative_to(ROOT)),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "bytes": destination.stat().st_size,
        "occurrences": len(reopened.payload["assembly_ir"]["boards"]),
        "distinct_designs_referenced": len({item["design_id"] for item in reopened.payload["assembly_ir"]["boards"]}),
        "retained_designs": [{"design_id": item["design_id"], "name": item.get("name", item["design_id"])} for item in retained],
        "source": str(source.relative_to(ROOT)),
    }
    return result


def prepare_marble(source: Path, destination: Path, count: int, design: dict) -> dict:
    retained = copy.deepcopy(design)
    digest = retained["source"]["source_digest"]
    retained["source"]["artifact_path"] = "package:" + _source_member_name(source.name, digest)
    boards = [{
        "id": f"marble-{index + 1}", "name": f"Marble v1.4.4 · memory {index + 1}",
        "design_id": retained["design_id"],
        "frame": frame({"units": "mm", "handedness": "right"}, index),
    } for index in range(count)]
    payload = {
        "project": {"id": f"marble-memory-{count}", "name": f"Marble v1.4.4 repeated {count}"},
        "design_ir": retained,
        "assembly_ir": {"contract": "spike/assembly-ir/v1", "assembly_id": f"marble-memory-{count}",
                        "name": f"Marble repeated {count}", "parts": [], "boards": boards},
        "assembly_designs": {"contract": "spike/assembly-designs/v1", "active_design_id": retained["design_id"],
                             "designs": [retained]},
        "audit": [{"event": "large_assembly_memory_fixture", "source": str(source.relative_to(ROOT)),
                   "occurrences": count, "distinct_designs": 1, "geometry": "production KiCad import"}],
    }
    assembly_design_bytes = len(json.dumps(payload["assembly_designs"], separators=(",", ":"),
                                           ensure_ascii=False).encode("utf-8"))
    retained_design_limit = PackageLimits().max_design_ir_json_bytes
    if assembly_design_bytes > retained_design_limit:
        destination.unlink(missing_ok=True)
        return {
            "path": str(destination.relative_to(ROOT)), "status": "unavailable",
            "reason": "production_retained_design_limit",
            "assembly_design_bytes": assembly_design_bytes, "max_design_ir_json_bytes": retained_design_limit,
            "occurrences": count, "distinct_designs_referenced": 1,
            "source": str(source.relative_to(ROOT)), "source_digest": retained["source"]["source_digest"],
            "component_count": len(retained.get("components", [])), "track_count": len(retained.get("tracks", [])),
            "pad_count": len(retained.get("pads", [])),
            "component_model_assignment_count": sum(bool(component.get("model_ids"))
                                                    for component in retained.get("components", [])),
        }
    manifest = write_spike_package(destination, payload, source_artifacts={source.name: source.read_bytes()},
                                   application_version=__version__)
    reopened = read_project(destination, include_members=True)
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    retained_sha256 = hashlib.sha256(canonical(retained).encode("utf-8")).hexdigest()
    reopened_design_sha256 = hashlib.sha256(canonical(reopened.payload["design_ir"]).encode("utf-8")).hexdigest()
    reopened_retained = reopened.payload["assembly_designs"]
    reopened_assembly_sha256 = hashlib.sha256(canonical(reopened_retained["designs"][0]).encode("utf-8")).hexdigest()
    if retained_sha256 != reopened_design_sha256 or retained_sha256 != reopened_assembly_sha256:
        destination.unlink(missing_ok=True)
        raise ValueError("Marble retained design records changed during package round trip.")
    source_path = retained["source"]["artifact_path"].removeprefix("package:")
    if reopened.members.get(source_path) != source.read_bytes():
        destination.unlink(missing_ok=True)
        raise ValueError("Marble embedded source bytes changed during package round trip.")
    if len(reopened_retained["designs"]) != 1 or reopened_retained["active_design_id"] != retained["design_id"]:
        destination.unlink(missing_ok=True)
        raise ValueError("Marble retained design ownership changed during package round trip.")
    source_models = sorted((component.get("id"), tuple(component.get("model_ids", [])))
                           for component in retained.get("components", []))
    reopened_models = sorted((component.get("id"), tuple(component.get("model_ids", [])))
                             for component in reopened.payload["design_ir"].get("components", []))
    if source_models != reopened_models:
        destination.unlink(missing_ok=True)
        raise ValueError("Marble component model assignments changed during package round trip.")
    return {
        "path": str(destination.relative_to(ROOT)), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "bytes": destination.stat().st_size, "manifest_payload_sha256": manifest["manifest_payload_sha256"],
        "occurrences": len(reopened.payload["assembly_ir"]["boards"]), "distinct_designs_referenced": 1,
        "retained_designs": [{"design_id": retained["design_id"], "name": retained.get("name", "Marble")}],
        "source": str(source.relative_to(ROOT)),
        "source_digest": retained["source"]["source_digest"],
        "retained_design_sha256": retained_sha256,
        "assembly_design_bytes": assembly_design_bytes,
        "component_count": len(retained.get("components", [])), "track_count": len(retained.get("tracks", [])),
        "pad_count": len(retained.get("pads", [])),
        "net_count": len(retained.get("nets", [])), "via_count": len(retained.get("vias", [])),
        "zone_count": len(retained.get("zones", [])), "drawing_count": len(retained.get("drawings", [])),
        "component_model_assignment_count": sum(bool(row[1]) for row in source_models),
        "embedded_source_bytes_verified": source.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--marble-source", type=Path, default=DEFAULT_MARBLE_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    records = []
    marble_source = args.marble_source.resolve()
    marble = import_design(str(marble_source), with_report=True)
    if not marble.get("ok", True) or not isinstance(marble.get("design"), dict):
        raise RuntimeError(f"Production Marble import failed: {marble}")
    marble_design = marble["design"]
    for count in (10, 20):
        records.append(prepare_marble(marble_source, output / f"marble-repeated-{count}.spike", count, marble_design))
        for distinct in (False, True):
            label = "distinct" if distinct else "repeated"
            records.append(prepare(source, output / f"cm4-sailor-{label}-{count}.spike", count, distinct))
    manifest = {"contract": "spike/large-assembly-memory-fixtures/v1", "fixtures": records}
    target = output / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
