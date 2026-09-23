# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Run skew tetra optimization/refinement, RWG construction, and local track sizing.

Writes a new example directory with a tetrahedral VTU visualization and hashed
JSON results. No field solution or deployment qualification is asserted.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.tetra_mesh_refinement import refine_tetra_mesh, _det
from python.spike_core.tetra_mesh_optimization import optimize_tetra_mesh
from python.spike_core.mom_surface_basis import build_surface_basis, divergence
from python.spike_core.contracts import DesignIR, AnalysisSpec
from python.spike_core.hybrid_mesh import build_hybrid_mesh


def fixture():
    points = [[0., 0., 0.], [2., 0., 0.], [.3, 1., 0.], [.2, .2, 1.], [.4, .2, .01]]
    cells, boundary = [], []
    for index, face in enumerate(itertools.combinations(range(4), 3)):
        tet = [*face, 4]
        if _det(points, tet) < 0:
            tet[0], tet[1] = tet[1], tet[0]
        cells.append({"id": f"cell_{index}", "kind": "tetrahedron", "vertices": tet,
                      "material_id": "copper", "source_object_ids": ["body"]})
        boundary.append({"vertices": list(face), "label": "outer"})
    return {"contract": "spike/solver-mesh/v1", "units": "m", "coordinate_system": "right_handed_xyz",
            "vertices": points, "cells": cells, "object_map": {"body": {"kind": "solid"}},
            "counts": {"vertices": 5, "cells": 4}}, boundary


def vtu(mesh):
    root = ET.Element("VTKFile", type="UnstructuredGrid", version="0.1", byte_order="LittleEndian")
    piece = ET.SubElement(ET.SubElement(root, "UnstructuredGrid"), "Piece",
        NumberOfPoints=str(len(mesh["vertices"])), NumberOfCells=str(len(mesh["cells"])))
    points = ET.SubElement(ET.SubElement(piece, "Points"), "DataArray", type="Float64",
                           NumberOfComponents="3", format="ascii")
    points.text = " ".join(str(x) for p in mesh["vertices"] for x in p)
    cells = ET.SubElement(piece, "Cells")
    for name, values, dtype in (("connectivity", [v for c in mesh["cells"] for v in c["vertices"]], "Int64"),
                               ("offsets", [4*(i+1) for i in range(len(mesh["cells"]))], "Int64"),
                               ("types", [10]*len(mesh["cells"]), "UInt8")):
        ET.SubElement(cells, "DataArray", type=dtype, Name=name, format="ascii").text = " ".join(map(str, values))
    return ET.tostring(root, encoding="unicode")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        parser.error("output must be a new directory")
    mesh, boundary = fixture()
    optimized = optimize_tetra_mesh(mesh, boundary)
    refined = refine_tetra_mesh(optimized["mesh"], [[0, 1]], boundary)
    mesh = refined["mesh"]
    triangles = []
    for face in refined["boundary_triangles"]:
        tri = face["vertices"][:]
        owner = next(c for c in mesh["cells"] if set(tri) <= set(c["vertices"]))
        opposite = next(v for v in owner["vertices"] if v not in tri)
        if _det(mesh["vertices"], tri + [opposite]) > 0:
            tri[0], tri[1] = tri[1], tri[0]
        triangles.append(tri)
    # Surface basis admits only referenced vertices: compact the boundary explicitly.
    used = sorted({v for tri in triangles for v in tri})
    mapping = {v: i for i, v in enumerate(used)}
    surface = build_surface_basis([mesh["vertices"][v] for v in used],
                                  [[mapping[v] for v in tri] for tri in triangles])
    defect = max(abs(divergence(surface, i, e.plus_face)*surface.areas_m2[e.plus_face]
                     + divergence(surface, i, e.minus_face)*surface.areas_m2[e.minus_face])
                 for i, e in enumerate(surface.edges))
    design = DesignIR(tracks=[{"id": "trace", "net_name": "SIG", "layer": "F.Cu",
        "start": [0, 0], "end": [10, 0], "width": .2}])
    spec = AnalysisSpec(net_names=["SIG"], mesh={"target_size_mm": 1., "feature_aware": False,
        "local_controls": {"contract": "spike/local-track-mesh-controls/v1",
            "refinements": [{"track_id": "trace", "from_fraction": .2, "to_fraction": .8, "target_size_mm": .2}],
            "splits": [{"track_id": "trace", "fractions": [.35]}]}})
    track = build_hybrid_mesh(design, spec)
    report = {"status": "completed", "production_qualified": False,
        "tetra_counts": mesh["counts"], "optimization": optimized["quality"],
        "refinement": refined["quality"], "rwg_basis_count": len(surface.edges),
        "rwg_boundary_edges": len(surface.boundary_edges), "integrated_divergence_defect_m": defect,
        "track_branches": len(track.branches), "track_length_mm": sum(b.length_mm for b in track.branches),
        "scope": "Mesh and basis operation only; no MoM/FEM field solve"}
    output.mkdir(parents=True)
    for name, value in (("mesh.json", mesh), ("boundary.json", refined["boundary_triangles"]),
                         ("track-analysis.json", spec.to_dict()), ("report.json", report)):
        (output/name).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    (output/"mesh.vtu").write_text(vtu(mesh), encoding="utf-8")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    (output/"SHA256.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print(json.dumps(report, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
