# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Verify lossless selected-pair preparation on pinned Marble and WREN sources.

This verifies geometry retention, not field extraction or protocol compliance.
No material assumptions, shortened routes, fitted tolerances or vendor models.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.si_pair_geometry import prepare_pair_geometry
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.spider_v2_schema import content_digest
from scripts.verify_si_board_protocol_readiness import BOARDS

OWNERS = (
    "scripts/verify_si_pair_geometry.py", "scripts/verify_si_board_protocol_readiness.py",
    "scripts/verify_si_real_boards.py", "scripts/verify_wren_si_scenario.py",
    "python/spike_core/si_pair_geometry.py", "python/spike_core/si_channel.py",
    "python/spike_core/spider_v2.py", "python/spike_core/spider_v2_schema.py",
    "python/spike_core/service_project.py", "python/spike_core/kicad_importer.py",
)
COLLECTIONS = ("tracks", "arcs", "vias", "pads", "zones", "drills", "castellations")


def check_preparation(design: SpiDeRV2, result: dict) -> dict:
    """Independent retention/interval checks; do not trust the coverage flags."""
    if (result["channel_extracted"] is not False or result["production_qualified"] is not False
            or result["compliance_status"] != "not_evaluated"):
        raise ValueError("Geometry preparation must not claim channel qualification")
    bound = {key: value for key, value in result.items() if key != "preparation_digest_sha256"}
    if content_digest(bound) != result["preparation_digest_sha256"]:
        raise ValueError("Preparation digest mismatch")
    if (result["design_digest_sha256"] != content_digest(design.to_dict())
            or result["source"] != asdict(design.source)):
        raise ValueError("Preparation source/design identity mismatch")
    retained, summary, expected_tracks = [], {}, {}
    for polarity in ("signal", "victim"):
        route = result["routes"][polarity]
        counts = {}
        for name in COLLECTIONS:
            expected = sorted((item for item in getattr(design, name)
                               if item.net_id == route["net_id"]), key=lambda item: item.id)
            if route["sources"][name] != [asdict(item) for item in expected]:
                raise ValueError(f"{polarity}: retained {name} differ from source")
            retained.extend(item.id for item in expected)
            counts[name] = len(expected)
            if name == "tracks":
                expected_tracks.update({item.id: item for item in expected})
        summary[polarity] = {"source_counts": counts,
                             "topology_status": route["topology"]["status"],
                             "straight_centerline_length_mm": route["straight_centerline_length_mm"],
                             "transition_count": len(route["transition_regions"])}
    if (sorted(retained) != result["coverage"]["retained_source_ids"]
            or len(retained) != result["coverage"]["retained_source_count"]):
        raise ValueError("Retained-source inventory mismatch")
    intervals = {identifier: [] for identifier in expected_tracks}
    for part in result["track_partitions"]:
        if part["track_id"] not in intervals:
            raise ValueError("Partition names an unselected source")
        lo, hi = (Fraction(*item) for item in part["interval"])
        if not 0 <= lo < hi <= 1:
            raise ValueError("Invalid retained source interval")
        intervals[part["track_id"]].append((lo, hi))
    for pieces in intervals.values():
        pieces.sort()
        if (not pieces or pieces[0][0] != 0 or pieces[-1][1] != 1
                or any(a[1] != b[0] for a, b in zip(pieces, pieces[1:]))):
            raise ValueError("Selected source interval lost or multiply covered")
    return {"routes": summary, "retained_source_count": len(retained),
            "parallel_candidate_count": len(result["parallel_overlap_candidates"]),
            "partition_count": len(result["track_partitions"]),
            "preparation_digest_sha256": result["preparation_digest_sha256"],
            "retention_checks": "passed", "channel_extracted": False,
            "production_qualified": False, "compliance_status": "not_evaluated"}


def evaluate_board(name: str) -> dict:
    from python.spike_core.service_project import import_design

    spec = BOARDS[name]
    path = ROOT / spec["path"]
    identity = sha256(path.read_bytes()).hexdigest()
    if identity != spec["sha256"]:
        raise ValueError(f"{name}: pinned source identity mismatch")
    imported = import_design(str(path.resolve()), with_report=True)
    design = SpiDeRV2.from_dict(imported["design"])
    if design.source.source_digest != identity:
        raise ValueError(f"{name}: importer source identity mismatch")
    before = content_digest(design.to_dict())
    pairs = {}
    for pair in spec["pairs"]:
        request = {"signal_net": pair + "_P", "victim_net": pair + "_N",
                   "reference_net": "GND", "reference_layer": "In1.Cu"}
        pairs[pair] = check_preparation(design, prepare_pair_geometry(design, request))
    if before != content_digest(design.to_dict()):
        raise ValueError("Preparation mutated the imported design")
    if identity != sha256(path.read_bytes()).hexdigest():
        raise ValueError("Board source changed during verification")
    return {"source_path": str(spec["path"]), "source_sha256": identity,
            "design_digest_sha256": before, "import_status": imported["report"]["status"],
            "pairs": pairs}


def build_evidence() -> dict:
    hashes = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in OWNERS}
    boards = {name: evaluate_board(name) for name in BOARDS}
    if hashes != {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in OWNERS}:
        raise ValueError("Inspected implementation changed during verification")
    return {"contract": "spike/si-pair-retention-evidence/v1", "boards": boards,
            "source_sha256": hashes, "retention_checks": "passed",
            "channel_extracted": False, "production_qualified": False,
            "compliance_status": "not_evaluated",
            "scope": "Complete selected-net source and exact straight-track parameter coverage only"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("A fresh output file is required")
    result = build_evidence()
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"retention_checks": result["retention_checks"],
                      "pair_count": sum(len(row["pairs"]) for row in result["boards"].values()),
                      "channel_extracted": False, "production_qualified": False}))
    return 0  # Only the explicitly named retention checks succeeded.


if __name__ == "__main__":
    raise SystemExit(main())
