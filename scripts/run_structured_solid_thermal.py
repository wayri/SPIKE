# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Fixed-file CLI for the bounded structured solid-thermal reference solver."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.structured_solid_thermal import solve_structured_solid_thermal
from python.spike_core.structured_electrothermal import CONTRACT as COUPLED_CONTRACT, solve_structured_electrothermal
from python.spike_core.transient_diode_field import CONTRACT as DIODE_CONTRACT, solve_transient_diode_field
from python.spike_core.laminar_channel_cht import CONTRACT as CHANNEL_CONTRACT, solve_laminar_channel_cht
from python.spike_core.enclosure_stokes import CONTRACT as ENCLOSURE_CONTRACT, solve_enclosure_stokes


MAX_CONTROL_BYTES = 8 * 1024 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SPIKE bounded 3-D structured solid-thermal reference solver.")
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request_path, result_path = _path(args.request), _path(args.result)
    if request_path == result_path or not request_path.is_file() or request_path.stat().st_size > MAX_CONTROL_BYTES:
        parser.error("request/result paths are invalid or the request exceeds 8 MiB")
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(f"cannot read request: {exc}")
    contract = request.get("contract") if isinstance(request, dict) else None
    if contract == ENCLOSURE_CONTRACT:
        result = solve_enclosure_stokes(request)
    elif contract == CHANNEL_CONTRACT:
        result = solve_laminar_channel_cht(request)
    elif contract == DIODE_CONTRACT:
        result = solve_transient_diode_field(request)
    elif contract == COUPLED_CONTRACT:
        result = solve_structured_electrothermal(request)
    else:
        result = solve_structured_solid_thermal(request)
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"
    if len(payload.encode("ascii")) > MAX_CONTROL_BYTES:
        parser.error("result exceeds the 8 MiB control-file limit")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = result_path.with_name(f".{result_path.name}.{os.getpid()}.tmp")
    temporary.write_text(payload, encoding="ascii", newline="\n")
    os.replace(temporary, result_path)
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
