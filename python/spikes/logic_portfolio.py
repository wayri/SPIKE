# SPDX-License-Identifier: Apache-2.0
"""Bounded 54/74 functional logic portfolio over SPIKE's digital kernel.

The package records below are independently authored from factual manufacturer
pin/function tables.  They are not vendor timing or electrical models.  The
only executable backend is the existing four-state :class:`DigitalKernel`;
this module composes its primitives and never evaluates a second Python truth
solver.  Package power pins are declared interfaces only.
"""

from __future__ import annotations

from copy import deepcopy
import re

from .digital import DigitalKernel
from .standard_logic import package as _standard_package


CONTRACT = "spikes/logic-portfolio/v1"
BACKEND = "python.spikes.digital.DigitalKernel"
ACCESSED_ON = "2026-10-13"
LIMITATIONS = (
    "Original four-state functional model only; no voltage thresholds, drive strength, "
    "supply behavior, propagation-time qualification, setup/hold checks, metastability, "
    "package parasitics, temperature, or manufacturer model is implied. Delay is applied "
    "per composed kernel primitive in caller-defined ticks."
)


class UnsupportedLogicModelError(ValueError):
    """The descriptor is documented but cannot be bound without missing semantics."""


class _Builder:
    def __init__(self) -> None:
        self.primitives: list[dict[str, object]] = []
        self.internal: list[str] = []

    def temp(self, stem: str = "n") -> str:
        name = f"${stem}{len(self.internal) + 1}"
        self.internal.append(name)
        return name

    def gate(self, kind: str, inputs: list[str] | tuple[str, ...], output: str | None = None) -> str:
        output = output or self.temp(kind)
        self.primitives.append({"kind": kind, "inputs": list(inputs), "output": output})
        return output

    def invert(self, signal: str) -> str:
        return self.gate("not", [signal])

    def mux2(self, low: str, high: str, select: str) -> str:
        not_select = self.invert(select)
        low_term = self.gate("and", [low, not_select])
        high_term = self.gate("and", [high, select])
        return self.gate("or", [low_term, high_term])

    def mux(self, data: list[str], selects_lsb_first: list[str]) -> str:
        layer = list(data)
        for select in selects_lsb_first:
            layer = [self.mux2(layer[index], layer[index + 1], select)
                     for index in range(0, len(layer), 2)]
        if len(layer) != 1:
            raise AssertionError("multiplexer input count must be a power of two")
        return layer[0]


def _roles(pin_names: list[str], *, inputs: tuple[str, ...] = (),
           outputs: tuple[str, ...] = (), inouts: tuple[str, ...] = ()) -> dict[str, str]:
    result = {name: "power" if name in {"VCC", "GND"} else "unconnected" for name in pin_names}
    result.update({name: "input" for name in inputs})
    result.update({name: "output" for name in outputs})
    result.update({name: "inout" for name in inouts})
    return result


def _package_pins(pin_names: list[str], roles: dict[str, str]) -> list[dict[str, str]]:
    return [{"number": str(index), "name": name, "role": roles[name]}
            for index, name in enumerate(pin_names, 1)]


def _descriptor(model_id: str, function: str, device_family: str, *,
                pin_names: list[str] | None, roles: dict[str, str] | None,
                builder: _Builder | None, source_url: str,
                series_names: tuple[str, ...], package: str | None,
                support: str = "executable", model_status: str = "generic_functional_unqualified",
                unsupported_reason: str | None = None) -> dict[str, object]:
    pins = _package_pins(pin_names, roles or {}) if pin_names else []
    return {
        "contract": CONTRACT,
        "model_id": model_id,
        "function": function,
        "device_family": device_family,
        "series_names": list(series_names),
        "package": package,
        "pinout_status": "manufacturer_documented" if pin_names else "not_claimed",
        "pins": pins,
        "source": {"manufacturer": "Texas Instruments" if "ti.com" in source_url else "Nexperia",
                   "url": source_url, "accessed_on": ACCESSED_ON,
                   "scope": "function and listed package pinout only"},
        "backend": BACKEND if builder is not None else None,
        "support": support,
        "model_status": model_status,
        "internal_signals": list(builder.internal) if builder else [],
        "primitives": deepcopy(builder.primitives) if builder else [],
        "unsupported_reason": unsupported_reason,
        "electrical_circuit_coupled": False,
        "power_behavior": "declared_only" if pin_names else "not_applicable",
        "limitations": LIMITATIONS,
    }


