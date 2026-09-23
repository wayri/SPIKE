"""Bridge persistent SPIKES sessions into calibrated instrument waveforms."""

from __future__ import annotations

from typing import Any

from .instrument_contracts import (
    MAX_WAVEFORM_SAMPLES,
    CalibrationRecord,
    CalibrationState,
    SampledWaveform,
)
from .instruments import InstrumentError
from .native_abi import NativeTransientResult
from .session import Lifecycle, SimulationSession
from .streaming import EventCaptureEngine, RollingSampleBuffer
from .streaming_contracts import (
    CapturedEvent,
    StreamChannel,
    TriggerSpec,
    UniformStreamSchema,
)


class SessionWaveformRecorder:
    """Acquire one uniformly sampled signal while advancing a session lockstep.

    This is a synchronous reference bridge.  A GUI/HIL host will later consume
    the same waveform contract from a non-blocking bounded ring.
    """

    def __init__(self, session: SimulationSession, signal: int | str) -> None:
        self.session = session
        signal_id = session.signal_id(signal) if isinstance(signal, str) else int(signal)
        if not 0 <= signal_id < len(session.block.signals):
            raise InstrumentError("Recorder signal ID is outside the compiled block.")
        self.descriptor = session.block.signals[signal_id]
        if not self.descriptor.unit:
            raise InstrumentError("Instrument recording requires an explicit signal unit.")

    def capture(self, sample_count: int, *, scheduler: Any | None = None) -> SampledWaveform:
        if isinstance(sample_count, bool) or int(sample_count) != sample_count:
            raise InstrumentError("Sample count must be an integer.")
        sample_count = int(sample_count)
        if not 2 <= sample_count <= MAX_WAVEFORM_SAMPLES:
            raise InstrumentError(f"Sample count must be 2..{MAX_WAVEFORM_SAMPLES}.")
        if self.session.lifecycle is not Lifecycle.RUNNING:
            raise InstrumentError("Session must be running for lockstep instrument capture.")
        t0_s = self.session.simulation_time_s
        values = [self.session.read(self.descriptor.id)]
        for _ in range(sample_count - 1):
            self.session.step(scheduler=scheduler)
            if self.session.lifecycle is not Lifecycle.RUNNING:
                raise InstrumentError("Session tripped or stopped during instrument capture.")
            values.append(self.session.read(self.descriptor.id))
        calibration = CalibrationRecord(
            calibration_id=f"simulation.{self.session.block.content_sha256[:16]}",
            source="SPIKES compiled-block numerical coordinates",
            state=CalibrationState.VERIFIED,
            scale_verified=True,
            timebase_verified=True,
            uncertainty_fraction=0.0,
            notes="Coordinate calibration only; device/model qualification remains separate.",
        )
        return SampledWaveform(
            channel=self.descriptor.name,
            unit=self.descriptor.unit,
            sample_rate_hz=1.0 / self.session.block.nominal_step_s,
            samples=tuple(values),
            calibration=calibration,
            provenance=(
                f"compiled-block:{self.session.block.content_sha256}",
                "spikes.session-waveform-recorder/v1",
            ),
            t0_s=t0_s,
        )


def native_transient_waveform(
    result: NativeTransientResult,
    *,
    quantity: str,
    target: str,
) -> SampledWaveform:
    """Convert one uniformly spaced native transient vector for instruments."""

    if not isinstance(result, NativeTransientResult):
        raise InstrumentError("Native transient waveform conversion requires a native result.")
    if result.status != "converged":
        raise InstrumentError(f"Native transient result is not converged: {result.message}")
    quantity = str(quantity).strip().lower()
    readers = {
        "voltage": (result.node_voltage, "V"),
        "current": (result.element_current, "A"),
        "power": (result.element_power, "W"),
    }
    if quantity not in readers:
        raise InstrumentError("Quantity must be voltage, current, or power.")
    count = result.point_count
    if count < 2 or count > MAX_WAVEFORM_SAMPLES:
        raise InstrumentError("Native result does not contain a bounded multi-sample waveform.")
    times = tuple(result.time(index) for index in range(count))
    intervals = tuple(right - left for left, right in zip(times, times[1:]))
    first_interval = intervals[0]
    if first_interval <= 0.0:
        raise InstrumentError("Native transient timebase is not strictly increasing.")
    tolerance = max(1.0e-15, abs(first_interval) * 1.0e-10)
    if any(abs(interval - first_interval) > tolerance for interval in intervals[1:]):
        raise InstrumentError(
            "Native transient samples are not uniformly spaced; resampling must be explicit."
        )
    reader, unit = readers[quantity]
    values = tuple(reader(index, target) for index in range(count))
    calibration = CalibrationRecord(
        calibration_id="native.transient.api.v1",
        source="SPIKES native transient numerical coordinates",
        state=CalibrationState.VERIFIED,
        scale_verified=True,
        timebase_verified=True,
        uncertainty_fraction=0.0,
        notes="Coordinate calibration only; discretization and device-model error remain separate.",
    )
    return SampledWaveform(
        channel=f"{quantity}:{target}",
        unit=unit,
        sample_rate_hz=1.0 / first_interval,
        samples=values,
        calibration=calibration,
        provenance=(
            f"native-library:{result.library.path}",
            "spikes.native-transient-waveform/v1",
        ),
        t0_s=times[0],
    )


