# SPDX-License-Identifier: Apache-2.0
"""Export the current requested-library tranche without executing models.

Output is a new directory: never merge into or overwrite an installed library.
Manufacturer discovery records are deliberately separate from runnable models.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "standalone/spikes_project/studio/python"))

from spikes import logic_portfolio, manufacturer_model_catalog
from spikes_studio import compiled_part_models


def build(destination: Path) -> dict:
    """Write an inert, hash-inventoried snapshot; fail if destination exists."""
    destination = Path(destination)
    # Validate/generate everything before creating the destination.
    manufacturer_model_catalog.validate_catalog()
    records = compiled_part_models.records()
    files = {
        "manufacturer-acquisition.json": {
            "schema": manufacturer_model_catalog.CATALOG_SCHEMA,
            "records": manufacturer_model_catalog.catalog(),
            "coverage": manufacturer_model_catalog.coverage_summary(),
        },
        "logic-portfolio.json": {
            "contract": logic_portfolio.CONTRACT,
            "records": logic_portfolio.catalog(),
            "coverage": logic_portfolio.coverage_summary(),
        },
        "sampled-control-library.spkctl": compiled_part_models.catalog(),
    }
    for record in records:
        identifier = record["descriptor"]["id"]
        files[f"controllers/{identifier}.json"] = record["configuration"]
    encoded = {name: (json.dumps(data, indent=2, sort_keys=True,
                                allow_nan=False) + "\n").encode("utf-8")
               for name, data in files.items()}
    manifest = {
        "contract": "spikes/requested-library-snapshot/v1",
        "assessed_on": manufacturer_model_catalog.ASSESSED_ON,
        "files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(),
                   "bytes": len(data)} for name, data in sorted(encoded.items())],
        "manufacturer_models_runnable": 0,
        "manufacturer_models_qualified": 0,
        "compiled_generic_models": len(records),
        "logic": logic_portfolio.coverage_summary(),
        "complete_requested_portfolio": False,
        "limitations": [
            "Manufacturer records are acquisition evidence, not simulation models.",
            "Logic descriptors target the explicit Python reference backend; the native SDK is separate.",
            "Controller JSON can be loaded by the compiled-block workflow with explicit trust approval.",
            "Known compiled models use shared cross-parameter validation and output-envelope checks on import.",
            "Generic sampled models are not qualified manufacturer equivalents or continuous device physics.",
            "The full 54/74 portfolio and 100 qualified variants per active category remain open.",
        ],
    }
    encoded["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in encoded.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = build(args.output)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Library export failed: {exc}\n")
    print(json.dumps({"output": str(args.output.resolve()), **manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