def _gate_package(code: str) -> dict[str, object]:
    package = _standard_package(f"SN74HC{code}N")
    builder = _Builder()
    names = [pin["name"] for pin in package["pins"]]
    role_by_name = {pin["name"]: pin["role"] for pin in package["pins"]}
    pin_name_by_number = {pin["number"]: pin["name"] for pin in package["pins"]}
    for gate in package["gates"]:
        builder.gate(package["family"], [pin_name_by_number[item] for item in gate["inputs"]],
                     pin_name_by_number[gate["output"]])
    functions = {
        "00": "quad 2-input NAND", "02": "quad 2-input NOR", "04": "hex inverter",
        "08": "quad 2-input AND", "10": "triple 3-input NAND", "11": "triple 3-input AND",
        "20": "dual 4-input NAND", "21": "dual 4-input AND", "32": "quad 2-input OR",
        "86": "quad 2-input XOR",
    }
    result = _descriptor(f"HC{code}", functions[code], f"54/74HC{code}", pin_names=names,
                         roles=role_by_name, builder=builder, source_url=package["source_url"],
                         series_names=(f"SN54HC{code}", f"SN74HC{code}"),
                         package="J/N shared 14-pin functional pinout")
    # standard_logic already records the exact physical numbering; retain it.
    result["pins"] = deepcopy(package["pins"])
    return result


def _tristate(model_id: str, active_high: bool) -> dict[str, object]:
    names = ["1OE", "1A", "1Y", "2OE", "2A", "2Y", "GND",
             "3Y", "3A", "3OE", "4Y", "4A", "4OE", "VCC"]
    roles = _roles(names, inputs=("1OE", "1A", "2OE", "2A", "3A", "3OE", "4A", "4OE"),
                   outputs=("1Y", "2Y", "3Y", "4Y"))
    builder = _Builder()
    for channel in range(1, 5):
        enable = f"{channel}OE" if active_high else builder.invert(f"{channel}OE")
        builder.gate("tristate", [f"{channel}A", enable], f"{channel}Y")
    code = "126" if active_high else "125"
    return _descriptor(model_id, f"quad tri-state buffer, {'active-high' if active_high else 'active-low'} enable",
                       f"74HC{code}", pin_names=names, roles=roles, builder=builder,
                       source_url=f"https://assets.nexperia.com/documents/data-sheet/74HC_HCT{code}.pdf",
                       series_names=(f"74HC{code}",), package="SO/TSSOP-14 documented pinout")


def _decoder138() -> dict[str, object]:
    names = ["A", "B", "C", "G2A", "G2B", "G1", "Y7", "GND",
             "Y6", "Y5", "Y4", "Y3", "Y2", "Y1", "Y0", "VCC"]
    roles = _roles(names, inputs=("A", "B", "C", "G2A", "G2B", "G1"),
                   outputs=tuple(f"Y{i}" for i in range(8)))
    builder = _Builder()
    complements = [builder.invert(name) for name in ("A", "B", "C")]
    enabled = builder.gate("and", ["G1", builder.invert("G2A"), builder.invert("G2B")])
    for value in range(8):
        terms = [name if value & (1 << bit) else complements[bit]
                 for bit, name in enumerate(("A", "B", "C"))]
        selected = builder.gate("and", [enabled, *terms])
        builder.gate("not", [selected], f"Y{value}")
    return _descriptor("HC138", "3-to-8 active-low decoder", "54/74HC138", pin_names=names,
                       roles=roles, builder=builder,
                       source_url="https://www.ti.com/lit/ds/symlink/sn74hc138.pdf",
                       series_names=("SN54HC138", "SN74HC138"),
                       package="J/N shared 16-pin functional pinout")


