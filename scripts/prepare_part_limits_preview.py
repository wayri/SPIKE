# SPDX-License-Identifier: Apache-2.0
"""Create original cached backend evidence for the part-limit UI fixture."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.engineering_review import review_engineering

rules = json.loads((ROOT / "examples/part_limits/part-limits.json").read_text(encoding="utf-8"))["rules"]
request = {"contract": "spike/engineering-review-request/v1", "boards": [
    {"occurrence_id": "board-a", "design": {"components": [{"id": "u1", "reference": "U1", "value": "Synthetic test part"}]}}],
    "overrides": [], "part_limits": rules}
output = ROOT / "app/.tmp/part-limits-review.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"request": request, "result": review_engineering(request)}, indent=2) + "\n", encoding="utf-8")
print(output)
