"""Fixed FreeCAD-hosted BREP/STEP assembly writer; no user script execution."""
import base64
import hashlib
import json
import math
from pathlib import Path

import FreeCAD as App
import Import
import Part


def vector(p, z=0):
    return App.Vector(*p) if len(p) == 3 else App.Vector(p[0], p[1], z)


def wire(ring, z):
    current = vector(ring["start_mm"], z)
    edges = []
    for s in ring["segments"]:
        end = vector(s["end_mm"], z)
        edge = Part.makeLine(current, end) if s["kind"] == "line" else Part.Arc(current, vector(s["mid_mm"], z), end).toShape()
        edges.append(edge)
        current = end
    result = Part.Wire(edges)
    if not result.isClosed() or not result.isValid():
        raise ValueError("Invalid or open extrusion wire.")
    return result


def shape_for(geom, root, token):
    kind = geom["type"]
    if kind == "box":
        return Part.makeBox(*geom["size_mm"])
    if kind == "cylinder":
        return Part.makeCylinder(geom["radius_mm"], geom["height_mm"])
    if kind == "extrusion":
        rings = geom["rings"]
        z = geom.get("z_mm", 0)
        face = Part.Face(wire(next(r for r in rings if r["role"] == "outer"), z))
        for r in rings:
            if r["role"] == "cutout":
                hole = Part.Face(wire(r, z))
                common = face.common(hole)
                if abs(common.Area-hole.Area) > max(1e-8, hole.Area*1e-8):
                    raise ValueError("Cutout must be wholly inside the outer face and disjoint from other cutouts.")
                face = face.cut(hole)
        if not face.isValid() or face.Area <= 0:
            raise ValueError("Extrusion face is invalid.")
        return face.extrude(App.Vector(0, 0, geom["height_mm"]))
    if kind == "route":
        points = [vector(p) for p in geom["points_mm"]]
        radius = geom["radius_mm"]
        # Round-jointed routing envelope. It is deliberately not a bend-radius-
        # controlled manufactured cable or a prediction of twist/shield geometry.
        pieces = [Part.makeCylinder(radius, (b-a).Length, a, b-a) for a,b in zip(points, points[1:])]
        pieces.extend(Part.makeSphere(radius, p) for p in points[1:-1])
        return pieces[0].multiFuse(pieces[1:]).removeSplitter() if len(pieces) > 1 else pieces[0]
    if kind == "step":
        source = root / (token + "-input.step")
        source.write_bytes(base64.b64decode(geom["data_base64"], validate=True))
        return Part.read(str(source))
    raise ValueError("Unsupported geometry.")


def metrics(obj):
    shape = obj.Shape.copy()
    shape.Placement = obj.getGlobalPlacement()
    box = shape.BoundBox
    return {"solid_count": len(shape.Solids), "volume_mm3": sum(s.Volume for s in shape.Solids),
            "bounds_mm": [box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax]}


def solid_leaves(obj):
    children = getattr(obj, "Group", [])
    if children:
        return [leaf for child in children for leaf in solid_leaves(child)]
    return [obj] if hasattr(obj, "Shape") and obj.Shape.Solids else []


def combined_metrics(leaves):
    rows = [metrics(o) for o in leaves]
    return {"solid_count": sum(r["solid_count"] for r in rows), "volume_mm3": sum(r["volume_mm3"] for r in rows),
            "bounds_mm": [min(r["bounds_mm"][i] for r in rows) for i in range(3)] + [max(r["bounds_mm"][i] for r in rows) for i in range(3,6)]}


