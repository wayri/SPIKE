"""Exact per-layer copper-land profiles shared by typed DesignIR entities."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Mapping, Sequence


def _text(value: Any, default: str = "") -> str:
    result = str(value or "").strip()
    return result or default


def _point(value: Any) -> tuple[float, float]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 2:
        return float(value[0]), float(value[1])
    return 0.0, 0.0


@dataclass(frozen=True)
class LandProfile:
    """One exact, source-declared REGULAR copper land on one layer."""

    layer_id: str
    use: str
    shape: str
    size_mm: tuple[float, float]
    offset_mm: tuple[float, float] = (0.0, 0.0)
    source_primitive_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "size_mm", _point(self.size_mm))
        object.__setattr__(self, "offset_mm", _point(self.offset_mm))
        if not self.layer_id:
            raise ValueError("Land profiles require a layer identity.")
        if self.use != "regular" or self.shape not in {"circle", "rect"}:
            raise ValueError("Only REGULAR circle/rectangle land profiles are currently lossless.")
        if not all(math.isfinite(value) for value in (*self.size_mm, *self.offset_mm)) or min(self.size_mm) <= 0:
            raise ValueError("Land-profile dimensions and offsets must be finite and dimensions positive.")
        if self.shape == "circle" and not math.isclose(self.size_mm[0], self.size_mm[1], rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("Circular land profiles require equal dimensions.")


def land_profiles_from_v1(raw: Mapping[str, Any], layer_ids: Mapping[str, str]) -> List[LandProfile]:
    profiles: List[LandProfile] = []
    for item in raw.get("land_profiles", []):
        if not isinstance(item, Mapping):
            raise ValueError("Land profiles must be objects.")
        source_layer = _text(item.get("layer_id", item.get("layer")))
        profiles.append(LandProfile(
            layer_id=layer_ids.get(source_layer, source_layer),
            use=_text(item.get("use"), "regular").lower(),
            shape=_text(item.get("shape")).lower(),
            size_mm=_point(item.get("size_mm", item.get("size"))),
            offset_mm=_point(item.get("offset_mm", item.get("offset", (0.0, 0.0)))),
            source_primitive_id=_text(item.get("source_primitive_id", item.get("primitive_id"))),
        ))
    return profiles


def hydrate_land_profiles(values: Dict[str, Any]) -> Dict[str, Any]:
    values["land_profiles"] = [
        item if isinstance(item, LandProfile) else LandProfile(**dict(item))
        for item in values.get("land_profiles", [])
    ]
    return values


def project_land_profiles_to_v1(
    profiles: Sequence[LandProfile], layer_names: Mapping[str, str],
) -> List[Dict[str, Any]]:
    return [{
        "layer_id": layer_names.get(item.layer_id, item.layer_id), "use": item.use,
        "shape": item.shape, "size_mm": list(item.size_mm), "offset_mm": list(item.offset_mm),
        "source_primitive_id": item.source_primitive_id,
    } for item in profiles]


def validate_land_profiles(
    pads: Sequence[Any], vias: Sequence[Any], *, layers: Sequence[Any],
) -> None:
    layer_order = {item.id: item.order for item in layers}

    def common(profiles: Sequence[LandProfile]) -> List[str]:
        profile_layers = [item.layer_id for item in profiles]
        if len(profile_layers) != len(set(profile_layers)) or any(item not in layer_order for item in profile_layers):
            raise ValueError("Land-profile layers must be unique canonical layer identities.")
        if profile_layers != sorted(profile_layers, key=layer_order.__getitem__):
            raise ValueError("Land profiles must follow canonical physical layer order.")
        return profile_layers

    for pad in pads:
        if pad.land_profiles and set(common(pad.land_profiles)) != set(pad.layer_ids):
            raise ValueError("Pad land profiles must cover exactly the pad layer identities.")
    for via in vias:
        if not via.land_profiles:
            continue
        profile_layers = common(via.land_profiles)
        if len(profile_layers) < 2 or profile_layers[0] != via.start_layer_id or profile_layers[-1] != via.end_layer_id:
            raise ValueError("Via land profiles must span from the start layer through the end layer.")
