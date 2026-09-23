"""Minimal SPIKE extension SDK example."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def summarize(design: Dict[str, Any]) -> Dict[str, Any]:
    names = sorted({
        str(item.get("name", ""))
        for item in design.get("nets", [])
        if item.get("name")
    })
    return {
        "net_count": len(names),
        "track_count": len(design.get("tracks", [])),
        "via_count": len(design.get("vias", [])),
        "zone_count": len(design.get("zones", [])),
        "layer_count": len(design.get("layers", [])),
        "nets": names,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    contribution = request.get("contribution_id", "")
    if contribution not in {"net-inventory-app", "summarize-nets", "net-inventory-report"}:
        raise ValueError(f"Unsupported contribution: {contribution}")
    inventory = summarize(request.get("context", {}).get("design", {}))
    Path(args.result).write_text(json.dumps({
        "contract": "spike/extension-result/v1",
        "status": "completed",
        "title": "Net inventory",
        "view": {
            "type": "property_table",
            "columns": ["Metric", "Value"],
            "rows": [
                ["Nets", inventory["net_count"]],
                ["Tracks", inventory["track_count"]],
                ["Vias", inventory["via_count"]],
                ["Zones", inventory["zone_count"]],
                ["Layers", inventory["layer_count"]]
            ]
        },
        "data": inventory
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
