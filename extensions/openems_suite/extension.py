# SPDX-License-Identifier: Apache-2.0
"""OpenEMS PI/SI workflow extension."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python.spike_core.contracts import AnalysisSpec, DesignIR
from extensions.openems_suite.engine import (
    _validate_openems_case,
    prepare_openems_case,
    run_openems_case,
)


MODES = {"openems-pi": "pi", "openems-si": "si"}


def _mapping(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def _em_workflow(contribution: str, context: dict) -> dict:
    design = DesignIR(**_mapping(context.get("design"), "design"))
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
    if contribution in MODES:
        data = _em_workflow(contribution, context)
    else:
        raise ValueError("Unknown OpenEMS Suite contribution.")
    return {"contract": "spike/extension-result/v1",
            "status": "completed" if data["status"] in {"completed", "ready_to_run"} else "completed_with_warnings",
            "title": "OpenEMS Suite: " + str(contribution).removeprefix("openems-").upper(),
            "data": data}


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
