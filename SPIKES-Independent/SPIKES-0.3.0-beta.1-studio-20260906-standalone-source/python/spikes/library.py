"""Immutable built-in archetype registry for the current SPIKES capabilities."""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

try:
    from python.spike_core.native_mna import REQUEST_CONTRACT as NATIVE_REQUEST_CONTRACT
    from python.spike_core.native_mna import validate_native_mna_request
except ModuleNotFoundError as exc:
    if exc.name != "python":
        raise
    from spike_core.native_mna import REQUEST_CONTRACT as NATIVE_REQUEST_CONTRACT
    from spike_core.native_mna import validate_native_mna_request

from .library_contracts import (
    ELABORATION_CONTRACT,
    LIBRARY_CONTRACT,
    LIBRARY_VALIDATION_CONTRACT,
    ArchetypeDescriptor,
    ArchetypePreset,
    ParameterSpec,
)
from .version import ENGINE_VERSION


LIBRARY_VERSION = ENGINE_VERSION
_INSTANCE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$", flags=re.ASCII)
_ELABORATORS = {
    "resistor",
    "dc_voltage_source",
    "dc_current_source",
    "vcvs",
    "vccs",
    "voltage_divider",
    "thevenin_source",
    "norton_source",
}


class ArchetypeLibraryError(ValueError):
    """A deterministic library lookup, parameter, or elaboration failure."""


class ArchetypeUnavailableError(ArchetypeLibraryError):
    """Raised when an explicitly unavailable descriptor is elaborated."""


def _provenance(validation: str = "experimental") -> dict[str, Any]:
    return {
        "origin": "spikes_builtin",
        "implementation": "python.spikes.library",
        "library_version": LIBRARY_VERSION,
        "validation": validation,
        "external_model": False,
    }


def _parameter(
    name: str,
    unit: str,
    default: float,
    minimum: float,
    maximum: float,
    description: str,
) -> ParameterSpec:
    return ParameterSpec(name, unit, default, minimum, maximum, description)


_RESISTANCE = lambda name="resistance_ohm", default=1000.0, description="Linear resistance.": _parameter(  # noqa: E731
    name, "ohm", default, 1e-12, 1e15, description,
)
_VOLTAGE = lambda name="voltage_v", default=5.0, description="Constant DC voltage.": _parameter(  # noqa: E731
    name, "V", default, -1e12, 1e12, description,
)
_CURRENT = lambda name="current_a", default=1e-3, description="Constant DC current.": _parameter(  # noqa: E731
    name, "A", default, -1e9, 1e9, description,
)


