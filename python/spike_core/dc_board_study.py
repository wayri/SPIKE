# SPDX-License-Identifier: Apache-2.0
"""Offline explicit/source-authenticated board-volume DC composition."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from .dc_board_volume import compile_board_volume
from .dc_tetra_rt0 import solve_tetra_dc
from .dc_tetra_rt0_evidence import validate_tetra_dc

MODEL = "spike/dc-board-volume-model/v1"
SOURCE = "spike/source-board-volume-study/v1"
SCALABLE_MODEL = "spike/dc-board-volume-scalable-model/v1"
SCALABLE_SOURCE = "spike/source-board-volume-scalable-study/v1"


def require(condition, message):
    if not condition: raise ValueError(message)


def canonical(value):
    return json.loads(json.dumps(value, allow_nan=False))


def board_model(prepared, *, target_mm, max_cells, scalable=False):
    from shapely.geometry import mapping
    groups = [{"layer": layer, "net": net, **{k: deepcopy(record[k]) for k in
               ("thickness_mm", "z_mm", "conductivity_s_m", "source_inventory")},
               "geometry": mapping(record["geometry"])} for (layer, net), record in sorted(prepared["groups"].items())]
    def records(name):
        return [{k: mapping(v) if k == "geometry" else deepcopy(v) for k, v in row.items()}
                for row in prepared[name]]
    require(type(scalable) is bool, "Explicit scalable model profile required")
    raw = {"contract": SCALABLE_MODEL if scalable else MODEL, "groups": groups, "barrels": records("barrels"), "contacts": records("contacts"),
           "expected_axial_source_ids": sorted(prepared["expected_axial_source_ids"]),
           "target_mm": target_mm, "max_cells": max_cells}
    return json.loads(json.dumps(raw, allow_nan=False))


def compile_model(raw):
    from shapely.geometry import shape
    require(type(raw) is dict and set(raw) == {"contract", "groups", "barrels", "contacts", "expected_axial_source_ids", "target_mm", "max_cells"}
            and raw["contract"] in (MODEL, SCALABLE_MODEL), "Invalid board-volume model contract")
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    require(len(encoded) <= (64 if raw["contract"] == SCALABLE_MODEL else 16)*1024*1024 and type(raw["groups"]) is list and len(raw["groups"]) <= 128,
            "Board-volume model input budget exceeded")
    groups = {}
    for row in raw["groups"]:
        require(type(row) is dict and set(row) == {"layer", "net", "geometry", "thickness_mm", "z_mm", "conductivity_s_m", "source_inventory"},
                "Invalid board-volume group")
        key = (row["layer"], row["net"]); require(key not in groups, "Duplicate board copper group")
        groups[key] = {k: shape(v) if k == "geometry" else deepcopy(v) for k, v in row.items() if k not in ("layer", "net")}
    def records(name):
        require(type(raw[name]) is list and len(raw[name]) <= 4096, "Board geometry record budget exceeded")
        return [{k: shape(v) if k == "geometry" else deepcopy(v) for k, v in row.items()} for row in raw[name]]
    return compile_board_volume(groups, records("barrels"), records("contacts"),
        expected_axial_source_ids=raw["expected_axial_source_ids"], target_mm=raw["target_mm"], max_cells=raw["max_cells"],
        scalable=raw["contract"] == SCALABLE_MODEL)


def solve_board_model(raw):
    compiled = compile_model(raw)
    result = solve_tetra_dc(compiled["request"]); validate_tetra_dc(result)
    expected = math.fsum(v["mesh_volume_mm3"]*1e-9 for v in compiled["coverage"]["volumes"])
    actual = result["current_density_observable"]["physical_volume_m3"]
    require(abs(expected-actual) <= 1e-10*max(expected, actual), "Full selected-model physical volume differs")
    return {"contract": "spike/dc-board-volume-run/v1", "source_model": deepcopy(raw),
            "coverage": canonical(compiled["coverage"]), "result": result, "production_qualified": False,
            "complete_selected_model_volume": True, "source_authentication": "not_performed_by_pure_model_solver"}


def validate_board_run(run):
    require(run.get("contract") == "spike/dc-board-volume-run/v1" and run.get("production_qualified") is False
            and run.get("complete_selected_model_volume") is True
            and run.get("source_authentication") == "not_performed_by_pure_model_solver", "Board run scope differs")
    compiled = compile_model(run["source_model"])
    require(run["coverage"] == canonical(compiled["coverage"]) and run["result"]["source_request"] == compiled["request"],
            "Board result detached from source geometry/contact/coverage")
    validate_tetra_dc(run["result"])


def admit_source_config(config):
    require(type(config) is dict and set(config) == {"contract", "source_path", "source_sha256", "net_names", "electrodes",
            "plating_thickness_mm", "conductivity_s_m", "target_mm", "max_cells"} and config["contract"] in (SOURCE, SCALABLE_SOURCE),
            "Invalid source-board study contract")


def solve_source_board(config):
    from .dc_board_source import prepare_source_board
    admit_source_config(config)
    prepared = prepare_source_board(config["source_path"], config["source_sha256"], net_names=config["net_names"],
        electrodes=config["electrodes"], plating_thickness_mm=config["plating_thickness_mm"], conductivity_s_m=config["conductivity_s_m"])
    raw = board_model(prepared, target_mm=config["target_mm"], max_cells=config["max_cells"], scalable=config["contract"] == SCALABLE_SOURCE)
    run = solve_board_model(raw)
    require(hashlib.sha256(Path(config["source_path"]).read_bytes()).hexdigest() == config["source_sha256"],
            "Native board source changed during volume solve")
    return {"contract": "spike/source-board-volume-run/v1", "source_request": deepcopy(config), "run": run,
            "source_evidence": prepared["source_evidence"], "electrode_evidence": prepared["electrode_evidence"],
            "source_fill_evidence": canonical(prepared["source_fill_evidence"]),
            "model_assumptions": prepared["model_assumptions"], "source_revalidated_after_solve": True,
            "production_qualified": False, "full_board_pisi_ready": False}


def validate_source_board_run(record):
    from .dc_board_source import prepare_source_board
    require(record.get("contract") == "spike/source-board-volume-run/v1"
            and record.get("production_qualified") is False and record.get("full_board_pisi_ready") is False
            and record.get("source_revalidated_after_solve") is True, "Source board run scope differs")
    config = record["source_request"]
    admit_source_config(config)
    prepared = prepare_source_board(config["source_path"], config["source_sha256"], net_names=config["net_names"],
        electrodes=config["electrodes"], plating_thickness_mm=config["plating_thickness_mm"], conductivity_s_m=config["conductivity_s_m"])
    require(record["run"]["source_model"] == board_model(prepared, target_mm=config["target_mm"], max_cells=config["max_cells"], scalable=config["contract"] == SCALABLE_SOURCE)
            and record["source_evidence"] == prepared["source_evidence"]
            and record["electrode_evidence"] == prepared["electrode_evidence"]
            and record["source_fill_evidence"] == canonical(prepared["source_fill_evidence"])
            and record["model_assumptions"] == prepared["model_assumptions"], "Source geometry/electrode provenance detached")
    validate_board_run(record["run"])
