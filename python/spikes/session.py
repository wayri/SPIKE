"""Persistent lockstep and soft-real-time session orchestration for SPIKES.

The scheduler and Python plant adapter are intended for deterministic testing,
interactive dashboards, and soft-real-time co-simulation.  Python execution is
not deterministic-WCET, hard-real-time, or HIL qualified.
"""

from __future__ import annotations

import copy
import math
import time
from collections import deque
from dataclasses import replace
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence

from .session_contracts import (
    CompiledBlock,
    ControlType,
    InputDescriptor,
    SessionCheckpoint,
    SessionEvent,
    SessionStats,
)


class SessionError(RuntimeError):
    pass


class SessionStateError(SessionError):
    pass


class SessionStepError(SessionError):
    pass


class Lifecycle(str, Enum):
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    TRIPPED = "tripped"
    CLOSED = "closed"


class Plant(Protocol):
    """Pluggable numerical plant behind a compiled block contract."""

    def initialize(self, block: CompiledBlock) -> Sequence[float]: ...

    def step(
        self,
        simulation_time_s: float,
        step_s: float,
        inputs: Sequence[float],
        previous_signals: Sequence[float],
    ) -> Sequence[float]: ...

    def checkpoint(self) -> Any: ...

    def restore(self, state: Any) -> None: ...


class FunctionalPlant:
    """Small callback adapter useful for examples and controller integration."""

    def __init__(
        self,
        initial_signals: Sequence[float],
        step_function: Callable[[float, float, Sequence[float], Sequence[float]], Sequence[float]],
    ) -> None:
        self._initial = tuple(float(item) for item in initial_signals)
        self._step_function = step_function

    def initialize(self, block: CompiledBlock) -> Sequence[float]:
        return self._initial

    def step(
        self,
        simulation_time_s: float,
        step_s: float,
        inputs: Sequence[float],
        previous_signals: Sequence[float],
    ) -> Sequence[float]:
        return self._step_function(simulation_time_s, step_s, inputs, previous_signals)

    def checkpoint(self) -> Any:
        return None

    def restore(self, state: Any) -> None:
        if state is not None:
            raise ValueError("FunctionalPlant has no restorable private state.")


class Scheduler(Protocol):
    def monotonic_ns(self) -> int: ...

    def sleep_until_ns(self, target_ns: int) -> None: ...


class WallClockScheduler:
    """Best-effort wall-clock pacing; not a real-time scheduler."""

    def monotonic_ns(self) -> int:
        return time.perf_counter_ns()

    def sleep_until_ns(self, target_ns: int) -> None:
        remaining_ns = target_ns - self.monotonic_ns()
        if remaining_ns > 0:
            time.sleep(remaining_ns / 1_000_000_000.0)


class VirtualClockScheduler:
    """Manually advanced clock for deterministic scheduler tests."""

    def __init__(self, initial_ns: int = 0) -> None:
        self._now_ns = int(initial_ns)

    def monotonic_ns(self) -> int:
        return self._now_ns

    def sleep_until_ns(self, target_ns: int) -> None:
        self._now_ns = max(self._now_ns, int(target_ns))

    def advance_ns(self, duration_ns: int) -> None:
        if duration_ns < 0:
            raise ValueError("virtual clock cannot move backward.")
        self._now_ns += int(duration_ns)


