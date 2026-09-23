"""Validated, CAD-neutral assembly input for named-solid mechanical exchange."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
from pathlib import Path

CONTRACT = "spike/mcad-assembly/v1"
IDENTITY = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]
MAX_BYTES = 64 * 1024**2
MAX_OBJECTS = 10000


def finite(value, label, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite.")
    if abs(value) > 1e7 or (positive and value <= 0):
        raise ValueError(f"{label} is outside the supported mechanical dimensions.")
    return value


def point(value, size, label):
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} requires {size} coordinates.")
    return [finite(v, label) for v in value]


def rigid_transform(value):
    point(value, 16, "transform")
    if any(abs(a-b) > 1e-9 for a, b in zip(value[12:], [0, 0, 0, 1])):
        raise ValueError("Transform must be row-major affine, with translation in mm.")
    columns = [[value[r*4+c] for r in range(3)] for c in range(3)]
    for a in range(3):
        for b in range(3):
            if abs(sum(x*y for x,y in zip(columns[a], columns[b])) - int(a == b)) > 1e-8:
                raise ValueError("Transforms must be rigid: scale and shear are not supported.")
    a, b, c = columns
    det = a[0]*(b[1]*c[2]-b[2]*c[1])-b[0]*(a[1]*c[2]-a[2]*c[1])+c[0]*(a[1]*b[2]-a[2]*b[1])
    if abs(det-1) > 1e-8:
        raise ValueError("Transforms must preserve handedness; model mirroring must be explicit geometry.")
    return value


def validate_assembly(raw):
    from jsonschema import Draft202012Validator
    if not isinstance(raw, dict):
        raise ValueError("MCAD assembly must be an object.")
    encoded = json.dumps(raw, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_BYTES:
        raise ValueError("MCAD assembly exceeds 64 MiB.")
    schema = json.loads((Path(__file__).resolve().parents[2] / "schemas/mcad-assembly-v1.schema.json").read_text(encoding="utf-8"))
    error = next(Draft202012Validator(schema).iter_errors(raw), None)
    if error:
        raise ValueError(f"Invalid MCAD assembly at {list(error.path)}: {error.message}")
    data = copy.deepcopy(raw)
    objects = {o["id"]: o for o in data["objects"]}
    materials = {m["id"]: m for m in data.get("materials", [])}
    if len(objects) != len(data["objects"]) or len(materials) != len(data.get("materials", [])):
        raise ValueError("MCAD object and material IDs must be unique.")
    total_points = 0
    for obj in objects.values():
        rigid_transform(obj.setdefault("transform", IDENTITY.copy()))
        if obj.get("material_id") and obj["material_id"] not in materials:
            raise ValueError(f"Unknown material on {obj['id']}.")
        visited = {obj["id"]}
        parent = obj.get("parent_id", "")
        while parent:
            if parent in visited or parent not in objects or objects[parent]["kind"] != "assembly":
                raise ValueError("MCAD parents must be existing assemblies without cycles.")
            visited.add(parent)
            if len(visited) > 64:
                raise ValueError("MCAD hierarchy exceeds 64 levels.")
            parent = objects[parent].get("parent_id", "")
        if obj["kind"] == "assembly":
            if "geometry" in obj:
                raise ValueError("Assembly containers cannot also own geometry.")
            continue
        geom = obj.get("geometry", {})
        kind = geom.get("type")
        if kind == "box":
            for v in point(geom["size_mm"], 3, "box size"):
                finite(v, "box size", True)
        elif kind == "cylinder":
            finite(geom["radius_mm"], "radius", True)
            finite(geom["height_mm"], "height", True)
        elif kind == "extrusion":
            finite(geom["height_mm"], "height", True)
            finite(geom.get("z_mm", 0), "z")
            if sum(r["role"] == "outer" for r in geom["rings"]) != 1:
                raise ValueError("Each extrusion requires one outer ring; islands are separate objects.")
            for ring in geom["rings"]:
                start = point(ring["start_mm"], 2, "ring start")
                current = start
                for segment in ring["segments"]:
                    end = point(segment["end_mm"], 2, "ring endpoint")
                    if math.dist(current, end) <= 1e-10:
                        raise ValueError("Ring segments cannot be zero-length; split full circles into arcs.")
                    if segment["kind"] == "arc":
                        point(segment["mid_mm"], 2, "arc midpoint")
                    current = end
                    total_points += 1
                if math.dist(current, start) > 1e-8:
                    raise ValueError("Extrusion rings must be closed.")
        elif kind == "route":
            finite(geom["radius_mm"], "route radius", True)
            pts = [point(p, 3, "route point") for p in geom["points_mm"]]
            if any(math.dist(a, b) <= 1e-9 for a,b in zip(pts, pts[1:])):
                raise ValueError("Routes cannot contain zero-length segments.")
            total_points += len(pts)
        elif kind == "step":
            try:
                payload = base64.b64decode(geom["data_base64"], validate=True)
            except Exception as exc:
                raise ValueError("Invalid STEP asset base64.") from exc
            from .mcad_importer import validate_step_mcad_artifact
            validate_step_mcad_artifact(payload)
            if hashlib.sha256(payload).hexdigest() != geom["sha256"]:
                raise ValueError("STEP asset digest mismatch.")
        else:
            raise ValueError(f"Object {obj['id']} requires supported solid geometry.")
    if total_points > 200000:
        raise ValueError("MCAD assembly exceeds 200000 curve segments/route points.")
    if not any(o["kind"] != "assembly" for o in objects.values()):
        raise ValueError("MCAD assembly contains no geometric objects.")
    used_groups = {o.get("parent_id") for o in objects.values() if o.get("parent_id")}
    if any(o["kind"] == "assembly" and o["id"] not in used_groups for o in objects.values()):
        raise ValueError("Empty assembly containers have no STEP representation; remove them or supply geometry.")
    return data
