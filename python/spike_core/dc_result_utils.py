"""Small deterministic policies shared by DC solver result construction."""

from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
import json
from math import ceil, sqrt
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .contracts import AnalysisSpec


def weighted_percentile_density(edges: List[Dict[str, Any]], quantile: float) -> float:
    weighted = sorted(
        (
            float(edge["current_density_a_mm2"]),
            max(
                float(edge["length_mm"])
                * float(edge["width_mm"])
                * float(edge["thickness_mm"]),
                1e-18,
            ),
        )
        for edge in edges
        if edge["current_density_supported"]
    )
    if not weighted:
        return 0.0
    target = min(max(float(quantile), 0.0), 1.0) * sum(weight for _, weight in weighted)
    cumulative = 0.0
    for value, weight in weighted:
        cumulative += weight
        if cumulative >= target:
            return value
    return weighted[-1][0]


def sample_indexes(count: int, limit: int) -> List[int]:
    """Return evenly spaced indexes for legacy scalar-only callers.

    New callers with geometry or result records must use
    :func:`stratified_sample_records`.  An index alone has no layer, source, or
    coordinate information, so it cannot provide the ownership guarantees
    required by field and mesh visualizations.
    """

    if count <= limit:
        return list(range(count))
    if limit <= 1:
        return [0]
    return sorted({round(index * (count - 1) / (limit - 1)) for index in range(limit)})