def _builtins() -> tuple[ArchetypeDescriptor, ...]:
    runnable = (
        ArchetypeDescriptor(
            archetype_id="spikes.ideal:resistor@1",
            title="Ideal linear resistor",
            family="passive.resistor",
            summary="Temperature-invariant positive linear resistance.",
            status="runnable",
            fidelity="mathematical_ideal",
            pins=("positive", "negative"),
            parameters=(_RESISTANCE(),),
            presets=(
                ArchetypePreset("one_k", "1 kOhm", {"resistance_ohm": 1e3}),
                ArchetypePreset("ten_k", "10 kOhm", {"resistance_ohm": 1e4}),
                ArchetypePreset("one_meg", "1 MOhm", {"resistance_ohm": 1e6}),
            ),
            tags=("ideal", "linear", "passive", "resistor"),
            required_capabilities=("native.linear_mna.resistor",),
            elaborator="resistor",
            limitations=("No temperature coefficient, tolerance, noise, parasitics, power rating, or failure behavior.",),
            provenance=_provenance(),
        ),
        ArchetypeDescriptor(
            archetype_id="spikes.ideal:dc_voltage_source@1",
            title="Ideal DC voltage source",
            family="source.voltage",
            summary="Zero-impedance constant independent voltage source.",
            status="runnable",
            fidelity="mathematical_ideal",
            pins=("positive", "negative"),
            parameters=(_VOLTAGE(),),
            presets=(
                ArchetypePreset("zero", "0 V", {"voltage_v": 0.0}),
                ArchetypePreset("logic_3v3", "3.3 V", {"voltage_v": 3.3}),
                ArchetypePreset("logic_5v", "5 V", {"voltage_v": 5.0}),
                ArchetypePreset("bench_12v", "12 V", {"voltage_v": 12.0}),
            ),
            tags=("dc", "ideal", "source", "voltage"),
            required_capabilities=("native.linear_mna.voltage_source",),
            elaborator="dc_voltage_source",
            limitations=("No source impedance, limits, noise, ripple, dynamics, or protection behavior.",),
            provenance=_provenance(),
        ),
        ArchetypeDescriptor(
            archetype_id="spikes.ideal:dc_current_source@1",
            title="Ideal DC current source",
            family="source.current",
            summary="Infinite-impedance constant independent current source.",
            status="runnable",
            fidelity="mathematical_ideal",
            pins=("positive", "negative"),
            parameters=(_CURRENT(),),
            presets=(
                ArchetypePreset("zero", "0 A", {"current_a": 0.0}),
                ArchetypePreset("one_ma", "1 mA", {"current_a": 1e-3}),
                ArchetypePreset("ten_ma", "10 mA", {"current_a": 1e-2}),
            ),
            tags=("current", "dc", "ideal", "source"),
            required_capabilities=("native.linear_mna.current_source",),
            elaborator="dc_current_source",
            limitations=("No compliance voltage, output resistance, limits, noise, or dynamics.",),
            provenance=_provenance(),
        ),
        ArchetypeDescriptor(
            archetype_id="spikes.ideal:vcvs@1",
            title="Linear voltage-controlled voltage source",
            family="controlled_source.vcvs",
            summary="Four-terminal linear differential voltage-gain block.",
            status="runnable",
            fidelity="mathematical_ideal",
            pins=("output_positive", "output_negative", "control_positive", "control_negative"),
            parameters=(_parameter("gain", "1", 1.0, -1e12, 1e12, "Differential voltage gain."),),
            presets=(
                ArchetypePreset("buffer", "Unity buffer", {"gain": 1.0}),
                ArchetypePreset("inverting", "Inverting unity gain", {"gain": -1.0}),
                ArchetypePreset("gain_ten", "Gain of ten", {"gain": 10.0}),
            ),
            tags=("controlled", "gain", "ideal", "linear", "vcvs", "voltage"),
            required_capabilities=("native.linear_mna.vcvs",),
            elaborator="vcvs",
            limitations=("Not an op-amp: no rails, saturation, bandwidth, slew rate, input current, or stability behavior.",),
            provenance=_provenance(),
        ),
        ArchetypeDescriptor(
            archetype_id="spikes.ideal:vccs@1",
            title="Linear voltage-controlled current source",
            family="controlled_source.vccs",
            summary="Four-terminal linear differential transconductance block.",
            status="runnable",
            fidelity="mathematical_ideal",
            pins=("output_positive", "output_negative", "control_positive", "control_negative"),
            parameters=(_parameter("transconductance_s", "S", 1e-3, -1e9, 1e9, "Differential transconductance."),),
            presets=(
                ArchetypePreset("one_ms", "1 mS", {"transconductance_s": 1e-3}),
                ArchetypePreset("ten_ms", "10 mS", {"transconductance_s": 1e-2}),
                ArchetypePreset("inverting_one_ms", "-1 mS", {"transconductance_s": -1e-3}),
            ),
            tags=("controlled", "current", "ideal", "linear", "transconductance", "vccs"),
            required_capabilities=("native.linear_mna.vccs",),
            elaborator="vccs",
            limitations=("No output compliance, impedance, bandwidth, noise, or nonlinear transfer behavior.",),
            provenance=_provenance(),
        ),
        ArchetypeDescriptor(
            archetype_id="spikes.ideal:voltage_divider@1",
            title="Two-resistor voltage divider",
            family="network.resistive",
            summary="Reusable three-pin linear divider assembled from two ideal resistors.",
            status="runnable",
            fidelity="mathematical_ideal",
            pins=("input", "output", "reference"),
            parameters=(
                _RESISTANCE("top_resistance_ohm", 10e3, "Resistance from input to output."),
                _RESISTANCE("bottom_resistance_ohm", 10e3, "Resistance from output to reference."),
            ),
            presets=(
                ArchetypePreset("half", "1:2 divider", {"top_resistance_ohm": 10e3, "bottom_resistance_ohm": 10e3}),
                ArchetypePreset("one_tenth", "1:10 divider", {"top_resistance_ohm": 90e3, "bottom_resistance_ohm": 10e3}),
            ),
            tags=("divider", "linear", "network", "resistor", "voltage"),
            required_capabilities=("native.linear_mna.resistor",),
            elaborator="voltage_divider",
            limitations=("No loading compensation, tolerance, noise, temperature, parasitics, or ratings.",),
            provenance=_provenance(),
        ),
        ArchetypeDescriptor(
            archetype_id="spikes.ideal:thevenin_source@1",
            title="Thevenin DC source",
            family="source.equivalent",
            summary="Constant voltage source with positive series resistance.",
            status="runnable",
            fidelity="generic_functional",
            pins=("positive", "negative"),
            parameters=(
                _VOLTAGE("open_circuit_voltage_v", 5.0, "Open-circuit terminal voltage."),
                _RESISTANCE("series_resistance_ohm", 0.1, "Series source resistance."),
            ),
            presets=(
                ArchetypePreset("logic_3v3", "3.3 V / 100 mOhm", {"open_circuit_voltage_v": 3.3, "series_resistance_ohm": 0.1}),
                ArchetypePreset("bench_5v", "5 V / 100 mOhm", {"open_circuit_voltage_v": 5.0, "series_resistance_ohm": 0.1}),
                ArchetypePreset("automotive_12v", "12 V / 50 mOhm", {"open_circuit_voltage_v": 12.0, "series_resistance_ohm": 0.05}),
            ),
            tags=("dc", "equivalent", "linear", "source", "thevenin"),
            required_capabilities=("native.linear_mna.resistor", "native.linear_mna.voltage_source"),
            elaborator="thevenin_source",
            limitations=("No transient impedance, current limit, battery state, noise, temperature, or protection behavior.",),
            provenance=_provenance(),
        ),
        ArchetypeDescriptor(
            archetype_id="spikes.ideal:norton_source@1",
            title="Norton DC source",
            family="source.equivalent",
            summary="Constant source current with positive parallel resistance.",
            status="runnable",
            fidelity="generic_functional",
            pins=("positive", "negative"),
            parameters=(
                _CURRENT("source_current_a", 1e-3, "Current delivered internally from negative toward positive."),
                _RESISTANCE("parallel_resistance_ohm", 1e3, "Parallel source resistance."),
            ),
            presets=(
                ArchetypePreset("one_ma_one_k", "1 mA / 1 kOhm", {"source_current_a": 1e-3, "parallel_resistance_ohm": 1e3}),
                ArchetypePreset("ten_ma_one_k", "10 mA / 1 kOhm", {"source_current_a": 1e-2, "parallel_resistance_ohm": 1e3}),
            ),
            tags=("current", "dc", "equivalent", "linear", "norton", "source"),
            required_capabilities=("native.linear_mna.current_source", "native.linear_mna.resistor"),
            elaborator="norton_source",
            limitations=("No compliance, current limit, transient impedance, noise, temperature, or protection behavior.",),
            provenance=_provenance(),
        ),
    )

    unavailable_specs = (
        (
            "spikes.generic:diode@1", "Generic PN diode", "semiconductor.diode", ("anode", "cathode"),
            ("diode", "nonlinear", "pn"),
            ("native.nonlinear_dae", "model.diode.charge_conserving", "physics.electrothermal"),
            "No qualified nonlinear, charge-storage, breakdown, and electrothermal diode kernel is implemented.",
        ),
        (
            "spikes.generic:opamp.voltage_feedback@1", "Generic voltage-feedback op-amp", "analog.opamp",
            ("noninverting", "inverting", "positive_supply", "negative_supply", "output"),
            ("amplifier", "analog", "opamp"),
            ("native.nonlinear_dae", "model.opamp.dynamic", "event.saturation"),
            "A controlled source is not an honest op-amp model; rail limits, saturation, bandwidth, slew, input/output limits, and stability are not implemented.",
        ),
        (
            "spikes.generic:bjt.npn@1", "Generic NPN BJT", "semiconductor.bjt", ("collector", "base", "emitter"),
            ("bjt", "npn", "semiconductor"),
            ("native.nonlinear_dae", "model.bjt.charge_conserving", "physics.electrothermal"),
            "No qualified charge-conserving, high-injection, breakdown, and electrothermal NPN BJT kernel is implemented.",
        ),
        (
            "spikes.generic:bjt.pnp@1", "Generic PNP BJT", "semiconductor.bjt", ("collector", "base", "emitter"),
            ("bjt", "pnp", "semiconductor"),
            ("native.nonlinear_dae", "model.bjt.charge_conserving", "physics.electrothermal"),
            "No qualified charge-conserving, high-injection, breakdown, and electrothermal PNP BJT kernel is implemented.",
        ),
        (
            "spikes.generic:mosfet.nmos@1", "Generic N-channel MOSFET", "semiconductor.mosfet", ("drain", "gate", "source", "bulk"),
            ("mosfet", "nmos", "semiconductor"),
            ("native.nonlinear_dae", "model.mosfet.charge_conserving", "physics.electrothermal"),
            "No qualified charge-conserving capacitance, body-diode, breakdown, and electrothermal NMOS kernel is implemented.",
        ),
        (
            "spikes.generic:mosfet.pmos@1", "Generic P-channel MOSFET", "semiconductor.mosfet", ("drain", "gate", "source", "bulk"),
            ("mosfet", "pmos", "semiconductor"),
            ("native.nonlinear_dae", "model.mosfet.charge_conserving", "physics.electrothermal"),
            "No qualified charge-conserving capacitance, body-diode, breakdown, and electrothermal PMOS kernel is implemented.",
        ),
        (
            "spikes.power:gan.hemt@1", "Generic enhancement-mode GaN HEMT", "semiconductor.wbg", ("drain", "gate", "source"),
            ("gan", "hemt", "power", "wbg"),
            ("native.nonlinear_dae", "model.gan.dynamic", "physics.electrothermal"),
            "No qualified trapping, dynamic resistance, charge, reverse-conduction, breakdown, and electrothermal GaN kernel is implemented.",
        ),
        (
            "spikes.power:sic.mosfet@1", "Generic SiC MOSFET", "semiconductor.wbg", ("drain", "gate", "source", "kelvin_source"),
            ("mosfet", "power", "sic", "wbg"),
            ("native.nonlinear_dae", "model.sic.dynamic", "physics.electrothermal"),
            "No qualified charge, body-diode, reverse-recovery, breakdown, short-circuit, and electrothermal SiC kernel is implemented.",
        ),
    )
    unavailable = tuple(
        ArchetypeDescriptor(
            archetype_id=archetype_id,
            title=title,
            family=family,
            summary=f"Planned physics-rich {title.lower()} archetype.",
            status="unavailable",
            fidelity="compact",
            pins=pins,
            tags=tags,
            required_capabilities=capabilities,
            unavailable_reason=reason,
            limitations=("Descriptor-only: it cannot elaborate or simulate in this release.",),
            provenance=_provenance("unavailable"),
        )
        for archetype_id, title, family, pins, tags, capabilities, reason in unavailable_specs
    )
    return runnable + unavailable


