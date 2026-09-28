# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Refill a copied KiCad PCB and record reproducible recovery provenance.

The source board is only read.  The result is a KiCad-generated candidate,
not evidence that an upstream conversion was lossless or physically correct.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_import(board: Path) -> dict[str, Any]:
    """Return SPIKE importer evidence without treating outlines as copper."""
    from python.spike_core.kicad_importer import import_kicad_design

    design = import_kicad_design(str(board))
    zones = list(design.zones)
    source_ids = [str(zone.get("source_zone_id", "")) for zone in zones]
    return {
        "zone_records": len(zones),
        "source_zone_ids": sorted(set(source_ids) - {""}),
        "source_zone_id_counts": dict(sorted(Counter(source_ids).items())),
        "outline_intent_records": sum(
            zone.get("source_kind") == "zone_outline_intent" for zone in zones
        ),
        "filled_component_records": sum(
            bool(zone.get("source_fill_provenance_complete")) for zone in zones
        ),
        "filled_component_ids": sorted(
            str(zone.get("filled_copper_id", "")) for zone in zones
            if zone.get("filled_copper_id")
        ),
        "import_issue_count": len(design.issues),
        "import_issue_codes": sorted(issue.code for issue in design.issues),
    }


def compare_summary(source: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    source_ids = set(source["source_zone_ids"])
    candidate_ids = set(candidate["source_zone_ids"])
    return {
        "source_zone_ids_preserved": source_ids == candidate_ids,
        "source_zone_ids_missing": sorted(source_ids - candidate_ids),
        "source_zone_ids_added": sorted(candidate_ids - source_ids),
        "source_zone_id_counts_preserved": (
            source["source_zone_id_counts"] == candidate["source_zone_id_counts"]
        ),
        "filled_component_records_delta": (
            candidate["filled_component_records"] - source["filled_component_records"]
        ),
        "outline_intent_records_delta": (
            candidate["outline_intent_records"] - source["outline_intent_records"]
        ),
    }


def bounded_text(value: str | bytes, limit: int = 16_000) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value if len(value) <= limit else value[:limit] + "\n...[truncated]"


def copy_inputs(source: Path, output: Path) -> tuple[Path, list[dict[str, str]]]:
    if output.exists():
        raise ValueError("Output directory must not already exist")
    output.mkdir(parents=True)
    candidate = output / source.name
    copied = []
    for item in (source, source.with_suffix(".kicad_pro")):
        if item.is_file():
            target = output / item.name
            shutil.copy2(item, target)
            copied.append({"source": str(item), "candidate": str(target), "sha256": sha256(target)})
    if not candidate.is_file():
        raise ValueError("Could not create copied board")
    return candidate, copied


def recover(source: Path, output: Path, kicad_cli: Path, timeout_s: int = 300) -> dict[str, Any]:
    source = source.resolve(strict=True)
    if source.suffix.lower() != ".kicad_pcb":
        raise ValueError("Input must be a .kicad_pcb board")
    output = output.resolve()
    if output == source.parent or source.parent in output.parents:
        raise ValueError("Output must not be the source directory or an ancestor of it")
    source_hash_before = sha256(source)
    source_summary = summarize_import(source)
    candidate, copied = copy_inputs(source, output)
    diagnostic_path = output / "native-drc.json"
    command = [str(kicad_cli), "pcb", "drc", "--format", "json", "--output",
               str(diagnostic_path), "--severity-all", "--refill-zones", "--save-board",
               str(candidate)]
    try:
        native = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s)
        native_record = {
            "command": command, "returncode": native.returncode,
            "stdout": bounded_text(native.stdout), "stderr": bounded_text(native.stderr),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as error:
        native_record = {
            "command": command, "returncode": None,
            "stdout": bounded_text(error.stdout or ""), "stderr": bounded_text(error.stderr or ""),
            "timed_out": True,
        }
    if not candidate.is_file():
        raise RuntimeError("KiCad did not retain the copied board")
    candidate_summary = summarize_import(candidate)
    source_hash_after = sha256(source)
    report = {
        "contract": "spike/kicad-zone-refill-recovery/v1",
        "source": {"path": str(source), "sha256_before": source_hash_before,
                   "sha256_after": source_hash_after,
                   "unchanged": source_hash_before == source_hash_after,
                   "spike_import": source_summary},
        "candidate": {"path": str(candidate), "sha256": sha256(candidate),
                      "spike_import": candidate_summary},
        "copied_inputs": copied,
        "native_diagnostics": native_record,
        "refill_completed": native_record["returncode"] == 0 and not native_record["timed_out"],
        "native_diagnostics_path": str(diagnostic_path) if diagnostic_path.is_file() else "",
        "comparison": compare_summary(source_summary, candidate_summary),
        "provenance": {
            "candidate_copper_origin": "KiCad zone refill on copied input",
            "source_fill_preserved_is_not_conversion_losslessness": True,
            "refill_is_not_physical_fabrication_evidence": True,
            "solver_qualified": False,
        },
    }
    (output / "zone-fill-recovery.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--kicad-cli", type=Path,
                        default=Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"))
    parser.add_argument("--timeout-s", type=int, default=300)
    args = parser.parse_args()
    report = recover(args.input, args.output, args.kicad_cli.resolve(strict=True), args.timeout_s)
    print(json.dumps({"report": str(args.output.resolve() / "zone-fill-recovery.json"),
                      "source_unchanged": report["source"]["unchanged"],
                      "refill_completed": report["refill_completed"],
                      "native_returncode": report["native_diagnostics"]["returncode"],
                      "comparison": report["comparison"]}, indent=2))
    return 0 if report["refill_completed"] and report["source"]["unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
