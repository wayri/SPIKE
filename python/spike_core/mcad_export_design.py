"""Explicit board/harness projection into the mechanical exchange schema.

Missing source geometry is reported. No bounding-box PCB or component model is
invented. More detailed geometry can be supplied as named assembly objects.
"""
import copy
import hashlib
import json
import math

from .assembly_frames import multiply
from .mcad_export_contract import CONTRACT, IDENTITY, validate_assembly


def _rings_from_drawings(drawings):
    selected = [row for row in drawings if row.get('layer') == 'Edge.Cuts']
    if all(row.get('type') in {'line', 'rect'} for row in selected):
        from .board_outline_geometry import straight_outline_rings
        return straight_outline_rings(selected)
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


def _design_views(raw):
    """Return solver-facing and canonical views without discarding source data."""
    if not isinstance(raw, dict):
        raise ValueError("Mechanical projection requires a SpiDeR design object.")
    if raw.get("contract") == "spike/design-ir/v2":
        from .spider_v2 import SpiDeRV2
        canonical = SpiDeRV2.from_dict(raw)
        return canonical.to_v1(allow_unprojected_arcs=True).to_dict(), canonical.to_dict()
    if raw.get("contract") == "spike/v1":
        return copy.deepcopy(raw), copy.deepcopy(raw)
    raise ValueError("Mechanical projection requires SpiDeR v1/v2 or an explicit assembly.")


def _component_identity(component, index):
    return str(component.get("id") or component.get("reference") or component.get("ref") or f"component-{index}")


def _append_board_projection(assembly, design, *, object_id, name, transform, parent_id=None,
                             design_id="", canonical_design=None, legacy_ids=False, issue):
    """Append one board occurrence and occurrence-qualified source metadata."""
    objects = assembly["objects"]
    board = {"id": object_id, "name": name, "kind": "assembly", "transform": list(transform),
             "source": {"occurrence_id": object_id, "design_id": design_id}}
    if parent_id:
        board["parent_id"] = parent_id
    objects.append(board)
    rings = design.get("metadata", {}).get("board_outline_rings")
    if rings:
        rings = _convert_rings(rings)
    else:
        rings = _rings_from_drawings(design.get("metadata", {}).get("board_outline_drawings", []))
    if not rings:
        raise ValueError(f"Board occurrence {object_id} requires a source outline; bounds are not an outline.")
    stackup = design.get("stackup", [])
    if not stackup:
        raise ValueError(f"Board occurrence {object_id} requires a physical stackup with explicit thickness and material.")
    z = 0.0
    dielectric_count = 0
    for index, layer in enumerate(stackup):
        layer_name = str(layer.get("name", index))
        kind = str(layer.get("type", layer.get("layer_type", ""))).lower()
        structural = kind in {"dielectric", "core", "prepreg", "copper"} or "dielectric" in layer_name.lower() or layer_name.endswith(".Cu")
        thickness = layer.get("thickness_mm", layer.get("thickness"))
        source_id = layer_name if legacy_ids else f"{object_id}/{layer_name}"
        if thickness is None and not structural:
            issue("PROCESS_LAYER_THICKNESS_UNSPECIFIED", "Nonstructural print/paste layer has no thickness; omitted from the mechanical stack height.", source_id)
            continue
        if not isinstance(thickness, (int, float)) or isinstance(thickness, bool) or not math.isfinite(thickness) or thickness <= 0:
            raise ValueError(f"Stackup layer {layer_name} on board occurrence {object_id} needs positive thickness_mm.")
        if kind in {"dielectric", "core", "prepreg"} or "dielectric" in layer_name.lower():
            material_id = f"layer-material:{index}" if legacy_ids else f"{object_id}/layer-material:{index}"
            layer_id = f"layer:{index}" if legacy_ids else f"{object_id}/layer:{index}"
            assembly["materials"].append({"id": material_id, "name": str(layer.get("material") or layer_name),
                                          "properties": copy.deepcopy(layer)})
            objects.append({"id": layer_id, "name": layer_name, "kind": "dielectric", "parent_id": object_id,
                            "material_id": material_id,
                            "geometry": {"type": "extrusion", "rings": rings, "height_mm": thickness, "z_mm": z},
                            "source": {"layer": layer_name, "stackup_index": index,
                                       "occurrence_id": object_id, "design_id": design_id}})
            dielectric_count += 1
        else:
            issue("LAYER_GEOMETRY_OMITTED", "Patterned copper/process layer needs explicit solid geometry; no full-board slab was invented.", source_id)
        z += thickness
    if not dielectric_count:
        raise ValueError(f"No physical dielectric layers are available for board occurrence {object_id}.")
    if design.get("pads") or design.get("vias") or design.get("metadata", {}).get("drills"):
        issue("BOARD_DRILLS_OMITTED", "Automatic board projection currently retains only outline cutouts; pad/via drills require explicit geometry.", object_id)
    if design.get("bends") or design.get("technology", "rigid") != "rigid":
        issue("FLAT_BOARD_PROJECTION", "Flex bends are not folded by this projection; provide placed material bodies for the formed assembly.", object_id)

    canonical_models = {
        str(model.get("id")): copy.deepcopy(model)
        for model in (canonical_design or {}).get("models", []) if isinstance(model, dict)
    }
    properties = assembly.setdefault("properties", {})
    from .mcad_component_models import retained_design_digest
    properties.setdefault("retained_design_digests", {})[design_id] = retained_design_digest(canonical_design or design)
    if canonical_models:
        properties.setdefault("retained_design_models", {}).setdefault(
            design_id, list(canonical_models.values()))
    occurrences = properties.setdefault("component_occurrences", [])
    source_components = (canonical_design or {}).get("components")
    if not isinstance(source_components, list):
        source_components = design.get("components", [])
    if source_components:
        properties.setdefault("retained_design_components", {}).setdefault(
            design_id, copy.deepcopy(source_components))
    for index, component in enumerate(source_components):
        component_id = _component_identity(component, index)
        occurrence_id = f"{object_id}/component:{component_id}"
        model_ids = [str(value) for value in component.get("model_ids", []) if isinstance(value, str)]
        occurrences.append({
            "id": occurrence_id,
            "name": str(component.get("name") or component.get("reference") or component.get("ref") or component_id),
            "board_occurrence_id": object_id,
            "design_id": design_id,
            "component_id": component_id,
            "placement": {key: copy.deepcopy(component[key]) for key in
                          ("position_mm", "position", "x", "y", "rotation_deg", "rotation", "side", "model_transform")
                          if key in component},
            "model_ids": model_ids,
        })
        issue("COMPONENT_GEOMETRY_REQUIRED",
              "Component placement and model references were retained, but a complete embedded STEP body is required for mechanical solid export.",
              occurrence_id)


