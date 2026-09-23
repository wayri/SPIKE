# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Execute a loaded 10.3125-GBd example and compare recovered observed symbols."""
import json
from pathlib import Path
import platform
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from python.spike_core.si_channel import _prbs7
from python.spike_core.si_workflow import run_si_workflow


def qualification_report():
    request = json.loads((ROOT / "examples/si/10g-nrz-cdr.json").read_text())
    result = run_si_workflow(request)
    if result["time_domain"]["status"] != "completed":
        return {"status": "fail", "reason": result["time_domain"], "result": result}
    cdr = result["time_domain"]["receivers"][0]["clock_recovery"]
    times = np.asarray(cdr["sample_times_s"])
    voltage = np.asarray(cdr["sample_values_v"])
    # Independent physical mapping: delay=l*sqrt(LC) of this matched ideal line.
    channel = request["channel"]
    delay = channel["length_m"] * np.sqrt(channel["inductance_h_per_m"] * channel["capacitance_f_per_m"])
    coordinates = (times - delay) * request["bit_rate_hz"]
    indices = np.floor(coordinates).astype(int)
    valid = (indices >= 128) & (indices < request["bit_count"] - 2)
    observed = int(np.count_nonzero(valid))
    expected = _prbs7(request["bit_count"])[indices[valid]]
    decisions = voltage[valid] >= request["receivers"][0]["cdr"]["threshold_v"]
    errors = int(np.count_nonzero(decisions != expected))
    criteria = {"time_domain_completed": True, "at_least_800_observed_symbols": observed >= 800,
                "observed_symbol_errors_zero": errors == 0,
                "transition_updates_available": cdr["status"] == "tracking",
                "no_frequency_bound_hits": cdr["frequency_bound_hit_count"] == 0}
    return {"contract": "spike/cdr-workflow-verification/v1",
            "status": "pass" if all(criteria.values()) else "fail", "criteria": criteria,
            "observed_symbols": observed, "observed_symbol_errors": errors,
            "runtime": {"python": platform.python_version(), "numpy": np.__version__},
            "production_qualified": False, "request": request, "result": result,
            "limitations": ["Finite deterministic PRBS7 observation; zero errors is not a BER guarantee.",
                            "Analytical matched-line fixture, not a measured/protocol receiver qualification."]}


if __name__ == "__main__":
    report = qualification_report()
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    raise SystemExit(0 if report["status"] == "pass" else 1)
