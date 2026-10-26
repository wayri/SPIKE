# SPDX-License-Identifier: Apache-2.0
"""Saved-study bridge for the explicit AC-resistor to creeping-CHT runner."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from typing import Any
import uuid

from .multiboard_identity import canonical_json_digest
from .solvers.execution.coupling import em_network_resistor_cht as solver


CASE_TYPE = "em-resistor-cht"
_PAYLOAD_FIELDS = {"request", "result", "study"}
_RESULT_BYTES = 16 * 1024**2
_STUDY_BYTES = 3 * 1024**2


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError("EM_RESISTOR_CHT_STUDY: " + message)


def _plain_json(value: Any, limit: int, label: str) -> Any:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError(f"EM_RESISTOR_CHT_STUDY: {label} must be finite plain JSON: {exc}") from exc
    _require(len(encoded) <= limit, f"{label} exceeds {limit} bytes")
    return json.loads(encoded)


def _admit_request(value: Any) -> dict[str, Any]:
    raw = solver._snapshot(value)
    cht = raw["cht_request"]
    _require(isinstance(cht, dict) and "mesh" in cht and isinstance(cht.get("energy"), dict),
             "explicit retained CHT request required")
    geometry, _ = solver._admit_with_reuse(cht["mesh"])
    fluid = solver._phases(cht["energy"], len(geometry["cell_volumes"]))
    sources = cht["energy"].get("source_w_m3")
    _require(isinstance(sources, list) and len(sources) == len(fluid)
             and all(type(item) in (int, float) and item == 0. for item in sources),
             "pre-existing volumetric sources must be exactly zero")
    ac = raw["ac_request"]
    _require(isinstance(ac, dict) and isinstance(ac.get("source"), dict),
             "explicit sampled AC source required")
    ports = ac["source"].get("port_names")
    frequencies = ac["source"].get("frequencies_hz")
    _require(isinstance(ports, list) and 1 <= len(ports) <= 16
             and all(isinstance(port, str) and port for port in ports)
             and len(set(ports)) == len(ports), "unique ordered AC port names required")
    index = raw["sample_index"]
    _require(isinstance(frequencies, list) and type(index) is int and 0 <= index < len(frequencies),
             "select one explicit AC frequency index")
    solver._mapping(raw["resistor_cell_weights"], ports, fluid)
    return raw


def _result_matches(result: Any, request: dict[str, Any]) -> bool:
    ac = result.get("ac") if isinstance(result, dict) else None
    cht = result.get("cht") if isinstance(result, dict) else None
    return (isinstance(result, dict)
            and result.get("contract") == solver.RESULT_CONTRACT
            and result.get("input_digest_sha256") == canonical_json_digest(request)
            and result.get("mesh_digest_sha256") == canonical_json_digest(request["cht_request"]["mesh"])
            and result.get("model_status") == "experimental"
            and result.get("production_qualified") is False
            and isinstance(ac, dict)
            and ac.get("contract") == "spike/em-network-ac-result/v1"
            and isinstance(ac.get("samples"), list)
            and isinstance(cht, dict)
            and cht.get("contract") == "spike/cfd-tetra-cht-result/v1"
            and cht.get("status") == "completed"
            and isinstance(cht.get("fields"), dict)
            and isinstance(cht.get("diagnostics"), dict)
            and isinstance(cht["diagnostics"].get("energy"), dict))


def _admit_result(value: Any, request: dict[str, Any]) -> dict[str, Any]:
    result = _plain_json(value, _RESULT_BYTES, "result")
    _require(_result_matches(result, request),
             "result contract, experimental status, input digest, or mesh digest does not match request")
    return result


def _stable_id(kind: str, value: Any) -> str:
    return f"{kind}-{canonical_json_digest(value)[:24]}"


def _run(settings: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    facts = {}
    for source, target in (("contract", "contract"), ("status", "status"),
                           ("model_status", "modelStatus")):
        if isinstance(result.get(source), str):
            facts[target] = result[source]
    if isinstance(result.get("cht"), dict) and isinstance(result["cht"].get("status"), str):
        facts["status"] = result["cht"]["status"]
    return {
        "id": str(uuid.uuid4()),
        "capturedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "association": "workspace-capture",
        "caseType": CASE_TYPE,
        "mode": "steady",
        "scenario": {},
        "settings": copy.deepcopy(settings),
        "facts": facts,
        "resultSnapshot": copy.deepcopy(result),
    }


def _append_history(runs: list[Any], settings: dict[str, Any], result: dict[str, Any],
                    *, force: bool = False) -> list[Any]:
    retained = copy.deepcopy(runs)
    if not force and any(isinstance(item, dict)
                         and item.get("settings") == settings
                         and item.get("resultSnapshot") == result for item in retained):
        return retained
    candidate = _run(settings, result)
    retained.append(candidate)
    return retained


def _new_study(request: dict[str, Any]) -> dict[str, Any]:
    digest = canonical_json_digest(request)
    return {
        "version": 1,
        "id": f"em-resistor-cht-study-{digest[:24]}",
        "name": "AC resistor / CHT study",
        "notes": "",
        "tags": ["em-resistor-cht", "experimental"],
        "archived": False,
        "datasets": [],
        "cases": [{
            "id": f"em-resistor-cht-case-{digest[:24]}",
            "type": CASE_TYPE,
            "mode": "steady",
            "name": "AC resistor / solid / fluid heat coupling",
            "notes": "Experimental; not production qualified.",
            "scenario": {},
            "settings": {"request": copy.deepcopy(request)},
            "runs": [],
            "datasetIds": [],
        }],
    }


def _admit_study(value: Any) -> dict[str, Any]:
    study = _plain_json(value, _STUDY_BYTES, "study")
    _require(isinstance(study, dict) and study.get("version") == 1, "SimulationStudy v1 required")
    cases = study.get("cases")
    _require(isinstance(cases, list) and len(cases) == 1,
             "supplied study must contain exactly one unambiguous case")
    case = cases[0]
    _require(isinstance(case, dict) and case.get("type") == CASE_TYPE,
             f"the sole case must have type {CASE_TYPE}")
    _require(isinstance(case.get("settings"), dict)
             and isinstance(case["settings"].get("request"), dict), "saved case request required")
    _require(isinstance(case.get("runs", []), list), "saved case history must be an array")
    return study


def prepare_em_resistor_cht_study(payload: Any) -> dict[str, Any]:
    """Admit and bind a solver request/result without executing either solver."""
    _require(isinstance(payload, dict) and set(payload).issubset(_PAYLOAD_FIELDS)
             and set(payload).issuperset({"request"}),
             "exact request plus optional result and study fields required")
    request = _admit_request(payload["request"])
    study = _admit_study(payload["study"]) if "study" in payload else _new_study(request)
    case = study["cases"][0]
    previous_settings = copy.deepcopy(case["settings"])
    previous_request = previous_settings["request"]
    previous_result = case.get("resultSnapshot")
    runs = copy.deepcopy(case.get("runs", []))
    request_changed = previous_request != request
    if previous_result is not None:
        if not request_changed and not _result_matches(previous_result, previous_request):
            raise ValueError("EM_RESISTOR_CHT_STUDY: stored current result does not match its unchanged request")
        if isinstance(previous_result, dict) and request_changed:
            runs = _append_history(runs, previous_settings, previous_result)
        case.pop("resultSnapshot", None)
    if request_changed or "result" in payload:
        case.pop("resultRef", None)
    case["settings"] = {"request": copy.deepcopy(request)}
    case["mode"] = "steady"
    if "result" in payload:
        current = _admit_result(payload["result"], request)
        runs = _append_history(runs, case["settings"], current, force=True)
        case["resultSnapshot"] = copy.deepcopy(current)
    elif previous_result is not None and previous_request == request and _result_matches(previous_result, request):
        case["resultSnapshot"] = copy.deepcopy(previous_result)
    case["runs"] = runs
    output = _plain_json(study, _STUDY_BYTES, "prepared study")
    _require(len(output["cases"][0]["runs"]) <= 100, "case history exceeds 100 runs")
    return output
