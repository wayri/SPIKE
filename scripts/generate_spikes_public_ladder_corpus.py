"""Regenerate the first-party CC0 equal-model ladder corpus."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spikes.public_corpus import PUBLIC_LADDER_SIZES, render_ladder_deck


def main() -> int:
    destination = ROOT / "benchmarks" / "public_equal_model"
    destination.mkdir(parents=True, exist_ok=True)
    for tier, sections in PUBLIC_LADDER_SIZES.items():
        path = destination / f"ladder_{tier}_{sections}.cir"
        path.write_bytes(render_ladder_deck(tier, sections))
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
