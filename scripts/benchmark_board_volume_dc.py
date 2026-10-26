# SPDX-License-Identifier: Apache-2.0
"""Separate explicit full-pad EBrake24V/Marble DC studies; never board qualification."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.solvers.power_integrity.dc.dc_board_source import prepare_board_sources, authenticate_board_pads
from python.spike_core.solvers.power_integrity.dc.dc_board_study import board_model, solve_board_model
from python.spike_core.kicad_source_evidence import read_kicad_board_pad_inventory
from python.spike_core.kicad_importer import import_kicad_design

BOARDS = {
    "ebrake": ("app/public/demo/ebrake1.kicad_pcb", "d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca"),
    "marble": ("build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb", "3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512")}
STUDIES = {
    "ebrake-24v-fullpads": {"board": "ebrake", "net": "24V", "electrodes":
        [("J13.1", "B.Cu", "bottom", 1.), ("Q2.2", "B.Cu", "bottom", -.25),
         ("Q4.2", "B.Cu", "bottom", -.25), ("Q6.2", "B.Cu", "bottom", -.25), ("Q8.2", "B.Cu", "bottom", -.25)],
        "scope": "Separate owner-selected24V rail, unit-total-current copper transfer; operating device loads not inferred."},
    "marble-1v0-fullpads": {"board": "marble", "net": "+1V0", "electrodes":
        [("U1.P14", "F.Cu", "top", .5), ("U1.K8", "F.Cu", "top", -.5)],
        "scope": "Separate same-net0.5A copper transfer at the original positive-rail pin locations; physical ground return not qualified."},
    "marble-reviewed-net-fullpads": {"board": "marble", "net": "Net-(C383-Pad1)", "electrodes":
        [("U37.18", "B.Cu", "bottom", 1.), ("R195.1", "F.Cu", "top", -1.)],
        "scope": "Separate full-pad version of the reviewed U37.18/R195.1 DC probe; not a full-board or AC/SI result."}}


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(folder, board_name):
    relative, pinned = BOARDS[board_name]; source = ROOT/relative
    report = {"contract": "spike/source-board-volume-audit/v1", "board": board_name, "source_path": relative,
              "source_sha256_before": sha(source), "production_qualified": False, "full_board_pisi_ready": False,
              "original_point_studies_modified": False, "studies": {}}
    if report["source_sha256_before"] != pinned: raise ValueError("Pinned board changed; review source identity")
    start = time.perf_counter()
    try:
        print(board_name+": authenticating native pad/via inventory", flush=True)
        inventory = read_kicad_board_pad_inventory(source, pinned)
        print(board_name+": importing current source", flush=True)
        design = import_kicad_design(str(source)); authenticate_board_pads(design, inventory)
        report["native_inventory"] = {"pads": inventory["pad_count"], "vias": inventory["via_count"], "authenticated": True}
    except Exception as error:
        report["source_admission"] = {"status": "blocked", "exception": type(error).__name__, "message": str(error),
                                      "traceback": traceback.format_exc()}
        design = None
    for identity, study in STUDIES.items():
        if study["board"] != board_name: continue
        outcome = {"scope": study["scope"], "net": study["net"], "status": "blocked", "stage_complete": False,
                   "production_qualified": False, "model_assumptions": {"plating_thickness_mm": .025,
                    "conductivity_s_m": 5.8e7, "target_mm": 2., "max_cells": 5000}}
        report["studies"][identity] = outcome
        if design is None:
            outcome["blocker"] = "Native source admission failed before finite electrode/volume construction"; continue
        try:
            electrodes = []
            for pin, layer, side, current in study["electrodes"]:
                pads = [p for p in design.pads if p.get("component_pad") == pin and p.get("net_name") == study["net"]]
                if len(pads) != 1: raise ValueError("Source pin/net identity missing or ambiguous: "+pin)
                electrodes.append({"id": pin, "pad_id": pads[0]["id"], "layer": layer, "side": side, "current_a": current})
            outcome["explicit_electrodes"] = electrodes
            print(identity+": preparing all selected source copper and barrel gaps", flush=True)
            prepared = prepare_board_sources(design, net_names=[study["net"]], electrodes=electrodes,
                plating_thickness_mm=.025, conductivity_s_m=5.8e7)
            outcome["electrode_evidence"] = prepared["electrode_evidence"]
            outcome["source_fill_evidence"] = prepared["source_fill_evidence"]
            outcome["source_counts"] = {"groups": len(prepared["groups"]), "barrel_gaps": len(prepared["barrels"]),
                                        "axial_sources": len(prepared["expected_axial_source_ids"])}
            model = board_model(prepared, target_mm=2., max_cells=5000)
            model_path = folder/(identity+".model.json"); model_path.write_text(json.dumps(model, indent=2)+"\n", encoding="utf-8")
            outcome["model"] = model_path.relative_to(ROOT).as_posix(); outcome["model_sha256"] = sha(model_path)
            print(identity+": compiling/solving full selected volume", flush=True)
            run = solve_board_model(model)
            path = folder/(identity+".result.json"); path.write_text(json.dumps(run, indent=2)+"\n", encoding="utf-8")
            outcome.update({"status": "discrete_run_verified", "result": path.relative_to(ROOT).as_posix(), "result_sha256": sha(path),
                            "acceptance": "Single explicit model only; mesh refinement and real-board acceptance remain open"})
        except Exception as error:
            outcome.update({"blocker": str(error), "exception": type(error).__name__, "traceback": traceback.format_exc()})
    report["elapsed_s"] = time.perf_counter()-start; report["source_sha256_after"] = sha(source)
    report["source_unchanged"] = report["source_sha256_before"] == report["source_sha256_after"]
    path = folder/(board_name+"-audit.json"); path.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"board": board_name, "source_unchanged": report["source_unchanged"],
                      "studies": {k: {"status": v["status"], "blocker": v.get("blocker")} for k, v in report["studies"].items()}}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--board", choices=BOARDS, required=True)
    args = parser.parse_args(); folder = args.output.resolve()
    if folder.exists() or not folder.is_relative_to(ROOT): parser.error("Choose a fresh output folder in the repository")
    folder.mkdir(parents=True)
    execute(folder, args.board)


if __name__ == "__main__": main()
