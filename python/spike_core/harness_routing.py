"""Bounded rectilinear cable routing around explicitly declared keepout boxes."""
from __future__ import annotations

import heapq
import math


def point(value, label="Point"):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{label} requires XYZ millimetres.")
    result = tuple(float(v) for v in value)
    if not all(math.isfinite(v) for v in result):
        raise ValueError(f"{label} must be finite.")
    return result


def route_cable(start, end, keepouts=(), clearance_mm=2.0, waypoints=()):
    """A* on obstacle-face coordinates; fail explicitly on search exhaustion.

    Boxes represent forbidden volumes, not an enclosure's outer bounding box.
    Corners are geometric polylines, not bend-radius-qualified cable geometry.
    """
    start, end = point(start), point(end)
    clearance = float(clearance_mm)
    if not math.isfinite(clearance) or clearance < 0:
        raise ValueError("Cable clearance must be finite and non-negative.")
    if len(keepouts) > 24 or len(waypoints) > 32:
        raise ValueError("Cable routing admits at most 24 keepouts and 32 waypoints.")
    boxes = []
    for box in keepouts:
        lo, hi = point(box["min_mm"]), point(box["max_mm"])
        if any(a >= b for a, b in zip(lo, hi)):
            raise ValueError("Keepout minimum must be below maximum on every axis.")
        boxes.append((tuple(v - clearance for v in lo), tuple(v + clearance for v in hi)))

    def inside(p):
        return any(all(lo[i] < p[i] < hi[i] for i in range(3)) for lo, hi in boxes)

    def clear(a, b):
        axis = next((i for i in range(3) if a[i] != b[i]), 0)
        for lo, hi in boxes:
            if all(lo[i] < a[i] < hi[i] for i in range(3) if i != axis):
                if max(min(a[axis], b[axis]), lo[axis]) < min(max(a[axis], b[axis]), hi[axis]):
                    return False
        return True

    anchors = [start, *[point(p, "Waypoint") for p in waypoints], end]
    if any(inside(p) for p in anchors):
        raise ValueError("A connector or waypoint is inside an inflated cable keepout.")
    route = [start]
    expanded = 0
    for a, b in zip(anchors, anchors[1:]):
        axes = [sorted({a[i], b[i], *[v[i] for box in boxes for v in box]}) for i in range(3)]
        source = tuple(axes[i].index(a[i]) for i in range(3))
        target = tuple(axes[i].index(b[i]) for i in range(3))
        def position(node):
            return tuple(axes[i][node[i]] for i in range(3))
        def distance(p, q):
            return sum(abs(x - y) for x, y in zip(p, q))
        queue = [(distance(a, b), 0.0, source)]
        costs, previous = {source: 0.0}, {}
        while queue:
            _, cost, node = heapq.heappop(queue)
            if cost != costs[node]:
                continue
            if node == target:
                break
            expanded += 1
            if expanded > 100000:
                raise ValueError("Cable route search exceeded 100000 nodes; simplify keepouts or add waypoints.")
            p = position(node)
            for axis in range(3):
                for direction in (-1, 1):
                    next_node = list(node)
                    next_node[axis] += direction
                    if not 0 <= next_node[axis] < len(axes[axis]):
                        continue
                    neighbor = tuple(next_node)
                    q = position(neighbor)
                    if not clear(p, q):
                        continue
                    candidate = cost + distance(p, q)
                    if candidate < costs.get(neighbor, math.inf):
                        costs[neighbor], previous[neighbor] = candidate, node
                        heapq.heappush(queue, (candidate + distance(q, b), candidate, neighbor))
        else:
            raise ValueError("No cable route found through the declared keepouts.")
        nodes = [target]
        while nodes[-1] != source:
            nodes.append(previous[nodes[-1]])
        route.extend(position(n) for n in reversed(nodes[:-1]))
    simplified = []
    for p in route:
        if simplified and p == simplified[-1]:
            continue
        if len(simplified) >= 2:
            a, b = simplified[-2:]
            if any(all(a[i] == b[i] == p[i] for i in range(3) if i != axis) and min(a[axis], p[axis]) <= b[axis] <= max(a[axis], p[axis]) for axis in range(3)):
                simplified.pop()
        simplified.append(p)
    return {"route_mm": simplified, "routed_length_mm": sum(math.dist(a, b) for a, b in zip(simplified, simplified[1:])), "expanded_nodes": expanded}
