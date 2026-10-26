# SPDX-License-Identifier: Apache-2.0
"""Reviewed export of finite sampled SI01 candidate constraints.

This module does not run a solver or apply native layout rules.  It turns an
existing SI01-S01 result and an explicit review decision into a digest-bound,
neutral record.  Only limits supplied by the original study are exportable.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import re


SELECTION = "spike/si-candidate-constraint-selection/v1"
MANIFEST = "spike/si-candidate-constraint-manifest/v1"
SOURCE = "spike/si-candidate-study-result/v1"
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class SiCandidateConstraintError(ValueError):
    """Fail-closed constraint-export error."""


def _require(condition, message):
    if not condition:
        raise SiCandidateConstraintError(message)


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise SiCandidateConstraintError(f"Source is not finite canonical JSON: {error}") from error


def canonical_sha256(value):
    """Return the canonical JSON digest used at this export boundary."""
    return sha256(_canonical(value)).hexdigest()


def _number(value, label):
    _require(type(value) in (int, float) and math.isfinite(float(value)), f"{label} must be finite")
    return float(value)


def _record(value, fields, label):
    _require(isinstance(value, dict) and set(value) == set(fields), f"Invalid {label} fields")


def _named_rows(rows, label):
    _require(isinstance(rows, list), f"{label} must be a list")
    output = {}
    for row in rows:
        _require(isinstance(row, dict) and isinstance(row.get("candidate_id"), str),
                 f"Invalid {label} row")
        identity = row["candidate_id"]
        _require(_IDENTIFIER.fullmatch(identity) is not None and identity not in output,
                 f"Duplicate or invalid {label} identity")
        output[identity] = row
    return output


def _trace(case):
    result = case.get("result")
    _require(isinstance(result, dict), "Completed selected case must retain its child result")
    matches = [row for row in result.get("loaded_transfers", [])
               if row.get("source_port") == 0 and row.get("observed_port") == 1]
    _require(len(matches) == 1 and isinstance(matches[0].get("trace"), list),
             "Selected case must retain one channel-facing transfer trace")
    points = []
    for point in matches[0]["trace"]:
        _require(isinstance(point, dict), "Invalid retained trace point")
        frequency = _number(point.get("frequency_hz"), "trace frequency")
        real = _number(point.get("real"), "trace real")
        imag = _number(point.get("imag"), "trace imaginary")
        points.append((frequency, real, imag))
    _require(points and all(points[i][0] < points[i + 1][0] for i in range(len(points) - 1)),
             "Selected trace frequencies must be strictly increasing")
    return points


def _witness(case, corner_id, point):
    frequency, real, imag = point
    return {"case_id": case["id"], "corner_id": corner_id, "frequency_hz": frequency,
            "real": real, "imag": imag, "gain": math.hypot(real, imag)}


def _same_number(left, right, label):
    _require(_number(left, label) == _number(right, label), f"Retained {label} differs")


def _verify_report(report, source_limit, cases):
    _require(isinstance(report, dict), "Invalid retained limit report")
    for key in ("id", "metric", "frequency_band_hz", "bound"):
        _require(report.get(key) == source_limit.get(key), f"Retained limit {key} differs from source request")
    _require(report.get("metric") in {"min_gain", "max_gain"}, "Unsupported source limit metric")
    band = report["frequency_band_hz"]
    _require(isinstance(band, list) and len(band) == 2, "Invalid source limit band")
    lo, hi = _number(band[0], "band start"), _number(band[1], "band end")
    _require(0 <= lo <= hi, "Invalid source limit band")
    bound = _number(report["bound"], "limit bound")
    samples = []
    completed_ids = []
    for case in cases:
        if case.get("status") != "completed":
            continue
        completed_ids.append(case["id"])
        samples.extend(_witness(case, case["corner_id"], point) for point in _trace(case)
                       if lo <= point[0] <= hi)
    coverage = len(completed_ids) == len(cases)
    _require(report.get("coverage_complete") is coverage, "Retained coverage flag differs")
    _require(report.get("evaluated_case_ids") == completed_ids, "Retained evaluated case identities differ")
    minimum = min(samples, key=lambda p: (p["gain"], p["frequency_hz"], p["case_id"])) if samples else None
    maximum = min(samples, key=lambda p: (-p["gain"], p["frequency_hz"], p["case_id"])) if samples else None
    worst = minimum if report["metric"] == "min_gain" else maximum
    margin = (worst["gain"] - bound if report["metric"] == "min_gain" else bound - worst["gain"]) if worst else None
    expected_status = "incomplete" if not coverage else "passed" if margin >= 0 else "failed"
    _require(report.get("status") == expected_status, "Retained limit status differs")
    for name, expected in (("minimum", minimum), ("maximum", maximum), ("worst", worst)):
        actual = report.get(name)
        _require((actual is None) == (expected is None), f"Retained {name} witness differs")
        if expected is not None:
            _require(set(actual) == set(expected), f"Retained {name} witness fields differ")
            for key in ("case_id", "corner_id"):
                _require(actual[key] == expected[key], f"Retained {name} identity differs")
            for key in ("frequency_hz", "real", "imag", "gain"):
                _same_number(actual[key], expected[key], f"{name}.{key}")
    if margin is None:
        _require(report.get("margin") is None, "Retained margin differs")
    else:
        _same_number(report.get("margin"), margin, "margin")
    return {key: report[key] for key in ("id", "metric", "frequency_band_hz", "bound", "status",
                                         "coverage_complete", "minimum", "maximum", "worst", "margin",
                                         "evaluated_case_ids")}


def export_candidate_constraints(source_result, selection):
    """Create a neutral reviewed manifest from one existing SI01-S01 result."""
    source_digest = canonical_sha256(source_result)
    _record(selection, {"contract", "expected_source_result_sha256", "candidate_id", "decision",
                        "reviewer_id", "review_basis", "constraint_ids"}, "selection")
    _require(selection["contract"] == SELECTION, "Unsupported selection contract")
    _require(_DIGEST.fullmatch(str(selection["expected_source_result_sha256"])) is not None,
             "Expected source digest must be lowercase SHA-256")
    _require(selection["expected_source_result_sha256"] == source_digest, "Source result digest differs")
    _require(_IDENTIFIER.fullmatch(str(selection["candidate_id"])) is not None, "Invalid selected candidate")
    _require(selection["decision"] in {"accept_sampled", "hold", "reject"}, "Invalid review decision")
    _require(_IDENTIFIER.fullmatch(str(selection["reviewer_id"])) is not None, "Invalid reviewer identity")
    _require(isinstance(selection["review_basis"], str) and 1 <= len(selection["review_basis"]) <= 512,
             "Review basis must be explicit and bounded")
    ids = selection["constraint_ids"]
    _require(isinstance(ids, list) and ids and len(ids) == len(set(ids)) and
             all(isinstance(item, str) and _IDENTIFIER.fullmatch(item) for item in ids),
             "Select unique constraint identities")

    _require(isinstance(source_result, dict) and source_result.get("contract") == SOURCE,
             "Expected SI01-S01 result")
    _require(source_result.get("model_status") == "experimental" and
             source_result.get("production_qualified") is False,
             "Source scope flags differ")
    input_digest = source_result.get("input_digest")
    _require(isinstance(input_digest, str) and _DIGEST.fullmatch(input_digest) is not None,
             "Missing source input digest")
    request = source_result.get("source_request")
    _require(isinstance(request, dict) and request.get("contract") == "spike/si-candidate-study-request/v1" and
             canonical_sha256(request) == input_digest, "Source request identity differs")
    source_limits = {row.get("id"): row for row in request.get("limits", []) if isinstance(row, dict)}
    _require(len(source_limits) == len(request.get("limits", [])) and set(ids) <= set(source_limits),
             "Selected constraint is absent or duplicated in source request")

    candidates = _named_rows(source_result.get("candidates"), "candidate")
    candidate = candidates.get(selection["candidate_id"])
    _require(candidate is not None, "Selected candidate is absent")
    all_cases = source_result.get("cases")
    _require(isinstance(all_cases, list), "Source cases must be retained")
    case_index = {}
    for case in all_cases:
        _require(isinstance(case, dict) and _IDENTIFIER.fullmatch(str(case.get("id"))) is not None and
                 case["id"] not in case_index, "Duplicate or invalid source case")
        case_index[case["id"]] = case
    case_ids = candidate.get("case_ids")
    _require(isinstance(case_ids, list) and case_ids and len(case_ids) == len(set(case_ids)) and
             set(case_ids) <= set(case_index), "Selected candidate case coverage differs")
    expected_source_cases = [row for row in request.get("cases", [])
                             if isinstance(row, dict) and row.get("candidate_id") == selection["candidate_id"]]
    _require({row.get("id") for row in expected_source_cases} == set(case_ids),
             "Selected candidate does not cover its complete source population")
    cases = [case_index[identity] for identity in case_ids]
    _require(all(case.get("candidate_id") == selection["candidate_id"] for case in cases),
             "Selected case belongs to another candidate")
    request_case_index = {row["id"]: row for row in expected_source_cases}
    for case in cases:
        supplied = request_case_index[case["id"]]
        _require(case.get("corner_id") == supplied.get("corner_id") and
                 case.get("request_digest") == canonical_sha256(supplied.get("request")),
                 "Selected case identity or request digest differs")
    reports = candidate.get("limits")
    _require(isinstance(reports, list), "Selected candidate limits are absent")
    report_index = {row.get("id"): row for row in reports if isinstance(row, dict)}
    _require(len(report_index) == len(reports) and set(report_index) == set(source_limits) and
             set(ids) <= set(report_index),
             "Selected candidate limit coverage differs")
    verified_reports = {identity: _verify_report(report_index[identity], source_limits[identity], cases)
                        for identity in source_limits}
    expected_candidate_status = ("incomplete" if any(row["status"] == "incomplete" for row in verified_reports.values())
                                 else "passed" if all(row["status"] == "passed" for row in verified_reports.values())
                                 else "failed")
    _require(candidate.get("status") == expected_candidate_status, "Retained candidate status differs")
    constraints = [verified_reports[identity] for identity in ids]
    applicable = selection["decision"] == "accept_sampled"
    if applicable:
        _require(candidate.get("status") == "passed" and all(row["status"] == "passed" and row["coverage_complete"] for row in constraints),
                 "Accepted sampled constraints require complete passing evidence")
        _require(all(case.get("status") == "completed" for case in cases),
                 "Accepted sampled constraints require completed selected cases")

    return {"contract": MANIFEST, "status": "reviewed", "applicable": applicable,
            "decision": selection["decision"], "reviewer_id": selection["reviewer_id"],
            "review_basis": selection["review_basis"], "candidate_id": selection["candidate_id"],
            "source_result_sha256": source_digest, "source_input_sha256": input_digest,
            "source_contract": SOURCE,
            "study_status": source_result.get("status"), "assessment_status": source_result.get("assessment_status"),
            "candidate_statuses": [{"candidate_id": key, "status": row.get("status"),
                                    "case_ids": row.get("case_ids")} for key, row in candidates.items()],
            "selected_cases": [{"id": row["id"], "corner_id": row.get("corner_id"),
                                "status": row.get("status"), "issue": row.get("issue"),
                                "request_digest": row.get("request_digest")} for row in cases],
            "constraints": constraints, "source_limitations": source_result.get("limitations", []),
            "limitations": ["Finite supplied samples only; no continuous-band limit is established.",
                            "The manifest records reviewed evidence but does not apply a native layout constraint.",
                            "Geometry, physical measurement and family-level qualification remain separate."],
            "native_layout_applied": False, "continuous_band_qualified": False,
            "physical_qualified": False, "production_qualified": False, "family_complete": False}
