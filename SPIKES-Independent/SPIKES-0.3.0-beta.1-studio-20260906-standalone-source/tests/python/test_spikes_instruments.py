import math
import json
import unittest

from python.spikes import (
    AcquisitionStatus,
    CalibrationRecord,
    CalibrationState,
    DMM,
    FrequencyResponse,
    InstrumentError,
    NetworkAnalyzer,
    SampledWaveform,
    Scope,
    ScopeTrigger,
    SpectrumAnalyzer,
    impedance_to_reflection,
    reflection_to_impedance,
    smith_coordinates,
)
from python.spikes.instrument_contracts import WAVEFORM_CONTRACT


def verified_calibration() -> CalibrationRecord:
    return CalibrationRecord(
        calibration_id="sim.scale.v1",
        source="SPIKES deterministic simulation scale",
        state=CalibrationState.VERIFIED,
        scale_verified=True,
        timebase_verified=True,
        uncertainty_fraction=1e-9,
    )


def waveform(samples, *, sample_rate_hz=100_000.0, status=AcquisitionStatus.VALID):
    return SampledWaveform(
        channel="vout",
        unit="V",
        sample_rate_hz=sample_rate_hz,
        samples=tuple(samples),
        calibration=verified_calibration(),
        provenance=("simulation:test-case",),
        status=status,
        t0_s=0.125,
    )


class InstrumentContractTests(unittest.TestCase):
    def test_waveform_has_versioned_explicit_time_axis_and_json_data(self):
        source = waveform((0.0, 1.0, 2.0), sample_rate_hz=20.0)
        self.assertEqual(source.contract, WAVEFORM_CONTRACT)
        self.assertEqual(source.sample_interval_s, 0.05)
        self.assertEqual(source.to_dict()["t0_s"], 0.125)
        self.assertEqual(source.to_dict()["sample_interval_s"], 0.05)
        self.assertEqual(source.to_dict()["calibration"]["state"], "verified")
        json.dumps(source.to_dict(), allow_nan=False)

    def test_nonfinite_and_malformed_acquisitions_fail_closed(self):
        with self.assertRaises(ValueError):
            waveform((0.0, math.nan))
        with self.assertRaises(ValueError):
            FrequencyResponse(
                name="dut",
                quantity="Z",
                unit="V",  # impedance has an unambiguous SI unit contract
                frequency_hz=(1.0,),
                values=(50.0,),
                reference_impedance_ohm=50.0,
                calibration=verified_calibration(),
                provenance=("test",),
            )

    def test_uncalibrated_or_clipped_data_cannot_make_physical_claims(self):
        uncalibrated = SampledWaveform(
            channel="vout",
            unit="V",
            sample_rate_hz=10.0,
            samples=(0.0, 1.0),
            calibration=CalibrationRecord(
                calibration_id="unknown.v1",
                source="unknown input",
                state=CalibrationState.UNCALIBRATED,
                scale_verified=False,
                timebase_verified=False,
            ),
            provenance=("untrusted:test",),
        )
        with self.assertRaises(InstrumentError):
            DMM().rms(uncalibrated)
        with self.assertRaises(InstrumentError):
            DMM().mean(waveform((0.0, 1.0), status=AcquisitionStatus.CLIPPED))


class ScopeTests(unittest.TestCase):
    def test_rising_trigger_capture_preserves_absolute_trigger_time(self):
        source = waveform((-2.0, -1.0, 1.0, 2.0, 2.0, 2.0), sample_rate_hz=10.0)
        capture = Scope().capture(
            source,
            trigger=ScopeTrigger(level=0.0, edge="rising"),
            record_length=4,
            pretrigger_samples=1,
        )
        self.assertEqual(capture.waveform.samples, (-1.0, 1.0, 2.0, 2.0))
        self.assertEqual(capture.trigger_index, 1)
        self.assertAlmostEqual(capture.trigger_time_s, 0.275)
        self.assertAlmostEqual(capture.waveform.t0_s, 0.225)

    def test_no_complete_triggered_record_is_an_error(self):
        with self.assertRaises(InstrumentError):
            Scope().capture(
                waveform((0.0, 1.0, 2.0, 3.0)),
                trigger=ScopeTrigger(level=10.0),
                record_length=3,
            )


