# SPDX-License-Identifier: Apache-2.0
"""Run a finite supplied-line candidate/corner study; no physical board claim."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.si_candidate_study import run_si_candidate_study


def request():
    return json.loads(Path(__file__).with_name("candidates.request.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    print(json.dumps(run_si_candidate_study(request()), allow_nan=False))