def _decoder139() -> dict[str, object]:
    names = ["1G", "1A", "1B", "1Y0", "1Y1", "1Y2", "1Y3", "GND",
             "2Y3", "2Y2", "2Y1", "2Y0", "2B", "2A", "2G", "VCC"]
    inputs = tuple(f"{channel}{name}" for channel in (1, 2) for name in ("G", "A", "B"))
    outputs = tuple(f"{channel}Y{i}" for channel in (1, 2) for i in range(4))
    roles = _roles(names, inputs=inputs, outputs=outputs)
    builder = _Builder()
    for channel in (1, 2):
        a, b, disable = f"{channel}A", f"{channel}B", f"{channel}G"
        not_a, not_b, enabled = builder.invert(a), builder.invert(b), builder.invert(disable)
        for value in range(4):
            terms = [a if value & 1 else not_a, b if value & 2 else not_b]
            builder.gate("not", [builder.gate("and", [enabled, *terms])], f"{channel}Y{value}")
    return _descriptor("HC139", "dual 2-to-4 active-low decoder", "54/74HC139", pin_names=names,
                       roles=roles, builder=builder,
                       source_url="https://www.ti.com/lit/ds/symlink/sn74hc139.pdf",
                       series_names=("SN54HC139", "SN74HC139"),
                       package="J/N shared 16-pin functional pinout")


def _mux151() -> dict[str, object]:
    names = ["I3", "I2", "I1", "I0", "Y", "Y_N", "E", "GND",
             "S2", "S1", "S0", "I7", "I6", "I5", "I4", "VCC"]
    roles = _roles(names, inputs=tuple(f"I{i}" for i in range(8)) + ("S0", "S1", "S2", "E"),
                   outputs=("Y", "Y_N"))
    builder = _Builder()
    selected = builder.mux([f"I{i}" for i in range(8)], ["S0", "S1", "S2"])
    y = builder.gate("and", [selected, builder.invert("E")], "Y")
    builder.gate("not", [y], "Y_N")
    return _descriptor("HC151", "8-to-1 multiplexer with complementary outputs", "74HC151",
                       pin_names=names, roles=roles, builder=builder,
                       source_url="https://assets.nexperia.com/documents/data-sheet/74HC_HCT151.pdf",
                       series_names=("74HC151",), package="SO/TSSOP-16 documented pinout")


def _mux153() -> dict[str, object]:
    names = ["1G", "S1", "1I3", "1I2", "1I1", "1I0", "1Y", "GND",
             "2Y", "2I0", "2I1", "2I2", "2I3", "S0", "2G", "VCC"]
    inputs = ("1G", "2G", "S0", "S1") + tuple(f"{channel}I{i}" for channel in (1, 2) for i in range(4))
    roles = _roles(names, inputs=inputs, outputs=("1Y", "2Y"))
    builder = _Builder()
    for channel in (1, 2):
        selected = builder.mux([f"{channel}I{i}" for i in range(4)], ["S0", "S1"])
        builder.gate("and", [selected, builder.invert(f"{channel}G")], f"{channel}Y")
    return _descriptor("HC153", "dual 4-to-1 multiplexer", "54/74HC153", pin_names=names,
                       roles=roles, builder=builder,
                       source_url="https://www.ti.com/lit/ds/symlink/sn74hc153.pdf",
                       series_names=("SN54HC153", "SN74HC153"),
                       package="J/N shared 16-pin functional pinout")


def _mux157() -> dict[str, object]:
    names = ["S", "1A", "1B", "1Y", "2A", "2B", "2Y", "GND",
             "3Y", "3B", "3A", "4Y", "4B", "4A", "G", "VCC"]
    inputs = ("S", "G") + tuple(f"{channel}{side}" for channel in range(1, 5) for side in ("A", "B"))
    roles = _roles(names, inputs=inputs, outputs=tuple(f"{channel}Y" for channel in range(1, 5)))
    builder = _Builder()
    enabled = builder.invert("G")
    for channel in range(1, 5):
        selected = builder.mux2(f"{channel}A", f"{channel}B", "S")
        builder.gate("and", [selected, enabled], f"{channel}Y")
    return _descriptor("HC157", "quad 2-to-1 multiplexer with common strobe", "54/74HC157",
                       pin_names=names, roles=roles, builder=builder,
                       source_url="https://www.ti.com/lit/ds/symlink/sn74hc157.pdf",
                       series_names=("SN54HC157", "SN74HC157"),
                       package="J/N shared 16-pin functional pinout")


