# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Explicit loaded NEXT/FEXT terminal voltages using the existing N-port solver."""
from collections.abc import Mapping
import math
import numpy as np

from .si_channel import _frequency_grid, _real_impulse, _fft_convolve_prefix
from .si_workflow import _loaded_response

CONTRACT = "spike/si-loaded-crosstalk-result/v1"
ROLES = {"aggressor_near", "aggressor_far", "victim_near", "victim_far"}


def validate_model(raw, port_count=4):
    if not isinstance(raw, Mapping) or set(raw) - {"port_map", "termination_ohm", "waveform_v", "trace_limit"}:
        raise ValueError("Unknown loaded crosstalk model fields")
    ports = raw.get("port_map")
    if not isinstance(ports, Mapping) or set(ports) != ROLES:
        raise ValueError("Explicit aggressor/victim near/far port map required")
    if any(type(value) is not int or not 0 <= value < port_count for value in ports.values()) or len(set(ports.values())) != 4:
        raise ValueError("Crosstalk ports must be distinct zero-based network port indices")
    resistances = raw.get("termination_ohm")
    if not isinstance(resistances, (list, tuple)) or len(resistances) != port_count:
        raise ValueError("One explicit resistance per network port required, including the source")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not 1e-6 <= value <= 1e12 for value in resistances):
        raise ValueError("Termination resistance must be finite within 1e-6..1e12 ohm")
    waveform = raw.get("waveform_v")
    if waveform is not None:
        if not isinstance(waveform, (list, tuple)) or not 2 <= len(waveform) <= 65536:
            raise ValueError("waveform_v must contain 2..65536 Thevenin voltage samples")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not -1e6 <= value <= 1e6 for value in waveform):
            raise ValueError("Waveform voltage must be finite within +/-1e6 V")
    limit = raw.get("trace_limit", 2048)
    if type(limit) is not int or not 16 <= limit <= 16384:
        raise ValueError("trace_limit must be an integer in 16..16384")
    return {"port_map": dict(ports), "termination_ohm": list(resistances),
            "waveform_v": list(waveform) if waveform is not None else None, "trace_limit": limit}


def analyze_crosstalk(network, *, port_map, termination_ohm, waveform_v=None, trace_limit=2048, cancel_check=None):
    """All other sources suppressed; waveform is open-circuit source voltage.

    Finite-band Hermitian reconstruction is not causality repair. Non-DC or
    nonuniform data retains a frequency-only result, never invented DC.
    """
    def cancelled():
        if cancel_check is not None and cancel_check():
            raise ValueError("Loaded crosstalk analysis cancelled")
    cancelled()
    count = network.port_count
    if not 4 <= count <= 16:
        raise ValueError("Loaded crosstalk supports 4..16 network ports")
    model = validate_model({"port_map": port_map, "termination_ohm": termination_ohm,
        "waveform_v": waveform_v, "trace_limit": trace_limit}, count)
    f = np.asarray(network.frequencies_hz, dtype=float)
    z = np.asarray(network.reference_impedance_ohm, dtype=float)
    if f.ndim != 1 or not 1 <= len(f) <= 8193 or not np.all(np.isfinite(f)) or np.any(f < 0) or np.any(np.diff(f) <= 0):
        raise ValueError("Network frequencies must be 1..8193 finite increasing nonnegative samples")
    if z.shape != (count,) or not np.all(np.isfinite(z)) or np.any(z <= 0):
        raise ValueError("Finite positive real reference impedance per port required")
    s = network.s_parameters()
    if s.shape != (len(f), count, count) or not np.all(np.isfinite(s)):
        raise ValueError("Finite aligned network matrices required")
    resistance = np.asarray(model["termination_ohm"], dtype=float)
    y = np.tile(1 / resistance, (len(f), 1)).astype(complex)
    drive = np.zeros((len(f), count, 1), dtype=complex)
    source = model["port_map"]["aggressor_near"]
    drive[:, source, 0] = 1 / resistance[source]
    try:
        cancelled()
        transfer = _loaded_response(network, y, drive, 25.0, np.zeros_like(y.real))[0][:, :, 0]
    except np.linalg.LinAlgError as exc:
        raise ValueError("Loaded crosstalk network is singular") from exc
    cancelled()
    if not np.all(np.isfinite(transfer)):
        raise ValueError("Loaded voltage transfer is not finite")
    index = np.unique(np.linspace(0, len(f) - 1, min(len(f), trace_limit)).astype(int))
    result = {"contract": CONTRACT, "status": "completed", "port_map": model["port_map"],
        "termination_ohm": model["termination_ohm"], "frequency_response": {},
        "source_definition": "Thevenin open-circuit voltage at aggressor_near through its specified resistance; other ports are resistively terminated",
        "production_qualified": False, "geometry_or_field_coupling_claimed": False,
        "limitations": ["Linear network result; no nonlinear receiver, compliance, BER or measured correlation claim.",
            "NEXT/FEXT labels rely on caller-supplied physical near/far mapping.",
            "Finite bandwidth and record length limit transient accuracy; no passivity or causality enforcement."]}
    responses = {"next": transfer[:, model["port_map"]["victim_near"]], "fext": transfer[:, model["port_map"]["victim_far"]]}
    for name, values in responses.items():
        result["frequency_response"][name] = {"units": "V/V", "trace": [
            {"frequency_hz": float(f[i]), "real": float(values[i].real), "imag": float(values[i].imag),
             "magnitude": float(abs(values[i])), "transfer_db": 20 * math.log10(max(float(abs(values[i])), 1e-300))} for i in index]}
    if waveform_v is None:
        result["time_domain"] = {"status": "not_requested"}
        return result
    try:
        frequencies = _frequency_grid(f)
        dt = 1 / ((2 * len(frequencies) - 1) * (frequencies[1] - frequencies[0]))
        impulses = {name: _real_impulse(values) for name, values in responses.items()}
    except ValueError as exc:
        result["time_domain"] = {"status": "unsupported_grid", "reason": str(exc)}
        return result
    wave = np.asarray(model["waveform_v"], dtype=float)
    voltages = {}
    for name, impulse in impulses.items():
        cancelled()
        voltages[name] = _fft_convolve_prefix(wave, impulse)
    cancelled()
    if not math.isfinite(dt) or not all(np.all(np.isfinite(values)) for values in voltages.values()):
        raise ValueError("Transient crosstalk is not finite")
    extremes = {0, len(wave)-1}
    for values in voltages.values():
        extremes.update((int(np.argmin(values)), int(np.argmax(values))))
    budget = min(len(wave), trace_limit)
    regular = np.linspace(0, len(wave)-1, budget).astype(int)
    chosen = set(extremes)
    for index in regular:
        if len(chosen) == budget:
            break
        chosen.add(int(index))
    indices = np.asarray(sorted(chosen), dtype=int)
    result["time_domain"] = {"status": "completed", "delta_t_s": float(dt), "sample_count": len(wave),
        "time_s": (indices * dt).tolist(), "source_v": wave[indices].tolist(),
        "next_v": voltages["next"][indices].tolist(), "fext_v": voltages["fext"][indices].tolist(),
        "peak_abs_next_v": float(np.max(np.abs(voltages["next"]))), "peak_abs_fext_v": float(np.max(np.abs(voltages["fext"]))),
        "initial_state": "Zero source voltage and zero network state before sample zero",
        "impulse_record_duration_s": float((2 * len(f) - 1) * dt),
        "noise_in_waveform": False}
    return result
