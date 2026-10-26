# SPDX-License-Identifier: Apache-2.0
"""Retained physical witnesses and volume ranks must survive adversarial replay."""
from copy import deepcopy
import unittest
import numpy as np
from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0 import solve_tetra_dc
from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0_evidence import validate_tetra_dc
from python.spike_core.solvers.power_integrity.dc.dc_tetra_density import tetra_density_enclosure
from tests.python.test_assembly_tetra_thermal import cube, faces_at


def request():
    mesh = cube(2)
    return {"contract": "spike/tetra-dc-rt0-request/v1", "mesh": mesh,
            "conductivity_s_m": {c["id"]: 2. for c in mesh["cells"]},
            "contacts": [{"id": "left", "faces": faces_at(mesh, 0), "current_a": 1.},
                         {"id": "right", "faces": faces_at(mesh, 1), "current_a": -1.}]}


class TetraEvidenceTests(unittest.TestCase):
    def test_fresh_fields_and_adversarial_physical_witnesses(self):
        out = solve_tetra_dc(request()); validate_tetra_dc(out)
        for change in (lambda r: r["cells"][0]["outward_face_current_a"].__setitem__(0, 1.),
                       lambda r: r["cells"][0]["vertex_density_a_m2"][0].__setitem__(0, 1e20),
                       lambda r: r["cells"][0].__setitem__("volume_m3", 1.),
                       lambda r: r["cells"][0].__setitem__("mean_potential_v", 1e308),
                       lambda r: r["cells"][0].__setitem__("joule_heat_w", 0.),
                       lambda r: r["cells"][0].__setitem__("source_object_ids", ["forged"]),
                       lambda r: r["cells"].pop(),
                       lambda r: r["face_potential_v"].__setitem__(r["gauge_face_ids"][0], 1.),
                       lambda r: r["contacts"][0].__setitem__("id", "detached"),
                       lambda r: r["contacts"][0].__setitem__("recovered_inward_current_a", .5),
                       lambda r: r["current_density_observable"]["p95"].__setitem__("upper_a_m2", 0.),
                       lambda r: r["current_density_observable"].__setitem__("complete_board_physical_volume", True),
                       lambda r: r.__setitem__("production_qualified", True)):
            changed = deepcopy(out); change(changed)
            with self.assertRaises(ValueError): validate_tetra_dc(changed)

    def test_volume_rank_retains_zero_field_and_does_not_use_cell_count(self):
        values = np.zeros((2, 4, 3)); values[1, :, 2] = 100.
        weights = [.96, .04]
        p95 = tetra_density_enclosure(values, weights); p99 = tetra_density_enclosure(values, weights, .99)
        self.assertEqual((p95["lower_a_m2"], p95["upper_a_m2"]), (0., 0.))
        self.assertEqual((p99["lower_a_m2"], p99["upper_a_m2"]), (100., 100.))
        # Repartition the high-density volume into100 cells: the physical rank is unchanged.
        refined = np.concatenate((values[:1], np.repeat(values[1:], 100, axis=0)))
        refined_weights = [.96]+[.04/100]*100
        self.assertEqual(tetra_density_enclosure(refined, refined_weights)["upper_a_m2"], 0.)
        self.assertEqual(tetra_density_enclosure(refined, refined_weights, .99)["lower_a_m2"], 100.)

    def test_density_uncertainty_invalid_volume_and_nonfinite_reject(self):
        values = np.zeros((1, 4, 3)); values[0, 0, 0] = 1.
        with self.assertRaisesRegex(ValueError, "refinement"): tetra_density_enclosure(values, [1.])
        for weights in ([0.], [-1.], [float("nan")]):
            with self.assertRaises(ValueError): tetra_density_enclosure(np.zeros((1, 4, 3)), weights)
        values[0, 0, 0] = float("inf")
        with self.assertRaises(ValueError): tetra_density_enclosure(values, [1.])

    def test_no_input_mutation_fresh_source_snapshot_and_cancellation(self):
        raw = request(); before = deepcopy(raw); result = solve_tetra_dc(raw)
        self.assertEqual(raw, before)
        raw["mesh"]["vertices"][0][0] = 20.
        self.assertEqual(result["source_request"], before); validate_tetra_dc(result)
        with self.assertRaisesRegex(ValueError, "cancelled"): solve_tetra_dc(before, cancelled=lambda: True)


if __name__ == "__main__": unittest.main()
