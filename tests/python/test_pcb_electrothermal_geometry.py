# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""PCB solver-mesh to retained electrothermal-body bridge tests."""
from __future__ import annotations

import copy
import unittest

from python.spike_core.assembly_electrothermal_setup import prepare_electrothermal
from python.spike_core.assembly_field_handoff import prepare_assembly_field_handoff
from python.spike_core.pcb_electrothermal_geometry import prepare_pcb_electrothermal_geometry


def mesh(units: str = "mm") -> dict:
    scale = 0.001 if units == "m" else 1.0
    vertices = [[scale * value for value in point] for point in (
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
        [2, 0, 0], [3, 0, 0], [2, 1, 0], [2, 0, 1],
    )]
    cells = [
        {"id": "copper-cell", "kind": "tetrahedron", "vertices": [0, 1, 2, 3],
         "material_id": "local-copper", "source_object_ids": ["trace"]},
        {"id": "core-cell", "kind": "tetrahedron", "vertices": [4, 5, 6, 7],
         "material_id": "local-fr4", "source_object_ids": ["core"]},
    ]
    return {"contract": "spike/solver-mesh/v1", "units": units,
            "coordinate_system": "right_handed_xyz", "vertices": vertices, "cells": cells,
            "counts": {"vertices": 8, "cells": 2},
            "object_map": {"trace": {"kind": "copper", "net": "VCC", "layer": "F.Cu"},
                           "core": {"kind": "board_layer", "layer": "dielectric"}}}


def bridge(occurrence: str, design: str, units: str = "mm") -> dict:
    return prepare_pcb_electrothermal_geometry({
        "contract": "spike/pcb-electrothermal-geometry-request/v1",
        "occurrence_id": occurrence, "reference_id": design,
        "source_sha256": "a" * 64,
        "stack_binding": {"id": "stack", "source_sha256": "b" * 64},
        "material_map": {"local-copper": "copper", "local-fr4": "fr4"},
        "mesh": mesh(units),
    })


def assembly() -> dict:
    return {"contract": "spike/assembly-ir/v1", "assembly_id": "pcb-pair", "name": "PCB pair",
            "boards": [
                {"id": "left", "design_id": "board-design",
                 "frame": {"frame_id": "left-frame", "parent_frame_id": "assembly"}},
                {"id": "right", "design_id": "board-design",
                 "frame": {"frame_id": "right-frame", "parent_frame_id": "assembly",
                           "transform": [0, -1, 0, 10, 1, 0, 0, 0,
                                         0, 0, 1, 0, 0, 0, 0, 1]}},
            ]}


