# SPDX-License-Identifier: Apache-2.0
"""KLayout batch probe for bounded, read-only layout inspection.

This script is executed by KLayout's embedded Python runtime.  It deliberately
uses only the database API: no Qt modules, DRC, LVS, extraction, or layout
write operation is involved.
"""

from __future__ import annotations

import json
import math

import pya


CONTRACT = "spikes/klayout-layout-inspection/v1"


def _required_text(name):
    value = globals().get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing runtime variable: " + name)
    return value


def _required_limit(name):
    value = int(_required_text(name))
    if value <= 0:
        raise ValueError(name + " must be positive")
    return value


def _bbox(box, dbu_um):
    if box is None or box.empty():
        return {"bbox_dbu": None, "bbox_um": None}
    coordinates = [int(box.left), int(box.bottom), int(box.right), int(box.top)]
    return {
        "bbox_dbu": coordinates,
        "bbox_um": [coordinate * dbu_um for coordinate in coordinates],
    }


def _vector(vector):
    return [int(vector.x), int(vector.y)]


def _transform(instance, dbu_um):
    transform = instance.cplx_trans
    offset = _vector(transform.disp)
    return {
        "magnification": float(transform.mag),
        "rotation_degrees": float(transform.angle),
        "mirrored": bool(transform.mirror),
        "offset_dbu": offset,
        "offset_um": [coordinate * dbu_um for coordinate in offset],
    }


def _version():
    application = pya.Application.instance()
    if application is None:
        return "unavailable"
    value = application.version()
    return str(value)[:256] if value else "unavailable"


def inspect():
    input_layout = _required_text("input_layout")
    max_cells = _required_limit("max_cells")
    max_layers = _required_limit("max_layers")
    max_instances = _required_limit("max_instances")
    max_shapes = _required_limit("max_shapes")
    max_cell_layer_pairs = _required_limit("max_cell_layer_pairs")

    layout = pya.Layout()
    layout.read(input_layout)
    dbu_um = float(layout.dbu)
    if not math.isfinite(dbu_um) or dbu_um <= 0.0:
        raise ValueError("layout database unit must be finite and positive")

    cells = list(layout.each_cell())
    layer_indices = [int(index) for index in layout.layer_indices()]
    if len(cells) > max_cells:
        raise ValueError("layout cell count exceeds max_cells")
    if len(layer_indices) > max_layers:
        raise ValueError("layout layer count exceeds max_layers")
    if len(cells) * len(layer_indices) > max_cell_layer_pairs:
        raise ValueError("layout cell/layer matrix exceeds max_cell_layer_pairs")

    top_indices = {int(cell.cell_index()) for cell in layout.top_cells()}
    cell_records = []
    hierarchy_edges = 0
    hierarchy_occurrences = 0
    defined_shapes = 0

    for cell in cells:
        direct_shapes = []
        direct_shape_count = 0
        for layer_index in layer_indices:
            count = int(cell.shapes(layer_index).size())
            if count:
                direct_shapes.append({"layer_index": layer_index, "count": count})
                direct_shape_count += count
        defined_shapes += direct_shape_count
        if defined_shapes > max_shapes:
            raise ValueError("layout defined shape count exceeds max_shapes")

        children = []
        for instance in cell.each_inst():
            hierarchy_edges += 1
            occurrence_count = int(instance.cell_inst.size())
            hierarchy_occurrences += occurrence_count
            if hierarchy_edges > max_instances or hierarchy_occurrences > max_instances:
                raise ValueError("layout hierarchy exceeds max_instances")
            child = instance.cell
            record = {
                "child_index": int(instance.cell_index),
                "child_name": str(child.name)[:1024],
                "occurrence_count": occurrence_count,
                "regular_array": bool(instance.is_regular_array()),
                "array_shape": [int(instance.na), int(instance.nb)],
                "array_a_dbu": _vector(instance.a),
                "array_b_dbu": _vector(instance.b),
                "transform": _transform(instance, dbu_um),
            }
            record.update(_bbox(instance.bbox(), dbu_um))
            children.append(record)

        cell_index = int(cell.cell_index())
        record = {
            "index": cell_index,
            "name": str(cell.name)[:1024],
            "is_top": cell_index in top_indices,
            "direct_shape_count": direct_shape_count,
            "direct_shapes": direct_shapes,
            "children": children,
        }
        record.update(_bbox(cell.bbox(), dbu_um))
        cell_records.append(record)

    layer_records = []
    for layer_index in layer_indices:
        info = layout.get_info(layer_index)
        count = sum(int(cell.shapes(layer_index).size()) for cell in cells)
        boxes = [cell.bbox(layer_index) for cell in layout.top_cells()]
        nonempty = [box for box in boxes if not box.empty()]
        if nonempty:
            left = min(box.left for box in nonempty)
            bottom = min(box.bottom for box in nonempty)
            right = max(box.right for box in nonempty)
            top = max(box.top for box in nonempty)
            layer_box = pya.Box(left, bottom, right, top)
        else:
            layer_box = None
        record = {
            "index": layer_index,
            "layer": int(info.layer),
            "datatype": int(info.datatype),
            "name": str(info.name)[:1024],
            "defined_shape_count": count,
        }
        record.update(_bbox(layer_box, dbu_um))
        layer_records.append(record)

    top_cells = [
        {
            "index": record["index"],
            "name": record["name"],
            "bbox_dbu": record["bbox_dbu"],
            "bbox_um": record["bbox_um"],
        }
        for record in cell_records if record["is_top"]
    ]
    return {
        "contract": CONTRACT,
        "status": "inspected",
        "engine": {"id": "klayout", "version": _version()},
        "model_status": "read_only_inspection",
        "units": {
            "dbu_um": dbu_um,
            "integer_coordinates": "database_units",
            "physical_coordinates": "micrometres",
        },
        "summary": {
            "cell_count": len(cell_records),
            "top_cell_count": len(top_cells),
            "layer_count": len(layer_records),
            "defined_shape_count": defined_shapes,
            "hierarchy_edge_count": hierarchy_edges,
            "hierarchy_occurrence_count": hierarchy_occurrences,
        },
        "top_cells": top_cells,
        "cells": cell_records,
        "layers": layer_records,
        "capabilities": {
            "layout_inspection": True,
            "layout_modification": False,
            "drc": False,
            "lvs": False,
            "pex": False,
        },
        "limitations": [
            "Shape counts cover definitions stored in cells, not flattened occurrence counts.",
            "Cell, layer, hierarchy, and shape limits are checked after KLayout reads the file; they do not hard-bound parser memory.",
            "This inspection does not perform DRC, LVS, parasitic extraction, or electrical validation.",
            "The KLayout child process is a process boundary, not a security sandbox.",
        ],
    }


def main():
    report_path = _required_text("report_path")
    try:
        report = inspect()
    except Exception as exc:
        report = {
            "contract": CONTRACT,
            "status": "failed",
            "error": {
                "code": "klayout_probe_failed",
                "detail": (type(exc).__name__ + ": " + str(exc))[:4096],
            },
        }
        with open(report_path, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
        raise
    with open(report_path, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")


main()
