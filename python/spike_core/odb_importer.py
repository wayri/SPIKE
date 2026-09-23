"""ODB++Design adapter. Geometry and connectivity share the native DesignIR path.

The parser keeps vendor attributes and source records, and never guesses a
padstack, missing dielectric, negative plane or 3D assignment from a filename.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import zlib

from .contracts import DesignIR, ValidationIssue
from .importers import ImportPolicy
from .odb_features import Attributes, number, parse_features, records, tokens, units
from .source_package import SourcePackage, safe_member_name, source_identity


def decode_odb_json_archive(table, contract):
    """Decode and authenticate a self-contained compact ODB JSON list."""
    if (not isinstance(table, dict) or table.get("contract") != contract
            or table.get("encoding") != "zlib+base64+json"):
        raise ValueError("Unsupported ODB JSON archive contract or encoding.")
    try:
        raw = zlib.decompress(base64.b64decode(table["data"], validate=True))
    except (KeyError, ValueError, zlib.error) as exc:
        raise ValueError("Invalid compressed ODB source table.") from exc
    if hashlib.sha256(raw).hexdigest() != table.get("sha256"):
        raise ValueError("ODB JSON archive digest mismatch.")
    expected_bytes = table.get("bytes", table.get("uncompressed_size_bytes"))
    if expected_bytes is not None and len(raw) != expected_bytes:
        raise ValueError("ODB JSON archive byte count mismatch.")
    rows = json.loads(raw)
    if not isinstance(rows, list) or len(rows) != table.get("count"):
        raise ValueError("ODB JSON archive count mismatch.")
    return rows


def decode_odb_source_table(table):
    """Decode and authenticate a compact ODB provenance table."""
    return decode_odb_json_archive(table, "spike/odb-source-table/v1")


def canonical_layer_name(value: str) -> str:
    """Preserve ODB matrix identity while normalizing KiCad copper suffixes."""
    value = value.strip()
    if value.upper().endswith(".CU"):
        return value[:-3] + ".Cu"
    return value


def matrix_blocks(text):
    blocks = []
    block = None
    for _, raw in records(text):
        if raw.endswith("{"):
            if block is not None:
                raise ValueError("Nested ODB++ matrix blocks are invalid.")
            block = {"block": raw[:-1].strip()}
        elif raw == "}":
            if block is None:
                raise ValueError("Unmatched ODB++ matrix brace.")
            blocks.append(block)
            block = None
        elif block is not None:
            key, sep, value = raw.partition("=")
            if not sep or key.strip() in block:
                raise ValueError("Invalid/duplicate ODB++ matrix field.")
            block[key.strip()] = value.strip()
    if block is not None:
        raise ValueError("Unterminated ODB++ matrix block.")
    return blocks


def parse_eda(text, fallback="INCH"):
    factor, _ = units(text, fallback)
    attrs = Attributes()
    nets, packages, subnets, feature_nets = [], [], [], {}
    layers = []
    current = None
    subnet = None
    for line, raw in records(text):
        if attrs.consume(raw):
            continue
        t = tokens(raw)
        if t[0] == "LYR":
            if layers:
                raise ValueError("Duplicate ODB++ EDA layer list.")
            layers = [value.lower() for value in t[1:]]
        elif t[0] == "NET":
            current = {"id": len(nets) + 1, "name": t[1], "odb_source": attrs.source(raw), "properties": []}
            nets.append(current)
            subnet = None
        elif t[0] == "SNT":
            if current not in nets:
                raise ValueError("Subnet without an electrical net.")
            subnet = {"net_id": current["id"], "type": t[1], "fields": t[2:], "features": []}
            subnets.append(subnet)
        elif t[0] == "FID":
            if subnet is None or len(t) != 4 or t[1] not in {"C", "L", "H"}:
                raise ValueError(f"Invalid ODB++ feature-net reference at line {line}.")
            layer_index, feature_index = int(t[2]), int(t[3])
            if not 0 <= layer_index < len(layers) or feature_index < 0:
                raise ValueError("ODB++ feature-net index outside layer table.")
            key = (layers[layer_index], feature_index)
            if key in feature_nets:
                raise ValueError(f"Duplicate ODB++ feature-net assignment: {key}")
            feature_nets[key] = subnet
            subnet["features"].append({"layer": key[0], "index": key[1], "type": t[1]})
        elif t[0] == "PKG":
            current = {"name": t[1], "odb_source": attrs.source(raw), "records": [], "properties": []}
            if len(t) >= 7:
                current["bounds_mm"] = [number(v) * factor for v in t[3:7]]
            packages.append(current)
            subnet = None
        elif t[0] == "PRP" and current is not None:
            current["properties"].append({"name": t[1], "values": t[2:], "record": raw})
        elif current is not None:
            current.setdefault("records", []).append(raw)
    return nets, packages, subnets, feature_nets


def parse_components(text, layer, fallback, packages):
    factor, _ = units(text, fallback)
    attrs = Attributes()
    output = []
    current = None
    for _, raw in records(text):
        if attrs.consume(raw):
            continue
        t = tokens(raw)
        if t[0] == "CMP":
            if len(t) != 8 or t[5] not in {"N", "M"}:
                raise ValueError("Malformed ODB++ component placement.")
            pkg = int(t[1])
            if not 0 <= pkg < len(packages):
                raise ValueError("Component references an unknown EDA package.")
            bottom = layer.endswith("bot")
            package = packages[pkg]
            current = {"id": f"odb:{layer}:component:{len(output)}", "reference": t[6],
                       "value": t[7], "part_name": t[7], "footprint": packages[pkg]["name"],
                       "at": [number(v) * factor for v in t[2:4]], "rotation": -number(t[4]),
                       "layer": "B.Cu" if bottom else "F.Cu", "side": "bottom" if bottom else "top",
                       "mirrored": t[5] == "M", "properties": [], "pins": [], "bom_records": [],
                       "odb_source": attrs.source(raw),
                       # Packages can contain thousands of records and are shared by
                       # every occurrence. Embedding the full package here made the
                       # JSON snapshot grow as package_size * component_count. Keep a
                       # stable index plus the small fields needed by consumers; the
                       # exact package remains once in metadata and in the digest-bound
                       # source package.
                       "odb_package_ref": {"index": pkg, "name": package["name"],
                                           **({"bounds_mm": package["bounds_mm"]} if "bounds_mm" in package else {})}}
            if current["odb_source"]["uid"]:
                current["id"] = f"odb:{layer}:component:uid:{current['odb_source']['uid']}"
            output.append(current)
        elif t[0] == "PRP" and current is not None:
            current["properties"].append({"name": t[1], "values": t[2:], "record": raw})
            if t[1].upper() == "VALUE" and len(t) >= 3:
                current["value"] = t[2]
        elif t[0] == "TOP" and current is not None:
            if len(t) != 9 or t[5] not in {"N", "M"}:
                raise ValueError("Malformed ODB++ toeprint record.")
            current["pins"].append({"index": int(t[1]), "at": [number(v) * factor for v in t[2:4]],
                                    "rotation": -number(t[4]), "mirrored": t[5] == "M",
                                    "net_index": int(t[6]), "subnet_index": int(t[7]), "number": t[8], "record": raw})
        elif current is not None:
            current["bom_records"].append(raw)
    return output


def import_odb_design(path: str, *, step: str = "", policy: ImportPolicy | None = None) -> DesignIR:
    policy = policy or ImportPolicy()
    digest, size = source_identity(Path(path), policy)
    design = DesignIR(design_id=f"odb-{digest[:24]}", source_format="odb++", source_path=str(Path(path).resolve()))
    retained = []
    issue_counts = {}
    issue_severity_counts = {}
    issue_sample_counts = {}

    def issue(code, message, source_id="", source=None, severity="error"):
        issue_counts[code] = issue_counts.get(code, 0) + 1
        severity_key = f"{code}:{severity}"
        issue_severity_counts[severity_key] = issue_severity_counts.get(severity_key, 0) + 1
        issue_sample_counts[severity_key] = issue_sample_counts.get(severity_key, 0) + 1
        # Large real boards may contain thousands of repeated unsupported
        # artwork records. The source package remains digest-bound and the
        # exact count is retained, while diagnostics keep a representative
        # bounded sample instead of making an otherwise readable job fail.
        if issue_sample_counts[severity_key] > 100:
            return
        if len(design.issues) >= 10_000:
            raise ValueError("ODB++ diagnostic limit exceeded.")
        design.issues.append(ValidationIssue(code, severity, message, source_id))
        if source is not None:
            retained.append({"id": source_id, "code": code, "source": source})

    with SourcePackage(path, policy) as job:
        root = job.root_for("matrix/matrix")
        blocks = matrix_blocks(job.text(root + "matrix/matrix", required=True))
        design.metadata["odb_matrix"] = blocks
        blocks = [dict(b, **{k: b[k].lower() for k in ("NAME", "START_NAME", "END_NAME") if k in b}, _source=dict(b)) for b in blocks]
        steps = [b["NAME"] for b in blocks if b["block"] == "STEP" and "NAME" in b]
        if len(set(steps)) != len(steps):
            raise ValueError("Duplicate ODB++ step names.")
        step = step.lower()
        if not step:
            if len(steps) != 1:
                raise ValueError(f"ODB++ job has multiple/no steps; select a step explicitly: {', '.join(steps)}")
            step = steps[0]
        if step not in steps or "/" in safe_member_name(step):
            raise ValueError(f"Unknown or unsafe ODB++ step: {step}")
        prefix = root + "steps/" + step + "/"
        design.name = step
        info = job.text(root + "misc/info")
        _, default_units = units(info)
        layer_blocks = sorted([b for b in blocks if b["block"] == "LAYER"], key=lambda b: int(b["ROW"]))
        names = [b["NAME"] for b in layer_blocks]
        canonical_names = [canonical_layer_name(b.get("_source", {}).get("NAME", b["NAME"])) for b in layer_blocks]
        canonical_by_name = dict(zip(names, canonical_names))
        if (len(set(names)) != len(names) or len(set(canonical_names)) != len(canonical_names)
                or len({b["ROW"] for b in layer_blocks}) != len(layer_blocks)):
            raise ValueError("Duplicate ODB++ layer names or rows.")
        for index, (block, canonical_name) in enumerate(zip(layer_blocks, canonical_names)):
            name = block["NAME"]
            if "/" in safe_member_name(name):
                raise ValueError("Unsafe ODB++ layer name.")
            design.layers.append({"id": canonical_name, "name": canonical_name, "order": index, "type": block.get("TYPE", "DOCUMENT").lower(),
                                  "odb_source": block.get("_source", block)})
        eda = job.text(prefix + "eda/data")
        nets, packages, subnets, feature_nets = parse_eda(eda, default_units)
        design.nets = [n for n in nets if n["name"] != "$NONE$"]
        net_ids = {n["id"] for n in design.nets}
        components_by_side = {}
        all_features = {}
        electrical_layer_names = {
            block["NAME"] for block in layer_blocks
            if block.get("TYPE", "DOCUMENT").upper() in {"SIGNAL", "POWER_GROUND", "MIXED", "DRILL"}
        }
        for block in layer_blocks:
            job.check_time()
            layer = block["NAME"]
            kind = block.get("TYPE", "DOCUMENT").upper()
            layer_prefix = prefix + "layers/" + layer + "/"
            component_text = job.text(layer_prefix + "components")
            if component_text:
                components = parse_components(component_text, layer, default_units, packages)
                components_by_side["B" if layer.endswith("bot") else "T"] = components
                design.components.extend(components)
            feature_text = job.text(layer_prefix + "features")
            if not feature_text:
                if kind in {"SIGNAL", "POWER_GROUND", "MIXED"}:
                    issue("ODB_COPPER_MISSING", f"Copper layer {layer} has no features file.", layer)
                continue
            copper = kind in {"SIGNAL", "POWER_GROUND", "MIXED"}
            if block.get("POLARITY", "POSITIVE") != "POSITIVE":
                issue("ODB_LAYER_POLARITY_UNSUPPORTED", f"Negative layer {layer} needs plane compositing.", layer,
                      {"matrix": block, "features": feature_text}, "error" if copper else "warning")
                continue
            callback = lambda c, m, s, r: issue(c, m, s, r, "error" if copper or kind == "DRILL" else "warning")
            features = parse_features(feature_text, layer, default_units, callback)
            for row in features:
                key = (layer, row["odb_source"]["feature_index"])
                all_features[key] = row
                row["layer"] = canonical_by_name[layer]
                row["layers"] = [canonical_by_name[layer]]
                subnet = feature_nets.get(key)
                row["net_id"] = subnet["net_id"] if subnet and subnet["net_id"] in net_ids else 0
                if copper:
                    if row["kind"] == "track": design.tracks.append(row)
                    elif row["kind"] == "arc": design.metadata.setdefault("arcs", []).append(row)
                    elif row["kind"] == "pad": design.pads.append(row)
                    elif row["kind"] == "zone": design.zones.append(row)
                    if not subnet:
                        issue("ODB_CONNECTIVITY_MISSING", "Copper feature has no EDA net assignment.", row["id"])
                elif kind == "DRILL":
                    if row["kind"] != "pad" or row["shape"] not in {"circle", "oval"}:
                        issue("ODB_DRILL_UNSUPPORTED", "Only circular and oval drill hits are normalized.", row["id"], row)
                        continue
                    span = [canonical_by_name.get(block.get("START_NAME", ""), ""),
                            canonical_by_name.get(block.get("END_NAME", ""), "")]
                    if any(n not in canonical_names for n in span):
                        issue("ODB_DRILL_SPAN_MISSING", "Drill layer has unresolved start/end layers.", row["id"])
                    drill_shape = "slot" if row["shape"] == "oval" else "circle"
                    design.metadata.setdefault("manufacturing_drills", []).append({
                        "id": row["id"], "at": row["at"], "shape": drill_shape,
                        "diameter_mm": row["size"][0] if drill_shape == "circle" else None,
                        "size_mm": row["size"] if drill_shape == "slot" else None,
                        "rotation_deg": row.get("rotation") if drill_shape == "slot" else None,
                        "source_layer_id": canonical_by_name[layer], "net_id": row["net_id"] or "",
                        "span_layer_ids": span if all(n in canonical_names for n in span) else [],
                        "span_provenance": "explicit" if all(n in names for n in span) else "unresolved", "plating_status": "unknown", "plated": None,
                        "owner_kind": "unresolved", "odb_source": row["odb_source"]})
                else:
                    design.metadata.setdefault("odb_artwork", []).append(row)
        if len({c["reference"] for c in design.components}) != len(design.components):
            raise ValueError("Duplicate ODB++ component references.")
        for subnet in subnets:
            features = [all_features.get((f["layer"], f["index"])) for f in subnet["features"]]
            # EDA toeprints commonly reference the same land on copper, mask,
            # and paste. Unsupported decorative/manufacturing artwork must not
            # invalidate otherwise complete electrical connectivity.
            if any(feature is None and reference["layer"] in electrical_layer_names
                   for reference, feature in zip(subnet["features"], features)):
                issue("ODB_FEATURE_REFERENCE_UNRESOLVED", "EDA subnet refers to absent or unsupported geometry.", source=subnet)
            if subnet["type"] == "TOP":
                try:
                    side, component_index, toe_index = subnet["fields"]
                    if int(component_index) < 0 or int(toe_index) < 0: raise IndexError()
                    component = components_by_side[side][int(component_index)]
                    pin = component["pins"][int(toe_index)]
                    if pin["net_index"] + 1 != subnet["net_id"]:
                        raise ValueError("Toeprint net disagrees with EDA subnet.")
                    for row in features:
                        if row and row["kind"] == "pad":
                            row.update(component=component["reference"], number=pin["number"])
                    lands = [row for row in features if row in design.pads and row.get("kind") == "pad"]
                    holes = [drill for drill in design.metadata.get("manufacturing_drills", [])
                             if any(row and row["id"] == drill["id"] for row in features)]
                    for hole in holes:
                        matching_lands = [land for land in lands if land["at"] == hole["at"]]
                        if matching_lands:
                            owner = min(matching_lands, key=lambda land: canonical_names.index(land["layer"]))
                            hole.update(owner_kind="pad", owner_id=owner["id"], owner_match="exact_source",
                                        net_id=owner.get("net_id") or "", plating_status="plated",
                                        plated=True, span_provenance="matched_owner")
                except (ValueError, IndexError, KeyError) as exc:
                    issue("ODB_TOEPRINT_UNRESOLVED", f"Invalid component pin linkage: {exc}", source=subnet)
            elif subnet["type"] == "VIA":
                # Retain exact per-layer lands, but require an explicit drill hit
                # before declaring a vertical conductive connection.
                lands = [f for f in features if f and f in design.pads]
                holes = [d for d in design.metadata.get("manufacturing_drills", [])
                         if any(f and f["id"] == d["id"] for f in features)]
                if len(holes) == 1 and len(lands) >= 2 and all(p["shape"] == "circle" and p["at"] == holes[0]["at"] for p in lands):
                    hole = holes[0]
                    land_names = [p["layer"] for p in sorted(lands, key=lambda p: canonical_names.index(p["layer"]))]
                    if hole["span_layer_ids"] != [land_names[0], land_names[-1]]:
                        issue("ODB_VIA_SPAN_UNRESOLVED", "Via land span differs from drill span.", source=subnet)
                        continue
                    if len({tuple(p["size"]) for p in lands}) != 1 or hole["diameter_mm"] >= lands[0]["size"][0]:
                        issue("ODB_VIA_LANDS_UNRESOLVED", "Variable or invalid via lands need padstack normalization.", source=subnet)
                        continue
                    via = {"id": "odb:via:" + hole["id"], "at": hole["at"], "diameter": lands[0]["size"][0],
                           "drill": hole["diameter_mm"], "net_id": hole["net_id"], "layers": land_names,
                           "start_layer": land_names[0], "end_layer": land_names[-1], "type": "through",
                           "odb_source": subnet}
                    design.vias.append(via)
                    hole.update(owner_kind="via", owner_id=via["id"], plating_status="via", plated=True, owner_match="exact_source")
                    for land in lands: design.pads.remove(land)
                else:
                    issue("ODB_VIA_UNRESOLVED", "Via requires matching circular lands and a unique drill hit.", source=subnet)
        for drill in design.metadata.get("manufacturing_drills", []):
            if drill["owner_kind"] == "unresolved":
                issue("ODB_DRILL_OWNER_UNRESOLVED", "Drill geometry is retained but its plating and copper ownership are unresolved.",
                      drill["id"], drill)
        profile_text = job.text(prefix + "profile")
        if profile_text:
            # Profile is a single contour, without S/SE wrappers.
            from .odb_features import contours
            factor, _ = units(profile_text, default_units)
            profile_lines = [r for _, r in records(profile_text) if not r.startswith(("UNITS=", "ID=", "U ", "F "))]
            try:
                rings = contours(profile_lines, factor)
                design.metadata["board_outline_rings"] = rings
                points = [r["start_mm"] for r in rings] + [s["end_mm"] for r in rings for s in r["segments"]]
                # Arc extents are conservatively bounded by their full circle.
                import math
                for r in rings:
                    start = r["start_mm"]
                    for s in r["segments"]:
                        if s["kind"] == "arc":
                            x, y = s["center_mm"]; radius = math.dist(start, [x, y])
                            points.extend([[x-radius, y-radius], [x+radius, y+radius]])
                        start = s["end_mm"]
                design.metadata["board_bounds_mm"] = [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]
            except ValueError as exc:
                issue("ODB_PROFILE_UNSUPPORTED", str(exc), source={"profile": profile_text})
        else:
            issue("ODB_PROFILE_MISSING", "Board profile is missing.")
        stephdr = job.text(prefix + "stephdr")
        if "STEP-REPEAT" in stephdr:
            issue("ODB_STEP_REPEAT_UNSUPPORTED", "Panel step-repeat instances require expansion; select the board step.", source={"stephdr": stephdr})
        stackup = job.text(root + "matrix/stackup")
        if stackup:
            from .odb_stackup import parse_stackup
            design.stackup = parse_stackup(stackup, issue)
            design.metadata["odb_stackup_xml"] = stackup
        supplement = job.text(prefix + "spike/board.json")
        if supplement:
            apply_supplement(design, json.loads(supplement), job, root)
        copper_order = [l["name"] for l in design.layers if l["type"] in {"signal", "power_ground", "mixed"}]
        physical_copper = [s["name"] for s in design.stackup if s.get("type") in {"copper", "signal", "conductor"}]
        if design.stackup and physical_copper != copper_order:
            issue("ODB_STACKUP_UNRESOLVED", "Physical copper order does not match the complete matrix copper order.", severity="warning")
        if any(a["name"] in physical_copper and b["name"] in physical_copper for a, b in zip(design.stackup, design.stackup[1:])):
            issue("ODB_STACKUP_UNRESOLVED", "Adjacent copper layers have no resolved dielectric separation.", severity="warning")
        if not design.stackup:
            issue("ODB_STACKUP_MISSING", "Physical stackup requires resolved thickness/material data; matrix order is retained.", severity="warning")
        if not eda:
            issue("ODB_EDA_MISSING", "EDA data is missing; copper connectivity is unavailable.")
        if not design.metadata.get("model_references"):
            issue("ODB_MODELS_MISSING", "No explicit component 3D model assignments were supplied.", severity="warning")
        total_error_count = sum(count for key, count in issue_severity_counts.items() if key.endswith(":error"))
        design.metadata.update(source_sha256=digest, source_size_bytes=size, odb_steps=steps, odb_selected_step=step,
                               odb_info=info, odb_packages=packages, odb_subnets=subnets, odb_retained=retained, odb_issue_counts=issue_counts,
                               odb_issue_severity_counts=issue_severity_counts,
                               odb_members=[{"name": n, "size_bytes": job.sizes[n]} for n in sorted(job.members)],
                               geometry_normalized=total_error_count == 0,
                               geometry_solver_ready=total_error_count == 0,
                               physical_units_resolved=True, parser="ODB++Design", parser_revision="odb-v1",
                               stackup_physical_complete=bool(design.stackup) and not any(i.code == "ODB_STACKUP_UNRESOLVED" for i in design.issues),
                               stackup_missing_copper_layers=[l["name"] for l in design.layers if l["type"] in {"signal", "power_ground", "mixed"} and l["name"] not in {s["name"] for s in design.stackup}])
        # Direct load_design callers get the same source mutation protection as
        # callers requesting a report.
        if source_identity(Path(path), policy)[0] != digest:
            raise ValueError("ODB++ source changed while it was being imported.")
    return design


def apply_supplement(design, value, job, root):
    """Portable explicit enrichment for information absent in manufacturing jobs."""
    if not isinstance(value, dict) or value.get("contract") != "spike/board-enrichment/v1":
        raise ValueError("Board supplement must use spike/board-enrichment/v1.")
    if set(value) - {"contract", "stackup", "components", "extensions"}:
        raise ValueError("Unknown board enrichment fields.")
    from jsonschema import Draft202012Validator
    schema = json.loads((Path(__file__).resolve().parents[2] / "schemas/board-enrichment-v1.schema.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(value))
    if errors: raise ValueError(f"Invalid board enrichment: {errors[0].message}")
    names = {l["name"] for l in design.layers}
    stackup = value.get("stackup", [])
    seen = set()
    for row in stackup:
        if not isinstance(row, dict) or not row.get("name") or row["name"] in seen:
            raise ValueError("Enrichment stackup needs unique layer names.")
        seen.add(row["name"])
        if number(row.get("thickness_mm", 0)) <= 0:
            raise ValueError("Stackup thickness_mm must be positive.")
        if row.get("type") in {"copper", "signal", "conductor"} and row["name"] not in names:
            raise ValueError("Enriched copper layer does not exist in the matrix.")
        if row.get("type") == "dielectric" and (number(row.get("epsilon_r", 0)) < 1 or number(row.get("loss_tangent", -1)) < 0):
            raise ValueError("Dielectric needs explicit epsilon_r and loss_tangent.")
    if "stackup" in value:
        design.stackup = [dict(r, thickness=r["thickness_mm"]) for r in stackup]
    lookup = {c["reference"]: c for c in design.components}
    seen = set()
    for entry in value.get("components", []):
        reference = entry.get("reference")
        if reference not in lookup or reference in seen:
            raise ValueError("Enrichment has an unknown/duplicate component reference.")
        seen.add(reference)
        component = lookup[reference]
        component["vendor_properties"] = entry.get("properties", {})
        for model in entry.get("models", []):
            member = root + safe_member_name(model["path"])
            if member not in job.members:
                raise ValueError(f"Assigned model is missing from source package: {member}")
            transform = model.get("transform")
            if not isinstance(transform, list) or len(transform) != 16:
                raise ValueError("3D model requires an explicit 4x4 transform in mm.")
            transform = [number(v) for v in transform]
            if transform[12:] != [0, 0, 0, 1]:
                raise ValueError("Model transform must be a row-major affine matrix.")
            data = job.read(member)
            digest = hashlib.sha256(data).hexdigest()
            if model.get("sha256", digest) != digest:
                raise ValueError("Assigned 3D model digest does not match its bytes.")
            design.metadata.setdefault("model_references", []).append({"component": reference, "uri": f"odb-asset:{digest}",
                                                                        "digest": digest, "transform": transform, "path_in_source": member})
            design.metadata.setdefault("odb_model_assets", {})[digest] = {"name": member, "encoding": "base64", "data": base64.b64encode(data).decode("ascii")}
    design.metadata["board_enrichment"] = value
