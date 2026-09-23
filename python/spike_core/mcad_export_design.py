"""Explicit board/harness projection into the mechanical exchange schema.

Missing source geometry is reported. No bounding-box PCB or component model is
invented. More detailed geometry can be supplied as named assembly objects.
"""
import copy
import hashlib
import json
import math

from .mcad_export_contract import CONTRACT, IDENTITY, validate_assembly


def _rings_from_drawings(drawings):
    edges = []
    for d in drawings:
        if d.get("layer") != "Edge.Cuts":
            continue
        kind = d.get("type")
        if kind not in {"line", "arc", "rect"}:
            raise ValueError("Board outline needs explicit rings for this Edge.Cuts primitive.")
        if kind == "rect":
            a, b = d["start"], d["end"]
            pts = [a, [b[0], a[1]], b, [a[0], b[1]], a]
            edges.extend((list(a), {"kind": "line", "end_mm": list(b)}) for a,b in zip(pts, pts[1:]))
        else:
            s = {"kind": kind, "end_mm": list(d["end"])}
            if kind == "arc":
                if "mid" not in d:
                    raise ValueError("Outline arc needs its source midpoint.")
                s["mid_mm"] = list(d["mid"])
            edges.append((list(d["start"]), s))
    if not edges:
        return []
    start, first = edges.pop(0)
    segments, current = [first], first["end_mm"]
    while math.dist(current, start) > 1e-8:
        matches = [(i, False) for i,(a,b) in enumerate(edges) if math.dist(a, current) < 1e-8]
        matches += [(i, True) for i,(a,b) in enumerate(edges) if math.dist(b["end_mm"], current) < 1e-8]
        if len(matches) != 1:
            raise ValueError("Board edge graph is open or branched; supply explicit closed rings.")
        index, reverse = matches[0]
        a, s = edges.pop(index)
        if reverse:
            s = {**s, "end_mm": a}
        segments.append(s)
        current = s["end_mm"]
    if edges:
        raise ValueError("Multiple Edge.Cuts loops need explicit outer/cutout rings for MCAD export.")
    return [{"role": "outer", "start_mm": start, "segments": segments}]


def _convert_rings(rings):
    from .odb_features import arc_mid
    result = copy.deepcopy(rings)
    for ring in result:
        current = ring["start_mm"]
        for s in ring["segments"]:
            if s["kind"] == "arc" and "mid_mm" not in s:
                s["mid_mm"] = arc_mid(current, s["end_mm"], s["center_mm"], s["clockwise"])
            s.pop("center_mm", None)
            s.pop("clockwise", None)
            current = s["end_mm"]
    return result


