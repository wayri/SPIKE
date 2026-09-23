"""Load narrowly scoped, version-bound openEMS validation evidence."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


EVIDENCE_CONTRACT = "spike/openems-reference-validation/v1"


@lru_cache(maxsize=1)
def load_openems_reference_evidence() -> Dict[str, Any] | None:
    path = Path(__file__).with_name("validation_data") / "openems-simple-patch-v1.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if payload.get("contract") != EVIDENCE_CONTRACT or payload.get("status") != "passed":
        return None
    runs = payload.get("runs")
    convergence = payload.get("convergence")
    if not isinstance(runs, list) or len(runs) < 3 or not isinstance(convergence, dict):
        return None
    numeric = [
        run.get(key)
        for run in runs
        for key in ("mesh_resolution_mm", "resonance_hz", "maximum_directivity_linear")
    ]
    numeric.extend(convergence.values())
    try:
        if not all(math.isfinite(float(value)) for value in numeric):
            return None
    except (TypeError, ValueError):
        return None
    if float(convergence["finest_pair_resonance_relative_change"]) > float(convergence["maximum_resonance_relative_change"]):
        return None
    if float(convergence["finest_pair_directivity_relative_change"]) > float(convergence["maximum_directivity_relative_change"]):
        return None
    return payload


def matching_openems_reference_evidence(engine_version: str, adapter_version: str) -> Dict[str, Any] | None:
    evidence = load_openems_reference_evidence()
    if evidence is None:
        return None
    if str(evidence.get("engine", {}).get("version")) != str(engine_version):
        return None
    if str(evidence.get("adapter_version")) != str(adapter_version):
        return None
    return evidence


__all__ = ["load_openems_reference_evidence", "matching_openems_reference_evidence"]
