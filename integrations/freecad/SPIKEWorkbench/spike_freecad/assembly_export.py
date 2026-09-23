"""Export placed FreeCAD parts as portable SPIKE assembly exchange archives."""
from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path

import FreeCAD as App


def export_assembly(document, objects, destination):
    """Export selected roots (including groups) without modifying source objects.

    Shape placements are separated from local STEP geometry. Optional
    SPIKEBoardSource string properties bind a placed PCB to its electrical file.
    """
    target = Path(destination)
    if target.suffix.lower() != ".spikeassembly":
        target = target.with_suffix(".spikeassembly")
    selected = list(objects)
    if not selected:
        raise ValueError("Select the assembly roots or parts to export.")
    # Selecting a parent and its descendants must not duplicate occurrences.
    descendants = set()
    def mark_children(obj, visited):
        if obj.Name in visited: raise ValueError("Cyclic FreeCAD group hierarchy.")
        for child in getattr(obj, "Group", []):
            descendants.add(child.Name)
            mark_children(child, visited | {obj.Name})
    for obj in selected: mark_children(obj, set())
    roots = [obj for obj in selected if obj.Name not in descendants]
    manifest = {"contract": "spike/assembly-exchange/v1", "name": document.Label,
                "source_cad": "FreeCAD " + ".".join(App.Version()[:3]), "units": "mm", "occurrences": []}
    seen, assets = set(), {}
    total_bytes = 0
    def matrix(placement):
        value = placement.toMatrix()
        return [getattr(value, f"A{r}{c}") for r in range(1, 5) for c in range(1, 5)]
    with tempfile.TemporaryDirectory(prefix="spike-freecad-assembly-") as directory:
        root = Path(directory)
        def visit(obj, parent_id=None, parent_world=None):
            nonlocal total_bytes
            if obj.Name in seen:
                raise ValueError(f"Object {obj.Name} occurs under multiple selected parents; export separate links instead.")
            seen.add(obj.Name)
            if len(seen) > 120: raise ValueError("SPIKE assembly exchange supports at most 120 occurrences.")
            if getattr(obj, "Scale", 1.0) != 1.0:
                raise ValueError(f"Bake scale on {obj.Label} before exporting.")
            global_placement = obj.getGlobalPlacement() if hasattr(obj, "getGlobalPlacement") else App.Placement()
            board_source = str(getattr(obj, "SPIKEBoardSource", "") or "")
            shape = getattr(obj, "Shape", None)
            if obj.TypeId in {"App::Part", "App::DocumentObjectGroup", "App::DocumentObjectGroupPython"}:
                shape = None
            shape = shape.copy() if shape is not None and not shape.isNull() else None
            if shape is not None and not board_source:
                # Feature.Shape includes the local object placement already.
                global_placement = global_placement.multiply(obj.Placement.inverse()).multiply(shape.Placement)
                shape.Placement = App.Placement()
            relative = parent_world.inverse().multiply(global_placement) if parent_world else global_placement
            occurrence = {"id": obj.Name, "name": obj.Label, "transform": matrix(relative)}
            if parent_id: occurrence["parent_id"] = parent_id
            if board_source:
                source = Path(board_source)
                if source.suffix.lower() not in {".kicad_pcb", ".ipc2581"} or not source.is_file():
                    raise ValueError(f"{obj.Label}: SPIKEBoardSource must name a KiCad or IPC-2581 file.")
                if source.stat().st_size > 256 * 1024**2: raise ValueError("Board source exceeds 256 MiB.")
                asset = f"assets/{obj.Name}{source.suffix.lower()}"
                assets[asset] = source.read_bytes()
                occurrence.update(kind="board", asset=asset)
            elif shape is not None:
                asset = f"assets/{obj.Name}.step"
                exported = root / f"{obj.Name}.step"
                shape.exportStep(str(exported))
                if exported.stat().st_size > 256 * 1024**2: raise ValueError("STEP part exceeds 256 MiB.")
                assets[asset] = exported.read_bytes()
                occurrence.update(kind="part", part_type="enclosure", asset=asset)
            else:
                children = list(getattr(obj, "Group", []))
                if not children: raise ValueError(f"{obj.Label} has no exportable shape or children.")
                occurrence["kind"] = "group"
            manifest["occurrences"].append(occurrence)
            if occurrence["kind"] == "group":
                for child in children: visit(child, obj.Name, global_placement)
            else:
                total_bytes += len(assets[asset])
                if total_bytes > 512 * 1024**2: raise ValueError("Assembly assets exceed 512 MiB.")
        for obj in roots: visit(obj)
        if not manifest["occurrences"]: raise ValueError("No assembly occurrences selected.")
        # Store instead of deflate so very repetitive CAD files cannot trip the
        # importer's archive-bomb compression-ratio ceiling.
        temporary = target.with_name(target.name + ".tmp")
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("assembly.json", json.dumps(manifest, indent=2))
                for name, payload in assets.items(): archive.writestr(name, payload)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return {"path": str(target), "occurrences": len(manifest["occurrences"]), "assets": len(assets)}
