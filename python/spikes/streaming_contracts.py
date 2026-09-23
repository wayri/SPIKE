"""Versioned contracts for bounded continuous waveform capture."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


STREAM_SCHEMA_CONTRACT = "spikes/uniform-stream-schema/v1"
SAMPLE_WINDOW_CONTRACT = "spikes/sample-window/v1"
TRIGGER_CONTRACT = "spikes/event-trigger/v1"
CAPTURED_EVENT_CONTRACT = "spikes/captured-event/v1"

MAX_CHANNELS = 1024
MAX_BUFFER_SAMPLES = 16_777_216
MAX_CAPTURE_SAMPLES = 1_048_576

_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:/-]{0,127}$", re.ASCII)


def finite(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric, not boolean.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(result) or (positive and result <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{label} must be {qualifier}.")
    return result


def positive_integer(value: Any, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{label} must be an integer from 1 through {maximum}.")
    return value


def identifier(value: Any, label: str) -> str:
    normalized = str(value).strip()
    if _ID.fullmatch(normalized) is None:
        raise ValueError(f"{label} must be a bounded stable identifier.")
    return normalized


@dataclass(frozen=True, slots=True)
class StreamChannel:
    channel_id: str
    unit: str
    quantity: str = "value"

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel_id", identifier(self.channel_id, "channel ID"))
        unit = str(self.unit).strip()
        if not unit or len(unit) > 32:
            raise ValueError("Stream channels require a bounded explicit unit.")
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "quantity", identifier(self.quantity, "channel quantity"))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.channel_id, "unit": self.unit, "quantity": self.quantity}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StreamChannel":
        return cls(value.get("id", ""), value.get("unit", ""), value.get("quantity", "value"))


@dataclass(frozen=True, slots=True)
class UniformStreamSchema:
    stream_id: str
    channels: tuple[StreamChannel, ...]
    sample_interval_s: float
    t0_s: float = 0.0
    source_sha256: str = ""
    contract: str = STREAM_SCHEMA_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != STREAM_SCHEMA_CONTRACT:
            raise ValueError(f"Expected stream contract {STREAM_SCHEMA_CONTRACT}.")
        object.__setattr__(self, "stream_id", identifier(self.stream_id, "stream ID"))
        if not self.channels or len(self.channels) > MAX_CHANNELS:
            raise ValueError(f"Streams require 1..{MAX_CHANNELS} channels.")
        if len({item.channel_id for item in self.channels}) != len(self.channels):
            raise ValueError("Stream channel IDs must be unique.")
        object.__setattr__(self, "sample_interval_s", finite(self.sample_interval_s, "sample interval", positive=True))
        object.__setattr__(self, "t0_s", finite(self.t0_s, "stream start time"))
        digest = str(self.source_sha256).lower().strip()
        if digest and (len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)):
            raise ValueError("source_sha256 must be empty or lowercase SHA-256 hex.")
        object.__setattr__(self, "source_sha256", digest)

    def time_at(self, sample_index: int) -> float:
        if isinstance(sample_index, bool) or not isinstance(sample_index, int) or sample_index < 0:
            raise ValueError("sample index must be a non-negative integer.")
        return self.t0_s + sample_index * self.sample_interval_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "stream_id": self.stream_id,
            "channels": [item.to_dict() for item in self.channels],
            "sample_interval_s": self.sample_interval_s,
            "t0_s": self.t0_s,
            "source_sha256": self.source_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "UniformStreamSchema":
        if not isinstance(value, Mapping):
            raise ValueError("stream schema must be an object.")
        channels = value.get("channels", ())
        if not isinstance(channels, (list, tuple)):
            raise ValueError("stream channels must be an array.")
        if any(not isinstance(item, Mapping) for item in channels):
            raise ValueError("each stream channel must be an object.")
        return cls(
            contract=value.get("contract", ""),
            stream_id=value.get("stream_id", ""),
            channels=tuple(StreamChannel.from_dict(item) for item in channels),
            sample_interval_s=value.get("sample_interval_s"),
            t0_s=value.get("t0_s", 0.0),
            source_sha256=value.get("source_sha256", ""),
        )


def normalized_frame(values: Sequence[Any], channel_count: int) -> tuple[float, ...]:
    if len(values) != channel_count:
        raise ValueError(f"Sample frame requires exactly {channel_count} channel values.")
    return tuple(finite(value, f"channel {index}") for index, value in enumerate(values))


@dataclass(frozen=True, slots=True)
class SampleWindow:
    first_sample_index: int
    frames: tuple[tuple[float, ...], ...]
    dropped_samples: int = 0
    contract: str = SAMPLE_WINDOW_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != SAMPLE_WINDOW_CONTRACT:
            raise ValueError(f"Expected sample-window contract {SAMPLE_WINDOW_CONTRACT}.")
        if isinstance(self.first_sample_index, bool) or self.first_sample_index < 0:
            raise ValueError("first sample index must be non-negative.")
        if isinstance(self.dropped_samples, bool) or self.dropped_samples < 0:
            raise ValueError("dropped sample count must be non-negative.")

    @property
    def sample_count(self) -> int:
        return len(self.frames)


@dataclass(frozen=True, slots=True)
class TriggerSpec:
    channel_index: int
    level: float
    edge: str = "rising"
    hysteresis: float = 0.0
    pretrigger_samples: int = 256
    posttrigger_samples: int = 256
    holdoff_samples: int = 0
    contract: str = TRIGGER_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != TRIGGER_CONTRACT:
            raise ValueError(f"Expected trigger contract {TRIGGER_CONTRACT}.")
        if isinstance(self.channel_index, bool) or not isinstance(self.channel_index, int) or self.channel_index < 0:
            raise ValueError("trigger channel index must be non-negative.")
        object.__setattr__(self, "level", finite(self.level, "trigger level"))
        edge = str(self.edge).lower().strip()
        if edge not in {"rising", "falling", "either", "manual"}:
            raise ValueError("trigger edge must be rising, falling, either, or manual.")
        object.__setattr__(self, "edge", edge)
        hysteresis = finite(self.hysteresis, "trigger hysteresis")
        if hysteresis < 0.0:
            raise ValueError("trigger hysteresis cannot be negative.")
        object.__setattr__(self, "hysteresis", hysteresis)
        for name in ("pretrigger_samples", "posttrigger_samples", "holdoff_samples"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer.")
        if self.pretrigger_samples + self.posttrigger_samples + 1 > MAX_CAPTURE_SAMPLES:
            raise ValueError(f"event capture exceeds {MAX_CAPTURE_SAMPLES} samples.")


@dataclass(frozen=True, slots=True)
class CapturedEvent:
    event_sequence: int
    trigger_sample_index: int
    first_sample_index: int
    frames: tuple[tuple[float, ...], ...]
    trigger: TriggerSpec
    reason: str = "threshold"
    contract: str = CAPTURED_EVENT_CONTRACT

    @property
    def sample_count(self) -> int:
        return len(self.frames)

    def to_dict(self, *, include_samples: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "contract": self.contract,
            "event_sequence": self.event_sequence,
            "trigger_sample_index": self.trigger_sample_index,
            "first_sample_index": self.first_sample_index,
            "sample_count": self.sample_count,
            "reason": self.reason,
            "trigger": {
                "contract": self.trigger.contract,
                "channel_index": self.trigger.channel_index,
                "level": self.trigger.level,
                "edge": self.trigger.edge,
                "hysteresis": self.trigger.hysteresis,
                "pretrigger_samples": self.trigger.pretrigger_samples,
                "posttrigger_samples": self.trigger.posttrigger_samples,
                "holdoff_samples": self.trigger.holdoff_samples,
            },
        }
        if include_samples:
            result["frames"] = [list(frame) for frame in self.frames]
        return result


__all__ = [
    "CAPTURED_EVENT_CONTRACT", "MAX_BUFFER_SAMPLES", "MAX_CAPTURE_SAMPLES",
    "MAX_CHANNELS", "SAMPLE_WINDOW_CONTRACT", "STREAM_SCHEMA_CONTRACT",
    "TRIGGER_CONTRACT", "CapturedEvent", "SampleWindow", "StreamChannel",
    "TriggerSpec", "UniformStreamSchema", "finite", "normalized_frame",
    "positive_integer",
]
