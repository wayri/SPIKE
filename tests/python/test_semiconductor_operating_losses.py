# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original multi-affine SI oracle; synthetic values, not device validation."""
import copy
import itertools
import math
import sys
import unittest

from python.spike_core.semiconductor_operating_losses import (
    AXES, LOSS_COLUMNS, MAX_AXIS_NODES, MODEL_KIND,
    SemiconductorOperatingLossError, evaluate_semiconductor_operating_loss,
)


def oracle(t, v, i):
    # All 8 independent multi-affine terms, including cross-coordinate terms.
    return 1 + .01*t + .02*v + .3*i + .0001*t*v + .001*t*i + .002*v*i + .00001*t*v*i


def table():
    axes = ([300, 325, 450], [0, 50, 200], [0, 2, 9])
    model = {"kind": MODEL_KIND, **dict(zip(AXES, axes)),
             "operating_voltage_v": 125, "operating_current_a": 4,
             "switching_frequency_hz": 1000,
             "conditions": "Original synthetic data; fixed duty and gate drive; no measured device.",
             "energy_terms_nonoverlapping": True}
    for name, scale in zip(LOSS_COLUMNS, (1, .001, .002, .0005)):
        model[name] = [[[scale*oracle(t, v, i) for i in axes[2]] for v in axes[1]] for t in axes[0]]
    return model


