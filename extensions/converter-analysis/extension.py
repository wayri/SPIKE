"""Bundled PWM converter study assistant extension."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def readiness(design: Dict[str, Any], selection: Dict[str, Any]) -> Dict[str, Any]:
    components = design.get("components", []) if isinstance(design, dict) else []
    pads = design.get("pads", []) if isinstance(design, dict) else []
    modeled = sum(1 for item in components if item.get("models") or item.get("model_path") or item.get("spice_model"))
    return {
        "design": str(design.get("name", "Untitled design")),
        "components": len(components),
        "pads": len(pads),
        "components_with_declared_models": modeled,
        "selection_available": bool(selection),
        "study_contract": "spike/converter-study/v1",
        "execution_method": "run_converter_study",
        "coupling": "one_way_staged",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    contribution = request.get("contribution_id", "")
    if contribution not in {"converter-study-assistant", "converter-design-readiness"}:
        raise ValueError(f"Unsupported contribution: {contribution}")
    context = request.get("context", {})
    data = readiness(context.get("design", {}), context.get("selection", {}))
    rows = [[key.replace("_", " ").title(), value] for key, value in data.items()]
    Path(args.result).write_text(json.dumps({
        "contract": "spike/extension-result/v1",
        "status": "completed",
        "title": "PWM converter study readiness",
        "view": {"type": "property_table", "columns": ["Property", "Value"], "rows": rows},
        "data": data,
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
