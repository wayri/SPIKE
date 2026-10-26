# SPDX-License-Identifier: Apache-2.0
"""Independent scalar radiation oracles and coupled heat-balance regressions."""
import copy
import json
import math
import unittest

from python.spike_core.solvers.electromagnetics.fields.multiboard_radiation import RadiationExchange, SIGMA
from python.spike_core.solvers.thermal_fluid.heat.multiboard_thermal import MultiboardThermalError, run_multiboard_thermal
from tests.python.test_multiboard_thermal import request as conduction_request


def request(emissivity=1., view_factor=1.):
    raw = conduction_request(.01)
    for model, power in zip(raw["board_models"], (8., 2.)):
        model["elements"][0].update(power_w=power, ambient_resistance_c_per_w=10., thermal_capacitance_j_per_c=2.)
    raw["radiation_surfaces"] = [{"id": face, "board_id": board, "node": "board", "area_mm2": 10000.,
        "emissivity": emissivity, "view_factors": {other: view_factor, "ambient": 1 - view_factor}}
        for board, face, other in (("A", "face-a", "face-b"), ("B", "face-b", "face-a"))]
    return raw


def scalar_closed_pair_heat(ta_c, tb_c, ea=1., eb=1.):
    return .01 * SIGMA * ((ta_c + 273.15) ** 4 - (tb_c + 273.15) ** 4) / (1 / ea + 1 / eb - 1)


