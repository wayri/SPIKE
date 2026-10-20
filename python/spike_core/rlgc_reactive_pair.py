# SPDX-License-Identifier: Apache-2.0
"""Sampled series-R/L and node-shunt-C loads for a supplied coupled pair.

Original derivation: Is=Iline+jwC*V and Vs=V+(R+jwL)*Is.
With Yt=1/(R+jwL)+jwC and J=Vs/(R+jwL), Norton closure gives
(I-diag(gamma)*S)*a=d, gamma=(1-Zref*Yt)/(1+Zref*Yt),
d=sqrt(Zref)*J/(1+Zref*Yt). RMS source complex power splits into
line power, R|Is|^2 heat and 2jw*(UL-UC), where UL/UC are mean J.
Foundation: Staelin (2011), MIT OCW chapter8 sections8.1.4/8.3.1;
independently derived, see method record. Stored energy is never heat.
"""
from __future__ import annotations
import math
import numpy as np

from . import rlgc_terminated_pair as resistive
from .sparameter_sampling import SParameterSamplingError, _digest, _snapshot

pair = resistive.pair
REQUEST = "spike/rlgc-reactive-pair-request/v1"
RESULT = "spike/rlgc-reactive-pair-result/v1"
_MAX_BYTES = 32*1024*1024
_MAX_CONDITION = 1e8


class ReactivePairError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = "REACTIVE_PAIR_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise ReactivePairError(code, message)


def _adapter(raw):
    return {"contract": resistive.REQUEST, "pair": raw["pair"], "sources": raw["sources"],
        "terminations": [{key: term[key] for key in ("id", "port", "resistance_ohm")} for term in raw["terminations"]]}


def _prepare(raw, poll):
    resistive._record(raw, {"contract", "pair", "terminations", "sources"}, "reactive pair")
    _require(raw["contract"] == REQUEST, "Unsupported reactive pair contract")
    terms = raw["terminations"]
    _require(isinstance(terms, list) and len(terms) == 4, "Provide four physical R/L/C terminations")
    for term in terms:
        resistive._record(term, {"id", "port", "resistance_ohm", "inductance_h", "capacitance_f"}, "R/L/C termination")
        for key, maximum in (("inductance_h", 1e3), ("capacitance_f", 1.)):
            value = term[key]
            _require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum,
                     key+" must be finite, nonnegative and within the stated bound")
    resistive._prepare(_adapter(raw), poll)
    return sorted(terms, key=lambda term: term["port"])


def _feedback(scattering, source, resistance, inductance, capacitance, omega, reference):
    impedance = resistance+1j*omega*inductance
    admittance = 1/impedance
    total = admittance+1j*omega*capacitance
    denominator = 1+reference*total
    gamma = (1-reference*total)/denominator
    drive = np.sqrt(reference)*(admittance*source)/denominator
    system = np.eye(4)-gamma[:, None]*scattering
    condition = float(np.linalg.cond(system))
    _require(math.isfinite(condition) and condition <= _MAX_CONDITION, "Reactive feedback exceeds condition1e8", "ill_conditioned")
    incident = np.linalg.solve(system, drive)
    residual = float(np.linalg.norm(system@incident-drive))
    scale = float(np.linalg.norm(system)*np.linalg.norm(incident)+np.linalg.norm(drive))
    _require(np.isfinite(incident).all() and math.isfinite(residual) and residual <= 1e-10*scale,
             "Reactive feedback residual failed", "numerical_failure")
    return incident, condition, residual