def _canonical_json(value: Any) -> str:
    """Serialize mixed result records into an order-independent stable key."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _record_identity(record: Dict[str, Any]) -> str:
    """Return a stable identity without relying on producer list order."""

    identity = {
        "id": record.get("id", ""),
        "source_id": record.get("source_id", ""),
        "source_kind": record.get("source_kind", record.get("kind", "")),
        "component_ref": record.get("component_ref", record.get("component_id", "")),
        "net": record.get("net", record.get("net_name", "")),
        "layer": record.get("layer", ""),
        "layers": record.get("layers", record.get("span", "")),
        "vertices_mm": record.get("vertices_mm", ""),
        "position_mm": record.get("position_mm", ""),
        "start_mm": record.get("start_mm", ""),
        "end_mm": record.get("end_mm", ""),
        "x_mm": record.get("x_mm", ""),
        "y_mm": record.get("y_mm", ""),
    }
    return _canonical_json(identity)


def _record_centroid(record: Dict[str, Any]) -> Tuple[float, float]:
    """Extract a deterministic board-plane centroid from a mesh/result record."""

    vertices = record.get("vertices_mm")
    if isinstance(vertices, Sequence) and not isinstance(vertices, (str, bytes)):
        points = [point for point in vertices if isinstance(point, Sequence) and len(point) >= 2]
        if points:
            return (
                sum(float(point[0]) for point in points) / len(points),
                sum(float(point[1]) for point in points) / len(points),
            )
    for key in ("position_mm", "at", "center_mm", "start_mm", "end_mm"):
        point = record.get(key)
        if isinstance(point, Sequence) and not isinstance(point, (str, bytes)) and len(point) >= 2:
            return float(point[0]), float(point[1])
    return float(record.get("x_mm", 0.0)), float(record.get("y_mm", 0.0))


def _representation_key(record: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """Group samples by board ownership before distributing visual budget."""

    source_kind = str(record.get("source_kind", record.get("kind", "unknown")))
    component = str(record.get("component_ref", record.get("component_id", "")))
    source_id = str(record.get("source_id", record.get("id", "")))
    # A component bond may emit several geometry records with a shared source
    # identifier.  Keep the component identity in the stratum as well so one
    # component cannot hide another during preview admission.
    source = f"{source_id}|{component}" if component else source_id
    return (
        str(record.get("net", record.get("net_name", ""))),
        str(record.get("layer", record.get("span", ""))),
        source_kind,
        source,
    )


def _category_key(record: Dict[str, Any]) -> Tuple[str, str, str]:
    representation = _representation_key(record)
    return representation[:3]


def _numeric_value(record: Dict[str, Any], value_key: str | None) -> float | None:
    if not value_key:
        return None
    value = record.get(value_key)
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric and abs(numeric) != float("inf") else None


def stratified_sample_records(
    records: Iterable[Dict[str, Any]],
    limit: int,
    *,
    value_key: str | None = None,
) -> List[Dict[str, Any]]:
    """Deterministically downsample records without producer-order bias.

    The policy first reserves global numeric extrema when a value field is
    supplied, then preserves net/layer/source-kind categories and individual
    source/component groups.  Remaining budget is distributed across spatial
    bins before a stable hash-based fill.  The returned order is canonical, so
    reordering the producer's input yields exactly the same selected records.
    """

    budget = max(0, int(limit))
    ordered = sorted((dict(record) for record in records), key=_record_identity)
    if budget == 0 or not ordered:
        return []
    if len(ordered) <= budget:
        return ordered

    identities = [_record_identity(record) for record in ordered]
    selected: set[str] = set()

    def choose(record: Dict[str, Any]) -> bool:
        identity = _record_identity(record)
        if identity in selected or len(selected) >= budget:
            return False
        selected.add(identity)
        return True

    valued = [
        (value, identity, record)
        for identity, record in zip(identities, ordered)
        if (value := _numeric_value(record, value_key)) is not None
    ]
    if valued:
        choose(min(valued, key=lambda item: (item[0], item[1]))[2])
        choose(max(valued, key=lambda item: (item[0], item[1]))[2])

    categories: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    representations: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for record in ordered:
        categories[_category_key(record)].append(record)
        representations[_representation_key(record)].append(record)

    # Preserve visible layer/source-kind categories before deeper per-source detail.
    for key in sorted(categories):
        choose(categories[key][0])
    for key in sorted(representations):
        choose(representations[key][0])

    if len(selected) < budget:
        centers = {identity: _record_centroid(record) for identity, record in zip(identities, ordered)}
        xs = [point[0] for point in centers.values()]
        ys = [point[1] for point in centers.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1e-12)
        span_y = max(max_y - min_y, 1e-12)
        cells_per_axis = max(1, min(128, int(ceil(sqrt(budget)))))
        aspect = sqrt(span_x / span_y)
        bins_x = max(1, min(128, int(round(cells_per_axis * aspect))))
        bins_y = max(1, min(128, int(ceil(cells_per_axis / max(aspect, 1e-12)))))

        spatial: Dict[Tuple[Tuple[str, str, str], int, int, Tuple[str, str, str, str]], List[Dict[str, Any]]] = defaultdict(list)
        for identity, record in zip(identities, ordered):
            x, y = centers[identity]
            x_bin = min(bins_x - 1, int((x - min_x) / span_x * bins_x))
            y_bin = min(bins_y - 1, int((y - min_y) / span_y * bins_y))
            spatial[(_category_key(record), x_bin, y_bin, _representation_key(record))].append(record)

        # Round-robin categories prevents a dense plane from starving vias,
        # pads, or another copper layer while still covering its own extent.
        per_category: Dict[Tuple[str, str, str], deque[Dict[str, Any]]] = defaultdict(deque)
        for key in sorted(spatial):
            per_category[key[0]].append(spatial[key][0])
        while len(selected) < budget and any(per_category.values()):
            progressed = False
            for key in sorted(per_category):
                if per_category[key]:
                    progressed = choose(per_category[key].popleft()) or progressed
                    if len(selected) >= budget:
                        break
            if not progressed:
                break

    # Fill remaining capacity using a stable hash, not source insertion order.
    for record in sorted(
        ordered,
        key=lambda item: (sha256(_record_identity(item).encode("utf-8")).hexdigest(), _record_identity(item)),
    ):
        choose(record)
        if len(selected) >= budget:
            break

    return [record for record in ordered if _record_identity(record) in selected]


def terminal_resistance(item: Dict[str, Any], spec: AnalysisSpec) -> float:
    package_models = spec.options.get("package_models", {})
    model = package_models.get(str(item.get("component_ref", "")), {}) if isinstance(package_models, dict) else {}
    return max(
        0.0,
        sum(
            float(value or 0)
            for value in (
                item.get("series_resistance_ohm", 0),
                item.get("contact_resistance_ohm", model.get("contact_resistance_ohm", 0)),
                item.get("package_resistance_ohm", model.get("package_resistance_ohm", 0)),
            )
        ),
    )


def terminal_net(spec: AnalysisSpec, item: Dict[str, Any]) -> str:
    explicit = str(item.get("net") or item.get("net_name") or "")
    if explicit:
        return explicit
    return spec.net_names[0] if len(spec.net_names) == 1 else ""
