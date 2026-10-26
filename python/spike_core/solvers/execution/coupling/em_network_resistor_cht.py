# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Explicit AC circuit resistor heat -> retained solid volumes -> creeping CHT.

An experimental in-process composition, not an EM-body heating model. Every
port resistor is explicitly located in solid cells or outside the domain.
The original AC and CHT owners retain all their acceptance gates.
"""
from __future__ import annotations

import json
import math

from ...thermal_fluid.flow.cfd_tetra_cht import _phases, solve_cfd_tetra_cht
from ...thermal_fluid.flow.cfd_tetra_mesh import _admit_with_reuse
from .em_network_ac import solve_em_network_ac
from ....multiboard_identity import canonical_json_digest

REQUEST_CONTRACT = "spike/em-network-resistor-cht-request/v1"
RESULT_CONTRACT = "spike/em-network-resistor-cht-result/v1"
_FIELDS = {"contract", "ac_request", "cht_request", "sample_index", "resistor_cell_weights"}
_REQUEST_BYTES = 8 * 1024**2
_RESULT_BYTES = 16 * 1024**2


def _require(condition, message):
    if not condition:
        raise ValueError("EM_NETWORK_CHT: " + message)


def _poll(cancel_check):
    _require(cancel_check is None or not cancel_check(), "CANCELLED")


def _snapshot(request, cancel_check=None):
    # Bound traversal and individual tokens before the JSON encoder allocates
    # their escaped representation. This is admission, not a resident-RAM cap.
    pending, nodes, characters = [(request, 0)], 0, 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        _require(nodes <= 1_000_000 and depth <= 64, "JSON structure exceeds admission budget")
        if nodes % 1024 == 0:
            _poll(cancel_check)
        if type(value) is dict:
            _require(len(value) <= 1_000_000 and all(type(key) is str for key in value),
                     "Plain string-key JSON objects required")
            _require(nodes + len(pending) + 2*len(value) <= 1_000_000,
                     "JSON structure exceeds admission budget")
            pending.extend((item, depth+1) for pair in value.items() for item in pair)
        elif type(value) is list:
            _require(nodes + len(pending) + len(value) <= 1_000_000,
                     "JSON array exceeds admission budget")
            pending.extend((item, depth+1) for item in value)
        elif type(value) is str:
            characters += len(value)
            _require(characters <= _REQUEST_BYTES, "JSON strings exceed admission budget")
        elif type(value) is int:
            _require(value.bit_length() <= 1024, "JSON integer exceeds admission budget")
        else:
            _require(value is None or type(value) is bool
                     or (type(value) is float and math.isfinite(value)), "Finite plain JSON required")
    parts, size = [], 0
    for part in json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False).iterencode(request):
        size += len(part.encode("utf-8"))
        _require(size <= _REQUEST_BYTES, "Request exceeds 8 MiB")
        parts.append(part)
    result = json.loads("".join(parts))
    _require(isinstance(result, dict) and set(result) == _FIELDS
             and result["contract"] == REQUEST_CONTRACT, "Invalid exact request fields")
    return result


def _mapping(raw, ports, fluid):
    _require(isinstance(raw, dict) and set(raw) == set(ports),
             "Every port resistor needs an explicit destination or null outside")
    mapped = {}
    for port, values in raw.items():
        if values is None:
            mapped[port] = None
            continue
        _require(isinstance(values, dict) and 0 < len(values) <= len(fluid),
                 "Cell weights must be a nonempty bounded object")
        entries = []
        for key, weight in values.items():
            _require(isinstance(key, str) and key.isascii() and key.isdecimal()
                     and len(key) <= 4 and str(int(key)) == key and int(key) < len(fluid),
                     "Cell keys must be canonical retained zero-based indices")
            index = int(key)
            _require(not fluid[index], "Resistor heat must map to explicitly marked solid cells")
            _require(type(weight) in (int, float) and 0 <= weight <= 1,
                     "Cell fractions must be finite and nonnegative")
            entries.append((index, float(weight)))
        _require(abs(math.fsum(weight for _, weight in entries)-1.) <= 1e-12,
                 "Cell fractions must sum to one; no renormalization")
        mapped[port] = entries
    return mapped


def _conserved(actual, expected, label):
    _require(math.isfinite(actual) and math.isfinite(expected)
             and (actual == expected if expected == 0. else abs(actual-expected) <= 1e-10*abs(expected)),
             label + " does not conserve circuit watts")


def run_em_network_resistor_cht(request, *, cancel_check=None):
    """Select one exact AC sample; deposit only R*|I_rms|² on explicit solids.

    Mapping keys index the unchanged retained mesh cell array. Null places the
    corresponding resistor outside. Initial volumetric sources must all be
    zero, preventing double counting. This does not iterate electrical R(T).
    """
    _require(cancel_check is None or callable(cancel_check), "Cancellation check must be callable")
    _poll(cancel_check)
    raw = _snapshot(request, cancel_check)
    _poll(cancel_check)
    cht = raw["cht_request"]
    _require(isinstance(cht, dict) and "mesh" in cht and isinstance(cht.get("energy"), dict),
             "Explicit retained CHT request required")
    geometry, reuse = _admit_with_reuse(cht["mesh"], cancel_check)
    volumes = geometry["cell_volumes"]
    fluid = _phases(cht["energy"], len(volumes))
    sources = cht["energy"]["source_w_m3"]
    _require(isinstance(sources, list) and len(sources) == len(volumes)
             and all(type(value) in (int, float) and value == 0. for value in sources),
             "Pre-existing volumetric sources must be exactly zero; prevent double counting")
    ac_request = raw["ac_request"]
    _require(isinstance(ac_request, dict) and isinstance(ac_request.get("source"), dict),
             "Explicit sampled AC source required")
    source = ac_request["source"]
    ports, frequencies = source.get("port_names"), source.get("frequencies_hz")
    _require(isinstance(ports, list) and 1 <= len(ports) <= 16
             and all(isinstance(port, str) and port for port in ports)
             and len(set(ports)) == len(ports), "Unique ordered AC port names required")
    index = raw["sample_index"]
    _require(isinstance(frequencies, list) and type(index) is int and 0 <= index < len(frequencies),
             "Select one explicit AC frequency index")
    mapping = _mapping(raw["resistor_cell_weights"], ports, fluid)
    _poll(cancel_check)
    ac = solve_em_network_ac(ac_request, cancel_check=cancel_check)
    powers = ac["samples"][index]["series_resistor_power_w"]
    _require(len(powers) == len(ports) and all(math.isfinite(p) and p >= 0. for p in powers),
             "Invalid circuit resistor powers")
    contributions = [[] for _ in volumes]
    outside = []
    for port, power in zip(ports, powers):
        if mapping[port] is None:
            outside.append(power)
        else:
            for cell, weight in mapping[port]:
                contributions[cell].append(power*weight)
    cell_power = [math.fsum(values) for values in contributions]
    deposited, exterior, total = math.fsum(cell_power), math.fsum(outside), math.fsum(powers)
    _conserved(math.fsum((deposited, exterior)), total, "Mapped plus outside heat")
    density = [power/float(volume) for power, volume in zip(cell_power, volumes)]
    _require(all(math.isfinite(value) for value in density), "Unrepresentable volumetric heat density")
    _conserved(math.fsum(q*float(v) for q, v in zip(density, volumes)), deposited,
               "Volume-integrated heat")
    generated = {**cht, "energy": {**cht["energy"], "source_w_m3": density}}
    _poll(cancel_check)
    coupled = solve_cfd_tetra_cht(generated, cancel_check=cancel_check, _mesh_reuse=reuse)
    _require(coupled.get("status") != "cancelled", "CANCELLED")
    _require(coupled.get("status") == "completed", "CHT stage did not complete: " + str(coupled.get("issues", [])))
    _conserved(coupled["diagnostics"]["energy"]["generated_heat_w"], deposited, "CHT source")
    result = {
        "contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
        "input_digest_sha256": canonical_json_digest(raw),
        "mesh_digest_sha256": canonical_json_digest(cht["mesh"]),
        "heat_mapping": "explicit_solid_cell_fractions_no_geometry_inference",
        "frequency_hz": frequencies[index], "cell_power_w": cell_power,
        "deposited_series_resistor_power_w": deposited,
        "outside_series_resistor_power_w": exterior,
        "unclassified_em_network_power_w": ac["samples"][index]["unclassified_network_power_w"],
        "ac": ac, "cht": coupled,
        "limitations": [
            "One exact supplied AC case; frequencies are not summed and broadband causality is not established.",
            "Only external series-resistor RMS loss heats explicitly mapped solids; no EM-body/radiation conversion.",
            "Steady one-way constant-property creeping flow and perfect thermal contact; no R(T) feedback.",
            "No live SPICE, inertia, turbulence, buoyancy, transient or production qualification.",
        ],
    }
    _require(len(json.dumps(result, allow_nan=False).encode("utf-8")) <= _RESULT_BYTES,
             "Result exceeds 16 MiB")
    _poll(cancel_check)
    return result
