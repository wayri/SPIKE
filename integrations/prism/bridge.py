# SPDX-License-Identifier: Apache-2.0
"""Bounded SPIKE-owned snapshot exchange; no Prism implementation or solver."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

MAX_EXCHANGE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_DEPTH = 32
METHODS = frozenset({"capabilities", "list_solvers", "run_preflighted_analysis"})
REQUEST_CONTRACT = "spike/prism-request/v1"
RESULT_CONTRACT = "spike/prism-result/v1"
BOARD_CONTRACT = "spike/prism-board/v1"
SPEC_KEYS = frozenset({"contract", "analysis_id", "mode", "solver_id", "formulation",
    "required_capabilities", "net_names", "sources", "loads", "return_path", "probes",
    "frequency_start_hz", "frequency_stop_hz", "frequency_points", "transient", "mesh", "limits", "options"})
SPEC_REQUIRED = frozenset({"contract", "mode", "net_names", "sources", "loads", "return_path", "probes", "mesh", "limits", "options"})


def finite_tree(value):
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_DEPTH:
            raise ValueError("Exchange nesting exceeds 32 levels.")
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("JSON object keys must be strings.")
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            try:
                valid = math.isfinite(item)
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError("Exchange numbers must be finite.")
        elif not isinstance(item, (str, bool, type(None))):
            raise ValueError("Exchange contains a non-JSON value.")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key: " + key[:128])
        result[key] = value
    return result


def read_json(path, limit=MAX_EXCHANGE_BYTES):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Exchange file exceeds its byte limit.")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda token: (_ for _ in ()).throw(ValueError("Non-finite JSON: " + token)))
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("Exchange must be bounded UTF-8 JSON.") from exc
    finite_tree(value)
    return value


def _encoded(value):
    finite_tree(value)
    try:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("Exchange strings must encode as UTF-8.") from exc
    if len(payload) > MAX_EXCHANGE_BYTES:
        raise ValueError("Result exceeds the 64 MiB exchange limit; reduce the board or analysis scope.")
    return payload


def digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def check_output(path, protected):
    target = Path(path).resolve()
    for source in protected:
        source = Path(source).resolve()
        if target == source or (target.exists() and source.exists() and os.path.samefile(target, source)):
            raise ValueError("Result must not overwrite its request or source exchange file.")
    return target


def write_json(path, value, *, protected=()):
    target = check_output(path, protected)
    payload = _encoded(value)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _object(value, allowed, required, label):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError(label + " has missing or unknown fields.")


def snapshot(source):
    _object(source, {"file_name", "encoding", "data", "sha256"}, {"file_name", "encoding", "data", "sha256"}, "Source snapshot")
    name = source["file_name"]
    if (not isinstance(name, str) or len(name) > 255
            or not re.fullmatch(r'[^/\\:\x00-\x1f<>|?*]+\.kicad_pcb', name)
            or name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}):
        raise ValueError("Source file_name must be a portable basename ending .kicad_pcb.")
    if source["encoding"] != "utf-8" or not isinstance(source["data"], str):
        raise ValueError("Source must contain exact UTF-8 text with encoding utf-8.")
    try:
        payload = source["data"].encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Source text must encode as UTF-8.") from exc
    if not payload or len(payload) > MAX_SOURCE_BYTES:
        raise ValueError("Source snapshot must contain 1 byte to 32 MiB of UTF-8 data.")
    if not isinstance(source["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", source["sha256"]) or hashlib.sha256(payload).hexdigest() != source["sha256"]:
        raise ValueError("Source SHA-256 does not match the exact UTF-8 bytes.")
    return payload, {"file_name": name, "sha256": source["sha256"], "byte_count": len(payload)}


def analysis_spec(spec):
    _object(spec, SPEC_KEYS, SPEC_REQUIRED, "Explicit AnalysisSpec")
    if spec["contract"] != "spike/v1" or not isinstance(spec["mode"], str) or not spec["mode"].strip():
        raise ValueError("AnalysisSpec requires spike/v1 and an explicit mode.")
    for key in ("net_names", "sources", "loads", "probes", "required_capabilities"):
        if key in spec and not isinstance(spec[key], list):
            raise ValueError("AnalysisSpec." + key + " must be an array.")
    for key in ("net_names", "required_capabilities"):
        if key in spec and any(not isinstance(item, str) for item in spec[key]):
            raise ValueError("AnalysisSpec." + key + " entries must be strings.")
    for key in ("sources", "loads", "probes"):
        if any(not isinstance(item, dict) for item in spec[key]):
            raise ValueError("AnalysisSpec." + key + " entries must be objects.")
        for record in spec[key]:
            for field in ("position_mm", "at"):
                if field not in record:
                    continue
                point = record[field]
                if isinstance(point, dict) and {"x", "y"} <= set(point) <= {"x", "y", "z"}:
                    coordinates = list(point.values())
                elif isinstance(point, list) and len(point) in (2, 3):
                    coordinates = point
                else:
                    raise ValueError("AnalysisSpec." + key + "." + field + " requires 2/3 coordinates or an explicit x/y object.")
                if any(type(value) not in (int, float) for value in coordinates):
                    raise ValueError("AnalysisSpec." + key + "." + field + " coordinates must be finite numbers.")
    for key in ("analysis_id", "solver_id", "formulation"):
        if key in spec and not isinstance(spec[key], str):
            raise ValueError("AnalysisSpec." + key + " must be a string.")
    for key in ("frequency_start_hz", "frequency_stop_hz"):
        if key in spec and spec[key] is not None and (type(spec[key]) not in (int, float) or spec[key] < 0):
            raise ValueError("AnalysisSpec." + key + " must be a nonnegative number or null.")
    if "frequency_points" in spec and (type(spec["frequency_points"]) is not int or spec["frequency_points"] < 1):
        raise ValueError("AnalysisSpec.frequency_points must be a positive integer.")
    for key in ("return_path", "mesh", "limits", "options", "transient"):
        if key in spec and not isinstance(spec[key], dict):
            raise ValueError("AnalysisSpec." + key + " must be an object.")
    finite_tree(spec)
    return {"sha256": digest(spec)}


def _runtime():
    root = Path(__file__).resolve().parents[2]
    if (root / "python" / "spike_core").is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from python.spike_core.kicad_importer import import_kicad_design
        from python.spike_core.service import handle
        return import_kicad_design, handle
    except ImportError as exc:
        raise RuntimeError("SPIKE Python runtime is unavailable. Run this source-only add-on from integrations/prism in a SPIKE checkout using its approved Python environment; frozen installer support is not qualified. Missing dependency: " + str(exc)) from exc


def import_snapshot(source, importer=None):
    payload, binding = snapshot(source)
    if importer is None:
        importer, _ = _runtime()
    with tempfile.TemporaryDirectory(prefix="spike-prism-") as directory:
        path = Path(directory) / source["file_name"]
        path.write_bytes(payload)
        raw = importer(str(path))
        design = raw.to_dict() if hasattr(raw, "to_dict") else raw
        # Source path is transport-local. Source IDs, coordinates, model status
        # and importer issues are left exactly as the existing adapter returned.
        # SpiDeR.to_dict() can retain coordinate tuples. The standard JSON
        # conversion normalizes only JSON-compatible containers, not objects
        # through a permissive default=str fallback.
        design = json.loads(json.dumps(design, ensure_ascii=False, allow_nan=False))
        _encoded(design)
        design["source_path"] = source["file_name"]
        for component in design.get("components", []):
            component["model_resolved"] = ""
        design.setdefault("metadata", {})["prism_snapshot_policy"] = {
            "source_only": True, "dependent_3d_assets_supplied": False,
            "resolved_3d_model_paths": "omitted"}
        design.setdefault("issues", []).append({"code": "PRISM_DEPENDENT_ASSETS_OMITTED",
            "severity": "warning", "message": "Source-only snapshot: dependent 3D assets and machine-local resolved model paths are omitted.",
            "path": "components.model_resolved", "suggestion": "Use a reviewed asset-aware exchange for analyses requiring dependent 3D geometry.", "status": "open"})
    if design.get("contract") != "spike/v1" or design.get("metadata", {}).get("source_sha256") != binding["sha256"]:
        raise ValueError("SPIKE importer did not retain the exact snapshot source binding.")
    return design


def _call(method, params, dispatch):
    if method not in METHODS:
        raise ValueError("Worker method is not allowed by the Prism bridge.")
    if dispatch is None:
        _, dispatch = _runtime()
    response = dispatch({"method": method, "params": params})
    finite_tree(response)
    if not isinstance(response, dict) or not isinstance(response.get("ok"), bool):
        raise ValueError("SPIKE worker returned an invalid response.")
    return response


def _analysis_bindings(exchange):
    return {"design_id": exchange["design_binding"]["design_id"],
            "design_digest_sha256": exchange["design_binding"]["digest_sha256"],
            "input_source_sha256": exchange["source_binding"]["sha256"],
            "input_analysis_spec_sha256": exchange["analysis_spec_binding"]["sha256"]}


def execute(request, *, dispatch=None, importer=None):
    finite_tree(request)
    _object(request, {"contract", "api_version", "request_id", "operation", "source", "analysis_spec"},
            {"contract", "api_version", "request_id", "operation"}, "Prism request")
    if request["contract"] != REQUEST_CONTRACT or type(request["api_version"]) is not int or request["api_version"] != 1:
        raise ValueError("Expected spike/prism-request/v1 with api_version 1.")
    if not isinstance(request["request_id"], str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request["request_id"]):
        raise ValueError("request_id must be a bounded plain identifier.")
    operation = request["operation"]
    if not isinstance(operation, str) or operation not in {"capabilities", "inspect-board", "analyze"}:
        raise ValueError("Operation must be capabilities, inspect-board or analyze.")
    if (operation == "capabilities" and ("source" in request or "analysis_spec" in request)
            or operation == "inspect-board" and "analysis_spec" in request
            or operation != "capabilities" and "source" not in request
            or operation == "analyze" and "analysis_spec" not in request):
        raise ValueError("Operation has an invalid source or explicit AnalysisSpec combination.")
    result = {"contract": RESULT_CONTRACT, "api_version": 1, "request_id": request["request_id"],
              "operation": operation, "request_sha256": digest(request), "status": "completed",
              "source_binding": None, "design_binding": None, "analysis_spec_binding": None,
              "analysis_spec": None, "design": None, "capabilities": None, "analysis": None, "error": None}
    if operation == "capabilities":
        values = {}
        for method in ("capabilities", "list_solvers"):
            response = _call(method, {}, dispatch)
            if not response["ok"]:
                return {**result, "status": "error", "error": response}
            values[method] = response.get("result")
        result["capabilities"] = values
    else:
        _, result["source_binding"] = snapshot(request["source"])
        if operation == "analyze":
            result["analysis_spec_binding"] = analysis_spec(request["analysis_spec"])
            result["analysis_spec"] = request["analysis_spec"]
        design = import_snapshot(request["source"], importer)
        result["design"] = design
        result["design_binding"] = {"design_id": design.get("design_id"), "digest_sha256": digest(design)}
        if operation == "analyze":
            response = _call("run_preflighted_analysis", {"design": design, "spec": request["analysis_spec"]}, dispatch)
            if not response["ok"]:
                return {**result, "status": "error", "error": response}
            analysis = response.get("result")
            if not isinstance(analysis, dict) or analysis.get("contract") != "spike/preflighted-analysis/v1" or analysis.get("status") not in {"completed", "blocked"}:
                raise ValueError("SPIKE worker returned an invalid preflighted analysis envelope.")
            raw = analysis.get("analysis_result")
            if raw is not None:
                if not isinstance(raw, dict) or not isinstance(raw.get("provenance"), dict):
                    raise ValueError("SPIKE worker returned an AnalysisResult without object provenance.")
                bindings = _analysis_bindings(result)
                for key, value in bindings.items():
                    if key in raw["provenance"] and raw["provenance"][key] != value:
                        raise ValueError("SPIKE AnalysisResult has conflicting production provenance: " + key)
                # Bind the actual result at production, before transport. Admission
                # must never manufacture lineage for an unrelated raw result.
                # All model/status/fields/issues and existing provenance survive.
                analysis = {**analysis, "analysis_result": {**raw,
                    "provenance": {**raw["provenance"], **bindings}}}
            result["analysis"] = analysis
            result["status"] = analysis["status"]
    _encoded(result)
    return result


def board_exchange(value, importer=None):
    finite_tree(value)
    _object(value, {"contract", "api_version", "source"}, {"contract", "api_version", "source"}, "Prism board exchange")
    if value["contract"] != BOARD_CONTRACT or type(value["api_version"]) is not int or value["api_version"] != 1:
        raise ValueError("Expected spike/prism-board/v1 with api_version 1.")
    return import_snapshot(value["source"], importer)


def admit_exchange(exchange, design, host_binding, *, expected_spec_digest, admit=None, binding_function=None):
    """Validate external bindings before using the existing result admission."""
    if not isinstance(expected_spec_digest, str) or not re.fullmatch("[0-9a-f]{64}", expected_spec_digest):
        raise ValueError("Supply the SHA-256 of the current explicit AnalysisSpec to reject stale settings.")
    if binding_function is None or admit is None:
        _runtime()
        from python.spike_core.extension_analysis_results import admit_analysis_result, design_binding
        admit = admit or admit_analysis_result
        binding_function = binding_function or design_binding
    _encoded(exchange)
    allowed = {"contract", "api_version", "request_id", "operation", "request_sha256", "status", "source_binding", "design_binding", "analysis_spec_binding", "analysis_spec", "design", "capabilities", "analysis", "error"}
    _object(exchange, allowed, allowed, "Prism result exchange")
    binding = binding_function(design)
    if host_binding != binding or exchange["design_binding"] != binding or binding_function(exchange["design"]) != binding:
        raise ValueError("Prism result does not match the exact host SpiDeR design binding.")
    if (exchange["contract"] != RESULT_CONTRACT or type(exchange["api_version"]) is not int or exchange["api_version"] != 1
            or exchange["operation"] != "analyze" or exchange["status"] != "completed" or exchange["error"] is not None):
        raise ValueError("Only completed spike/prism-result/v1 analyses can be imported. Keep blocked/failed exchanges as diagnostics; inspect analysis.preflight and analysis.analysis_result issues, correct the setup/runtime, and rerun.")
    source = exchange["source_binding"]
    _object(source, {"file_name", "sha256", "byte_count"}, {"file_name", "sha256", "byte_count"}, "Source binding")
    if design.get("metadata", {}).get("source_sha256") != source["sha256"] or design.get("source_path") != source["file_name"]:
        raise ValueError("Prism source binding does not match the host design.")
    if exchange["analysis_spec_binding"] != analysis_spec(exchange["analysis_spec"]):
        raise ValueError("Prism AnalysisSpec binding does not match its explicit input.")
    if exchange["analysis_spec_binding"]["sha256"] != expected_spec_digest:
        raise ValueError("Prism result is stale for the current AnalysisSpec; rerun with the current explicit settings.")
    analysis = exchange["analysis"]
    if not isinstance(analysis, dict) or analysis.get("contract") != "spike/preflighted-analysis/v1" or analysis.get("status") != "completed":
        raise ValueError("Prism preflighted analysis did not complete.")
    raw = analysis.get("analysis_result")
    if not isinstance(raw, dict):
        raise ValueError("Prism exchange contains no AnalysisResult.")
    provenance = raw.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("Prism AnalysisResult is missing production provenance.")
    for key, value in _analysis_bindings(exchange).items():
        if provenance.get(key) != value:
            raise ValueError("Prism AnalysisResult has missing or conflicting production provenance: " + key)
    return admit(raw, binding, extension_id="spike.prism-bridge", expected_spec_digest=expected_spec_digest)


def error_result(request, error):
    """Echo only bindings that can be validated even when execution fails."""
    request = request if isinstance(request, dict) else {}
    identifier = request.get("request_id")
    operation = request.get("operation")
    result = {"contract": RESULT_CONTRACT, "api_version": 1,
              "request_id": identifier if isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", identifier) else None,
              "operation": operation if isinstance(operation, str) and operation in {"capabilities", "inspect-board", "analyze"} else None,
              "request_sha256": None, "status": "error",
              "source_binding": None, "design_binding": None, "analysis_spec_binding": None,
              "analysis_spec": None, "design": None, "capabilities": None, "analysis": None,
              "error": {"code": "PRISM_BRIDGE_REJECTED", "message": str(error)[:4000]}}
    try:
        result["request_sha256"] = digest(request)
        if "source" in request:
            _, result["source_binding"] = snapshot(request["source"])
        if "analysis_spec" in request:
            result["analysis_spec_binding"] = analysis_spec(request["analysis_spec"])
            result["analysis_spec"] = request["analysis_spec"]
    except (ValueError, TypeError):
        pass
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args(argv)
    request = None
    try:
        # Check collision before executing an importer or analysis.
        check_output(args.result, (args.request,))
        request = read_json(args.request)
        result = execute(request)
        write_json(args.result, result, protected=(args.request,))
        return 2 if result["status"] == "error" else 0
    except Exception as exc:
        # The process boundary always attempts a failed diagnostic for worker
        # implementation errors too; termination signals are not intercepted.
        try:
            write_json(args.result, error_result(request, exc), protected=(args.request,))
        except (ValueError, OSError):
            pass
        print(str(exc)[:4000], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