class SimulationSession:
    """Persistent execution state for one immutable compiled block."""

    def __init__(
        self,
        block: CompiledBlock,
        plant: Plant,
        *,
        event_capacity: int = 1024,
        deadline_s: float | None = None,
        trip_after_consecutive_overruns: int | None = None,
    ) -> None:
        if event_capacity <= 0:
            raise ValueError("event_capacity must be positive.")
        if deadline_s is not None and (not math.isfinite(deadline_s) or deadline_s <= 0.0):
            raise ValueError("deadline_s must be finite and positive.")
        if trip_after_consecutive_overruns is not None and trip_after_consecutive_overruns <= 0:
            raise ValueError("trip_after_consecutive_overruns must be positive.")
        self.block = block
        self._plant = plant
        self._event_capacity = int(event_capacity)
        self._events: deque[SessionEvent] = deque(maxlen=self._event_capacity)
        self._event_sequence = 0
        self._stats = SessionStats()
        self._deadline_ns = None if deadline_s is None else round(deadline_s * 1_000_000_000)
        self._trip_overruns = trip_after_consecutive_overruns
        self._input_by_name = {item.name: item for item in block.inputs}
        self._signal_by_name = {item.name: item for item in block.signals}
        self._inputs = [item.default_value for item in block.inputs]
        self._pulse_remaining = [0.0 for _ in block.inputs]
        self._momentary_pending = [False for _ in block.inputs]
        self._ramp_targets: list[float | None] = [None for _ in block.inputs]
        self._signals = self._validated_signals(plant.initialize(block))
        self.lifecycle = Lifecycle.READY
        self.simulation_time_s = 0.0
        self.step_index = 0
        self._log("session_ready", "info", "Session initialized.")

    @property
    def stats(self) -> SessionStats:
        return replace(self._stats, dropped_events=max(0, self._event_sequence - len(self._events)))

    @property
    def events(self) -> tuple[SessionEvent, ...]:
        return tuple(self._events)

    @property
    def inputs(self) -> tuple[float, ...]:
        return tuple(self._inputs)

    @property
    def signals(self) -> tuple[float, ...]:
        return tuple(self._signals)

    def input_id(self, name: str) -> int:
        try:
            return self._input_by_name[name].id
        except KeyError as exc:
            raise KeyError(f"Unknown input {name!r}.") from exc

    def signal_id(self, name: str) -> int:
        try:
            return self._signal_by_name[name].id
        except KeyError as exc:
            raise KeyError(f"Unknown signal {name!r}.") from exc

    def read(self, signal: int | str) -> float:
        descriptor = self._resolve_signal(signal)
        return self._signals[descriptor.id]

    def start(self) -> None:
        self._require(Lifecycle.READY, Lifecycle.PAUSED)
        self.lifecycle = Lifecycle.RUNNING
        self._log("session_started", "info", "Session running.")

    def pause(self) -> None:
        self._require(Lifecycle.RUNNING)
        self.lifecycle = Lifecycle.PAUSED
        self._log("session_paused", "info", "Session paused.")

    def close(self) -> None:
        if self.lifecycle is Lifecycle.CLOSED:
            return
        self.lifecycle = Lifecycle.CLOSED
        self._log("session_closed", "info", "Session closed.")

    def apply_control(
        self,
        control: int | str,
        value: float | None = None,
        *,
        duration_s: float | None = None,
    ) -> float:
        if self.lifecycle in {Lifecycle.TRIPPED, Lifecycle.CLOSED}:
            raise SessionStateError(f"Controls cannot be applied while session is {self.lifecycle.value}.")
        item = self._resolve_input(control)
        index = item.id
        kind = item.control_type
        if kind is ControlType.MOMENTARY:
            if value is not None or duration_s is not None:
                raise ValueError("momentary control does not accept value or duration.")
            self._inputs[index] = item.active_value
            self._momentary_pending[index] = True
        elif kind is ControlType.TOGGLE:
            if duration_s is not None:
                raise ValueError("toggle control does not accept duration.")
            if value is None:
                self._inputs[index] = item.active_value if self._inputs[index] != item.active_value else item.default_value
            else:
                if not isinstance(value, (bool, int, float)) or float(value) not in (0.0, 1.0):
                    raise ValueError("toggle value must be boolean, zero, or one.")
                self._inputs[index] = item.active_value if bool(value) else item.default_value
        elif kind is ControlType.PULSE:
            if value is not None:
                raise ValueError("pulse control does not accept value.")
            duration = item.pulse_duration_s if duration_s is None else float(duration_s)
            if not math.isfinite(duration) or duration <= 0.0:
                raise ValueError("pulse duration must be finite and positive.")
            self._inputs[index] = item.active_value
            self._pulse_remaining[index] = duration
        elif kind is ControlType.SET:
            if value is None or duration_s is not None:
                raise ValueError("set control requires value and does not accept duration.")
            self._inputs[index] = self._bounded(item, value)
        elif kind is ControlType.INCREMENT:
            if value is None or duration_s is not None:
                raise ValueError("increment control requires a delta and does not accept duration.")
            self._inputs[index] = self._bounded(item, self._inputs[index] + float(value))
        elif kind is ControlType.ANALOG_RAMP:
            if value is None or duration_s is not None:
                raise ValueError("analog ramp requires a target and does not accept duration.")
            self._ramp_targets[index] = self._bounded(item, value)
        self._log(
            "control_applied",
            "info",
            f"Applied {kind.value} control {item.name}.",
            input_id=item.id,
            input_name=item.name,
            value=self._inputs[index],
            target=self._ramp_targets[index],
        )
        return self._inputs[index]

    def step(self, step_s: float | None = None, *, scheduler: Scheduler | None = None) -> tuple[float, ...]:
        self._require(Lifecycle.RUNNING)
        duration = self.block.nominal_step_s if step_s is None else float(step_s)
        if not math.isfinite(duration) or duration <= 0.0:
            raise ValueError("step_s must be finite and positive.")
        clock = scheduler or WallClockScheduler()
        self._advance_controls(duration)
        started = clock.monotonic_ns()
        try:
            candidate = self._plant.step(
                self.simulation_time_s, duration, tuple(self._inputs), tuple(self._signals)
            )
            next_signals = self._validated_signals(candidate)
        except Exception as exc:
            self.safe_trip(f"plant step failed: {exc}", code="plant_step_failure")
            raise SessionStepError(str(exc)) from exc
        elapsed = max(0, clock.monotonic_ns() - started)
        overrun = self._deadline_ns is not None and elapsed > self._deadline_ns
        consecutive = self._stats.consecutive_overruns + 1 if overrun else 0
        self._stats = replace(
            self._stats,
            steps=self._stats.steps + 1,
            measured_compute_ns=self._stats.measured_compute_ns + elapsed,
            maximum_compute_ns=max(self._stats.maximum_compute_ns, elapsed),
            deadline_overruns=self._stats.deadline_overruns + int(overrun),
            consecutive_overruns=consecutive,
        )
        self._signals = next_signals
        self.simulation_time_s += duration
        self.step_index += 1
        self._release_one_shots(duration)
        if overrun:
            self._log("deadline_overrun", "warning", "Soft deadline exceeded.", compute_ns=elapsed)
            if self._trip_overruns is not None and consecutive >= self._trip_overruns:
                self.safe_trip("consecutive soft deadline overruns", code="deadline_trip")
        return tuple(self._signals)

    def run_lockstep(
        self,
        steps: int,
        *,
        step_s: float | None = None,
        scheduler: Scheduler | None = None,
    ) -> tuple[float, ...]:
        if isinstance(steps, bool) or int(steps) != steps or steps < 0:
            raise ValueError("steps must be a non-negative integer.")
        for _ in range(int(steps)):
            self.step(step_s, scheduler=scheduler)
            if self.lifecycle is Lifecycle.TRIPPED:
                break
        return tuple(self._signals)

    def run_continuous(
        self,
        *,
        scheduler: Scheduler | None = None,
        max_steps: int | None = None,
        wall_duration_s: float | None = None,
    ) -> tuple[float, ...]:
        """Pace fixed simulation steps against a best-effort wall clock.

        At least one finite bound is mandatory. Late steps are never skipped, so
        numerical execution remains deterministic for the same control sequence.
        """
        self._require(Lifecycle.RUNNING)
        if max_steps is None and wall_duration_s is None:
            raise ValueError("continuous runs require max_steps or wall_duration_s.")
        if max_steps is not None and (
            isinstance(max_steps, bool) or int(max_steps) != max_steps or max_steps < 0
        ):
            raise ValueError("max_steps must be non-negative.")
        if wall_duration_s is not None and (not math.isfinite(wall_duration_s) or wall_duration_s < 0.0):
            raise ValueError("wall_duration_s must be finite and non-negative.")
        clock = scheduler or WallClockScheduler()
        period_ns = max(1, round(self.block.nominal_step_s * 1_000_000_000))
        epoch = clock.monotonic_ns()
        deadline = None if wall_duration_s is None else epoch + round(wall_duration_s * 1_000_000_000)
        completed = 0
        while self.lifecycle is Lifecycle.RUNNING:
            if max_steps is not None and completed >= max_steps:
                break
            target = epoch + (completed + 1) * period_ns
            if deadline is not None and target > deadline:
                break
            self.step(scheduler=clock)
            completed += 1
            now = clock.monotonic_ns()
            lateness = max(0, now - target)
            if lateness:
                self._stats = replace(
                    self._stats, maximum_lateness_ns=max(self._stats.maximum_lateness_ns, lateness)
                )
                self._log("scheduler_late", "warning", "Wall-clock scheduler is late.", lateness_ns=lateness)
            else:
                clock.sleep_until_ns(target)
        return tuple(self._signals)

    def safe_trip(self, reason: str, *, code: str = "user_trip") -> None:
        if self.lifecycle is Lifecycle.CLOSED:
            raise SessionStateError("Closed sessions cannot be tripped.")
        for item in self.block.inputs:
            self._inputs[item.id] = item.safe_value
        self._pulse_remaining = [0.0 for _ in self.block.inputs]
        self._momentary_pending = [False for _ in self.block.inputs]
        self._ramp_targets = [None for _ in self.block.inputs]
        self.lifecycle = Lifecycle.TRIPPED
        self._log("safe_trip", "critical", str(reason), code=code)

    def rearm(self) -> None:
        self._require(Lifecycle.TRIPPED)
        self.lifecycle = Lifecycle.READY
        self._log("session_rearmed", "warning", "Session explicitly re-armed at safe inputs.")

    def checkpoint(self) -> SessionCheckpoint:
        if self.lifecycle is Lifecycle.CLOSED:
            raise SessionStateError("Closed sessions cannot be checkpointed.")
        lifecycle = Lifecycle.PAUSED.value if self.lifecycle is Lifecycle.RUNNING else self.lifecycle.value
        control_state = {
            "pulse_remaining": list(self._pulse_remaining),
            "momentary_pending": list(self._momentary_pending),
            "ramp_targets": list(self._ramp_targets),
        }
        checkpoint = SessionCheckpoint(
            block_sha256=self.block.content_sha256,
            simulation_time_s=self.simulation_time_s,
            step_index=self.step_index,
            lifecycle=lifecycle,
            inputs=tuple(self._inputs),
            signals=tuple(self._signals),
            control_state=control_state,
            plant_state=copy.deepcopy(self._plant.checkpoint()),
        )
        checkpoint.to_dict()
        self._log("checkpoint_created", "info", "Session checkpoint created.")
        return checkpoint

    def restore(self, checkpoint: SessionCheckpoint) -> None:
        if self.lifecycle is Lifecycle.CLOSED:
            raise SessionStateError("Closed sessions cannot be restored.")
        if checkpoint.block_sha256 != self.block.content_sha256:
            raise ValueError("checkpoint belongs to a different compiled block.")
        if len(checkpoint.inputs) != len(self.block.inputs) or len(checkpoint.signals) != len(self.block.signals):
            raise ValueError("checkpoint vector sizes do not match the compiled block.")
        try:
            lifecycle = Lifecycle(checkpoint.lifecycle)
        except ValueError as exc:
            raise ValueError("checkpoint lifecycle is unsupported.") from exc
        if lifecycle in {Lifecycle.RUNNING, Lifecycle.CLOSED}:
            raise ValueError("checkpoint lifecycle cannot be running or closed.")
        state = checkpoint.control_state
        pulses = list(state.get("pulse_remaining", ()))
        momentary = list(state.get("momentary_pending", ()))
        ramps = list(state.get("ramp_targets", ()))
        if not (len(pulses) == len(momentary) == len(ramps) == len(self.block.inputs)):
            raise ValueError("checkpoint control state sizes do not match the compiled block.")
        restored_inputs = [
            self._bounded(item, checkpoint.inputs[item.id]) for item in self.block.inputs
        ]
        restored_signals = self._validated_signals(checkpoint.signals)
        restored_pulses = [float(item) for item in pulses]
        if any(not math.isfinite(item) or item < 0.0 for item in restored_pulses):
            raise ValueError("checkpoint pulse timers must be finite and non-negative.")
        restored_momentary = [bool(item) for item in momentary]
        restored_ramps = [
            None if value is None else self._bounded(self.block.inputs[index], value)
            for index, value in enumerate(ramps)
        ]
        if lifecycle is Lifecycle.TRIPPED and any(
            restored_inputs[item.id] != item.safe_value for item in self.block.inputs
        ):
            raise ValueError("tripped checkpoints must contain safe input values.")
        self._plant.restore(copy.deepcopy(checkpoint.plant_state))
        self._inputs = restored_inputs
        self._signals = restored_signals
        self._pulse_remaining = restored_pulses
        self._momentary_pending = restored_momentary
        self._ramp_targets = restored_ramps
        self.simulation_time_s = float(checkpoint.simulation_time_s)
        self.step_index = int(checkpoint.step_index)
        self.lifecycle = lifecycle
        self._log("checkpoint_restored", "info", "Session checkpoint restored.")

    def _advance_controls(self, duration: float) -> None:
        for item in self.block.inputs:
            target = self._ramp_targets[item.id]
            if target is None:
                continue
            current = self._inputs[item.id]
            delta = item.ramp_rate_per_s * duration
            if abs(target - current) <= delta:
                self._inputs[item.id] = target
                self._ramp_targets[item.id] = None
            else:
                self._inputs[item.id] = current + math.copysign(delta, target - current)

    def _release_one_shots(self, duration: float) -> None:
        for item in self.block.inputs:
            index = item.id
            if self._momentary_pending[index]:
                self._inputs[index] = item.default_value
                self._momentary_pending[index] = False
            if self._pulse_remaining[index] > 0.0:
                self._pulse_remaining[index] = max(0.0, self._pulse_remaining[index] - duration)
                if self._pulse_remaining[index] == 0.0:
                    self._inputs[index] = item.default_value

    def _validated_signals(self, values: Sequence[float]) -> list[float]:
        converted = [float(item) for item in values]
        if len(converted) != len(self.block.signals):
            raise ValueError("plant returned the wrong number of signals.")
        if any(not math.isfinite(item) for item in converted):
            raise ValueError("plant returned a non-finite signal.")
        return converted

    @staticmethod
    def _bounded(item: InputDescriptor, value: float) -> float:
        numeric = float(value)
        if not math.isfinite(numeric) or not item.minimum <= numeric <= item.maximum:
            raise ValueError(f"control value for {item.name} must be inside [{item.minimum}, {item.maximum}].")
        return numeric

    def _resolve_input(self, value: int | str) -> InputDescriptor:
        if isinstance(value, str):
            try:
                return self._input_by_name[value]
            except KeyError as exc:
                raise KeyError(f"Unknown input {value!r}.") from exc
        if isinstance(value, bool) or int(value) != value or not 0 <= int(value) < len(self.block.inputs):
            raise KeyError(f"Unknown input id {value!r}.")
        return self.block.inputs[int(value)]

    def _resolve_signal(self, value: int | str):
        if isinstance(value, str):
            try:
                return self._signal_by_name[value]
            except KeyError as exc:
                raise KeyError(f"Unknown signal {value!r}.") from exc
        if isinstance(value, bool) or int(value) != value or not 0 <= int(value) < len(self.block.signals):
            raise KeyError(f"Unknown signal id {value!r}.")
        return self.block.signals[int(value)]

    def _require(self, *states: Lifecycle) -> None:
        if self.lifecycle not in states:
            expected = ", ".join(item.value for item in states)
            raise SessionStateError(f"Session is {self.lifecycle.value}; expected {expected}.")

    def _log(self, kind: str, severity: str, message: str, **details: Any) -> None:
        event = SessionEvent(
            sequence=self._event_sequence,
            step_index=self.step_index,
            simulation_time_s=self.simulation_time_s,
            kind=kind,
            severity=severity,
            message=message,
            details=tuple(sorted(details.items())),
        )
        self._event_sequence += 1
        self._events.append(event)


__all__ = [
    "FunctionalPlant",
    "Lifecycle",
    "Plant",
    "Scheduler",
    "SessionError",
    "SessionStateError",
    "SessionStepError",
    "SimulationSession",
    "VirtualClockScheduler",
    "WallClockScheduler",
]
