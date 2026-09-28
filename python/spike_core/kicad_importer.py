"""KiCad PCB adapter for the EDA-neutral SPIKE importer registry."""

from __future__ import annotations

import os
import re
import sys
import hashlib
import json
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from .contracts import DesignIR, ValidationIssue


def _kicad_model_roots() -> list[Path]:
    roots = []
    for variable in ("KICAD10_3DMODEL_DIR", "KICAD9_3DMODEL_DIR", "KICAD8_3DMODEL_DIR"):
        value = os.environ.get(variable, "")
        if value:
            roots.append(Path(value))
    if sys.platform == "win32":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        for version in ("10.0", "9.0", "8.0"):
            roots.append(program_files / "KiCad" / version / "share" / "kicad" / "3dmodels")
    return list(dict.fromkeys(root for root in roots if root.is_dir()))


def _resolve_model_reference(reference: str, project_directory: str | Path | None = None) -> str:
    if not reference:
        return ""
    resolved = reference
    for variable in re.findall(r"\$\{([^}]+)\}", resolved):
        value = os.environ.get(variable, "")
        if variable == "KIPRJMOD" and project_directory:
            value = str(Path(project_directory))
        if value:
            resolved = resolved.replace("${" + variable + "}", value)
    candidates = []
    if "${" not in resolved:
        candidates.append(Path(resolved))
    if reference.startswith("${KICAD") and "}" in reference:
        suffix = reference.split("}", 1)[1].lstrip("/\\")
        candidates.extend(root / suffix for root in _kicad_model_roots())
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    return ""


