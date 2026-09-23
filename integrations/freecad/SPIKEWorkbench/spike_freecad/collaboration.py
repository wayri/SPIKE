"""Interactive, file-based assembly collaboration using fixed Part constructors."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile

import FreeCAD as App
import Part

from .session_contract import HEADER, SESSION, FEEDBACK, MAX_BYTES, digest, loads, validate


def _property(obj, name, value):
    obj.addProperty("App::PropertyString", name, "SPIKE")
    setattr(obj, name, value)
    obj.setEditorMode(name, 1)


def _matrix(placement):
    m = placement.toMatrix()
    return [getattr(m, f"A{r}{c}") for r in range(1, 5) for c in range(1, 5)]


def _local_digest(feature):
    shape = feature.Shape.copy()
    shape.Placement = App.Placement()
    # OCC's in-memory flags are normalized by BREP loading, as on FCStd reopen.
    # Normalize both paths before hashing so saving a document is not an edit.
    normalized = Part.Shape()
    normalized.importBrepFromString(shape.exportBrepToString())
    return hashlib.sha256(normalized.exportBrepToString().encode()).hexdigest()


def _shape(geometry, assets):
    if geometry["type"] == "step":
        data = base64.b64decode(assets[geometry["asset_sha256"]]["data_base64"], validate=True)
        with tempfile.TemporaryDirectory(prefix="spike-session-") as folder:
            path = Path(folder) / "asset.step"
            path.write_bytes(data)
            # Preserve source STEP's own internal placements below a neutral
            # feature frame, separate from the occurrence placement.
            return Part.makeCompound([Part.read(str(path))])
    def wire(ring):
        z = geometry["z_mm"]
        vector = lambda p: App.Vector(p[0], p[1], z)
        start = vector(ring["start_mm"])
        edges = []
        for segment in ring["segments"]:
            end = vector(segment["end_mm"])
            edges.append(Part.Arc(start, vector(segment["mid_mm"]), end).toShape() if segment["kind"] == "arc" else Part.makeLine(start, end))
            start = end
        return Part.Wire(edges)
    rings = geometry["rings"]
    face = Part.Face(wire(next(r for r in rings if r["role"] == "outer")))
    for ring in rings:
        if ring["role"] == "cutout":
            hole = Part.Face(wire(ring))
            if abs(face.common(hole).Area - hole.Area) > max(1e-8, hole.Area*1e-8):
                raise ValueError("Board cutouts must be contained and disjoint.")
            face = face.cut(hole)
    return face.extrude(App.Vector(0, 0, geometry["height_mm"]))


def import_session(document, payload):
    validate(payload)
    if payload["contract"] != SESSION: raise ValueError("Expected SPIKE collaboration session.")
    if any(getattr(o, "SPIKESessionId", "") == payload["session_id"] for o in document.Objects):
        raise ValueError("This session is already open in the document.")
    document.openTransaction("Import SPIKE collaboration session")
    try:
        root = document.addObject("App::Part", "SPIKE_Session")
        root.Label = "SPIKE collaboration"
        _property(root, "SPIKESessionId", payload["session_id"])
        baseline = {"contract": FEEDBACK, **{k: payload[k] for k in HEADER},
                    "objects": [{k: o[k] for k in ("id", "name", "transform")} for o in payload["objects"]], "measurements": []}
        _property(root, "SPIKEBaselineJSON", json.dumps(baseline))
        _property(root, "SPIKEParentsJSON", json.dumps({o["id"]: o["parent_id"] for o in payload["objects"]}))
        _property(root, "SPIKEDiagnosticsJSON", json.dumps(payload["diagnostics"]))
        _property(root, "SPIKEMeasurementsJSON", "[]")
        _property(root, "SPIKEMeasurementPoses", "")
        created = {}
        for row in payload["objects"]:
            obj = document.addObject("App::Part", "SPIKE_Occurrence")
            obj.Label = row["name"]
            _property(obj, "SPIKEOccurrenceId", row["id"])
            _property(obj, "SPIKESessionId", payload["session_id"])
            _property(obj, "SPIKEGeometryName", "")
            created[row["id"]] = obj
            if row["geometry"]:
                feature = document.addObject("Part::Feature", "SPIKE_Geometry")
                feature.Label = row["name"] + " geometry"
                feature.Shape = _shape(row["geometry"], payload["assets"])
                if feature.Shape.isNull() or not feature.Shape.isValid() or not feature.Shape.Solids or any(s.Volume <= 0 for s in feature.Shape.Solids):
                    raise ValueError(f"{row['name']}: imported geometry is not a valid solid.")
                obj.addObject(feature)
                obj.SPIKEGeometryName = feature.Name
                _property(feature, "SPIKELocalShapeSHA256", _local_digest(feature))
                _property(feature, "SPIKEBaselinePlacement", json.dumps(_matrix(feature.Placement)))
                if feature.ViewObject:
                    feature.ViewObject.ShapeColor = (0.15, 0.55, 0.30) if row["kind"] == "board" else (0.7, 0.72, 0.78)
        for row in payload["objects"]:
            parent = created[row["parent_id"]] if row["parent_id"] else root
            parent.addObject(created[row["id"]])
            created[row["id"]].Placement = App.Placement(App.Matrix(*row["transform"]))
        document.recompute()
        # Recompute finalizes OCC shape flags; bind the resulting local BREP,
        # after parent relationships and placements have been established.
        for obj in created.values():
            if obj.SPIKEGeometryName:
                feature = document.getObject(obj.SPIKEGeometryName)
                feature.SPIKELocalShapeSHA256 = _local_digest(feature)
                feature.SPIKEBaselinePlacement = json.dumps(_matrix(feature.Placement))
        document.commitTransaction()
        return root
    except Exception:
        document.abortTransaction()
        raise


def session_root(document, selection=()):
    roots = [o for o in document.Objects if hasattr(o, "SPIKEBaselineJSON")]
    selected = [o for o in roots if o in selection]
    if len(selected) == 1: return selected[0]
    session_ids = set()
    for obj in selection:
        owner = obj if hasattr(obj, "SPIKESessionId") else obj.getParentGeoFeatureGroup()
        if owner is not None and hasattr(owner, "SPIKESessionId"):
            session_ids.add(owner.SPIKESessionId)
    matches = [o for o in roots if o.SPIKESessionId in session_ids]
    if len(session_ids) == 1 and len(matches) == 1: return matches[0]
    if len(roots) != 1: raise ValueError("Select exactly one SPIKE collaboration root.")
    return roots[0]


def build_feedback(document, root):
    result = loads(root.SPIKEBaselineJSON)
    parents = json.loads(root.SPIKEParentsJSON)
    expected_ids = {o["id"] for o in result["objects"]}
    occurrences = [o for o in document.Objects if getattr(o, "SPIKESessionId", "") == root.SPIKESessionId and hasattr(o, "SPIKEOccurrenceId")]
    by_id = {o.SPIKEOccurrenceId: o for o in occurrences}
    if len(by_id) != len(occurrences) or set(by_id) != expected_ids:
        raise ValueError("Session occurrences were deleted or duplicated; export a new session.")
    if _matrix(root.getGlobalPlacement()) != _matrix(App.Placement()):
        raise ValueError("Move individual occurrences; the session root must remain at the assembly origin.")
    for row in result["objects"]:
        obj = by_id[row["id"]]
        parent = by_id[parents[row["id"]]] if parents[row["id"]] else root
        if obj not in parent.Group or obj.getParentGeoFeatureGroup() != parent:
            raise ValueError("Reparenting requires a new session; this feedback supports placement and label edits.")
        expected_children = {by_id[i].Name for i, p in parents.items() if p == row["id"]}
        if obj.SPIKEGeometryName:
            expected_children.add(obj.SPIKEGeometryName)
            feature = document.getObject(obj.SPIKEGeometryName)
            if feature is None or feature not in obj.Group or _local_digest(feature) != feature.SPIKELocalShapeSHA256 or _matrix(feature.Placement) != json.loads(feature.SPIKEBaselinePlacement):
                raise ValueError("Geometry changed inside an occurrence. Export new geometry through Export SPIKE Assembly.")
        if {c.Name for c in obj.Group} != expected_children:
            raise ValueError("Session contains added or removed geometry. Use Export SPIKE Assembly for structural changes.")
        row["name"] = obj.Label
        row["transform"] = _matrix(obj.Placement)
    if {c.Name for c in root.Group} != {by_id[i].Name for i,p in parents.items() if p is None}:
        raise ValueError("Session root structure changed; export a fresh session.")
    result["measurements"] = json.loads(root.SPIKEMeasurementsJSON) if root.SPIKEMeasurementPoses == digest(result["objects"]) else []
    return validate(result)


def measure_clearance(document, root, selected):
    feedback = build_feedback(document, root)
    # Selecting a geometry child is equivalent to selecting its occurrence.
    occurrences = []
    for item in selected:
        obj = item if hasattr(item, "SPIKEOccurrenceId") else item.getParentGeoFeatureGroup()
        if obj is None or not hasattr(obj, "SPIKEOccurrenceId") or obj.SPIKESessionId != root.SPIKESessionId:
            raise ValueError("Select two solid occurrences from this SPIKE session.")
        if obj not in occurrences: occurrences.append(obj)
    if len(occurrences) != 2: raise ValueError("Select exactly two solid occurrences.")
    shapes = []
    for obj in occurrences:
        feature = document.getObject(obj.SPIKEGeometryName)
        if feature is None: raise ValueError("An origin-only occurrence has no solid to measure.")
        shape = feature.Shape.copy()
        shape.Placement = feature.getGlobalPlacement().multiply(feature.Placement.inverse()).multiply(shape.Placement)
        shapes.append(shape)
    distance = shapes[0].distToShape(shapes[1])[0]
    overlap = max(0.0, shapes[0].common(shapes[1]).Volume)
    row = {"object_a_id": occurrences[0].SPIKEOccurrenceId, "object_b_id": occurrences[1].SPIKEOccurrenceId,
           "distance_mm": distance, "overlap_volume_mm3": overlap}
    rows = feedback["measurements"]
    pair = {row["object_a_id"], row["object_b_id"]}
    rows = [r for r in rows if {r["object_a_id"], r["object_b_id"]} != pair] + [row]
    validate({**feedback, "measurements": rows})
    root.SPIKEMeasurementsJSON = json.dumps(rows)
    root.SPIKEMeasurementPoses = digest(feedback["objects"])
    return row


def write_feedback(path, value):
    validate(value)
    target = Path(path)
    # A unique temporary sibling avoids clobbering another writer's temporary file.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False, suffix=".tmp") as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, allow_nan=False, indent=2)
            stream.close()
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