def assembly_from_context(context):
    parameters = context.get("parameters", {})
    if not isinstance(parameters.get("allow_partial", False), bool):
        raise ValueError("allow_partial must be a boolean.")
    if "assembly" in parameters:
        if parameters["assembly"].get("diagnostics") and not parameters.get("allow_partial", False):
            raise ValueError("Assembly contains projection diagnostics; review before setting allow_partial.")
        return validate_assembly(parameters["assembly"])
    design = copy.deepcopy(context.get("design") or {})
    project = context.get("project", {})
    if project.get("source_board") and project.get("source_format") == "kicad":
        import tempfile
        from pathlib import Path
        from .kicad_importer import import_kicad_design
        with tempfile.TemporaryDirectory(prefix="spike-mcad-source-") as folder:
            path = Path(folder) / "source.kicad_pcb"
            path.write_text(project["source_board"], encoding="utf-8")
            design = import_kicad_design(str(path)).to_dict()
    if design.get("contract") == "spike/design-ir/v2":
        from .design_ir_v2 import DesignIRV2
        design = DesignIRV2.from_dict(design).to_v1().to_dict()
    if design and design.get("contract") != "spike/v1":
        raise ValueError("Mechanical projection requires DesignIR v1/v2 or an explicit assembly.")
    ident = design.get("design_id") or hashlib.sha256(json.dumps(design, sort_keys=True).encode()).hexdigest()[:24]
    assembly = {"contract": CONTRACT, "id": "mcad:" + ident, "name": context.get("project", {}).get("name") or design.get("name") or "SPIKE assembly",
                "units": "mm", "objects": [], "materials": [], "diagnostics": [],
                "provenance": {"design_id": ident, "source_format": design.get("source_format"), "coordinate_convention": "source XY, physical stackup top-to-bottom in positive Z"}}
    objects, diagnostics = assembly["objects"], assembly["diagnostics"]
    def issue(code, message, source_id=""):
        diagnostics.append({"code": code, "message": message, "source_id": source_id})
    if design:
        objects.append({"id": "board", "name": design.get("name") or "Board", "kind": "assembly"})
        rings = parameters.get("board_rings") or design.get("metadata", {}).get("board_outline_rings")
        if rings:
            rings = _convert_rings(rings)
        else:
            rings = _rings_from_drawings(design.get("metadata", {}).get("board_outline_drawings", []))
        if not rings:
            raise ValueError("Board export requires a source outline or explicit board_rings; bounds are not an outline.")
        stackup = design.get("stackup", [])
        if not stackup:
            raise ValueError("Board export requires a physical stackup with explicit thickness and material.")
        z = 0.
        dielectric_count = 0
        for index, layer in enumerate(stackup):
            name = str(layer.get("name", index))
            kind = str(layer.get("type", layer.get("layer_type", ""))).lower()
            structural = kind in {"dielectric", "core", "prepreg", "copper"} or "dielectric" in name.lower() or name.endswith(".Cu")
            thickness = layer.get("thickness_mm", layer.get("thickness"))
            if thickness is None and not structural:
                issue("PROCESS_LAYER_THICKNESS_UNSPECIFIED", "Nonstructural print/paste layer has no thickness; omitted from the mechanical stack height.", name)
                continue
            if not isinstance(thickness, (int, float)) or isinstance(thickness, bool) or not math.isfinite(thickness) or thickness <= 0:
                raise ValueError(f"Stackup layer {layer.get('name', index)} needs positive thickness_mm.")
            if kind in {"dielectric", "core", "prepreg"} or "dielectric" in name.lower():
                material_id = f"layer-material:{index}"
                assembly["materials"].append({"id": material_id, "name": str(layer.get("material") or name), "properties": copy.deepcopy(layer)})
                objects.append({"id": f"layer:{index}", "name": name, "kind": "dielectric", "parent_id": "board", "material_id": material_id,
                                "geometry": {"type": "extrusion", "rings": rings, "height_mm": thickness, "z_mm": z},
                                "source": {"layer": name, "stackup_index": index}})
                dielectric_count += 1
            else:
                issue("LAYER_GEOMETRY_OMITTED", "Patterned copper/process layer needs explicit solid geometry; no full-board slab was invented.", name)
            z += thickness
        if not dielectric_count:
            raise ValueError("No physical dielectric layers are available for the board body.")
        if design.get("pads") or design.get("vias") or design.get("metadata", {}).get("drills"):
            issue("BOARD_DRILLS_OMITTED", "Automatic board projection currently retains only outline cutouts; pad/via drills require explicit geometry.")
        if design.get("bends") or design.get("technology", "rigid") != "rigid":
            issue("FLAT_BOARD_PROJECTION", "Flex bends are not folded by this projection; provide placed material bodies for the formed assembly.")
        for component in design.get("components", []):
            issue("COMPONENT_GEOMETRY_REQUIRED", "Component geometry and complete model-to-assembly transform must be supplied as a named STEP object.", str(component.get("id") or component.get("reference") or component.get("ref")))
        assembly.setdefault("properties", {})["component_inventory"] = design.get("components", [])
    harness = context.get("harness")
    if harness:
        from .harness import validate_harness
        harness = validate_harness(harness)
        objects.append({"id": "harness", "name": harness["name"], "kind": "assembly"})
        assembly.setdefault("properties", {})["harness_document"] = harness
        routes = {r["id"]: r for r in harness["routes"]}
        for w in harness["wires"]:
            route = routes.get(w.get("route_id"))
            radius = parameters.get("wire_radius_mm", {}).get(w["id"])
            if not route or radius is None:
                issue("WIRE_GEOMETRY_REQUIRED", "Wire needs a route and explicit external radius in wire_radius_mm.", w["id"])
                continue
            frame = route.get("frame_id")
            transform = parameters.get("route_frames", {}).get(frame, IDENTITY) if frame in (None, "", "assembly") else parameters.get("route_frames", {}).get(frame)
            if transform is None:
                raise ValueError(f"Harness route frame {frame} needs an explicit transform in route_frames.")
            objects.append({"id": "wire:" + w["id"], "name": w["id"], "kind": "harness", "parent_id": "harness", "transform": list(transform),
                            "geometry": {"type": "route", "points_mm": route["points_mm"], "radius_mm": radius}, "properties": copy.deepcopy(w)})
            issue("ROUTING_ENVELOPE", "Round-jointed wire envelope; bend radii, twist, shielding and separate insulation layers require explicit geometry.", w["id"])
        for connector in harness["connectors"]:
            issue("CONNECTOR_GEOMETRY_REQUIRED", "Harness connector has no automatic mechanical body.", connector["id"])
    objects.extend(copy.deepcopy(parameters.get("objects", [])))
    if harness and not any(o.get("parent_id") == "harness" for o in objects):
        objects[:] = [o for o in objects if o["id"] != "harness"]
    assembly["materials"].extend(copy.deepcopy(parameters.get("materials", [])))
    if diagnostics and not parameters.get("allow_partial", False):
        raise ValueError("MCAD projection is incomplete: " + "; ".join(sorted({i["code"] for i in diagnostics})) + ". Review with mcad-plan; explicit allow_partial exports only the stated geometry.")
    return validate_assembly(assembly)
