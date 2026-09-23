"""Fail-closed deck adapter for the bounded nonlinear reference analyses.

This module intentionally does not widen :mod:`spikes.netlist`'s primary
analysis contract.  It removes exactly one nonlinear analysis card, elaborates
the remaining circuit as an operating-point deck, then dispatches to the
analytic-Jacobian reference analyses.  Unsupported SPICE variants are errors,
not silently changed into another calculation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from .analyses import AcExcitation
from .contracts import CircuitProject, ProbeDescriptor
from .netlist import parse_netlist, parse_spice_number
from .nonlinear_analyses import (
    run_biased_noise,
    run_local_distortion,
    run_nonlinear_adjoint_sensitivity,
    run_nonlinear_small_signal,
    run_two_tone_intermodulation,
)


NONLINEAR_DECK_REQUEST_CONTRACT = "spikes/nonlinear-deck-analysis-request/v1"
NONLINEAR_DECK_RESULT_CONTRACT = "spikes/nonlinear-deck-analysis-result/v1"
MAX_NONLINEAR_DECK_POINTS = 65_536
_ANALYSIS_RE = re.compile(r"(?i)^\s*\.(noise|sens|disto2|disto|nlss)\b")
_PRIMARY_RE = re.compile(r"(?i)^\s*\.(op|dc|tran)\b")


def _positive_number(token: str, label: str) -> float:
    value = parse_spice_number(token, "scalar")
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and positive.")
    return value


def _frequency_values(scale: str, points_per_interval: int, start_hz: float, stop_hz: float) -> tuple[float, ...]:
    scale = scale.lower()
    if scale not in {"lin", "dec", "oct"}:
        raise ValueError("NOISE sweep must be LIN, DEC, or OCT.")
    if isinstance(points_per_interval, bool) or points_per_interval < 1:
        raise ValueError("NOISE sweep point count must be a positive integer.")
    if stop_hz < start_hz:
        raise ValueError("NOISE stop frequency must not be below its start frequency.")
    if scale == "lin":
        count = points_per_interval
        values = (
            (start_hz,) if count == 1 else
            tuple(start_hz + index * (stop_hz - start_hz) / (count - 1) for index in range(count))
        )
    else:
        base = 10.0 if scale == "dec" else 2.0
        intervals = math.log(stop_hz / start_hz, base) if stop_hz > start_hz else 0.0
        count = int(math.floor(intervals * points_per_interval + 1.0e-12)) + 1
        values = tuple(start_hz * base ** (index / points_per_interval) for index in range(count))
        if values[-1] < stop_hz * (1.0 - 1.0e-12):
            values = (*values, stop_hz)
    if len(values) > MAX_NONLINEAR_DECK_POINTS:
        raise ValueError(f"Nonlinear deck sweep exceeds {MAX_NONLINEAR_DECK_POINTS} points.")
    return values


@dataclass(frozen=True, slots=True)
class NonlinearDeckRequest:
    mode: str
    output_probe: ProbeDescriptor
    source: str = ""
    frequency_hz: tuple[float, ...] = ()
    element_names: tuple[str, ...] = ()
    amplitude: float = 0.0
    amplitude_2: float = 0.0
    derivative_step: float | None = None
    magnitude: float = 1.0
    phase_deg: float = 0.0
    contract: str = NONLINEAR_DECK_REQUEST_CONTRACT

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "contract": self.contract,
            "mode": self.mode,
            "output_probe": self.output_probe.to_dict(),
        }
        if self.source:
            result["source"] = self.source
        if self.frequency_hz:
            result["frequency_hz"] = list(self.frequency_hz)
        if self.element_names:
            result["element_names"] = list(self.element_names)
        if self.amplitude:
            result["amplitude"] = self.amplitude
        if self.amplitude_2:
            result["amplitude_2"] = self.amplitude_2
        if self.derivative_step is not None:
            result["derivative_step"] = self.derivative_step
        if self.mode == "nonlinear_small_signal":
            result.update(magnitude=self.magnitude, phase_deg=self.phase_deg)
        return result


@dataclass(frozen=True, slots=True)
class ParsedNonlinearDeck:
    project: CircuitProject
    request: NonlinearDeckRequest


def _parse_card(card: str) -> NonlinearDeckRequest:
    tokens = card.split()
    keyword = tokens[0].lower()
    try:
        if keyword == ".noise":
            if len(tokens) != 7:
                raise ValueError("NOISE requires: .noise V(out) SOURCE LIN|DEC|OCT POINTS START STOP.")
            probe = ProbeDescriptor.parse(tokens[1])
            if probe.quantity != "node_voltage":
                raise ValueError("NOISE currently requires a voltage output probe.")
            points = int(tokens[4])
            if str(points) != tokens[4].lstrip("+"):
                raise ValueError("NOISE point count must be an integer.")
            frequencies = _frequency_values(
                tokens[3], points, _positive_number(tokens[5], "NOISE start frequency"),
                _positive_number(tokens[6], "NOISE stop frequency"),
            )
            return NonlinearDeckRequest("biased_noise", probe, source=tokens[2].upper(), frequency_hz=frequencies)
        if keyword == ".sens":
            if len(tokens) < 2:
                raise ValueError("SENS requires: .sens OUTPUT [ELEMENT ...].")
            return NonlinearDeckRequest(
                "adjoint_sensitivity", ProbeDescriptor.parse(tokens[1]),
                element_names=tuple(token.upper() for token in tokens[2:]),
            )
        if keyword == ".disto":
            if len(tokens) not in {4, 5}:
                raise ValueError(
                    "Bounded DISTO requires: .disto OUTPUT SOURCE AMPLITUDE [DERIVATIVE_STEP]; "
                    "the SPICE3 DEC/OCT form is not implemented."
                )
            return NonlinearDeckRequest(
                "local_distortion", ProbeDescriptor.parse(tokens[1]), source=tokens[2].upper(),
                amplitude=_positive_number(tokens[3], "DISTO amplitude"),
                derivative_step=None if len(tokens) == 4 else _positive_number(tokens[4], "DISTO derivative step"),
            )
        if keyword == ".disto2":
            if len(tokens) not in {5, 6}:
                raise ValueError(
                    "DISTO2 requires: .disto2 OUTPUT SOURCE AMPLITUDE1 AMPLITUDE2 [DERIVATIVE_STEP]."
                )
            return NonlinearDeckRequest(
                "two_tone_intermodulation", ProbeDescriptor.parse(tokens[1]), source=tokens[2].upper(),
                amplitude=_positive_number(tokens[3], "DISTO2 first amplitude"),
                amplitude_2=_positive_number(tokens[4], "DISTO2 second amplitude"),
                derivative_step=None if len(tokens) == 5 else _positive_number(tokens[5], "DISTO2 derivative step"),
            )
        if keyword == ".nlss":
            if len(tokens) not in {3, 4, 5}:
                raise ValueError("NLSS requires: .nlss OUTPUT SOURCE [MAGNITUDE [PHASE_DEG]].")
            magnitude = 1.0 if len(tokens) < 4 else _positive_number(tokens[3], "NLSS magnitude")
            phase = 0.0 if len(tokens) < 5 else parse_spice_number(tokens[4], "scalar")
            return NonlinearDeckRequest(
                "nonlinear_small_signal", ProbeDescriptor.parse(tokens[1]), source=tokens[2].upper(),
                magnitude=magnitude, phase_deg=phase,
            )
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"Invalid {keyword} card: {exc}") from exc
    raise ValueError(f"Unsupported nonlinear deck analysis {keyword}.")


def parse_nonlinear_analysis_deck(
    text: str,
    *,
    source_name: str = "<memory>",
    native_extensions: bool = False,
) -> ParsedNonlinearDeck:
    """Parse one bounded nonlinear analysis card and its operating-point circuit."""

    raw = str(text)
    cards: list[str] = []
    retained: list[str] = []
    primary: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if _ANALYSIS_RE.match(stripped):
            cards.append(stripped)
        else:
            retained.append(line)
            if _PRIMARY_RE.match(stripped):
                primary.append(stripped)
    if len(cards) != 1:
        raise ValueError("A nonlinear analysis deck requires exactly one .noise, .sens, .disto, .disto2, or .nlss card.")
    if len(primary) > 1 or (primary and not primary[0].lower().startswith(".op")):
        raise ValueError("Nonlinear deck analyses require an operating point and cannot be combined with DC or TRAN.")
    if not primary:
        end_index = next((index for index, line in enumerate(retained) if line.strip().lower() == ".end"), len(retained))
        retained.insert(end_index, ".op")
    request = _parse_card(cards[0])
    project = parse_netlist("\n".join(retained), source_name=source_name, native_extensions=native_extensions)
    names = {element.name for element in project.elements}
    nodes = {"0"}
    for element in project.elements:
        nodes.update((element.positive_node, element.negative_node))
    available = nodes if request.output_probe.quantity == "node_voltage" else names
    if any(target not in available for target in request.output_probe.targets):
        raise ValueError(f"Nonlinear deck output {request.output_probe.name} references an unknown target.")
    if request.source:
        source = next((element for element in project.elements if element.name == request.source), None)
        if source is None or source.kind not in {"voltage_source", "current_source"}:
            raise ValueError(f"Nonlinear deck source {request.source} must name an independent V or I source.")
    if request.element_names:
        missing = [name for name in request.element_names if name not in names]
        if missing:
            raise ValueError("SENS references unknown elements: " + ", ".join(missing))
    return ParsedNonlinearDeck(project, request)


def run_nonlinear_analysis_deck(deck: ParsedNonlinearDeck) -> dict[str, Any]:
    """Execute a previously parsed bounded nonlinear deck request."""

    project, request = deck.project, deck.request
    if request.mode == "biased_noise":
        result = run_biased_noise(
            project, request.output_probe, frequency_hz=request.frequency_hz
        )
        frequencies = request.frequency_hz
        gain = run_nonlinear_small_signal(
            project, AcExcitation(request.source), request.output_probe
        )["data"]["output"]["magnitude"]
        psd_values = result["data"]["output_noise_psd_v2_hz"]
        result["data"]["input_referred_noise_density_v_sqrt_hz"] = (
            None if gain == 0.0 else math.sqrt(float(psd_values[0])) / gain
        )
        result["data"]["input_referred_noise_density_v_sqrt_hz_by_frequency"] = (
            None if gain == 0.0 else [math.sqrt(float(value)) / gain for value in psd_values]
        )
    elif request.mode == "adjoint_sensitivity":
        element_names = request.element_names or tuple(
            element.name for element in project.elements
            if element.kind in {"resistor", "diode", "voltage_source", "current_source"}
        )
        if not element_names:
            raise ValueError("SENS found no supported R, D, V, or I parameters.")
        result = run_nonlinear_adjoint_sensitivity(project, request.output_probe, element_names)
    elif request.mode == "local_distortion":
        result = run_local_distortion(
            project, request.source, request.output_probe,
            amplitude=request.amplitude, derivative_step=request.derivative_step,
        )
    elif request.mode == "two_tone_intermodulation":
        result = run_two_tone_intermodulation(
            project, request.source, request.output_probe,
            amplitude_1=request.amplitude, amplitude_2=request.amplitude_2,
            derivative_step=request.derivative_step,
        )
    elif request.mode == "nonlinear_small_signal":
        result = run_nonlinear_small_signal(
            project, AcExcitation(request.source, request.magnitude, request.phase_deg),
            request.output_probe,
        )
    else:  # pragma: no cover - immutable requests originate in the parser
        raise ValueError(f"Unsupported nonlinear deck mode {request.mode}.")
    return {
        "contract": NONLINEAR_DECK_RESULT_CONTRACT,
        "status": result["status"],
        "analysis": request.to_dict(),
        "result": result,
        "issues": [],
        "provenance": {
            "implementation": "python.spikes.nonlinear_deck.fail_closed_adapter",
            "primary_analysis": "operating_point",
        },
    }


__all__ = [
    "NONLINEAR_DECK_REQUEST_CONTRACT", "NONLINEAR_DECK_RESULT_CONTRACT",
    "NonlinearDeckRequest", "ParsedNonlinearDeck",
    "parse_nonlinear_analysis_deck", "run_nonlinear_analysis_deck",
]