def import_kicad_design(path: str) -> DesignIR:
    """Normalize a KiCad PCB file without leaking parser objects downstream."""

    from python.core.board_parser import KicadParser

    parser_log = StringIO()
    with redirect_stdout(parser_log):
        parser = KicadParser(path)
    issues = []
    if not parser.layers:
        issues.append(ValidationIssue(
            code="IMPORT_NO_LAYERS",
            severity="error",
            message="No board layers were extracted.",
            suggestion="Verify the file is a supported KiCad PCB file.",
        ))
    if not parser.stackup:
        issues.append(ValidationIssue(
            code="STACKUP_MISSING",
            severity="warning",
            message="No explicit stackup was extracted; AC and HF results are limited.",
            suggestion="Define copper, dielectric, thickness, and material properties.",
        ))
    ordered_layer_items = list(parser.layers.items())
    copper_layer_names = [
        str(layer_info.get("name", "")).strip('"')
        for _layer_id, layer_info in ordered_layer_items
        if str(layer_info.get("name", "")).strip('"').endswith(".Cu")
        or str(layer_info.get("type", "")).lower() in {"signal", "power", "mixed", "jumper"}
    ]
    stackup_copper_names = {
        str(layer.get("name", "")).strip('"')
        for layer in parser.stackup
        if str(layer.get("name", "")).strip('"').endswith(".Cu")
        or str(layer.get("type", "")).lower() == "copper"
    }
    missing_stackup_layers = [name for name in copper_layer_names if name not in stackup_copper_names]
    if parser.stackup and missing_stackup_layers:
        issues.append(ValidationIssue(
            code="STACKUP_COPPER_LAYERS_MISSING",
            severity="warning",
            message=(
                f"The KiCad layer table contains {len(copper_layer_names)} copper layers, "
                f"but {len(missing_stackup_layers)} have no stackup row: {', '.join(missing_stackup_layers)}."
            ),
            suggestion=(
                "Add thickness and material data for the listed layers. "
                "Their geometry remains imported and available for DC analysis."
            ),
        ))
    if not parser.nets:
        issues.append(ValidationIssue(
            code="NETS_MISSING",
            severity="warning",
            message="No named nets were extracted.",
            suggestion="Confirm the board has been saved with net connectivity.",
        ))
    if parser.diagnostics:
        issues.append(ValidationIssue(
            code="IMPORT_OBJECT_DIAGNOSTICS",
            severity="warning",
            message=f"The KiCad importer recorded {len(parser.diagnostics)} recoverable object diagnostics.",
            suggestion="Review importer diagnostics before relying on geometry completeness.",
        ))

    components = []
    footprints = {item.get("reference"): item for item in getattr(parser, "footprints", [])}
    grouped_components = {}
    for pad in parser.pads:
        ref = pad.get("component") or "U?"
        item = grouped_components.setdefault(ref, {"reference": ref, "pad_count": 0, "nets": set(), "positions": []})
        item["pad_count"] += 1
        if pad.get("net_name"):
            item["nets"].add(pad["net_name"])
        if pad.get("at"):
            item["positions"].append(pad["at"])
    for item in grouped_components.values():
        positions = item.pop("positions")
        item["nets"] = sorted(item["nets"])
        if positions:
            item["at"] = [
                sum(point[0] for point in positions) / len(positions),
                sum(point[1] for point in positions) / len(positions),
            ]
        components.append(item)
    for footprint in footprints.values():
        match = next((item for item in components if item["reference"] == footprint.get("reference")), None)
        if match is None:
            match = {"reference": footprint.get("reference", "U?"), "pad_count": 0, "nets": []}
            components.append(match)
        match["library"] = footprint.get("library", "")
        match["value"] = footprint.get("value", "")
        match["properties"] = dict(footprint.get("properties", {}))
        match["model_path"] = footprint.get("model_path", "")
        match["model_resolved"] = _resolve_model_reference(
            footprint.get("model_path", ""), Path(path).resolve().parent
        )
        match["layer"] = footprint.get("layer", "")
        match.setdefault("at", list(footprint.get("at", (0, 0))))
        match["rotation"] = footprint.get("rotation", 0)
        for key in (
            "zone_connection_override", "zone_connection_declared",
            "thermal_gap_override_mm", "thermal_spoke_width_override_mm",
            "thermal_settings_valid",
        ):
            if key in footprint:
                match[key] = footprint[key]
        if footprint.get("id"):
            match["id"] = footprint["id"]
            match["source_id"] = footprint["id"]

    source_path = Path(path).resolve()
    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    # Some published libraries repeat a pad UUID for physically distinct pads.
    # Keep all occurrences and retain the original identity as provenance.
    uuid_counts = Counter(p.get("uuid") for p in parser.pads if p.get("uuid"))
    occurrences = Counter()
    for pad in parser.pads:
        native = pad.get("uuid")
        if native and uuid_counts[native] > 1:
            fingerprint = hashlib.sha256(json.dumps(pad, sort_keys=True).encode()).hexdigest()[:20]
            key = (native, fingerprint)
            occurrences[key] += 1
            pad["source_native_uuid"] = native
            pad["source_id"] = f"{native}:occurrence:{fingerprint}:{occurrences[key]}"
    if occurrences:
        issues.append(ValidationIssue("KICAD_DUPLICATE_PAD_UUID", "warning",
            "Repeated source pad UUIDs were disambiguated by occurrence; original UUIDs remain in source_native_uuid."))
    # Legacy boards can contain identical anonymous objects. A content hash
    # describes their geometry, but cannot identify separate occurrences.
    for kind, rows in (("track", parser.tracks), ("pad", parser.pads), ("via", parser.vias), ("zone", parser.zones)):
        anonymous = [(row, hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest())
                     for row in rows if not any(row.get(k) for k in ("source_id", "uuid", "id"))]
        counts = Counter(fingerprint for _, fingerprint in anonymous)
        ordinals = Counter()
        for row, fingerprint in anonymous:
            if counts[fingerprint] > 1:
                ordinals[fingerprint] += 1
                row["source_id"] = f"anonymous-{kind}:{fingerprint}:occurrence:{ordinals[fingerprint]}"
        if ordinals:
            issues.append(ValidationIssue("KICAD_DUPLICATE_ANONYMOUS_OBJECT", "warning",
                f"Identical anonymous {kind} records were retained with separate occurrence identities."))
    board_bbox = parser.board_bbox
    board_bounds_mm = [
        float(board_bbox["min_x"]), float(board_bbox["min_y"]),
        float(board_bbox["max_x"]), float(board_bbox["max_y"]),
    ]
    return DesignIR(
        design_id=f"kicad-{source_digest[:24]}",
        name=Path(path).stem,
        source_format="kicad",
        source_path=str(source_path),
        layers=[
            {"id": layer_id, **{**layer_info, "name": str(layer_info.get("name", "")).strip('"')}}
            for layer_id, layer_info in ordered_layer_items
        ],
        nets=[{"id": net_id, "name": net_name} for net_id, net_name in parser.nets.items()],
        tracks=list(parser.tracks),
        vias=list(parser.vias),
        pads=list(parser.pads),
        zones=list(parser.zones),
        components=components,
        stackup=list(parser.stackup),
        technology=str(getattr(parser, "technology", "rigid")),
        regions=list(getattr(parser, "regions", [])),
        bends=list(getattr(parser, "bends", [])),
        issues=issues,
        metadata={
            "board_outline_drawings": [dict(d) for d in parser.drawings if d.get("layer") == "Edge.Cuts"],
            "board_bbox": board_bbox,
            "board_bounds_mm": board_bounds_mm,
            "parser": "KicadParser",
            "parser_revision": "kicad-zone-fill-v2",
            "parser_log": parser_log.getvalue().splitlines(),
            "parser_diagnostics": list(parser.diagnostics),
            "footprint_models": sum(bool(item.get("model_path")) for item in components),
            "rigid_flex_region_count": len(getattr(parser, "regions", [])),
            "bend_count": len(getattr(parser, "bends", [])),
            "copper_layer_count": len(copper_layer_names),
            "stackup_missing_copper_layers": missing_stackup_layers,
            "source_sha256": source_digest,
        },
    )
