# SPDX-License-Identifier: Apache-2.0
"""Analytical oracles for bounded supplied-field reconstruction, not CFD."""
import copy
import json
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad

from python.spike_core.enclosure_flow_analysis import (
    CONTRACT, RESULT_CONTRACT, _cell_data, _velocity, analyze_enclosure_flow,
)
from python.spike_core.enclosure_refinement import build_enclosure_grid


def fixture(n=2, refined=False, psi=None):
    grid = build_enclosure_grid({
        "shape": [n, n, 1], "spacing_m": [1/n, 1/n, 1.], "origin_m": [0., 0., 0.],
        "local_refinement": ([{"bounds_m": [[0., 1/n], [0., 1/n], [0., 1.]],
                              "split_factor": 2}] if refined else []),
    })
    x, y, _ = grid["axes_m"]
    if psi is None:
        psi = np.sin(np.pi*x[:, None]) * np.sin(np.pi*y[None, :])
        # Exact zero boundary values, not rounded sin(pi).
        psi[0, :] = psi[-1, :] = psi[:, 0] = psi[:, -1] = 0.
    hx, hy, _ = grid["cell_widths_m"]
    ux = np.diff(psi, axis=1) / hy[None, :]
    uy = -np.diff(psi, axis=0) / hx[:, None]
    nz = grid["shape"][2]
    faces = (np.repeat(ux[:, :, None], nz, axis=2), np.repeat(uy[:, :, None], nz, axis=2),
             np.zeros((len(hx), len(hy), nz+1)))
    return {
        "contract": CONTRACT, "grid": grid, "fluid_mask": np.ones(grid["shape"], dtype=bool),
        "face_velocity_m_s": faces, "velocity_reference_frame": "stationary",
        "probes_m": [[.2, .2, .3]], "seed_points_m": [[.25, .25, .3]],
        "controls": {"max_time_s": .1, "max_step_s": .02},
    }


def completed(test, request):
    result = analyze_enclosure_flow(request)
    test.assertEqual(result["status"], "completed", result)
    return result


