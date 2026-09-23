"""Bundled mechanical exchange extension process entrypoint."""
import argparse
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from python.spike_core.mcad_export import export_assembly
from python.spike_core.mcad_export_design import assembly_from_context


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    action = request["contribution_id"]
    if action == "mcad-schema":
        data = json.loads((Path(__file__).resolve().parents[2] / "schemas/mcad-assembly-v1.schema.json").read_text(encoding="utf-8"))
    elif action in {"mcad-plan", "mcad-export"}:
        context = copy.deepcopy(request["context"])
        if action == "mcad-plan":
            context.setdefault("parameters", {})["allow_partial"] = True
        assembly = assembly_from_context(context)
        data = assembly if action == "mcad-plan" else export_assembly(assembly)
    else:
        raise ValueError("Unknown MCAD contribution.")
    Path(args.result).write_text(json.dumps({"contract": "spike/extension-result/v1", "status": "completed",
        "title": "MCAD Collaboration", "data": data}, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
