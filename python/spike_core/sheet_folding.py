# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded analytical preview geometry for rectangular sheet and flex folding."""
from __future__ import annotations

import json
import math
from copy import deepcopy

CONTRACT = "spike/sheet-folding/v1"
PREVIEW_CONTRACT = "spike/sheet-folding-preview/v1"
KINDS = {"sheet", "sheet_metal", "flex_pcb", "rigid_flex_pcb"}
MAX_BENDS = 64
MAX_SEGMENTS = 128
MAX_FLEX_REGIONS = 256
MAX_TEXT_BYTES = 2_000_000


def _number(value, label, minimum=None, maximum=None):
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number.")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} must be at most {maximum}.")
    return value


def _exact_dict(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f"{label} has missing or unknown fields.")


def _identifier(value, label):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{label} must be a non-empty string of at most 128 characters.")
    return value


def validate_sheet(raw: dict) -> dict:
    """Validate and normalize the deliberately narrow v1 sheet definition."""
    _exact_dict(raw, ("contract", "id", "kind", "sheet", "bends", "flex_regions"), "sheet definition")
    if raw["contract"] != CONTRACT:
        raise ValueError("Unsupported sheet-folding contract.")
    identifier = _identifier(raw["id"], "id")
    kind = raw["kind"]
    if kind not in KINDS:
        raise ValueError("kind must be sheet, sheet_metal, flex_pcb, or rigid_flex_pcb.")
    sheet = raw["sheet"]
    _exact_dict(sheet, ("length_mm", "width_mm", "thickness_mm", "material"), "sheet")
    length = _number(sheet["length_mm"], "sheet.length_mm", 1e-9, 1e7)
    width = _number(sheet["width_mm"], "sheet.width_mm", 1e-9, 1e7)
    thickness = _number(sheet["thickness_mm"], "sheet.thickness_mm", 1e-9, 1e5)
    try:
        material = deepcopy(sheet["material"])
        encoded_material = json.dumps(material, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("sheet.material must be null or JSON data.") from exc
    if len(encoded_material.encode("utf-8")) > 100_000:
        raise ValueError("sheet.material exceeds 100000 encoded bytes.")
    snapshot_fields = {"schema_version", "material_id", "revision", "digest", "record"}
    if isinstance(material, dict) and set(material) == snapshot_fields:
        from .material_library import MaterialError, validate_snapshot
        try:
            material = validate_snapshot(material)
        except MaterialError as exc:
            raise ValueError(f"sheet.material recognized snapshot is invalid: {exc}") from exc

    regions_raw = raw["flex_regions"]
    if not isinstance(regions_raw, list) or len(regions_raw) > MAX_FLEX_REGIONS:
        raise ValueError(f"flex_regions must be a list with at most {MAX_FLEX_REGIONS} entries.")
    regions = []
    region_ids = set()
    for index, region in enumerate(regions_raw):
        _exact_dict(region, ("id", "start_x_mm", "end_x_mm"), f"flex_regions[{index}]")
        rid = _identifier(region["id"], f"flex_regions[{index}].id")
        if rid in region_ids:
            raise ValueError("flex region ids must be unique.")
        start = _number(region["start_x_mm"], f"flex_regions[{index}].start_x_mm", 0, length)
        end = _number(region["end_x_mm"], f"flex_regions[{index}].end_x_mm", 0, length)
        if end <= start:
            raise ValueError("Each flex region must have positive length.")
        regions.append({"id": rid, "start_x_mm": start, "end_x_mm": end})
        region_ids.add(rid)
    regions.sort(key=lambda item: item["start_x_mm"])
    if any(a["end_x_mm"] > b["start_x_mm"] for a, b in zip(regions, regions[1:])):
        raise ValueError("Flex regions must not overlap.")
    if kind in {"sheet", "sheet_metal"} and regions:
        raise ValueError("General sheets and sheet_metal do not accept flex_regions.")
    if kind not in {"sheet", "sheet_metal"} and not regions:
        raise ValueError("Flex and rigid-flex sheets require at least one flex region.")

    bends_raw = raw["bends"]
    if not isinstance(bends_raw, list) or len(bends_raw) > MAX_BENDS:
        raise ValueError(f"bends must be a list with at most {MAX_BENDS} entries.")
    bends = []
    bend_ids = set()
    for index, bend in enumerate(bends_raw):
        fields = ("id", "start_x_mm", "angle_deg", "inside_radius_mm", "k_factor", "fixed_side", "segments")
        _exact_dict(bend, fields, f"bends[{index}]")
        bid = _identifier(bend["id"], f"bends[{index}].id")
        if bid in bend_ids:
            raise ValueError("Bend ids must be unique.")
        start = _number(bend["start_x_mm"], f"bends[{index}].start_x_mm", 0, length)
        angle = _number(bend["angle_deg"], f"bends[{index}].angle_deg", -180, 180)
        if angle == 0:
            raise ValueError("Bend angle_deg must be nonzero; use fraction=0 for a flat preview.")
        radius = _number(bend["inside_radius_mm"], f"bends[{index}].inside_radius_mm", 0, 1e6)
        if radius <= 0:
            raise ValueError("Bend inside_radius_mm must be positive.")
        k_factor = _number(bend["k_factor"], f"bends[{index}].k_factor", 0, 1)
        if bend["fixed_side"] != "negative_x":
            raise ValueError("v1 supports only fixed_side='negative_x'.")
        if type(bend["segments"]) is not int or not 1 <= bend["segments"] <= MAX_SEGMENTS:
            raise ValueError(f"bend segments must be an integer from 1 through {MAX_SEGMENTS}.")
        allowance = abs(math.radians(angle)) * (radius + k_factor * thickness)
        end = start + allowance
        if end > length + 1e-12:
            raise ValueError(f"Bend {bid} extends beyond the sheet length.")
        if kind not in {"sheet", "sheet_metal"} and not any(start >= r["start_x_mm"] - 1e-12 and end <= r["end_x_mm"] + 1e-12 for r in regions):
            raise ValueError(f"Bend {bid} is not wholly confined to one flex region.")
        bends.append({"id": bid, "start_x_mm": start, "angle_deg": angle,
                      "inside_radius_mm": radius, "k_factor": k_factor,
                      "fixed_side": "negative_x", "segments": bend["segments"]})
        bend_ids.add(bid)
    if any(bends[i]["start_x_mm"] > bends[i + 1]["start_x_mm"] for i in range(len(bends) - 1)):
        raise ValueError("Bends must be supplied in increasing start_x_mm sequence.")
    if any(_bend_end(a, thickness) > b["start_x_mm"] + 1e-12 for a, b in zip(bends, bends[1:])):
        raise ValueError("Bend flat spans overlap; this topology is unsupported.")
    return {"contract": CONTRACT, "id": identifier, "kind": kind,
            "sheet": {"length_mm": length, "width_mm": width,
                      "thickness_mm": thickness, "material": material},
            "bends": bends, "flex_regions": regions}


def _bend_end(bend, thickness):
    return bend["start_x_mm"] + abs(math.radians(bend["angle_deg"])) * (
        bend["inside_radius_mm"] + bend["k_factor"] * thickness)


def _stations(definition):
    values = {0.0, definition["sheet"]["length_mm"]}
    for bend in definition["bends"]:
        start = bend["start_x_mm"]
        end = _bend_end(bend, definition["sheet"]["thickness_mm"])
        values.update(start + (end - start) * i / bend["segments"] for i in range(bend["segments"] + 1))
    return sorted(values)


def _midpoint_at(x, bends, fraction):
    px = pz = heading = 0.0
    cursor = 0.0
    for bend in bends:
        start = bend["start_x_mm"]
        end = _bend_end(bend, definition_thickness(bends))
        straight = min(x, start) - cursor
        if straight > 0:
            px += straight * math.cos(heading)
            pz += straight * math.sin(heading)
            cursor += straight
        if x <= start:
            break
        travel = min(x, end) - start
        final_angle = math.radians(bend["angle_deg"])
        applied = final_angle * fraction
        if abs(applied) < 1e-15:
            px += travel * math.cos(heading)
            pz += travel * math.sin(heading)
        else:
            local_angle = applied * travel / (end - start)
            thickness = definition_thickness(bends)
            correction = (0.5 - bend["k_factor"]) * thickness
            phi = abs(local_angle)
            sign = 1.0 if applied > 0 else -1.0
            # Algebraically this is radius*sin(phi) and
            # radius*(1-cos(phi)), with neutral radius scaled by 1/f.
            # This form neither constructs that potentially huge radius nor
            # loses the small vertical displacement to 1-cos cancellation.
            one_minus_cos = 2.0 * math.sin(0.5 * phi) ** 2
            dx = travel * math.sin(phi) / phi + correction * math.sin(phi)
            dz = sign * (travel * one_minus_cos / phi + correction * one_minus_cos)
            px += dx * math.cos(heading) - dz * math.sin(heading)
            pz += dx * math.sin(heading) + dz * math.cos(heading)
        if x <= end:
            heading += applied * travel / (end - start)
            return px, pz, heading
        heading += applied
        cursor = end
    remainder = x - cursor
    px += remainder * math.cos(heading)
    pz += remainder * math.sin(heading)
    return px, pz, heading


def definition_thickness(bends):
    # Injected on validated bend dictionaries only during mesh construction.
    return bends[0]["_thickness_mm"] if bends else 0.0


def _mesh(definition, fraction, label):
    bends = [dict(item, _thickness_mm=definition["sheet"]["thickness_mm"]) for item in definition["bends"]]
    stations = _stations(definition)
    width = definition["sheet"]["width_mm"]
    half_t = 0.5 * definition["sheet"]["thickness_mm"]
    vertices = []
    for ix, x in enumerate(stations):
        mx, mz, heading = _midpoint_at(x, bends, fraction)
        nx, nz = -math.sin(heading), math.cos(heading)
        for side, y in enumerate((-0.5 * width, 0.5 * width)):
            for face, offset in enumerate((-half_t, half_t)):
                vertices.append({"id": f"{definition['id']}:{label}:v:{ix}:{side}:{face}",
                                 "position_mm": [mx + offset * nx, y, mz + offset * nz]})
    triangles = []
    def add(name, a, b, c):
        triangles.append({"id": f"{definition['id']}:{label}:t:{name}",
                          "vertex_ids": [vertices[a]["id"], vertices[b]["id"], vertices[c]["id"]]})
    for i in range(len(stations) - 1):
        a, b = 4 * i, 4 * (i + 1)
        for face in (0, 1):
            if face == 0:
                add(f"{i}:face:{face}:0", a + face, b + 2 + face, b + face)
                add(f"{i}:face:{face}:1", a + face, a + 2 + face, b + 2 + face)
            else:
                add(f"{i}:face:{face}:0", a + face, b + face, b + 2 + face)
                add(f"{i}:face:{face}:1", a + face, b + 2 + face, a + 2 + face)
        for side in (0, 2):
            if side == 0:
                add(f"{i}:edge:{side}:0", a + side, b + side + 1, a + side + 1)
                add(f"{i}:edge:{side}:1", a + side, b + side, b + side + 1)
            else:
                add(f"{i}:edge:{side}:0", a + side, a + side + 1, b + side + 1)
                add(f"{i}:edge:{side}:1", a + side, b + side + 1, b + side)
    last = 4 * (len(stations) - 1)
    add("end:0:0", 0, 3, 2); add("end:0:1", 0, 1, 3)
    add("end:1:0", last, last + 3, last + 1); add("end:1:1", last, last + 2, last + 3)
    return {"vertices": vertices, "triangles": triangles}


def fold_sheet(raw: dict, fraction=1.0) -> dict:
    """Return flat and folded closed triangle previews; this is not a solver."""
    definition = validate_sheet(raw)
    fraction = _number(fraction, "fraction", 0, 1)
    return {"contract": PREVIEW_CONTRACT, "source_contract": CONTRACT,
            "source_id": definition["id"], "fraction": fraction,
            "model_status": "analytical_geometry_preview",
            "flat_mesh": _mesh(definition, 0.0, "flat"),
            "folded_mesh": _mesh(definition, fraction, "folded"),
            "bends": [{**{key: bend[key] for key in ("id", "start_x_mm", "angle_deg",
                       "inside_radius_mm", "k_factor")},
                       "flat_end_x_mm": _bend_end(bend, definition["sheet"]["thickness_mm"]),
                       "bend_allowance_mm": _bend_end(bend, definition["sheet"]["thickness_mm"])
                       - bend["start_x_mm"]} for bend in definition["bends"]],
            "limitations": ["rectangular sheets and parallel bends only",
                            "prescribed geometry only; no stress, strain, springback, or life prediction"]}


def _dxf_pairs(contents):
    lines = [line.strip() for line in contents.replace("\r", "").split("\n")]
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) % 2:
        raise ValueError("ASCII DXF must contain group-code/value pairs.")
    result = []
    for index in range(0, len(lines), 2):
        try:
            code = int(lines[index])
        except ValueError as exc:
            raise ValueError("ASCII DXF contains a non-integer group code.") from exc
        result.append((code, lines[index + 1]))
    return result


