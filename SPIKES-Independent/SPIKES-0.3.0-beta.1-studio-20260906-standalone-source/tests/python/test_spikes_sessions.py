import json
import unittest

from python.spikes.session import (
    FunctionalPlant,
    Lifecycle,
    SessionStateError,
    SimulationSession,
    VirtualClockScheduler,
)
from python.spikes.session_contracts import (
    CompiledBlock,
    ControlType,
    InputDescriptor,
    SessionCheckpoint,
    SignalDescriptor,
)


def make_block(*, controls=None, step=0.1):
    return CompiledBlock.build(
        "test.integrator",
        (SignalDescriptor(0, "position", "m"),),
        tuple(controls or ()),
        nominal_step_s=step,
        metadata={"model_status": "reference"},
        implementation_fingerprint="integrator-v1",
    )


def integrator_plant(initial=0.0):
    return FunctionalPlant(
        (initial,),
        lambda _time, dt, inputs, signals: (signals[0] + dt * (inputs[0] if inputs else 1.0),),
    )


class CompiledBlockTests(unittest.TestCase):
    def test_ids_and_hash_are_stable_and_contract_is_explicitly_soft_realtime(self):
        controls = (InputDescriptor(0, "drive", ControlType.SET, minimum=-2, maximum=2),)
        first = make_block(controls=controls)
        second = make_block(controls=controls)
        self.assertEqual(first.content_sha256, second.content_sha256)
        self.assertEqual(first.signals[0].id, 0)
        self.assertEqual(first.inputs[0].id, 0)
        self.assertFalse(first.to_dict()["capabilities"]["hard_realtime_qualified"])
        encoded = json.loads(json.dumps(first.to_dict(), allow_nan=False))
        self.assertEqual(CompiledBlock.from_dict(encoded), first)

    def test_rejects_unstable_or_duplicate_descriptor_ids(self):
        with self.assertRaises(ValueError):
            CompiledBlock.build(
                "bad", (SignalDescriptor(1, "out"),), nominal_step_s=1e-3
            )


class SessionLifecycleTests(unittest.TestCase):
    def test_lockstep_is_deterministic_and_lifecycle_is_enforced(self):
        session = SimulationSession(make_block(), integrator_plant())
        self.assertEqual(session.lifecycle, Lifecycle.READY)
        with self.assertRaises(SessionStateError):
            session.step()
        session.start()
        session.run_lockstep(10)
        self.assertAlmostEqual(session.read("position"), 1.0)
        self.assertEqual(session.step_index, 10)
        self.assertAlmostEqual(session.simulation_time_s, 1.0)
        session.pause()
        with self.assertRaises(SessionStateError):
            session.step()
        session.start()
        session.close()
        self.assertEqual(session.lifecycle, Lifecycle.CLOSED)

    def test_checkpoint_restore_replays_identically(self):
        block = make_block()
        session = SimulationSession(block, integrator_plant())
        session.start()
        session.run_lockstep(3)
        checkpoint = session.checkpoint()
        encoded = json.loads(json.dumps(checkpoint.to_dict(), allow_nan=False))
        checkpoint = SessionCheckpoint.from_dict(encoded)
        session.run_lockstep(4)
        expected = session.signals
        session.restore(checkpoint)
        self.assertEqual(session.lifecycle, Lifecycle.PAUSED)
        session.start()
        session.run_lockstep(4)
        self.assertEqual(session.signals, expected)

    def test_checkpoint_rejects_a_different_compiled_block(self):
        session = SimulationSession(make_block(), integrator_plant())
        checkpoint = session.checkpoint()
        other = SimulationSession(
            CompiledBlock.build(
                "other", (SignalDescriptor(0, "position"),), nominal_step_s=0.1
            ),
            integrator_plant(),
        )
        with self.assertRaises(ValueError):
            other.restore(checkpoint)


