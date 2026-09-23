# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Exact orthogonal-box assembly lowering; no inferred PCB or port geometry.

The vacuum between separate board dielectric volumes is not replaced by a
bounding substrate. Oblique placements require a different, qualified mesher.
"""
import hashlib
import itertools
import json
import math
import re


def _record(raw, keys, label):
    if not isinstance(raw, dict) or set(raw) != set(keys):
        raise ValueError(f"Invalid {label} fields")


def _number(value, lower, upper):
    if type(value) not in (int,float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError("Invalid finite bounded numeric value")
    return float(value)


def _vector(value):
    if not isinstance(value,list) or len(value)!=3:
        raise ValueError("Expected three coordinates in mm")
    return [_number(v,-1e6,1e6) for v in value]


def _identity(value):
    if not isinstance(value,str) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}",value) is None:
        raise ValueError("Expected literal bounded identity")
    return value


def _overlap(a,b):
    return all(min(a["stop_mm"][i],b["stop_mm"][i]) > max(a["start_mm"][i],b["start_mm"][i]) for i in range(3))


def compile_assembly_geometry(raw):
    """Admit <=16 boards/256 boxes, returning exact world-axis boxes in mm."""
    _record(raw,{"contract","boards","air_margin_mm"},"assembly")
    if raw["contract"]!="spike/openems-box-assembly/v1":
        raise ValueError("Unsupported assembly contract")
    encoded=json.dumps(raw,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    if len(encoded)>8*1024**2:raise ValueError("Assembly control exceeds 8 MiB")
    margin=_number(raw["air_margin_mm"],1e-6,1e5)
    boards=raw["boards"]
    if not isinstance(boards,list) or not 1<=len(boards)<=16:
        raise ValueError("Expected 1..16 boards")
    world=[];owners=set()
    for board in boards:
        _record(board,{"id","world_from_local_mm","boxes"},"board")
        owner=_identity(board["id"])
        if owner in owners:raise ValueError("Duplicate board identity")
        owners.add(owner)
        matrix=board["world_from_local_mm"]
        if not isinstance(matrix,list) or len(matrix)!=16:
            raise ValueError("Expected sixteen row-major transform values")
        for v in matrix:_number(v,-1e6,1e6)
        rotation=[matrix[r*4+c] for r in range(3) for c in range(3)]
        if any(v not in (-1.,0.,1.) for v in rotation):
            raise ValueError("Only exact orthogonal axis-permutation placement is supported")
        if matrix[12:] != [0,0,0,1] or any(
            sum(abs(matrix[r*4+c]) for c in range(3)) != 1 for r in range(3)
        ) or any(sum(abs(matrix[r*4+c]) for r in range(3)) != 1 for c in range(3)):
            raise ValueError("Expected proper rigid axis-permutation transform")
        determinant=(matrix[0]*(matrix[5]*matrix[10]-matrix[6]*matrix[9])
                     -matrix[1]*(matrix[4]*matrix[10]-matrix[6]*matrix[8])
                     +matrix[2]*(matrix[4]*matrix[9]-matrix[5]*matrix[8]))
        if determinant != 1:
            raise ValueError("Reflection is not a proper rigid placement")
        boxes=board["boxes"]
        if not isinstance(boxes,list) or not boxes or len(boxes)+len(world)>256:
            raise ValueError("Assembly requires boxes and at most 256 primitives")
        ids=set();has_dielectric=False
        for box in boxes:
            _record(box,{"id","kind","start_mm","stop_mm","epsilon_r","conductivity_s_m"},"box")
            identity=_identity(box["id"])
            if identity in ids:raise ValueError("Duplicate board primitive identity")
            ids.add(identity)
            if box["kind"] not in ("dielectric","conductor"):
                raise ValueError("Unsupported primitive material kind")
            start=_vector(box["start_mm"]);stop=_vector(box["stop_mm"])
            if any(b-a<1e-6 for a,b in zip(start,stop)):
                raise ValueError("Box must have positive resolved thickness on every axis")
            epsilon=_number(box["epsilon_r"],1.,1e4)
            sigma=_number(box["conductivity_s_m"],0.,1e9)
            if box["kind"]=="conductor" and sigma<=0:
                raise ValueError("Conductors require positive finite conductivity")
            has_dielectric |= box["kind"]=="dielectric"
            corners=[[sum(matrix[4*r+c]*p[c] for c in range(3))+matrix[4*r+3] for r in range(3)]
                     for p in itertools.product(*zip(start,stop))]
            low=[min(p[i] for p in corners) for i in range(3)]
            high=[max(p[i] for p in corners) for i in range(3)]
            world.append({"board_id":owner,"id":identity,"kind":box["kind"],
                "start_mm":low,"stop_mm":high,"epsilon_r":epsilon,"conductivity_s_m":sigma})
        if not has_dielectric:raise ValueError("Each board requires explicit dielectric volume")
    for i,a in enumerate(world):
        for b in world[i+1:]:
            if _overlap(a,b) and (a["board_id"]!=b["board_id"] or a["kind"]==b["kind"]):
                raise ValueError("Overlapping boards or ambiguous same-priority material volumes")
    domain={"start_mm":[min(b["start_mm"][i] for b in world)-margin for i in range(3)],
            "stop_mm":[max(b["stop_mm"][i] for b in world)+margin for i in range(3)]}
    pins=[sorted({domain["start_mm"][i],domain["stop_mm"][i]} |
                 {b[k][i] for b in world for k in ("start_mm","stop_mm")}) for i in range(3)]
    if math.prod(len(axis)-1 for axis in pins)>2_000_000:
        raise ValueError("Mandatory mesh interface grid exceeds cell budget")
    return {"contract":"spike/openems-world-box-geometry/v1","input_sha256":hashlib.sha256(encoded).hexdigest(),
        "units":"mm","background":{"epsilon_r":1.,"conductivity_s_m":0.},"boxes":world,
        "domain":domain,"mandatory_mesh_lines_mm":pins,"production_qualified":False,
        "limitations":["exact orthogonal boxes only; no curved, cutout, via or inferred connector lowering",
                       "mesh lines are interface constraints, not a wavelength/CFL qualified mesh",
                       "no port construction, solver execution or independent field validation"]}


def emit_csxcad_geometry(csx,raw):
    """Populate a NEW vacuum CSXCAD structure; admission completes before writes.

    Caller owns structure lifetime, grid unit (1e-3 m), ports and FDTD setup.
    Official API: https://docs.openems.de/python/CSXCAD/CSXCAD.html
    """
    compiled=compile_assembly_geometry(raw)
    for index,box in enumerate(compiled["boxes"]):
        material=csx.AddMaterial(f"spike_assembly_{index}",epsilon=box["epsilon_r"],kappa=box["conductivity_s_m"])
        material.AddBox(box["start_mm"],box["stop_mm"],priority=10 if box["kind"]=="conductor" else 0)
    return compiled
