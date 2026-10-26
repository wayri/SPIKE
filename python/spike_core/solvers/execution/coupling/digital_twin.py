# SPDX-License-Identifier: Apache-2.0
"""Offline, bounded comparison of supplied predictions and telemetry.

``compare_digital_twin`` accepts this JSON-compatible request shape::

    {
      "contract": "spike/digital-twin-request/v1",
      "model_id": "converter-A",
      "model_revision": "rev-7",
      "model_status": "approximate",  # approximate|experimental|validated|unsupported
      "channels": [
        {"id": "temperature", "unit": "K", "tolerance": 2.0}
      ],
      "prediction": {
        "model_id": "converter-A", "model_revision": "rev-7",
        "channels": [{"id": "temperature", "unit": "K"}],
        "samples": [{"time_s": 0.0, "values": {"temperature": 300.0}}]
      },
      "telemetry": {
        "model_id": "converter-A", "model_revision": "rev-7",
        "channels": [{"id": "temperature", "unit": "K"}],
        "samples": [{"time_s": 0.0, "values": {"temperature": 301.0}}]
      }
    }

All identities, channel IDs, and units must agree exactly. Timestamps are
matched exactly; this module does not resample or interpolate. It compares
already supplied values and makes no physics, device-control, or calibration
claim.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

REQUEST_CONTRACT = "spike/digital-twin-request/v1"
RESULT_CONTRACT = "spike/digital-twin-result/v1"
MODEL_STATUSES = {"approximate", "experimental", "validated", "unsupported"}
MAX_CHANNELS = 128
MAX_SAMPLES_PER_SERIES = 10_000
MAX_TOTAL_VALUES = 500_000
MAX_TRACE_POINTS_PER_CHANNEL = 2_048
MAX_TOTAL_TRACE_POINTS = 20_000
MAX_CANONICAL_BYTES = 8 * 1024 * 1024
MAX_TEXT_LENGTH = 256

_LIMITATIONS = [
    "This is an offline comparison of supplied values; it does not control devices or acquire telemetry.",
    "Exact timestamps only; unmatched samples are reported and no interpolation is invented.",
    "Model status is preserved from the request; agreement does not validate physics or qualify hardware.",
    "Channel tolerances are supplied acceptance thresholds, not calibration or uncertainty estimates.",
]


class _AdmissionError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def _reject(code: str, message: str, path: str = "$") -> None:
    raise _AdmissionError(code, message, path)


def _object(value: Any, fields: set[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        _reject("INVALID_OBJECT", f"{path} must be an object with string keys.", path)
    missing = sorted(fields - set(value))
    unknown = sorted(set(value) - fields)
    if missing or unknown:
        detail = []
        if missing:
            detail.append(f"missing {missing}")
        if unknown:
            detail.append(f"unknown {unknown}")
        _reject("INVALID_FIELDS", f"{path} has {' and '.join(detail)} fields.", path)
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT_LENGTH:
        _reject("INVALID_TEXT", f"{path} must be a nonempty string of at most {MAX_TEXT_LENGTH} characters.", path)
    return value


def _number(value: Any, path: str, *, nonnegative: bool = False) -> float:
    if type(value) not in (int, float):
        _reject("INVALID_NUMBER", f"{path} must be a finite number, not a boolean.", path)
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        _reject("INVALID_NUMBER", f"{path} must be a finite number.", path)
    if not math.isfinite(result) or (nonnegative and result < 0.0):
        qualifier = "finite and nonnegative" if nonnegative else "finite"
        _reject("INVALID_NUMBER", f"{path} must be {qualifier}.", path)
    return result


def _canonical_digest(request: Any) -> tuple[str | None, tuple[str, str] | None]:
    digest = hashlib.sha256()
    size = 0
    try:
        encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
        for chunk in encoder.iterencode(request):
            encoded = chunk.encode("utf-8")
            size += len(encoded)
            if size > MAX_CANONICAL_BYTES:
                return None, ("REQUEST_SIZE_LIMIT", f"Canonical request exceeds {MAX_CANONICAL_BYTES} bytes.")
            digest.update(encoded)
    except (TypeError, ValueError, OverflowError):
        return None, ("NON_CANONICAL_INPUT", "Request must be finite, JSON-compatible data.")
    return digest.hexdigest(), None


def _channel_specs(raw: Any) -> tuple[list[dict[str, Any]], dict[str, tuple[str, float]]]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_CHANNELS:
        _reject("CHANNEL_LIMIT", f"$.channels requires 1..{MAX_CHANNELS} entries.", "$.channels")
    ordered: list[dict[str, Any]] = []
    by_id: dict[str, tuple[str, float]] = {}
    for index, item in enumerate(raw):
        path = f"$.channels[{index}]"
        channel = _object(item, {"id", "unit", "tolerance"}, path)
        channel_id = _text(channel["id"], f"{path}.id")
        unit = _text(channel["unit"], f"{path}.unit")
        tolerance = _number(channel["tolerance"], f"{path}.tolerance", nonnegative=True)
        if channel_id in by_id:
            _reject("DUPLICATE_CHANNEL", f"Duplicate channel ID {channel_id!r}.", f"{path}.id")
        by_id[channel_id] = (unit, tolerance)
        ordered.append({"id": channel_id, "unit": unit, "tolerance": tolerance})
    return ordered, by_id


def _series_channels(raw: Any, expected: Mapping[str, tuple[str, float]], path: str) -> None:
    if not isinstance(raw, list) or len(raw) != len(expected):
        _reject("CHANNEL_DECLARATION_MISMATCH", f"{path} must declare every configured channel exactly once.", path)
    declared: dict[str, str] = {}
    for index, item in enumerate(raw):
        item_path = f"{path}[{index}]"
        channel = _object(item, {"id", "unit"}, item_path)
        channel_id = _text(channel["id"], f"{item_path}.id")
        unit = _text(channel["unit"], f"{item_path}.unit")
        if channel_id in declared:
            _reject("DUPLICATE_CHANNEL", f"Duplicate channel ID {channel_id!r}.", f"{item_path}.id")
        declared[channel_id] = unit
    expected_units = {channel_id: spec[0] for channel_id, spec in expected.items()}
    if declared != expected_units:
        _reject("CHANNEL_DECLARATION_MISMATCH", f"{path} IDs and units must exactly match $.channels.", path)


def _series(raw: Any, expected_identity: tuple[str, str],
            channels: Mapping[str, tuple[str, float]], path: str) -> list[tuple[float, dict[str, float]]]:
    series = _object(raw, {"model_id", "model_revision", "channels", "samples"}, path)
    identity = (_text(series["model_id"], f"{path}.model_id"),
                _text(series["model_revision"], f"{path}.model_revision"))
    if identity != expected_identity:
        _reject("MODEL_IDENTITY_MISMATCH", f"{path} model identity is stale or belongs to another model.", path)
    _series_channels(series["channels"], channels, f"{path}.channels")
    samples = series["samples"]
    if not isinstance(samples, list) or not 1 <= len(samples) <= MAX_SAMPLES_PER_SERIES:
        _reject("SAMPLE_LIMIT", f"{path}.samples requires 1..{MAX_SAMPLES_PER_SERIES} entries.", f"{path}.samples")
    if len(samples) * len(channels) > MAX_TOTAL_VALUES:
        _reject("VALUE_LIMIT", f"{path} exceeds the {MAX_TOTAL_VALUES} value limit.", f"{path}.samples")
    expected_ids = set(channels)
    admitted: list[tuple[float, dict[str, float]]] = []
    previous = -1.0
    for index, item in enumerate(samples):
        item_path = f"{path}.samples[{index}]"
        sample = _object(item, {"time_s", "values"}, item_path)
        time_s = _number(sample["time_s"], f"{item_path}.time_s", nonnegative=True)
        if time_s <= previous:
            _reject("TIME_ORDER", f"{path} timestamps must be strictly increasing.", f"{item_path}.time_s")
        previous = time_s
        values = sample["values"]
        if not isinstance(values, Mapping) or any(not isinstance(key, str) for key in values):
            _reject("INVALID_VALUES", f"{item_path}.values must be an object.", f"{item_path}.values")
        if set(values) != expected_ids:
            _reject("CHANNEL_VALUES_MISMATCH", f"{item_path}.values must contain exactly the configured channel IDs.", f"{item_path}.values")
        admitted.append((time_s, {channel_id: _number(values[channel_id], f"{item_path}.values.{channel_id}")
                                  for channel_id in channels}))
    return admitted


def compare_digital_twin(request: Any) -> dict[str, Any]:
    """Validate and compare one bounded prediction/telemetry request.

    The exact request shape is documented in the module docstring. Malformed,
    stale, unit-inconsistent, or non-overlapping inputs return ``rejected``
    with one structured issue. Accepted results preserve ``model_status`` and
    report exact-time residuals without interpreting model validity.
    """
    digest, preflight_error = _canonical_digest(request)
    candidate_id = request.get("model_id") if isinstance(request, Mapping) else None
    candidate_revision = request.get("model_revision") if isinstance(request, Mapping) else None
    candidate_status = request.get("model_status") if isinstance(request, Mapping) else None
    result_id = (candidate_id if isinstance(candidate_id, str) and candidate_id.strip()
                 and len(candidate_id) <= MAX_TEXT_LENGTH else None)
    result_revision = (candidate_revision if isinstance(candidate_revision, str) and candidate_revision.strip()
                       and len(candidate_revision) <= MAX_TEXT_LENGTH else None)
    result: dict[str, Any] = {
        "contract": RESULT_CONTRACT,
        "status": "rejected",
        "request_sha256": digest,
        "model_id": result_id,
        "model_revision": result_revision,
        "model_status": candidate_status if candidate_status in MODEL_STATUSES else None,
        "issues": [],
        "limitations": list(_LIMITATIONS),
    }
    try:
        if preflight_error is not None:
            _reject(preflight_error[0], preflight_error[1])
        root = _object(request, {"contract", "model_id", "model_revision", "model_status",
                                 "channels", "prediction", "telemetry"}, "$")
        if root["contract"] != REQUEST_CONTRACT:
            _reject("UNSUPPORTED_CONTRACT", f"contract must be {REQUEST_CONTRACT!r}.", "$.contract")
        model_id = _text(root["model_id"], "$.model_id")
        revision = _text(root["model_revision"], "$.model_revision")
        model_status = root["model_status"]
        if not isinstance(model_status, str) or model_status not in MODEL_STATUSES:
            _reject("INVALID_MODEL_STATUS", f"model_status must be one of {sorted(MODEL_STATUSES)}.", "$.model_status")
        channel_specs, channels = _channel_specs(root["channels"])
        prediction = _series(root["prediction"], (model_id, revision), channels, "$.prediction")
        telemetry = _series(root["telemetry"], (model_id, revision), channels, "$.telemetry")
        predicted_by_time = dict(prediction)
        measured_by_time = dict(telemetry)
        matched_times = sorted(predicted_by_time.keys() & measured_by_time.keys())
        if not matched_times:
            _reject("NO_MATCHED_SAMPLES", "Prediction and telemetry have no exactly matching timestamps.", "$")

        unmatched_prediction = len(prediction) - len(matched_times)
        unmatched_telemetry = len(telemetry) - len(matched_times)
        channel_results = []
        for spec in channel_specs:
            channel_id = spec["id"]
            residuals = [measured_by_time[t][channel_id] - predicted_by_time[t][channel_id]
                         for t in matched_times]
            if not all(math.isfinite(value) for value in residuals):
                _reject("NUMERICAL_RANGE", f"Residual arithmetic overflowed for channel {channel_id!r}.")
            maximum = max(abs(value) for value in residuals)
            rmse = 0.0 if maximum == 0.0 else maximum * math.sqrt(
                math.fsum((value / maximum) ** 2 for value in residuals) / len(residuals)
            )
            violations = sum(abs(value) > spec["tolerance"] for value in residuals)
            trace_count = min(len(matched_times), MAX_TRACE_POINTS_PER_CHANNEL,
                              MAX_TOTAL_TRACE_POINTS // len(channel_specs))
            trace = [{
                "time_s": time_s,
                "predicted": predicted_by_time[time_s][channel_id],
                "measured": measured_by_time[time_s][channel_id],
                "residual": residuals[index],
                "threshold_violated": abs(residuals[index]) > spec["tolerance"],
            } for index, time_s in enumerate(matched_times[:trace_count])]
            channel_results.append({
                **spec,
                "matched_count": len(matched_times),
                "unmatched_prediction_count": unmatched_prediction,
                "unmatched_telemetry_count": unmatched_telemetry,
                "max_abs_error": maximum,
                "rmse": rmse,
                "threshold_violation_count": violations,
                "trace": trace,
                "trace_truncated": trace_count < len(matched_times),
            })
        result.update({
            "status": "completed",
            "model_id": model_id,
            "model_revision": revision,
            "model_status": model_status,
            "matched_sample_count": len(matched_times),
            "unmatched_prediction_sample_count": unmatched_prediction,
            "unmatched_telemetry_sample_count": unmatched_telemetry,
            "threshold_violation_count": sum(item["threshold_violation_count"] for item in channel_results),
            "channels": channel_results,
        })
    except _AdmissionError as error:
        result["issues"] = [{"severity": "error", "code": error.code,
                             "message": str(error), "path": error.path}]
    return result


__all__ = ["REQUEST_CONTRACT", "RESULT_CONTRACT", "compare_digital_twin"]
