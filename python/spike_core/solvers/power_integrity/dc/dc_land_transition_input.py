# SPDX-License-Identifier: Apache-2.0
"""Explicit finite rectangle-to-face mapping; semantic labels never weld fluxes."""
from __future__ import annotations
import hashlib
import itertools
import json
import math

import numpy as np

REQUEST = "spike/dc-land-transition-request/v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), "Expected finite real SI input")
    return float(value)


def prepare(raw):
    require(type(raw) is dict and set(raw) == {"contract", "axes_mm", "conductivity_s_m", "contacts"},
            "Land transition requires exact declared fields")
    require(raw["contract"] == REQUEST, "Unsupported land transition contract")
    require(type(raw["axes_mm"]) is list and len(raw["axes_mm"]) == 3, "Supply three Cartesian axes")
    axes, origins = [], []
    for axis in raw["axes_mm"]:
        require(type(axis) is list and 2 <= len(axis) <= 25, "Each axis needs 2..25 explicit planes")
        values = np.array([number(v) for v in axis])
        require(np.max(np.abs(values)) <= 1e6 and np.all(np.diff(values) >= 1e-9),
                "Axes must be increasing, representable and within geometry budget")
        origins.append(float(values[0]))
        axes.append((values-values[0])*1e-3)
    shape = tuple(len(a)-1 for a in axes)
    require(math.prod(shape) <= 4096, "Land transition cell budget exceeded")
    sigma = number(raw["conductivity_s_m"])
    require(1e-6 <= sigma <= 1e12, "Unsupported scalar conductivity")
    nx, ny, nz = shape
    ox = (nx+1)*ny*nz
    oy = ox+nx*(ny+1)*nz
    count = oy+nx*ny*(nz+1)
    require(count <= 16000, "Land transition face budget exceeded")

    def face(axis, i, j, k):
        return ((i*ny+j)*nz+k if axis == 0 else
                ox+(i*(ny+1)+j)*nz+k if axis == 1 else oy+(i*ny+j)*(nz+1)+k)

    cells, local_faces, lengths = [], [], []
    for i, j, k in itertools.product(range(nx), range(ny), range(nz)):
        cells.append((i, j, k))
        local_faces.append([face(0, i, j, k), face(0, i+1, j, k), face(1, i, j, k),
                            face(1, i, j+1, k), face(2, i, j, k), face(2, i, j, k+1)])
        lengths.append([axes[a][n+1]-axes[a][n] for a, n in enumerate((i, j, k))])
    lengths = np.asarray(lengths)
    require(np.max(lengths.max(axis=1)/lengths.min(axis=1)) <= 1e4, "Land cell aspect budget exceeded")
    counts = np.bincount(np.asarray(local_faces).ravel(), minlength=count)
    boundary = counts == 1
    require(type(raw["contacts"]) is list and 2 <= len(raw["contacts"]) <= 64,
            "Supply 2..64 explicit finite contacts")
    patches, used, ids = [], set(), set()
    for item in raw["contacts"]:
        require(type(item) is dict and set(item) == {"id", "attachment_id", "face", "rectangle_mm", "current_a"},
                "Contact requires exact declared fields")
        for key in ("id", "attachment_id"):
            require(type(item[key]) is str and 0 < len(item[key]) <= 80, "Contact identities must be bounded strings")
        require(item["id"] not in ids, "Duplicate contact ID")
        ids.add(item["id"])
        require(item["face"] in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max"), "Unsupported contact face")
        axis = "xyz".index(item["face"][0]); uv = [a for a in range(3) if a != axis]
        rectangle = item["rectangle_mm"]
        require(type(rectangle) is list and len(rectangle) == 2, "Supply two patch intervals")
        limits = []
        for pair, a in zip(rectangle, uv):
            require(type(pair) is list and len(pair) == 2, "Supply finite patch interval")
            lower, upper = [number(v) for v in pair]
            # Compare original mm planes, with no mesh-sized snapping.
            original = raw["axes_mm"][a]
            require(lower < upper and lower in original and upper in original,
                    "Contact edges must match explicit grid planes")
            limits.append((original.index(lower), original.index(upper)))
        side = 0 if item["face"].endswith("min") else shape[axis]
        selected, areas = [], []
        for u in range(*limits[0]):
            for v in range(*limits[1]):
                index = [0, 0, 0]; index[axis] = side; index[uv[0]] = u; index[uv[1]] = v
                fid = face(axis, *index)
                require(boundary[fid] and fid not in used, "Overlapping or non-exterior contact support")
                used.add(fid); selected.append(fid)
                areas.append((axes[uv[0]][u+1]-axes[uv[0]][u])*(axes[uv[1]][v+1]-axes[uv[1]][v]))
        current = number(item["current_a"])
        require(abs(current) <= 1e9, "Contact current budget exceeded")
        patches.append({**item, "faces": selected, "face_areas_m2": areas, "area_m2": math.fsum(areas), "current_a": current})
    scale = math.fsum(abs(p["current_a"]) for p in patches)
    balance = math.fsum(p["current_a"] for p in patches)
    require(abs(balance) <= 64*np.finfo(float).eps*scale, "Unbalanced prescribed contact currents")
    prescribed = np.zeros(count)
    for patch in patches:
        weights = np.array(patch["face_areas_m2"])/patch["area_m2"]
        values = -patch["current_a"]*weights
        require(np.isfinite(values).all() and (patch["current_a"] == 0 or np.all(values != 0)),
                "Finite contact face current underflowed or overflowed")
        prescribed[patch["faces"]] = values
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    require(len(encoded) <= 1024*1024, "Land transition input exceeds 1 MiB")
    return {"axes": axes, "origins_mm": origins, "shape": shape, "cells": cells, "faces": np.asarray(local_faces),
            "lengths": lengths, "boundary": boundary, "face_count": count, "patches": patches,
            "sigma": sigma, "prescribed": prescribed, "current_scale": scale,
            "input_current_balance_a": balance, "digest": hashlib.sha256(encoded).hexdigest()}