class MultiboardRadiationTests(unittest.TestCase):
    def test_uniform_surface_subdivision_and_jacobian(self):
        raw = request(.7)
        reference = run_multiboard_thermal(raw)
        raw["radiation_surfaces"] = [{"id": f"{board}-{i}", "board_id": board, "node": "board", "area_mm2": 5000.,
            "emissivity": .7, "view_factors": {f"{other}-0": .5, f"{other}-1": .5}}
            for board, other in (("A", "B"), ("B", "A")) for i in range(2)]
        subdivided = run_multiboard_thermal(raw)
        for board in ("A", "B"):
            self.assertAlmostEqual(subdivided["board_temperatures_c"][board]["board"], reference["board_temperatures_c"][board]["board"], places=9)
        ids = [json.dumps([b, "board"], separators=(",", ":")) for b in ("A", "B")]
        exchange = RadiationExchange(raw["radiation_surfaces"], ids)
        temperature = [90., 60.]
        result = exchange.evaluate(temperature, 25.)
        for column in range(2):
            plus, minus = temperature[:], temperature[:]
            plus[column] += .001
            minus[column] -= .001
            heat_plus, heat_minus = exchange.evaluate(plus, 25.)["node_heat_w"], exchange.evaluate(minus, 25.)["node_heat_w"]
            for row in range(2):
                difference = (heat_plus[row] - heat_minus[row]) / .002
                self.assertAlmostEqual(result["jacobian"][row][column], difference, places=8)

    def test_gray_parallel_closed_surfaces_against_scalar_resistance_oracle(self):
        raw = request(.6)
        raw["radiation_surfaces"][1]["emissivity"] = .8
        ids = [json.dumps([b, "board"], separators=(",", ":")) for b in ("A", "B")]
        exchange = RadiationExchange(raw["radiation_surfaces"], ids).evaluate([100., 50.], 25.)
        exact = scalar_closed_pair_heat(100., 50., .6, .8)
        self.assertAlmostEqual(exchange["node_heat_w"][0], exact, places=11)
        self.assertAlmostEqual(exchange["node_heat_w"][1], -exact, places=11)
        self.assertAlmostEqual(exchange["ambient_heat_flow_w"], 0., places=12)
        self.assertAlmostEqual(exchange["closure_residual_w"], 0., places=12)

    def test_both_powered_radiation_primary_and_scalar_steady_oracle(self):
        raw = request()
        result = run_multiboard_thermal(raw)
        # Total power 10 W exits two 0.1 W/K paths; sum of rises is 100 K.
        # Bisection independently solves just the temperature difference.
        lo, hi = 0., 100.
        for _ in range(100):
            difference = (lo + hi) / 2
            a, b = 25 + (100 + difference) / 2, 25 + (100 - difference) / 2
            balance_a = .1 * (a - 25) + .01 * difference + scalar_closed_pair_heat(a, b) - 8
            if balance_a > 0:
                hi = difference
            else:
                lo = difference
        a, b = 25 + (100 + difference) / 2, 25 + (100 - difference) / 2
        self.assertAlmostEqual(result["board_temperatures_c"]["A"]["board"], a, places=7)
        self.assertAlmostEqual(result["board_temperatures_c"]["B"]["board"], b, places=7)
        self.assertLess(result["summary"]["max_node_residual_w"], 1e-8)
        self.assertLess(abs(result["summary"]["energy_balance_residual_w"]), 1e-8)
        radiation = result["radiation_exchange"][0]["heat_flow_w"]
        standoff = result["contact_heat_flows"][0]["heat_flow_w"]
        self.assertGreater(radiation, 5 * standoff)
        conduction_only = copy.deepcopy(raw)
        conduction_only.pop("radiation_surfaces")
        uncoupled_radiation = run_multiboard_thermal(conduction_only)
        self.assertGreater(uncoupled_radiation["board_temperatures_c"]["A"]["board"], a)
        self.assertLess(uncoupled_radiation["board_temperatures_c"]["B"]["board"], b)
        hotter_b = copy.deepcopy(raw)
        hotter_b["board_models"][1]["elements"][0]["power_w"] = 4
        stronger = run_multiboard_thermal(hotter_b)
        self.assertGreater(stronger["board_temperatures_c"]["A"]["board"], a)
        self.assertGreater(stronger["board_temperatures_c"]["B"]["board"], b)

    def test_transient_refines_to_independent_adaptive_ode_reference(self):
        from scipy.integrate import solve_ivp
        def rhs(_, t):
            flow = scalar_closed_pair_heat(t[0], t[1]) + .01 * (t[0] - t[1])
            return [(8 - .1 * (t[0] - 25) - flow) / 2, (2 - .1 * (t[1] - 25) + flow) / 2]
        reference = solve_ivp(rhs, (0., 5.), [25., 25.], rtol=1e-11, atol=1e-12).y[:, -1]
        errors = []
        for dt in (.2, .1, .05):
            raw = request()
            raw.update(mode="transient", duration_s=5., time_step_s=dt)
            result = run_multiboard_thermal(raw)
            final = [result["board_temperatures_c"][board]["board"] for board in ("A", "B")]
            errors.append(max(abs(value - exact) for value, exact in zip(final, reference)))
            self.assertLess(result["summary"]["max_transient_energy_balance_error_w"], 1e-8)
            self.assertAlmostEqual(result["radiation_exchange"][0]["heat_flow_w"], scalar_closed_pair_heat(*final), places=10)
        self.assertLess(errors[1], errors[0])
        self.assertLess(errors[2], errors[1])
        self.assertLess(errors[2], .04)

    def test_open_environment_closure_and_unequal_areas(self):
        raw = request(.8, .8)
        raw["radiation_surfaces"][1]["area_mm2"] = 20000
        raw["radiation_surfaces"][1]["view_factors"] = {"face-a": .4, "ambient": .6}
        result = run_multiboard_thermal(raw)
        self.assertLess(abs(result["summary"]["radiation_closure_residual_w"]), 1e-10)
        self.assertGreater(result["summary"]["radiation_ambient_heat_flow_w"], 0)
        self.assertLess(abs(result["summary"]["energy_balance_residual_w"]), 1e-8)

    def test_radiation_without_standoff_and_zero_cross_view_factor(self):
        raw = request()
        raw["assembly"]["thermal_contacts"] = []
        raw["contact_models"] = []
        result = run_multiboard_thermal(raw)
        self.assertTrue(result["coupled_physics"])
        self.assertEqual(result["contact_heat_flows"], [])
        raw = request(view_factor=0.)
        self.assertEqual(run_multiboard_thermal(raw)["radiation_exchange"], [])
        raw["assembly"]["thermal_contacts"] = []
        raw["contact_models"] = []
        with self.assertRaisesRegex(MultiboardThermalError, "inter-board view factor"):
            run_multiboard_thermal(raw)

    def test_bad_view_factors_properties_and_node_binding_rejected(self):
        mutations = [lambda s: s[0]["view_factors"].update({"face-b": .9}),
                     lambda s: s[0]["view_factors"].update({"face-b": .5, "ambient": .5}),
                     lambda s: s[0].update(emissivity=0), lambda s: s[0].update(emissivity=1.1),
                     lambda s: s[0].update(area_mm2=-1), lambda s: s[0].update(node="missing"),
                     lambda s: s[0]["view_factors"].update({"face-b": math.nan}),
                     lambda s: s[0]["view_factors"].update({"missing": 0})]
        for mutate in mutations:
            raw = request()
            mutate(raw["radiation_surfaces"])
            with self.subTest(mutation=mutate), self.assertRaises(MultiboardThermalError):
                run_multiboard_thermal(raw)
        for malformed in ({}, None, "surfaces"):
            raw = request()
            raw["radiation_surfaces"] = malformed
            with self.assertRaises(MultiboardThermalError):
                run_multiboard_thermal(raw)


if __name__ == "__main__":
    unittest.main()
