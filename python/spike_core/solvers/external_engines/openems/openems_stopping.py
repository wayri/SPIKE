# SPDX-License-Identifier: Apache-2.0
"""Bounded interpretation of retained openEMS native stopping evidence."""
from __future__ import annotations

import math
import re
from collections.abc import Mapping


STOPPING_CONTRACT = "spike/openems-stopping-evidence/v1"
PARSER_ID = "spike_openems_native_log_v2"
MAX_LOG_CHARACTERS = 8 * 1024 * 1024
MAX_RELEVANT_LINE_CHARACTERS = 4096

_PROGRESS = re.compile(
    r"Timestep:\s*(?P<timestep>\d{1,12})\s*\|\|[^\r\n]{0,1024}?Energy:\s*~"
    r"(?P<energy>[+\-]?(?:\d{1,24}(?:\.\d{0,24})?|\.\d{1,24})(?:[eE][+\-]?\d{1,4})?)\s*"
    r"\(\s*(?P<sign>[+\-])\s*(?P<decay>\d{1,8}(?:\.\d{0,8})?)\s*dB\s*\)"
)
_SUMMARY = re.compile(r"Time for\s+(?P<timestep>\d{1,12})\s+iterations\b")
_CAP_WARNING = re.compile(
    r"Max\. number of timesteps was reached before the end-criteria of\s*"
    r"(?P<decay>[+\-]?\d{1,8}(?:\.\d{0,8})?)\s*dB\s+was reached",
    re.IGNORECASE,
)
_CONFIGURED_CAP = re.compile(r"Max\. number of timesteps:\s*(?P<timestep>\d{1,12})\b")
_ENGINE_VERSION = re.compile(r"\|\s*openEMS\s+\S+\s+--\s+version\s+v?(?P<version>\S+)", re.IGNORECASE)


def _execution_status(execution: Mapping) -> str:
    if execution.get("timed_out") is True:
        return "timed_out"
    if execution.get("quota_exceeded") is True:
        return "quota_exceeded"
    returncode = execution.get("returncode")
    if type(returncode) is int:
        return "completed" if returncode == 0 else "process_failed"
    return "unknown"