class PcbElectrothermalGeometryTests(unittest.TestCase):
    def test_repeated_mesh_units_rotation_and_complete_provenance(self):
        left_request = {"contract": "spike/pcb-electrothermal-geometry-request/v1",
                        "occurrence_id": "left", "reference_id": "board-design",
                        "source_sha256": "a" * 64,
                        "stack_binding": {"id": "stack", "source_sha256": "b" * 64},
                        "material_map": {"local-copper": "copper", "local-fr4": "fr4"},
                        "mesh": mesh("mm")}
        before = copy.deepcopy(left_request)
        left = prepare_pcb_electrothermal_geometry(left_request)
        right = bridge("right", "board-design", "m")
        self.assertEqual(left_request, before)
        self.assertEqual(len(left["body"]["boundary_faces"]), 8)
        self.assertEqual(left["body"]["mesh"]["cells"], before["mesh"]["cells"])
        self.assertEqual(left["cell_ownership"]["copper-cell"]["net_ids"], ["VCC"])
        self.assertEqual(left["cell_ownership"]["copper-cell"]["layer_ids"], ["F.Cu"])
        self.assertEqual(left["cell_ownership"]["core-cell"]["net_ids"], [])
        geometry = {"contract": "spike/assembly-field-handoff-request/v1",
                    "assembly": assembly(), "domain": "thermal",
                    "bodies": [left["body"], right["body"]],
                    "materials": [
                        {"id": "copper", "thermal_conductivity_w_mk": 390,
                         "provenance": "Original synthetic copper fixture"},
                        {"id": "fr4", "thermal_conductivity_w_mk": 0.3,
                         "provenance": "Original synthetic FR4 fixture"},
                    ]}
        handoff = prepare_assembly_field_handoff(geometry)
        self.assertEqual(handoff["mesh"]["counts"], {"vertices": 16, "cells": 4})
        self.assertEqual({trace["occurrence_id"] for trace in handoff["source_traceability"]},
                         {"left", "right"})
        self.assertEqual(handoff["source_traceability"][1]["world_transform_mm"][0:4],
                         [0.0, -1.0, 0.0, 10.0])
        self.assertAlmostEqual(handoff["source_traceability"][0]["volume_m3"],
                               handoff["source_traceability"][1]["volume_m3"], places=20)

    def test_loss_cell_and_terminal_face_ownership_feed_existing_setup(self):
        prepared = [bridge("left", "board-design"), bridge("right", "board-design")]
        copper_faces = []
        for item in prepared:
            candidates = [face for face in item["boundary_face_ownership"]
                          if face["cell_id"] == "copper-cell"]
            self.assertEqual(len(candidates), 4)
            self.assertTrue(all(face["physical_material_id"] == "copper" and
                                face["source_object_ids"] == ["trace"] and face["net_ids"] == ["VCC"]
                                for face in candidates))
            copper_faces.append(candidates[0])
        geometry = {"contract": "spike/assembly-field-handoff-request/v1",
                    "assembly": assembly(), "domain": "thermal",
                    "bodies": [item["body"] for item in prepared],
                    "materials": [
                        {"id": "copper", "thermal_conductivity_w_mk": 390,
                         "provenance": "Original synthetic copper fixture"},
                        {"id": "fr4", "thermal_conductivity_w_mk": 0.3,
                         "provenance": "Original synthetic FR4 fixture"},
                    ]}
        request = {"contract": "spike/assembly-electrothermal-request/v1", "geometry": geometry,
                   "thermal_problem": {"contract": "spike/assembly-field-thermal-problem/v1",
                                       "boundaries": [], "heat_sources": [], "contacts": []},
                   "electrical": {"materials": [
                       {"id": "copper", "conductivity_s_m": 5.8e7,
                        "temperature_coefficient_per_k": 0.0039, "reference_temperature_k": 300,
                        "temperature_range_k": [250, 400]},
                       {"id": "fr4", "conductivity_s_m": 0,
                        "temperature_coefficient_per_k": 0, "reference_temperature_k": 300,
                        "temperature_range_k": [250, 400]},
                   ], "terminals": [
                       {"id": "source", "face": {"occurrence_id": "left",
                                                   "face_id": copper_faces[0]["face_id"]}, "voltage_v": 1},
                       {"id": "return", "face": {"occurrence_id": "right",
                                                   "face_id": copper_faces[1]["face_id"]}, "voltage_v": 0},
                   ], "contacts": []},
                   "heat_sources": [{"contract": "spike/electrical-heat-source/v1", "id": "loss",
                                     "model": {"kind": "spectral_resistive", "frequency_hz": [0],
                                               "rms_current_a": [1], "resistance_ohm": [1]},
                                     "distribution": [{"occurrence_id": "left", "cell_id": "copper-cell",
                                                       "weight": 1}],
                                     "provenance": {"source_sha256": "c" * 64,
                                                    "description": "Original synthetic loss fixture"}}],
                   "loss_accounting": "explicit_nonoverlapping_losses",
                   "iteration": {"initial_temperature_k": 300, "max_iterations": 5, "relaxation": 0.5,
                                 "temperature_tolerance_k": 0.1, "power_relative_tolerance": 0.01}}
        setup = prepare_electrothermal(request)
        self.assertEqual(set(setup["local_cells"]),
                         {("left", "copper-cell"), ("left", "core-cell"),
                          ("right", "copper-cell"), ("right", "core-cell")})
        self.assertEqual(len(setup["terminals"]), 2)
        self.assertEqual(setup["terminals"][0]["vertices"],
                         next(face["vertices"] for face in setup["handoff"]["boundary_faces"]
                              if face["occurrence_id"] == "left" and
                              face["local_face_id"] == copper_faces[0]["face_id"]))

    def test_rejects_incomplete_provenance_materials_and_nonmanifold_cells(self):
        cases = []
        unused = mesh()
        unused["object_map"]["unused"] = {"kind": "copper", "net": "FLOAT", "layer": "B.Cu"}
        cases.append((unused, {"local-copper": "copper", "local-fr4": "fr4"}, "source object"))
        missing_material = mesh()
        missing_material["cells"][1]["material_id"] = "undeclared"
        cases.append((missing_material, {"local-copper": "copper", "local-fr4": "fr4"}, "material_map"))
        nonmanifold = mesh()
        nonmanifold["vertices"].extend([[0, 0, -1], [0, 0, 2]])
        nonmanifold["cells"] = [nonmanifold["cells"][0],
                                {**nonmanifold["cells"][0], "id": "second", "vertices": [0, 2, 1, 8]},
                                {**nonmanifold["cells"][0], "id": "third", "vertices": [0, 1, 2, 9]}]
        nonmanifold["counts"] = {"vertices": 10, "cells": 3}
        nonmanifold["object_map"] = {"trace": nonmanifold["object_map"]["trace"]}
        cases.append((nonmanifold, {"local-copper": "copper"}, "non-manifold"))
        for candidate, material_map, message in cases:
            raw = {"contract": "spike/pcb-electrothermal-geometry-request/v1",
                   "occurrence_id": "left", "reference_id": "board-design", "source_sha256": "a" * 64,
                   "stack_binding": {"id": "stack", "source_sha256": "b" * 64},
                   "material_map": material_map, "mesh": candidate}
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                prepare_pcb_electrothermal_geometry(raw)

    def test_malformed_indices_unhashable_fields_and_oversize_fail_before_faces(self):
        mutations = [
            (lambda value: value["mesh"]["cells"][0].update(material_id=["not", "hashable"]),
             "local material id"),
            (lambda value: value["mesh"]["cells"][0].update(source_object_ids=[["not-hashable"]]),
             "source ownership"),
            (lambda value: value["mesh"]["cells"][0].update(vertices=[0, 1, 2, "3"]),
             "integer indices"),
            (lambda value: value["mesh"]["cells"][0].update(vertices=[0, 1, 2, 80]),
             "integer indices"),
            (lambda value: value["mesh"]["vertices"][0].__setitem__(0, []),
             "vertex coordinates"),
        ]
        for mutation, message in mutations:
            raw = {"contract": "spike/pcb-electrothermal-geometry-request/v1",
                   "occurrence_id": "left", "reference_id": "board-design", "source_sha256": "a" * 64,
                   "stack_binding": {"id": "stack", "source_sha256": "b" * 64},
                   "material_map": {"local-copper": "copper", "local-fr4": "fr4"}, "mesh": mesh()}
            mutation(raw)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                prepare_pcb_electrothermal_geometry(raw)

        oversized = mesh()
        oversized["cells"] = [oversized["cells"][0]] * 100_001
        oversized["counts"] = {"vertices": len(oversized["vertices"]), "cells": len(oversized["cells"])}
        raw = {"contract": "spike/pcb-electrothermal-geometry-request/v1",
               "occurrence_id": "left", "reference_id": "board-design", "source_sha256": "a" * 64,
               "stack_binding": {"id": "stack", "source_sha256": "b" * 64},
               "material_map": {"local-copper": "copper"}, "mesh": oversized}
        with self.assertRaisesRegex(ValueError, "control budget|cell budget"):
            prepare_pcb_electrothermal_geometry(raw)


if __name__ == "__main__":
    unittest.main()