def export(root_name):
    root = Path(root_name)
    request = json.loads((root / "assembly.json").read_text(encoding="utf-8"))
    document = App.newDocument("SPIKE_EXCHANGE")
    created, records = {}, []
    brep_bytes = 0
    try:
        # AP214 preserves product assembly structure. Sidecar/FCStd carry arbitrary properties.
        prefs = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Part/STEP")
        prefs.SetString("Scheme", "AP214IS")
        prefs.SetBool("ExportLegacy", False)
        prefs.SetBool("ReadShapeCompoundMode", False)
        for obj in request["objects"]:
            token = "SPIKE_" + hashlib.sha256(obj["id"].encode()).hexdigest()[:24]
            feature = document.addObject("App::Part" if obj["kind"] == "assembly" else "Part::Feature", token)
            feature.Label = obj["name"] + " [" + token + "]"
            feature.addProperty("App::PropertyString", "SPIKE_ID", "SPIKE").SPIKE_ID = obj["id"]
            feature.addProperty("App::PropertyString", "SPIKE_Kind", "SPIKE").SPIKE_Kind = obj["kind"]
            feature.addProperty("App::PropertyString", "SPIKE_Properties", "SPIKE").SPIKE_Properties = json.dumps(obj.get("properties", {}), ensure_ascii=False)
            feature.addProperty("App::PropertyString", "SPIKE_Material", "SPIKE").SPIKE_Material = obj.get("material_id", "")
            feature.addProperty("App::PropertyString", "SPIKE_Source", "SPIKE").SPIKE_Source = json.dumps(obj.get("source", {}), ensure_ascii=False)
            if "color_rgb" in obj:
                feature.addProperty("App::PropertyColor", "SPIKE_Color", "SPIKE").SPIKE_Color = tuple(obj["color_rgb"])
            if obj["kind"] != "assembly":
                shape = shape_for(obj["geometry"], root, token)
                if shape.isNull() or not shape.isValid() or not shape.Solids or any(s.Volume <= 0 for s in shape.Solids):
                    raise ValueError(f"Object {obj['id']} did not form valid positive-volume solids.")
                # Reject mixed wire/surface/solid STEP compounds rather than omit them.
                solids_only = Part.makeCompound(shape.Solids)
                if any(len(getattr(shape, k)) != len(getattr(solids_only, k)) for k in ("Faces", "Edges", "Vertexes")):
                    raise ValueError(f"Object {obj['id']} contains non-solid surfaces, wires or points.")
                if len(shape.Solids) == 1:
                    shape = shape.Solids[0]
                # Keep source STEP placements below a neutral feature placement.
                if obj["geometry"]["type"] == "step":
                    shape = Part.makeCompound([shape])
                feature.Shape = shape
                local_brep = root / (token + ".brep")
                shape.exportBrep(str(local_brep))
                brep_bytes += local_brep.stat().st_size
                if brep_bytes > 64 * 1024**2:
                    raise ValueError("Individual BREP output exceeds the 64 MiB combined budget.")
            matrix = App.Matrix(*obj["transform"])
            feature.Placement = App.Placement(matrix)
            created[obj["id"]] = feature
            records.append({"id": obj["id"], "name": obj["name"], "token": token,
                            "step_label": feature.Label, "kind": obj["kind"], "parent_id": obj.get("parent_id", ""),
                            "material_id": obj.get("material_id", ""), "transform": obj["transform"],
                            "color_rgb": obj.get("color_rgb"),
                            "properties": obj.get("properties", {}), "source": obj.get("source", {}),
                            "brep_file": token + ".brep" if obj["kind"] != "assembly" else None})
        for obj in request["objects"]:
            if obj.get("parent_id"):
                created[obj["parent_id"]].addObject(created[obj["id"]])
        document.recompute()
        for record in records:
            if record["kind"] != "assembly":
                record.update(metrics(created[record["id"]]))
        roots = [created[o["id"]] for o in request["objects"] if not o.get("parent_id")]
        # STEP's top-level product is a coordinate root. Keep user placements
        # below an identity exchange root, including a single translated board.
        exchange_root = document.addObject("App::Part", "SPIKE_ExchangeRoot")
        exchange_root.Label = request["name"]
        exchange_root.addProperty("App::PropertyString", "SPIKE_Materials", "SPIKE").SPIKE_Materials = json.dumps(request.get("materials", []), ensure_ascii=False)
        exchange_root.addProperty("App::PropertyString", "SPIKE_Provenance", "SPIKE").SPIKE_Provenance = json.dumps(request.get("provenance", {}), ensure_ascii=False)
        for obj in roots:
            exchange_root.addObject(obj)
        document.recompute()
        output = root / "assembly.step"
        Import.export([exchange_root], str(output), exportHidden=True, legacy=False, keepPlacement=True)
        document.saveAs(str(root / "assembly.FCStd"))
        if output.stat().st_size > 64 * 1024**2:
            raise ValueError("STEP output exceeds 64 MiB.")
        # Read our STEP using a fresh document and compare each named leaf in
        # world coordinates. This detects dropped identities and placement loss.
        check = App.newDocument("SPIKE_REIMPORT")
        try:
            Import.insert(str(output), check.Name)
            check.recompute()
            imported = [o for o in check.Objects if hasattr(o, "Shape") and not getattr(o, "Group", []) and o.Shape.Solids]
            consumed = set()
            for record in records:
                if record["kind"] == "assembly":
                    groups = [o for o in check.Objects if record["token"] in o.Label]
                    if len(groups) != 1:
                        raise ValueError(f"STEP reimport lost assembly identity {record['id']}.")
                    if record["parent_id"]:
                        parent_token = next(r["token"] for r in records if r["id"] == record["parent_id"])
                        if not any(parent_token in p.Label for p in groups[0].InList):
                            raise ValueError(f"STEP reimport changed group parent for {record['id']}.")
                    continue
                # OCC may decompose a multi-solid asset into a group whose
                # children inherit its label. Match the root of that subtree.
                matches = [o for o in check.Objects if record["token"] in o.Label
                           and not any(record["token"] in p.Label for p in o.InList)]
                if len(matches) != 1:
                    raise ValueError(f"STEP reimport lost named object {record['id']} ({len(matches)} matches): {[(o.TypeId, o.Label) for o in imported]}.")
                leaves = solid_leaves(matches[0])
                if not leaves or any(o.Name in consumed for o in leaves):
                    raise ValueError("STEP objects are empty or share unexpected leaf instances.")
                consumed.update(o.Name for o in leaves)
                observed = combined_metrics(leaves)
                parent_id = record["parent_id"]
                if parent_id:
                    parent_token = next(r["token"] for r in records if r["id"] == parent_id)
                    if not any(parent_token in p.Label for p in matches[0].InList):
                        raise ValueError(f"STEP reimport changed parent assembly for {record['id']}.")
                if observed["solid_count"] != record["solid_count"] or not math.isclose(observed["volume_mm3"], record["volume_mm3"], rel_tol=1e-6, abs_tol=1e-7):
                    raise ValueError(f"STEP reimport changed solid volume/count for {record['id']}.")
                if any(abs(a-b) > 1e-5 for a,b in zip(observed["bounds_mm"], record["bounds_mm"])):
                    raise ValueError(f"STEP reimport changed placement/bounds for {record['id']}: {record['bounds_mm']} -> {observed['bounds_mm']}.")
                record["step_roundtrip"] = "passed"
            if len(imported) != len(consumed):
                raise ValueError("STEP reimport changed the named leaf count.")
        finally:
            App.closeDocument(check.Name)
        report = {"contract": "spike/mcad-export-manifest/v1", "assembly_id": request["id"], "name": request["name"],
                  "units": "mm", "step_schema": "AP214IS", "freecad_version": ".".join(App.Version()[:3]),
                  "objects": records, "materials": request.get("materials", []), "properties": request.get("properties", {}),
                  "provenance": request.get("provenance", {}), "diagnostics": request.get("diagnostics", []),
                  "roundtrip": "named solids, volume and world bounds checked", "solver_qualified": False,
                  "metadata_carrier": "companion JSON; custom FreeCAD properties are not assumed to survive STEP"}
        (root / "manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    finally:
        App.closeDocument(document.Name)
