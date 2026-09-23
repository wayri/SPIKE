import unittest

from python.spikes import (
    CompiledBlock,
    FunctionalPlant,
    SessionCaptureMonitor,
    SignalDescriptor,
    SimulationSession,
    TriggerSpec,
    VirtualClockScheduler,
)


class SessionCaptureTests(unittest.TestCase):
    def test_continuous_session_retains_ring_and_trigger_windows_only(self):
        block = CompiledBlock.build(
            "crossing",
            (SignalDescriptor(0, "vout", "V", -1.0),),
            nominal_step_s=0.1,
            implementation_fingerprint="session-capture-test",
        )
        plant = FunctionalPlant(
            (-1.0,),
            lambda _time, _step, _inputs, previous: (previous[0] + 0.25,),
        )
        session = SimulationSession(block, plant)
        session.start()
        monitor = SessionCaptureMonitor(
            session,
            ("vout",),
            rolling_capacity_samples=4,
            trigger=TriggerSpec(0, 0.0, pretrigger_samples=2, posttrigger_samples=2),
        )
        events = monitor.run_steps(8, scheduler=VirtualClockScheduler())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].frames, ((-0.5,), (-0.25,), (0.0,), (0.25,), (0.5,)))
        window = monitor.rolling.snapshot()
        self.assertEqual(window.sample_count, 4)
        self.assertEqual(window.dropped_samples, 5)
        self.assertEqual(window.frames[-1], (1.0,))

    def test_user_or_limit_marker_can_capture_current_history(self):
        block = CompiledBlock.build(
            "manual",
            (SignalDescriptor(0, "current", "A", 0.0),),
            nominal_step_s=0.1,
            implementation_fingerprint="manual-capture-test",
        )
        session = SimulationSession(
            block,
            FunctionalPlant((0.0,), lambda _t, _dt, _inputs, previous: (previous[0] + 1.0,)),
        )
        session.start()
        monitor = SessionCaptureMonitor(
            session,
            ("current",),
            rolling_capacity_samples=4,
            trigger=TriggerSpec(0, 0.0, edge="manual", pretrigger_samples=1, posttrigger_samples=1),
        )
        monitor.run_steps(2, scheduler=VirtualClockScheduler())
        self.assertIsNone(monitor.mark_event("warning:soa_margin"))
        event = monitor.step(scheduler=VirtualClockScheduler())
        self.assertEqual(event.reason, "warning:soa_margin")
        self.assertEqual(event.frames, ((1.0,), (2.0,), (3.0,)))


if __name__ == "__main__":
    unittest.main()
