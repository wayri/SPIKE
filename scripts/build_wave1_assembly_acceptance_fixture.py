"""Build the deterministic packaged Wave 1 desktop assembly acceptance fixture."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.dependencies import dependency_status
from python.spike_core.design_ir_v2 import AssemblyIRV1, DesignIRV2
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.service_project_handlers import handle_project_request


APP_VERSION = "0.2.5"


def _freecad_executable() -> Path:
    record = next(
        (item for item in dependency_status()["dependencies"] if item.get("id") == "freecad"),
        {},
    )
    path = Path(str(record.get("path", "")))
    if record.get("status") != "ready" or not path.is_file():
        raise RuntimeError("The locked FreeCAD runtime is required to build the Wave 1 fixture.")
    return path


def _make_step_sources(output: Path) -> tuple[Path, Path]:
    script = output / "make_wave1_shapes.py"
    enclosure = output / "wave1-enclosure.step"
    lid = output / "wave1-lid.step"
    script.write_text(
        "import FreeCAD as App\n"
        "import Part\n"
        "from pathlib import Path\n"
        "root=Path(__file__).parent\n"
        "doc=App.newDocument('SPIKE_WAVE1_FIXTURE')\n"
        "enclosure=doc.addObject('Part::Feature','Enclosure')\n"
        "enclosure.Shape=Part.makeBox(50.0,35.0,20.0)\n"
        "lid=doc.addObject('Part::Feature','Lid')\n"
        "lid.Shape=Part.makeBox(46.0,31.0,3.0)\n"
        "doc.recompute()\n"
        "Part.export([enclosure],str(root/'wave1-enclosure.step'))\n"
        "Part.export([lid],str(root/'wave1-lid.step'))\n"
        "App.closeDocument(doc.Name)\n",
        encoding="utf-8",
    )
    executable = _freecad_executable()
    completed = subprocess.run(
        [
            str(executable), "--console",
            "--user-cfg", str(output / "freecad-user.cfg"),
            "--system-cfg", str(output / "freecad-system.cfg"),
            str(script),
        ],
        cwd=output,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0 or not enclosure.is_file() or not lid.is_file():
        detail = completed.stderr.decode("utf-8", "replace")[-2000:]
        raise RuntimeError(f"FreeCAD failed to create the Wave 1 STEP fixtures: {detail}")
    script.unlink(missing_ok=True)
    (output / "freecad-user.cfg").unlink(missing_ok=True)
    (output / "freecad-system.cfg").unlink(missing_ok=True)
    cache = output / "__pycache__"
    if cache.is_dir():
        for generated in cache.glob("make_wave1_shapes.*.pyc"):
            generated.unlink()
        try:
            cache.rmdir()
        except OSError:
            pass
    return enclosure, lid


def _call(method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = handle_project_request(
        method, params, request_id=f"wave1-fixture-{method}", application_version=APP_VERSION,
    )
    if not response or not response.get("ok"):
        raise RuntimeError(f"{method} failed: {(response or {}).get('error', 'no response')}")
    return response["result"]


def _board_design(source: Path, package_name: str) -> dict[str, Any]:
    design = DesignIRV2.from_v1(import_kicad_design(str(source))).to_dict()
    digest = str(design["source"]["source_digest"])
    suffix = "".join(Path(package_name).suffixes[-2:])
    design["source"]["artifact_path"] = f"package:sources/{digest}{suffix}"
    return design


def build(output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    project_path = output / "wave1-assembly-acceptance.spike"
    board_a_path = ROOT / "app" / "public" / "demo" / "MODULAR-BUS-NIB.kicad_pcb"
    board_b_path = ROOT / "app" / "public" / "demo" / "ebrake1.kicad_pcb"
    board_a = _board_design(board_a_path, board_a_path.name)
    board_b = _board_design(board_b_path, board_b_path.name)
    assembly = AssemblyIRV1.from_dict({
        "assembly_id": "wave1-acceptance-assembly",
        "name": "Wave 1 packaged assembly acceptance",
        "boards": [
            {
                "id": "controller-board", "name": "Controller board", "design_id": board_a["design_id"],
                "frame": {"frame_id": "controller-board-frame", "parent_frame_id": "assembly"},
            },
            {
                "id": "load-board", "name": "Load board", "design_id": board_b["design_id"],
                "frame": {
                    "frame_id": "load-board-frame", "parent_frame_id": "assembly",
                    "transform": [1, 0, 0, 90, 0, 1, 0, 0, 0, 0, 1, 8, 0, 0, 0, 1],
                },
            },
        ],
        "harnesses": [{
            "id": "power-harness", "name": "Power harness",
            "endpoint_a": "controller-board:J1", "endpoint_b": "load-board:J2",
            "length_mm": 140.0, "pin_map": {"1": "1", "2": "2"},
        }],
        "connector_mappings": [{
            "id": "power-connector-map", "name": "Power connector map", "kind": "connector-pin-map",
            "data": {"endpoint_a": "controller-board:J1", "endpoint_b": "load-board:J2", "pins": {"1": "1", "2": "2"}},
        }],
        "rigid_flex_links": [{
            "id": "fixture-flex-link", "name": "Acceptance flex link", "kind": "rigid-flex-link",
            "data": {"board_a_id": "controller-board", "board_b_id": "load-board", "bend_radius_mm": 4.0},
        }],
    }).to_dict()
    manifest = write_spike_package(
        project_path,
        {
            "project": {"id": "wave1-assembly-acceptance", "name": project_path.name},
            "design_ir": board_a,
            "assembly_ir": assembly,
            "assembly_designs": {
                "contract": "spike/assembly-designs/v1",
                "active_design_id": board_a["design_id"],
                "designs": [board_a, board_b],
            },
            "audit": [{"event": "wave1_acceptance_fixture_created", "solver_ready": False}],
        },
        source_artifacts={board_a_path.name: board_a_path.read_bytes(), board_b_path.name: board_b_path.read_bytes()},
        application_version=APP_VERSION,
    )
    enclosure, lid = _make_step_sources(output)
    parts: list[dict[str, Any]] = []
    shapes: list[dict[str, Any]] = []
    for index, (source, name, part_type, z_mm) in enumerate((
        (enclosure, "Acceptance enclosure", "enclosure", 0.0),
        (lid, "Acceptance lid", "mechanical", 35.0),
    )):
        attached = _call("attach_mcad_part_to_project", {
            "project_path": str(project_path), "source_path": str(source),
            "name": name, "part_type": part_type, "material_id": "aluminium-6061",
            "frame": {
                "frame_id": f"wave1-part-{index}-frame", "parent_frame_id": "assembly",
                "transform": [1, 0, 0, 15, 0, 1, 0, 20, 0, 0, 1, z_mm, 0, 0, 0, 1],
            },
        })
        manifest = attached["manifest"]
        part = attached["part"]
        extracted = _call("extract_mcad_package_shape_in_project", {
            "project_path": str(project_path),
            "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
            "part_id": part["id"],
        })
        manifest = extracted["manifest"]
        preview = _call("generate_mcad_selector_preview_in_project", {
            "project_path": str(project_path),
            "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
            "shape_id": extracted["shape_id"],
        })
        manifest = preview["manifest"]
        visual = _call("tessellate_mcad_part_in_project", {
            "project_path": str(project_path),
            "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
            "part_id": part["id"],
        })
        manifest = visual["manifest"]
        parts.append({"part_id": part["id"], "name": name, "source": source.name})
        shapes.append({"part_id": part["id"], "shape_id": extracted["shape_id"], "entity_count": extracted["entity_count"]})

    visual_source = ROOT / "app" / "public" / "demo" / "models" / "ebrake1_board.glb"
    direct_visual = _call("attach_mcad_part_to_project", {
        "project_path": str(project_path), "source_path": str(visual_source),
        "name": "Direct GLB reference", "part_type": "fixture", "material_id": "",
        "frame": {
            "frame_id": "wave1-direct-glb-frame", "parent_frame_id": "load-board-frame",
            "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 4, 0, 0, 0, 1],
        },
    })
    manifest = direct_visual["manifest"]
    parts.append({"part_id": direct_visual["part"]["id"], "name": "Direct GLB reference", "source": visual_source.name})

    reopened = read_project(project_path, include_members=True)
    summary = {
        "contract": "spike/wave1-assembly-acceptance-fixture/v1",
        "project": project_path.name,
        "manifest_payload_sha256": manifest["manifest_payload_sha256"],
        "design_ids": [board_a["design_id"], board_b["design_id"]],
        "board_ids": [item["id"] for item in reopened.payload["assembly_ir"]["boards"]],
        "parts": parts,
        "shapes": shapes,
        "member_count": len(reopened.members),
        "topology_ready": True,
        "visual_only": True,
        "solver_ready": False,
    }
    (output / "wave1-assembly-acceptance.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return project_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "wave1-assembly-acceptance")
    args = parser.parse_args()
    project = build(args.output_dir.resolve())
    print(f"Wave 1 packaged assembly acceptance fixture: {project}")
    print("Qualification: topology-ready and visualizable; explicitly not solver-ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