class FlowAnalysisTests(unittest.TestCase):
    def test_three_component_affine_trace(self):
        request = fixture()
        grid = build_enclosure_grid({
            "shape": [2, 2, 2], "spacing_m": [.5, .5, .5],
            "origin_m": [0., 0., 0.], "local_refinement": [],
        })
        # Independent discrete curl: xy streamfunction minus z contribution,
        # plus twice a yz streamfunction. In the low cell u=(4x,4y,-8z).
        psi = np.zeros((3, 3))
        psi[1, 1] = 1.
        ux = np.repeat((2*np.diff(psi, axis=1))[:, :, None], 2, axis=2)
        uy = np.repeat((-2*np.diff(psi, axis=0))[:, :, None], 2, axis=2)
        uy += np.broadcast_to(4*np.diff(psi, axis=1)[None, :, :], (2, 3, 2))
        uz = np.broadcast_to(-4*np.diff(psi, axis=0)[None, :, :], (2, 2, 3)).copy()
        request.update(grid=grid, fluid_mask=np.ones((2, 2, 2), dtype=bool),
                       face_velocity_m_s=(ux, uy, uz), probes_m=[[.1, .2, .3]],
                       seed_points_m=[[.1, .2, .3]],
                       controls={"max_time_s": .03, "max_step_s": .007})
        result = completed(self, request)
        np.testing.assert_allclose(result["probes"][0]["velocity_m_s"], [.4, .8, -2.4], atol=1e-15)
        for point in result["streamlines"][0]["points"]:
            t = point["time_s"]
            np.testing.assert_allclose(point["position_m"],
                                       [.1*math.exp(4*t), .2*math.exp(4*t), .3*math.exp(-8*t)],
                                       rtol=3e-15)

    def test_affine_divergence_free_orbit_and_arclength(self):
        request = fixture()
        result = completed(self, request)
        np.testing.assert_allclose(result["probes"][0]["velocity_m_s"], [.8, -.8, 0.], atol=1e-15)
        trace = result["streamlines"][0]
        self.assertEqual(trace["termination_reason"], "time_limit")
        for point in trace["points"]:
            t = point["time_s"]
            expected = [.25*math.exp(4*t), .25*math.exp(-4*t), .3]
            np.testing.assert_allclose(point["position_m"], expected, rtol=2e-15, atol=1e-16)
            self.assertLess(abs(point["position_m"][0]*point["position_m"][1] - .0625), 1e-16)
        # Independent adaptive integral of the analytical hyperbolic orbit.
        expected_arc = quad(lambda t: math.sqrt(math.exp(8*t)+math.exp(-8*t)), 0., .1,
                            epsabs=1e-13, epsrel=1e-13)[0]
        self.assertAlmostEqual(trace["arclength_m"], expected_arc, delta=2e-15)
        self.assertLess(trace["arclength_quadrature_error_estimate_m"], 2e-15)

    def test_constant_local_field_and_sampling_refinement(self):
        psi = np.zeros((5, 5))
        psi[1:3, 1], psi[1:3, 2] = .25, .5
        request = fixture(4, psi=psi)
        request["seed_points_m"] = [[.3, .3, .3]]
        request["probes_m"] = [[.35, .4, .3]]
        request["controls"]["max_time_s"] = .1
        endpoints = []
        for step in (.1, .05, .0125):
            request["controls"]["max_step_s"] = step
            result = completed(self, request)
            np.testing.assert_allclose(result["probes"][0]["velocity_m_s"], [1., 0., 0.], atol=1e-15)
            trace = result["streamlines"][0]
            endpoint = trace["points"][-1]
            endpoints.append(endpoint["position_m"])
            np.testing.assert_allclose(endpoint["position_m"], [.4, .3, .3], atol=2e-15)
            self.assertAlmostEqual(trace["arclength_m"], .1, delta=1e-15)
        np.testing.assert_allclose(endpoints, np.tile([.4, .3, .3], (3, 1)), atol=2e-15)

    def test_nonuniform_normal_continuity_flux_and_volume_integral(self):
        request = fixture(refined=True)
        request["seed_points_m"] = [[.1, .1, .3]]
        request["probes_m"] = [[.25, .2, .3]]
        result = completed(self, request)
        grid, faces = request["grid"], request["face_velocity_m_s"]
        axes = grid["axes_m"]
        left, right = (0, 0, 0), (1, 0, 0)
        position = np.array([axes[0][1], .2, .3])
        uleft = _velocity(_cell_data(axes, faces, left), position)
        uright = _velocity(_cell_data(axes, faces, right), position)
        self.assertEqual(uleft[0], uright[0])
        self.assertEqual(result["probes"][0]["cell_index"], [1, 0, 0])
        self.assertEqual(result["probes"][0]["velocity_m_s"][0], uright[0])
        for cell in np.ndindex(grid["shape"]):
            data = _cell_data(axes, faces, cell)
            volume = grid["cell_volumes_m3"][cell]
            corner_sum = sum((_velocity(data, np.where(bits, data[1], data[0]))
                              for bits in np.ndindex((2, 2, 2))), np.zeros(3))
            expected_integral = volume * .5 * (data[2] + data[3])
            np.testing.assert_allclose(volume * corner_sum / 8, expected_integral, atol=1e-16)
            face_flux = math.fsum((data[3][d]-data[2][d]) * volume/(data[1][d]-data[0][d])
                                 for d in range(3))
            self.assertAlmostEqual(face_flux, 0., delta=2e-16)

    def test_exact_cell_exit_and_no_skipped_cells(self):
        request = fixture()
        request["controls"].update(max_time_s=1., max_step_s=1.)
        result = completed(self, request)
        trace = result["streamlines"][0]
        event = next(p for p in trace["points"] if p["position_m"][0] == .5)
        self.assertAlmostEqual(event["time_s"], math.log(2)/4, delta=2e-16)
        np.testing.assert_allclose(event["position_m"], [.5, .125, .3], atol=1e-15)
        self.assertGreater(trace["cell_events"], 2)
        previous = np.array(trace["points"][0]["position_m"])
        for point in trace["points"][1:]:
            cell = point["cell_index"]
            low = np.array([request["grid"]["axes_m"][d][cell[d]] for d in range(3)])
            high = np.array([request["grid"]["axes_m"][d][cell[d]+1] for d in range(3)])
            current = np.array(point["position_m"])
            self.assertTrue(np.all(previous >= low) and np.all(previous <= high))
            self.assertTrue(np.all(current >= low) and np.all(current <= high))
            previous = current

    def test_obstacle_disconnected_tangency_and_stagnation(self):
        psi = np.zeros((5, 5))
        psi[1, 1] = 1.
        request = fixture(4, psi=psi)
        request["fluid_mask"][2, :, :] = False
        request["seed_points_m"] = [[.1, .1, .3], [.9, .3, .3]]
        request["probes_m"] = []
        request["controls"].update(max_time_s=2., max_step_s=.05)
        result = completed(self, request)
        self.assertEqual(result["streamlines"][1]["termination_reason"], "stagnation")
        self.assertEqual(result["streamlines"][1]["arclength_m"], 0.)
        for point in result["streamlines"][0]["points"]:
            self.assertTrue(request["fluid_mask"][tuple(point["cell_index"])])
            self.assertLessEqual(point["position_m"][0], .5)
        # The fluid-solid interface has exactly zero normal velocity but need
        # not have zero tangential RT0 trace. This is impermeability, not no-slip.
        wall_cell = (1, 0, 0)
        value = _velocity(_cell_data(request["grid"]["axes_m"],
                                    request["face_velocity_m_s"], wall_cell), np.array([.5, .1, .3]))
        self.assertEqual(value[0], 0.)
        self.assertNotEqual(value[1], 0.)

    def test_ambiguous_corner_stops_without_diagonal_jump(self):
        psi = np.zeros((5, 5))
        # On cell(1,1): streamfunction y-x, giving exactly u=v=1.
        psi[1, 1], psi[2, 1], psi[1, 2], psi[2, 2] = 0., -.25, .25, 0.
        request = fixture(4, psi=psi)
        request["probes_m"] = []
        request["seed_points_m"] = [[.375, .375, .3]]
        request["controls"].update(max_time_s=1., max_step_s=1.)
        trace = completed(self, request)["streamlines"][0]
        self.assertEqual(trace["termination_reason"], "ambiguous_cell_edge")
        np.testing.assert_array_equal(trace["points"][-1]["position_m"], [.5, .5, .3])
        self.assertEqual(trace["cell_events"], 1)

    def test_limits_determinism_and_source_digest(self):
        request = fixture()
        request["controls"].update(max_time_s=10., max_step_s=.001, max_points_per_streamline=3)
        first = completed(self, request)
        self.assertEqual(first["streamlines"][0]["termination_reason"], "point_limit")
        self.assertEqual(first, completed(self, request))
        old_digest = first["source_digest_sha256"]
        request["controls"].update(max_time_s=10., max_step_s=1., max_points_per_streamline=100,
                                   max_cell_events=1)
        result = completed(self, request)
        self.assertEqual(result["streamlines"][0]["termination_reason"], "event_limit")
        self.assertNotEqual(old_digest, result["source_digest_sha256"])
        request["controls"]["max_total_points"] = 1
        self.assertBlocked(request, "point budget")
        request["controls"]["max_total_points"] = 8192
        request["controls"]["max_output_bytes"] = 1024
        self.assertBlocked(request, "byte budget")

    def test_cancel_and_wall_clock_have_no_partial_outputs(self):
        request = fixture()
        result = analyze_enclosure_flow(request, cancel_check=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        self.assertNotIn("streamlines", result)
        calls = [0]

        def cancel_after_work():
            calls[0] += 1
            return calls[0] > 10

        result = analyze_enclosure_flow(request, cancel_check=cancel_after_work)
        self.assertEqual(result["status"], "cancelled")
        self.assertNotIn("streamlines", result)
        with patch("python.spike_core.enclosure_flow_analysis.time.monotonic", side_effect=[0., 100.]):
            self.assertBlocked(request, "runtime")

    def assertBlocked(self, request, reason=None):
        result = analyze_enclosure_flow(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertNotIn("probes", result)
        self.assertNotIn("streamlines", result)
        if reason:
            self.assertIn(reason, result["reason"])
        return result

    def test_strict_inputs_and_forged_grid(self):
        cases = []
        unknown = fixture()
        unknown["pressure_pa"] = 0.
        cases.append(unknown)
        for key, value in (("unknown", 1), ("max_step_s", 0.), ("max_cell_events", True),
                           ("max_runtime_s", 31.), ("max_output_bytes", 2_000_001)):
            request = fixture()
            request["controls"][key] = value
            cases.append(request)
        for key, value in (("velocity_reference_frame", "co_rotating"),
                           ("fluid_mask", np.ones((2, 2, 1))),
                           ("probes_m", [[0., .1, .3]]),
                           ("seed_points_m", [[.5, .1, .3]]),
                           ("seed_points_m", [[.1, .1, .3]]*17),
                           ("probes_m", [[.1, .1, .3]]*65)):
            request = fixture()
            request[key] = value
            cases.append(request)
        request = fixture()
        request["grid"]["cell_volumes_m3"][0, 0, 0] *= 2
        cases.append(request)
        request = fixture()
        request["grid"]["cell_centers_m"][0][0] = float("nan")
        cases.append(request)
        request = fixture()
        request["grid"]["parent_indices"][0][0] = 1
        cases.append(request)
        request = fixture()
        request["seed_points_m"] = [[.8, .8, .3]]
        request["fluid_mask"][:] = False
        request["fluid_mask"][0, 0, 0] = True
        request["face_velocity_m_s"] = tuple(np.zeros_like(f) for f in request["face_velocity_m_s"])
        cases.append(request)
        for request in cases:
            with self.subTest(options=str(request.keys())):
                self.assertBlocked(request)

    def test_wall_solid_divergence_nonfinite_and_underflow_rejection(self):
        request = fixture()
        request["face_velocity_m_s"][0][0, 0, 0] = 1e-30
        self.assertBlocked(request, "exactly zero")
        request = fixture()
        request["fluid_mask"][1, 0, 0] = False
        self.assertBlocked(request, "solid")
        request = fixture()
        request["face_velocity_m_s"][0][1, 0, 0] *= 1.01
        self.assertBlocked(request, "divergence")
        for value in (float("nan"), float("inf")):
            request = fixture()
            request["face_velocity_m_s"][0][1, 0, 0] = value
            self.assertBlocked(request)
        request = fixture()
        request["face_velocity_m_s"] = tuple(f*1e-315 for f in request["face_velocity_m_s"])
        self.assertBlocked(request)
        request = fixture()
        request["controls"]["max_step_s"] = 1e-320
        self.assertBlocked(request)

    def test_serialized_request_preserves_reconstruction_and_digest(self):
        request = fixture()
        expected = completed(self, request)
        serialized = json.loads(json.dumps(
            request, default=lambda value: value.tolist()
            if isinstance(value, np.ndarray) else value.item(), allow_nan=False))
        self.assertEqual(expected, completed(self, serialized))

    def test_zero_field_no_mutation_and_truthful_output(self):
        request = fixture()
        request["face_velocity_m_s"] = tuple(np.zeros_like(f) for f in request["face_velocity_m_s"])
        original = copy.deepcopy(request)
        result = completed(self, request)
        self.assertEqual(result["diagnostics"]["max_divergence_s_inv"], 0.)
        self.assertEqual(result["streamlines"][0]["termination_reason"], "stagnation")
        self.assertEqual(result["source_data_kind"], "supplied_shared_face_field")
        self.assertEqual(result["contract"], RESULT_CONTRACT)
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["velocity_reference_frame"], "stationary")
        self.assertEqual(result["model_status"], "experimental")
        self.assertNotIn("curl", json.dumps(result))
        for old, current in zip(original["face_velocity_m_s"], request["face_velocity_m_s"]):
            np.testing.assert_array_equal(old, current)
        for old, current in zip(original["grid"]["axes_m"], request["grid"]["axes_m"]):
            np.testing.assert_array_equal(old, current)

    def test_normalized_numpy_scalars_in_digest(self):
        request = fixture()
        # z=1 is interior after translation of z domain to (0,2).
        request["grid"] = build_enclosure_grid({
            "shape": [2, 2, 1], "spacing_m": [.5, .5, 2.],
            "origin_m": [0., 0., 0.], "local_refinement": [],
        })
        request["probes_m"] = [[np.float64(.2), np.float64(.2), np.int64(1)]]
        request["seed_points_m"] = [[np.float64(.25), np.float64(.25), np.int64(1)]]
        first = completed(self, request)
        request["probes_m"] = [[.2, .2, 1.]]
        request["seed_points_m"] = [[.25, .25, 1.]]
        self.assertEqual(first["source_digest_sha256"], completed(self, request)["source_digest_sha256"])


if __name__ == "__main__":
    unittest.main()