class ArchetypeLibrary:
    """Read-only registry with deterministic discovery and elaboration."""

    def __init__(self, descriptors: Iterable[ArchetypeDescriptor]) -> None:
        ordered = tuple(sorted(descriptors, key=lambda item: item.archetype_id))
        identifiers = [item.archetype_id for item in ordered]
        if len(identifiers) != len(set(identifiers)):
            raise ArchetypeLibraryError("Archetype IDs must be unique.")
        self._items = ordered
        self._by_id = {item.archetype_id: item for item in ordered}

    def catalog(self) -> dict[str, Any]:
        runnable = sum(item.available for item in self._items)
        return {
            "contract": LIBRARY_CONTRACT,
            "version": LIBRARY_VERSION,
            "status": "experimental",
            "counts": {"total": len(self._items), "runnable": runnable, "unavailable": len(self._items) - runnable},
            "archetypes": [item.to_summary_dict() for item in self._items],
            "provenance": _provenance(),
        }

    def inspect(self, archetype_id: str) -> ArchetypeDescriptor:
        key = str(archetype_id).strip().lower()
        try:
            return self._by_id[key]
        except KeyError as exc:
            raise ArchetypeLibraryError(f"Unknown archetype: {archetype_id}.") from exc

    def search(self, query: str = "", *, status: str = "all") -> tuple[ArchetypeDescriptor, ...]:
        normalized_status = str(status).strip().lower()
        if normalized_status not in {"all", "runnable", "unavailable"}:
            raise ArchetypeLibraryError("Search status must be all, runnable, or unavailable.")
        terms = tuple(term for term in str(query).strip().lower().split() if term)
        matches = []
        for item in self._items:
            if normalized_status != "all" and item.status != normalized_status:
                continue
            haystack = " ".join((item.archetype_id, item.title, item.family, item.summary, *item.tags)).lower()
            if all(term in haystack for term in terms):
                matches.append(item)
        return tuple(matches)

    def resolve_parameters(
        self,
        archetype_id: str,
        *,
        preset: str | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, float]:
        descriptor = self.inspect(archetype_id)
        if not descriptor.available:
            raise ArchetypeUnavailableError(
                f"{descriptor.archetype_id} is unavailable: {descriptor.unavailable_reason}"
            )
        specs = {parameter.name: parameter for parameter in descriptor.parameters}
        values = {name: spec.default for name, spec in specs.items()}
        if preset:
            presets = {item.preset_id: item for item in descriptor.presets}
            if preset not in presets:
                raise ArchetypeLibraryError(f"Unknown preset {preset!r} for {descriptor.archetype_id}.")
            values.update(presets[preset].values)
        if overrides is not None:
            if not isinstance(overrides, Mapping):
                raise ArchetypeLibraryError("Parameter overrides must be a mapping.")
            unknown = set(overrides) - set(specs)
            if unknown:
                raise ArchetypeLibraryError(f"Unknown parameter overrides: {sorted(unknown)}.")
            values.update({name: specs[name].validate(value) for name, value in overrides.items()})
        return {name: specs[name].validate(values[name]) for name in sorted(values)}

    def elaborate(
        self,
        archetype_id: str,
        instance_id: str,
        pin_bindings: Mapping[str, str],
        *,
        preset: str | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        descriptor = self.inspect(archetype_id)
        if not descriptor.available:
            raise ArchetypeUnavailableError(
                f"{descriptor.archetype_id} is unavailable: {descriptor.unavailable_reason}"
            )
        if descriptor.elaborator not in _ELABORATORS:
            raise ArchetypeLibraryError(f"Archetype {descriptor.archetype_id} has no registered elaborator.")
        if _INSTANCE_RE.fullmatch(str(instance_id)) is None:
            raise ArchetypeLibraryError("Instance ID must be a bounded ASCII identifier beginning with a letter.")
        if not isinstance(pin_bindings, Mapping):
            raise ArchetypeLibraryError("Pin bindings must be a mapping.")
        bindings = {str(pin).strip().lower(): str(node).strip() for pin, node in pin_bindings.items()}
        if set(bindings) != set(descriptor.pins):
            missing = sorted(set(descriptor.pins) - set(bindings))
            extra = sorted(set(bindings) - set(descriptor.pins))
            raise ArchetypeLibraryError(f"Pin binding mismatch; missing={missing}, extra={extra}.")
        if any(not node for node in bindings.values()):
            raise ArchetypeLibraryError("Pin binding nodes cannot be empty.")
        if any(node.lower().startswith("__spikes_") for node in bindings.values()):
            raise ArchetypeLibraryError("Nodes beginning with __spikes_ are reserved for elaborator internals.")
        parameters = self.resolve_parameters(descriptor.archetype_id, preset=preset, overrides=overrides)
        slug = re.sub(r"[^A-Za-z0-9_]", "_", str(instance_id)).upper()
        elements, internal_nodes = _elaborate_elements(descriptor.elaborator, slug, bindings, parameters)
        return {
            "contract": ELABORATION_CONTRACT,
            "status": "ready",
            "model_status": "experimental",
            "archetype": descriptor.to_summary_dict(),
            "instance_id": str(instance_id),
            "pin_bindings": dict(sorted(bindings.items())),
            "preset": preset or "",
            "parameters": parameters,
            "elements": elements,
            "internal_nodes": internal_nodes,
            "provenance": {
                **dict(descriptor.provenance),
                "archetype_id": descriptor.archetype_id,
                "elaborator": descriptor.elaborator,
                "explicit_overrides": sorted((overrides or {}).keys()),
            },
        }

    def validate(self) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        runnable = 0
        unavailable = 0
        for descriptor in self._items:
            if not descriptor.available:
                unavailable += 1
                continue
            runnable += 1
            bindings = {
                pin: "0" if pin in {"negative", "reference", "output_negative", "control_negative"} else f"test_{pin}"
                for pin in descriptor.pins
            }
            try:
                elaborated = self.elaborate(descriptor.archetype_id, "validation", bindings)
                request = {
                    "contract": NATIVE_REQUEST_CONTRACT,
                    "request_id": f"library-{runnable}",
                    "ground_node": "0",
                    "analysis": {"mode": "operating_point"},
                    "elements": elaborated["elements"],
                    "resource_limits": {"memory_limit_gb": 2.0, "linear_backend": "dense"},
                }
                validation = validate_native_mna_request(request)
                if not validation["valid"]:
                    issues.append({
                        "code": "SPIKES_LIBRARY_NATIVE_VALIDATION_FAILED",
                        "severity": "error",
                        "path": descriptor.archetype_id,
                        "message": "Nominal elaboration did not satisfy the native MNA request contract.",
                        "native_issues": validation["issues"],
                    })
            except (ArchetypeLibraryError, ValueError) as exc:
                issues.append({
                    "code": "SPIKES_LIBRARY_ELABORATION_FAILED",
                    "severity": "error",
                    "path": descriptor.archetype_id,
                    "message": str(exc),
                })
        return {
            "contract": LIBRARY_VALIDATION_CONTRACT,
            "valid": not issues,
            "counts": {"total": len(self._items), "runnable": runnable, "unavailable": unavailable, "issues": len(issues)},
            "issues": issues,
            "provenance": _provenance(),
        }


def _elaborate_elements(
    elaborator: str,
    slug: str,
    pins: Mapping[str, str],
    parameters: Mapping[str, float],
) -> tuple[list[dict[str, Any]], list[str]]:
    def resistor(identifier: str, positive: str, negative: str, value: float) -> dict[str, Any]:
        return {
            "id": identifier,
            "type": "resistor",
            "positive_node": positive,
            "negative_node": negative,
            "resistance_ohm": value,
        }

    def voltage(identifier: str, positive: str, negative: str, value: float) -> dict[str, Any]:
        return {
            "id": identifier,
            "type": "voltage_source",
            "positive_node": positive,
            "negative_node": negative,
            "dc_value": value,
        }

    def current(identifier: str, positive: str, negative: str, value: float) -> dict[str, Any]:
        return {
            "id": identifier,
            "type": "current_source",
            "positive_node": positive,
            "negative_node": negative,
            "dc_value": value,
        }

    if elaborator == "resistor":
        return [resistor(f"R_{slug}", pins["positive"], pins["negative"], parameters["resistance_ohm"])], []
    if elaborator == "dc_voltage_source":
        return [voltage(f"V_{slug}", pins["positive"], pins["negative"], parameters["voltage_v"])], []
    if elaborator == "dc_current_source":
        return [current(f"I_{slug}", pins["positive"], pins["negative"], parameters["current_a"])], []
    if elaborator == "vcvs":
        return [{
            "id": f"E_{slug}",
            "type": "vcvs",
            "positive_node": pins["output_positive"],
            "negative_node": pins["output_negative"],
            "control_positive_node": pins["control_positive"],
            "control_negative_node": pins["control_negative"],
            "gain": parameters["gain"],
        }], []
    if elaborator == "vccs":
        return [{
            "id": f"G_{slug}",
            "type": "vccs",
            "positive_node": pins["output_positive"],
            "negative_node": pins["output_negative"],
            "control_positive_node": pins["control_positive"],
            "control_negative_node": pins["control_negative"],
            "transconductance_s": parameters["transconductance_s"],
        }], []
    if elaborator == "voltage_divider":
        return [
            resistor(f"R_{slug}_TOP", pins["input"], pins["output"], parameters["top_resistance_ohm"]),
            resistor(f"R_{slug}_BOTTOM", pins["output"], pins["reference"], parameters["bottom_resistance_ohm"]),
        ], []
    if elaborator == "thevenin_source":
        internal = f"__spikes_{slug.lower()}_thevenin"
        return [
            voltage(f"V_{slug}", internal, pins["negative"], parameters["open_circuit_voltage_v"]),
            resistor(f"R_{slug}", internal, pins["positive"], parameters["series_resistance_ohm"]),
        ], [internal]
    if elaborator == "norton_source":
        return [
            current(f"I_{slug}", pins["negative"], pins["positive"], parameters["source_current_a"]),
            resistor(f"R_{slug}", pins["positive"], pins["negative"], parameters["parallel_resistance_ohm"]),
        ], []
    raise ArchetypeLibraryError(f"Unknown elaborator: {elaborator}.")


BUILTIN_LIBRARY = ArchetypeLibrary(_builtins())


__all__ = [
    "BUILTIN_LIBRARY",
    "LIBRARY_VERSION",
    "ArchetypeLibrary",
    "ArchetypeLibraryError",
    "ArchetypeUnavailableError",
]