class SessionCaptureMonitor:
    """Bounded rolling/event capture around deterministic session steps."""

    def __init__(
        self,
        session: SimulationSession,
        signals: tuple[int | str, ...],
        *,
        rolling_capacity_samples: int,
        trigger: TriggerSpec | None = None,
        max_queued_events: int = 32,
    ) -> None:
        if not signals:
            raise InstrumentError("Session capture requires at least one signal.")
        descriptors = []
        for signal in signals:
            signal_id = session.signal_id(signal) if isinstance(signal, str) else int(signal)
            if not 0 <= signal_id < len(session.block.signals):
                raise InstrumentError("Session capture signal ID is outside the compiled block.")
            descriptor = session.block.signals[signal_id]
            if not descriptor.unit:
                raise InstrumentError(f"Signal {descriptor.name} lacks an explicit unit.")
            descriptors.append(descriptor)
        if len({item.id for item in descriptors}) != len(descriptors):
            raise InstrumentError("Session capture signals must be unique.")
        self.session = session
        self.signal_ids = tuple(item.id for item in descriptors)
        self.schema = UniformStreamSchema(
            stream_id=f"session.{session.block.name}",
            channels=tuple(StreamChannel(item.name, item.unit, "simulation_signal") for item in descriptors),
            sample_interval_s=session.block.nominal_step_s,
            t0_s=session.simulation_time_s,
            source_sha256=session.block.content_sha256,
        )
        self.rolling = RollingSampleBuffer(self.schema, rolling_capacity_samples)
        self.events = (
            EventCaptureEngine(self.schema, trigger, max_queued_events=max_queued_events)
            if trigger is not None else None
        )
        self._started = False

    def sample_current(self) -> CapturedEvent | None:
        frame = tuple(self.session.read(signal_id) for signal_id in self.signal_ids)
        self.rolling.append(frame)
        event = self.events.feed(frame) if self.events is not None else None
        self._started = True
        return event

    def step(self, *, scheduler: Any | None = None) -> CapturedEvent | None:
        if self.session.lifecycle is not Lifecycle.RUNNING:
            raise InstrumentError("Session must be running for continuous capture.")
        if not self._started:
            self.sample_current()
        self.session.step(scheduler=scheduler)
        return self.sample_current()

    def run_steps(self, steps: int, *, scheduler: Any | None = None) -> tuple[CapturedEvent, ...]:
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 0:
            raise InstrumentError("Capture step count must be a non-negative integer.")
        completed: list[CapturedEvent] = []
        for _ in range(steps):
            event = self.step(scheduler=scheduler)
            if event is not None:
                completed.append(event)
            if self.session.lifecycle is not Lifecycle.RUNNING:
                break
        return tuple(completed)

    def mark_event(self, reason: str = "user_marker") -> CapturedEvent | None:
        """Capture around the current sample for a user, limit, or solver event."""

        if self.events is None:
            raise InstrumentError("Session capture monitor has no event trigger configured.")
        if not self._started:
            self.sample_current()
        return self.events.trigger_now(reason)


__all__ = [
    "SessionCaptureMonitor", "SessionWaveformRecorder", "native_transient_waveform",
]
