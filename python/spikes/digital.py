"""Deterministic four-state digital event-kernel foundation for SPIKES.

This is an experimental owned reference kernel, not a Verilog/VHDL compiler.
It provides the event and signal semantics needed by a later HDL frontend and
mixed-signal bridge while failing closed on oscillating zero-delay networks.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import heapq
import re
from typing import Any


DIGITAL_MODEL_CONTRACT = "spikes/digital-model/v1"
DIGITAL_TRACE_CONTRACT = "spikes/digital-trace/v1"
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.$:-]{0,127}$", re.ASCII)


class DigitalModelError(ValueError):
    """A digital model or event request is invalid."""


class DigitalConvergenceError(RuntimeError):
    """A zero-delay network exceeded its bounded delta-cycle budget."""


class LogicValue(str, Enum):
    ZERO = "0"
    ONE = "1"
    X = "X"
    Z = "Z"

    @classmethod
    def parse(cls, value: Any) -> "LogicValue":
        if isinstance(value, cls):
            return value
        token = str(value).strip().upper()
        aliases = {"FALSE": "0", "TRUE": "1", "LOW": "0", "HIGH": "1"}
        try:
            return cls(aliases.get(token, token))
        except ValueError as exc:
            raise DigitalModelError(f"Unsupported four-state logic value: {value!r}.") from exc


def resolve_logic(drivers: tuple[LogicValue, ...]) -> LogicValue:
    """Resolve equal-strength four-state drivers deterministically."""

    active = tuple(value for value in drivers if value is not LogicValue.Z)
    if not active:
        return LogicValue.Z
    if LogicValue.X in active:
        return LogicValue.X
    return active[0] if all(value is active[0] for value in active) else LogicValue.X


@dataclass(frozen=True, slots=True)
class DigitalTransition:
    time_tick: int
    delta: int
    signal: str
    previous: LogicValue
    value: LogicValue

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_tick": self.time_tick,
            "delta": self.delta,
            "signal": self.signal,
            "previous": self.previous.value,
            "value": self.value.value,
        }


@dataclass(slots=True)
class _Signal:
    name: str
    value: LogicValue
    drivers: dict[str, LogicValue]


@dataclass(slots=True)
class _Primitive:
    primitive_id: str
    kind: str
    inputs: tuple[str, ...]
    output: str
    delay_ticks: int
    last_clock: LogicValue = LogicValue.X


class DigitalKernel:
    """Bounded deterministic event scheduler with integer simulation ticks."""

    _ARITY = {
        "buf": (1, 1),
        "not": (1, 1),
        "and": (2, 64),
        "or": (2, 64),
        "xor": (2, 64),
        "nand": (2, 64),
        "nor": (2, 64),
        "tristate": (2, 2),
        "dff": (2, 2),
    }

    def __init__(self, *, max_delta_cycles: int = 1024, trace_capacity: int = 100_000) -> None:
        if not isinstance(max_delta_cycles, int) or not 1 <= max_delta_cycles <= 1_000_000:
            raise DigitalModelError("max_delta_cycles must be an integer from 1 through 1000000.")
        if not isinstance(trace_capacity, int) or not 1 <= trace_capacity <= 10_000_000:
            raise DigitalModelError("trace_capacity must be an integer from 1 through 10000000.")
        self.max_delta_cycles = max_delta_cycles
        self.time_tick = 0
        self._signals: dict[str, _Signal] = {}
        self._primitives: dict[str, _Primitive] = {}
        self._fanout: dict[str, list[str]] = {}
        self._events: list[tuple[int, int, int, str, str, LogicValue]] = []
        self._sequence = 0
        self._trace: deque[DigitalTransition] = deque(maxlen=trace_capacity)
        self.dropped_transitions = 0

    @staticmethod
    def _name(value: str, label: str) -> str:
        name = str(value).strip()
        if _NAME.fullmatch(name) is None:
            raise DigitalModelError(f"{label} must be a bounded portable identifier.")
        return name

    def add_signal(self, name: str, initial: LogicValue | str = LogicValue.Z) -> None:
        name = self._name(name, "signal name")
        if name in self._signals:
            raise DigitalModelError(f"Duplicate digital signal: {name}.")
        value = LogicValue.parse(initial)
        drivers = {"$initial": value} if value is not LogicValue.Z else {}
        self._signals[name] = _Signal(name, value, drivers)
        self._fanout[name] = []

    def release_initial(self, signal: str) -> None:
        """Remove an initial-condition driver at the current simulation time."""

        self._require_signal(signal)
        self.drive(signal, "$initial", LogicValue.Z)

    def add_primitive(
        self,
        primitive_id: str,
        kind: str,
        inputs: tuple[str, ...] | list[str],
        output: str,
        *,
        delay_ticks: int = 0,
    ) -> None:
        primitive_id = self._name(primitive_id, "primitive id")
        kind = str(kind).strip().lower()
        if primitive_id in self._primitives:
            raise DigitalModelError(f"Duplicate digital primitive: {primitive_id}.")
        if kind not in self._ARITY:
            raise DigitalModelError(f"Unsupported digital primitive kind: {kind}.")
        normalized_inputs = tuple(str(item).strip() for item in inputs)
        low, high = self._ARITY[kind]
        if not low <= len(normalized_inputs) <= high:
            raise DigitalModelError(f"{kind} requires {low} through {high} inputs.")
        for signal in (*normalized_inputs, output):
            self._require_signal(signal)
        if not isinstance(delay_ticks, int) or not 0 <= delay_ticks <= 2**63 - 1:
            raise DigitalModelError("delay_ticks must be a non-negative 64-bit integer.")
        primitive = _Primitive(
            primitive_id, kind, normalized_inputs, output, delay_ticks,
            last_clock=self._signals[normalized_inputs[1]].value if kind == "dff" else LogicValue.X,
        )
        self._primitives[primitive_id] = primitive
        for signal in normalized_inputs:
            self._fanout[signal].append(primitive_id)
            self._fanout[signal].sort()
        if kind != "dff":
            self._schedule_primitive(primitive, self.time_tick, 0)

    def drive(
        self,
        signal: str,
        driver_id: str,
        value: LogicValue | str,
        *,
        delay_ticks: int = 0,
    ) -> None:
        self._require_signal(signal)
        driver_id = self._name(driver_id, "driver id") if driver_id != "$initial" else driver_id
        if not isinstance(delay_ticks, int) or delay_ticks < 0:
            raise DigitalModelError("delay_ticks must be a non-negative integer.")
        target_time = self.time_tick + delay_ticks
        delta = 1 if delay_ticks == 0 else 0
        self._push_event(target_time, delta, signal, driver_id, LogicValue.parse(value))

    def run_until(self, stop_tick: int) -> tuple[DigitalTransition, ...]:
        if not isinstance(stop_tick, int) or stop_tick < self.time_tick:
            raise DigitalModelError("stop_tick must be an integer at or after the current tick.")
        produced: list[DigitalTransition] = []
        while self._events and self._events[0][0] <= stop_tick:
            time_tick, delta, _, signal_name, driver_id, value = heapq.heappop(self._events)
            if delta > self.max_delta_cycles:
                raise DigitalConvergenceError(
                    f"Digital delta-cycle limit exceeded at tick {time_tick}; possible zero-delay oscillation."
                )
            self.time_tick = time_tick
            signal = self._signals[signal_name]
            if value is LogicValue.Z:
                signal.drivers.pop(driver_id, None)
            else:
                signal.drivers[driver_id] = value
            resolved = resolve_logic(tuple(signal.drivers.values()))
            if resolved is signal.value:
                continue
            previous = signal.value
            signal.value = resolved
            transition = DigitalTransition(time_tick, delta, signal_name, previous, resolved)
            produced.append(transition)
            if len(self._trace) == self._trace.maxlen:
                self.dropped_transitions += 1
            self._trace.append(transition)
            for primitive_id in self._fanout[signal_name]:
                self._schedule_primitive(self._primitives[primitive_id], time_tick, delta)
        self.time_tick = stop_tick
        return tuple(produced)

    def value(self, signal: str) -> LogicValue:
        self._require_signal(signal)
        return self._signals[signal].value

    def trace(self) -> dict[str, Any]:
        return {
            "contract": DIGITAL_TRACE_CONTRACT,
            "time_tick": self.time_tick,
            "transitions": [item.to_dict() for item in self._trace],
            "dropped_transitions": self.dropped_transitions,
        }

    def model(self) -> dict[str, Any]:
        return {
            "contract": DIGITAL_MODEL_CONTRACT,
            "status": "experimental",
            "signals": [
                {"name": name, "value": signal.value.value}
                for name, signal in sorted(self._signals.items())
            ],
            "primitives": [
                {
                    "id": item.primitive_id,
                    "kind": item.kind,
                    "inputs": list(item.inputs),
                    "output": item.output,
                    "delay_ticks": item.delay_ticks,
                }
                for item in sorted(self._primitives.values(), key=lambda value: value.primitive_id)
            ],
            "limitations": [
                "Reference primitive kernel only; no Verilog/VHDL frontend is implemented.",
                "All drivers currently use one strength and integer simulation ticks.",
                "No analog threshold, metastability probability, or timing-check model is implied.",
            ],
        }

    def _require_signal(self, signal: str) -> None:
        if signal not in self._signals:
            raise DigitalModelError(f"Unknown digital signal: {signal}.")

    def _push_event(
        self, time_tick: int, delta: int, signal: str, driver_id: str, value: LogicValue
    ) -> None:
        self._sequence += 1
        heapq.heappush(
            self._events,
            (time_tick, delta, self._sequence, signal, driver_id, value),
        )

    def _schedule_primitive(self, primitive: _Primitive, time_tick: int, source_delta: int) -> None:
        values = tuple(self._signals[name].value for name in primitive.inputs)
        if primitive.kind == "dff":
            clock = values[1]
            rising = primitive.last_clock is LogicValue.ZERO and clock is LogicValue.ONE
            primitive.last_clock = clock
            if not rising:
                return
            output_value = values[0] if values[0] in {LogicValue.ZERO, LogicValue.ONE} else LogicValue.X
        else:
            output_value = _gate_value(primitive.kind, values)
        if primitive.delay_ticks:
            target_time = time_tick + primitive.delay_ticks
            delta = 0
        else:
            target_time = time_tick
            delta = source_delta + 1
        self._push_event(target_time, delta, primitive.output, primitive.primitive_id, output_value)


def _gate_value(kind: str, values: tuple[LogicValue, ...]) -> LogicValue:
    binary = {LogicValue.ZERO, LogicValue.ONE}
    if kind == "buf":
        return values[0] if values[0] in binary else LogicValue.X
    if kind == "not":
        return LogicValue.ONE if values[0] is LogicValue.ZERO else (
            LogicValue.ZERO if values[0] is LogicValue.ONE else LogicValue.X
        )
    if kind == "tristate":
        data, enable = values
        if enable is LogicValue.ZERO:
            return LogicValue.Z
        if enable is LogicValue.ONE:
            return data
        return LogicValue.X
    if kind in {"and", "nand"}:
        result = LogicValue.ZERO if LogicValue.ZERO in values else (
            LogicValue.ONE if all(value is LogicValue.ONE for value in values) else LogicValue.X
        )
        return _gate_value("not", (result,)) if kind == "nand" else result
    if kind in {"or", "nor"}:
        result = LogicValue.ONE if LogicValue.ONE in values else (
            LogicValue.ZERO if all(value is LogicValue.ZERO for value in values) else LogicValue.X
        )
        return _gate_value("not", (result,)) if kind == "nor" else result
    if kind == "xor":
        if any(value not in binary for value in values):
            return LogicValue.X
        return LogicValue.ONE if sum(value is LogicValue.ONE for value in values) % 2 else LogicValue.ZERO
    raise DigitalModelError(f"Unsupported gate evaluation: {kind}.")


__all__ = [
    "DIGITAL_MODEL_CONTRACT",
    "DIGITAL_TRACE_CONTRACT",
    "DigitalConvergenceError",
    "DigitalKernel",
    "DigitalModelError",
    "DigitalTransition",
    "LogicValue",
    "resolve_logic",
]
