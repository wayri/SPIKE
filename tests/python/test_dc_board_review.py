# SPDX-License-Identifier: Apache-2.0
"""Independent boundary-review counterexamples for retained board DC evidence."""
from copy import deepcopy
import hashlib
import math
import unittest

from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0 import solve_tetra_dc
from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0_evidence import validate_tetra_dc
from python.spike_core.solvers.power_integrity.dc.dc_tetra_density import tetra_density_enclosure
from python.spike_core.solvers.power_integrity.dc.dc_board_study import solve_source_board, validate_source_board_run
from tests.python.test_dc_tetra_rt0 import slab, merge_meshes, request, faces_at
from tests.python.test_dc_board_source import source_model, FIXTURE


class BoardCompositionReviewTests(unittest.TestCase):
    def test_retained_weak_driven_component_cannot_disappear(self):
        raw = request(merge_meshes(slab(owner="strong"), slab(origin=(3., 0., 0.), owner="weak")))
        raw["contacts"] = [{"id": str(i), "faces": faces_at(raw["mesh"], 0, x), "current_a": current}
                           for i, (x, current) in enumerate([(0., 1.), (1., -1.), (3., 1e-12), (4., -1e-12)])]
        result = solve_tetra_dc(raw)
        validate_tetra_dc(result)
        for cell in result["cells"]:
            if cell["id"].startswith("weak"):
                cell["outward_face_current_a"] = [0.] * 4
                cell["vertex_density_a_m2"] = [[0.] * 3 for _ in range(4)]
                for name in ("joule_heat_w", "mean_joule_density_w_m3", "mean_potential_v"):
                    cell[name] = 0.
                for face in cell["face_ids"]:
                    result["face_potential_v"][face] = 0.
        for contact in result["contacts"][2:]:
            for name in ("recovered_inward_current_a", "mean_potential_v", "signed_terminal_work_w"):
                contact[name] = 0.
            contact["absolute_current_recovery_error_a"] = abs(contact["inward_current_a"])
        result["joule_heat_w"] = math.fsum(c["joule_heat_w"] for c in result["cells"])
        result["signed_terminal_work_w"] = math.fsum(c["signed_terminal_work_w"] for c in result["contacts"])
        for name, q in (("p95", .95), ("p99", .99)):
            result["current_density_observable"][name] = tetra_density_enclosure(
                [c["vertex_density_a_m2"] for c in result["cells"]], [c["volume_m3"] for c in result["cells"]], q)
        with self.assertRaises(ValueError):
            validate_tetra_dc(result)

    def test_source_replay_enforces_same_request_contract_as_execution(self):
        prepared = source_model()
        config = {"contract": "spike/source-board-volume-study/v1", "source_path": str(FIXTURE),
                  "source_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), "net_names": ["VDD"],
                  "electrodes": prepared["source_evidence"]["electrodes"], "plating_thickness_mm": .025,
                  "conductivity_s_m": 5.8e7, "target_mm": 1., "max_cells": 5000}
        result = solve_source_board(config)
        validate_source_board_run(result)
        for mutation in (lambda c: c.__setitem__("contract", "forged/other-physics/v99"),
                         lambda c: c.__setitem__("unadmitted_geometry_override", {"plating": "different"})):
            bad = deepcopy(result)
            mutation(bad["source_request"])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_source_board_run(bad)


if __name__ == "__main__":
    unittest.main()