def _import_dxf(contents):
    pairs = _dxf_pairs(contents)
    units_code = next((value for i, (code, value) in enumerate(pairs)
                       if code == 9 and value == "$INSUNITS" and i + 1 < len(pairs)
                       for next_code, value in [pairs[i + 1]] if next_code == 70), "0")
    if units_code not in {"0", "4"}:
        raise ValueError("DXF import supports only unitless-as-mm or millimetre $INSUNITS=4.")
    entities = []
    active = False
    current = None
    for code, value in pairs:
        if code == 0 and value == "SECTION":
            active = False
        elif code == 2 and value == "ENTITIES":
            active = True
        elif code == 0 and value == "ENDSEC":
            active = False
            if current:
                entities.append(current); current = None
        elif active and code == 0:
            if current:
                entities.append(current)
            if value in {"LWPOLYLINE", "LINE", "POLYLINE", "ARC", "CIRCLE", "SPLINE"}:
                if value != "LWPOLYLINE":
                    raise ValueError(f"DXF entity {value} is unsupported; use one closed rectangular LWPOLYLINE.")
                current = {"type": value, "xs": [], "ys": [], "flags": 0,
                           "elevation": 0.0, "thickness": 0.0,
                           "extrusion": [0.0, 0.0, 1.0]}
            elif value not in {"EOF"}:
                raise ValueError(f"DXF entity {value} is unsupported; use one closed rectangular LWPOLYLINE.")
        elif active and current is not None:
            if code == 10: current["xs"].append(_number(float(value), "DXF x"))
            elif code == 20: current["ys"].append(_number(float(value), "DXF y"))
            elif code == 70: current["flags"] = int(value)
            elif code == 42 and float(value) != 0: raise ValueError("Bulged DXF polyline segments are unsupported.")
            elif code == 38: current["elevation"] = _number(float(value), "DXF elevation")
            elif code == 39: current["thickness"] = _number(float(value), "DXF thickness")
            elif code in (210, 220, 230):
                current["extrusion"][(code - 210) // 10] = _number(float(value), "DXF extrusion")
    if current:
        entities.append(current)
    if len(entities) != 1:
        raise ValueError("DXF must contain exactly one supported outline entity.")
    poly = entities[0]
    if poly["elevation"] != 0:
        raise ValueError("Nonzero DXF LWPOLYLINE elevation is unsupported.")
    if poly["thickness"] != 0:
        raise ValueError("Nonzero DXF LWPOLYLINE thickness is ambiguous and unsupported.")
    if poly["extrusion"] != [0.0, 0.0, 1.0]:
        raise ValueError("DXF LWPOLYLINE must use the default (0,0,1) extrusion direction.")
    if len(poly["xs"]) != len(poly["ys"]):
        raise ValueError("DXF LWPOLYLINE must have matching x and y coordinate counts.")
    points = list(zip(poly["xs"], poly["ys"]))
    if len(points) == 5 and points[0] == points[-1]:
        points.pop()
    if len(points) != 4 or not poly["flags"] & 1:
        raise ValueError("DXF outline must be one closed four-vertex LWPOLYLINE.")
    for start, end in zip(points, points[1:] + points[:1]):
        if start == end or (start[0] != end[0] and start[1] != end[1]):
            raise ValueError("DXF rectangle edges must be nonzero and axis aligned in cyclic order.")
    xs, ys = sorted({p[0] for p in points}), sorted({p[1] for p in points})
    if len(xs) != 2 or len(ys) != 2 or set(points) != {(x, y) for x in xs for y in ys}:
        raise ValueError("DXF outline must be an axis-aligned rectangle.")
    source = ({"source_format": "dxf", "source_units": "mm"} if units_code == "4" else
              {"source_format": "dxf", "source_units": "unitless",
               "interpreted_units": "mm", "units_assumption_requires_review": True})
    source["thickness_requires_review"] = True
    return {"contract": CONTRACT, "id": "imported-dxf-sheet", "kind": "sheet_metal",
            "sheet": {"length_mm": xs[1] - xs[0], "width_mm": ys[1] - ys[0],
                      "thickness_mm": None,
                      "material": source},
            "bends": [], "flex_regions": [], "import_status": "requires_thickness"}


def import_sheet_text(contents: str, source_format: str) -> dict:
    """Import neutral JSON or a minimal dependency-free ASCII DXF rectangle."""
    if not isinstance(contents, str) or len(contents.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError(f"contents must be text of at most {MAX_TEXT_BYTES} encoded bytes.")
    if not isinstance(source_format, str):
        raise ValueError("source_format must be json or dxf.")
    fmt = source_format.lower()
    if fmt == "json":
        try:
            raw = json.loads(contents)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON sheet definition: {exc.msg}.") from exc
        return validate_sheet(raw)
    if fmt == "dxf":
        # DXF outlines do not encode a physical sheet thickness. Return a
        # visibly incomplete draft rather than silently inventing one.
        return _import_dxf(contents)
    raise ValueError("source_format must be json or dxf.")