def _adder283() -> dict[str, object]:
    names = ["S2", "B2", "A2", "S1", "A1", "B1", "CIN", "GND",
             "COUT", "S4", "B4", "A4", "S3", "A3", "B3", "VCC"]
    inputs = tuple(f"A{i}" for i in range(1, 5)) + tuple(f"B{i}" for i in range(1, 5)) + ("CIN",)
    roles = _roles(names, inputs=inputs, outputs=tuple(f"S{i}" for i in range(1, 5)) + ("COUT",))
    builder = _Builder()
    carry = "CIN"
    for bit in range(1, 5):
        a, b = f"A{bit}", f"B{bit}"
        axb = builder.gate("xor", [a, b])
        builder.gate("xor", [axb, carry], f"S{bit}")
        ab = builder.gate("and", [a, b])
        ac = builder.gate("and", [a, carry])
        bc = builder.gate("and", [b, carry])
        carry = builder.gate("or", [ab, ac, bc], "COUT" if bit == 4 else None)
    return _descriptor("HC283", "4-bit binary full adder", "CD74HC283", pin_names=names,
                       roles=roles, builder=builder,
                       source_url="https://www.ti.com/lit/ds/symlink/cd74hc283.pdf",
                       series_names=("CD74HC283",), package="D/N 16-pin documented pinout")


def _comparator688() -> dict[str, object]:
    names = ["G", "P0", "Q0", "P1", "Q1", "P2", "Q2", "P3", "Q3", "GND",
             "Q4", "P4", "Q5", "P5", "Q6", "P6", "Q7", "P7", "P_EQ_Q_N", "VCC"]
    inputs = ("G",) + tuple(f"P{i}" for i in range(8)) + tuple(f"Q{i}" for i in range(8))
    roles = _roles(names, inputs=inputs, outputs=("P_EQ_Q_N",))
    builder = _Builder()
    equal_bits = [builder.invert(builder.gate("xor", [f"P{i}", f"Q{i}"])) for i in range(8)]
    enabled_equal = builder.gate("and", [builder.invert("G"), *equal_bits])
    builder.gate("not", [enabled_equal], "P_EQ_Q_N")
    return _descriptor("HC688", "8-bit identity comparator with active-low output", "54/74HC688",
                       pin_names=names, roles=roles, builder=builder,
                       source_url="https://www.ti.com/lit/ds/symlink/sn74hc688.pdf",
                       series_names=("SN54HC688", "SN74HC688"),
                       package="J/N shared 20-pin functional pinout")


def _transceiver245() -> dict[str, object]:
    names = ["DIR", *[f"A{i}" for i in range(1, 9)], "GND",
             *[f"B{i}" for i in range(8, 0, -1)], "OE", "VCC"]
    buses = tuple(f"A{i}" for i in range(1, 9)) + tuple(f"B{i}" for i in range(1, 9))
    roles = _roles(names, inputs=("DIR", "OE"), inouts=buses)
    builder = _Builder()
    enabled = builder.invert("OE")
    a_to_b = builder.gate("and", [enabled, "DIR"])
    b_to_a = builder.gate("and", [enabled, builder.invert("DIR")])
    for bit in range(1, 9):
        builder.gate("tristate", [f"A{bit}", a_to_b], f"B{bit}")
        builder.gate("tristate", [f"B{bit}", b_to_a], f"A{bit}")
    return _descriptor("HC245", "octal bidirectional tri-state bus transceiver", "54/74HC245",
                       pin_names=names, roles=roles, builder=builder,
                       source_url="https://www.ti.com/lit/ds/symlink/sn74hc245.pdf",
                       series_names=("SN54HC245", "SN74HC245"),
                       package="J/N shared 20-pin functional pinout")


