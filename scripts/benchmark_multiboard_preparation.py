# SPDX-License-Identifier: Apache-2.0
"""Bounded repeated-source benchmark for multi-board preparation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.multiboard_analysis import _design_summary
from python.spike_core.multiboard_execution import _plain_json_source
from python.spike_core.spider_v2 import SpiDeRV2


def retained_design(track_count: int) -> dict:
    return {
        "contract": "spike/design-ir/v2", "design_id": "shared-layout", "name": "Shared benchmark layout",
        "source": {"source_format": "synthetic", "source_digest": "benchmark-shared-layout"},
        "layers": [{"id": "front", "name": "F.Cu", "layer_type": "copper"}],
        "tracks": [{"id": f"track-{index}", "start_mm": [float(index), 0.0],
                    "end_mm": [float(index) + 0.5, 1.0]} for index in range(track_count)],
        "arcs": [], "vias": [], "pads": [], "zones": [], "regions": [],
        "components": [], "nets": [],
    }


def elapsed(operation, repeats: int) -> list[float]:
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - started) * 1000.0)
    return samples


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--occurrences", type=int, default=30)
    parser.add_argument("--tracks", type=int, default=4000)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    if not 2 <= args.occurrences <= 30 or not 1 <= args.tracks <= 20_000 or not 3 <= args.repeats <= 30:
        raise SystemExit("benchmark bounds exceeded")

    design = retained_design(args.tracks)
    expected_summary = _design_summary(design)
    expected_parsed = SpiDeRV2.from_dict(design).to_dict()

    def before():
        summaries = [_design_summary(design) for _ in range(args.occurrences)]
        parsed = [SpiDeRV2.from_dict(design) for _ in range(args.occurrences)]
        return summaries, parsed

    def after():
        summary_cache = {"shared-layout": _design_summary(design)}
        summaries = [summary_cache["shared-layout"] for _ in range(args.occurrences)]
        cacheable = _plain_json_source(design)
        cached = SpiDeRV2.from_dict(design) if cacheable else None
        parsed = [cached if cacheable else SpiDeRV2.from_dict(design) for _ in range(args.occurrences)]
        return summaries, parsed

    before_summaries, before_parsed = before()  # warm imports and dataclass paths
    after_summaries, after_parsed = after()
    assert all(value == expected_summary for value in before_summaries + after_summaries)
    assert all(value.to_dict() == expected_parsed for value in before_parsed + after_parsed)
    before_ms = elapsed(before, args.repeats)
    after_ms = elapsed(after, args.repeats)
    before_median = statistics.median(before_ms)
    after_median = statistics.median(after_ms)
    occurrence_ids = [f"board-{index:02d}" for index in range(args.occurrences)]
    namespaces = [f"assembly/{value}" for value in occurrence_ids]
    report = {
        "contract": "spike/multiboard-preparation-performance/v1",
        "fixture": {"occurrences": args.occurrences, "unique_designs": 1, "tracks": args.tracks,
                    "repeats": args.repeats},
        "before_median_ms": before_median,
        "after_median_ms": after_median,
        "speedup": before_median / after_median,
        "summary_scans_before": args.occurrences, "summary_scans_after": 1,
        "design_parses_before": args.occurrences, "design_parses_after": 1,
        "plain_json_admission_walks_after": 1,
        "identity_checks": {"board_ids_unique": len(set(occurrence_ids)) == args.occurrences,
                            "namespaces_unique": len(set(namespaces)) == args.occurrences,
                            "source_design_id": "shared-layout"},
        "samples_ms": {"before": before_ms, "after": after_ms},
        "notes": "Preparation-only synthetic fixture; no solver, native UI, large board, or CFD run.",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