def _assembly_designs(context, assembly):
    """Resolve the complete retained design set for every board occurrence."""
    if not assembly.boards:
        return {}
    project = context.get("project", {}) if isinstance(context.get("project"), dict) else {}
    retained = project.get("assembly_designs", context.get("assembly_designs"))
    active = context.get("design")
    raw_designs = retained.get("designs") if isinstance(retained, dict) else None
    if raw_designs is None:
        if not isinstance(active, dict):
            raise ValueError("AssemblyIR mechanical projection requires the retained assembly_designs set or its one active SpiDeR design.")
        active_v1, active_canonical = _design_views(active)
        active_id = str(active_canonical.get("design_id") or active_v1.get("design_id") or "")
        missing = sorted({board.design_id for board in assembly.boards} - {active_id})
        if missing:
            raise ValueError("AssemblyIR mechanical projection is missing retained SpiDeR designs: " + ", ".join(missing[:5]))
        return {active_id: (active_v1, active_canonical)}
    if retained.get("contract") != "spike/assembly-designs/v1" or not isinstance(raw_designs, list):
        raise ValueError("AssemblyIR mechanical projection requires spike/assembly-designs/v1.")
    designs = {}
    for raw in raw_designs:
        v1, canonical = _design_views(raw)
        design_id = str(canonical.get("design_id") or v1.get("design_id") or "")
        if not design_id or design_id in designs:
            raise ValueError("Retained assembly SpiDeR identities must be non-empty and unique.")
        designs[design_id] = (v1, canonical)
    missing = sorted({board.design_id for board in assembly.boards} - set(designs))
    if missing:
        raise ValueError("AssemblyIR mechanical projection is missing retained SpiDeR designs: " + ", ".join(missing[:5]))
    return designs


