"""Typed source geometry retained outside solver-visible DesignIR entities."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Mapping, Sequence


def _text(value: Any) -> str:
    return str(value or "").strip()


def _point(value: Any) -> tuple[float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise ValueError("Retained pad occurrences require two-coordinate millimetre points.")
    point = float(value[0]), float(value[1])
    if not all(math.isfinite(item) for item in point):
        raise ValueError("Retained pad-occurrence coordinates must be finite.")
    return point


@dataclass(frozen=True)
class RetainedPadPin:
    component_id: str
    pin: str

    def __post_init__(self) -> None:
        if not self.component_id or not self.pin:
            raise ValueError("Retained pad pin references require component and pin identities.")


@dataclass(frozen=True)
class RetainedPadShape:
    kind: str
    size_mm: tuple[float, float]
    source_primitive_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "size_mm", _point(self.size_mm))
        if self.kind not in {"circle", "rect"} or min(self.size_mm) <= 0:
            raise ValueError("Retained pad shapes must be positive circles or rectangles.")
        if self.kind == "circle" and not math.isclose(self.size_mm[0], self.size_mm[1], rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("Retained circular pad shapes require equal dimensions.")


@dataclass(frozen=True)
class RetainedPadOccurrence:
    source_index: int
    source_id: str
    layer_id: str
    pad_usage: str
    at_mm: tuple[float, float]
    shape: RetainedPadShape
    pin: RetainedPadPin | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "at_mm", _point(self.at_mm))
        if self.source_index < 0 or not self.source_id or not self.layer_id:
            raise ValueError("Retained pad occurrences require non-negative source indices and identities.")


@dataclass(frozen=True)
class RetainedPadstackOccurrenceGroup:
    id: str
    kind: str
    status: str
    reason: str
    padstack_ref: str
    net_id: str
    at_mm: tuple[float, float]
    expected_regular_layer_ids: tuple[str, ...]
    observed_layer_ids: tuple[str, ...]
    occurrence_count: int
    occurrences: tuple[RetainedPadOccurrence, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "at_mm", _point(self.at_mm))
        object.__setattr__(self, "expected_regular_layer_ids", tuple(self.expected_regular_layer_ids))
        object.__setattr__(self, "observed_layer_ids", tuple(self.observed_layer_ids))
        object.__setattr__(self, "occurrences", tuple(self.occurrences))
        if not self.id or not self.padstack_ref or not self.net_id:
            raise ValueError("Retained padstack groups require group, padstack, and net identities.")
        if (self.kind, self.status, self.reason) != (
            "incomplete_padstack_occurrence_group", "retained_unresolved", "missing_required_regular_layers",
        ):
            raise ValueError("Retained padstack groups require the qualified incomplete-group state.")
        expected, observed = self.expected_regular_layer_ids, self.observed_layer_ids
        if not expected or len(expected) != len(set(expected)) or len(observed) != len(set(observed)):
            raise ValueError("Retained padstack layer identities must be non-empty and unique.")
        if not observed or not set(observed) < set(expected):
            raise ValueError("Retained incomplete groups must observe a strict non-empty subset of expected layers.")
        occurrence_layers = tuple(item.layer_id for item in self.occurrences)
        if self.occurrence_count != len(self.occurrences) or occurrence_layers != observed:
            raise ValueError("Retained padstack occurrence counts and observed layers must match exactly.")
        if len({item.source_index for item in self.occurrences}) != len(self.occurrences):
            raise ValueError("Retained padstack occurrence source indices must be unique within a group.")
        if any(item.at_mm != self.at_mm for item in self.occurrences):
            raise ValueError("Retained padstack occurrences must share the exact group location.")


def _pin(value: Any, component_ids: Mapping[str, str] | None = None) -> RetainedPadPin | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("Retained pad pin references must be objects or null.")
    source_component = _text(value.get("component_id", value.get("component")))
    return RetainedPadPin((component_ids or {}).get(source_component, source_component), _text(value.get("pin")))


def retained_groups_from_v1(
    metadata: Mapping[str, Any], layer_ids: Mapping[str, str], net_ids: Mapping[str, str],
    component_ids: Mapping[str, str],
) -> List[RetainedPadstackOccurrenceGroup]:
    groups: List[RetainedPadstackOccurrenceGroup] = []
    for raw in metadata.get("ipc2581_incomplete_pad_occurrence_groups", []):
        if not isinstance(raw, Mapping):
            raise ValueError("Retained padstack occurrence groups must be objects.")
        occurrences = []
        for item in raw.get("occurrences", []):
            if not isinstance(item, Mapping) or not isinstance(item.get("shape"), Mapping):
                raise ValueError("Retained pad occurrences and shapes must be objects.")
            shape = item["shape"]
            source_layer = _text(item.get("layer_id", item.get("layer")))
            occurrences.append(RetainedPadOccurrence(
                source_index=int(item.get("source_index", -1)), source_id=_text(item.get("source_id")),
                layer_id=layer_ids.get(source_layer, source_layer), pad_usage=_text(item.get("pad_usage")),
                at_mm=_point(item.get("at_mm", item.get("at"))),
                shape=RetainedPadShape(_text(shape.get("kind")), _point(shape.get("size_mm")), _text(shape.get("source_primitive_id"))),
                pin=_pin(item.get("pin"), component_ids),
            ))
        source_net = _text(raw.get("net_id", raw.get("net")))
        groups.append(RetainedPadstackOccurrenceGroup(
            id=_text(raw.get("id")), kind=_text(raw.get("kind")), status=_text(raw.get("status")),
            reason=_text(raw.get("reason")), padstack_ref=_text(raw.get("padstack_ref")),
            net_id=net_ids.get(source_net, source_net), at_mm=_point(raw.get("at_mm", raw.get("at"))),
            expected_regular_layer_ids=tuple(layer_ids.get(_text(item), _text(item)) for item in raw.get("expected_regular_layer_ids", [])),
            observed_layer_ids=tuple(layer_ids.get(_text(item), _text(item)) for item in raw.get("observed_layer_ids", [])),
            occurrence_count=int(raw.get("occurrence_count", -1)), occurrences=tuple(occurrences),
        ))
    return groups


def hydrate_retained_groups(values: Mapping[str, Any]) -> List[RetainedPadstackOccurrenceGroup]:
    groups = []
    for raw in values.get("retained_padstack_occurrence_groups", []):
        if isinstance(raw, RetainedPadstackOccurrenceGroup):
            groups.append(raw)
            continue
        item = dict(raw)
        occurrences = []
        for occurrence in item.get("occurrences", []):
            occurrence = dict(occurrence)
            occurrence["shape"] = occurrence["shape"] if isinstance(occurrence["shape"], RetainedPadShape) else RetainedPadShape(**dict(occurrence["shape"]))
            occurrence["pin"] = occurrence.get("pin") if isinstance(occurrence.get("pin"), RetainedPadPin) else _pin(occurrence.get("pin"))
            occurrences.append(RetainedPadOccurrence(**occurrence))
        item["occurrences"] = tuple(occurrences)
        groups.append(RetainedPadstackOccurrenceGroup(**item))
    return groups


def project_retained_groups_to_v1(
    groups: Sequence[RetainedPadstackOccurrenceGroup], layer_names: Mapping[str, str],
    net_names: Mapping[str, str], component_names: Mapping[str, str],
) -> List[Dict[str, Any]]:
    return [{
        "id": group.id, "kind": group.kind, "status": group.status, "reason": group.reason,
        "padstack_ref": group.padstack_ref, "net_id": net_names.get(group.net_id, group.net_id),
        "at_mm": list(group.at_mm),
        "expected_regular_layer_ids": [layer_names.get(item, item) for item in group.expected_regular_layer_ids],
        "observed_layer_ids": [layer_names.get(item, item) for item in group.observed_layer_ids],
        "occurrence_count": group.occurrence_count,
        "occurrences": [{
            "source_index": item.source_index, "source_id": item.source_id,
            "layer_id": layer_names.get(item.layer_id, item.layer_id), "pad_usage": item.pad_usage,
            "at_mm": list(item.at_mm),
            "shape": {"kind": item.shape.kind, "size_mm": list(item.shape.size_mm), "source_primitive_id": item.shape.source_primitive_id},
            "pin": None if item.pin is None else {"component_id": component_names.get(item.pin.component_id, item.pin.component_id), "pin": item.pin.pin},
        } for item in group.occurrences],
    } for group in groups]


def validate_retained_groups(
    groups: Sequence[RetainedPadstackOccurrenceGroup], *, layers: Sequence[Any], nets: Sequence[Any], components: Sequence[Any],
) -> None:
    if len({item.id for item in groups}) != len(groups):
        raise ValueError("Retained padstack group identities must be unique.")
    layer_order = {item.id: item.order for item in layers}
    net_ids = {item.id for item in nets}
    component_ids = {item.id for item in components}
    for group in groups:
        if group.net_id not in net_ids or any(item not in layer_order for item in group.expected_regular_layer_ids):
            raise ValueError("Retained padstack groups must reference canonical net and layer identities.")
        expected = tuple(sorted(group.expected_regular_layer_ids, key=layer_order.__getitem__))
        observed = tuple(item for item in expected if item in set(group.observed_layer_ids))
        if expected != group.expected_regular_layer_ids or observed != group.observed_layer_ids:
            raise ValueError("Retained padstack layers must follow canonical physical order.")
        if any(item.pin is not None and item.pin.component_id not in component_ids for item in group.occurrences):
            raise ValueError("Retained pad occurrences must reference canonical component identities.")


@dataclass(frozen=True)
class RetainedPrimitiveSegment:
    kind: str
    end_mm: tuple[float, float]
    center_mm: tuple[float, float] | None = None
    clockwise: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "end_mm", _point(self.end_mm))
        if self.kind == "line":
            if self.center_mm is not None or self.clockwise is not None:
                raise ValueError("Retained line segments cannot carry arc fields.")
        elif self.kind == "arc":
            object.__setattr__(self, "center_mm", _point(self.center_mm))
            if not isinstance(self.clockwise, bool):
                raise ValueError("Retained arc segments require an explicit direction.")
        else:
            raise ValueError("Retained primitive segments must be lines or circular arcs.")


@dataclass(frozen=True)
class RetainedPrimitiveRing:
    role: str
    start_mm: tuple[float, float]
    segments: tuple[RetainedPrimitiveSegment, ...]
    fill_style_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_mm", _point(self.start_mm))
        object.__setattr__(self, "segments", tuple(self.segments))
        if self.role not in {"outer", "cutout"} or not self.segments:
            raise ValueError("Retained primitive rings require a role and segments.")
        current = self.start_mm
        for segment in self.segments:
            if segment.end_mm == current:
                raise ValueError("Retained primitive segments must have non-zero endpoints.")
            if segment.kind == "arc":
                start_radius = math.hypot(current[0] - segment.center_mm[0], current[1] - segment.center_mm[1])
                end_radius = math.hypot(segment.end_mm[0] - segment.center_mm[0], segment.end_mm[1] - segment.center_mm[1])
                if start_radius <= 0 or not math.isclose(start_radius, end_radius, rel_tol=1e-9, abs_tol=1e-10):
                    raise ValueError("Retained primitive arcs must be non-degenerate circles.")
            current = segment.end_mm
        if current != self.start_mm or (self.role == "outer" and not self.fill_style_id):
            raise ValueError("Retained primitive rings must close exactly and outer rings require a fill identity.")


@dataclass(frozen=True)
class RetainedPrimitiveContour:
    boundary_rings: tuple[RetainedPrimitiveRing, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "boundary_rings", tuple(self.boundary_rings))
        if not self.boundary_rings or self.boundary_rings[0].role != "outer" or any(
            item.role != "cutout" for item in self.boundary_rings[1:]
        ):
            raise ValueError("Retained primitive contours require one outer ring followed by cutouts.")


@dataclass(frozen=True)
class RetainedUserPrimitive:
    id: str
    kind: str
    source_index: int
    source_units: str
    contours: tuple[RetainedPrimitiveContour, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "contours", tuple(self.contours))
        if not self.id or self.kind != "user_special" or self.source_index < 0 or not self.source_units or not self.contours:
            raise ValueError("Retained user primitives require bounded source identity, units, and contours.")


@dataclass(frozen=True)
class RetainedOccurrenceTransform:
    rotation_deg: float = 0.0
    mirror: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.rotation_deg, bool) or not math.isfinite(float(self.rotation_deg)) or not isinstance(self.mirror, bool):
            raise ValueError("Retained occurrence transforms require finite rotation and boolean mirroring.")
        object.__setattr__(self, "rotation_deg", float(self.rotation_deg))


@dataclass(frozen=True)
class RetainedNonregularPadstackOccurrence:
    source_index: int
    source_id: str
    kind: str
    status: str
    reason: str
    padstack_ref: str
    layer_id: str
    layer_polarity: str
    raw_net_ref: str
    resolved_net_id: str
    occurrence_pad_usage: str
    matched_profile_use: str
    at_mm: tuple[float, float]
    xform: RetainedOccurrenceTransform
    primitive_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "at_mm", _point(self.at_mm))
        expected = ("retained_padstack_nonregular_occurrence", "retained_unresolved",
                    "negative_plane_user_primitive_semantics_pending", "negative", "via", "thermal")
        actual = (self.kind, self.status, self.reason, self.layer_polarity,
                  self.occurrence_pad_usage, self.matched_profile_use)
        if actual != expected or self.source_index < 0 or not all((
            self.source_id, self.padstack_ref, self.layer_id, self.raw_net_ref, self.resolved_net_id, self.primitive_ref,
        )):
            raise ValueError("Retained non-regular padstack occurrences require the exact qualified source state.")


@dataclass(frozen=True)
class RetainedNonregularPadstackGeometry:
    contract: str
    user_primitives: tuple[RetainedUserPrimitive, ...]
    occurrences: tuple[RetainedNonregularPadstackOccurrence, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_primitives", tuple(self.user_primitives))
        object.__setattr__(self, "occurrences", tuple(self.occurrences))
        if self.contract != "spike/retained-padstack-geometry/v1" or not self.user_primitives or not self.occurrences:
            raise ValueError("Retained non-regular padstack geometry requires its v1 contract and non-empty records.")


def _segment(raw: Mapping[str, Any]) -> RetainedPrimitiveSegment:
    return RetainedPrimitiveSegment(
        kind=_text(raw.get("kind")), end_mm=_point(raw.get("end_mm")),
        center_mm=_point(raw.get("center_mm")) if raw.get("center_mm") is not None else None,
        clockwise=raw.get("clockwise"),
    )


def _geometry(raw: Mapping[str, Any], layer_ids: Mapping[str, str] | None = None,
              net_ids: Mapping[str, str] | None = None) -> RetainedNonregularPadstackGeometry:
    primitives = []
    for item in raw.get("user_primitives", []):
        contours = []
        for contour in item.get("contours", []):
            rings = [RetainedPrimitiveRing(
                role=_text(ring.get("role")), start_mm=_point(ring.get("start_mm")),
                segments=tuple(_segment(segment) for segment in ring.get("segments", [])),
                fill_style_id=_text(ring.get("fill_style_id")),
            ) for ring in contour.get("boundary_rings", [])]
            contours.append(RetainedPrimitiveContour(tuple(rings)))
        primitives.append(RetainedUserPrimitive(
            id=_text(item.get("id")), kind=_text(item.get("kind")), source_index=int(item.get("source_index", -1)),
            source_units=_text(item.get("source_units")), contours=tuple(contours),
        ))
    occurrences = []
    for item in raw.get("occurrences", []):
        source_layer, source_net = _text(item.get("layer_id")), _text(item.get("resolved_net_id"))
        xform = item.get("xform") if isinstance(item.get("xform"), Mapping) else {}
        occurrences.append(RetainedNonregularPadstackOccurrence(
            source_index=int(item.get("source_index", -1)), source_id=_text(item.get("source_id")),
            kind=_text(item.get("kind")), status=_text(item.get("status")), reason=_text(item.get("reason")),
            padstack_ref=_text(item.get("padstack_ref")), layer_id=(layer_ids or {}).get(source_layer, source_layer),
            layer_polarity=_text(item.get("layer_polarity")).lower(), raw_net_ref=_text(item.get("raw_net_ref")),
            resolved_net_id=(net_ids or {}).get(source_net, source_net),
            occurrence_pad_usage=_text(item.get("occurrence_pad_usage")).lower(),
            matched_profile_use=_text(item.get("matched_profile_use")).lower(), at_mm=_point(item.get("at_mm")),
            xform=RetainedOccurrenceTransform(rotation_deg=xform.get("rotation_deg", 0.0), mirror=xform.get("mirror", False)),
            primitive_ref=_text(item.get("primitive_ref")),
        ))
    return RetainedNonregularPadstackGeometry(_text(raw.get("contract")), tuple(primitives), tuple(occurrences))


def retained_nonregular_geometry_from_v1(
    metadata: Mapping[str, Any], layer_ids: Mapping[str, str], net_ids: Mapping[str, str],
) -> RetainedNonregularPadstackGeometry | None:
    raw = metadata.get("ipc2581_retained_nonregular_padstack_geometry")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("Retained non-regular padstack geometry must be an object.")
    return _geometry(raw, layer_ids, net_ids)


def hydrate_retained_nonregular_geometry(values: Mapping[str, Any]) -> RetainedNonregularPadstackGeometry | None:
    raw = values.get("retained_nonregular_padstack_geometry")
    if raw is None or isinstance(raw, RetainedNonregularPadstackGeometry):
        return raw
    if not isinstance(raw, Mapping):
        raise ValueError("Retained non-regular padstack geometry must be an object.")
    return _geometry(raw)


def project_retained_nonregular_geometry_to_v1(
    geometry: RetainedNonregularPadstackGeometry, layer_names: Mapping[str, str], net_names: Mapping[str, str],
) -> Dict[str, Any]:
    def segment(item: RetainedPrimitiveSegment) -> Dict[str, Any]:
        raw: Dict[str, Any] = {"kind": item.kind, "end_mm": list(item.end_mm)}
        if item.kind == "arc":
            raw.update({"center_mm": list(item.center_mm), "clockwise": item.clockwise})
        return raw

    return {
        "contract": geometry.contract,
        "user_primitives": [{
            "id": primitive.id, "kind": primitive.kind, "source_index": primitive.source_index,
            "source_units": primitive.source_units,
            "contours": [{"boundary_rings": [{
                "role": ring.role, "fill_style_id": ring.fill_style_id, "start_mm": list(ring.start_mm),
                "segments": [segment(item) for item in ring.segments],
            } for ring in contour.boundary_rings]} for contour in primitive.contours],
        } for primitive in geometry.user_primitives],
        "occurrences": [{
            "source_index": item.source_index, "source_id": item.source_id, "kind": item.kind,
            "status": item.status, "reason": item.reason, "padstack_ref": item.padstack_ref,
            "layer_id": layer_names.get(item.layer_id, item.layer_id), "layer_polarity": item.layer_polarity,
            "raw_net_ref": item.raw_net_ref,
            "resolved_net_id": net_names.get(item.resolved_net_id, item.resolved_net_id),
            "occurrence_pad_usage": item.occurrence_pad_usage, "matched_profile_use": item.matched_profile_use,
            "at_mm": list(item.at_mm),
            "xform": {"rotation_deg": item.xform.rotation_deg, "mirror": item.xform.mirror},
            "primitive_ref": item.primitive_ref,
        } for item in geometry.occurrences],
    }


def validate_retained_nonregular_geometry(
    geometry: RetainedNonregularPadstackGeometry | None, *, layers: Sequence[Any], nets: Sequence[Any],
) -> None:
    if geometry is None:
        return
    primitives = {item.id for item in geometry.user_primitives}
    if len(primitives) != len(geometry.user_primitives):
        raise ValueError("Retained user primitive identities must be unique.")
    layer_ids, net_ids = {item.id for item in layers}, {item.id for item in nets}
    if len({item.source_index for item in geometry.occurrences}) != len(geometry.occurrences):
        raise ValueError("Retained non-regular occurrence source indices must be unique.")
    for item in geometry.occurrences:
        if item.layer_id not in layer_ids or item.resolved_net_id not in net_ids or item.primitive_ref not in primitives:
            raise ValueError("Retained non-regular occurrences must reference canonical layers, nets, and user primitives.")


# This envelope is deliberately source-only.  It is not a pad, via, or
# conductor representation, and consumers must not use it to compose source
# transforms or project solver-visible geometry.
_CONTOUR_LAND_CONTRACT = "spike/retained-standard-contour-land-geometry/v2"
_CONTOUR_LAND_SEMANTIC_STATE = "unapplied_normative_semantics_missing"
_CONTOUR_LAND_PROJECTION = "forbidden"
_MAX_RETAINED_STANDARD_CONTOUR_LAND_RECORDS = 100_000


def _bounded_text(value: Any, field_name: str, *, maximum: int = 256) -> str:
    result = _text(value)
    if not result or len(result) > maximum:
        raise ValueError(f"Retained standard contour-land {field_name} must be a bounded non-empty string.")
    return result


def _bounded_attributes(value: Any, field_name: str) -> Dict[str, str]:
    if not isinstance(value, Mapping) or len(value) > 64:
        raise ValueError(f"Retained standard contour-land {field_name} must be a bounded attribute object.")
    result = {str(key): str(item) for key, item in value.items()}
    if any(not key or len(key) > 128 or len(item) > 4096 for key, item in result.items()):
        raise ValueError(f"Retained standard contour-land {field_name} contains an unbounded attribute.")
    return dict(sorted(result.items()))


def _source_index(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Retained standard contour-land source indices must be non-negative integers.")
    return value


@dataclass(frozen=True)
class RetainedStandardContourLandXform:
    """Closed, uncomposed source-Xform facts for one source element."""

    rotation_deg: float
    mirror: bool
    raw_attributes: Dict[str, str]
    x_offset_mm: float | None = None
    y_offset_mm: float | None = None
    face_up: bool | None = None
    scale: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.rotation_deg, bool) or not math.isfinite(float(self.rotation_deg)) or not isinstance(self.mirror, bool):
            raise ValueError("Retained standard contour-land transforms require finite rotation and boolean mirroring.")
        object.__setattr__(self, "rotation_deg", float(self.rotation_deg))
        object.__setattr__(self, "raw_attributes", _bounded_attributes(self.raw_attributes, "xform raw_attributes"))
        for name in ("x_offset_mm", "y_offset_mm", "scale"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not math.isfinite(float(value))):
                raise ValueError("Retained standard contour-land transforms require finite normalized values.")
            if value is not None:
                object.__setattr__(self, name, float(value))
        if self.face_up is not None and not isinstance(self.face_up, bool):
            raise ValueError("Retained standard contour-land transforms require boolean face_up when present.")


@dataclass(frozen=True)
class RetainedStandardContourLandLocation:
    at_mm: tuple[float, float]
    raw_attributes: Dict[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "at_mm", _point(self.at_mm))
        object.__setattr__(self, "raw_attributes", _bounded_attributes(self.raw_attributes, "location raw_attributes"))


@dataclass(frozen=True)
class RetainedStandardContourLandDefinition:
    id: str
    kind: str
    status: str
    reason: str
    source_index: int
    source_units: str
    raw_entry_attributes: Dict[str, str]
    contour: Dict[str, Any]
    fill_descriptor: Dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _bounded_text(self.id, "definition id"))
        object.__setattr__(self, "source_index", _source_index(self.source_index))
        object.__setattr__(self, "source_units", _bounded_text(self.source_units, "definition units", maximum=64))
        object.__setattr__(self, "raw_entry_attributes", _bounded_attributes(self.raw_entry_attributes, "definition raw_entry_attributes"))
        if (self.kind, self.status, self.reason) != (
            "standard_contour_land_definition", "retained_unresolved", "contour_land_layer_transform_semantics_pending",
        ):
            raise ValueError("Retained standard contour-land definitions require the reviewed source-only state.")
        if not isinstance(self.contour, Mapping) or not isinstance(self.fill_descriptor, Mapping):
            raise ValueError("Retained standard contour-land definitions require source contour and fill facts.")
        contour, fill = dict(self.contour), dict(self.fill_descriptor)
        points = contour.get("points_mm")
        if not isinstance(points, list) or not (4 <= len(points) <= 4096):
            raise ValueError("Retained standard contour-land contours require bounded closed source points.")
        normalized_points = [list(_point(item)) for item in points]
        if normalized_points[0] != normalized_points[-1]:
            raise ValueError("Retained standard contour-land contours must close exactly.")
        contour["points_mm"] = normalized_points
        for key in ("raw_poly_begin_attributes", "raw_fill_ref_attributes"):
            contour[key] = _bounded_attributes(contour.get(key), f"contour {key}")
        steps = contour.get("raw_poly_step_attributes")
        if not isinstance(steps, list) or len(steps) > 4096:
            raise ValueError("Retained standard contour-land contour steps must be bounded.")
        contour["raw_poly_step_attributes"] = [_bounded_attributes(item, "contour raw_poly_step_attributes") for item in steps]
        if _bounded_text(contour.get("kind"), "contour kind", maximum=64) != "closed_line_ring":
            raise ValueError("Retained standard contour-land contours must remain closed line rings.")
        contour["fill_style_ref"] = _bounded_text(contour.get("fill_style_ref"), "fill style ref")
        fill["id"] = _bounded_text(fill.get("id"), "fill descriptor id")
        fill["source_units"] = _bounded_text(fill.get("source_units"), "fill descriptor units", maximum=64)
        fill["declared_fill_property"] = _bounded_text(fill.get("declared_fill_property"), "fill property", maximum=64)
        fill["raw_attributes"] = _bounded_attributes(fill.get("raw_attributes"), "fill raw_attributes")
        object.__setattr__(self, "contour", contour)
        object.__setattr__(self, "fill_descriptor", fill)


@dataclass(frozen=True)
class RetainedStandardContourLandPadstack:
    name: str
    source_index: int
    raw_attributes: Dict[str, str]
    declared_regular_layer_id: str
    raw_declared_regular_layer_ref: str
    raw_profile_attributes: Dict[str, str]
    profile_location: RetainedStandardContourLandLocation
    profile_xform: RetainedStandardContourLandXform
    primitive_ref: str
    raw_primitive_ref_attributes: Dict[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _bounded_text(self.name, "padstack name"))
        object.__setattr__(self, "source_index", _source_index(self.source_index))
        object.__setattr__(self, "declared_regular_layer_id", _bounded_text(self.declared_regular_layer_id, "declared layer id"))
        object.__setattr__(self, "raw_declared_regular_layer_ref", _bounded_text(self.raw_declared_regular_layer_ref, "raw declared layer ref"))
        object.__setattr__(self, "primitive_ref", _bounded_text(self.primitive_ref, "primitive ref"))
        for name in ("raw_attributes", "raw_profile_attributes", "raw_primitive_ref_attributes"):
            object.__setattr__(self, name, _bounded_attributes(getattr(self, name), name))
        if not isinstance(self.profile_location, RetainedStandardContourLandLocation) or not isinstance(self.profile_xform, RetainedStandardContourLandXform):
            raise ValueError("Retained standard contour-land padstacks require typed source location and Xform facts.")


@dataclass(frozen=True)
class RetainedStandardContourLandPinProvenance:
    raw_component_ref: str
    resolved_component_id: str
    component_layer_id: str
    pin: str
    raw_attributes: Dict[str, str]

    def __post_init__(self) -> None:
        for name in ("raw_component_ref", "resolved_component_id", "component_layer_id", "pin"):
            object.__setattr__(self, name, _bounded_text(getattr(self, name), f"pin {name}"))
        object.__setattr__(self, "raw_attributes", _bounded_attributes(self.raw_attributes, "pin raw_attributes"))


@dataclass(frozen=True)
class RetainedStandardContourLandOccurrence:
    source_index: int
    source_id: str
    kind: str
    status: str
    reason: str
    padstack_ref: str
    primitive_ref: str
    declared_regular_layer_id: str
    observed_layer_id: str
    declared_layer_matches_observed: bool
    raw_observed_layer_ref: str
    observed_layer_polarity: str
    raw_net_ref: str
    resolved_net_id: str
    pin_provenance: RetainedStandardContourLandPinProvenance
    at_mm: tuple[float, float]
    xform: RetainedStandardContourLandXform
    raw_primitive_ref_attributes: Dict[str, str]
    raw_pad_attributes: Dict[str, str]
    raw_set_attributes: Dict[str, str]
    raw_layer_feature_attributes: Dict[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_index", _source_index(self.source_index))
        object.__setattr__(self, "at_mm", _point(self.at_mm))
        for name in ("source_id", "padstack_ref", "primitive_ref", "declared_regular_layer_id", "observed_layer_id", "raw_observed_layer_ref", "observed_layer_polarity", "raw_net_ref", "resolved_net_id"):
            object.__setattr__(self, name, _bounded_text(getattr(self, name), name))
        if (self.kind, self.status, self.reason) != (
            "standard_contour_land_occurrence", "retained_unresolved", "contour_land_layer_transform_semantics_pending",
        ) or self.observed_layer_polarity != "positive" or not isinstance(self.declared_layer_matches_observed, bool):
            raise ValueError("Retained standard contour-land occurrences require the reviewed source-only state.")
        if not isinstance(self.pin_provenance, RetainedStandardContourLandPinProvenance) or not isinstance(self.xform, RetainedStandardContourLandXform):
            raise ValueError("Retained standard contour-land occurrences require typed pin provenance and Xform facts.")
        for name in ("raw_primitive_ref_attributes", "raw_pad_attributes", "raw_set_attributes", "raw_layer_feature_attributes"):
            object.__setattr__(self, name, _bounded_attributes(getattr(self, name), name))


@dataclass(frozen=True)
class RetainedStandardContourLandGeometry:
    contract: str
    semantic_state: str
    projection: str
    definitions: tuple[RetainedStandardContourLandDefinition, ...]
    padstacks: tuple[RetainedStandardContourLandPadstack, ...]
    occurrences: tuple[RetainedStandardContourLandOccurrence, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "definitions", tuple(self.definitions))
        object.__setattr__(self, "padstacks", tuple(self.padstacks))
        object.__setattr__(self, "occurrences", tuple(self.occurrences))
        if (self.contract, self.semantic_state, self.projection) != (
            _CONTOUR_LAND_CONTRACT, _CONTOUR_LAND_SEMANTIC_STATE, _CONTOUR_LAND_PROJECTION,
        ) or not self.definitions or not self.padstacks or not self.occurrences:
            raise ValueError("Retained standard contour-land geometry is source-only and projection-forbidden.")
        if any(len(items) > _MAX_RETAINED_STANDARD_CONTOUR_LAND_RECORDS for items in (
            self.definitions, self.padstacks, self.occurrences,
        )):
            raise ValueError("Retained standard contour-land geometry exceeds its bounded record limit.")


def _contour_xform(raw: Any) -> RetainedStandardContourLandXform:
    if not isinstance(raw, Mapping):
        raise ValueError("Retained standard contour-land Xform must be an object.")
    return RetainedStandardContourLandXform(**dict(raw))


def _contour_land_geometry(raw: Mapping[str, Any], layer_ids: Mapping[str, str] | None = None,
                           net_ids: Mapping[str, str] | None = None,
                           component_ids: Mapping[str, str] | None = None) -> RetainedStandardContourLandGeometry:
    for name in ("definitions", "padstacks", "occurrences"):
        rows = raw.get(name)
        if not isinstance(rows, list) or len(rows) > _MAX_RETAINED_STANDARD_CONTOUR_LAND_RECORDS:
            raise ValueError("Retained standard contour-land geometry requires bounded record arrays.")
    definitions = tuple(RetainedStandardContourLandDefinition(**dict(item)) for item in raw["definitions"])
    padstacks = []
    for item in raw["padstacks"]:
        values = dict(item)
        values["declared_regular_layer_id"] = (layer_ids or {}).get(_text(values.get("declared_regular_layer_id")), _text(values.get("declared_regular_layer_id")))
        values["profile_location"] = RetainedStandardContourLandLocation(**dict(values.get("profile_location") or {}))
        values["profile_xform"] = _contour_xform(values.get("profile_xform"))
        padstacks.append(RetainedStandardContourLandPadstack(**values))
    occurrences = []
    for item in raw["occurrences"]:
        values = dict(item)
        values["declared_regular_layer_id"] = (layer_ids or {}).get(_text(values.get("declared_regular_layer_id")), _text(values.get("declared_regular_layer_id")))
        values["observed_layer_id"] = (layer_ids or {}).get(_text(values.get("observed_layer_id")), _text(values.get("observed_layer_id")))
        values["resolved_net_id"] = (net_ids or {}).get(_text(values.get("resolved_net_id")), _text(values.get("resolved_net_id")))
        pin = dict(values.get("pin_provenance") or {})
        pin["resolved_component_id"] = (component_ids or {}).get(_text(pin.get("resolved_component_id")), _text(pin.get("resolved_component_id")))
        pin["component_layer_id"] = (layer_ids or {}).get(_text(pin.get("component_layer_id")), _text(pin.get("component_layer_id")))
        values["pin_provenance"] = RetainedStandardContourLandPinProvenance(**pin)
        values["xform"] = _contour_xform(values.get("xform"))
        occurrences.append(RetainedStandardContourLandOccurrence(**values))
    values = dict(raw)
    values.setdefault("semantic_state", _CONTOUR_LAND_SEMANTIC_STATE)
    values.setdefault("projection", _CONTOUR_LAND_PROJECTION)
    values.update({"definitions": definitions, "padstacks": tuple(padstacks), "occurrences": tuple(occurrences)})
    return RetainedStandardContourLandGeometry(**values)


def retained_standard_contour_land_geometry_from_v1(
    metadata: Mapping[str, Any], layer_ids: Mapping[str, str], net_ids: Mapping[str, str], component_ids: Mapping[str, str],
) -> RetainedStandardContourLandGeometry | None:
    raw = metadata.get("ipc2581_retained_standard_contour_land_geometry")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("Retained standard contour-land geometry must be an object.")
    # Older loose retention payloads stay losslessly in v1 metadata.  Only the
    # reviewed v2 envelope is promoted into this closed typed contract.
    if raw.get("contract") != _CONTOUR_LAND_CONTRACT:
        return None
    return _contour_land_geometry(raw, layer_ids, net_ids, component_ids)


def hydrate_retained_standard_contour_land_geometry(values: Mapping[str, Any]) -> RetainedStandardContourLandGeometry | None:
    raw = values.get("retained_standard_contour_land_geometry")
    if raw is None or isinstance(raw, RetainedStandardContourLandGeometry):
        return raw
    if not isinstance(raw, Mapping):
        raise ValueError("Retained standard contour-land geometry must be an object.")
    return _contour_land_geometry(raw)


def _project_xform(item: RetainedStandardContourLandXform) -> Dict[str, Any]:
    raw: Dict[str, Any] = {"rotation_deg": item.rotation_deg, "mirror": item.mirror, "raw_attributes": dict(item.raw_attributes)}
    for name in ("x_offset_mm", "y_offset_mm", "face_up", "scale"):
        value = getattr(item, name)
        if value is not None:
            raw[name] = value
    return raw


def project_retained_standard_contour_land_geometry_to_v1(
    geometry: RetainedStandardContourLandGeometry, layer_names: Mapping[str, str], net_names: Mapping[str, str],
    component_names: Mapping[str, str],
) -> Dict[str, Any]:
    return {
        "contract": geometry.contract, "semantic_state": geometry.semantic_state, "projection": geometry.projection,
        "definitions": [{"id": item.id, "kind": item.kind, "status": item.status, "reason": item.reason,
                         "source_index": item.source_index, "source_units": item.source_units,
                         "raw_entry_attributes": dict(item.raw_entry_attributes), "contour": dict(item.contour),
                         "fill_descriptor": dict(item.fill_descriptor)} for item in geometry.definitions],
        "padstacks": [{"name": item.name, "source_index": item.source_index, "raw_attributes": dict(item.raw_attributes),
                       "declared_regular_layer_id": layer_names.get(item.declared_regular_layer_id, item.declared_regular_layer_id),
                       "raw_declared_regular_layer_ref": item.raw_declared_regular_layer_ref,
                       "raw_profile_attributes": dict(item.raw_profile_attributes),
                       "profile_location": {"at_mm": list(item.profile_location.at_mm), "raw_attributes": dict(item.profile_location.raw_attributes)},
                       "profile_xform": _project_xform(item.profile_xform), "primitive_ref": item.primitive_ref,
                       "raw_primitive_ref_attributes": dict(item.raw_primitive_ref_attributes)} for item in geometry.padstacks],
        "occurrences": [{"source_index": item.source_index, "source_id": item.source_id, "kind": item.kind,
                         "status": item.status, "reason": item.reason, "padstack_ref": item.padstack_ref,
                         "primitive_ref": item.primitive_ref,
                         "declared_regular_layer_id": layer_names.get(item.declared_regular_layer_id, item.declared_regular_layer_id),
                         "observed_layer_id": layer_names.get(item.observed_layer_id, item.observed_layer_id),
                         "declared_layer_matches_observed": item.declared_layer_matches_observed,
                         "raw_observed_layer_ref": item.raw_observed_layer_ref,
                         "observed_layer_polarity": item.observed_layer_polarity, "raw_net_ref": item.raw_net_ref,
                         "resolved_net_id": net_names.get(item.resolved_net_id, item.resolved_net_id),
                         "pin_provenance": {"raw_component_ref": item.pin_provenance.raw_component_ref,
                                            "resolved_component_id": component_names.get(item.pin_provenance.resolved_component_id, item.pin_provenance.resolved_component_id),
                                            "component_layer_id": layer_names.get(item.pin_provenance.component_layer_id, item.pin_provenance.component_layer_id),
                                            "pin": item.pin_provenance.pin, "raw_attributes": dict(item.pin_provenance.raw_attributes)},
                         "at_mm": list(item.at_mm), "xform": _project_xform(item.xform),
                         "raw_primitive_ref_attributes": dict(item.raw_primitive_ref_attributes), "raw_pad_attributes": dict(item.raw_pad_attributes),
                         "raw_set_attributes": dict(item.raw_set_attributes), "raw_layer_feature_attributes": dict(item.raw_layer_feature_attributes)}
                        for item in geometry.occurrences],
    }


def validate_retained_standard_contour_land_geometry(
    geometry: RetainedStandardContourLandGeometry | None, *, layers: Sequence[Any], nets: Sequence[Any], components: Sequence[Any],
) -> None:
    if geometry is None:
        return
    definitions = {item.id for item in geometry.definitions}
    padstacks = {item.name: item for item in geometry.padstacks}
    layer_ids, net_ids, component_ids = {item.id for item in layers}, {item.id for item in nets}, {item.id for item in components}
    if len(definitions) != len(geometry.definitions) or len(padstacks) != len(geometry.padstacks):
        raise ValueError("Retained standard contour-land definition and padstack identities must be unique.")
    if any(item.declared_regular_layer_id not in layer_ids or item.primitive_ref not in definitions for item in geometry.padstacks):
        raise ValueError("Retained standard contour-land padstacks must reference canonical layers and definitions.")
    if len({item.source_index for item in geometry.occurrences}) != len(geometry.occurrences):
        raise ValueError("Retained standard contour-land occurrence source indices must be unique.")
    for item in geometry.occurrences:
        stack = padstacks.get(item.padstack_ref)
        if (item.declared_regular_layer_id not in layer_ids or item.observed_layer_id not in layer_ids
                or item.resolved_net_id not in net_ids or item.pin_provenance.resolved_component_id not in component_ids
                or item.pin_provenance.component_layer_id not in layer_ids or item.primitive_ref not in definitions
                or stack is None or stack.primitive_ref != item.primitive_ref
                or item.declared_regular_layer_id != stack.declared_regular_layer_id
                or item.declared_layer_matches_observed != (item.declared_regular_layer_id == item.observed_layer_id)):
            raise ValueError("Retained standard contour-land occurrences must reference canonical source facts.")