class SemiconductorOperatingLossTests(unittest.TestCase):
    def reject(self, model, code, temperature=350):
        with self.assertRaises(SemiconductorOperatingLossError) as caught:
            evaluate_semiconductor_operating_loss(model, temperature)
        self.assertEqual(caught.exception.code, code)

    def test_multiaffine_oracle_in_every_cell(self):
        model = table()
        before = copy.deepcopy(model)
        for t, v, i in itertools.product([312.5, 360], [10, 125], [.4, 4]):
            model.update(operating_voltage_v=v, operating_current_a=i)
            result = evaluate_semiconductor_operating_loss(model, t)
            expected = oracle(t, v, i)
            self.assertAlmostEqual(result["average_power_w"], expected * 4.5, delta=1e-12)
            for name, scale in zip(LOSS_COLUMNS, (1, .001, .002, .0005)):
                self.assertAlmostEqual(result["ledger"][name], expected*scale, delta=1e-13)
            self.assertEqual(result["temporal_scope"], "steady_average_only")
        model.update(operating_voltage_v=125, operating_current_a=4)
        self.assertEqual(before, model)

    def test_all_grid_nodes_are_exact_including_endpoints(self):
        model = table()
        for ti, vi, ii in itertools.product(range(3), repeat=3):
            model.update(operating_voltage_v=model["voltage_v"][vi], operating_current_a=model["current_a"][ii])
            result = evaluate_semiconductor_operating_loss(model, model["temperature_k"][ti])
            for name in LOSS_COLUMNS:
                self.assertEqual(result["ledger"][name], model[name][ti][vi][ii])

    def test_asymmetric_grids_and_refinement_preserve_multiaffine_oracle(self):
        for axes in (([300, 450], [0, 50, 200], [0, 2, 5, 9]),
                     ([300, 320, 375, 450], [0, 25, 50, 100, 200], [0, 1, 2, 4, 9])):
            model = table()
            model.update(dict(zip(AXES, axes)))
            for name, scale in zip(LOSS_COLUMNS, (1, .001, .002, .0005)):
                model[name] = [[[scale*oracle(t, v, i) for i in axes[2]] for v in axes[1]] for t in axes[0]]
            self.assertAlmostEqual(evaluate_semiconductor_operating_loss(model, 350)["average_power_w"],
                                   oracle(350, 125, 4)*4.5, delta=1e-12)

    def test_maximum_grid_budget_and_axis_budget_are_admitted(self):
        # 64*32*16 = 32768 nodes, four tensors; no unbounded dense operation.
        axes = ([float(300+i) for i in range(64)], list(range(32)), list(range(16)))
        model = table()
        model.update(dict(zip(AXES, axes)), operating_voltage_v=10, operating_current_a=5)
        for name in LOSS_COLUMNS:
            model[name] = [[[1.0]*16 for _ in range(32)] for _ in range(64)]
        self.assertEqual(evaluate_semiconductor_operating_loss(model, 350)["average_power_w"], 3001)

    def test_brackets_units_and_loss_ledger(self):
        result = evaluate_semiconductor_operating_loss(table(), 350)
        ledger = result["ledger"]
        self.assertEqual(ledger["axis_brackets"], {"temperature_k": [325, 450], "voltage_v": [50, 200], "current_a": [2, 9]})
        self.assertEqual(ledger["interpolation_fractions"], {"temperature_k": .2, "voltage_v": .5, "current_a": 2/7})
        self.assertEqual(ledger["turn_on_power_w"], ledger["turn_on_energy_j"]*1000)
        self.assertEqual(ledger["turn_off_power_w"], ledger["turn_off_energy_j"]*1000)
        self.assertEqual(ledger["reverse_recovery_power_w"], ledger["reverse_recovery_energy_j"]*1000)
        self.assertEqual(result["average_power_w"], math.fsum(ledger[name] for name in
                         ("conduction_power_w", "turn_on_power_w", "turn_off_power_w", "reverse_recovery_power_w")))

    def test_zero_frequency_has_only_conduction_and_zero_values_admitted(self):
        model = table()
        model["switching_frequency_hz"] = 0
        result = evaluate_semiconductor_operating_loss(model, 350)
        self.assertEqual(result["average_power_w"], result["ledger"]["conduction_power_w"])
        for name in LOSS_COLUMNS:
            model[name] = [[[0]*3 for _ in range(3)] for _ in range(3)]
        self.assertEqual(evaluate_semiconductor_operating_loss(model, 350)["average_power_w"], 0)

    def test_no_extrapolation_even_one_ulp(self):
        for name, operating, code in (("temperature_k", None, "temperature_out_of_bounds"),
                                       ("voltage_v", "operating_voltage_v", "voltage_out_of_bounds"),
                                       ("current_a", "operating_current_a", "current_out_of_bounds")):
            for end, direction in ((0, -math.inf), (-1, math.inf)):
                model = table()
                value = math.nextafter(model[name][end], direction)
                if operating is None:
                    self.reject(model, code, value)
                else:
                    model[operating] = value
                    self.reject(model, "invalid_number" if value < 0 else code)

    def test_strict_fields_kind_and_energy_nonoverlap(self):
        for operation in (lambda m: m.pop("conditions"), lambda m: m.update(units="mJ")):
            model = table()
            operation(model)
            self.reject(model, "invalid_fields")
        model = table()
        model["kind"] = "spice"
        self.reject(model, "unsupported_model")
        for value in (False, 1, "true", None):
            model = table()
            model["energy_terms_nonoverlapping"] = value
            self.reject(model, "overlapping_energy_terms")
        for value in ("", "  ", "x"*4097, None):
            model = table()
            model["conditions"] = value
            self.reject(model, "invalid_text")

    def test_axes_strictly_increasing_nonnegative_and_bounded(self):
        for name in AXES:
            for values, code in (([1], "axis_budget"), ([1]*(MAX_AXIS_NODES+1), "axis_budget"),
                                 ([1, 1, 2], "invalid_grid"), ([3, 2, 1], "invalid_grid"),
                                 ([-1, 0, 1], "invalid_number"), ((1, 2), "axis_budget")):
                model = table()
                model[name] = values
                self.reject(model, code)
        model = table()
        model["temperature_k"][0] = 0
        self.reject(model, "invalid_grid")

    def test_grid_budget_checked_before_tensor_traversal(self):
        model = table()
        for name in AXES:
            model[name] = list(range(1, 34))
        for name in LOSS_COLUMNS:
            model[name] = None
        self.reject(model, "grid_budget")

    def test_ragged_wrong_order_and_nonlist_tensors(self):
        for name in LOSS_COLUMNS:
            for bad in ([], None, [1, 2, 3], [[[]]*3]*3, [[[1]*4]*3]*3):
                model = table()
                model[name] = bad
                self.reject(model, "array_length")

    def test_all_samples_validated_not_only_interpolation_corners(self):
        for value in (-1, math.nan, math.inf, -math.inf, True, "1", 10**400):
            for name in LOSS_COLUMNS:
                model = table()
                model[name][0][0][0] = value  # selected cell has indices 1,1,1
                self.reject(model, "invalid_number")

    def test_nonfinite_and_boolean_coordinates_and_frequency(self):
        for value in (math.nan, math.inf, True, "300", 10**400, -1):
            self.reject(table(), "invalid_number", value)
            for name in ("operating_voltage_v", "operating_current_a", "switching_frequency_hz"):
                model = table()
                model[name] = value
                self.reject(model, "invalid_number")

    def test_interpolation_large_finite_constant_does_not_overflow(self):
        model = table()
        model["switching_frequency_hz"] = 0
        for name in LOSS_COLUMNS:
            model[name] = [[[sys.float_info.max]*3 for _ in range(3)] for _ in range(3)]
        self.assertEqual(evaluate_semiconductor_operating_loss(model, 350)["average_power_w"], sys.float_info.max)

    def test_power_product_and_total_overflow_have_coded_errors(self):
        model = table()
        model["switching_frequency_hz"] = sys.float_info.max
        for name in LOSS_COLUMNS[1:]:
            model[name] = [[[2.0]*3 for _ in range(3)] for _ in range(3)]
        self.reject(model, "numeric_range")
        model["switching_frequency_hz"] = 1
        for name in LOSS_COLUMNS:
            model[name] = [[[sys.float_info.max/2]*3 for _ in range(3)] for _ in range(3)]
        self.reject(model, "numeric_range")


if __name__ == "__main__":
    unittest.main()
