"""Generate the portable MCAD session/feedback schema pair."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
string = {"type": "string", "minLength": 1, "maxLength": 512, "pattern": r"\S"}
sha = {"type": "string", "pattern": "^[a-f0-9]{64}$"}


def record(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required, "additionalProperties": False}


def array(items, minimum=0, maximum=130):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


point = array({"type": "number"}, 2, 2)
pose = {"id": string, "name": string, "transform": array({"type": "number"}, 16, 16)}
header = {"session_id": string, "project_id": string, "assembly_id": string,
          "baseline_assembly_sha256": sha, "baseline_designs_sha256": sha}
segment = {"oneOf": [record({"kind": {"const": "line"}, "end_mm": point}),
                      record({"kind": {"const": "arc"}, "end_mm": point, "mid_mm": point})]}
ring = record({"role": {"enum": ["outer", "cutout"]}, "start_mm": point, "segments": array(segment, 1, 100000)})
geometry = {"oneOf": [{"type": "null"}, record({"type": {"const": "step"}, "asset_sha256": sha}),
    record({"type": {"const": "board_outline"}, "rings": array(ring, 1, 256),
            "height_mm": {"type": "number", "exclusiveMinimum": 0}, "z_mm": {"type": "number"}})]}
session = record({"contract": {"const": "spike/mcad-session/v1"}, **header,
    "objects": array(record({**pose, "kind": {"enum": ["board", "part", "group"]},
                              "parent_id": {"oneOf": [string, {"type": "null"}]}, "geometry": geometry}), 1),
    "assets": {"type": "object", "maxProperties": 100, "propertyNames": sha,
               "additionalProperties": record({"type": {"const": "step"}, "data_base64": {"type": "string", "contentEncoding": "base64"}})},
    "diagnostics": array(string, 0, 1000)})
feedback = record({"contract": {"const": "spike/mcad-feedback/v1"}, **header, "objects": array(record(pose), 1),
    "measurements": array(record({"object_a_id": string, "object_b_id": string,
        "distance_mm": {"type": "number", "minimum": 0}, "overlap_volume_mm3": {"type": "number", "minimum": 0}}), 0, 100)})
for name, schema in (("mcad-session-v1", session), ("mcad-feedback-v1", feedback)):
    value = {"$schema": "https://json-schema.org/draft/2020-12/schema",
             "$id": f"https://spike.local/schemas/{name}.schema.json",
             "description": "Millimetres; right-handed Z-up; parent-local row-major proper rigid transforms. Runtime validation additionally enforces identities, graph topology, finite numbers, geometry closure, SHA-256 assets and bounded total input.", **copy.deepcopy(schema)}
    contents = json.dumps(value, indent=2) + "\n"
    for folder in (ROOT / "schemas", ROOT / "integrations/freecad/SPIKEWorkbench/Resources/schemas"):
        (folder / (name + ".schema.json")).write_text(contents, encoding="utf-8")
