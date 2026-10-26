# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Explicit circuit-series-resistor heat from sampled EM-network AC, not EM-body heat."""
from copy import deepcopy
import json
import math

from ...thermal_fluid.heat.assembly_tetra_thermal import run_assembly_tetra_thermal
from ...thermal_fluid.heat.assembly_tetra_thermal_validation import validate_request
from .em_network_ac import _digest, solve_em_network_ac

REQUEST_CONTRACT = "spike/em-network-resistor-thermal-request/v1"


def run_em_network_resistor_thermal(request, *, cancel_check=None):
    """A null per-port map explicitly locates its series resistor outside the mesh.

    Non-null maps distribute its known R*I_rms² using supplied cell fractions.
    Never deposits the EM network's unclassified/radiated power as heat.
    """
    encoded = json.dumps(request, allow_nan=False)
    if len(encoded.encode()) > 8*1024**2:
        raise ValueError("EM_NETWORK_THERMAL: Request exceeds 8 MiB")
    raw = json.loads(encoded)
    if (not isinstance(raw, dict) or set(raw) != {"contract", "ac_request", "thermal_request", "sample_index", "resistor_cell_weights"}
            or raw["contract"] != REQUEST_CONTRACT):
        raise ValueError("EM_NETWORK_THERMAL: Invalid exact request fields")
    thermal, index = raw["thermal_request"], raw["sample_index"]
    if not isinstance(thermal, dict) or thermal.get("heat_sources_w_m3", {}):
        raise ValueError("EM_NETWORK_THERMAL: Pre-existing heat is unsupported; prevent double counting")
    data = validate_request(thermal)
    cells = thermal["mesh"]["cells"]
    volumes = {cell["id"]: volume for cell, (volume, _) in zip(cells, data["geometry"])}
    source = raw["ac_request"].get("source", {})
    ports, frequencies = source.get("port_names", []), source.get("frequencies_hz", [])
    weights = raw["resistor_cell_weights"]
    if type(index) is not int or not 0 <= index < len(frequencies) or not isinstance(weights, dict) or set(weights) != set(ports):
        raise ValueError("EM_NETWORK_THERMAL: Exact sample and every port heat destination required")
    for values in weights.values():
        if values is None:
            continue
        if (not isinstance(values, dict) or not values or set(values)-set(volumes) or any(
                type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values.values())
                or abs(math.fsum(values.values())-1) > 1e-12):
            raise ValueError("EM_NETWORK_THERMAL: Explicit nonnegative cell weights must sum to one; no renormalization")
    ac = solve_em_network_ac(raw["ac_request"], cancel_check=cancel_check)
    powers = ac["samples"][index]["series_resistor_power_w"]
    cell_power, outside = {cell_id: 0. for cell_id in volumes}, 0.
    for port, power in zip(ports, powers):
        if weights[port] is None:
            outside += power
        else:
            for cell_id, weight in weights[port].items():
                cell_power[cell_id] += power*weight
    deposited, total = math.fsum(cell_power.values()), math.fsum(powers)
    if abs(deposited+outside-total) > 1e-10*max(total, 1e-300):
        raise ValueError("EM_NETWORK_THERMAL: Circuit heat allocation does not conserve power")
    generated = {**deepcopy(thermal), "heat_sources_w_m3": {c: p/volumes[c] for c, p in cell_power.items()}}
    if cancel_check and cancel_check():
        raise ValueError("EM_NETWORK_THERMAL: CANCELLED")
    heat = run_assembly_tetra_thermal(generated)
    if cancel_check and cancel_check():
        raise ValueError("EM_NETWORK_THERMAL: CANCELLED")
    if abs(heat["heat_balance"]["source_w"]-deposited) > 1e-10*max(deposited, 1e-300):
        raise ValueError("EM_NETWORK_THERMAL: Thermal source differs from mapped resistor loss")
    result = {"contract": "spike/em-network-resistor-thermal-result/v1", "model_status": "experimental",
        "production_qualified": False, "input_digest": _digest(raw), "mesh_digest": _digest(thermal["mesh"]),
        "ac": ac, "thermal": heat, "frequency_hz": frequencies[index], "cell_power_w": cell_power,
        "deposited_series_resistor_power_w": deposited, "outside_series_resistor_power_w": outside,
        "unclassified_em_network_power_w": ac["samples"][index]["unclassified_network_power_w"],
        "heat_mapping": "explicit_caller_cell_weights_not_geometry_extraction",
        "limitations": ["Circuit series-resistor heat only; no EM-body, radiation, reactive power or surface-loss conversion",
                        "Single selected operating case; different frequencies are not summed",
                        "Steady one-way temperature; no SPICE execution or temperature feedback"]}
    if len(json.dumps(result, allow_nan=False).encode()) > 16*1024**2:
        raise ValueError("EM_NETWORK_THERMAL: Result exceeds 16 MiB")
    return result