class DMMAndSpectrumTests(unittest.TestCase):
    def test_dmm_mean_rms_ac_rms_and_frequency(self):
        sample_rate = 100_000.0
        frequency = 1_000.0
        values = tuple(2.0 + 3.0 * math.sin(2.0 * math.pi * frequency * index / sample_rate) for index in range(1000))
        source = waveform(values, sample_rate_hz=sample_rate)
        meter = DMM()
        self.assertAlmostEqual(meter.mean(source).value, 2.0, places=12)
        self.assertAlmostEqual(meter.rms(source).value, math.sqrt(4.0 + 4.5), places=12)
        self.assertAlmostEqual(meter.rms(source, ac_coupled=True).value, 3.0 / math.sqrt(2.0), places=12)
        self.assertAlmostEqual(meter.frequency(source).value, frequency, places=9)

    def test_fft_reports_one_sided_peak_amplitude_and_frequency(self):
        sample_rate = 1024.0
        values = tuple(2.5 * math.cos(2.0 * math.pi * 64.0 * index / sample_rate) for index in range(1024))
        trace = SpectrumAnalyzer().analyze(waveform(values, sample_rate_hz=sample_rate), window="rectangular")
        peak_index = max(range(1, len(trace.complex_amplitude)), key=lambda index: abs(trace.complex_amplitude[index]))
        self.assertEqual(trace.frequency_hz[peak_index], 64.0)
        self.assertAlmostEqual(abs(trace.complex_amplitude[peak_index]), 2.5, places=11)
        json.dumps(trace.to_dict(), allow_nan=False)

    def test_fft_configuration_is_bounded_and_explicit(self):
        with self.assertRaises(InstrumentError):
            SpectrumAnalyzer().analyze(waveform((0.0, 1.0, 0.0)), fft_points=6)
        with self.assertRaises(InstrumentError):
            SpectrumAnalyzer().analyze(waveform((0.0, 1.0)), window="mystery")


class NetworkAnalyzerTests(unittest.TestCase):
    def response(self, values, quantity="Z", unit="ohm"):
        return FrequencyResponse(
            name="negative_resistance_dut",
            quantity=quantity,
            unit=unit,
            frequency_hz=(1e6, 2e6),
            values=tuple(values),
            reference_impedance_ohm=50.0,
            calibration=verified_calibration(),
            provenance=("simulation:four-quadrant-dut",),
        )

    def test_s_z_round_trip_preserves_active_negative_resistance(self):
        analyzer = NetworkAnalyzer()
        impedance = self.response((-25.0 + 10.0j, 75.0 - 20.0j))
        reflection = analyzer.to_reflection(impedance)
        self.assertGreater(abs(reflection.values[0]), 1.0)
        restored = analyzer.to_impedance(reflection)
        for actual, expected in zip(restored.values, impedance.values):
            self.assertAlmostEqual(actual.real, expected.real, places=11)
            self.assertAlmostEqual(actual.imag, expected.imag, places=11)
        points = analyzer.smith(reflection)
        self.assertAlmostEqual(points[0].normalized_resistance, -0.5, places=12)
        self.assertAlmostEqual(points[0].normalized_reactance, 0.2, places=12)
        json.dumps(points[0].to_dict(), allow_nan=False)

    def test_scalar_conversions_and_smith_coordinates(self):
        gamma = impedance_to_reflection(100.0 + 50.0j, 50.0)
        self.assertAlmostEqual(reflection_to_impedance(gamma, 50.0).real, 100.0)
        self.assertEqual(smith_coordinates(gamma), (gamma.real, gamma.imag))
        with self.assertRaises(InstrumentError):
            reflection_to_impedance(1.0 + 0.0j)
        with self.assertRaises(InstrumentError):
            impedance_to_reflection(-50.0 + 0.0j)

    def test_network_claim_rejects_unverified_timebase(self):
        calibration = CalibrationRecord(
            calibration_id="scale-only.v1",
            source="scale-only test",
            state=CalibrationState.VERIFIED,
            scale_verified=True,
            timebase_verified=False,
        )
        response = FrequencyResponse(
            name="dut",
            quantity="S11",
            unit="1",
            frequency_hz=(1e6,),
            values=(0.1 + 0.2j,),
            reference_impedance_ohm=50.0,
            calibration=calibration,
            provenance=("test",),
        )
        with self.assertRaises(InstrumentError):
            NetworkAnalyzer().to_impedance(response)


if __name__ == "__main__":
    unittest.main()
