# SPDX-License-Identifier: Apache-2.0
"""Generate native preview data by running original synthetic PI fixtures."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.python.test_smps_converter import request as smps_request
from tests.python.test_capacitor_placement import request as cap_request
from tests.python.test_pi_return_path import request as return_request, design
from python.spike_core.service import handle


def main():
    payload = {}
    for key, method, params in [
        ("smps", "run_smps_converter", {"request": smps_request(losses=True)}),
        ("capacitor", "evaluate_capacitor_placement", {"request": cap_request()}),
        ("return", "plan_pi_return_path", {"request": return_request(), "design": design()}),
    ]:
        response = handle({"method": method, "params": params})
        if not response["ok"]:
            raise RuntimeError(response["error"])
        payload[key] = {**params, "result": response["result"]}
    destination = ROOT / "app/scripts/fixtures/pi-engineering-result.json"
    destination.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Generated original PI numerical preview fixtures: {destination}")


if __name__ == "__main__":
    main()
