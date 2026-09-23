"""Dependency-free collaboration contract; mirrored in the FreeCAD workbench.

Run scripts/sync_freecad_contract.py after edits. Tests enforce byte parity.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re

SESSION = "spike/mcad-session/v1"
FEEDBACK = "spike/mcad-feedback/v1"
MAX_BYTES = 32 * 1024**2
HEADER = {"session_id", "project_id", "assembly_id", "baseline_assembly_sha256", "baseline_designs_sha256"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError("Invalid collaboration record fields.")


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError("Collaboration identifiers and labels require 1–512 characters.")


def number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError("Expected a finite physical number.")


def point(value, length):
    if not isinstance(value, list) or len(value) != length:
        raise ValueError("Invalid coordinate array.")
    for v in value: number(v)


def rigid(value):
    point(value, 16)
    if any(abs(value[i]) > 1e-10 for i in (12, 13, 14)) or abs(value[15] - 1) > 1e-10:
        raise ValueError("Expected a proper rigid transform.")
    rows = [value[i:i+3] for i in (0, 4, 8)]
    for i in range(3):
        for j in range(3):
            if abs(sum(a*b for a, b in zip(rows[i], rows[j])) - int(i == j)) > 1e-8:
                raise ValueError("Scale and shear are not supported.")
    a,b,c,d,e,f,g,h,i = sum(rows, [])
    if abs(a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)-1) > 1e-8:
        raise ValueError("Reflections are not supported.")


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch("[a-f0-9]{64}", value):
        raise ValueError("Invalid SHA-256 identity.")


def validate(value):
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 24 or count > 500000: raise ValueError("Collaboration JSON exceeds nesting/value limits.")
        if isinstance(item, dict): pending.extend((v, depth+1) for v in item.values())
        elif isinstance(item, list): pending.extend((v, depth+1) for v in item)
    if len(json.dumps(value, allow_nan=False).encode()) > MAX_BYTES:
        raise ValueError("Collaboration JSON exceeds 32 MiB.")
    session = isinstance(value, dict) and value.get("contract") == SESSION
    keys(value, HEADER | {"contract", "objects"} | ({"assets", "diagnostics"} if session else {"measurements"}))
    if value["contract"] not in {SESSION, FEEDBACK}: raise ValueError("Unsupported collaboration contract.")
    for k in HEADER:
        _sha(value[k]) if k.endswith("sha256") else text(value[k])
    objects = value["objects"]
    if not isinstance(objects, list) or not 1 <= len(objects) <= 130:
        raise ValueError("Collaboration requires 1–130 occurrences.")
    ids = set()
    for obj in objects:
        keys(obj, {"id", "name", "transform"} | ({"kind", "parent_id", "geometry"} if session else set()))
        text(obj["id"]); text(obj["name"]); rigid(obj["transform"])
        if obj["id"] in ids: raise ValueError("Duplicate occurrence identity.")
        ids.add(obj["id"])
    if session:
        assets = value["assets"]
        if not isinstance(assets, dict) or len(assets) > 100: raise ValueError("Invalid asset table.")
        for sha, asset in assets.items():
            _sha(sha); keys(asset, {"type", "data_base64"})
            if asset["type"] != "step": raise ValueError("Only embedded STEP assets are supported.")
            data = base64.b64decode(asset["data_base64"], validate=True)
            if hashlib.sha256(data).hexdigest() != sha: raise ValueError("STEP asset digest mismatch.")
        parents = {}
        segments = 0
        for obj in objects:
            if obj["kind"] not in {"board", "part", "group"}: raise ValueError("Invalid occurrence kind.")
            parent = obj["parent_id"]
            if parent is not None and parent not in ids: raise ValueError("Unknown occurrence parent.")
            parents[obj["id"]] = parent
            geom = obj["geometry"]
            if geom is None: continue
            if not isinstance(geom, dict): raise ValueError("Invalid geometry.")
            if geom.get("type") == "step":
                keys(geom, {"type", "asset_sha256"})
                if geom["asset_sha256"] not in assets: raise ValueError("Missing STEP asset.")
            elif geom.get("type") == "board_outline":
                keys(geom, {"type", "rings", "height_mm", "z_mm"})
                number(geom["height_mm"], positive=True); number(geom["z_mm"])
                if not isinstance(geom["rings"], list) or not 1 <= len(geom["rings"]) <= 256:
                    raise ValueError("Invalid board outline rings.")
                if sum(r.get("role") == "outer" for r in geom["rings"]) != 1: raise ValueError("One outer board ring is required.")
                for ring in geom["rings"]:
                    keys(ring, {"role", "start_mm", "segments"})
                    if ring["role"] not in {"outer", "cutout"}: raise ValueError("Invalid ring role.")
                    point(ring["start_mm"], 2)
                    if not isinstance(ring["segments"], list) or not ring["segments"]: raise ValueError("Empty outline.")
                    segments += len(ring["segments"])
                    if segments > 100000: raise ValueError("Too many outline segments.")
                    for segment in ring["segments"]:
                        keys(segment, {"kind", "end_mm"}, {"mid_mm"})
                        point(segment["end_mm"], 2)
                        if segment["kind"] == "arc": point(segment.get("mid_mm"), 2)
                        elif segment["kind"] != "line" or "mid_mm" in segment: raise ValueError("Invalid outline segment.")
                    if ring["segments"][-1]["end_mm"] != ring["start_mm"]: raise ValueError("Open board outline.")
            else: raise ValueError("Unsupported collaboration geometry.")
        for ident in parents:
            seen = set()
            while ident is not None:
                if ident in seen: raise ValueError("Cyclic occurrence hierarchy.")
                seen.add(ident); ident = parents[ident]
        if not isinstance(value["diagnostics"], list) or len(value["diagnostics"]) > 1000: raise ValueError("Invalid diagnostics.")
        for item in value["diagnostics"]: text(item)
    else:
        rows = value["measurements"]
        if not isinstance(rows, list) or len(rows) > 100: raise ValueError("Too many measurements.")
        for row in rows:
            keys(row, {"object_a_id", "object_b_id", "distance_mm", "overlap_volume_mm3"})
            if row["object_a_id"] not in ids or row["object_b_id"] not in ids or row["object_a_id"] == row["object_b_id"]:
                raise ValueError("Measurement requires two known distinct occurrences.")
            for k in ("distance_mm", "overlap_volume_mm3"):
                number(row[k])
                if row[k] < 0: raise ValueError("Negative clearance measurement.")
    return value


def loads(data):
    if len(data.encode("utf-8")) > MAX_BYTES: raise ValueError("Collaboration JSON exceeds 32 MiB.")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError("Duplicate JSON key.")
            result[key] = value
        return result
    try:
        return validate(json.loads(data, object_pairs_hook=pairs))
    except (RecursionError, TypeError, KeyError, OverflowError) as exc:
        raise ValueError("Malformed collaboration JSON.") from exc
