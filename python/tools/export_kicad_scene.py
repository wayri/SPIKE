"""Export an offline, renderer-ready KiCad scene and quality manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from python.spike_core.models import export_kicad_visual_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    output_directory = (args.output if not args.output.suffix else args.output.parent / args.output.stem).resolve()
    result = export_kicad_visual_bundle(args.board, output_directory, args.timeout)
    manifest = args.manifest.resolve() if args.manifest else output_directory / f"{args.board.stem}.scene.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    portable_manifest = dict(result)
    portable_manifest["scenes"] = {
        key: Path(value).relative_to(output_directory).as_posix()
        for key, value in result["scenes"].items()
    }
    portable_manifest["layout"] = {
        **result["layout"],
        "layers": {
            key: Path(value).relative_to(output_directory).as_posix()
            for key, value in result["layout"]["layers"].items()
        },
    }
    portable_manifest["generator"] = {
        key: value for key, value in result["generator"].items() if key != "runtime_path"
    }
    manifest.write_text(json.dumps(portable_manifest, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "scenes": result["scenes"],
        "layout": result["layout"],
        "manifest": str(manifest.resolve()),
        "missing_model_count": result["quality"]["missing_model_count"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
