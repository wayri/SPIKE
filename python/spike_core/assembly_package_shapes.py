"""Strict package-shape ownership and topology-reference validation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Dict, Mapping

from .design_ir_v2_schema import canonical_uuid
from .package_shape_geometry import PackageShapeGeometryError, canonicalize_selector_geometry


ASSEMBLY_PACKAGE_SHAPES_V1 = "spike/assembly-package-shapes/v1"
PACKAGE_SHAPE_KERNEL_V1 = "spike/package-shape-kernel/v1"
PACKAGE_SHAPE_SELECTOR_PREVIEW_V1 = "spike/package-shape-selector-preview/v1"
TOPOLOGY_KINDS = {"solid", "shell", "face", "edge", "axis", "vertex"}
CONSTRAINT_KINDS = {"face", "edge", "axis", "concentric", "coincident", "distance", "angle"}
MAX_SHAPES = 100
MAX_ENTITIES_PER_SHAPE = 200_000
MAX_TOTAL_ENTITIES = 500_000
MAX_RECORDS = 5_000
MAX_PREVIEW_SELECTORS = 20_000
_ID = re.compile(r"^\S(?:.{0,254}\S)?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_URI = re.compile(r"^package:models/artifacts/[A-Za-z0-9][A-Za-z0-9._+-]*\.(?:step|stp)$")
_TOPOLOGY_URI = re.compile(r"^package:geometry/package-shapes/[A-Za-z0-9][A-Za-z0-9._+-]*\.spkshape$")
_SELECTOR_PREVIEW_URI = re.compile(r"^package:geometry/package-shapes/[A-Za-z0-9][A-Za-z0-9._+-]*\.spkselect\.glb$")
_EXTENSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class AssemblyPackageShapeError(ValueError):
    """Raised when exact package-shape ownership is incomplete or inconsistent."""


def _strict_object(raw: Any, fields: set[str], label: str) -> Dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != fields:
        raise AssemblyPackageShapeError(f"{label} must contain exactly: {', '.join(sorted(fields))}.")
    return dict(raw)


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise AssemblyPackageShapeError(f"{label} must be a non-empty identity of at most 256 characters.")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise AssemblyPackageShapeError(f"{label} must be a lowercase SHA-256 digest.")
    return value


def _extensions(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) or _EXTENSION.fullmatch(key) is None for key in value):
        raise AssemblyPackageShapeError(f"{label} must be an object with namespaced keys.")
    return dict(value)


def model_transform_sha256(transform: Any) -> str:
    values = transform if isinstance(transform, list) else []
    payload = (json.dumps(values, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def selector_inventory_sha256(entities: Any) -> str:
    """Digest the ordered canonical selector inventory bound into a preview."""

    payload = (json.dumps(entities, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _finite_optional(value: Any, label: str, *, nonnegative: bool = False) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise AssemblyPackageShapeError(f"{label} must be finite or null.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AssemblyPackageShapeError(f"{label} must be finite or null.") from exc
    if not math.isfinite(number) or (nonnegative and number < 0):
        raise AssemblyPackageShapeError(f"{label} must be {'non-negative and ' if nonnegative else ''}finite or null.")
    return number


def _reference(raw: Any, *, shapes: Mapping[str, Dict[str, Any]], label: str) -> Dict[str, str]:
    value = _strict_object(raw, {"ref_kind", "part_id", "shape_id", "topology_id", "topology_kind"}, label)
    if value["ref_kind"] != "package_shape_topology":
        raise AssemblyPackageShapeError(f"{label} must use package_shape_topology ownership.")
    shape_id = _identifier(value["shape_id"], f"{label} shape_id")
    shape = shapes.get(shape_id)
    if shape is None:
        raise AssemblyPackageShapeError(f"{label} references unknown shape {shape_id}.")
    part_id = _identifier(value["part_id"], f"{label} part_id")
    topology_id = _identifier(value["topology_id"], f"{label} topology_id")
    kind = value["topology_kind"]
    if part_id != shape["part_id"]:
        raise AssemblyPackageShapeError(f"{label} part does not own shape {shape_id}.")
    actual_kind = shape["entity_kinds"].get(topology_id)
    if kind not in TOPOLOGY_KINDS or actual_kind != kind:
        raise AssemblyPackageShapeError(f"{label} topology identity or kind does not resolve in shape {shape_id}.")
    return {"ref_kind": "package_shape_topology", "part_id": part_id, "shape_id": shape_id, "topology_id": topology_id, "topology_kind": kind}


def canonicalize_assembly_package_shapes(raw: Any, assembly_ir: Any, model_index: Any) -> Dict[str, Any]:
    """Canonicalize and resolve every exact-shape, selector, constraint, and binding."""

    if raw is None or raw == {}:
        return {}
    root_fields = {"contract", "assembly_id", "shapes", "constraints", "thermal_contact_bindings", "electrical_bond_bindings", "extensions", "metadata"}
    root = _strict_object(raw, root_fields, "Assembly package-shape index")
    if root["contract"] != ASSEMBLY_PACKAGE_SHAPES_V1:
        raise AssemblyPackageShapeError("Assembly package-shape contract is unsupported or missing.")
    if not isinstance(assembly_ir, Mapping) or not isinstance(model_index, Mapping):
        raise AssemblyPackageShapeError("Assembly package shapes require canonical AssemblyIR and model index records.")
    assembly_id = _identifier(root["assembly_id"], "Assembly package-shape assembly_id")
    if assembly_id != assembly_ir.get("assembly_id"):
        raise AssemblyPackageShapeError("Assembly package shapes do not match the owning AssemblyIR identity.")
    parts = {str(item.get("id")): item for item in assembly_ir.get("parts", []) if isinstance(item, Mapping)}
    models = {str(item.get("id")): item for item in model_index.get("models", []) if isinstance(item, Mapping)}
    shape_items = root["shapes"]
    if not isinstance(shape_items, list) or len(shape_items) > MAX_SHAPES:
        raise AssemblyPackageShapeError(f"Assembly package shapes supports at most {MAX_SHAPES} shapes.")
    shapes: Dict[str, Dict[str, Any]] = {}
    canonical_shapes = []
    total_entities = 0
    for position, raw_shape in enumerate(shape_items):
        fields = {"shape_id", "part_id", "source_model_id", "source_artifact_uri", "source_sha256", "topology_artifact_uri", "topology_artifact_sha256", "kernel", "extraction", "entities", "extensions"}
        if isinstance(raw_shape, Mapping) and "selector_preview" in raw_shape:
            fields.add("selector_preview")
        shape = _strict_object(raw_shape, fields, f"Package shape {position}")
        part_id = _identifier(shape["part_id"], f"Package shape {position} part_id")
        source_model_id = _identifier(shape["source_model_id"], f"Package shape {position} source_model_id")
        part, model = parts.get(part_id), models.get(source_model_id)
        if part is None or model is None or model.get("model_type") != "step":
            raise AssemblyPackageShapeError(f"Package shape {position} must own an existing part and retained STEP model.")
        source_uri = shape["source_artifact_uri"]
        source_sha256 = _digest(shape["source_sha256"], f"Package shape {position} source_sha256")
        if not isinstance(source_uri, str) or _SOURCE_URI.fullmatch(source_uri) is None or source_uri != model.get("uri") or source_sha256 != model.get("digest"):
            raise AssemblyPackageShapeError(f"Package shape {position} source artifact does not match its retained STEP model.")
        current_model = str(part.get("model_id", ""))
        tessellation = (part.get("extensions") or {}).get("spike.mcad.tessellation") if isinstance(part.get("extensions"), Mapping) else None
        retained_source = str(tessellation.get("source_model_id", "")) if isinstance(tessellation, Mapping) else ""
        if source_model_id not in {current_model, retained_source}:
            raise AssemblyPackageShapeError(f"Package shape {position} retained STEP model does not belong to its part.")
        shape_id = _identifier(shape["shape_id"], f"Package shape {position} shape_id")
        if shape_id != canonical_uuid("step", source_sha256, "package-shape", source_model_id) or shape_id in shapes:
            raise AssemblyPackageShapeError(f"Package shape {position} identity is not canonical or is duplicated.")
        topology_uri = shape["topology_artifact_uri"]
        if not isinstance(topology_uri, str) or _TOPOLOGY_URI.fullmatch(topology_uri) is None:
            raise AssemblyPackageShapeError(f"Package shape {shape_id} topology artifact URI is unsafe.")
        topology_sha256 = _digest(shape["topology_artifact_sha256"], f"Package shape {shape_id} topology digest")
        kernel = _strict_object(shape["kernel"], {"id", "contract", "version"}, f"Package shape {shape_id} kernel")
        kernel = {"id": _identifier(kernel["id"], "Package-shape kernel id"), "contract": kernel["contract"], "version": _identifier(kernel["version"], "Package-shape kernel version")}
        if kernel["contract"] != PACKAGE_SHAPE_KERNEL_V1:
            raise AssemblyPackageShapeError("Package-shape kernel contract is unsupported.")
        extraction = _strict_object(shape["extraction"], {"status", "source_format", "source_model_transform_sha256", "topology_ready", "solver_ready"}, f"Package shape {shape_id} extraction")
        if extraction != {"status": "complete", "source_format": "step", "source_model_transform_sha256": model_transform_sha256(model.get("transform", [])), "topology_ready": True, "solver_ready": False}:
            raise AssemblyPackageShapeError(f"Package shape {shape_id} extraction qualification or transform identity is invalid.")
        entities = shape["entities"]
        if not isinstance(entities, list) or not entities or len(entities) > MAX_ENTITIES_PER_SHAPE:
            raise AssemblyPackageShapeError(f"Package shape {shape_id} selector inventory is empty or exceeds its limit.")
        total_entities += len(entities)
        if total_entities > MAX_TOTAL_ENTITIES:
            raise AssemblyPackageShapeError("Assembly package-shape selector inventory exceeds its total limit.")
        entity_ids: set[str] = set()
        native_ids: set[tuple[str, str]] = set()
        entity_kinds: Dict[str, str] = {}
        canonical_entities = []
        pending_axes: list[str] = []
        for entity_position, raw_entity in enumerate(entities):
            entity_fields = {"topology_id", "kind", "native_persistent_id", "fingerprint_sha256", "support"}
            if isinstance(raw_entity, Mapping) and "geometry" in raw_entity:
                entity_fields.add("geometry")
            entity = _strict_object(raw_entity, entity_fields, f"Package shape {shape_id} entity {entity_position}")
            kind = entity["kind"]
            native_id = _identifier(entity["native_persistent_id"], "Topology native persistent id")
            topology_id = _identifier(entity["topology_id"], "Topology identity")
            if kind not in TOPOLOGY_KINDS or topology_id != canonical_uuid("step", source_sha256, kind, native_id) or topology_id in entity_ids or (kind, native_id) in native_ids:
                raise AssemblyPackageShapeError(f"Package shape {shape_id} entity identity is invalid or duplicated.")
            support = _strict_object(entity["support"], {"surface_kind", "curve_kind", "axis_topology_id"}, f"Topology entity {topology_id} support")
            if support["surface_kind"] not in {None, "plane", "cylinder", "cone", "sphere", "torus", "nurbs", "other"} or support["curve_kind"] not in {None, "line", "circle", "ellipse", "bspline", "other"}:
                raise AssemblyPackageShapeError(f"Topology entity {topology_id} support kind is invalid.")
            if support["axis_topology_id"] is not None:
                pending_axes.append(_identifier(support["axis_topology_id"], f"Topology entity {topology_id} axis"))
            entity_ids.add(topology_id); native_ids.add((kind, native_id)); entity_kinds[topology_id] = kind
            canonical_entity = {"topology_id": topology_id, "kind": kind, "native_persistent_id": native_id, "fingerprint_sha256": _digest(entity["fingerprint_sha256"], f"Topology entity {topology_id} fingerprint"), "support": support}
            if "geometry" in entity:
                try:
                    canonical_entity["geometry"] = canonicalize_selector_geometry(entity["geometry"], kind, f"Topology entity {topology_id} geometry")
                except PackageShapeGeometryError as exc:
                    raise AssemblyPackageShapeError(str(exc)) from exc
            canonical_entities.append(canonical_entity)
        if any(entity_kinds.get(axis_id) != "axis" for axis_id in pending_axes):
            raise AssemblyPackageShapeError(f"Package shape {shape_id} contains an unresolved support axis.")
        selector_preview = None
        if "selector_preview" in shape:
            preview = _strict_object(shape["selector_preview"], {
                "contract", "artifact_uri", "artifact_sha256", "source_sha256",
                "topology_artifact_sha256", "selector_inventory_sha256", "freecad_version",
                "linear_deflection_mm", "face_count", "edge_count", "axis_count",
                "visual_only", "solver_ready",
            }, f"Package shape {shape_id} selector preview")
            if preview["contract"] != PACKAGE_SHAPE_SELECTOR_PREVIEW_V1:
                raise AssemblyPackageShapeError(f"Package shape {shape_id} selector-preview contract is unsupported.")
            preview_uri = preview["artifact_uri"]
            if not isinstance(preview_uri, str) or _SELECTOR_PREVIEW_URI.fullmatch(preview_uri) is None:
                raise AssemblyPackageShapeError(f"Package shape {shape_id} selector-preview artifact URI is unsafe.")
            if preview["source_sha256"] != source_sha256 or preview["topology_artifact_sha256"] != topology_sha256:
                raise AssemblyPackageShapeError(f"Package shape {shape_id} selector preview is not bound to its source and topology artifacts.")
            inventory_sha256 = selector_inventory_sha256(canonical_entities)
            if preview["selector_inventory_sha256"] != inventory_sha256:
                raise AssemblyPackageShapeError(f"Package shape {shape_id} selector preview does not match its selector inventory.")
            counts = {}
            for count_field, kind in (("face_count", "face"), ("edge_count", "edge"), ("axis_count", "axis")):
                count = preview[count_field]
                if isinstance(count, bool) or not isinstance(count, int) or count != sum(item["kind"] == kind for item in canonical_entities):
                    raise AssemblyPackageShapeError(f"Package shape {shape_id} selector-preview {count_field} is invalid.")
                counts[count_field] = count
            if sum(counts.values()) > MAX_PREVIEW_SELECTORS:
                raise AssemblyPackageShapeError(f"Package shape {shape_id} selector preview exceeds its selector limit.")
            try:
                linear_deflection_mm = float(preview["linear_deflection_mm"])
            except (TypeError, ValueError) as exc:
                raise AssemblyPackageShapeError(f"Package shape {shape_id} selector-preview deflection must be positive and finite.") from exc
            if isinstance(preview["linear_deflection_mm"], bool) or not math.isfinite(linear_deflection_mm) or linear_deflection_mm <= 0:
                raise AssemblyPackageShapeError(f"Package shape {shape_id} selector-preview deflection must be positive and finite.")
            if preview["visual_only"] is not True or preview["solver_ready"] is not False:
                raise AssemblyPackageShapeError(f"Package shape {shape_id} selector preview must remain visual-only and not solver-ready.")
            selector_preview = {
                "contract": PACKAGE_SHAPE_SELECTOR_PREVIEW_V1,
                "artifact_uri": preview_uri,
                "artifact_sha256": _digest(preview["artifact_sha256"], f"Package shape {shape_id} selector-preview digest"),
                "source_sha256": _digest(preview["source_sha256"], f"Package shape {shape_id} selector-preview source digest"),
                "topology_artifact_sha256": _digest(preview["topology_artifact_sha256"], f"Package shape {shape_id} selector-preview topology digest"),
                "selector_inventory_sha256": _digest(preview["selector_inventory_sha256"], f"Package shape {shape_id} selector-preview inventory digest"),
                "freecad_version": _identifier(preview["freecad_version"], f"Package shape {shape_id} selector-preview FreeCAD version"),
                "linear_deflection_mm": linear_deflection_mm,
                **counts,
                "visual_only": True,
                "solver_ready": False,
            }
        canonical_shape = {"shape_id": shape_id, "part_id": part_id, "source_model_id": source_model_id, "source_artifact_uri": source_uri, "source_sha256": source_sha256, "topology_artifact_uri": topology_uri, "topology_artifact_sha256": topology_sha256, "kernel": kernel, "extraction": extraction, "entities": canonical_entities, "extensions": _extensions(shape["extensions"], f"Package shape {shape_id} extensions"), "entity_kinds": entity_kinds}
        if selector_preview is not None:
            canonical_shape["selector_preview"] = selector_preview
        shapes[shape_id] = canonical_shape
        canonical_shapes.append({key: value for key, value in canonical_shape.items() if key != "entity_kinds"})
    constraints = root["constraints"]
    if not isinstance(constraints, list) or len(constraints) > MAX_RECORDS:
        raise AssemblyPackageShapeError("Assembly package-shape constraints exceed their limit.")
    constraint_ids: set[str] = set(); canonical_constraints = []
    for position, raw_constraint in enumerate(constraints):
        constraint = _strict_object(raw_constraint, {"constraint_id", "kind", "references", "value_mm", "value_deg", "status"}, f"Topology constraint {position}")
        identity = _identifier(constraint["constraint_id"], f"Topology constraint {position} identity")
        kind = constraint["kind"]
        references = constraint["references"]
        if identity in constraint_ids or kind not in CONSTRAINT_KINDS or constraint["status"] != "defined" or not isinstance(references, list) or not 1 <= len(references) <= 2:
            raise AssemblyPackageShapeError(f"Topology constraint {position} is invalid or duplicated.")
        if kind in {"concentric", "coincident", "distance", "angle"} and len(references) != 2:
            raise AssemblyPackageShapeError(f"Topology constraint {identity} requires exactly two references.")
        value_mm = _finite_optional(constraint["value_mm"], f"Topology constraint {identity} value_mm", nonnegative=True)
        value_deg = _finite_optional(constraint["value_deg"], f"Topology constraint {identity} value_deg")
        if kind == "angle" and value_deg is not None and not 0 <= value_deg <= 180:
            raise AssemblyPackageShapeError(f"Topology constraint {identity} value_deg must be within 0 through 180 degrees.")
        if (kind == "distance") != (value_mm is not None) or (kind == "angle") != (value_deg is not None) or (kind not in {"distance", "angle"} and (value_mm is not None or value_deg is not None)):
            raise AssemblyPackageShapeError(f"Topology constraint {identity} value does not match its kind.")
        constraint_ids.add(identity)
        resolved = [_reference(item, shapes=shapes, label=f"Topology constraint {identity} reference") for item in references]
        resolved_kinds = [item["topology_kind"] for item in resolved]
        if kind in {"face", "edge", "axis"} and any(item != kind for item in resolved_kinds):
            raise AssemblyPackageShapeError(f"Topology constraint {identity} requires {kind} references.")
        if kind == "concentric" and any(item != "axis" for item in resolved_kinds):
            raise AssemblyPackageShapeError(f"Topology constraint {identity} requires owned axis references.")
        if kind == "coincident" and len(set(resolved_kinds)) != 1:
            raise AssemblyPackageShapeError(f"Topology constraint {identity} requires matching topology kinds.")
        canonical_constraints.append({"constraint_id": identity, "kind": kind, "references": resolved, "value_mm": value_mm, "value_deg": value_deg, "status": "defined"})
    def bindings(raw_bindings: Any, entity_ids: set[str], label: str, allowed_kinds: set[str]) -> list[Dict[str, Any]]:
        if not isinstance(raw_bindings, list) or len(raw_bindings) > MAX_RECORDS:
            raise AssemblyPackageShapeError(f"{label} exceed their limit.")
        seen: set[str] = set(); result = []
        for position, raw_binding in enumerate(raw_bindings):
            binding = _strict_object(raw_binding, {"assembly_entity_id", "endpoint_a", "endpoint_b"}, f"{label} {position}")
            identity = _identifier(binding["assembly_entity_id"], f"{label} {position} identity")
            if identity not in entity_ids or identity in seen:
                raise AssemblyPackageShapeError(f"{label} {position} does not resolve uniquely in AssemblyIR.")
            endpoint_a = _reference(binding["endpoint_a"], shapes=shapes, label=f"{label} {identity} endpoint_a")
            endpoint_b = _reference(binding["endpoint_b"], shapes=shapes, label=f"{label} {identity} endpoint_b")
            if endpoint_a["topology_id"] == endpoint_b["topology_id"]:
                raise AssemblyPackageShapeError(f"{label} {identity} endpoints must be distinct.")
            if endpoint_a["topology_kind"] not in allowed_kinds or endpoint_b["topology_kind"] not in allowed_kinds:
                raise AssemblyPackageShapeError(f"{label} {identity} endpoint kind is not supported.")
            seen.add(identity); result.append({"assembly_entity_id": identity, "endpoint_a": endpoint_a, "endpoint_b": endpoint_b})
        return result
    thermal_ids = {str(item.get("id")) for item in assembly_ir.get("thermal_contacts", []) if isinstance(item, Mapping)}
    bond_ids = {str(item.get("id")) for item in assembly_ir.get("electrical_bonds", []) if isinstance(item, Mapping)}
    if not isinstance(root["metadata"], Mapping):
        raise AssemblyPackageShapeError("Assembly package-shape metadata must be an object.")
    return {"contract": ASSEMBLY_PACKAGE_SHAPES_V1, "assembly_id": assembly_id, "shapes": canonical_shapes, "constraints": canonical_constraints, "thermal_contact_bindings": bindings(root["thermal_contact_bindings"], thermal_ids, "Thermal contact bindings", {"face"}), "electrical_bond_bindings": bindings(root["electrical_bond_bindings"], bond_ids, "Electrical bond bindings", {"face", "edge", "vertex"}), "extensions": _extensions(root["extensions"], "Assembly package-shape extensions"), "metadata": dict(root["metadata"])}


def validate_package_shape_artifacts(index: Mapping[str, Any], member_digests: Mapping[str, str]) -> None:
    claimed: set[str] = set()
    for shape in index.get("shapes", []):
        member = str(shape["topology_artifact_uri"]).removeprefix("package:")
        if member in claimed:
            raise AssemblyPackageShapeError(f"Package-shape artifact is claimed more than once: {member}")
        claimed.add(member)
        actual = member_digests.get(member)
        if actual is None:
            raise AssemblyPackageShapeError(f"Package-shape topology artifact is missing: {member}")
        if actual.lower() != str(shape["topology_artifact_sha256"]).lower():
            raise AssemblyPackageShapeError(f"Package-shape topology artifact digest does not match: {member}")
        preview = shape.get("selector_preview")
        if isinstance(preview, Mapping):
            preview_member = str(preview["artifact_uri"]).removeprefix("package:")
            if preview_member in claimed:
                raise AssemblyPackageShapeError(f"Package-shape artifact is claimed more than once: {preview_member}")
            claimed.add(preview_member)
            preview_actual = member_digests.get(preview_member)
            if preview_actual is None:
                raise AssemblyPackageShapeError(f"Package-shape selector-preview artifact is missing: {preview_member}")
            if preview_actual.lower() != str(preview["artifact_sha256"]).lower():
                raise AssemblyPackageShapeError(f"Package-shape selector-preview artifact digest does not match: {preview_member}")
    present = {name for name in member_digests if name.startswith("geometry/package-shapes/")}
    if unexpected := present - claimed:
        raise AssemblyPackageShapeError(f"Package contains an unindexed package-shape topology artifact: {sorted(unexpected)[0]}")
