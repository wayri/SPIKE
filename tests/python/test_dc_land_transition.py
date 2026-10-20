# SPDX-License-Identifier: Apache-2.0
"""Physical constant fields, semantic contact separation and strict admission."""
from copy import deepcopy
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from python.spike_core.dc_land_transition import solve_land_transition
from python.spike_core.dc_land_transition_input import REQUEST, prepare
from python.spike_core.dc_land_transition_evidence import validate_land_result

ROOT = Path(__file__).resolve().parents[2]


def uniform_request(axis=2):
    axes = [[0., .3, 1.], [0., .4, 1.], [0., .1, .2]]
    uv = [a for a in range(3) if a != axis]
    rectangle = [[axes[a][0], axes[a][-1]] for a in uv]
    return {"contract": REQUEST, "axes_mm": axes, "conductivity_s_m": 5.8e7,
        "contacts": [{"id": "in", "attachment_id": "shared-label", "face": "xyz"[axis]+"_min",
                       "rectangle_mm": rectangle, "current_a": 1.},
                     {"id": "out", "attachment_id": "shared-label", "face": "xyz"[axis]+"_max",
                       "rectangle_mm": rectangle, "current_a": -1.}]}


class LandTransitionTests(unittest.TestCase):
    def test_nonuniform_grid_all_axes_exact_constant_field_and_heat(self):
        for axis in range(3):
            request = uniform_request(axis); before = deepcopy(request)
            result = solve_land_transition(request)
            sizes = np.array([a[-1]-a[0] for a in request["axes_mm"]])*1e-3
            area = np.prod(np.delete(sizes, axis)); expected_j = np.zeros(3); expected_j[axis] = 1/area
            exact_r = sizes[axis]/(5.8e7*area)
            for cell in result["cells"]:
                # Norm-relative vector error includes transverse components;
                # a zero expected component has no meaningful relative error.
                self.assertLess(np.linalg.norm(np.asarray(cell["center_density_a_m2"])-expected_j)
                                /np.linalg.norm(expected_j), 1e-10)
            self.assertLess(abs(result["joule_heat_w"]/exact_r-1), 1e-10)
            voltage = result["contacts"][0]["mean_potential_v"]-result["contacts"][1]["mean_potential_v"]
            self.assertLess(abs(voltage/exact_r-1), 1e-10)
            self.assertEqual(request, before)
            self.assertFalse(result["production_qualified"])
            self.assertFalse(result["complete_board_physical_volume"])
            self.assertLess(result["diagnostics"]["maximum_face_boundary_gauge_error_a"], 1e-9)
            self.assertNotEqual(result["contacts"][0]["face_ids"], result["contacts"][1]["face_ids"])
            json.dumps(result, allow_nan=False)

    def test_zero_sign_scaling_and_conductivity(self):
        base = solve_land_transition(uniform_request())
        for factor in (0., -1., 3.):
            request = uniform_request()
            for p in request["contacts"]:
                p["current_a"] *= factor
            result = solve_land_transition(request)
            self.assertAlmostEqual(result["joule_heat_w"], factor**2*base["joule_heat_w"], places=13)
            np.testing.assert_allclose([c["center_density_a_m2"] for c in result["cells"]],
                                       np.array([c["center_density_a_m2"] for c in base["cells"]])*factor, atol=1e-7)
        request = uniform_request(); request["conductivity_s_m"] *= 2
        result = solve_land_transition(request)
        self.assertAlmostEqual(result["joule_heat_w"]*2, base["joule_heat_w"], places=13)

    def test_record_order_and_distinct_patch_labels_do_not_weld(self):
        request = uniform_request(); base = solve_land_transition(request)
        request["contacts"].reverse()
        result = solve_land_transition(request)
        self.assertAlmostEqual(result["joule_heat_w"], base["joule_heat_w"], places=14)
        self.assertEqual({p["id"]: p["mean_potential_v"] for p in result["contacts"]},
                         {p["id"]: p["mean_potential_v"] for p in base["contacts"]})
        self.assertNotEqual(base["contacts"][0]["mean_potential_v"], base["contacts"][1]["mean_potential_v"])

    def test_overlap_rejected_even_with_zero_or_cancelling_current(self):
        for current in (0., 1.):
            request = uniform_request()
            request["contacts"][1]["face"] = "z_min"
            request["contacts"][0]["current_a"] = current
            request["contacts"][1]["current_a"] = -current
            with self.assertRaisesRegex(ValueError, "Overlapping"):
                solve_land_transition(request)

    def test_unbalanced_unaligned_unsupported_and_nonfinite_rejected(self):
        mutations = (
            lambda r: r["contacts"][1].__setitem__("current_a", -.9),
            lambda r: r["contacts"][0]["rectangle_mm"][0].__setitem__(0, .001),
            lambda r: r["contacts"][0].__setitem__("face", "annulus"),
            lambda r: r["contacts"][0].__setitem__("current_a", True),
            lambda r: r["contacts"][0].__setitem__("current_a", float("nan")),
            lambda r: r.__setitem__("conductivity_s_m", 0),
            lambda r: r["axes_mm"][0].reverse(),
            lambda r: r["contacts"][1].__setitem__("id", "in"),
        )
        for mutate in mutations:
            request = uniform_request(); mutate(request)
            with self.assertRaises(ValueError):
                solve_land_transition(request)

    def test_geometry_and_arithmetic_budgets(self):
        request = uniform_request(); request["axes_mm"] = [np.linspace(0, 1, 25).tolist()]*3
        with self.assertRaisesRegex(ValueError, "cell budget"):
            solve_land_transition(request)
        request = uniform_request(); request["axes_mm"][2] = [0., 1e-9]
        with self.assertRaisesRegex(ValueError, "aspect"):
            solve_land_transition(request)
        request = uniform_request()
        for patch in request["contacts"]:
            patch["current_a"] *= 1e-200
        with self.assertRaisesRegex(ValueError, "underflow"):
            solve_land_transition(request)

    def test_retained_field_mapping_heat_and_weak_law_forgeries(self):
        result = solve_land_transition(uniform_request())
        validate_land_result(result)
        for mutate in (
            lambda r: r.__setitem__("production_qualified", True),
            lambda r: r.__setitem__("input_digest", "0"*64),
            lambda r: r["contacts"][0]["face_ids"].reverse(),
            lambda r: r["contacts"][0].__setitem__("attachment_id", "different"),
            lambda r: r["contacts"][0].__setitem__("mean_potential_v", 1.),
            lambda r: r["cells"][0].__setitem__("volume_m3", 1.),
            lambda r: r["cells"][0].__setitem__("joule_heat_w", 0.),
            lambda r: r["cells"][0]["component_endpoint_density_a_m2"][0].__setitem__(0, 1e308),
            lambda r: r["cells"][0].__setitem__("mean_potential_v", 1.),
            lambda r: r["face_potential_v"].__setitem__(0, 1.),
        ):
            forged = deepcopy(result); mutate(forged)
            with self.assertRaises(ValueError):
                validate_land_result(forged)

    def test_actual_example_cli_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as folder:
            path = Path(folder)/"land.json"
            command = [sys.executable, str(ROOT/"examples/dc_land_transition/run_land.py"), "--output", str(path)]
            execution = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(execution.returncode, 0, execution.stderr)
            result = json.loads(path.read_text()); validate_land_result(result)
            self.assertEqual(len(result["contacts"]), 3)
            before = path.read_bytes()
            repeated = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(path.read_bytes(), before)

    def test_small_contact_stamp_is_not_zeroed_before_area_division(self):
        request = uniform_request(0)
        request["axes_mm"] = [[0., 1e-9]]*3
        request["conductivity_s_m"] = 1.
        for patch in request["contacts"]:
            patch["rectangle_mm"] = [[0., 1e-9]]*2
        for face, current in (("z_min", 1e-300), ("z_max", -1e-300)):
            request["contacts"].append({"id": face, "attachment_id": "tiny", "face": face,
                "rectangle_mm": [[0., 1e-9]]*2, "current_a": current})
        data = prepare(request)
        for patch in data["patches"][2:]:
            self.assertEqual(float(data["prescribed"][patch["faces"]][0]), -patch["current_a"])
        result = solve_land_transition(request); validate_land_result(result)
        for patch in result["contacts"]:
            self.assertFalse(patch["patch_relative_accuracy_certified"])

    def test_interior_trace_forgery_cannot_pass_by_norm_overflow(self):
        result = solve_land_transition(uniform_request())
        counts = Counter(fid for cell in result["cells"] for fid in cell["face_ids"])
        interior = next(fid for fid, count in counts.items() if count == 2)
        result["face_potential_v"][interior] = 1e308
        with self.assertRaisesRegex(ValueError, "weak law"):
            validate_land_result(result)


if __name__ == "__main__":
    unittest.main()
