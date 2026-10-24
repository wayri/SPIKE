# SPDX-License-Identifier: Apache-2.0
"""OpenEMS PI/SI workflow extension."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python.spike_core.contracts import AnalysisSpec, SpiDeR
from extensions.openems_suite.engine import (
    _validate_openems_case,
    prepare_openems_case,
    run_openems_case,
)
from extensions.openems_suite.openems_adapter_source import OPENEMS_DRIVER
from extensions.openems_suite.workspace_results import mesh_envelope, solve_envelope
from python.spike_core.extension_analysis_results import design_binding
import hashlib


MODES = {"openems-pi": "pi", "openems-si": "si", "openems-em": "emi"}
SOLVE_MODES = {"openems-pi-solve": "pi", "openems-si-solve": "si", "openems-em-solve": "emi"}


def _mapping(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def _em_workflow(contribution: str, context: dict) -> dict:
    design = SpiDeR(**_mapping(context.get("design"), "design"))
    parameters = _mapping(context.get("parameters"), "parameters")
    analysis = _mapping(parameters.get("analysis"), "analysis")
    if not analysis.get("net_names") or not isinstance(analysis["net_names"], list):
        raise ValueError("analysis.net_names must select one or more complete nets.")
    spec = AnalysisSpec(**{**analysis, "mode": MODES[contribution], "solver_id": "external.openems"})
    options = _mapping(parameters.get("engine_options", {}), "engine_options")
    operation = parameters.get("operation", "preflight")
    if operation not in {"preflight", "prepare", "run"}:
        raise ValueError("operation must be preflight, prepare, or run.")
    if operation == "preflight":
        validation = _validate_openems_case(design, spec, options)
        return {"operation": operation, "domain": MODES[contribution], "validation": validation,
                "status": "ready_to_run" if validation["can_run"] else "review_required"}
    prepared = prepare_openems_case(design, spec, options=options)
    if operation == "prepare" or prepared.get("status") != "ready_to_run":
        return {"operation": operation, "domain": MODES[contribution], "case": prepared,
                "status": prepared["status"]}
    # The extension host has a 3600 s cap; keep the contained engine run below it.
    result = run_openems_case(prepared["case_dir"], timeout_seconds=3300)
    return {"operation": operation, "domain": MODES[contribution], "case_dir": prepared["case_dir"],
            "status": result.get("status", "failed"), "result": result}


def execute(request: dict) -> dict:
    if request.get("contract") != "spike/extension/v1":
        raise ValueError("Unsupported extension request contract.")
    contribution = request.get("contribution_id")
    context = _mapping(request.get("context"), "context")
    if contribution in {*SOLVE_MODES, "openems-mesh", "openems-preview"}:
        return _workspace_workflow(request)
    if contribution in MODES:
        data = _em_workflow(contribution, context)
    else:
        raise ValueError("Unknown OpenEMS Suite contribution.")
    return {"contract": "spike/extension-result/v1",
            "status": "completed" if data["status"] in {"completed", "ready_to_run"} else "completed_with_warnings",
            "title": "OpenEMS Suite: " + str(contribution).removeprefix("openems-").upper(),
            "data": data}


def _workspace_workflow(request):
    context = request["context"]
    parameters = _mapping(context.get("parameters"), "parameters")
    analysis = _mapping(parameters.get("analysis"), "analysis")
    if not isinstance(analysis.get("net_names"), list) or not analysis["net_names"]:
        raise ValueError("analysis.net_names must select one or more complete nets.")
    contribution = request["contribution_id"]
    if contribution != "openems-preview" and context.get("design_binding") != design_binding(context.get("design")):
        raise ValueError("OpenEMS mesh/solve requires the current host design binding before execution.")
    mode = SOLVE_MODES.get(contribution, analysis.get("mode", "emi"))
    if mode not in {"pi", "si", "emi"}:
        raise ValueError("OpenEMS mode must be pi, si or emi.")
    spec = AnalysisSpec(**{**analysis, "mode":mode, "solver_id":"external.openems"})
    if contribution in SOLVE_MODES and len(spec.options.get("ports",[]))**2*spec.frequency_points > 250000:
        raise ValueError("OpenEMS network exchange exceeds the 250000-entry matrix bound; reduce ports or sweep points.")
    options = _mapping(parameters.get("engine_options", {}), "engine_options")
    prepared = prepare_openems_case(SpiDeR(**_mapping(context.get("design"), "design")), spec, options=options)
    if contribution == "openems-preview":
        return {"contract":"spike/extension-result/v1", "status":"completed_with_warnings", "title":"Prepared OpenEMS adapter and authenticated case (not executed)",
            "data":{"case":prepared,"script":OPENEMS_DRIVER,"adapter_source_sha256":hashlib.sha256(OPENEMS_DRIVER.encode()).hexdigest(),
                "preview_scope":"trusted adapter body only; execution adds authenticated case and fresh run context, whose full digest is recorded after execution", "solved":False}}
    if "case_dir" not in prepared:
        raw = {"status":"blocked", "case":prepared}
    else:
        raw = run_openems_case(prepared["case_dir"], setup_only=contribution == "openems-mesh", timeout_seconds=3300)
    required = "setup_completed" if contribution == "openems-mesh" else "completed"
    if raw.get("status") != required:
        return {"contract":"spike/extension-result/v1", "status":"failed", "title":"OpenEMS execution unavailable or blocked",
            "data":{"status":raw.get("status","failed"), "case":prepared, "result":raw, "solved":False}}
    return mesh_envelope(request, raw) if contribution == "openems-mesh" else solve_envelope(request, raw, spec, options)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON constant: {value}")))
    payload = execute(request)
    Path(args.result).write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
