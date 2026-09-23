import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from python.spike_core.harness import analyze_harness, compile_harness, compile_multiboard_harness, export_harness, import_harness


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    contribution = request["contribution_id"]
    context = request["context"]
    parameters = context.get("parameters", {})
    if contribution == "harness-import":
        data = import_harness(parameters["path"], column_map=parameters.get("column_map"), delimiter=parameters.get("delimiter"))
    elif contribution == "harness-validate": data = analyze_harness(context["harness"])
    elif contribution == "harness-compile": data = compile_harness(context["harness"])
    elif contribution == "harness-bind": data = compile_multiboard_harness(context["harness"], parameters["multiboard_request"])
    elif contribution == "harness-export": data = {"text": export_harness(context["harness"]), "filename": "harness.spike-harness.json"}
    elif contribution == "harness-schema": data = json.loads((Path(__file__).resolve().parents[2] / "schemas/harness-v1.schema.json").read_text(encoding="utf-8"))
    else: raise ValueError("Unknown harness contribution.")
    Path(args.result).write_text(json.dumps({"contract": "spike/extension-result/v1", "status": "completed", "title": "Harness Engineering", "data": data}, allow_nan=False), encoding="utf-8")


if __name__ == "__main__": main()
