# SPDX-License-Identifier: Apache-2.0
"""Finite explicit supplied-line SI candidate/corner comparison.

Reuses the existing linear loaded-network solver; introduces no field model.
All simulated samples are retained (at most 1024); limits are sampled V/V,
not continuous-band, layout, protocol, eye, BER or measured compliance.
Independent line-loading references: Staelin, Electromagnetics and Applications,
MIT OCW chapter 8, sections 8.1.1-8.1.2, printed pp229-232. See method record.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import re

import numpy as np

from .si_workflow import run_si_workflow, workflow_defaults

REQUEST = "spike/si-candidate-study-request/v1"
RESULT = "spike/si-candidate-study-result/v1"
_MAX_REQUEST_BYTES = 2 * 1024 * 1024
_MAX_RESULT_BYTES = 32 * 1024 * 1024


class SiCandidateStudyError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SI_CANDIDATE_STUDY_" + code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SiCandidateStudyError(code, message)


def _record(value, fields, label):
    _require(isinstance(value, dict) and set(value) == set(fields), f"Invalid {label} fields")


def _number(value, label):
    _require(type(value) in (int, float), f"{label} must be a finite number")
    try:
        value = float(value)
    except OverflowError as error:
        raise SiCandidateStudyError("invalid_request", f"Unrepresentable {label}") from error
    _require(math.isfinite(value), f"Nonfinite {label}")
    return value


def _name(value):
    _require(isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", value) is not None,
             "IDs must be bounded ASCII identifiers")


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def _digest(value):
    return sha256(_json(value)).hexdigest()


def _encoded_size(value, budget):
    """Bound serialized retention without constructing an aggregate JSON string."""
    size = 0
    for chunk in json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False,
                                  separators=(",", ":")).iterencode(value):
        size += len(chunk.encode())
        _require(size <= budget, "Study result exceeds remaining 32 MiB budget", "resource_limit")
    return size


def _bind_child(result, expected):
    _require(isinstance(result, dict) and result.get("contract") == "spike/si-workflow-result/v1",
             "Unexpected child result contract", "invalid_result")
    _require(_json(result.get("request")) == _json(expected), "Child expanded request differs", "invalid_result")
    # The existing SI workflow digest uses JSON's default ASCII escaping.
    expected_hash = sha256(json.dumps(expected, sort_keys=True, allow_nan=False,
                                      separators=(",", ":")).encode()).hexdigest()
    _require(result.get("request_sha256") == expected_hash, "Child request digest differs", "invalid_result")
    _require(result.get("status") in {"completed", "partial"}, "Unexpected child completion status", "invalid_result")


def _snapshot(request):
    chunks, size = [], 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False).iterencode(request):
            size += len(chunk.encode())
            _require(size <= _MAX_REQUEST_BYTES, "Study exceeds 2 MiB", "resource_limit")
            chunks.append(chunk)
        return json.loads("".join(chunks))
    except SiCandidateStudyError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise SiCandidateStudyError("invalid_request", f"Invalid finite JSON: {error}") from error


def _labels(values, label):
    _require(isinstance(values, list) and 1 <= len(values) <= 8, f"Provide 1..8 {label}", "resource_limit")
    for value in values:
        _name(value)
    _require(len(set(values)) == len(values), f"Duplicate {label}")


def _study_grid(study):
    _require(isinstance(study, dict) and study.get("contract") == "spike/si-workflow-request/v1", "Expected SI workflow request")
    _require(study.get("run_time_domain") is False, "Candidate studies require explicit run_time_domain=false")
    _require(study.get("edits", []) == [] and study.get("resonance_requests", []) == [], "Network edits and resonance fitting are outside this stage")
    channel = study.get("channel")
    _require(isinstance(channel, dict) and channel.get("kind") == "rlgc" and channel.get("coupled") is False,
             "Supply an explicit scalar RLGC line")
    required = {"length_m", "resistance_ohm_per_m", "inductance_h_per_m", "capacitance_f_per_m",
                "loss_tangent", "frequency_stop_hz", "frequency_points", "reference_impedance_ohm"}
    _require(required <= set(channel), "Supply line parameters and frequency/reference controls explicitly")
    for key in required:
        _number(channel[key], "channel." + key)
    count, stop = channel["frequency_points"], float(channel["frequency_stop_hz"])
    _require(int(count) == count and 3 <= count <= 1024, "Provide 3..1024 frequency samples", "resource_limit")
    _require(1 <= stop <= 1e14, "Invalid frequency stop")
    for key, port in (("sources", 0), ("receivers", 1)):
        endpoints = study.get(key)
        _require(isinstance(endpoints, list) and len(endpoints) == 1 and isinstance(endpoints[0], dict), "Supply one source and receiver")
        endpoint = endpoints[0]
        _require(type(endpoint.get("port")) is int and endpoint["port"] == port, "Use source port0 and receiver port1")
        _require("resistance_ohm" in endpoint and "ibis" not in endpoint and "cdr" not in endpoint,
                 "Explicit endpoint resistance required; IBIS/CDR outside this stage")
        _number(endpoint["resistance_ohm"], key + ".resistance_ohm")
        if key == "receivers":
            _require("capacitance_f" in endpoint, "Supply receiver capacitance explicitly")
            _number(endpoint["capacitance_f"], "receiver.capacitance_f")
    return np.linspace(0, stop, int(count)).tolist()


def _prepare(request):
    _record(request, {"contract", "candidate_ids", "corner_ids", "cases", "limits"}, "candidate study")
    _require(request["contract"] == REQUEST, "Unsupported candidate study contract")
    candidates, corners = request["candidate_ids"], request["corner_ids"]
    _labels(candidates, "candidates"); _labels(corners, "corners")
    _require(len(candidates)*len(corners) <= 32, "At most 32 cases", "resource_limit")
    cases = request["cases"]
    _require(isinstance(cases, list) and len(cases) == len(candidates)*len(corners), "Supply complete candidate/corner population")
    indexed, ids, grid = {}, set(), None
    for case in cases:
        _record(case, {"id", "candidate_id", "corner_id", "request"}, "case")
        for key in ("id", "candidate_id", "corner_id"):
            _name(case[key])
        pair = case["candidate_id"], case["corner_id"]
        _require(pair[0] in candidates and pair[1] in corners and pair not in indexed and case["id"] not in ids,
                 "Duplicate or undeclared case identity")
        current = _study_grid(case["request"])
        _require(grid is None or grid == current, "All cases require the identical explicit frequency grid")
        grid = current; indexed[pair] = case; ids.add(case["id"])
    _require(set(indexed) == {(candidate, corner) for candidate in candidates for corner in corners}, "Missing corner")
    limits, seen = request["limits"], set()
    _require(isinstance(limits, list) and 1 <= len(limits) <= 16, "Provide 1..16 sampled limits", "resource_limit")
    for limit in limits:
        _record(limit, {"id", "metric", "frequency_band_hz", "bound"}, "limit")
        _name(limit["id"])
        _require(limit["id"] not in seen and limit["metric"] in {"min_gain", "max_gain"}, "Duplicate limit or unsupported metric")
        seen.add(limit["id"])
        bound = _number(limit["bound"], "gain bound")
        _require(0 <= bound <= 1e12, "Gain bound must be nonnegative and bounded")
        band = limit["frequency_band_hz"]
        _require(isinstance(band, list) and len(band) == 2, "Provide explicit band endpoints")
        lo, hi = (_number(value, "band endpoint") for value in band)
        _require(0 <= lo <= hi <= grid[-1] and any(lo <= value <= hi for value in grid), "Band must contain supplied samples within the simulated grid")
    return indexed, grid


def _trace(result, grid):
    matches = [row for row in result["loaded_transfers"] if row["source_port"] == 0 and row["observed_port"] == 1]
    _require(len(matches) == 1, "Child transfer identity differs", "invalid_result")
    trace = matches[0]["trace"]
    _require([point["frequency_hz"] for point in trace] == grid, "Child trace omitted or changed frequency samples", "invalid_result")
    for point in trace:
        real, imag = (_number(point[key], "child transfer") for key in ("real", "imag"))
        _require(math.isfinite(math.hypot(real, imag)), "Nonfinite gain", "invalid_result")
    return trace


def _assess(candidate, corners, rows, limits):
    selected = [rows[(candidate, corner)] for corner in corners]
    complete = all(row["status"] == "completed" for row in selected)
    reports = []
    for limit in limits:
        lo, hi = limit["frequency_band_hz"]
        samples = [{"case_id": row["id"], "corner_id": row["corner_id"], "frequency_hz": point["frequency_hz"],
                    "real": point["real"], "imag": point["imag"], "gain": math.hypot(point["real"], point["imag"])}
                   for row in selected if row["status"] == "completed" for point in row["trace"] if lo <= point["frequency_hz"] <= hi]
        minimum = min(samples, key=lambda p: (p["gain"], p["frequency_hz"], p["case_id"])) if samples else None
        maximum = min(samples, key=lambda p: (-p["gain"], p["frequency_hz"], p["case_id"])) if samples else None
        worst = minimum if limit["metric"] == "min_gain" else maximum
        margin = (worst["gain"]-limit["bound"] if limit["metric"] == "min_gain" else limit["bound"]-worst["gain"]) if worst else None
        status = "incomplete" if not complete else "passed" if margin >= 0 else "failed"
        reports.append({**limit, "status": status, "coverage_complete": complete, "minimum": minimum,
            "maximum": maximum, "worst": worst, "margin": margin,
            "evaluated_case_ids": [row["id"] for row in selected if row["status"] == "completed"]})
    status = "incomplete" if not complete else "passed" if all(row["status"] == "passed" for row in reports) else "failed"
    return {"candidate_id": candidate, "status": status, "case_ids": [row["id"] for row in selected], "limits": reports}


def run_si_candidate_study(request, *, poll=None):
    """Compare an explicit population; failed/partial children remain in the result."""
    def check_cancelled():
        _require(poll is None or not poll(), "Candidate study cancelled", "cancelled")
    check_cancelled()
    raw = _snapshot(request)
    indexed, grid = _prepare(raw)
    rows = {}
    retained_bytes = _encoded_size(raw, _MAX_RESULT_BYTES) + _encoded_size(grid, _MAX_RESULT_BYTES)
    for candidate in raw["candidate_ids"]:
        for corner in raw["corner_ids"]:
            check_cancelled()
            case = indexed[(candidate, corner)]
            row = {key: case[key] for key in ("id", "candidate_id", "corner_id")}
            row.update(request_digest=_digest(case["request"]), result=None, issue=None, trace=[])
            try:
                expected = json.loads(_json({**workflow_defaults(), **case["request"]}))
                result = run_si_workflow(json.loads(_json(case["request"])))
                _encoded_size(result, _MAX_RESULT_BYTES - retained_bytes)
                _bind_child(result, expected)
                row["result"] = result
                row["status"] = "completed" if result["status"] == "completed" else "partial"
                if row["status"] == "completed":
                    row["trace"] = _trace(result, grid)
            except (ValueError, TypeError, KeyError, ArithmeticError) as error:
                if getattr(error, "code", None) == "SI_CANDIDATE_STUDY_RESOURCE_LIMIT":
                    raise
                row.update(status="failed", issue={"code": getattr(error, "code", "SI_WORKFLOW_CASE_FAILED"), "message": str(error)})
            check_cancelled()
            retained_bytes += _encoded_size({key: value for key, value in row.items() if key != "trace"},
                                            _MAX_RESULT_BYTES-retained_bytes)
            rows[(candidate, corner)] = row
    assessments = [_assess(candidate, raw["corner_ids"], rows, raw["limits"]) for candidate in raw["candidate_ids"]]
    incomplete = any(row["status"] == "incomplete" for row in assessments)
    output = {"contract": RESULT, "status": "partial" if incomplete else "completed", "model_status": "experimental",
        "production_qualified": False, "assessment_status": "incomplete" if incomplete else "passed" if all(row["status"] == "passed" for row in assessments) else "failed",
        "source_request": raw, "input_digest": _digest(raw), "frequencies_hz": grid,
        "cases": [{key: value for key, value in row.items() if key != "trace"} for row in rows.values()],
        "candidates": assessments, "feasible_candidate_ids": [row["candidate_id"] for row in assessments if row["status"] == "passed"],
        "limitations": ["Finite supplied scalar line/termination corners; no statistical population or geometry extraction.",
            "Limits use all supplied frequency samples and channel-facing voltage gain V/V, with direct binary64 comparisons and no automatic slack; not continuous-band compliance.",
            "Failed or partial corners cannot yield a passing candidate; incomplete-population envelopes remain provisional.",
            "Temperature/passive assumptions remain in each expanded child request; no material feedback, physical heat allocation or spatial fields are inferred.",
            "SI01 editor, general topology/port classes, native layout-rule export, eyes, nonlinear IBIS and physical qualification remain open."]}
    _encoded_size(output, _MAX_RESULT_BYTES)
    return output