def _point(raw, terms, child, index, scattering, solution):
    incident, condition, residual = solution
    omega = 2*np.pi*raw["sources"][index]["frequency_hz"]
    reference = raw["pair"]["modes"]["even"]["reference_impedance_ohm"]
    source = np.array([pair._complex(v) for v in raw["sources"][index]["voltage_v"]])
    r, l, c = (np.array([term[key] for term in terms]) for key in ("resistance_ohm", "inductance_h", "capacitance_f"))
    outgoing = scattering@incident
    voltage = np.sqrt(reference)*(incident+outgoing)
    line_current = (incident-outgoing)/np.sqrt(reference)
    cap_current = 1j*omega*c*voltage
    source_current = line_current+cap_current
    kvl = voltage+(r+1j*omega*l)*source_current-source
    scale = max(np.linalg.norm(voltage), np.linalg.norm((r+1j*omega*l)*source_current), np.linalg.norm(source))
    _require(np.linalg.norm(kvl) <= 1e-9*scale, "Reactive terminal KVL failed", "numerical_failure")
    physical = child["points"][index]
    for key, expected in (("voltage_v", voltage), ("current_into_line_a", line_current)):
        resistive._same_vector(np.array([pair._complex(p[key]) for p in physical["boundary_values"]]), expected)
    squared_source = np.real(source_current*np.conj(source_current))
    squared_voltage = np.real(voltage*np.conj(voltage))
    heat, magnetic, electric = r*squared_source, .5*l*squared_source, .5*c*squared_voltage
    source_power, line_power = source*np.conj(source_current), voltage*np.conj(line_current)
    reactive = 2*omega*(magnetic-electric)
    complex_residual = source_power-line_power-heat-1j*reactive
    complex_scale = np.maximum.reduce([abs(source_power), abs(line_power), heat, abs(reactive)])
    _require(np.isfinite(complex_residual).all() and np.all(abs(complex_residual) <= 1e-10*complex_scale),
             "Terminal complex-power identity failed", "numerical_failure")
    line = physical["power_balance"]
    line_heat = line["conductor_loss_w"]+line["dielectric_loss_w"]
    total_source, total_line = np.sum(source_power), np.sum(line_power)
    terminal_heat = float(np.sum(heat))
    source_residual = float(total_source.real-terminal_heat-line_heat)
    line_residual = float(total_line.real-line_heat)
    total_heat = terminal_heat+line_heat
    budget_scale = max(float(np.sum(abs(source_power))), float(np.vdot(incident, incident).real), total_heat)
    _require(math.isfinite(total_heat) and np.isfinite(total_source) and abs(source_residual) <= 1e-10*budget_scale
             and abs(line_residual) <= 1e-10*budget_scale, "Reactive source/heat budget failed", "numerical_failure")
    records = [{**term, "source_voltage_v": pair._pair(source[j]), "voltage_v": pair._pair(voltage[j]),
        "current_into_line_a": pair._pair(line_current[j]), "source_current_a": pair._pair(source_current[j]),
        "capacitor_current_a": pair._pair(cap_current[j]), "source_power_va": pair._pair(source_power[j]),
        "line_power_va": pair._pair(line_power[j]), "resistor_heat_w": float(heat[j]),
        "inductor_average_energy_j": float(magnetic[j]), "capacitor_average_energy_j": float(electric[j]),
        "reactive_exchange_var": float(reactive[j]), "kvl_residual_v": pair._pair(kvl[j]),
        "complex_power_residual_va": pair._pair(complex_residual[j])} for j, term in enumerate(terms)]
    return {"frequency_hz": raw["sources"][index]["frequency_hz"], "terminals": records,
        "feedback_condition": condition, "feedback_residual": residual,
        "power_balance": {"source_power_va": pair._pair(total_source), "line_power_va": pair._pair(total_line),
            "terminal_resistor_heat_w": terminal_heat, "line_conductor_heat_w": line["conductor_loss_w"],
            "line_dielectric_heat_w": line["dielectric_loss_w"], "total_heat_w": total_heat,
            "terminal_inductor_average_energy_j": float(np.sum(magnetic)), "terminal_capacitor_average_energy_j": float(np.sum(electric)),
            "terminal_reactive_exchange_var": float(np.sum(reactive)), "source_residual_w": source_residual,
            "line_residual_w": line_residual, "terminal_complex_residual_va": pair._pair(np.sum(complex_residual))}}


def run_rlgc_reactive_pair(request, *, cancel_check=None):
    """Solve sampled series-R/L, shunt-C loads; keep stored J out of heat W."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")
    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise ReactivePairError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Reactive pair cancelled", "cancelled")
    try:
        poll(); _prepare(request, poll)
        raw, size = _snapshot(request); terms = _prepare(raw, poll); admitted = _adapter(raw)
        count = len(raw["sources"])
        _require(4*size+count*(20480+4096*len(raw["pair"]["probes"]))+262144 <= _MAX_BYTES,
                 "Estimated reactive-pair output exceeds32MiB", "resource_limit")
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            scattering = resistive._bare_network(admitted, poll, cancel_check)
            r, l, c = (np.array([term[key] for term in terms]) for key in ("resistance_ohm", "inductance_h", "capacitance_f"))
            reference = raw["pair"]["modes"]["even"]["reference_impedance_ohm"]
            solutions = []
            for matrix, source in zip(scattering, raw["sources"]):
                poll()
                solutions.append(_feedback(matrix, np.array([pair._complex(v) for v in source["voltage_v"]]), r, l, c,
                    2*np.pi*source["frequency_hz"], reference))
            expected = resistive._pair_request(admitted, [solution[0] for solution in solutions])
            child = pair.run_rlgc_coupled_pair(expected, cancel_check=cancel_check)
            resistive._bind(child, expected, scattering, poll)
            pair._size(child, _MAX_BYTES-size)
            points = []
            for index, solution in enumerate(solutions):
                poll(); points.append(_point(raw, terms, child, index, scattering[index], solution))
        result = {"contract": RESULT, "model_status": "experimental", "production_qualified": False,
            "source_request": raw, "input_digest": _digest(raw), "pair_result": child, "points": points,
            "limitations": ["Sampled RMS seriesR/L and node-shuntC physical terminations; R1e-6..1e12ohm,L0..1e3H,C0..1F.",
                "Positive source resistance and fixed ideal L/C only; no shorts/opens, nonlinear, lossy-core, frequency-dependent endpoint or transient/causal qualification.",
                "Source current differs from line current by shunt capacitor current. Stored mean J and reactive var are not resistor/line heat W.",
                "Each positive frequency is an independent steady case, with no automatic frequency summation or transient thermal input.",
                "Unchanged supplied symmetric pair; no geometry/contact/material extraction, physical heat mapping or measured/board qualification."]}
        pair._size(result, _MAX_BYTES); poll()
        return result
    except ReactivePairError:
        raise
    except (resistive.TerminatedPairError, pair.CoupledPairError, resistive.RLGCLineNetworkError, SParameterSamplingError) as error:
        code = error.code
        for prefix in ("TERMINATED_PAIR_", "COUPLED_PAIR_", "RLGC_LINE_NETWORK_", "SPARAMETER_SAMPLING_"):
            code = code.removeprefix(prefix)
        raise ReactivePairError(code, str(error)) from error
    except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise ReactivePairError("numerical_failure", str(error)) from error
