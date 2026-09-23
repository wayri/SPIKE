# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Deterministic manual track sizing/split constraints; no CAD node movement."""
import math
from collections.abc import Mapping


def _number(value, label):
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a JSON number")
    try:
        value = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _keys(obj, allowed, label):
    if not isinstance(obj, Mapping) or set(obj) != allowed:
        raise ValueError(f"{label} requires exactly {sorted(allowed)}")


class LocalTrackControls:
    """Refinement-only interval controls addressed by persistent source track ID.

    Fractions are measured along the source start->end direction. A change is
    replayed when rebuilding the mesh; it never changes the supplied DesignIR.
    Other primitive types reject rather than silently ignoring a requested edit.
    """
    def __init__(self, raw, tracks, selected_nets, node_tolerance):
        self.refinements, self.splits = {}, {}
        self.tolerance = _number(node_tolerance, "node_tolerance")
        if self.tolerance <= 0:
            raise ValueError("node_tolerance must be positive")
        if raw is None:
            return
        _keys(raw, {"contract", "refinements", "splits"}, "local_controls")
        if raw["contract"] != "spike/local-track-mesh-controls/v1":
            raise ValueError("Unsupported local mesh control contract")
        source_ids = [str(t.get("id", f"track-{i+1}")) for i,t in enumerate(tracks)]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Manual meshing requires unique source track IDs")
        selected = set(selected_nets)
        admitted = {name for name,t in zip(source_ids, tracks)
                    if not selected or str(t.get("net_name") or t.get("net") or "") in selected}
        rules, splits = raw["refinements"], raw["splits"]
        if not isinstance(rules, list) or not isinstance(splits, list) or len(rules)+len(splits) > 256:
            raise ValueError("At most 256 local controls are admitted")
        def track_id(row):
            name = row["track_id"]
            if not isinstance(name, str) or name not in admitted:
                raise ValueError("Local control must name a known selected track")
            return name
        for row in rules:
            _keys(row, {"track_id", "from_fraction", "to_fraction", "target_size_mm"}, "refinement")
            name = track_id(row)
            start, end = (_number(row[key], key) for key in ("from_fraction", "to_fraction"))
            size = _number(row["target_size_mm"], "target_size_mm")
            if not 0 <= start < end <= 1 or size <= 2*node_tolerance:
                raise ValueError("Refinement requires 0<=from<to<=1 and size >2*node tolerance")
            self.refinements.setdefault(name, []).append((start,end,size))
        for row in splits:
            _keys(row, {"track_id", "fractions"}, "split")
            name = track_id(row)
            values = row["fractions"]
            if not isinstance(values, list) or not 1 <= len(values) <= 256:
                raise ValueError("Split requires 1..256 fractions")
            parsed = [_number(v, "fraction") for v in values]
            if any(not 0 < v < 1 for v in parsed) or len(set(parsed)) != len(parsed):
                raise ValueError("Split fractions must be unique and strictly inside (0,1)")
            if name in self.splits:
                raise ValueError("Use one split record per track")
            self.splits[name] = parsed

    def fractions(self, name, start, end, target, maximum):
        """Return segment endpoints excluding zero, retaining exact source end."""
        target = _number(target, "target")
        if target <= 0 or type(maximum) is not int or not 1 <= maximum <= 1_000_000:
            raise ValueError("Positive target and branch budget in [1,1000000] required")
        rules, splits = self.refinements.get(name, []), self.splits.get(name, [])
        if not rules and not splits:
            return None  # Preserve the legacy no-control discretization exactly.
        length = math.hypot(end[0]-start[0], end[1]-start[1])
        if not math.isfinite(length) or length <= 2*self.tolerance:
            raise ValueError("Controlled track has insufficient finite length")
        boundaries = sorted({0.,1.,*splits,*(v for a,b,_ in rules for v in (a,b))})
        if any((b-a)*length <= 2*self.tolerance for a,b in zip(boundaries,boundaries[1:])):
            raise ValueError("Manual split/refinement boundaries would collapse mesh nodes")
        result = []
        for a,b in zip(boundaries,boundaries[1:]):
            midpoint = (a+b)/2
            size = min([target]+[h for left,right,h in rules if left <= midpoint <= right])
            ratio = (b-a)*length/size
            if not math.isfinite(ratio) or ratio > maximum:
                raise ValueError("Local refinement exceeds admitted branch capacity")
            count = max(1, math.ceil(ratio))
            if len(result)+count > maximum:
                raise ValueError("Local refinement exceeds admitted branch capacity")
            if (b-a)*length/count <= 2*self.tolerance:
                raise ValueError("Local target would collapse mesh nodes")
            result.extend(a+(b-a)*i/count for i in range(1,count+1))
        result[-1] = 1.
        return result
