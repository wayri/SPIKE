"""JSON-compatible contracts for the first SPIKES circuit CLI slice."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping


PROJECT_CONTRACT = "spikes/circuit-project/v1"
RESULT_CONTRACT = "spikes/circuit-result/v1"
PROBE_CONTRACT = "spikes/probe/v1"

_NAME_RE = re.compile(r"^[A-Za-z0-9_.$:+-]+$", flags=re.ASCII)
_PROBE_RE = re.compile(r"^(?P<kind>[vViIpP])\((?P<targets>[^()]*)\)$", flags=re.ASCII)


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number) or (positive and number <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{label} must be {qualifier}.")
    return number


def _name(value: Any, label: str) -> str:
    normalized = str(value).strip()
    if not normalized or _NAME_RE.fullmatch(normalized) is None:
        raise ValueError(f"{label} contains unsupported characters.")
    return normalized


@dataclass(frozen=True, slots=True)
class SourceWaveform:
    """Bounded native independent-source waveform."""

    kind: str
    pulse: tuple[float, ...] = ()
    points: tuple[tuple[float, float], ...] = ()

    def __post_init__(self) -> None:
        kind = str(self.kind).strip().lower()
        if kind == "pulse":
            if len(self.pulse) != 7 or self.points:
                raise ValueError("PULSE waveform requires exactly seven values.")
            values = tuple(_finite(item, "PULSE value") for item in self.pulse)
            initial, pulsed, delay, rise, fall, width, period = values
            del initial, pulsed
            if min(delay, rise, fall, width) < 0.0 or period <= 0.0:
                raise ValueError("PULSE times must be nonnegative and period positive.")
            if rise + width + fall > period:
                raise ValueError("PULSE rise + width + fall must not exceed period.")
            object.__setattr__(self, "pulse", values)
        elif kind == "pwl":
            if self.pulse or not self.points or len(self.points) > 1_000_000:
                raise ValueError("PWL waveform requires 1 to 1,000,000 points.")
            normalized = tuple(
                (_finite(time, "PWL time"), _finite(value, "PWL value"))
                for time, value in self.points
            )
            if any(time < 0.0 for time, _ in normalized) or any(
                normalized[index][0] <= normalized[index - 1][0]
                for index in range(1, len(normalized))
            ):
                raise ValueError("PWL times must be nonnegative and strictly increasing.")
            object.__setattr__(self, "points", normalized)
        else:
            raise ValueError("Source waveform kind must be pulse or pwl.")
        object.__setattr__(self, "kind", kind)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            **({"pulse": list(self.pulse)} if self.kind == "pulse" else {}),
            **({"points": [list(point) for point in self.points]} if self.kind == "pwl" else {}),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SourceWaveform":
        return cls(
            kind=value.get("kind", ""),
            pulse=tuple(value.get("pulse", ())),
            points=tuple(tuple(point) for point in value.get("points", ())),
        )


@dataclass(frozen=True, slots=True)
class SwitchModel:
    """Native smooth voltage-controlled switch parameters."""

    on_resistance_ohm: float = 1.0e-3
    off_resistance_ohm: float = 1.0e9
    threshold_voltage_v: float = 0.5
    transition_voltage_v: float = 1.0e-3

    def __post_init__(self) -> None:
        on = _finite(self.on_resistance_ohm, "switch on resistance", positive=True)
        off = _finite(self.off_resistance_ohm, "switch off resistance", positive=True)
        threshold = _finite(self.threshold_voltage_v, "switch threshold")
        transition = _finite(self.transition_voltage_v, "switch transition", positive=True)
        if off <= on:
            raise ValueError("Switch off resistance must exceed on resistance.")
        object.__setattr__(self, "on_resistance_ohm", on)
        object.__setattr__(self, "off_resistance_ohm", off)
        object.__setattr__(self, "threshold_voltage_v", threshold)
        object.__setattr__(self, "transition_voltage_v", transition)

    def to_dict(self) -> dict[str, float]:
        return {
            "on_resistance_ohm": self.on_resistance_ohm,
            "off_resistance_ohm": self.off_resistance_ohm,
            "threshold_voltage_v": self.threshold_voltage_v,
            "transition_voltage_v": self.transition_voltage_v,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SwitchModel":
        return cls(
            on_resistance_ohm=value.get("on_resistance_ohm", 1.0e-3),
            off_resistance_ohm=value.get("off_resistance_ohm", 1.0e9),
            threshold_voltage_v=value.get("threshold_voltage_v", 0.5),
            transition_voltage_v=value.get("transition_voltage_v", 1.0e-3),
        )


@dataclass(frozen=True, slots=True)
class DiodeModel:
    """Bounded Shockley diode parameters accepted by the owned kernel."""

    saturation_current_a: float = 1.0e-14
    emission_coefficient: float = 1.0
    temperature_k: float = 300.15
    flicker_noise_coefficient: float = 0.0
    flicker_noise_exponent: float = 1.0

    def __post_init__(self) -> None:
        saturation_current = _finite(
            self.saturation_current_a, "diode saturation current", positive=True
        )
        emission = _finite(
            self.emission_coefficient, "diode emission coefficient", positive=True
        )
        temperature = _finite(
            self.temperature_k, "diode temperature", positive=True
        )
        flicker_coefficient = _finite(
            self.flicker_noise_coefficient, "diode flicker-noise coefficient"
        )
        flicker_exponent = _finite(
            self.flicker_noise_exponent, "diode flicker-noise exponent",
            positive=True,
        )
        if flicker_coefficient < 0.0:
            raise ValueError("diode flicker-noise coefficient must be nonnegative.")
        object.__setattr__(self, "saturation_current_a", saturation_current)
        object.__setattr__(self, "emission_coefficient", emission)
        object.__setattr__(self, "temperature_k", temperature)
        object.__setattr__(self, "flicker_noise_coefficient", flicker_coefficient)
        object.__setattr__(self, "flicker_noise_exponent", flicker_exponent)

    def to_dict(self) -> dict[str, float]:
        return {
            "saturation_current_a": self.saturation_current_a,
            "emission_coefficient": self.emission_coefficient,
            "temperature_k": self.temperature_k,
            "flicker_noise_coefficient": self.flicker_noise_coefficient,
            "flicker_noise_exponent": self.flicker_noise_exponent,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DiodeModel":
        return cls(
            saturation_current_a=value.get("saturation_current_a", 1.0e-14),
            emission_coefficient=value.get("emission_coefficient", 1.0),
            temperature_k=value.get("temperature_k", 300.15),
            flicker_noise_coefficient=value.get("flicker_noise_coefficient", 0.0),
            flicker_noise_exponent=value.get("flicker_noise_exponent", 1.0),
        )


@dataclass(frozen=True, slots=True)
class CircuitElement:
    """One supported, two-terminal linear R/L/C or independent source.

    A flattened subcircuit element uses a colon-delimited hierarchical name,
    for example ``XLOAD:R1``.  The final path component remains the SPICE
    primitive designator and therefore determines the element kind.
    """

    name: str
    kind: str
    positive_node: str
    negative_node: str
    value: float
    waveform: SourceWaveform | None = None
    control_positive_node: str | None = None
    control_negative_node: str | None = None
    control_source_id: str | None = None
    behavioral_expression: str | None = None
    switch_model: SwitchModel | None = None
    model_name: str | None = None
    diode_model: DiodeModel | None = None
    ac_magnitude: float = 0.0
    ac_phase_deg: float = 0.0
    initial_condition: float = 0.0

    def __post_init__(self) -> None:
        name = _name(self.name, "element name").upper()
        kind = str(self.kind).strip().lower()
        expected = {
            "resistor": "R",
            "capacitor": "C",
            "inductor": "L",
            "voltage_source": "V",
            "current_source": "I",
            "voltage_controlled_switch": "S",
            "diode": "D",
            "vcvs": "E",
            "vccs": "G",
            "cccs": "F",
            "ccvs": "H",
            "behavioral_voltage_source": "B",
            "behavioral_current_source": "B",
        }
        leaf_name = name.rsplit(":", 1)[-1]
        if kind not in expected or not (
            leaf_name.startswith(expected[kind])
            or (self.behavioral_expression is not None and leaf_name.startswith("B") and kind in {
                "voltage_source", "current_source", "vcvs", "vccs", "cccs", "ccvs"
            })
        ):
            raise ValueError("Element name and kind do not agree.")
        positive = _name(self.positive_node, "positive node")
        negative = _name(self.negative_node, "negative node")
        if positive.lower() == negative.lower():
            raise ValueError("Element terminals must be different nodes.")
        value = _finite(
            self.value,
            "element value",
            positive=kind in {"resistor", "capacitor", "inductor"},
        )
        is_source = kind in {"voltage_source", "current_source"}
        if self.waveform is not None and not is_source:
            raise ValueError("Only independent sources may carry a waveform.")
        voltage_controlled = kind in {"vcvs", "vccs"}
        current_controlled = kind in {"cccs", "ccvs"}
        if kind == "voltage_controlled_switch":
            if self.switch_model is None or self.control_positive_node is None or self.control_negative_node is None:
                raise ValueError("Controlled switch requires control nodes and switch model.")
            control_positive = _name(self.control_positive_node, "control positive node")
            control_negative = _name(self.control_negative_node, "control negative node")
            if control_positive.lower() == control_negative.lower():
                raise ValueError("Switch control terminals must be different nodes.")
            object.__setattr__(self, "control_positive_node", "0" if control_positive == "0" else control_positive.lower())
            object.__setattr__(self, "control_negative_node", "0" if control_negative == "0" else control_negative.lower())
        elif voltage_controlled:
            if self.control_positive_node is None or self.control_negative_node is None or self.control_source_id is not None:
                raise ValueError("Voltage-controlled sources require two control nodes and no control source ID.")
            control_positive = _name(self.control_positive_node, "control positive node")
            control_negative = _name(self.control_negative_node, "control negative node")
            if control_positive.lower() == control_negative.lower():
                raise ValueError("Controlled-source control terminals must be different nodes.")
            object.__setattr__(self, "control_positive_node", "0" if control_positive == "0" else control_positive.lower())
            object.__setattr__(self, "control_negative_node", "0" if control_negative == "0" else control_negative.lower())
        elif current_controlled:
            if self.control_source_id is None or any(item is not None for item in (
                self.control_positive_node, self.control_negative_node, self.switch_model
            )):
                raise ValueError("Current-controlled sources require exactly one control source ID.")
            object.__setattr__(self, "control_source_id", _name(self.control_source_id, "control source ID").upper())
        elif any(item is not None for item in (
            self.control_positive_node, self.control_negative_node, self.control_source_id, self.switch_model
        )):
            raise ValueError("Only controlled sources may carry control terminals or switch parameters.")
        if kind in {"behavioral_voltage_source", "behavioral_current_source"} and self.behavioral_expression is None:
            raise ValueError("A nonlinear behavioral source requires an expression.")
        if self.behavioral_expression is not None:
            expression = str(self.behavioral_expression).strip()
            if not expression or not leaf_name.startswith("B"):
                raise ValueError("A behavioral expression requires a B-designated element.")
            object.__setattr__(self, "behavioral_expression", expression)
        if kind == "diode":
            if self.diode_model is None or self.model_name is None:
                raise ValueError("Diode elements require a named diode model.")
            object.__setattr__(self, "model_name", _name(self.model_name, "diode model name").upper())
        elif self.diode_model is not None or self.model_name is not None:
            raise ValueError("Only a diode may carry a diode model or model name.")
        ac_magnitude = _finite(self.ac_magnitude, "AC source magnitude")
        ac_phase = _finite(self.ac_phase_deg, "AC source phase")
        if ac_magnitude < 0.0 or (not is_source and (ac_magnitude != 0.0 or ac_phase != 0.0)):
            raise ValueError("Only independent sources may carry a nonnegative AC phasor.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "positive_node", "0" if positive == "0" else positive.lower())
        object.__setattr__(self, "negative_node", "0" if negative == "0" else negative.lower())
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "ac_magnitude", ac_magnitude)
        object.__setattr__(self, "ac_phase_deg", ac_phase)
        initial_condition = _finite(self.initial_condition, "element initial condition")
        if kind not in {"capacitor", "inductor"} and initial_condition != 0.0:
            raise ValueError("Only capacitors and inductors may carry an initial condition.")
        object.__setattr__(self, "initial_condition", initial_condition)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "kind": self.kind,
            "positive_node": self.positive_node,
            "negative_node": self.negative_node,
            "value": self.value,
        }
        if self.waveform is not None:
            result["waveform"] = self.waveform.to_dict()
        if self.switch_model is not None:
            result.update(
                control_positive_node=self.control_positive_node,
                control_negative_node=self.control_negative_node,
                switch_model=self.switch_model.to_dict(),
            )
        elif self.control_positive_node is not None:
            result.update(
                control_positive_node=self.control_positive_node,
                control_negative_node=self.control_negative_node,
            )
        if self.control_source_id is not None:
            result["control_source_id"] = self.control_source_id
        if self.behavioral_expression is not None:
            result["behavioral_expression"] = self.behavioral_expression
        if self.diode_model is not None:
            result.update(
                model_name=self.model_name,
                diode_model=self.diode_model.to_dict(),
            )
        if self.kind in {"voltage_source", "current_source"} and (
            self.ac_magnitude != 0.0 or self.ac_phase_deg != 0.0
        ):
            result.update(
                ac_magnitude=self.ac_magnitude,
                ac_phase_deg=self.ac_phase_deg,
            )
        if self.kind in {"capacitor", "inductor"} and self.initial_condition != 0.0:
            result["initial_condition"] = self.initial_condition
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CircuitElement":
        waveform = value.get("waveform")
        switch_model = value.get("switch_model")
        diode_model = value.get("diode_model")
        if waveform is not None and not isinstance(waveform, Mapping):
            raise ValueError("element waveform must be an object.")
        if switch_model is not None and not isinstance(switch_model, Mapping):
            raise ValueError("element switch model must be an object.")
        if diode_model is not None and not isinstance(diode_model, Mapping):
            raise ValueError("element diode model must be an object.")
        return cls(
            name=value.get("name", ""),
            kind=value.get("kind", ""),
            positive_node=value.get("positive_node", ""),
            negative_node=value.get("negative_node", ""),
            value=value.get("value"),
            waveform=SourceWaveform.from_dict(waveform) if waveform is not None else None,
            control_positive_node=value.get("control_positive_node"),
            control_negative_node=value.get("control_negative_node"),
            control_source_id=value.get("control_source_id"),
            behavioral_expression=value.get("behavioral_expression"),
            switch_model=SwitchModel.from_dict(switch_model) if switch_model is not None else None,
            model_name=value.get("model_name"),
            diode_model=DiodeModel.from_dict(diode_model) if diode_model is not None else None,
            ac_magnitude=value.get("ac_magnitude", 0.0),
            ac_phase_deg=value.get("ac_phase_deg", 0.0),
            initial_condition=value.get("initial_condition", 0.0),
        )


@dataclass(frozen=True, slots=True)
class AnalysisDirective:
    """Operating point, DC/AC sweep, or bounded fixed-output-step transient."""

    mode: str
    source: str = ""
    start: float | None = None
    stop: float | None = None
    step: float | None = None
    time_step_s: float | None = None
    stop_time_s: float | None = None
    frequency_scale: str = ""
    frequency_points: int | None = None
    start_frequency_hz: float | None = None
    stop_frequency_hz: float | None = None
    use_initial_conditions: bool = False

    def __post_init__(self) -> None:
        mode = str(self.mode).strip().lower()
        if mode not in {"operating_point", "dc_sweep", "ac", "transient"}:
            raise ValueError("analysis mode must be operating_point, dc_sweep, ac, or transient.")
        object.__setattr__(self, "mode", mode)
        if not isinstance(self.use_initial_conditions, bool):
            raise ValueError("use_initial_conditions must be boolean.")
        if mode == "operating_point":
            if self.source or self.use_initial_conditions or any(
                item is not None
                for item in (
                    self.start, self.stop, self.step, self.time_step_s,
                    self.stop_time_s, self.frequency_points,
                    self.start_frequency_hz, self.stop_frequency_hz,
                )
            ):
                raise ValueError("Operating-point analysis cannot carry sweep or transient fields.")
            return
        if mode == "transient":
            if self.source or self.frequency_scale or any(item is not None for item in (
                self.start, self.stop, self.step, self.frequency_points,
                self.start_frequency_hz, self.stop_frequency_hz,
            )):
                raise ValueError("Transient analysis cannot carry DC sweep fields.")
            time_step = _finite(self.time_step_s, "transient time step", positive=True)
            stop_time = _finite(self.stop_time_s, "transient stop time", positive=True)
            if time_step > stop_time:
                raise ValueError("Transient time step must not exceed stop time.")
            object.__setattr__(self, "time_step_s", time_step)
            object.__setattr__(self, "stop_time_s", stop_time)
            return
        if mode == "ac":
            if self.use_initial_conditions:
                raise ValueError("AC analysis cannot request transient UIC semantics.")
            if any(item is not None for item in (
                self.start, self.stop, self.step, self.time_step_s,
                self.stop_time_s,
            )):
                raise ValueError("AC analysis cannot carry DC or transient fields.")
            source = _name(self.source, "AC source").upper()
            if not source.rsplit(":", 1)[-1].startswith(("V", "I")):
                raise ValueError("AC excitation must be an independent V or I source.")
            scale = str(self.frequency_scale).strip().lower()
            if scale not in {"lin", "dec", "oct"}:
                raise ValueError("AC frequency scale must be LIN, DEC, or OCT.")
            if isinstance(self.frequency_points, bool) or int(self.frequency_points or 0) != self.frequency_points:
                raise ValueError("AC frequency point count must be an integer.")
            points = int(self.frequency_points)
            if not 1 <= points <= 65_536:
                raise ValueError("AC frequency point count must be between 1 and 65536.")
            start_frequency = _finite(
                self.start_frequency_hz, "AC start frequency", positive=True
            )
            stop_frequency = _finite(
                self.stop_frequency_hz, "AC stop frequency", positive=True
            )
            if stop_frequency < start_frequency:
                raise ValueError("AC stop frequency must not be below its start.")
            object.__setattr__(self, "source", source)
            object.__setattr__(self, "frequency_scale", scale)
            object.__setattr__(self, "frequency_points", points)
            object.__setattr__(self, "start_frequency_hz", start_frequency)
            object.__setattr__(self, "stop_frequency_hz", stop_frequency)
            return
        if self.use_initial_conditions or self.time_step_s is not None or self.stop_time_s is not None or self.frequency_scale or any(
            item is not None for item in (
                self.frequency_points, self.start_frequency_hz,
                self.stop_frequency_hz,
            )
        ):
            raise ValueError("DC sweep analysis cannot carry transient fields.")
        source = _name(self.source, "sweep source").upper()
        if not source.rsplit(":", 1)[-1].startswith(("V", "I")):
            raise ValueError("DC sweep source must be an independent V or I source.")
        start = _finite(self.start, "sweep start")
        stop = _finite(self.stop, "sweep stop")
        step = _finite(self.step, "sweep step")
        if step == 0.0 or (stop - start) * step < 0.0:
            raise ValueError("Sweep step must be nonzero and point toward the stop value.")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "stop", stop)
        object.__setattr__(self, "step", step)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"mode": self.mode}
        if self.mode == "dc_sweep":
            result.update(source=self.source, start=self.start, stop=self.stop, step=self.step)
        elif self.mode == "transient":
            result.update(
                time_step_s=self.time_step_s,
                stop_time_s=self.stop_time_s,
                use_initial_conditions=self.use_initial_conditions,
            )
        elif self.mode == "ac":
            result.update(
                source=self.source,
                frequency_scale=self.frequency_scale,
                frequency_points=self.frequency_points,
                start_frequency_hz=self.start_frequency_hz,
                stop_frequency_hz=self.stop_frequency_hz,
            )
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AnalysisDirective":
        return cls(
            mode=value.get("mode", ""),
            source=value.get("source", ""),
            start=value.get("start"),
            stop=value.get("stop"),
            step=value.get("step"),
            time_step_s=value.get("time_step_s"),
            stop_time_s=value.get("stop_time_s"),
            frequency_scale=value.get("frequency_scale", ""),
            frequency_points=value.get("frequency_points"),
            start_frequency_hz=value.get("start_frequency_hz"),
            stop_frequency_hz=value.get("stop_frequency_hz"),
            use_initial_conditions=value.get("use_initial_conditions", False),
        )


@dataclass(frozen=True, slots=True)
class StepDirective:
    parameter: str
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        parameter = _name(self.parameter, "step parameter").lower()
        values = tuple(_finite(value, "step value") for value in self.values)
        if not values:
            raise ValueError("A step directive requires at least one value.")
        object.__setattr__(self, "parameter", parameter)
        object.__setattr__(self, "values", values)

    def to_dict(self) -> dict[str, Any]:
        return {"parameter": self.parameter, "values": list(self.values)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StepDirective":
        return cls(parameter=value.get("parameter", ""), values=tuple(value.get("values", ())))


@dataclass(frozen=True, slots=True)
class MeasureDirective:
    name: str
    analysis: str
    operation: str
    probe: ProbeDescriptor
    from_value: float | None = None
    to_value: float | None = None
    at_value: float | None = None

    def __post_init__(self) -> None:
        name = _name(self.name, "measurement name")
        analysis = str(self.analysis).strip().lower()
        operation = str(self.operation).strip().lower()
        if analysis not in {"op", "dc", "tran"}:
            raise ValueError("Measurement analysis must be op, dc, or tran.")
        if operation not in {"max", "min", "avg", "rms", "find"}:
            raise ValueError("Unsupported measurement operation.")
        start = None if self.from_value is None else _finite(self.from_value, "measurement FROM")
        stop = None if self.to_value is None else _finite(self.to_value, "measurement TO")
        at = None if self.at_value is None else _finite(self.at_value, "measurement AT")
        if (start is None) != (stop is None) or (start is not None and start > stop):
            raise ValueError("Measurement FROM and TO must be supplied together in ascending order.")
        if analysis == "op" and any(value is not None for value in (start, stop, at)):
            raise ValueError("Operating-point measurements do not accept FROM, TO, or AT.")
        if operation == "find" and analysis != "op" and at is None:
            raise ValueError("DC/transient FIND measurements require AT.")
        if operation != "find" and at is not None:
            raise ValueError("AT is valid only for FIND measurements.")
        if operation == "find" and (start is not None or stop is not None):
            raise ValueError("FIND does not accept a FROM/TO window.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "analysis", analysis)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "from_value", start)
        object.__setattr__(self, "to_value", stop)
        object.__setattr__(self, "at_value", at)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name, "analysis": self.analysis,
            "operation": self.operation, "probe": self.probe.to_dict(),
        }
        if self.from_value is not None:
            result.update(from_value=self.from_value, to_value=self.to_value)
        if self.at_value is not None:
            result["at_value"] = self.at_value
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MeasureDirective":
        probe = value.get("probe", {})
        if not isinstance(probe, Mapping):
            raise ValueError("Measurement probe must be an object.")
        return cls(
            name=value.get("name", ""), analysis=value.get("analysis", ""),
            operation=value.get("operation", ""), probe=ProbeDescriptor(
                contract=probe.get("contract", ""), name=probe.get("name", ""),
                quantity=probe.get("quantity", ""), targets=tuple(probe.get("targets", ())),
                unit=probe.get("unit", ""),
            ),
            from_value=value.get("from_value"), to_value=value.get("to_value"),
            at_value=value.get("at_value"),
        )


@dataclass(frozen=True, slots=True)
class StepVariant:
    parameters: tuple[tuple[str, float], ...]
    elements: tuple[CircuitElement, ...]

    def __post_init__(self) -> None:
        normalized = tuple((_name(name, "step parameter").lower(), _finite(value, "step value")) for name, value in self.parameters)
        if not normalized or len({name for name, _ in normalized}) != len(normalized):
            raise ValueError("Step variants require unique parameter values.")
        object.__setattr__(self, "parameters", normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameters": {name: value for name, value in self.parameters},
            "elements": [element.to_dict() for element in self.elements],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StepVariant":
        parameters = value.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise ValueError("Step-variant parameters must be an object.")
        return cls(
            parameters=tuple((str(name), number) for name, number in parameters.items()),
            elements=tuple(CircuitElement.from_dict(item) for item in value.get("elements", ())),
        )


@dataclass(frozen=True, slots=True)
class ProbeDescriptor:
    """Stable probe descriptor independent of plotting presentation."""

    name: str
    quantity: str
    targets: tuple[str, ...]
    unit: str
    contract: str = PROBE_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != PROBE_CONTRACT:
            raise ValueError(f"Expected probe contract {PROBE_CONTRACT}.")
        quantity = str(self.quantity).strip().lower()
        expected_counts = {"node_voltage": {1, 2}, "element_current": {1}, "element_power": {1}}
        if quantity not in expected_counts or len(self.targets) not in expected_counts[quantity]:
            raise ValueError("Probe quantity and target count do not agree.")
        normalized = tuple(
            ("0" if _name(target, "probe target") == "0" else _name(target, "probe target").lower())
            if quantity == "node_voltage" else _name(target, "probe target").upper()
            for target in self.targets
        )
        if any(not target for target in normalized):
            raise ValueError("Probe targets cannot be empty.")
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "targets", normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "name": self.name,
            "quantity": self.quantity,
            "targets": list(self.targets),
            "unit": self.unit,
        }

    @classmethod
    def parse(cls, expression: str) -> "ProbeDescriptor":
        compact = "".join(str(expression).split())
        matched = _PROBE_RE.fullmatch(compact)
        if matched is None:
            raise ValueError("Probe must use V(node), V(node,node), I(element), or P(element).")
        key = matched.group("kind").lower()
        raw_targets = matched.group("targets").split(",")
        if any(not item for item in raw_targets):
            raise ValueError("Probe targets cannot be empty.")
        targets = tuple(raw_targets)
        quantities = {"v": ("node_voltage", "V"), "i": ("element_current", "A"), "p": ("element_power", "W")}
        quantity, unit = quantities[key]
        canonical = f"{key.upper()}({','.join(targets)})"
        return cls(name=canonical, quantity=quantity, targets=targets, unit=unit)


@dataclass(frozen=True, slots=True)
class HierarchyInstance:
    """One elaborated subcircuit instance in a flattened circuit project."""

    path: str
    definition: str
    parent_path: str
    pins: tuple[str, ...]
    nodes: tuple[str, ...]

    def __post_init__(self) -> None:
        path = _name(self.path, "hierarchy path").upper()
        definition = _name(self.definition, "subcircuit definition").lower()
        parent = str(self.parent_path).strip()
        if parent:
            parent = _name(parent, "hierarchy parent path").upper()
            if path.rpartition(":")[0] != parent:
                raise ValueError("Hierarchy parent path does not match the instance path.")
        elif ":" in path:
            raise ValueError("Nested hierarchy instances require a parent path.")
        pins = tuple(_name(pin, "subcircuit pin").lower() for pin in self.pins)
        nodes = tuple(
            "0" if _name(node, "bound node") == "0" else _name(node, "bound node").lower()
            for node in self.nodes
        )
        if not pins or len(pins) != len(nodes) or len(pins) != len(set(pins)):
            raise ValueError("Hierarchy pins must be unique and match the bound-node count.")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "definition", definition)
        object.__setattr__(self, "parent_path", parent)
        object.__setattr__(self, "pins", pins)
        object.__setattr__(self, "nodes", nodes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "definition": self.definition,
            "parent_path": self.parent_path,
            "pins": list(self.pins),
            "nodes": list(self.nodes),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HierarchyInstance":
        return cls(
            path=value.get("path", ""),
            definition=value.get("definition", ""),
            parent_path=value.get("parent_path", ""),
            pins=tuple(value.get("pins", ())),
            nodes=tuple(value.get("nodes", ())),
        )


@dataclass(frozen=True, slots=True)
class CircuitProject:
    """Compiled intent from a supported textual netlist."""

    title: str
    elements: tuple[CircuitElement, ...]
    analysis: AnalysisDirective
    probes: tuple[ProbeDescriptor, ...] = ()
    source_name: str = "<memory>"
    source_sha256: str = ""
    contract: str = PROJECT_CONTRACT
    hierarchy: tuple[HierarchyInstance, ...] = ()
    global_nodes: tuple[str, ...] = ()
    steps: tuple[StepDirective, ...] = ()
    step_variants: tuple[StepVariant, ...] = ()
    measurements: tuple[MeasureDirective, ...] = ()
    temperature_c: float = 27.0

    def __post_init__(self) -> None:
        if self.contract != PROJECT_CONTRACT:
            raise ValueError(f"Expected project contract {PROJECT_CONTRACT}.")
        temperature = _finite(self.temperature_c, "circuit temperature")
        if not -273.15 < temperature <= 2000.0:
            raise ValueError("Circuit temperature must be above absolute zero and at most 2000 C.")
        object.__setattr__(self, "temperature_c", temperature)
        if not self.elements:
            raise ValueError("A circuit project requires at least one element.")
        names = [element.name.upper() for element in self.elements]
        if len(names) != len(set(names)):
            raise ValueError("Element names must be unique ignoring case.")
        if not any("0" in (element.positive_node, element.negative_node) for element in self.elements):
            raise ValueError("Circuit must contain explicit node 0 ground.")
        if self.analysis.mode in {"dc_sweep", "ac"} and self.analysis.source not in set(names):
            raise ValueError(f"Analysis source {self.analysis.source} does not exist.")
        if self.analysis.mode == "ac":
            excitation = next(
                element for element in self.elements
                if element.name == self.analysis.source
            )
            if excitation.kind not in {"voltage_source", "current_source"} or excitation.ac_magnitude <= 0.0:
                raise ValueError("AC analysis source must carry a positive AC magnitude.")
        element_names = set(names)
        voltage_defined = {
            element.name for element in self.elements
            if element.kind in {"voltage_source", "inductor", "vcvs", "ccvs"}
        }
        for element in self.elements:
            if element.kind in {"cccs", "ccvs"} and element.control_source_id not in voltage_defined:
                raise ValueError(
                    f"Current-controlled source {element.name} references unknown voltage-defined branch {element.control_source_id}."
                )
        nodes = {
            node
            for element in self.elements
            for node in (
                element.positive_node,
                element.negative_node,
                element.control_positive_node,
                element.control_negative_node,
            )
            if node is not None
        }
        global_nodes = tuple(
            _name(node, "global node").lower() for node in self.global_nodes
        )
        if "0" in global_nodes or len(global_nodes) != len(set(global_nodes)):
            raise ValueError("Global nodes must be unique and must not redeclare node 0.")
        object.__setattr__(self, "global_nodes", global_nodes)
        probe_names = [probe.name for probe in self.probes]
        if len(probe_names) != len(set(probe_names)):
            raise ValueError("Probe names must be unique.")
        for probe in self.probes:
            available = nodes if probe.quantity == "node_voltage" else element_names
            if any(target not in available for target in probe.targets):
                raise ValueError(f"Probe {probe.name} references an unknown target.")
        step_names = [step.parameter for step in self.steps]
        if len(step_names) != len(set(step_names)):
            raise ValueError("Step parameters must be unique.")
        expected_variants = math.prod(len(step.values) for step in self.steps) if self.steps else 0
        if bool(self.steps) != bool(self.step_variants) or (
            self.steps and len(self.step_variants) != expected_variants
        ):
            raise ValueError("Step directives and elaborated variants do not agree.")
        for variant in self.step_variants:
            if tuple(name for name, _ in variant.parameters) != tuple(step_names):
                raise ValueError("Step variant parameter order does not match directives.")
        measurement_names = [measure.name.lower() for measure in self.measurements]
        if len(measurement_names) != len(set(measurement_names)):
            raise ValueError("Measurement names must be unique ignoring case.")
        expected_analysis = {
            "operating_point": "op", "dc_sweep": "dc", "ac": "ac",
            "transient": "tran",
        }[self.analysis.mode]
        for measure in self.measurements:
            if measure.analysis != expected_analysis:
                raise ValueError(f"Measurement {measure.name} targets {measure.analysis}, not {expected_analysis}.")
            available = nodes if measure.probe.quantity == "node_voltage" else element_names
            if any(target not in available for target in measure.probe.targets):
                raise ValueError(f"Measurement {measure.name} references an unknown target.")
        instance_paths = [instance.path for instance in self.hierarchy]
        if len(instance_paths) != len(set(instance_paths)):
            raise ValueError("Hierarchy instance paths must be unique ignoring case.")
        known_paths: set[str] = set()
        for instance in self.hierarchy:
            if instance.parent_path and instance.parent_path not in known_paths:
                raise ValueError(f"Hierarchy parent {instance.parent_path} must precede its child.")
            known_paths.add(instance.path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "title": self.title,
            "elements": [element.to_dict() for element in self.elements],
            "analysis": self.analysis.to_dict(),
            "probes": [probe.to_dict() for probe in self.probes],
            "hierarchy": [instance.to_dict() for instance in self.hierarchy],
            "global_nodes": list(self.global_nodes),
            "steps": [step.to_dict() for step in self.steps],
            "step_variants": [variant.to_dict() for variant in self.step_variants],
            "measurements": [measure.to_dict() for measure in self.measurements],
            "temperature_c": self.temperature_c,
            "source": {"name": self.source_name, "sha256": self.source_sha256},
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CircuitProject":
        source = value.get("source", {})
        if not isinstance(source, Mapping):
            raise ValueError("project source must be an object.")
        raw_elements = value.get("elements", ())
        raw_probes = value.get("probes", ())
        raw_hierarchy = value.get("hierarchy", ())
        raw_globals = value.get("global_nodes", ())
        raw_steps = value.get("steps", ())
        raw_variants = value.get("step_variants", ())
        raw_measurements = value.get("measurements", ())
        if not all(isinstance(item, (list, tuple)) for item in (
            raw_elements, raw_probes, raw_hierarchy, raw_globals, raw_steps,
            raw_variants, raw_measurements,
        )):
            raise ValueError("project collection fields must be arrays.")
        analysis = value.get("analysis", {})
        if not isinstance(analysis, Mapping):
            raise ValueError("project analysis must be an object.")
        return cls(
            contract=value.get("contract", ""),
            title=str(value.get("title", "")),
            elements=tuple(CircuitElement.from_dict(item) for item in raw_elements),
            analysis=AnalysisDirective.from_dict(analysis),
            probes=tuple(
                ProbeDescriptor(
                    contract=item.get("contract", ""),
                    name=item.get("name", ""),
                    quantity=item.get("quantity", ""),
                    targets=tuple(item.get("targets", ())),
                    unit=item.get("unit", ""),
                )
                for item in raw_probes
            ),
            hierarchy=tuple(HierarchyInstance.from_dict(item) for item in raw_hierarchy),
            global_nodes=tuple(raw_globals),
            steps=tuple(StepDirective.from_dict(item) for item in raw_steps),
            step_variants=tuple(StepVariant.from_dict(item) for item in raw_variants),
            measurements=tuple(MeasureDirective.from_dict(item) for item in raw_measurements),
            temperature_c=value.get("temperature_c", 27.0),
            source_name=str(source.get("name", "<memory>")),
            source_sha256=str(source.get("sha256", "")),
        )


@dataclass(frozen=True, slots=True)
class CircuitResult:
    """Machine-readable SPIKES result envelope."""

    status: str
    model_status: str
    analysis: Mapping[str, Any]
    data: Mapping[str, Any] = field(default_factory=dict)
    probes: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    measurements: Mapping[str, Any] = field(default_factory=dict)
    issues: tuple[Mapping[str, Any], ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    contract: str = RESULT_CONTRACT

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "status": self.status,
            "model_status": self.model_status,
            "analysis": dict(self.analysis),
            "data": dict(self.data),
            "probes": dict(self.probes),
            "diagnostics": dict(self.diagnostics),
            "measurements": dict(self.measurements),
            "issues": [dict(issue) for issue in self.issues],
            "provenance": dict(self.provenance),
        }


__all__ = [
    "AnalysisDirective",
    "CircuitElement",
    "DiodeModel",
    "CircuitProject",
    "CircuitResult",
    "HierarchyInstance",
    "MeasureDirective",
    "PROBE_CONTRACT",
    "PROJECT_CONTRACT",
    "ProbeDescriptor",
    "RESULT_CONTRACT",
    "SourceWaveform",
    "StepDirective",
    "StepVariant",
    "SwitchModel",
]
