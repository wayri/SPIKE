# SPDX-License-Identifier: Apache-2.0
"""Opt-in SPIKE process extension for Prism snapshot/result exchange."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from bridge import (admit_exchange, board_exchange, execute, read_json, write_json,
                    check_output, _object)


def invoke(request, *, dispatch=None, importer=None):
    _object(request, {"contract", "api_version", "request_id", "extension", "contribution_id", "context"},
            {"contract", "api_version", "request_id", "extension", "contribution_id", "context"}, "Extension request")
    if request["contract"] != "spike/extension/v1" or type(request["api_version"]) is not int or request["api_version"] != 1:
        raise ValueError("Expected the SPIKE process extension v1 request.")
    context = request["context"]
    _object(context, {"parameters", "source", "design", "design_binding"}, set(), "Extension context")
    parameters = context.get("parameters", {})
    contribution = request["contribution_id"]
    protected = ()
    if contribution == "prism-capabilities":
        _object(parameters, set(), set(), "Capabilities parameters")
        data = execute({"contract": "spike/prism-request/v1", "api_version": 1,
                        "request_id": request["request_id"], "operation": "capabilities"}, dispatch=dispatch)
        if data["status"] != "completed":
            raise ValueError("SPIKE capability discovery failed: " + str(data["error"]))
        title = "Prism bridge capabilities"
    elif contribution == "prism-import-board":
        _object(parameters, set(), set(), "Board import parameters")
        source = context.get("source")
        _object(source, {"path", "policy", "options"}, {"path"}, "Workspace source")
        if source.get("options"):
            raise ValueError("Prism board importer supports no implicit source options.")
        path = Path(source["path"])
        if not path.name.endswith(".prism-board.json"):
            raise ValueError("Select a .prism-board.json snapshot exchange.")
        protected = (path,)
        data = {"design": board_exchange(read_json(path), importer)}
        title = "Prism board snapshot import"
    elif contribution == "prism-import-result":
        _object(parameters, {"exchange", "expected_analysis_spec_sha256"},
                {"exchange", "expected_analysis_spec_sha256"}, "Result import parameters")
        data = {"analysis_result": admit_exchange(parameters["exchange"], context.get("design"),
                context.get("design_binding"), expected_spec_digest=parameters["expected_analysis_spec_sha256"])}
        title = "Prism bound analysis result"
    else:
        raise ValueError("Unknown Prism extension contribution.")
    return {"contract": "spike/extension-result/v1", "status": "completed", "title": title, "data": data}, protected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        check_output(args.result, (args.request,))
        request = read_json(args.request)
        # Reject aliasing the importer source before running its adapter.
        context = request.get("context", {}) if isinstance(request, dict) else {}
        source = context.get("source", {}) if isinstance(context, dict) else {}
        source_path = source.get("path") if isinstance(source, dict) else None
        protected = (args.request, *((source_path,) if source_path else ()))
        check_output(args.result, protected)
        result, sources = invoke(request)
        write_json(args.result, result, protected=(*protected, *sources))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        print(str(exc)[:4000], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
