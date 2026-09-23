"""Fixed-memory rolling buffers and trigger-driven continuous capture."""

from __future__ import annotations

from collections import deque
from typing import Sequence

from .streaming_contracts import (
    MAX_BUFFER_SAMPLES,
    CapturedEvent,
    SampleWindow,
    TriggerSpec,
    UniformStreamSchema,
    normalized_frame,
    positive_integer,
)


class StreamCaptureError(RuntimeError):
    pass


class RollingSampleBuffer:
    """A sequential multi-channel ring whose memory never grows after admission."""

    def __init__(self, schema: UniformStreamSchema, capacity_samples: int) -> None:
        self.schema = schema
        self.capacity_samples = positive_integer(
            capacity_samples, "rolling capacity", MAX_BUFFER_SAMPLES
        )
        self._frames: deque[tuple[float, ...]] = deque(maxlen=self.capacity_samples)
        self._next_sample_index = 0
        self._first_sample_index = 0
        self.dropped_samples = 0

    @property
    def next_sample_index(self) -> int:
        return self._next_sample_index

    def append(self, frame: Sequence[float], *, sample_index: int | None = None) -> int:
        index = self._next_sample_index if sample_index is None else sample_index
        if isinstance(index, bool) or not isinstance(index, int) or index != self._next_sample_index:
            raise ValueError(f"rolling sample index must be the next sequential index {self._next_sample_index}.")
        normalized = normalized_frame(frame, len(self.schema.channels))
        if len(self._frames) == self.capacity_samples:
            self._first_sample_index += 1
            self.dropped_samples += 1
        self._frames.append(normalized)
        self._next_sample_index += 1
        return index

    def extend(self, frames: Sequence[Sequence[float]]) -> None:
        for frame in frames:
            self.append(frame)

    def snapshot(self) -> SampleWindow:
        return SampleWindow(
            first_sample_index=self._first_sample_index,
            frames=tuple(self._frames),
            dropped_samples=self.dropped_samples,
        )

    def clear(self, *, preserve_index: bool = True) -> None:
        self._frames.clear()
        self._first_sample_index = self._next_sample_index if preserve_index else 0
        if not preserve_index:
            self._next_sample_index = 0
            self.dropped_samples = 0


class EventCaptureEngine:
    """Captures finite pre/post-trigger windows without retaining the full run."""

    def __init__(
        self,
        schema: UniformStreamSchema,
        trigger: TriggerSpec,
        *,
        max_queued_events: int = 32,
    ) -> None:
        if trigger.channel_index >= len(schema.channels):
            raise ValueError("trigger channel index is outside the stream schema.")
        self.schema = schema
        self.trigger = trigger
        self.max_queued_events = positive_integer(max_queued_events, "event queue capacity", 65_536)
        self._prehistory: deque[tuple[int, tuple[float, ...]]] = deque(
            maxlen=trigger.pretrigger_samples + 1
        )
        self._events: deque[CapturedEvent] = deque(maxlen=self.max_queued_events)
        self._next_sample_index = 0
        self._active_frames: list[tuple[float, ...]] | None = None
        self._active_trigger_index = 0
        self._active_first_index = 0
        self._active_reason = "threshold"
        self._post_remaining = 0
        self._holdoff_until = 0
        self._rising_armed = False
        self._falling_armed = False
        self._previous_value: float | None = None
        self.event_sequence = 0
        self.dropped_events = 0
        self.dropped_event_samples = 0

    @property
    def queued_events(self) -> tuple[CapturedEvent, ...]:
        return tuple(self._events)

    def feed(self, frame: Sequence[float], *, sample_index: int | None = None) -> CapturedEvent | None:
        index = self._next_sample_index if sample_index is None else sample_index
        if isinstance(index, bool) or not isinstance(index, int) or index != self._next_sample_index:
            raise ValueError(f"event sample index must be the next sequential index {self._next_sample_index}.")
        normalized = normalized_frame(frame, len(self.schema.channels))
        self._next_sample_index += 1
        value = normalized[self.trigger.channel_index]

        if self._active_frames is not None:
            self._active_frames.append(normalized)
            self._post_remaining -= 1
            completed = self._finish_active(index) if self._post_remaining == 0 else None
            self._prehistory.append((index, normalized))
            self._update_arming(value)
            self._previous_value = value
            return completed

        self._prehistory.append((index, normalized))
        triggered = index >= self._holdoff_until and self._detect(value)
        self._update_arming(value)
        self._previous_value = value
        if not triggered:
            return None

        return self._start_capture(index, "threshold")

    def _detect(self, value: float) -> bool:
        previous = self._previous_value
        if previous is None:
            return False
        rising = self._rising_armed and previous < self.trigger.level <= value
        falling = self._falling_armed and previous > self.trigger.level >= value
        return (
            self.trigger.edge == "either" and (rising or falling)
            or self.trigger.edge == "rising" and rising
            or self.trigger.edge == "falling" and falling
        )

    def trigger_now(self, reason: str = "manual") -> CapturedEvent | None:
        """Start an event at the newest retained sample without adding a frame."""

        normalized_reason = str(reason).strip()
        if not normalized_reason or len(normalized_reason) > 256:
            raise ValueError("event reason must be non-empty and at most 256 characters.")
        if self._active_frames is not None:
            raise StreamCaptureError("an event capture is already active.")
        if not self._prehistory:
            raise StreamCaptureError("manual trigger requires at least one prior sample.")
        index = self._prehistory[-1][0]
        return self._start_capture(index, normalized_reason)

    def _start_capture(self, index: int, reason: str) -> CapturedEvent | None:
        history = tuple(self._prehistory)
        self._active_frames = [item[1] for item in history]
        self._active_first_index = history[0][0]
        self._active_trigger_index = index
        self._active_reason = reason
        self._post_remaining = self.trigger.posttrigger_samples
        self._rising_armed = False
        self._falling_armed = False
        if self._post_remaining == 0:
            return self._finish_active(index)
        return None

    def _update_arming(self, value: float) -> None:
        if value <= self.trigger.level - self.trigger.hysteresis:
            self._rising_armed = True
        if value >= self.trigger.level + self.trigger.hysteresis:
            self._falling_armed = True

    def _finish_active(self, final_index: int) -> CapturedEvent:
        assert self._active_frames is not None
        self.event_sequence += 1
        event = CapturedEvent(
            event_sequence=self.event_sequence,
            trigger_sample_index=self._active_trigger_index,
            first_sample_index=self._active_first_index,
            frames=tuple(self._active_frames),
            trigger=self.trigger,
            reason=self._active_reason,
        )
        if len(self._events) == self.max_queued_events:
            dropped = self._events[0]
            self.dropped_events += 1
            self.dropped_event_samples += dropped.sample_count
        self._events.append(event)
        self._active_frames = None
        self._post_remaining = 0
        self._holdoff_until = final_index + self.trigger.holdoff_samples + 1
        return event

    def pop_event(self) -> CapturedEvent | None:
        return self._events.popleft() if self._events else None

    def flush_incomplete(self) -> None:
        """Discard an unfinished post-trigger window and count its samples."""

        if self._active_frames is not None:
            self.dropped_event_samples += len(self._active_frames)
            self._active_frames = None
            self._post_remaining = 0


__all__ = ["EventCaptureEngine", "RollingSampleBuffer", "StreamCaptureError"]
