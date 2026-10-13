"""Executable release probes for bundled extension assets and Python hosting."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile


def verify_extension_runtime(executable, request):
    def invoke(extension, contribution, context):
        response = request(executable, "invoke_extension", {
            "extension_id": extension, "contribution_id": contribution, "context": context,
        })["result"]
        if response.get("status") != "completed":
            raise RuntimeError(f"Bundled extension did not complete: {response}")
        return response["data"]

    # Schema reads prove that non-Python distribution assets are available.
    mcad_schema = invoke("spike.mcad", "mcad-schema", {})
    if mcad_schema.get("properties", {}).get("contract", {}).get("const") != "spike/mcad-assembly/v1":
        raise RuntimeError("Bundled MCAD schema is missing or incompatible.")
    mcad = invoke("spike.mcad", "mcad-plan", {"parameters": {"assembly": {
        "contract": "spike/mcad-assembly/v1", "id": "probe", "name": "MCAD release probe", "units": "mm",
        "objects": [{"id": "cell", "name": "Cell", "kind": "cell", "geometry": {"type": "box", "size_mm": [1,2,3]}}]
    }}})
    if mcad.get("objects", [{}])[0].get("id") != "cell":
        raise RuntimeError("Bundled MCAD assembly planning failed.")
    schema = invoke("spike.harness", "harness-schema", {})
    if schema.get("properties", {}).get("contract", {}).get("const") != "spike/harness/v1":
        raise RuntimeError("Bundled harness schema is missing or incompatible.")
    document = {"contract": "spike/harness/v1", "id": "probe", "name": "Release probe",
                "connectors": [{"id": "J1", "pins": [{"id": "01"}]},
                               {"id": "J2", "pins": [{"id": "02"}]}],
                "wires": [{"id": "W1", "from": {"connector": "J1", "pin": "01"},
                           "to": {"connector": "J2", "pin": "02"},
                           "electrical": {"resistance_ohm": 0.1}}]}
    circuit = invoke("spike.harness", "harness-compile", {"harness": document})
    if circuit.get("status") != "compiled" or len(circuit.get("elements", [])) != 1:
        raise RuntimeError(f"Bundled harness circuit compilation failed: {circuit}")
    with tempfile.TemporaryDirectory(prefix="spike-odb-release-") as directory:
        root = Path(directory)
        files = {
            "matrix/matrix": "STEP {\nCOL=1\nNAME=board\n}\nLAYER {\nROW=1\nNAME=top\nTYPE=SIGNAL\nCONTEXT=BOARD\nPOLARITY=POSITIVE\n}\n",
            "misc/info": "UNITS=MM\n",
            "steps/board/profile": "UNITS=MM\nOB 0 0 I\nOS 5 0\nOS 5 5\nOS 0 5\nOS 0 0\nOE\n",
            "steps/board/eda/data": "UNITS=MM\nLYR top\nNET VCC\nSNT TRC\nFID C 0 0\n",
            "steps/board/layers/top/features": "UNITS=MM\n$0 r250\nL 1 1 4 1 0 P 0\n",
            "steps/board/spike/board.json": json.dumps({"contract": "spike/board-enrichment/v1",
                "stackup": [{"name": "top", "type": "copper", "thickness_mm": 0.035}]}),
        }
        for relative, text in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        design = invoke("spike.odb-import", "odb-design", {"source": {"path": str(root)}})["design"]
        if design.get("source_format") != "odb++" or len(design.get("tracks", [])) != 1:
            raise RuntimeError("Bundled ODB++ extension did not normalize the release probe.")
        if design["tracks"][0].get("width") != 0.25:
            raise RuntimeError("Bundled ODB++ extension changed symbol units.")
        imported = request(executable, "import_design_v2", {
            "path": str(root), "format_hint": "odb-design", "include_snapshot": True,
        })["result"]
        if imported.get("snapshot", {}).get("contract") != "spike/design-snapshot/v1" or len(imported["design"]["tracks"]) != 1:
            raise RuntimeError("Bundled ODB++ importer registry did not produce the desktop snapshot.")
    return {"status": "passed", "harness_elements": len(circuit["elements"]), "mcad_schema_and_plan": "passed",
            "odb_tracks": len(design["tracks"]), "schema_assets": "passed", "desktop_snapshot": "passed"}