def _generic_sequential() -> list[dict[str, object]]:
    models: list[dict[str, object]] = []

    builder = _Builder()
    builder.gate("dff", ["D", "CLK"], "Q")
    names = ["D", "CLK", "Q", "GND", "VCC"]
    models.append(_descriptor("CORE_DFF", "positive-edge D flip-flop core", "generic core",
                              pin_names=names, roles=_roles(names, inputs=("D", "CLK"), outputs=("Q",)),
                              builder=builder, source_url="https://www.ti.com/lit/ds/symlink/sn74hc74.pdf",
                              series_names=(), package="logical interface; not a physical package"))

    builder = _Builder()
    previous = "SER"
    for bit in range(8):
        builder.gate("dff", [previous, "CLK"], f"Q{bit}")
        previous = f"Q{bit}"
    names = ["SER", "CLK", *[f"Q{i}" for i in range(8)], "GND", "VCC"]
    models.append(_descriptor("CORE_SIPO8", "8-bit serial-in parallel-out shift core", "generic core",
                              pin_names=names, roles=_roles(names, inputs=("SER", "CLK"),
                                                            outputs=tuple(f"Q{i}" for i in range(8))),
                              builder=builder,
                              source_url="https://www.nexperia.com/products/analog-logic-ics/logic/flip-flops-latches-registers-counters-dividers/shift-registers/serie/74hc164-74hct164",
                              series_names=(), package="logical interface; not a physical package"))

    builder = _Builder()
    lower_all_one: str | None = None
    for bit in range(4):
        q = f"Q{bit}"
        toggle = q if bit == 0 else builder.gate("xor", [q, lower_all_one])
        count_next = builder.mux2(q, toggle if bit else builder.invert(q), "EN")
        next_value = builder.mux2(count_next, f"D{bit}", "LOAD")
        builder.gate("dff", [next_value, "CLK"], q)
        lower_all_one = q if lower_all_one is None else builder.gate("and", [lower_all_one, q])
    names = ["EN", "LOAD", "CLK", *[f"D{i}" for i in range(4)],
             *[f"Q{i}" for i in range(4)], "GND", "VCC"]
    models.append(_descriptor("CORE_COUNTER4_SYNC", "4-bit synchronous loadable up-counter core",
                              "generic core", pin_names=names,
                              roles=_roles(names, inputs=("EN", "LOAD", "CLK", "D0", "D1", "D2", "D3"),
                                           outputs=("Q0", "Q1", "Q2", "Q3")), builder=builder,
                              source_url="https://www.nexperia.com/products/analog-logic-ics/logic/flip-flops-latches-registers-counters-dividers",
                              series_names=(), package="logical interface; not a physical package"))
    for item in models:
        item["pinout_status"] = "logical_interface_only"
        item["source"]["scope"] = "functional precedent only; no package or named-part equivalence"
    return models


def _review_only() -> list[dict[str, object]]:
    entries = (
        ("HC74_FULL", "dual D flip-flop with asynchronous preset and clear", "54/74HC74",
         ("SN54HC74", "SN74HC74"),
         "https://www.ti.com/lit/ds/symlink/sn74hc74.pdf",
         "The kernel DFF has no asynchronous preset/clear or complemented-output primitive."),
        ("HC161_FULL", "presettable synchronous 4-bit counter", "54/74HC161",
         ("SN54HC161", "SN74HC161"),
         "https://www.ti.com/lit/ds/symlink/sn74hc161.pdf",
         "Exact clear/load/enable/ripple-carry semantics are not represented by a reviewed package netlist."),
        ("HC164_FULL", "8-bit serial-in parallel-out register with asynchronous clear", "74HC164",
         ("74HC164",),
         "https://assets.nexperia.com/documents/data-sheet/74HC_HCT164.pdf",
         "The executable shift core intentionally omits the part's asynchronous master reset."),
        ("HC373_FULL", "octal transparent latch with tri-state outputs", "54/74HC373",
         ("SN54HC373", "SN74HC373"),
         "https://www.ti.com/lit/ds/symlink/sn74hc373.pdf",
         "The kernel has no transparent-latch primitive."),
        ("HC595_FULL", "8-bit shift and storage registers with tri-state outputs", "54/74HC595",
         ("SN54HC595", "SN74HC595"),
         "https://www.ti.com/lit/ds/symlink/sn74hc595.pdf",
         "The kernel cannot reproduce the part's direct asynchronous shift-register clear."),
    )
    return [_descriptor(model_id, function, family, pin_names=None, roles=None, builder=None,
                        source_url=url, series_names=series_names, package=None,
                        support="review_only", model_status="unsupported_exact_function",
                        unsupported_reason=reason)
            for model_id, function, family, series_names, url, reason in entries]


def _build_catalog() -> list[dict[str, object]]:
    models = [_gate_package(code) for code in ("00", "02", "04", "08", "10", "11", "20", "21", "32", "86")]
    models.extend([
        _tristate("HC125", False), _tristate("HC126", True), _decoder138(), _decoder139(),
        _mux151(), _mux153(), _mux157(), _adder283(), _comparator688(), _transceiver245(),
    ])
    models.extend(_generic_sequential())
    models.extend(_review_only())
    return models


_CATALOG = _build_catalog()
_BY_ID = {item["model_id"]: item for item in _CATALOG}


def catalog(*, include_review_only: bool = True) -> list[dict[str, object]]:
    """Return isolated descriptors; family records are not orderable-part claims."""
    items = _CATALOG if include_review_only else [item for item in _CATALOG if item["support"] == "executable"]
    return deepcopy(items)