def assembly_from_context(context):
    parameters = context.get("parameters", {})
    if not isinstance(parameters.get("allow_partial", False), bool):
        raise ValueError("allow_partial must be a boolean.")
    if "assembly" in parameters:
        if parameters["assembly"].get("diagnostics") and not parameters.get("allow_partial", False):
            raise ValueError("Assembly contains projection diagnostics; review before setting allow_partial.")
        return validate_assembly(parameters["assembly"])
    project = context.get("project", {}) if isinstance(context.get("project"), dict) else {}
    assembly_raw = project.get("assembly_ir", context.get("assembly_ir"))
    if assembly_raw:
        from .spider_v2 import AssemblyIRV1
        assembly_ir = AssemblyIRV1.from_dict(assembly_raw)
        designs = _assembly_designs(context, assembly_ir)
        assembly = {"contract": CONTRACT, "id": "mcad:" + assembly_ir.assembly_id, "name": assembly_ir.name,
                    "units": "mm", "objects": [], "materials": [], "diagnostics": [],
                    "provenance": {"assembly_id": assembly_ir.assembly_id,
                        "design_ids": sorted({board.design_id for board in assembly_ir.boards}),
                        "board_occurrence_ids": [board.id for board in assembly_ir.boards],
                        "coordinate_convention": "AssemblyIR parent-relative right-handed millimetre frames; source board XY and physical stackup top-to-bottom in positive Z"}}
        objects, diagnostics = assembly["objects"], assembly["diagnostics"]
        def issue(code, message, source_id=""):
            diagnostics.append({"code": code, "message": message, "source_id": source_id})
        entities = [*assembly_ir.boards, *assembly_ir.parts]
        frame_owner = {entity.frame.frame_id: entity.id for entity in entities}
        root_frame_id = assembly_ir.frame.frame_id
        root_transform = tuple(assembly_ir.frame.transform)
        required_part_frames = set()
        for board_occurrence in assembly_ir.boards:
            parent_frame_id = board_occurrence.frame.parent_frame_id or root_frame_id
            while parent_frame_id != root_frame_id:
                if parent_frame_id in required_part_frames:
                    break
                required_part_frames.add(parent_frame_id)
                parent = next((part for part in assembly_ir.parts if part.frame.frame_id == parent_frame_id), None)
                if parent is None:
                    break
                parent_frame_id = parent.frame.parent_frame_id or root_frame_id
        for part in assembly_ir.parts:
            used_as_parent = part.frame.frame_id in required_part_frames
            if not used_as_parent:
                issue("ASSEMBLY_PART_GEOMETRY_REQUIRED",
                      "Assembly part has no embedded solid in the extension context; provide it as an explicit named object.", part.id)
                continue
            parent_id = frame_owner.get(part.frame.parent_frame_id) if part.frame.parent_frame_id != root_frame_id else None
            transform = tuple(part.frame.transform)
            if not parent_id:
                transform = multiply(root_transform, transform)
            row = {"id": part.id, "name": part.name or part.id, "kind": "assembly", "transform": list(transform),
                   "source": {"occurrence_id": part.id, "part_type": part.part_type, "model_id": part.model_id}}
            if parent_id:
                row["parent_id"] = parent_id
            objects.append(row)
            if part.part_type != "subassembly" or part.model_id:
                issue("ASSEMBLY_PART_GEOMETRY_REQUIRED",
                      "The hierarchy placement was retained, but the assembly part needs an embedded solid for physical export.", part.id)
        for board_occurrence in assembly_ir.boards:
            design, canonical = designs[board_occurrence.design_id]
            parent_id = frame_owner.get(board_occurrence.frame.parent_frame_id) if board_occurrence.frame.parent_frame_id != root_frame_id else None
            transform = tuple(board_occurrence.frame.transform)
            if not parent_id:
                transform = multiply(root_transform, transform)
            _append_board_projection(assembly, design, object_id=board_occurrence.id,
                name=board_occurrence.name or design.get("name") or board_occurrence.id,
                transform=transform, parent_id=parent_id, design_id=board_occurrence.design_id,
                canonical_design=canonical, issue=issue)
        for material in assembly_ir.to_dict()["materials"]:
            data = copy.deepcopy(material)
            material_id, material_name = data.pop("id"), data.pop("name")
            assembly["materials"].append({"id": material_id, "name": material_name or material_id, "properties": data})
        if assembly_ir.harnesses and not context.get("harness"):
            for harness in assembly_ir.harnesses:
                issue("HARNESS_GEOMETRY_REQUIRED",
                      "AssemblyIR retains harness connectivity but no routable solid; supply the harness document and explicit wire radii.", harness.id)
        design = {}
    else:
        design = copy.deepcopy(context.get("design") or {})
    if not assembly_raw and project.get("source_board") and project.get("source_format") == "kicad":
        import tempfile
        from pathlib import Path
        from .kicad_importer import import_kicad_design
        with tempfile.TemporaryDirectory(prefix="spike-mcad-source-") as folder:
            path = Path(folder) / "source.kicad_pcb"
            path.write_text(project["source_board"], encoding="utf-8")
            design = import_kicad_design(str(path)).to_dict()
    if not assembly_raw:
        if design:
            design, canonical = _design_views(design)
        ident = design.get("design_id") or hashlib.sha256(json.dumps(design, sort_keys=True).encode()).hexdigest()[:24]
        assembly = {"contract": CONTRACT, "id": "mcad:" + ident, "name": context.get("project", {}).get("name") or design.get("name") or "SPIKE assembly",
                    "units": "mm", "objects": [], "materials": [], "diagnostics": [],
                    "provenance": {"design_id": ident, "source_format": design.get("source_format"), "coordinate_convention": "source XY, physical stackup top-to-bottom in positive Z"}}
        objects, diagnostics = assembly["objects"], assembly["diagnostics"]
        def issue(code, message, source_id=""):
            diagnostics.append({"code": code, "message": message, "source_id": source_id})
        if design:
            if parameters.get("board_rings"):
                design.setdefault("metadata", {})["board_outline_rings"] = copy.deepcopy(parameters["board_rings"])
            _append_board_projection(assembly, design, object_id="board", name=design.get("name") or "Board",
                transform=IDENTITY, design_id=ident, canonical_design=canonical, legacy_ids=True, issue=issue)
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
    from .mcad_component_models import bind_component_models
    bind_component_models(assembly, parameters.get("component_models"))
    if diagnostics and not parameters.get("allow_partial", False):
        raise ValueError("MCAD projection is incomplete: " + "; ".join(sorted({i["code"] for i in diagnostics})) + ". Review with mcad-plan; explicit allow_partial exports only the stated geometry.")
    return validate_assembly(assembly)
