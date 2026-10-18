# SPDX-License-Identifier: Apache-2.0
"""Original three-section supplied RLGC line; no inferred transition geometry."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from python.spike_core.rlgc_line_cascade import run_rlgc_line_cascade


def request():return json.loads(Path(__file__).with_name('three-sections.request.json').read_text(encoding='utf-8'))


if __name__=='__main__':print(json.dumps(run_rlgc_line_cascade(request()),indent=2,allow_nan=False))
