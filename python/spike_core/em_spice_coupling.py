# SPDX-License-Identifier: Apache-2.0
"""Live, bounded linear AC/EM coupling through actual owned SPICE execution.

The native engine currently has no AC route. This adapter implements exact
frequency-domain real-block lowering to its operating-point controlled-source
solver. It does not claim native AC, nonlinear small signal or transient EM.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .em_network_ac import WAVE_CONVENTION, _digest, _pair, _pairs
from .em_spice_coupling_circuit import (
    admit_circuit, admittance, assemble, incidence, lower_real_block, require,
)
from .sparameter_sampling import REQUEST_CONTRACT as SAMPLING_CONTRACT, resample_sparameter_network
from .spikes_runtime import owned_library_path, run_netlist

REQUEST_CONTRACT = "spike/em-spice-coupling-request/v1"
RESULT_CONTRACT = "spike/em-spice-coupling-result/v1"
METHOD = "frequency_domain_real_block_owned_spice_operating_point"
TOLERANCE = 1e-10


def _relative_gate(error, scale, label):
    error, scale = np.asarray(error), np.maximum(scale, np.finfo(float).tiny)
    require(np.all(np.isfinite(error)) and np.all(np.isfinite(scale)), "Nonfinite " + label)
    relative = error / scale
    require(np.all(relative <= TOLERANCE), label + " residual failed")
    return float(np.max(relative, initial=0))


def _execute(netlist, real, vector, poll, library):
    poll()
    digest = hashlib.sha256(netlist.encode()).hexdigest()
    raw = run_netlist({"netlist": netlist, "probes": []})
    poll()
    require(isinstance(raw, dict) and raw.get("contract") == "spikes/circuit-result/v1"
            and raw.get("status") == "completed" and raw.get("model_status") == "experimental",
            "Owned SPICE engine did not complete the lowered circuit")
    require(raw.get("analysis") == {"mode": "operating_point"}, "Unexpected owned SPICE analysis")
    require(isinstance(raw.get("issues"), list) and all(isinstance(i, dict) for i in raw["issues"])
            and not any(i.get("severity") == "error" for i in raw["issues"]), "Owned SPICE blocking issue")
    provenance = raw.get("provenance", {})
    require(provenance.get("source_sha256") == digest, "Owned result source digest mismatch")
    require(isinstance(provenance.get("library"), str)
            and Path(provenance["library"]).resolve() == library,
            "Owned result library differs from release-owned admission")
    require(len(json.dumps(raw, allow_nan=False).encode()) <= 8 * 1024**2,
            "Owned SPICE output exceeds 8 MiB")
    values = raw.get("data", {}).get("node_voltage_v", {})
    require(set(values) == {"0"} | {f"x{i}" for i in range(len(vector))},
            "Owned SPICE omitted or added lowered unknowns")
    require(all(type(value) in (float, int) and math.isfinite(value) for value in values.values()),
            "Invalid owned SPICE unknown")
    x = np.array([values[f"x{i}"] for i in range(len(vector))])
    backward = _relative_gate(np.abs(real @ x - vector), np.abs(real) @ np.abs(x) + np.abs(vector),
                             "Per-equation real-block")
    sanitized = deepcopy(raw)
    sanitized["provenance"].pop("library", None)
    return x[:len(x)//2] + 1j*x[len(x)//2:], {
        "lowered_netlist_sha256": digest, "native_result_sha256": _digest(sanitized),
        "native_diagnostics": deepcopy(raw.get("diagnostics", {})),
        "native_issues": deepcopy(raw["issues"]), "maximum_relative_real_block_error": backward,
    }


def _observables(circuit, nodes, bindings, ports, frequency, s, z0, x, sources, bmatrix):
    n, m = len(nodes), len(sources)
    voltage, q = x[:n], x[n+m:]
    outgoing = s @ q
    port_v = bmatrix.T @ voltage
    port_i = (q - outgoing) / z0
    wave_v = q + outgoing
    port_error = _relative_gate(np.abs(port_v - wave_v), np.abs(port_v) + np.abs(q) + np.abs(outgoing),
                               "Per-port terminal/wave")
    # Scale by the separately evaluated branches at each physical node, never
    # by the global excitation. Strong ports cannot hide weak-node KCL errors.
    kcl, kcl_scale = np.zeros(n, complex), np.zeros(n)
    element_results, absorbed, heat, supplied = {}, [], [], []
    voltage_errors = []
    for element in circuit["elements"]:
        branch = incidence(nodes, circuit["ground_node"], element["positive_node"], element["negative_node"])
        delta_v = branch @ voltage
        kind = element["type"]
        if kind == "voltage_source":
            current = x[n + sources.index(element)]
            imposed = _pair(element["phasor"])
            voltage_errors.append(_relative_gate(abs(delta_v-imposed), abs(delta_v)+abs(imposed),
                                                 "Voltage source"))
        elif kind == "current_source":
            current = _pair(element["phasor"])
        else:
            current = admittance(element, frequency) * delta_v
        kcl += branch * current
        kcl_scale += np.abs(branch) * abs(current)
        power = float((delta_v * current.conjugate()).real)
        require(math.isfinite(power), "Nonfinite branch power")
        if kind in {"voltage_source", "current_source"}:
            supplied.append(-power)
        else:
            absorbed.append(power)
        if kind == "resistor":
            heat.append(float(abs(delta_v)**2 / element["value"]))
        element_results[element["id"]] = {
            "voltage_rms_v": _pairs([delta_v])[0], "current_positive_to_negative_rms_a": _pairs([current])[0],
            "absorbed_real_power_w": power,
        }
    kcl += bmatrix @ port_i
    kcl_scale += np.abs(bmatrix) @ np.abs(port_i)
    kcl_error = _relative_gate(np.abs(kcl), kcl_scale, "Per-node physical KCL")
    powers = (port_v * port_i.conjugate()).real
    wave_powers = (np.abs(q)**2 - np.abs(outgoing)**2) / z0
    wave_scale = (np.abs(q)**2 + np.abs(outgoing)**2) / z0 + np.abs(port_v) * np.abs(port_i)
    wave_error = _relative_gate(np.abs(powers-wave_powers), wave_scale, "Per-port power identity")
    network_power, source_power, resistor_heat = math.fsum(powers), math.fsum(supplied), math.fsum(heat)
    power_error = abs(source_power - resistor_heat - network_power)
    power_scale = math.fsum(abs(v) for v in supplied + absorbed) + math.fsum(abs(v) for v in powers)
    _relative_gate(power_error, power_scale, "Physical circuit power balance")
    return {
        "frequency_hz": frequency, "node_voltage_rms_v": dict(zip(nodes, _pairs(voltage))),
        "elements": element_results, "voltage_rms_v": _pairs(port_v),
        "current_into_network_rms_a": _pairs(port_i),
        "incident_wave_sqrt_w": _pairs(q/math.sqrt(z0)), "outgoing_wave_sqrt_w": _pairs(outgoing/math.sqrt(z0)),
        "port_real_power_w": powers.tolist(), "unclassified_network_power_w": network_power,
        "circuit_resistor_heat_w": resistor_heat, "source_real_power_w": source_power,
        "power_balance_error_w": power_error,
        "maximum_relative_kcl_error": kcl_error, "maximum_relative_boundary_error": port_error,
        "maximum_relative_wave_power_error": wave_error,
        "maximum_relative_source_voltage_error": max(voltage_errors, default=0),
    }


def run_em_spice_coupling(request, *, cancel_check=None):
    """Execute one actual owned-SPICE real-block solve per exact EM sample.

    Inputs/outputs are RMS, exp(+j*omega*t); positive currents enter an element
    or EM port at positive_node. No caller DLL, shell, model file or text is
    accepted. Run in the existing supervised worker, never on the UI thread.
    """
    require(cancel_check is None or callable(cancel_check), "Cancellation check must be callable")
    encoded = json.dumps(request, sort_keys=True, allow_nan=False)
    require(len(encoded.encode()) <= 8*1024**2, "Request exceeds 8 MiB")
    raw = json.loads(encoded)
    require(isinstance(raw, dict) and set(raw) == {
        "contract", "source", "wave_convention", "circuit", "port_bindings"}
        and raw["contract"] == REQUEST_CONTRACT and raw["wave_convention"] == WAVE_CONVENTION,
        "Exact versioned request and explicit RMS common-real wave convention required")

    def poll():
        require(cancel_check is None or not cancel_check(), "CANCELLED")

    poll()
    source = raw["source"]
    require(isinstance(source, dict) and isinstance(source.get("frequencies_hz"), list)
            and 1 <= len(source["frequencies_hz"]) <= 64, "Provide 1..64 exact AC samples")
    admitted = resample_sparameter_network({"contract": SAMPLING_CONTRACT, "source": source,
        "target_frequencies_hz": source["frequencies_hz"], "dc_policy": {"mode": "require_source"}},
        cancel_check=cancel_check)
    require(all(0 < f <= 1e15 for f in source["frequencies_hz"]), "Only positive AC frequencies <=1e15 Hz supported")
    z0, ports = source["reference_impedance_ohm"], source["port_names"]
    require(1e-6 <= z0 <= 1e9, "Reference outside bounded real impedance range")
    require(all(d["smax"] <= 1+TOLERANCE for d in admitted["diagnostics"]), "Nonpassive EM sample rejected")
    circuit, bindings = raw["circuit"], raw["port_bindings"]
    nodes = admit_circuit(circuit, bindings, ports)
    library = owned_library_path()
    library_sha = hashlib.sha256(library.read_bytes()).hexdigest()
    results = []
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        for frequency, records, diagnostic in zip(source["frequencies_hz"], source["s_parameters"], admitted["diagnostics"]):
            poll()
            s = np.array([[complex(c["real"], c["imag"]) for c in row] for row in records])
            matrix, rhs, voltage_sources, bmatrix = assemble(circuit, nodes, bindings, ports, frequency, s, z0)
            netlist, real, vector, condition = lower_real_block(matrix, rhs)
            x, evidence = _execute(netlist, real, vector, poll, library)
            sample = _observables(circuit, nodes, bindings, ports, frequency, s, z0, x, voltage_sources, bmatrix)
            sample.update(evidence, connection_condition=condition, source_smax=diagnostic["smax"])
            results.append(sample)
    result = {
        "contract": RESULT_CONTRACT, "status": "completed", "model_status": "experimental",
        "production_qualified": False, "input_digest": _digest(raw), "source_digest": _digest(source),
        "ports": ports, "port_bindings": deepcopy(bindings), "wave_convention": WAVE_CONVENTION,
        "samples": results, "issues": [issue for sample in results for issue in sample["native_issues"]],
        "provenance": {"method": METHOD, "engine": "SPIKES owned C++ kernel", "library_origin": "release_owned",
            "library_name": library.name, "library_sha256": library_sha, "native_execution_count": len(results),
            "raw_netlist_accepted": False, "caller_selected_library": False, "shell_invoked": False,
            "phasor_convention": "RMS_exp_positive_j_omega_t", "native_ac_route": False},
        "limitations": ["Linear RLC and independent sources only; no nonlinear devices or native SPICE AC route",
            "Exact supplied positive frequencies only; no transient, interpolation or causality qualification",
            "Reference-plane labels are metadata, not de-embedding or EM field-power calibration",
            "Network power deficit remains unclassified, not automatically heat",
            "Cancellation between native calls only; supervised worker termination required for an in-flight call",
            "Synthetic verification is not physical validation; knowledgeable human numerical review remains required"],
    }
    require(hashlib.sha256(library.read_bytes()).hexdigest() == library_sha, "Owned library changed during execution")
    require(len(json.dumps(result, allow_nan=False).encode()) <= 16*1024**2, "Result exceeds 16 MiB")
    poll()
    return result
