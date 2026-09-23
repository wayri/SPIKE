import unittest
from dataclasses import FrozenInstanceError

from python.spikes.dynamic_devices import DynamicDeviceModelError
from python.spikes.static_compact_devices import (
    EbersMollBJT,
    Level1MOSFET,
    ShichmanHodgesJFET,
    StaticDeviceValidity,
)


def finite_jacobian(function, point, step=1e-6):
    columns = []
    for column in range(len(point)):
        plus, minus = list(point), list(point)
        plus[column] += step
        minus[column] -= step
        high, low = function(*plus), function(*minus)
        columns.append(tuple((a - b) / (2 * step) for a, b in zip(high, low)))
    return tuple(tuple(columns[c][r] for c in range(len(point))) for r in range(len(point)))


class StaticCompactDeviceTests(unittest.TestCase):
    def assert_jacobian_close(self, actual, expected, relative=2e-7):
        for row_a, row_e in zip(actual, expected):
            for value_a, value_e in zip(row_a, row_e):
                self.assertAlmostEqual(value_a, value_e, delta=max(1e-12, abs(value_e) * relative))

    def assert_kcl_and_gauge_invariance(self, result):
        self.assertAlmostEqual(sum(result.currents_a), 0.0, places=14)
        for row in result.jacobian_s:
            self.assertAlmostEqual(sum(row), 0.0, delta=1e-9 * max(1.0, *(abs(v) for v in row)))
        for column in range(len(result.terminal_names)):
            self.assertAlmostEqual(sum(row[column] for row in result.jacobian_s), 0.0,
                                   delta=1e-9 * max(1.0, *(abs(row[column]) for row in result.jacobian_s)))

    def test_ebers_moll_exact_jacobian_active_and_reverse_active(self):
        model = EbersMollBJT(forward_transport_factor=0.995, reverse_transport_factor=0.4)
        for point in ((3.0, 0.72, 0.0), (0.0, 0.72, 3.0), (0.2, 0.35, 0.0)):
            result = model.evaluate(*point, 300.15)
            numeric = finite_jacobian(
                lambda c, b, e: model.evaluate(c, b, e, 300.15).currents_a,
                point,
                1e-7,
            )
            self.assertEqual(result.jacobian_kind, "analytic")
            self.assert_jacobian_close(result.jacobian_s, numeric, 5e-9)
            self.assert_kcl_and_gauge_invariance(result)
        active = model.evaluate(3.0, 0.72, 0.0, 300.15)
        self.assertGreater(active.current("collector"), 0.0)
        self.assertGreater(active.current("base"), 0.0)
        self.assertLess(active.current("emitter"), 0.0)

    def test_bjt_temperature_scaling_and_fail_closed_envelope(self):
        model = EbersMollBJT(validity=StaticDeviceValidity(maximum_voltage_v=10.0,
                                                           maximum_absolute_current_a=10.0))
        cold = model.evaluate(2.0, 0.45, 0.0, 275.0).current("collector")
        hot = model.evaluate(2.0, 0.45, 0.0, 400.0).current("collector")
        self.assertGreater(hot, cold)
        with self.assertRaises(DynamicDeviceModelError):
            model.evaluate(11.0, 0.0, 0.0, 300.15)
        with self.assertRaises(DynamicDeviceModelError):
            model.evaluate(1.0, 0.0, 0.0, 100.0)

    def test_mosfet_regions_reverse_conduction_body_effect_and_jacobian(self):
        model = Level1MOSFET(
            threshold_voltage_v=1.0,
            transconductance_a_per_v2=0.02,
            channel_length_modulation_per_v=0.02,
            body_effect_v_sqrt=0.4,
        )
        cutoff = model.evaluate(1.0, 0.5, 0.0, 0.0, 300.15)
        linear = model.evaluate(0.2, 3.0, 0.0, 0.0, 300.15)
        saturation = model.evaluate(4.0, 3.0, 0.0, 0.0, 300.15)
        reverse = model.evaluate(0.0, 3.0, 1.0, 0.0, 300.15)
        self.assertEqual(cutoff.current("drain"), 0.0)
        self.assertGreater(linear.current("drain"), 0.0)
        self.assertGreater(saturation.current("drain"), 0.0)
        self.assertLess(reverse.current("drain"), 0.0)
        body_reverse_bias = model.evaluate(4.0, 3.0, 0.0, -1.0, 300.15)
        self.assertLess(body_reverse_bias.current("drain"), saturation.current("drain"))
        for result in (cutoff, linear, saturation, reverse, body_reverse_bias):
            self.assertEqual(result.jacobian_kind, "qualified_numeric")
            self.assert_kcl_and_gauge_invariance(result)

    def test_mos_numeric_jacobian_is_independently_qualified(self):
        model = Level1MOSFET(transconductance_a_per_v2=0.01,
                             channel_length_modulation_per_v=0.03,
                             body_effect_v_sqrt=0.2)
        point = (2.7, 2.2, 0.1, -0.2)
        result = model.evaluate(*point, 340.0)
        expected = finite_jacobian(
            lambda d, g, s, b: model.evaluate(d, g, s, b, 340.0).currents_a,
            point,
            1e-5,
        )
        self.assert_jacobian_close(result.jacobian_s, expected, 2e-7)

    def test_jfet_cutoff_linear_saturation_reverse_and_numeric_jacobian(self):
        model = ShichmanHodgesJFET(transconductance_a_per_v2=0.004,
                                   channel_length_modulation_per_v=0.01)
        self.assertEqual(model.evaluate(2.0, -3.0, 0.0, 300.15).current("drain"), 0.0)
        self.assertGreater(model.evaluate(0.2, 0.0, 0.0, 300.15).current("drain"), 0.0)
        saturated = model.evaluate(4.0, 0.0, 0.0, 300.15)
        self.assertGreater(saturated.current("drain"), 0.0)
        self.assertLess(model.evaluate(0.0, 0.0, 1.0, 300.15).current("drain"), 0.0)
        point = (3.0, -0.5, 0.0)
        result = model.evaluate(*point, 325.0)
        expected = finite_jacobian(
            lambda d, g, s: model.evaluate(d, g, s, 325.0).currents_a,
            point,
            1e-5,
        )
        self.assert_jacobian_close(result.jacobian_s, expected, 2e-7)
        self.assert_kcl_and_gauge_invariance(result)

    def test_invalid_parameters_and_immutability(self):
        for constructor, kwargs in (
            (EbersMollBJT, {"forward_transport_factor": 1.1}),
            (Level1MOSFET, {"transconductance_a_per_v2": 0.0}),
            (Level1MOSFET, {"body_effect_v_sqrt": -1.0}),
            (ShichmanHodgesJFET, {"pinch_off_voltage_v": 1.0}),
        ):
            with self.subTest(constructor=constructor.__name__), self.assertRaises(DynamicDeviceModelError):
                constructor(**kwargs)
        model = Level1MOSFET()
        with self.assertRaises(FrozenInstanceError):
            model.threshold_voltage_v = 2.0


if __name__ == "__main__":
    unittest.main()
