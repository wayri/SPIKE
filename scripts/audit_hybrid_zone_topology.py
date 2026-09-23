# SPDX-License-Identifier: MIT
"""Read-only mesh topology diagnostic for the pinned MODULAR-BUS-NIB DC case."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
import json
from math import hypot
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.contracts import AnalysisSpec
from python.spike_core.convergence import _level_spec
from python.spike_core.hybrid_mesh import _Builder
from python.spike_core.service import _design_from_kicad


def shared_face_length(left, right, tolerance=1e-7):
    """Length in mm of coincident polygon edges; point contact contributes zero."""
    total = 0.0
    for a, b in zip(left, left[1:] + left[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = hypot(dx, dy)
        if length <= tolerance:
            continue
        for c, d in zip(right, right[1:] + right[:1]):
            if max(abs(dx * (v[1] - a[1]) - dy * (v[0] - a[0])) / length for v in (c, d)) > tolerance:
                continue
            lo, hi = sorted(((v[0] - a[0]) * dx / length + (v[1] - a[1]) * dy / length for v in (c, d)))
            total += max(0.0, min(length, hi) - max(0.0, lo))
    return total


class AuditBuilder(_Builder):
    def __init__(self, *args):
        super().__init__(*args)
        self.zone_polygons = {}

    def add_cell(self, *args, **kwargs):
        super().add_cell(*args, **kwargs)
        if args[1] == "zone":
            self.zone_polygons[self.mesh.nodes[-1].id] = list(args[5])


def component_sizes(nodes, branches):
    parents = {node: node for node in nodes}
    def root(node):
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node
    for branch in branches:
        a, b = branch.node_p, branch.node_n
        if a in parents and b in parents:
            parents[root(a)] = root(b)
    return sorted(Counter(root(node) for node in nodes).values(), reverse=True)


def audit(builder, names, solve=False, face_experiment=False):
    mesh = builder.build()
    by_zone = defaultdict(list)
    for branch in mesh.branches:
        if branch.kind == "zone":
            by_zone[branch.source_id].append(branch)
    zones = []
    zone_faces = {}
    for region in builder.zone_regions:
        branches = by_zone[region["source_id"]]
        ratios, zero_faces, examples = [], 0, []
        for branch in branches:
            face = shared_face_length(builder.zone_polygons[branch.node_p], builder.zone_polygons[branch.node_n], builder.containment_tolerance)
            zone_faces[branch.id] = face
            if face <= 1e-7:
                zero_faces += 1
            else:
                ratio = branch.width_mm / face
                ratios.append(ratio)
                if ratio > 3:
                    examples.append({"id": branch.id, "width_mm": branch.width_mm, "shared_face_mm": face,
                                     "ratio": ratio, "start_mm": branch.start_mm, "end_mm": branch.end_mm})
        sizes = component_sizes(region["nodes"], branches)
        zones.append({"id": region["source_id"], "layer": region["layer"], "cell_mm": region["cell_mm"],
                      "nodes": len(region["nodes"]), "branches": len(branches), "components": len(sizes),
                      "largest_component_sizes": sizes[:8], "zero_shared_face_branches": zero_faces,
                      "overwidth_branches_gt_3x": sum(r > 3 for r in ratios),
                      "max_width_to_face_ratio": max(ratios, default=0),
                      "examples": sorted(examples, key=lambda item: item["ratio"], reverse=True)[:3]})
    contacts = {}
    incident_kinds = defaultdict(set)
    for branch in mesh.branches:
        for node in (branch.node_p, branch.node_n):
            incident_kinds[node].add(branch.kind)
    for name, pad in names.items():
        attachments = [branch for branch in mesh.branches if branch.source_id == pad["id"] and "attachment" in branch.kind]
        contacts[name] = [{"id": branch.id, "kind": branch.kind, "layer": branch.layer,
                           "resistance_ohm": branch.resistance_ohm, "length_mm": branch.length_mm,
                           "width_mm": branch.width_mm, "start_mm": branch.start_mm, "end_mm": branch.end_mm,
                           "start_is_zone_cell": branch.node_p in builder.zone_polygons,
                           "start_incident_kinds": sorted(incident_kinds[branch.node_p])}
                          for branch in attachments if branch.layer == "F.Cu"]
    sizes = component_sizes(range(len(mesh.nodes)), mesh.branches)
    report = {"mesh": builder.spec.mesh, "nodes": len(mesh.nodes), "branches": dict(Counter(b.kind for b in mesh.branches)),
            "components": len(sizes), "largest_component_sizes": sizes[:10], "zones": zones,
            "terminal_zone_attachments": contacts, "issues": [issue.__dict__ for issue in mesh.issues]}
    if solve:
        from unittest.mock import patch
        from python.spike_core.hybrid_dc_solver import solve_hybrid_dc
        sources, loads = [dict(x) for x in builder.spec.sources], [dict(x) for x in builder.spec.loads]
        for terminal, name in zip(sources + loads, ["R19.3", "J14.2", "J20.2", "J15.2"]):
            terminal["geometry_anchor"] = {"type": "pad", "id": names[name]["id"]}
        spec = replace(builder.spec, sources=sources, loads=loads,
                       options={**builder.spec.options, "require_exact_terminal_geometry": True, "include_branch_results": True})
        report["dc_experiments"] = []
        removed = [b for b in mesh.branches if b.kind == "pad_attachment" and b.node_p in builder.zone_polygons
                   and b.source_id == names["J14.2"]["id"]]
        variants = [("baseline", mesh)]
        if removed:
            variants.append(("remove_J14_zone_centroid_attachments", replace(mesh, branches=[b for b in mesh.branches if b not in removed])))
        if face_experiment:
            corrected = [replace(b, width_mm=zone_faces[b.id]) if b.kind == "zone" else b for b in mesh.branches
                         if b.kind != "zone" or zone_faces[b.id] > 1e-7]
            variants.append(("diagnostic_shared_face_widths", replace(mesh, branches=corrected)))
        for label, graph in variants:
            with patch("python.spike_core.hybrid_dc_solver.build_hybrid_mesh", return_value=graph):
                result = solve_hybrid_dc(builder.design, spec)
            report["dc_experiments"].append({"label": label, "status": result.status,
                "model_status": result.model_status,
                "paths": result.networks.get("source_to_load", {}).get("paths", []),
                "residual": result.summary.get("max_scaled_linear_residual"),
                "copper_loss_w": result.summary.get("total_copper_loss_w"),
                "baseline_overwidth_zone_loss_w": sum(edge["power_loss_w"] for edge in result.fields.get("branch_results", [])
                    if edge["id"] in zone_faces and edge["width_mm"] > 3 * zone_faces[edge["id"]]),
                "baseline_zero_face_zone_loss_w": sum(edge["power_loss_w"] for edge in result.fields.get("branch_results", [])
                    if edge["id"] in zone_faces and zone_faces[edge["id"]] <= 1e-7),
                "J14_attachments": [{k:edge[k] for k in ["id", "kind", "layer", "current_a", "resistance_ohm", "power_loss_w"]}
                                    for edge in result.fields.get("branch_results", []) if edge.get("source_id") == names["J14.2"]["id"] and "attachment" in edge["kind"]]})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--factors", type=float, nargs="+", default=[2, 1, .5])
    parser.add_argument("--solve", action="store_true", help="Run an in-memory J14 attachment removal experiment")
    parser.add_argument("--face-experiment", action="store_true", help="Also replace full zone widths by actual shared faces; diagnostic only")
    args = parser.parse_args()
    design = _design_from_kicad(str(ROOT / "app/public/demo/MODULAR-BUS-NIB.kicad_pcb"))
    request = json.loads((ROOT / "docs/validation/modular-bus-nib-12vout-dcir-request.json").read_text())
    spec = AnalysisSpec(**request["spec"])
    spec = replace(spec, mesh={**spec.mesh, "solver_memory_limit_gb": 4.0})
    names = {pad["component_pad"]: pad for pad in design.pads if pad.get("component_pad") in {"R19.3", "J14.2", "J20.2", "J15.2"}}
    reports = []
    for index, factor in enumerate(args.factors):
        report = audit(AuditBuilder(design, _level_spec(spec, factor, index)), names, solve=args.solve, face_experiment=args.face_experiment)
        reports.append({"factor": factor, **report})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(reports, indent=2) + "\n")
        # Each of these six retained filled polygons had one zone component
        # before the contact/face repair. Reject loss of positive-area paths.
        if len(report["zones"]) != 6 or any(zone["components"] != 1 for zone in report["zones"]):
            raise AssertionError("Pinned board zone component count changed; inspect written topology evidence")
        if any(zone["zero_shared_face_branches"] or zone["max_width_to_face_ratio"] > 1 + 1e-7 for zone in report["zones"]):
            raise AssertionError("Zone branches exceed retained positive shared-face width")
        print(json.dumps({"factor": factor, "nodes": report["nodes"], "components": report["components"],
                          "zones": len(report["zones"])}), flush=True)


if __name__ == "__main__":
    main()