def parse_openems_stopping(
    log_text: str,
    *,
    requested_end_criteria: float,
    requested_max_timesteps: int,
    execution: Mapping,
    runtime_identity: Mapping,
) -> dict:
    """Return stopping evidence without equating normal exit with decay success.

    openEMS 0.0.36 exposes no structured stopping result from ``Run``.  This
    parser therefore consumes only the bounded native log retained by SPIKE.
    Exact final iteration counts come from the native summary; progress lines
    remain explicitly last-observed samples when a summary is absent.
    """
    if not isinstance(log_text, str):
        raise TypeError("OpenEMS stopping log must be text")
    if (isinstance(requested_end_criteria, bool)
            or not isinstance(requested_end_criteria, (int, float))
            or not math.isfinite(requested_end_criteria)
            or requested_end_criteria <= 0):
        raise ValueError("OpenEMS end criterion must be finite and positive")
    if type(requested_max_timesteps) is not int or requested_max_timesteps <= 0:
        raise ValueError("OpenEMS timestep cap must be a positive integer")
    if not isinstance(execution, Mapping) or not isinstance(runtime_identity, Mapping):
        raise TypeError("OpenEMS execution and runtime identity must be mappings")

    log_was_parser_truncated = len(log_text) > MAX_LOG_CHARACTERS
    bounded = log_text[-MAX_LOG_CHARACTERS:]
    samples = []
    summaries = []
    warnings = []
    configured_caps = []
    malformed_relevant_line_count = 0
    for line in bounded.splitlines():
        is_progress = "Timestep:" in line or "Energy:" in line
        is_summary = "Time for" in line and "iterations" in line
        is_warning = "end-criteria" in line
        is_configuration = "Max. number of timesteps:" in line
        if not (is_progress or is_summary or is_warning or is_configuration):
            continue
        if len(line) > MAX_RELEVANT_LINE_CHARACTERS:
            malformed_relevant_line_count += 1
            continue
        if is_progress:
            if line.count("Timestep:") != 1 or line.count("Energy:") != 1:
                malformed_relevant_line_count += 1
                continue
            match = _PROGRESS.search(line)
            if match is None:
                malformed_relevant_line_count += 1
                continue
            energy = float(match.group("energy"))
            decay_magnitude = float(match.group("decay"))
            decay_db = (-1.0 if match.group("sign") == "-" else 1.0) * decay_magnitude
            if (not math.isfinite(energy) or energy < 0
                    or not math.isfinite(decay_db) or decay_db > 0):
                malformed_relevant_line_count += 1
                continue
            samples.append({"timestep": int(match.group("timestep")),
                            "energy": energy, "decay_db": decay_db})
            continue
        if is_summary:
            match = _SUMMARY.search(line)
            if match is None:
                malformed_relevant_line_count += 1
            else:
                summaries.append(int(match.group("timestep")))
            continue
        if is_warning:
            match = _CAP_WARNING.search(line)
            if match is None:
                malformed_relevant_line_count += 1
            else:
                decay = float(match.group("decay"))
                if not math.isfinite(decay) or decay > 0:
                    malformed_relevant_line_count += 1
                else:
                    warnings.append(decay)
            continue
        match = _CONFIGURED_CAP.search(line)
        if match is None:
            malformed_relevant_line_count += 1
        else:
            configured_caps.append(int(match.group("timestep")))

    requested_db = 10.0 * math.log10(float(requested_end_criteria))
    observed = samples[-1] if samples else None
    final_count = summaries[-1] if summaries else None
    status = _execution_status(execution)
    retained_log_truncated = execution.get("log_truncated") is True or log_was_parser_truncated
    native_cap = configured_caps[-1] if configured_caps else None
    cap_configuration_matches = native_cap == requested_max_timesteps if native_cap is not None else None
    native_decay = warnings[-1] if warnings else None
    decay_configuration_matches = (math.isclose(native_decay, requested_db, rel_tol=0, abs_tol=0.005)
                                   if native_decay is not None else None)
    configuration_mismatch = cap_configuration_matches is False or decay_configuration_matches is False
    if warnings:
        cap_hit = True
    elif final_count is not None:
        cap_hit = final_count >= (native_cap if native_cap is not None else requested_max_timesteps)
    else:
        cap_hit = None

    reached = None
    if (status == "completed" and not retained_log_truncated
            and not malformed_relevant_line_count and not configuration_mismatch):
        if warnings:
            reached = False
        elif cap_hit is True:
            reached = False
        elif (observed is not None and final_count is not None
              and observed["timestep"] == final_count
              and observed["decay_db"] <= requested_db):
            reached = True

    if status == "timed_out":
        reason = "execution_timeout"
    elif status == "quota_exceeded":
        reason = "output_quota_exceeded"
    elif status == "process_failed":
        reason = "process_failed"
    elif status == "unknown":
        reason = "execution_status_unknown"
    elif retained_log_truncated:
        reason = "stopping_evidence_truncated"
    elif configuration_mismatch:
        reason = "runtime_configuration_mismatch"
    elif malformed_relevant_line_count:
        reason = "malformed_stopping_evidence"
    elif warnings:
        reason = "timestep_cap_before_requested_decay"
    elif cap_hit is True:
        reason = "timestep_cap_without_requested_decay"
    elif reached is True:
        reason = "requested_decay_observed"
    else:
        reason = "requested_decay_unconfirmed"

    if retained_log_truncated:
        evidence_status = "truncated"
    elif configuration_mismatch:
        evidence_status = "inconsistent"
    elif malformed_relevant_line_count:
        evidence_status = "malformed"
    elif samples or summaries or warnings:
        evidence_status = "observed"
    else:
        evidence_status = "missing"

    identified_runtime = dict(runtime_identity)
    versions = [match.group("version") for match in _ENGINE_VERSION.finditer(bounded)]
    if versions:
        identified_runtime["native_engine_version"] = versions[-1]

    return {
        "contract": STOPPING_CONTRACT,
        "execution_status": status,
        "requested_energy_decay_ratio": float(requested_end_criteria),
        "requested_energy_decay_db": requested_db,
        "requested_max_timesteps": requested_max_timesteps,
        "observed_energy_decay_db": observed["decay_db"] if observed else None,
        "observed_energy": observed["energy"] if observed else None,
        "observed_energy_timestep": observed["timestep"] if observed else None,
        "actual_final_timestep_count": final_count,
        "last_observed_timestep": observed["timestep"] if observed else None,
        "timestep_cap_hit": cap_hit,
        "did_reach_requested_decay": reached,
        "stopping_reason": reason,
        "evidence_status": evidence_status,
        "evidence_source": "bounded_openems_native_log_parser",
        "parser_id": PARSER_ID,
        "runtime_identity": identified_runtime,
        "native_reported_end_criteria_db": native_decay,
        "native_reported_max_timesteps": native_cap,
        "native_end_criteria_matches_request": decay_configuration_matches,
        "native_timestep_cap_matches_request": cap_configuration_matches,
        "malformed_relevant_line_count": malformed_relevant_line_count,
    }