class ControlTests(unittest.TestCase):
    def make_session(self, descriptor):
        session = SimulationSession(make_block(controls=(descriptor,)), integrator_plant())
        session.start()
        return session

    def test_set_increment_toggle_and_bounds(self):
        setter = self.make_session(
            InputDescriptor(0, "drive", ControlType.SET, minimum=-2, maximum=2)
        )
        setter.apply_control("drive", 2)
        setter.step()
        self.assertAlmostEqual(setter.read(0), 0.2)
        with self.assertRaises(ValueError):
            setter.apply_control(0, 3)

        increment = self.make_session(
            InputDescriptor(0, "trim", ControlType.INCREMENT, minimum=-2, maximum=2)
        )
        increment.apply_control(0, 0.5)
        self.assertEqual(increment.inputs, (0.5,))

        toggle = self.make_session(InputDescriptor(0, "enable", ControlType.TOGGLE))
        toggle.apply_control(0)
        self.assertEqual(toggle.inputs, (1.0,))
        toggle.apply_control(0)
        self.assertEqual(toggle.inputs, (0.0,))
        with self.assertRaises(ValueError):
            toggle.apply_control(0, 2)

    def test_momentary_pulse_and_analog_ramp_have_deterministic_step_semantics(self):
        momentary = self.make_session(InputDescriptor(0, "key_a", ControlType.MOMENTARY))
        momentary.apply_control("key_a")
        momentary.step()
        self.assertAlmostEqual(momentary.read(0), 0.1)
        self.assertEqual(momentary.inputs, (0.0,))

        pulse = self.make_session(
            InputDescriptor(0, "gate", ControlType.PULSE, pulse_duration_s=0.2)
        )
        pulse.apply_control(0)
        pulse.run_lockstep(3)
        self.assertAlmostEqual(pulse.read(0), 0.2)
        self.assertEqual(pulse.inputs, (0.0,))

        ramp = self.make_session(
            InputDescriptor(
                0, "command", ControlType.ANALOG_RAMP, maximum=2, ramp_rate_per_s=2
            )
        )
        ramp.apply_control(0, 1.0)
        ramp.run_lockstep(3)
        self.assertEqual(ramp.inputs, (0.6000000000000001,))


class SchedulingAndSafetyTests(unittest.TestCase):
    def test_continuous_mode_is_bounded_and_wall_clock_paced_without_skipping_steps(self):
        clock = VirtualClockScheduler()
        session = SimulationSession(make_block(step=0.001), integrator_plant())
        session.start()
        session.run_continuous(scheduler=clock, max_steps=5)
        self.assertEqual(session.step_index, 5)
        self.assertEqual(clock.monotonic_ns(), 5_000_000)
        self.assertFalse(session.stats.to_dict()["hard_realtime_qualified"])
        with self.assertRaises(ValueError):
            session.run_continuous(scheduler=clock)

    def test_deadline_overruns_are_counted_and_can_trip_to_safe_inputs(self):
        clock = VirtualClockScheduler()

        def slow_step(_time, dt, inputs, signals):
            clock.advance_ns(2_000_000)
            return (signals[0] + dt * inputs[0],)

        block = make_block(
            controls=(
                InputDescriptor(
                    0, "drive", ControlType.SET, default_value=1, safe_value=0
                ),
            ),
            step=0.001,
        )
        session = SimulationSession(
            block,
            FunctionalPlant((0,), slow_step),
            deadline_s=0.001,
            trip_after_consecutive_overruns=2,
        )
        session.start()
        session.run_lockstep(3, scheduler=clock)
        self.assertEqual(session.lifecycle, Lifecycle.TRIPPED)
        self.assertEqual(session.inputs, (0.0,))
        self.assertEqual(session.stats.deadline_overruns, 2)
        self.assertTrue(any(event.kind == "safe_trip" for event in session.events))
        session.rearm()
        self.assertEqual(session.lifecycle, Lifecycle.READY)

    def test_event_log_is_bounded_and_reports_drops(self):
        session = SimulationSession(make_block(), integrator_plant(), event_capacity=3)
        session.start()
        for _ in range(5):
            session.pause()
            session.start()
        session.pause()
        self.assertLessEqual(len(session.events), 3)
        self.assertGreater(session.stats.dropped_events, 0)


if __name__ == "__main__":
    unittest.main()
