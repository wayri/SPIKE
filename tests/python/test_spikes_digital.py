import unittest

from python.spikes.digital import (
    DIGITAL_MODEL_CONTRACT,
    DigitalConvergenceError,
    DigitalKernel,
    DigitalModelError,
    LogicValue,
    resolve_logic,
)


class SpikesDigitalKernelTests(unittest.TestCase):
    def test_run_returns_all_transitions_when_retained_trace_wraps(self):
        kernel = DigitalKernel(trace_capacity=1)
        kernel.add_signal("a")
        kernel.drive("a", "source", "0")
        kernel.drive("a", "source", "1")

        transitions = kernel.run_until(0)

        self.assertEqual([item.value for item in transitions], [LogicValue.ZERO, LogicValue.ONE])
        self.assertEqual(len(kernel.trace()["transitions"]), 1)
        self.assertEqual(kernel.dropped_transitions, 1)

    def test_four_state_driver_resolution(self):
        self.assertEqual(resolve_logic(()), LogicValue.Z)
        self.assertEqual(resolve_logic((LogicValue.Z, LogicValue.ONE)), LogicValue.ONE)
        self.assertEqual(resolve_logic((LogicValue.ONE, LogicValue.ONE)), LogicValue.ONE)
        self.assertEqual(resolve_logic((LogicValue.ZERO, LogicValue.ONE)), LogicValue.X)
        self.assertEqual(resolve_logic((LogicValue.X, LogicValue.ZERO)), LogicValue.X)

    def test_gate_delay_and_deterministic_delta_order(self):
        kernel = DigitalKernel()
        kernel.add_signal("a")
        kernel.add_signal("b")
        kernel.add_signal("y")
        kernel.add_primitive("g1", "and", ("a", "b"), "y", delay_ticks=3)
        kernel.drive("a", "stim_a", 1)
        kernel.drive("b", "stim_b", 1)
        kernel.run_until(2)
        self.assertEqual(kernel.value("y"), LogicValue.Z)
        transitions = kernel.run_until(3)
        self.assertEqual(kernel.value("y"), LogicValue.ONE)
        self.assertEqual(transitions[-1].time_tick, 3)

    def test_tristate_bus_conflict_and_release(self):
        kernel = DigitalKernel()
        kernel.add_signal("bus")
        kernel.drive("bus", "left", 1)
        kernel.drive("bus", "right", 0)
        kernel.run_until(0)
        self.assertEqual(kernel.value("bus"), LogicValue.X)
        kernel.drive("bus", "right", LogicValue.Z)
        kernel.run_until(0)
        self.assertEqual(kernel.value("bus"), LogicValue.ONE)

    def test_rising_edge_dff_captures_data_after_delay(self):
        kernel = DigitalKernel()
        for name in ("d", "clk", "q"):
            kernel.add_signal(name)
        kernel.drive("clk", "clock", 0)
        kernel.drive("d", "data", 1)
        kernel.run_until(0)
        kernel.add_primitive("ff1", "dff", ("d", "clk"), "q", delay_ticks=2)
        kernel.drive("clk", "clock", 1)
        kernel.run_until(1)
        self.assertEqual(kernel.value("q"), LogicValue.Z)
        kernel.run_until(2)
        self.assertEqual(kernel.value("q"), LogicValue.ONE)

    def test_zero_delay_oscillation_fails_closed(self):
        kernel = DigitalKernel(max_delta_cycles=16)
        kernel.add_signal("loop", LogicValue.ZERO)
        kernel.release_initial("loop")
        kernel.add_primitive("inv", "not", ("loop",), "loop")
        with self.assertRaises(DigitalConvergenceError):
            kernel.run_until(0)

    def test_model_is_versioned_and_invalid_models_are_rejected(self):
        kernel = DigitalKernel()
        kernel.add_signal("input")
        kernel.add_signal("output")
        kernel.add_primitive("buffer", "buf", ("input",), "output")
        self.assertEqual(kernel.model()["contract"], DIGITAL_MODEL_CONTRACT)
        with self.assertRaises(DigitalModelError):
            kernel.add_primitive("bad", "dff", ("input",), "output")
        with self.assertRaises(DigitalModelError):
            kernel.drive("missing", "driver", 1)


if __name__ == "__main__":
    unittest.main()
