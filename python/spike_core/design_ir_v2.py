"""Typed CAD-neutral DesignIR v2 and AssemblyIR v1 contracts."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
from .contracts import DesignIR, ValidationIssue
from .assembly_contract_validation import validate_optional_physical
from .assembly_placement_policy import AssemblyPlacementPolicy
from .custom_pad_geometry import validate_custom_pad_geometries
from .design_ir_v2_schema import (
    ASSEMBLY_IR_V1_CONTRACT, DESIGN_IR_V2_CONTRACT, Arc, Bend, CanonicalEntity, Castellation,
    Component, ComponentBond, Connector, CoordinateFrame, Drill, Layer, Material, ModelReference,
    NamedRecord, Net, Pad, Pin, Region, SourceIdentity, Track, Via, Zone, canonical_uuid,
    content_digest, drill_from_v1, entity_id as _entity_id, hydrate_land_profiles, hydrate_track_path,
    hydrate_zone_boundaries, land_profiles_from_v1, native_identity as _native_identity,
    net_lookup as _net_lookup, number as _number, point as _point, project_drill_to_v1,
    project_pad_to_v1, project_track_to_v1, project_via_to_v1, project_zone_to_v1,
    source_id as _source_id, strip_null_track_paths, text as _text, track_path_from_v1,
    validate_drill_references, validate_land_profiles,
    validate_track_paths, zone_from_v1,
)
from .design_ir_unresolved_geometry import (
    RetainedNonregularPadstackGeometry, RetainedPadstackOccurrenceGroup, hydrate_retained_groups,
    hydrate_retained_nonregular_geometry,
    project_retained_groups_to_v1, project_retained_nonregular_geometry_to_v1,
    retained_groups_from_v1, retained_nonregular_geometry_from_v1, validate_retained_groups,
    validate_retained_nonregular_geometry,
    RetainedStandardContourLandGeometry, hydrate_retained_standard_contour_land_geometry,
    project_retained_standard_contour_land_geometry_to_v1, retained_standard_contour_land_geometry_from_v1,
    validate_retained_standard_contour_land_geometry,
)
from .design_ir_thermal_connections import normalize_pad_kind
from .design_ir_v1_normalization import normalize_boolean, pad_drill_size
@dataclass
class DesignIRV2:
    design_id: str
    name: str
    source: SourceIdentity
    frame: CoordinateFrame = field(default_factory=CoordinateFrame)
    contract: str = DESIGN_IR_V2_CONTRACT
    materials: List[Material] = field(default_factory=list)
    layers: List[Layer] = field(default_factory=list)
    nets: List[Net] = field(default_factory=list)
    tracks: List[Track] = field(default_factory=list)
    arcs: List[Arc] = field(default_factory=list)
    zones: List[Zone] = field(default_factory=list)
    pads: List[Pad] = field(default_factory=list)
    vias: List[Via] = field(default_factory=list)
    drills: List[Drill] = field(default_factory=list)
    castellations: List[Castellation] = field(default_factory=list)
    pins: List[Pin] = field(default_factory=list)
    components: List[Component] = field(default_factory=list)
    component_bonds: List[ComponentBond] = field(default_factory=list)
    connectors: List[Connector] = field(default_factory=list)
    regions: List[Region] = field(default_factory=list)
    bends: List[Bend] = field(default_factory=list)
    models: List[ModelReference] = field(default_factory=list)
    constraints: List[NamedRecord] = field(default_factory=list)
    variants: List[NamedRecord] = field(default_factory=list)
    simulation_models: List[NamedRecord] = field(default_factory=list)
    retained_padstack_occurrence_groups: List[RetainedPadstackOccurrenceGroup] = field(default_factory=list)
    retained_nonregular_padstack_geometry: RetainedNonregularPadstackGeometry | None = None
    retained_standard_contour_land_geometry: RetainedStandardContourLandGeometry | None = None
    issues: List[ValidationIssue] = field(default_factory=list)
    vendor_extensions: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    def __post_init__(self) -> None:
        if self.contract != DESIGN_IR_V2_CONTRACT:
            raise ValueError(f"Unsupported DesignIR v2 contract: {self.contract}")
        if not self.design_id:
            raise ValueError("DesignIR v2 requires a deterministic design_id.")
        ids = [entity.id for collection in self._entity_collections() for entity in collection]
        if len(ids) != len(set(ids)):
            raise ValueError("DesignIR v2 canonical entity IDs must be unique.")
        validate_track_paths(self.tracks)
        validate_drill_references(self.drills, layers=self.layers, nets=self.nets, components=self.components, pads=self.pads, vias=self.vias)
        validate_land_profiles(self.pads, self.vias, layers=self.layers)
        validate_custom_pad_geometries(self.pads)
        validate_retained_groups(self.retained_padstack_occurrence_groups, layers=self.layers, nets=self.nets, components=self.components)
        validate_retained_nonregular_geometry(self.retained_nonregular_padstack_geometry, layers=self.layers, nets=self.nets)
        validate_retained_standard_contour_land_geometry(self.retained_standard_contour_land_geometry, layers=self.layers, nets=self.nets, components=self.components)
    def _entity_collections(self) -> List[List[CanonicalEntity]]:
        return [
            self.materials, self.layers, self.nets, self.tracks, self.arcs, self.zones,
            self.pads, self.vias, self.drills, self.castellations, self.pins, self.components,
            self.component_bonds, self.connectors, self.regions, self.bends, self.models,
            self.constraints, self.variants, self.simulation_models,
        ]
    def to_dict(self) -> Dict[str, Any]:
        return strip_null_track_paths(asdict(self))
    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "DesignIRV2":
        """Rehydrate the public JSON contract without relying on loose dicts."""
        entity_types = {
            "materials": Material,
            "layers": Layer,
            "nets": Net,
            "tracks": Track,
            "arcs": Arc,
            "zones": Zone,
            "pads": Pad,
            "vias": Via,
            "drills": Drill,
            "castellations": Castellation,
            "pins": Pin,
            "components": Component,
            "component_bonds": ComponentBond,
            "connectors": Connector,
            "regions": Region,
            "bends": Bend,
            "models": ModelReference,
            "constraints": NamedRecord,
            "variants": NamedRecord,
            "simulation_models": NamedRecord,
        }
        values = dict(raw)
        source = values.get("source")
        frame = values.get("frame")
        values["source"] = source if isinstance(source, SourceIdentity) else SourceIdentity(**dict(source or {}))
        values["frame"] = frame if isinstance(frame, CoordinateFrame) else CoordinateFrame(**dict(frame or {}))
        for key, entity_type in entity_types.items():
            hydrated = []
            for item in values.get(key, []):
                if isinstance(item, entity_type):
                    hydrated.append(item)
                    continue
                entity_values = hydrate_track_path(dict(item)) if key == "tracks" else dict(item)
                if key == "zones":
                    entity_values = hydrate_zone_boundaries(entity_values)
                if key in {"pads", "vias"}:
                    entity_values = hydrate_land_profiles(entity_values)
                hydrated.append(entity_type(**entity_values))
            values[key] = hydrated
        values["issues"] = [
            item if isinstance(item, ValidationIssue) else ValidationIssue(**dict(item))
            for item in values.get("issues", [])
        ]
        values["retained_padstack_occurrence_groups"] = hydrate_retained_groups(values)
        values["retained_nonregular_padstack_geometry"] = hydrate_retained_nonregular_geometry(values)
        values["retained_standard_contour_land_geometry"] = hydrate_retained_standard_contour_land_geometry(values)
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in values.items() if key in allowed})
    @classmethod
    def from_v1(cls, legacy: DesignIR, *, source_digest: str = "") -> "DesignIRV2":
        digest = source_digest or str(legacy.metadata.get("source_sha256", ""))
        if not digest:
            digest = content_digest(legacy.to_dict())
        source_format = legacy.source_format or "unknown"
        design_identity = legacy.design_id or legacy.name or content_digest({"name": legacy.name})
        design_id = canonical_uuid(source_format, "native", "design", design_identity)
        def records(name: str, *metadata_names: str) -> List[Mapping[str, Any]]:
            values = getattr(legacy, name, [])
            if not values:
                for metadata_name in metadata_names:
                    candidate = legacy.metadata.get(metadata_name)
                    if isinstance(candidate, list):
                        values = candidate
                        break
            return [item for item in values if isinstance(item, Mapping)] if isinstance(values, list) else []
        def raw_layers(raw: Mapping[str, Any]) -> List[str]:
            value = raw.get("layers")
            if isinstance(value, (list, tuple)):
                return [_text(item) for item in value if _text(item)]
            return [_text(raw.get("layer"))] if _text(raw.get("layer")) else []
        def layer_type(raw: Mapping[str, Any], name: str) -> str:
            declared = _text(raw.get("type")).lower()
            if declared == "drill":
                return "drill"
            if name.endswith(".Cu") or declared in {"copper", "signal", "power", "mixed"}:
                return "copper"
            return declared or "documentation"
        def linked_id(lookup: Mapping[str, str], value: Any) -> str:
            text = _text(value)
            return lookup.get(text, text)
        nets = [
            Net(
                id=_entity_id(source_format, digest, "net", raw, index),
                source_id=_source_id(raw, index),
                name=str(raw.get("name", raw.get("net_name", ""))),
                net_class=str(raw.get("class", "signal")),
                extensions={"spike.v1": dict(raw)},
            )
            for index, raw in enumerate(records("nets"))
        ]
        net_ids = _net_lookup(nets)
        layer_ids: Dict[str, str] = {}
        layers: List[Layer] = []
        stackup_rows = records("stackup")
        stackup_by_name = {_text(row.get("name")): row for row in stackup_rows if _text(row.get("name"))}
        materials: List[Material] = []
        material_ids: Dict[str, str] = {}
        material_name_ids: Dict[str, str] = {}
        z_mm = 0.0
        def material_for(row: Mapping[str, Any], index: int) -> str:
            material_name = _text(row.get("material") or row.get("material_name") or row.get("type"), "unspecified")
            fingerprint = content_digest({
                "name": material_name,
                "class": _text(row.get("type"), "unspecified"),
                "conductivity": row.get("conductivity_s_per_m", row.get("conductivity")),
                "epsilon_r": row.get("epsilon_r", row.get("relative_permittivity")),
                "loss_tangent": row.get("loss_tangent"),
                "thermal_conductivity": row.get("thermal_conductivity_w_per_mk", row.get("thermal_conductivity")),
                "density": row.get("density_kg_per_m3", row.get("density")),
                "heat_capacity": row.get("heat_capacity_j_per_kgk", row.get("heat_capacity")),
            })
            if fingerprint in material_ids:
                return material_ids[fingerprint]
            source_id = _native_identity(row) or f"material:{material_name}:{fingerprint[:16]}"
            entity_id = canonical_uuid(source_format, "native" if _native_identity(row) else "semantic", "material", source_id)
            materials.append(Material(
                id=entity_id,
                source_id=source_id,
                name=material_name,
                material_class=_text(row.get("type"), "unspecified"),
                conductivity_s_per_m=_number(row.get("conductivity_s_per_m", row.get("conductivity"))) if row.get("conductivity_s_per_m", row.get("conductivity")) is not None else None,
                relative_permittivity=_number(row.get("epsilon_r", row.get("relative_permittivity"))) if row.get("epsilon_r", row.get("relative_permittivity")) is not None else None,
                loss_tangent=_number(row.get("loss_tangent")) if row.get("loss_tangent") is not None else None,
                thermal_conductivity_w_per_mk=_number(row.get("thermal_conductivity_w_per_mk", row.get("thermal_conductivity"))) if row.get("thermal_conductivity_w_per_mk", row.get("thermal_conductivity")) is not None else None,
                density_kg_per_m3=_number(row.get("density_kg_per_m3", row.get("density"))) if row.get("density_kg_per_m3", row.get("density")) is not None else None,
                heat_capacity_j_per_kgk=_number(row.get("heat_capacity_j_per_kgk", row.get("heat_capacity"))) if row.get("heat_capacity_j_per_kgk", row.get("heat_capacity")) is not None else None,
                extensions={"spike.v1": dict(row)},
            ))
            material_ids[fingerprint] = entity_id
            material_name_ids.setdefault(material_name, entity_id)
            return entity_id
        for index, raw in enumerate(records("layers")):
            name = str(raw.get("name", raw.get("layer", f"Layer {index}")))
            entity_id = _entity_id(source_format, digest, "layer", raw, index)
            layer_ids[name] = entity_id
            layer_ids[_source_id(raw, index)] = entity_id
            stackup = stackup_by_name.get(name, {})
            thickness = raw.get("thickness_mm", stackup.get("thickness_mm", stackup.get("thickness")))
            thickness_mm = _number(thickness) if thickness is not None else None
            material_row = stackup or raw
            layers.append(Layer(
                id=entity_id,
                source_id=_source_id(raw, index),
                name=name,
                layer_type=layer_type({**stackup, **raw}, name),
                order=index,
                z_mm=z_mm,
                thickness_mm=thickness_mm,
                material_id=material_for(material_row, index),
                extensions={"spike.v1": dict(raw), "spike.v1.stackup": dict(stackup)} if stackup else {"spike.v1": dict(raw)},
            ))
            if thickness_mm is not None:
                z_mm += thickness_mm
        # Stackup can contain dielectric and process layers that are absent from
        # the graphical layer table. Preserve them as canonical layers too.
        for stackup_index, raw in enumerate(stackup_rows):
            name = _text(raw.get("name"))
            if not name or name in layer_ids:
                continue
            entity_id = _entity_id(source_format, digest, "stackup-layer", raw, stackup_index)
            thickness = raw.get("thickness_mm", raw.get("thickness"))
            thickness_mm = _number(thickness) if thickness is not None else None
            layer_ids[name] = entity_id
            layers.append(Layer(
                id=entity_id,
                source_id=_source_id(raw, stackup_index),
                name=name,
                layer_type=layer_type(raw, name),
                order=len(layers),
                z_mm=z_mm,
                thickness_mm=thickness_mm,
                material_id=material_for(raw, stackup_index),
                extensions={"spike.v1.stackup": dict(raw)},
            ))
            if thickness_mm is not None:
                z_mm += thickness_mm
        if stackup_rows:
            # The v1 layer table is a drawing order, whereas its stackup is the
            # physical order. Reorder the typed view by the latter and derive
            # elevations only once every dielectric/process layer is present.
            by_name = {item.name: item for item in layers}
            physical_names = [_text(row.get("name")) for row in stackup_rows if _text(row.get("name"))]
            ordered_names = [*physical_names, *(name for name in by_name if name not in physical_names)]
            z_mm = 0.0
            layers = [by_name[name] for name in ordered_names]
            for order, layer in enumerate(layers):
                layer.order = order
                layer.z_mm = z_mm
                if layer.thickness_mm is not None:
                    z_mm += layer.thickness_mm
        def net_id(raw: Mapping[str, Any]) -> str:
            value = str(raw.get("net_id") or raw.get("net") or raw.get("net_name") or raw.get("name") or "")
            return net_ids.get(value, value)
        def layer_id(raw: Mapping[str, Any]) -> str:
            value = str(raw.get("layer_id") or raw.get("layer") or "")
            return layer_ids.get(value, value)
        tracks = [Track(
            id=_entity_id(source_format, digest, "track", raw, index),
            source_id=str(raw.get("id", index)),
            name=str(raw.get("name", "")),
            net_id=net_id(raw),
            layer_id=layer_id(raw),
            start_mm=_point(raw.get("start")),
            end_mm=_point(raw.get("end")),
            width_mm=float(raw.get("width", raw.get("width_mm", 0.0)) or 0.0),
            path=track_path_from_v1(raw),
            extensions={"spike.v1": dict(raw)},
        ) for index, raw in enumerate(records("tracks"))]
        arcs = [Arc(
            id=_entity_id(source_format, digest, "arc", raw, index),
            source_id=_source_id(raw, index),
            name=_text(raw.get("name")),
            net_id=net_id(raw),
            layer_id=layer_id(raw),
            start_mm=_point(raw.get("start")),
            mid_mm=_point(raw.get("mid", raw.get("middle"))),
            end_mm=_point(raw.get("end")),
            width_mm=_number(raw.get("width", raw.get("width_mm"))),
            extensions={"spike.v1": dict(raw)},
        ) for index, raw in enumerate(records("arcs", "arcs", "geometry_arcs"))]
        vias = [Via(
            id=_entity_id(source_format, digest, "via", raw, index),
            source_id=_source_id(raw, index),
            net_id=net_id(raw),
            center_mm=_point(raw.get("at", raw.get("center"))),
            diameter_mm=float(raw.get("diameter", raw.get("size", 0.0)) or 0.0),
            drill_mm=float(raw.get("drill", 0.0) or 0.0),
            start_layer_id=layer_ids.get(str(raw.get("start_layer", raw.get("layers", [""])[0] if raw.get("layers") else "")), ""),
            end_layer_id=layer_ids.get(str(raw.get("end_layer", raw.get("layers", ["", ""])[-1] if raw.get("layers") else "")), ""),
            via_type=str(raw.get("type", "through")),
            land_profiles=land_profiles_from_v1(raw, layer_ids),
            extensions={"spike.v1": dict(raw)},
            plating_mm=_number(raw.get("plating_mm", raw.get("plating"))) if raw.get("plating_mm", raw.get("plating")) is not None else None,
        ) for index, raw in enumerate(records("vias"))]
        zones = [zone_from_v1(raw, index, source_format, digest, layer_ids, net_ids)
                 for index, raw in enumerate(records("zones"))]
        components = [Component(
            id=_entity_id(source_format, digest, "component", raw, index),
            source_id=_source_id(raw, index),
            name=str(raw.get("name", raw.get("reference", ""))),
            reference=str(raw.get("reference", "")),
            value=str(raw.get("value", "")),
            footprint=str(raw.get("footprint", raw.get("library", ""))),
            side="bottom" if str(raw.get("layer", "")).startswith("B.") else "top",
            position_mm=_point(raw.get("at")),
            rotation_deg=float(raw.get("rotation", 0.0) or 0.0),
            zone_connection_override=str(raw.get("zone_connection_override", "inherit")),
            zone_connection_declared=bool(raw.get("zone_connection_declared", False)),
            thermal_gap_override_mm=_number(raw.get("thermal_gap_override_mm")) if raw.get("thermal_gap_override_mm") is not None else None,
            thermal_spoke_width_override_mm=_number(raw.get("thermal_spoke_width_override_mm")) if raw.get("thermal_spoke_width_override_mm") is not None else None,
            thermal_settings_valid=bool(raw.get("thermal_settings_valid", False)),
            extensions={"spike.v1": dict(raw)},
        ) for index, raw in enumerate(records("components"))]
        component_lookup = {item.reference: item.id for item in components}
        component_lookup.update({item.source_id: item.id for item in components})
        pads: List[Pad] = []
        for index, raw in enumerate(records("pads")):
            drill_size = pad_drill_size(raw)
            has_drill = max(drill_size) > 0.0
            inferred_drill_shape = (
                "none" if not has_drill
                else "oval" if not math.isclose(drill_size[0], drill_size[1])
                else "circle"
            )
            inferred_plating = str(raw.get("type", "")).lower() != "np_thru_hole" and has_drill
            pads.append(Pad(
                id=_entity_id(source_format, digest, "pad", raw, index),
                source_id=_source_id(raw, index),
                name=str(raw.get("number", raw.get("name", ""))),
                net_id=net_id(raw),
                component_id=component_lookup.get(str(raw.get("component", "")), ""),
                layer_ids=[layer_ids.get(str(item), str(item)) for item in raw.get("layers", [raw.get("layer")]) if item],
                center_mm=_point(raw.get("at")),
                size_mm=_point(raw.get("size")),
                shape=str(raw.get("shape", "custom")),
                drill_size_mm=drill_size,
                drill_shape=str(raw.get("drill_shape", inferred_drill_shape)),
                plated=normalize_boolean(raw.get("plated"), inferred_plating),
                land_profiles=land_profiles_from_v1(raw, layer_ids),
                custom_geometry=dict(raw.get("custom_geometry") or {}),
                pad_kind=normalize_pad_kind(raw),
                zone_connection_override=str(raw.get("zone_connection_override", "inherit")),
                zone_connection_declared=bool(raw.get("zone_connection_declared", False)),
                zone_connection_layer_overrides={
                    layer_ids.get(str(layer), str(layer)): str(mode)
                    for layer, mode in dict(raw.get("zone_connection_layer_overrides") or {}).items()
                },
                thermal_gap_override_mm=_number(raw.get("thermal_gap_override_mm")) if raw.get("thermal_gap_override_mm") is not None else None,
                thermal_spoke_width_override_mm=_number(raw.get("thermal_spoke_width_override_mm")) if raw.get("thermal_spoke_width_override_mm") is not None else None,
                thermal_spoke_angle_deg=_number(raw.get("thermal_spoke_angle_deg")) if raw.get("thermal_spoke_angle_deg") is not None else None,
                thermal_settings_valid=bool(raw.get("thermal_settings_valid", False)),
                extensions={"spike.v1": dict(raw)},
            ))
        pad_lookup = {item.source_id: item.id for item in pads}
        via_lookup = {item.source_id: item.id for item in vias}
        drill_owner_lookup = {**{("pad", key): value for key, value in pad_lookup.items()}, **{("via", key): value for key, value in via_lookup.items()}}
        drills = [drill_from_v1(raw, index, source_format, digest, layer_ids, net_ids, component_lookup, drill_owner_lookup)
                  for index, raw in enumerate(records("drills", "manufacturing_drills"))]
        pins: List[Pin] = []
        pin_lookup: Dict[tuple[str, str], str] = {}
        for pad in pads:
            if not pad.component_id or not pad.name:
                continue
            key = (pad.component_id, pad.name)
            if key not in pin_lookup:
                source_id = f"{pad.component_id}:{pad.name}"
                pin_id = canonical_uuid(source_format, "semantic", "pin", source_id)
                pin_lookup[key] = pin_id
                pins.append(Pin(id=pin_id, source_id=source_id, component_id=pad.component_id, number=pad.name, net_id=pad.net_id, pad_ids=[]))
            pad.pin_id = pin_lookup[key]
            next(pin for pin in pins if pin.id == pad.pin_id).pad_ids.append(pad.id)
        for component in components:
            component.pin_ids = [pin.id for pin in pins if pin.component_id == component.id]
        castellations: List[Castellation] = []
        region_lookup: Dict[str, str] = {}
        regions: List[Region] = []
        for index, raw in enumerate(records("regions")):
            entity_id = _entity_id(source_format, digest, "region", raw, index)
            source_id = _source_id(raw, index)
            region_lookup[source_id] = entity_id
            region_lookup[_text(raw.get("name"))] = entity_id
            regions.append(Region(
                id=entity_id,
                source_id=source_id,
                name=_text(raw.get("name")),
                region_type=_text(raw.get("kind", raw.get("type")), "rigid"),
                outlines_mm=[[_point(point) for point in polygon] for polygon in raw.get("outlines", [raw.get("outline", [])]) if polygon],
                layer_ids=[linked_id(layer_ids, item) for item in raw_layers(raw)],
                extensions={"spike.v1": dict(raw)},
            ))
        for index, raw in enumerate(records("castellations", "castellations")):
            castellations.append(Castellation(
                id=_entity_id(source_format, digest, "castellation", raw, index),
                source_id=_source_id(raw, index),
                name=_text(raw.get("name")),
                net_id=net_id(raw),
                via_id=linked_id(via_lookup, raw.get("via_id", raw.get("via"))),
                boundary_region_id=linked_id(region_lookup, raw.get("boundary_region_id", raw.get("boundary_region"))),
                retained_fraction=_number(raw.get("retained_fraction", raw.get("fraction", 0.5)), 0.5),
                extensions={"spike.v1": dict(raw)},
            ))
        for via in vias:
            raw = via.extensions["spike.v1"]
            if bool(raw.get("castellation") or raw.get("is_castellation")):
                castellations.append(Castellation(
                    id=canonical_uuid(source_format, "semantic", "castellation", via.id),
                    source_id=f"castellation:{via.source_id}",
                    net_id=via.net_id,
                    via_id=via.id,
                    retained_fraction=_number(raw.get("retained_fraction", 0.5), 0.5),
                    extensions={"spike.v1.inferred_from_via": dict(raw)},
                ))
        bends = [Bend(
            id=_entity_id(source_format, digest, "bend", raw, index),
            source_id=_source_id(raw, index),
            name=_text(raw.get("name")),
            region_id=linked_id(region_lookup, raw.get("region_id", raw.get("region"))),
            line_start_mm=_point(raw.get("line_start", raw.get("start", (raw.get("points") or [None, None])[0]))),
            line_end_mm=_point(raw.get("line_end", raw.get("end", (raw.get("points") or [None, None])[-1]))),
            angle_deg=_number(raw.get("angle_deg")),
            radius_mm=_number(raw.get("radius_mm")) if raw.get("radius_mm") is not None else None,
            extensions={"spike.v1": dict(raw)},
        ) for index, raw in enumerate(records("bends"))]
        models: List[ModelReference] = []
        model_lookup: Dict[str, str] = {}
        model_records = records("models", "models", "model_references")
        for component in components:
            raw = component.extensions["spike.v1"]
            path = _text(raw.get("model_resolved") or raw.get("model_path") or raw.get("model_uri"))
            if path:
                model_records.append({"component": component.source_id, "uri": path, "transform": raw.get("model_transform", [])})
        for index, raw in enumerate(model_records):
            uri = _text(raw.get("uri") or raw.get("path") or raw.get("model_path") or raw.get("model_resolved"))
            source_id = _native_identity(raw) or f"model:{_text(raw.get('component') or raw.get('component_id') or raw.get('reference'))}:{content_digest({'uri': uri, 'transform': raw.get('transform', [])})}"
            entity_id = canonical_uuid(source_format, "native" if _native_identity(raw) else "semantic", "model", source_id)
            model_lookup[source_id] = entity_id
            models.append(ModelReference(
                id=entity_id,
                source_id=source_id,
                name=_text(raw.get("name"), uri),
                model_type=_text(raw.get("model_type", raw.get("type")), "3d"),
                uri=uri,
                digest=_text(raw.get("digest", raw.get("sha256"))),
                transform=[_number(item) for item in raw.get("transform", raw.get("model_transform", []))] if isinstance(raw.get("transform", raw.get("model_transform", [])), list) else [],
                extensions={"spike.v1": dict(raw)},
            ))
            component_key = _text(raw.get("component") or raw.get("component_id") or raw.get("reference"))
            component_id = linked_id(component_lookup, component_key)
            if component_id:
                component = next((item for item in components if item.id == component_id), None)
                if component is not None:
                    component.model_ids.append(entity_id)
        component_bonds = [ComponentBond(
            id=_entity_id(source_format, digest, "component-bond", raw, index),
            source_id=_source_id(raw, index),
            name=_text(raw.get("name")),
            component_id=linked_id(component_lookup, raw.get("component_id", raw.get("component"))),
            pin_id=linked_id({pin.source_id: pin.id for pin in pins}, raw.get("pin_id", raw.get("pin"))),
            pad_id=linked_id(pad_lookup, raw.get("pad_id", raw.get("pad"))),
            electrical_material_id=material_name_ids.get(_text(raw.get("electrical_material_id", raw.get("electrical_material"))), _text(raw.get("electrical_material_id", raw.get("electrical_material")))),
            thermal_material_id=material_name_ids.get(_text(raw.get("thermal_material_id", raw.get("thermal_material"))), _text(raw.get("thermal_material_id", raw.get("thermal_material")))),
            contact_area_mm2=_number(raw.get("contact_area_mm2")) if raw.get("contact_area_mm2") is not None else None,
            thickness_mm=_number(raw.get("thickness_mm")) if raw.get("thickness_mm") is not None else None,
            extensions={"spike.v1": dict(raw)},
        ) for index, raw in enumerate(records("component_bonds"))]
        connectors = [Connector(
            id=_entity_id(source_format, digest, "connector", raw, index),
            source_id=_source_id(raw, index),
            name=_text(raw.get("name", raw.get("reference"))),
            component_id=linked_id(component_lookup, raw.get("component_id", raw.get("component", raw.get("reference")))),
            pin_ids=[linked_id({pin.source_id: pin.id for pin in pins}, item) for item in raw.get("pin_ids", raw.get("pins", []))],
            mating_connector_id=_text(raw.get("mating_connector_id", raw.get("mate"))),
            extensions={"spike.v1": dict(raw)},
        ) for index, raw in enumerate(records("connectors"))]
        consumed = {
            "contract", "design_id", "name", "source_format", "source_path", "units", "layers", "nets",
            "tracks", "vias", "pads", "zones", "components", "component_bonds", "connectors", "stackup",
            "technology", "regions", "bends", "issues", "metadata",
        }
        legacy_dict = legacy.to_dict()
        unknown = {key: value for key, value in legacy_dict.items() if key not in consumed}
        retained_groups = retained_groups_from_v1(legacy.metadata, layer_ids, net_ids, component_lookup)
        retained_nonregular_geometry = retained_nonregular_geometry_from_v1(legacy.metadata, layer_ids, net_ids)
        retained_standard_contour_land_geometry = retained_standard_contour_land_geometry_from_v1(legacy.metadata, layer_ids, net_ids, component_lookup)
        return cls(
            design_id=design_id,
            name=legacy.name,
            source=SourceIdentity(source_format, digest, legacy.design_id, legacy.source_path),
            materials=materials,
            layers=layers,
            nets=nets,
            tracks=tracks,
            arcs=arcs,
            zones=zones,
            pads=pads,
            vias=vias,
            drills=drills,
            castellations=castellations,
            pins=pins,
            components=components,
            component_bonds=component_bonds,
            connectors=connectors,
            regions=regions,
            bends=bends,
            models=models,
            retained_padstack_occurrence_groups=retained_groups,
            retained_nonregular_padstack_geometry=retained_nonregular_geometry,
            retained_standard_contour_land_geometry=retained_standard_contour_land_geometry,
            issues=list(legacy.issues),
            vendor_extensions={"spike.v1.unknown": unknown} if unknown else {},
            metadata={
                **{key: value for key, value in legacy.metadata.items() if key not in
                   {"ipc2581_incomplete_pad_occurrence_groups", "ipc2581_retained_nonregular_padstack_geometry",
                    *({"ipc2581_retained_standard_contour_land_geometry"} if retained_standard_contour_land_geometry is not None else set())}},
                "legacy_design_id": legacy.design_id,
                "technology": legacy.technology,
                # The v1 shape has no dedicated material/model/castellation
                # collections. Keep the original source records for a
                # lossless v1 projection while the typed v2 collections drive
                # new consumers.
                "spike.v1.stackup": [dict(row) for row in stackup_rows],
            },
        )
    def to_v1(self) -> DesignIR:
        """Project a v2 design into the established solver-facing v1 model."""
        def legacy(entity: CanonicalEntity, fallback: Dict[str, Any]) -> Dict[str, Any]:
            raw = entity.extensions.get("spike.v1")
            return dict(raw) if isinstance(raw, dict) else fallback
        net_names = {item.id: item.name for item in self.nets}
        layer_names = {item.id: item.name for item in self.layers}
        component_names = {item.id: item.source_id or item.reference for item in self.components}
        owner_names = {item.id: item.source_id or item.id for item in [*self.pads, *self.vias]}
        stackup = self.metadata.get("spike.v1.stackup")
        if not isinstance(stackup, list):
            stackup = [
                dict(item.extensions.get("spike.v1.stackup"))
                for item in self.layers
                if isinstance(item.extensions.get("spike.v1.stackup"), dict)
            ]
        metadata = {
            **self.metadata,
            "design_ir_v2_id": self.design_id,
            "source_sha256": self.source.source_digest,
            "arcs": [legacy(item, {"id": item.source_id or item.id, "net_name": net_names.get(item.net_id, item.net_id), "layer": layer_names.get(item.layer_id, item.layer_id), "start": list(item.start_mm), "mid": list(item.mid_mm), "end": list(item.end_mm), "width": item.width_mm}) for item in self.arcs],
            "castellations": [legacy(item, {"id": item.source_id or item.id, "net_name": net_names.get(item.net_id, item.net_id), "via_id": item.via_id, "boundary_region_id": item.boundary_region_id, "retained_fraction": item.retained_fraction}) for item in self.castellations],
            "model_references": [legacy(item, {"id": item.source_id or item.id, "name": item.name, "type": item.model_type, "uri": item.uri, "digest": item.digest, "transform": list(item.transform)}) for item in self.models],
            "manufacturing_drills": [project_drill_to_v1(item, layer_names, net_names, component_names, owner_names) for item in self.drills],
        }
        if self.retained_padstack_occurrence_groups:
            metadata["ipc2581_incomplete_pad_occurrence_groups"] = project_retained_groups_to_v1(self.retained_padstack_occurrence_groups, layer_names, net_names, component_names)
        if self.retained_nonregular_padstack_geometry is not None:
            metadata["ipc2581_retained_nonregular_padstack_geometry"] = project_retained_nonregular_geometry_to_v1(self.retained_nonregular_padstack_geometry, layer_names, net_names)
        if self.retained_standard_contour_land_geometry is not None:
            metadata["ipc2581_retained_standard_contour_land_geometry"] = project_retained_standard_contour_land_geometry_to_v1(self.retained_standard_contour_land_geometry, layer_names, net_names, component_names)
        return DesignIR(
            design_id=str(self.metadata.get("legacy_design_id") or self.design_id),
            name=self.name,
            source_format=self.source.source_format,
            source_path=self.source.artifact_path,
            layers=[legacy(item, {"id": item.source_id or item.id, "name": item.name, "type": item.layer_type, "thickness_mm": item.thickness_mm}) for item in self.layers],
            nets=[legacy(item, {"id": item.source_id or item.id, "name": item.name}) for item in self.nets],
            tracks=[project_track_to_v1(item, net_names, layer_names) for item in self.tracks],
            vias=[project_via_to_v1(item, net_names, layer_names) for item in self.vias],
            pads=[project_pad_to_v1(item, net_names, layer_names) for item in self.pads],
            zones=[project_zone_to_v1(item, net_names, layer_names) for item in self.zones],
            components=[legacy(item, {"id": item.source_id or item.id, "reference": item.reference, "value": item.value, "footprint": item.footprint, "at": list(item.position_mm), "rotation": item.rotation_deg}) for item in self.components],
            component_bonds=[legacy(item, {"id": item.source_id or item.id, "component_id": item.component_id, "pin_id": item.pin_id, "pad_id": item.pad_id, "electrical_material_id": item.electrical_material_id, "thermal_material_id": item.thermal_material_id, "contact_area_mm2": item.contact_area_mm2, "thickness_mm": item.thickness_mm}) for item in self.component_bonds],
            connectors=[legacy(item, {"id": item.source_id or item.id, "component_id": item.component_id, "pin_ids": list(item.pin_ids), "mating_connector_id": item.mating_connector_id}) for item in self.connectors],
            stackup=[dict(row) for row in stackup if isinstance(row, Mapping)],
            technology=str(self.metadata.get("technology", "unknown")),
            regions=[legacy(item, {"id": item.source_id or item.id, "name": item.name, "kind": item.region_type, "outline": [[list(point) for point in polygon] for polygon in item.outlines_mm], "layers": [layer_names.get(layer, layer) for layer in item.layer_ids]}) for item in self.regions],
            bends=[legacy(item, {"id": item.source_id or item.id, "name": item.name, "region_id": item.region_id, "points": [list(item.line_start_mm), list(item.line_end_mm)], "angle_deg": item.angle_deg, "radius_mm": item.radius_mm}) for item in self.bends],
            issues=list(self.issues),
            metadata=metadata,
        )
@dataclass
class BoardInstance(CanonicalEntity):
    design_id: str = ""
    frame: CoordinateFrame = field(default_factory=CoordinateFrame)
@dataclass
class Harness(CanonicalEntity):
    endpoint_a: str = ""
    endpoint_b: str = ""
    length_mm: float = 0.0
    conductor_material_id: str = ""
    gauge_awg: Optional[float] = None
    pin_map: Dict[str, str] = field(default_factory=dict)
@dataclass
class AssemblyPart(CanonicalEntity):
    part_type: str = "enclosure"
    model_id: str = ""
    frame: CoordinateFrame = field(default_factory=CoordinateFrame)
    material_id: str = ""
    placement_policy: Optional[AssemblyPlacementPolicy] = None
@dataclass
class AssemblyContact(CanonicalEntity):
    endpoint_a: str = ""
    endpoint_b: str = ""
    contact_type: str = "mechanical"
    material_id: str = ""
    contact_area_mm2: Optional[float] = None
    thermal_resistance_k_per_w: Optional[float] = None
@dataclass
class AssemblyBond(CanonicalEntity):
    endpoint_a: str = ""
    endpoint_b: str = ""
    bond_type: str = "electrical"
    electrical_material_id: str = ""
    thermal_material_id: str = ""
    contact_area_mm2: Optional[float] = None
    thickness_mm: Optional[float] = None
    electrical_resistance_ohm: Optional[float] = None
@dataclass
class AssemblyIRV1:
    assembly_id: str
    name: str
    contract: str = ASSEMBLY_IR_V1_CONTRACT
    frame: CoordinateFrame = field(default_factory=lambda: CoordinateFrame(frame_id="assembly"))
    boards: List[BoardInstance] = field(default_factory=list)
    harnesses: List[Harness] = field(default_factory=list)
    connector_mappings: List[NamedRecord] = field(default_factory=list)
    rigid_flex_links: List[NamedRecord] = field(default_factory=list)
    parts: List[AssemblyPart] = field(default_factory=list)
    materials: List[Material] = field(default_factory=list)
    thermal_contacts: List[AssemblyContact] = field(default_factory=list)
    electrical_bonds: List[AssemblyBond] = field(default_factory=list)
    extensions: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    def __post_init__(self) -> None:
        if self.contract != ASSEMBLY_IR_V1_CONTRACT:
            raise ValueError(f"Unsupported AssemblyIR contract: {self.contract}")
        if not self.assembly_id.strip() or not self.name.strip():
            raise ValueError("AssemblyIR v1 requires non-empty assembly_id and name values.")
        if len(self.boards) > 30:
            raise ValueError("AssemblyIR v1 supports at most 30 board instances.")
        if len(self.parts) > 100:
            raise ValueError("AssemblyIR v1 supports at most 100 assembly parts.")
        if len(self.thermal_contacts) > 5000 or len(self.electrical_bonds) > 5000:
            raise ValueError("AssemblyIR v1 supports at most 5000 contacts or bonds per collection.")
        entities = [
            *self.boards, *self.harnesses, *self.connector_mappings,
            *self.rigid_flex_links, *self.parts, *self.materials,
            *self.thermal_contacts, *self.electrical_bonds,
        ]
        ids = [item.id for item in entities]
        if any(not item_id.strip() for item_id in ids):
            raise ValueError("AssemblyIR canonical entity IDs must be non-empty.")
        if len(ids) != len(set(ids)):
            raise ValueError("AssemblyIR canonical entity IDs must be unique.")
        if any(not board.design_id.strip() for board in self.boards):
            raise ValueError("Every AssemblyIR board instance must reference a design_id.")
        frame_ids = [self.frame.frame_id, *[board.frame.frame_id for board in self.boards], *[part.frame.frame_id for part in self.parts]]
        if any(not frame_id.strip() for frame_id in frame_ids):
            raise ValueError("AssemblyIR coordinate frames must have non-empty frame_id values.")
        if len(frame_ids) != len(set(frame_ids)):
            raise ValueError("AssemblyIR coordinate frame IDs must be unique.")
        child_frames = [*[board.frame for board in self.boards], *[part.frame for part in self.parts]]
        frame_lookup = {frame.frame_id: frame for frame in child_frames}
        for child in child_frames:
            parent_id = child.parent_frame_id or self.frame.frame_id
            if parent_id != self.frame.frame_id and parent_id not in frame_lookup:
                raise ValueError(f"AssemblyIR frame {child.frame_id} references unknown parent frame {parent_id}.")
            visited = {child.frame_id}
            while parent_id != self.frame.frame_id:
                if parent_id in visited:
                    raise ValueError(f"AssemblyIR frame hierarchy contains a cycle at {parent_id}.")
                visited.add(parent_id)
                parent = frame_lookup[parent_id]
                parent_id = parent.parent_frame_id or self.frame.frame_id
        for harness in self.harnesses:
            if not harness.endpoint_a.strip() or not harness.endpoint_b.strip():
                raise ValueError("AssemblyIR harness endpoints must be non-empty.")
            if not math.isfinite(harness.length_mm) or harness.length_mm < 0:
                raise ValueError("AssemblyIR harness length must be finite and non-negative.")
            if harness.gauge_awg is not None and (not math.isfinite(harness.gauge_awg) or not 0 <= harness.gauge_awg <= 40):
                raise ValueError("AssemblyIR harness gauge must be finite and between 0 and 40 AWG.")
            if any(not str(source).strip() or not str(target).strip() for source, target in harness.pin_map.items()):
                raise ValueError("AssemblyIR harness pin mappings must use non-empty pin identities.")
        for part in self.parts:
            if part.placement_policy is not None and not isinstance(part.placement_policy, AssemblyPlacementPolicy):
                raise ValueError("AssemblyIR part placement_policy must use spike/assembly-placement-policy/v1.")
            if part.placement_policy is not None:
                # Imported lazily because assembly_frames owns transform algebra
                # and itself consumes this typed AssemblyIR contract.
                from .assembly_frames import validate_rigid_transform
                validate_rigid_transform(part.frame.transform, f"AssemblyIR part {part.id} placement")
        for contact in self.thermal_contacts:
            if not contact.endpoint_a.strip() or not contact.endpoint_b.strip() or not contact.contact_type.strip():
                raise ValueError("AssemblyIR thermal contacts require endpoints and a contact_type.")
            contact.contact_area_mm2 = validate_optional_physical(contact.contact_area_mm2, "thermal contact area", strictly_positive=True)
            contact.thermal_resistance_k_per_w = validate_optional_physical(contact.thermal_resistance_k_per_w, "thermal contact resistance")
        for bond in self.electrical_bonds:
            if not bond.endpoint_a.strip() or not bond.endpoint_b.strip() or not bond.bond_type.strip():
                raise ValueError("AssemblyIR electrical bonds require endpoints and a bond_type.")
            bond.contact_area_mm2 = validate_optional_physical(bond.contact_area_mm2, "electrical bond contact area", strictly_positive=True)
            bond.thickness_mm = validate_optional_physical(bond.thickness_mm, "electrical bond thickness", strictly_positive=True)
            bond.electrical_resistance_ohm = validate_optional_physical(bond.electrical_resistance_ohm, "electrical bond resistance")
        for material in self.materials:
            material.conductivity_s_per_m = validate_optional_physical(material.conductivity_s_per_m, "material electrical conductivity")
            material.relative_permittivity = validate_optional_physical(material.relative_permittivity, "material relative permittivity", strictly_positive=True)
            material.loss_tangent = validate_optional_physical(material.loss_tangent, "material loss tangent")
            material.thermal_conductivity_w_per_mk = validate_optional_physical(material.thermal_conductivity_w_per_mk, "material thermal conductivity", strictly_positive=True)
            material.density_kg_per_m3 = validate_optional_physical(material.density_kg_per_m3, "material density", strictly_positive=True)
            material.heat_capacity_j_per_kgk = validate_optional_physical(material.heat_capacity_j_per_kgk, "material heat capacity", strictly_positive=True)
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AssemblyIRV1":
        """Rehydrate and validate the public AssemblyIR contract.

        Unknown top-level and entity fields are retained under an extension
        namespace so newer writers can be opened without silent data loss.
        """

        def frame(value: Any, *, fallback_id: str) -> CoordinateFrame:
            if isinstance(value, CoordinateFrame):
                return value
            values = dict(value) if isinstance(value, Mapping) else {}
            values.setdefault("frame_id", fallback_id)
            return CoordinateFrame(**{
                key: item for key, item in values.items()
                if key in CoordinateFrame.__dataclass_fields__
            })

        def entity(entity_type: type, value: Any, *, index: int) -> Any:
            if isinstance(value, entity_type):
                return value
            if not isinstance(value, Mapping):
                raise ValueError(f"AssemblyIR {entity_type.__name__} entry {index} must be an object.")
            values = dict(value)
            allowed = set(entity_type.__dataclass_fields__)
            unknown = {key: item for key, item in values.items() if key not in allowed}
            extensions = dict(values.get("extensions") or {})
            if unknown:
                extensions["spike.assembly-ir.unknown-fields"] = unknown
            values["extensions"] = extensions
            if "frame" in allowed:
                values["frame"] = frame(values.get("frame"), fallback_id=f"{entity_type.__name__.lower()}-{index}")
            if entity_type is AssemblyPart and values.get("placement_policy") is not None:
                values["placement_policy"] = AssemblyPlacementPolicy.from_dict(values["placement_policy"])
            return entity_type(**{key: item for key, item in values.items() if key in allowed})

        values = dict(raw)
        values["frame"] = frame(values.get("frame"), fallback_id="assembly")
        for key, entity_type in (
            ("boards", BoardInstance),
            ("harnesses", Harness),
            ("connector_mappings", NamedRecord),
            ("rigid_flex_links", NamedRecord),
            ("parts", AssemblyPart),
            ("materials", Material),
            ("thermal_contacts", AssemblyContact),
            ("electrical_bonds", AssemblyBond),
        ):
            items = values.get(key, [])
            if not isinstance(items, list):
                raise ValueError(f"AssemblyIR {key} must be an array.")
            values[key] = [entity(entity_type, item, index=index) for index, item in enumerate(items)]
        allowed = set(cls.__dataclass_fields__)
        unknown = {key: item for key, item in values.items() if key not in allowed}
        extensions = dict(values.get("extensions") or {})
        if unknown:
            extensions["spike.assembly-ir.unknown-fields"] = unknown
        values["extensions"] = extensions
        return cls(**{key: item for key, item in values.items() if key in allowed})
