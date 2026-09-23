# SPDX-License-Identifier: MIT
"""Indexed face projection must preserve the prior nearest-branch selection."""

import random
import unittest

from python.spike_core.result_face_projection import bind_result_faces, project_result_faces


def legacy_nearest(cell, edges):
    candidates = [edge for edge in edges if edge["source_id"] == cell["source_id"]]
    layer = cell["layer"]
    matching = [edge for edge in candidates if edge["layer"] == layer
                or layer in edge["layer"].split("->")
                or edge["layer"] in layer.split("->")]
    candidates = matching or candidates
    vertices = cell["vertices_mm"]
    center = [sum(vertex[axis] for vertex in vertices) / len(vertices) for axis in range(3)]
    return min(candidates, key=lambda edge: sum((center[axis] - edge[field]) ** 2
                                              for axis, field in enumerate(("x_mm", "y_mm", "z_mm"))))


class IndexedFaceProjectionTests(unittest.TestCase):
    def test_nearest_source_layer_and_stable_ties(self):
        rng = random.Random(20260924)
        edges = []
        for index in range(700):
            edges.append({
                "id": index, "source_id": f"zone-{index % 3}",
                "layer": ("F.Cu", "B.Cu", "F.Cu->B.Cu")[index % 3],
                "x_mm": rng.uniform(-20, 20), "y_mm": rng.uniform(-20, 20),
                "z_mm": rng.uniform(-1, 1), "net": "VCC", "kind": "zone",
            })
        cells = []
        for index in range(300):
            x, y = rng.uniform(-20, 20), rng.uniform(-20, 20)
            cells.append({"id": str(index), "source_id": f"zone-{index % 3}",
                          "layer": ("F.Cu", "B.Cu", "F.Cu->B.Cu")[index % 3],
                          "vertices_mm": [(x, y, 0), (x + .1, y, 0), (x, y + .1, 0)]})
        # Equidistant branches must retain the old first-in-source ordering.
        edges.extend([
            {"id": 700 + i, "source_id": "tie", "layer": "F.Cu", "x_mm": x,
             "y_mm": 0.0, "z_mm": 0.0, "net": "VCC", "kind": "zone"}
            for i, x in enumerate((-1.0, 1.0))
        ])
        cells.append({"id": "tie", "source_id": "tie", "layer": "F.Cu",
                      "vertices_mm": [(0, 0, 0), (0, 0, 0), (0, 0, 0)]})
        bindings = bind_result_faces(cells, edges)
        self.assertEqual([edge["id"] for _, edge, _ in bindings],
                         [legacy_nearest(cell, edges)["id"] for cell in cells])
        first = project_result_faces(cells, edges, lambda edge: float(edge["id"]), bindings=bindings)
        second = project_result_faces(cells, edges, lambda edge: float(edge["id"] * 2), bindings=bindings)
        self.assertEqual([sample["value"] * 2 for sample in first], [sample["value"] for sample in second])
        self.assertEqual([sample["value"] for sample in first],
                         [sample["value"] for sample in project_result_faces(cells, edges, lambda edge: float(edge["id"]))])


if __name__ == "__main__":
    unittest.main()