def library_model(model_id: str) -> dict[str, object]:
    """Return one canonical descriptor. Random aliases and inferred suffixes are rejected."""
    key = str(model_id).strip().upper()
    if key not in _BY_ID:
        raise ValueError(f"Unknown logic model {model_id!r}; use a canonical model_id from catalog().")
    return deepcopy(_BY_ID[key])


def coverage_summary() -> dict[str, int]:
    exact = [item for item in _CATALOG
             if item["support"] == "executable" and item["device_family"] != "generic core"]
    generic = [item for item in _CATALOG if item["device_family"] == "generic core"]
    return {
        "executable_distinct_device_families": len(exact),
        "executable_generic_cores": len(generic),
        "review_only_device_families": sum(item["support"] == "review_only" for item in _CATALOG),
        "documented_54_family_names": sum(any(str(name).startswith("SN54") for name in item["series_names"])
                                           for item in exact),
        "documented_74_family_names": sum(any("74" in str(name) for name in item["series_names"])
                                           for item in exact),
        "package_or_orderable_variants": 0,
    }


def bind(kernel: DigitalKernel, model_id: str, instance: str, mapping: dict[str, str], *,
         delay_ticks: int) -> dict[str, object]:
    """Compile a descriptor into existing DigitalKernel primitives.

    ``mapping`` uses every descriptor pin-number string exactly once.  Generic
    core descriptors use stable logical-interface positions, not physical IC
    claims.  Preflight completes before any signal or primitive is added.
    """
    if not isinstance(kernel, DigitalKernel):
        raise ValueError("A DigitalKernel is required")
    if not isinstance(instance, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,80}", instance):
        raise ValueError("Invalid instance identifier")
    if type(delay_ticks) is not int or not 0 <= delay_ticks <= 2**63 - 1:
        raise ValueError("delay_ticks must be an explicit nonnegative integer")
    descriptor = library_model(model_id)
    if descriptor["support"] != "executable":
        raise UnsupportedLogicModelError(str(descriptor["unsupported_reason"]))
    expected = {pin["number"] for pin in descriptor["pins"]}
    if not isinstance(mapping, dict) or set(mapping) != expected:
        raise ValueError("Map every descriptor pin exactly once using string pin numbers")
    current = kernel.model()
    signals = {signal["name"] for signal in current["signals"]}
    if any(not isinstance(signal, str) or signal not in signals for signal in mapping.values()):
        raise ValueError("Pin mapping refers to a missing digital signal")
    names_to_signals = {pin["name"]: mapping[pin["number"]] for pin in descriptor["pins"]}
    internal_map = {name: f"{instance}.{name[1:]}" for name in descriptor["internal_signals"]}
    if signals.intersection(internal_map.values()):
        raise ValueError("Digital instance internal signal already exists")
    primitive_ids = [f"{instance}.p{index}" for index in range(1, len(descriptor["primitives"]) + 1)]
    occupied = {primitive["id"] for primitive in current["primitives"]}
    if occupied.intersection(primitive_ids):
        raise ValueError("Digital instance already exists")
    endpoints = {**names_to_signals, **internal_map}
    allowed_kinds = {"buf": (1, 1), "not": (1, 1), "and": (2, 64), "or": (2, 64),
                     "xor": (2, 64), "nand": (2, 64), "nor": (2, 64),
                     "tristate": (2, 2), "dff": (2, 2)}
    for primitive in descriptor["primitives"]:
        kind = str(primitive["kind"])
        inputs = list(primitive["inputs"])
        low, high = allowed_kinds[kind]
        if not low <= len(inputs) <= high or any(name not in endpoints for name in [*inputs, primitive["output"]]):
            raise ValueError("Descriptor failed internal primitive preflight")
    for signal in internal_map.values():
        kernel.add_signal(signal)
    for primitive_id, primitive in zip(primitive_ids, descriptor["primitives"]):
        kernel.add_primitive(primitive_id, str(primitive["kind"]),
                             [endpoints[name] for name in primitive["inputs"]],
                             endpoints[primitive["output"]], delay_ticks=delay_ticks)
    return {**descriptor, "instance": instance, "mapping": deepcopy(mapping),
            "delay_ticks": delay_ticks}


__all__ = ["BACKEND", "CONTRACT", "UnsupportedLogicModelError", "bind", "catalog",
           "coverage_summary", "library_model"]
