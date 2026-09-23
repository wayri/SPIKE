"""ODB++ feature records normalized into SPIKE geometry, with source retention."""
from __future__ import annotations

import math
import re
import shlex

MAX_RECORDS = 1_000_000
MAX_LINE_CHARS = 1_048_576


def records(text):
    for index, raw in enumerate(text.splitlines(), 1):
        if index > MAX_RECORDS or len(raw) > MAX_LINE_CHARS:
            raise ValueError("ODB++ text exceeds record/line resource limit.")
        raw = raw.strip()
        if raw and not raw.startswith("#"):
            yield index, raw


def record_sections(raw):
    """Attribute separators are significant only outside quoted property text."""
    quote = None
    start = 0
    sections = []
    for index, character in enumerate(raw):
        if character in {"'", '"'}:
            if quote is None: quote = character
            elif quote == character: quote = None
        elif character == ";" and quote is None:
            sections.append(raw[start:index])
            start = index + 1
    sections.append(raw[start:])
    return sections


def tokens(raw):
    # ODB property strings use quoted spaces, without shell escape semantics.
    lexer = shlex.shlex(record_sections(raw)[0], posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    lexer.commenters = ""
    return list(lexer)


def number(value):
    result = float(value)
    if not math.isfinite(result) or abs(result) > 1e12:
        raise ValueError("ODB++ numbers must be finite and within coordinate bounds.")
    return result


def units(text, fallback="INCH"):
    declarations = {raw.split("=", 1)[1].strip().upper() for _, raw in records(text) if raw.startswith("UNITS=")}
    declarations.update(raw.split()[1].upper() for _, raw in records(text) if raw.startswith("U ") and len(raw.split()) == 2)
    if len(declarations) > 1:
        raise ValueError("Conflicting ODB++ units declarations.")
    unit = next(iter(declarations), fallback)
    if unit not in {"MM", "INCH"}:
        raise ValueError(f"Unsupported ODB++ units: {unit}")
    return (1.0 if unit == "MM" else 25.4), unit


class Attributes:
    def __init__(self):
        self.names = {}
        self.strings = {}

    def consume(self, raw):
        if raw[0] in "@&":
            parts = raw[1:].split(None, 1)
            if len(parts) == 1 and raw[0] == "&":
                key, value = parts[0], ""
            elif len(parts) == 2:
                key, value = parts
            else:
                raise ValueError("Malformed ODB++ attribute lookup entry.")
            table = self.names if raw[0] == "@" else self.strings
            if key in table:
                raise ValueError("Duplicate ODB++ attribute lookup index.")
            table[key] = value
            return True
        return False

    def source(self, raw):
        sections = record_sections(raw)
        assigned = {}
        if len(sections) > 1:
            for item in sections[1].strip().split(","):
                if not item or item.startswith("ID="):
                    continue
                key, _, value = item.strip().partition("=")
                # Keep the raw value and lookup separately: without the vendor
                # attribute type dictionary an integer is NOT necessarily text.
                assigned[self.names.get(key, "@" + key)] = {
                    "raw": value if _ else True,
                    **({"text_candidate": self.strings[value]} if value in self.strings else {}),
                }
        uid = next((part.strip()[3:] for part in sections[1:] if part.strip().startswith("ID=")), "")
        return {"attributes": assigned, "uid": uid, "record": raw}


def arc_mid(start, end, center, clockwise):
    r = math.dist(start, center)
    # ODB coordinates are commonly rounded independently by the exporter.
    # Accept at most 0.1 micrometre of radial closure error; larger mismatches
    # still fail rather than silently changing the declared circle.
    if r <= 0 or not math.isclose(r, math.dist(end, center), rel_tol=1e-9, abs_tol=1e-4):
        raise ValueError("Arc endpoints do not lie on the declared circle.")
    a = math.atan2(start[1] - center[1], start[0] - center[0])
    b = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = ((a - b) if clockwise else (b - a)) % math.tau or math.tau
    mid = a + (-1 if clockwise else 1) * sweep / 2
    return [center[0] + r * math.cos(mid), center[1] + r * math.sin(mid)]


def contours(lines, factor):
    rings = []
    ring = None
    current = None
    for raw in lines:
        t = tokens(raw)
        if t[0] in {"S", "SE", "CT", "CE"}:
            continue
        if t[0] == "OB" and len(t) == 4 and ring is None and t[3] in {"I", "H"}:
            current = [number(v) * factor for v in t[1:3]]
            ring = {"role": "outer" if t[3] == "I" else "cutout", "start_mm": current, "segments": []}
        elif t[0] in {"OS", "OC"} and ring is not None:
            if len(t) != (3 if t[0] == "OS" else 6):
                raise ValueError("Malformed contour segment.")
            end = [number(v) * factor for v in t[1:3]]
            segment = {"kind": "line", "end_mm": end}
            if t[0] == "OC":
                if t[5] not in {"Y", "N"}:
                    raise ValueError("Invalid contour arc direction.")
                center = [number(v) * factor for v in t[3:5]]
                arc_mid(current, end, center, t[5] == "Y")
                segment.update(kind="arc", center_mm=center, clockwise=t[5] == "Y")
                if end == current:
                    middle = arc_mid(current, end, center, t[5] == "Y")
                    ring["segments"].append({**segment, "end_mm": middle})
            elif math.dist(current, end) <= 1e-12:
                # KiCad exports the OB point again as the first OS. Dropping
                # this zero-extent edge preserves the boundary exactly.
                continue
            ring["segments"].append(segment)
            current = end
        elif t[0] == "OE" and ring is not None:
            if len(ring["segments"]) < 2 or math.dist(current, ring["start_mm"]) > 1e-9:
                raise ValueError("ODB++ contours must be explicitly closed.")
            rings.append(ring)
            ring = None
        else:
            raise ValueError(f"Unsupported or malformed contour record: {raw}")
    if ring is not None or not rings or rings[0]["role"] != "outer":
        raise ValueError("Incomplete ODB++ contour.")
    return rings


def symbol_shape(name, scale):
    match = re.fullmatch(r"(r|s|rect|oval|el)([0-9.]+)(?:x([0-9.]+))?(?:xr([0-9.]+))?", name)
    if not match:
        raise ValueError(f"Unsupported ODB++ symbol: {name}")
    kind, width, height, radius = match.groups()
    size = [number(width) * scale, number(height or width) * scale]
    radius_mm = number(radius) * scale if radius is not None else None
    if (min(size) <= 0 or (kind in {"r", "s"} and height is not None)
            or (kind in {"rect", "oval", "el"} and height is None)
            or (radius_mm is not None and (kind != "rect" or radius_mm <= 0 or radius_mm > min(size) / 2))):
        raise ValueError(f"Malformed ODB++ symbol: {name}")
    return {"r": "circle", "s": "rect", "rect": "roundrect" if radius_mm else "rect", "oval": "oval", "el": "ellipse"}[kind], size, radius_mm


def rounded_rect_geometry(size, radius):
    """Return a bounded, conservative local polygon for an ODB rounded rectangle."""
    width, height = size
    # Equal-angle chords are inside the declared circular corners. Bound the
    # sagitta to 1 micrometre, matching the custom-pad geometry contract.
    maximum_sagitta = min(0.001, radius * 0.25)
    segments = max(2, math.ceil((math.pi / 2) / math.acos(max(-1.0, 1 - maximum_sagitta / radius))))
    points = []
    for cx, cy, start in (
        (width / 2 - radius, height / 2 - radius, 0),
        (-width / 2 + radius, height / 2 - radius, math.pi / 2),
        (-width / 2 + radius, -height / 2 + radius, math.pi),
        (width / 2 - radius, -height / 2 + radius, 3 * math.pi / 2),
    ):
        for index in range(segments + 1):
            angle = start + index * math.pi / (2 * segments)
            point = [cx + radius * math.cos(angle), cy + radius * math.sin(angle)]
            if not points or math.dist(points[-1], point) > 1e-12:
                points.append(point)
    if len(points) > 1 and math.dist(points[0], points[-1]) <= 1e-12:
        points.pop()
    return {
        "status": "supported", "coordinate_space": "pad_local_mm", "mirror_x": False,
        "positive_filled_polygon": points,
        "curve_approximation": {
            "method": "inscribed_equal_angle_v1", "maximum_sagitta_mm": maximum_sagitta,
            "source_circle_count": 4, "flattened_segment_count": 4 * segments,
            "conservative_source_containment": True,
        },
    }


def parse_features(text, layer, fallback, issue, *, profile=False):
    factor, _ = units(text, fallback)
    symbols = {}
    attributes = Attributes()
    output = []
    rows = list(records(text))
    i = 0
    feature_index = 0
    declared_count = None
    while i < len(rows):
        line_no, raw = rows[i]
        i += 1
        if attributes.consume(raw):
            continue
        t = tokens(raw)
        if raw.startswith("$"):
            key = t[0][1:]
            if key in symbols or len(t) not in {2, 3}:
                raise ValueError("Malformed/duplicate ODB++ symbol table entry.")
            scale = factor / 1000
            if len(t) == 3:
                if t[2] not in {"I", "M"}:
                    raise ValueError("Unknown ODB++ symbol units.")
                scale = .0254 if t[2] == "I" else .001
            symbols[key] = (t[1], scale)
            continue
        if raw.startswith(("UNITS=", "ID=", "U ")):
            continue
        if t[0] == "F":
            declared_count = int(t[1])
            continue
        source_id = f"odb:{layer}:{feature_index}"
        source = {**attributes.source(raw), "line": line_no, "feature_index": feature_index}
        feature_index += 1
        block = [raw]
        kind = t[0]
        if kind in {"S", "CT", "OB"}:
            terminator = {"S": "SE", "CT": "CE", "OB": "OE"}[kind]
            while i < len(rows):
                block.append(rows[i][1])
                i += 1
                if block[-1] == terminator:
                    break
        source["records"] = block
        row = {"id": f"odb:{layer}:uid:{source['uid']}" if source["uid"] else source_id, "layer": layer, "layers": [layer], "odb_source": source}
        try:
            if kind in {"S", "CT", "OB"}:
                if kind == "S" and (len(t) != 3 or t[1] != "P"):
                    raise ValueError("Negative surface polarity requires layer compositing.")
                if block[-1] != terminator:
                    raise ValueError("Unterminated ODB++ surface.")
                row.update(kind="zone", boundary_rings=contours(block, factor), fill_property="FILL", fill_style_id="odb:solid")
            elif kind in {"L", "A"}:
                sym = 5 if kind == "L" else 7
                if len(t) != (8 if kind == "L" else 11) or t[sym + 1] != "P":
                    raise ValueError("Unsupported line/arc polarity or malformed record.")
                shape, size, _ = symbol_shape(*symbols[t[sym]])
                if shape != "circle":
                    raise ValueError("Non-round stroked symbols require exact sweep normalization.")
                row.update(kind="track" if kind == "L" else "arc", start=[number(v) * factor for v in t[1:3]],
                           end=[number(v) * factor for v in t[3:5]], width=size[0])
                if kind == "A":
                    if t[10] not in {"Y", "N"}:
                        raise ValueError("Invalid arc direction.")
                    center = [number(v) * factor for v in t[5:7]]
                    row.update(mid=arc_mid(row["start"], row["end"], center, t[10] == "Y"),
                               center=center, clockwise=t[10] == "Y")
                elif math.dist(row["start"], row["end"]) <= 1e-12:
                    row.update(kind="pad", at=row.pop("start"), size=size, shape="circle", rotation=0, type="smd")
                    row.pop("end", None); row.pop("width", None)
            elif kind == "P":
                if len(t) < 7 or t[4] != "P":
                    raise ValueError("Resized/negative pads require additional normalization.")
                shape, size, radius = symbol_shape(*symbols[t[3]])
                orient = int(t[6])
                if orient not in range(10) or len(t) != (8 if orient >= 8 else 7):
                    raise ValueError("Invalid pad orientation.")
                rotation = number(t[7]) if orient >= 8 else (orient % 4) * 90
                mirrored = orient in {4, 5, 6, 7, 9}
                # SPIKE's XY convention uses counter-clockwise angles.
                row.update(kind="pad", at=[number(v) * factor for v in t[1:3]], size=size, shape=shape,
                           rotation=rotation if mirrored else -rotation, type="smd")
                if radius is not None:
                    row["shape"] = "custom"
                    row["custom_geometry"] = rounded_rect_geometry(size, radius)
            else:
                raise ValueError(f"Unsupported ODB++ feature record {kind}.")
            if row["kind"] == "zone":
                groups = []
                for ring in row["boundary_rings"]:
                    if ring["role"] == "outer": groups.append([])
                    groups[-1].append(ring)
                for group_index, group in enumerate(groups):
                    output.append({**row, "id": row["id"] + (f":island:{group_index}" if len(groups) > 1 else ""), "boundary_rings": group})
            else:
                output.append(row)
        except (ValueError, KeyError, IndexError) as exc:
            issue("ODB_FEATURE_UNSUPPORTED", str(exc), source_id, source)
    if declared_count is not None and declared_count != feature_index:
        raise ValueError(f"ODB++ feature count mismatch on {layer}: {declared_count} != {feature_index}.")
    return output
