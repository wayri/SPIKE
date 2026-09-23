import unittest

from python.spikes import (
    CompiledBlock,
    DMM,
    FunctionalPlant,
    InstrumentError,
    SessionWaveformRecorder,
    SignalDescriptor,
    SimulationSession,
    SpectrumAnalyzer,
    VirtualClockScheduler,
)


def session(unit="V"):
    block = CompiledBlock.build(
        "ramp",
        (SignalDescriptor(0, "vout", unit, 0.0),),
        nominal_step_s=0.001,
        implementation_fingerprint="instrument-session-fixture",
    )
    plant = FunctionalPlant((0.0,), lambda time_s, step_s, _inputs, _previous: (time_s + step_s,))
    return SimulationSession(block, plant)


class SessionInstrumentTests(unittest.TestCase):
    def test_lockstep_capture_has_exact_simulation_timebase_and_provenance(self):
        simulation = session()
        simulation.start()
        waveform = SessionWaveformRecorder(simulation, "vout").capture(
            5, scheduler=VirtualClockScheduler()
        )
        self.assertEqual(waveform.samples, (0.0, 0.001, 0.002, 0.003, 0.004))
        self.assertEqual(waveform.sample_rate_hz, 1000.0)
        self.assertEqual(simulation.step_index, 4)
        self.assertIn(simulation.block.content_sha256, waveform.provenance[0])
        self.assertAlmostEqual(DMM().mean(waveform).value, 0.002)
        self.assertTrue(SpectrumAnalyzer().analyze(waveform).frequency_hz)

    def test_capture_requires_running_session_explicit_units_and_bounds(self):
        simulation = session()
        recorder = SessionWaveformRecorder(simulation, 0)
        with self.assertRaises(InstrumentError):
            recorder.capture(2)
        with self.assertRaises(InstrumentError):
            SessionWaveformRecorder(session(unit=""), 0)
        simulation.start()
        with self.assertRaises(InstrumentError):
            recorder.capture(1)


if __name__ == "__main__":
    unittest.main()
