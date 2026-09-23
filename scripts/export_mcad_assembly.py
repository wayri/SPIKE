"""Export a SPIKE named mechanical assembly to a STEP/FCStd/BREP ZIP."""
import argparse
import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.spike_core.mcad_export import export_assembly
from python.spike_core.mcad_export_contract import MAX_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assembly", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="New .zip or .step output path")
    args = parser.parse_args()
    if args.assembly.stat().st_size > MAX_BYTES:
        parser.error("Assembly exceeds 64 MiB")
    suffix = args.output.suffix.lower()
    if suffix not in {".zip", ".step", ".stp"}:
        parser.error("Output must be .zip, .step or .stp")
    if args.output.exists():
        parser.error("Output already exists; choose a new path")
    result = export_assembly(json.loads(args.assembly.read_text(encoding="utf-8")))
    artifact = result["artifacts"][1 if suffix == ".zip" else 0]
    # Exclusive creation also protects an output created during conversion.
    with args.output.open("xb") as stream:
        stream.write(base64.b64decode(artifact["data"], validate=True))
    print(json.dumps({"output":str(args.output), "sha256":artifact["sha256"], "objects":len(result["manifest"]["objects"]),
                      "verification":result["manifest"]["roundtrip"]}))


if __name__ == "__main__": main()
