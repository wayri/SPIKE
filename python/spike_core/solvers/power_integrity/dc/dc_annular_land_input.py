# SPDX-License-Identifier: Apache-2.0
"""Strict full-azimuth annular face support; patch labels never weld traces."""
from __future__ import annotations
import hashlib
import json
import math

import numpy as np

REQUEST = "spike/dc-annular-land-request/v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, low=-1e6, high=1e6):
    require(type(value) in (int, float) and low <= value <= high and math.isfinite(value),
            "Annular input must be a finite real in the supported range")
    return float(value)


def prepare(raw):
    require(type(raw) is dict and set(raw) == {"contract", "radial_planes_mm", "axial_planes_mm",
            "conductivity_s_m", "contacts"}, "Annular land requires exact declared fields")
    require(raw["contract"] == REQUEST, "Unsupported annular land contract")
    planes = []
    for key in ("radial_planes_mm", "axial_planes_mm"):
        values = raw[key]
        require(type(values) is list and 2 <= len(values) <= 65, "Annular axes need 2..65 explicit planes")
        axis = np.array([number(v) for v in values])
        require(np.all(np.diff(axis) >= 1e-9), "Annular planes must increase by at least 1e-9 mm")
        planes.append(axis)
    rmm, zmm = planes
    require(rmm[0] >= 1e-9 and np.all(np.diff(rmm) <= rmm[:-1]),
            "Axis singularity is unsupported; each radial cell ratio must be <=2")
    nr, nz = len(rmm)-1, len(zmm)-1
    require(nr*nz <= 512, "Annular land exceeds 512 cells")
    sigma = number(raw["conductivity_s_m"], 1e-6, 1e12)
    # Preserve differences before SI conversion. A large global z origin is
    # immaterial; physical radius remains explicit in cylindrical areas.
    dr, dz, radius = np.diff(rmm)*1e-3, np.diff(zmm)*1e-3, rmm*1e-3
    require(np.max(dr)/np.min(dz) <= 1e4 and np.max(dz)/np.min(dr) <= 1e4,
            "Annular cell aspect budget exceeded")
    annulus = math.pi*dr*(2*radius[:-1]+dr)
    offset = (nr+1)*nz
    face_count = offset+nr*(nz+1)
    cells, faces = [], []
    for i in range(nr):
        for j in range(nz):
            cells.append((i, j))
            faces.append([i*nz+j, (i+1)*nz+j, offset+i*(nz+1)+j, offset+i*(nz+1)+j+1])
    contacts = raw["contacts"]
    require(type(contacts) is list and 2 <= len(contacts) <= 8, "Supply 2..8 explicit annular contacts")
    patches, used, names = [], set(), set()
    for contact in contacts:
        require(type(contact) is dict and set(contact) == {"id", "attachment_id", "face", "interval_mm", "current_a"},
                "Annular contact requires exact declared fields")
        for key in ("id", "attachment_id"):
            require(type(contact[key]) is str and bool(contact[key].strip()) and len(contact[key]) <= 80,
                    "Annular contact identities must be bounded nonempty strings")
        require(contact["id"] not in names, "Duplicate annular contact ID")
        names.add(contact["id"])
        side = contact["face"]
        require(side in ("r_min", "r_max", "z_min", "z_max"), "Unsupported annular contact face")
        interval = contact["interval_mm"]
        require(type(interval) is list and len(interval) == 2, "Supply one full-azimuth face interval")
        lo, hi = (number(v) for v in interval)
        original = raw["axial_planes_mm"] if side.startswith("r") else raw["radial_planes_mm"]
        require(lo < hi and lo in original and hi in original, "Annular patch must match explicit planes exactly")
        selected, areas = [], []
        for k in range(original.index(lo), original.index(hi)):
            if side.startswith("r"):
                i = 0 if side == "r_min" else nr
                fid, area = i*nz+k, 2*math.pi*radius[i]*dz[k]
            else:
                j = 0 if side == "z_min" else nz
                fid, area = offset+k*(nz+1)+j, annulus[k]
            require(fid not in used, "Annular contact patches overlap")
            used.add(fid); selected.append(fid); areas.append(float(area))
        current = number(contact["current_a"], -1e9, 1e9)
        patches.append({**contact, "face_ids": selected, "face_areas_m2": areas,
                        "area_m2": math.fsum(areas), "current_a": current})
    scale = math.fsum(abs(p["current_a"]) for p in patches)
    balance = math.fsum(p["current_a"] for p in patches)
    require(abs(balance) <= 64*np.finfo(float).eps*scale, "Annular prescribed currents are unbalanced")
    prescribed = np.zeros(face_count)
    for p in patches:
        values = -p["current_a"]*(np.array(p["face_areas_m2"])/p["area_m2"])
        require(np.isfinite(values).all() and (p["current_a"] == 0 or np.all(values != 0)),
                "Annular contact current overflowed or underflowed")
        prescribed[p["face_ids"]] = values
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    require(len(encoded) <= 1024*1024, "Annular request exceeds 1 MiB")
    return {"rmm": rmm, "zmm": zmm, "radius": radius, "dr": dr, "dz": dz, "annulus": annulus,
            "cells": cells, "faces": np.array(faces), "face_count": face_count, "sigma": sigma,
            "patches": patches, "prescribed": prescribed, "current_scale": scale,
            "input_current_balance_a": balance, "digest": hashlib.sha256(encoded).hexdigest()}
