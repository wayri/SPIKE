"""Distribution entrypoint; vendor parser stays out of the desktop process."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from python.spike_core.importers import ImportPolicy
from python.spike_core.odb_importer import import_odb_design


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    if request["contribution_id"] == "odb-enrichment-schema":
        data = json.loads((Path(__file__).resolve().parents[2] / "schemas/board-enrichment-v1.schema.json").read_text(encoding="utf-8"))
    else:
        source = request["context"]["source"]
        options = source.get("options", {})
        if set(options) - {"step"}: raise ValueError("Unknown ODB++ import options.")
        design = import_odb_design(source["path"], step=options.get("step", ""), policy=ImportPolicy(**source.get("policy", {})))
        data = {"design": design.to_dict()}
    Path(args.result).write_text(json.dumps({"contract": "spike/extension-result/v1", "status": "completed", "title": "ODB++ import", "data": data}, allow_nan=False), encoding="utf-8")


if __name__ == "__main__": main()
