"""Source-to-receiver SI orchestration with explicit linear model boundaries."""
from __future__ import annotations

from copy import deepcopy
from math import sqrt
from typing import Any, Mapping

import numpy as np

from .si_channel import _frequency_grid, _real_impulse, _prbs7, _fft_convolve_prefix, time_domain_report
from .si_ibis import parse_ibis, reduce_ibis
from .si_network_workflow import acquire_network, checked, digest, edit_network
from .si_passives import CAPACITOR_GRADES, RESISTOR_GRADES, KB, number, passive_defaults, resolve_passive, passive_admittance, resistor_noise
from .sparameters import NetworkData, analyze_network, touchstone_text
from .si_workflow_resonance import validate_resonance_requests, workflow_resonance_reports
from .si_symbol_clock import sample_nrz_clock
from .si_clock_recovery import recover_nrz_clock, validate_cdr_model

REQUEST = "spike/si-workflow-request/v1"
RESULT = "spike/si-workflow-result/v1"
SERIES_IMPACT_RESULT = "spike/si-series-component-impact-result/v1"
SOURCE = {"resistance_ohm": 50.0, "low_v": 0.0, "high_v": 1.8, "rise_time_s": 100e-12,
          "fall_time_s": 100e-12, "capacitance_f": 0.0, "package_r_ohm": 0.0,
          "package_l_h": 0.0, "package_c_f": 0.0, "pattern_shift_bits": 0, "delay_s": 0.0}
RECEIVER = {"resistance_ohm": 1e6, "capacitance_f": 2e-12, "package_r_ohm": 0.0,
            "package_l_h": 0.0, "package_c_f": 0.0, "vil_v": 0.63, "vih_v": 1.17,
            "input_noise_rms_v": 0.0}


def workflow_defaults() -> dict[str, Any]:
    return {"contract": REQUEST, "channel": {"kind": "rlgc", "coupled": True, "length_m": 0.05,
            "resistance_ohm_per_m": 5.0, "inductance_h_per_m": 250e-9, "capacitance_f_per_m": 100e-12,
            "loss_tangent": 0.015, "inductive_coupling": 0.08, "capacitive_coupling": 0.08,
            "frequency_stop_hz": 8e9, "frequency_points": 1025, "reference_impedance_ohm": 50.0},
            "sources": [{"port": 0, **SOURCE}], "receivers": [{"port": 2, **RECEIVER}],
            "passives": [], "edits": [], "bit_rate_hz": 1e9, "bit_count": 256,
            "temperature_c": 25.0, "run_time_domain": True, "export_format": "RI"}


def workflow_catalog() -> dict[str, Any]:
    return {"defaults": workflow_defaults(), "capacitor_grades": deepcopy(CAPACITOR_GRADES),
            "resistor_grades": deepcopy(RESISTOR_GRADES), "resistor": passive_defaults(),
            "capacitor": passive_defaults("capacitor"), "source": dict(SOURCE), "receiver": dict(RECEIVER),
            "model_status": "experimental", "production_qualified": False}


def _port(value, ports):
    if type(value) is not int or not 0 <= value < ports:
        raise ValueError(f"Port must be an integer in 0..{ports - 1}.")
    return value


def _endpoints(raw, role, ports):
    if not isinstance(raw, list) or not 1 <= len(raw) <= ports:
        raise ValueError(f"{role}s must contain 1..{ports} endpoint objects.")
    result, evidence = [], []
    defaults = SOURCE if role == "source" else RECEIVER
    for endpoint in raw:
        checked(endpoint, set(defaults) | {"port", "ibis"} | ({"cdr"} if role == "receiver" else set()), role)
        model = {**defaults, **endpoint}
        model["port"] = _port(endpoint.get("port"), ports)
        if "ibis" in endpoint:
            binding = endpoint["ibis"]
            ibis = parse_ibis(binding["text"], binding.get("name", "model.ibs"))
            reduction = reduce_ibis(ibis, binding, role)
            model.update(reduction["values"])
            evidence.append({"port": model["port"], "role": role, **reduction})
        for key, value in model.items():
            if key not in {"port", "ibis", "cdr"}:
                number(value, f"{role}.{key}")
        number(model["resistance_ohm"], "endpoint resistance", 1e-6, 1e12)
        for key in {"capacitance_f", "package_r_ohm", "package_l_h", "package_c_f"}:
            number(model[key], key, 0, 1e6)
        if role == "source":
            if model["high_v"] <= model["low_v"]:
                raise ValueError("Source high_v must exceed low_v.")
            for key in {"rise_time_s", "fall_time_s", "delay_s"}:
                number(model[key], key, 0, 1)
            shift = number(model["pattern_shift_bits"], "pattern_shift_bits", 0, 126)
            if int(shift) != shift:
                raise ValueError("pattern_shift_bits must be integral.")
        else:
            if model["vih_v"] <= model["vil_v"]:
                raise ValueError("Receiver vih_v must exceed vil_v.")
            number(model["input_noise_rms_v"], "input_noise_rms_v", 0, 1e3)
            if "cdr" in model:
                model["cdr"] = validate_cdr_model(model["cdr"])
        result.append(model)
    return result, evidence


def _loads(network, sources, receivers, passives, temperature):
    f, count, ports = network.frequencies_hz, len(network.frequencies_hz), network.port_count
    omega = 2 * np.pi * f
    # Unassigned ports receive real reference terminations, documented in result.
    y = np.tile(1 / network.reference_impedance_ohm, (count, 1)).astype(complex)
    drive = np.zeros((count, ports, len(sources)), dtype=complex)
    extra_y, extra_z = np.zeros_like(y), np.zeros_like(y)
    resolved = []
    branch_admittance = np.zeros_like(y)
    receiver_factors = np.ones_like(y)
    if not isinstance(passives, list) or len(passives) > 64:
        raise ValueError("At most 64 passive attachments are supported.")
    for item in passives:
        checked(item, {"id", "port", "connection", "model"}, "passive attachment")
        port = _port(item.get("port"), ports)
        connection = item.get("connection", "shunt")
        if connection not in {"series", "shunt"}:
            raise ValueError("Passive connection must be series or shunt.")
        raw = {"temperature_c": temperature, **item.get("model", {})}
        model = resolve_passive(raw)
        if model["model"]["temperature_c"] != temperature:
            raise ValueError("Loaded noise currently requires passive and study temperatures to agree.")
        admittance = passive_admittance(model, f)
        if connection == "series":
            if port not in [e["port"] for e in sources + receivers]:
                raise ValueError("Series attachments require an explicitly defined endpoint on that port.")
            extra_z[:, port] += 1 / admittance
        else:
            extra_y[:, port] += admittance
        report = {**item, **model}
        if model["model"]["kind"] == "resistor" and len(f) > 1:
            report["noise"] = resistor_noise(model, float(f[f > 0][0]), float(f[-1]))
        resolved.append(report)
    for role, endpoints in [("source", sources), ("receiver", receivers)]:
        for index, m in enumerate(endpoints):
            port = m["port"]
            package = m["package_r_ohm"] + 1j * omega * m["package_l_h"] + extra_z[:, port]
            if role == "source":
                # C_comp and C_pkg are lumped at the channel-facing terminal in
                # this linear reduction; exact package topology needs a network.
                branch_y = 1 / (m["resistance_ohm"] + package)
                y[:, port] = branch_y + 1j * omega * (m["capacitance_f"] + m["package_c_f"])
                drive[:, port, index] = branch_y
                branch_admittance[:, port] = branch_y
            else:
                die_y = 1 / m["resistance_ohm"] + 1j * omega * m["capacitance_f"]
                y[:, port] = die_y / (1 + package * die_y) + 1j * omega * m["package_c_f"]
                branch_admittance[:, port] = die_y / (1 + package * die_y)
                receiver_factors[:, port] = 1 / (1 + package * die_y)
    y += extra_y
    excess_current = np.zeros(y.shape, dtype=float)
    for item in resolved:
        m = item["model"]
        if m["kind"] != "resistor":
            continue
        port = item["port"]
        voltage_psd = np.zeros_like(f)
        positive = f > 0
        per_decade_v2 = (m["dc_voltage_v"] * 1e-6 * 10 ** (m["noise_index_db"] / 20)) ** 2
        voltage_psd[positive] = per_decade_v2 / (f[positive] * np.log(10))
        z_rl = item["effective"]["resistance_ohm"] + 1j * omega * m["inductance_h"]
        if item.get("connection", "shunt") == "shunt":
            gain = 1 / z_rl
        else:
            gain = branch_admittance[:, port] / (1 + 1j * omega * m["capacitance_f"] * z_rl)
        excess_current[:, port] += voltage_psd * np.abs(gain) ** 2
    return y, drive, resolved, receiver_factors, excess_current


def _loaded_response(network, y, drive, temperature, excess_current):
    s, z = network.s_parameters(), network.reference_impedance_ohm
    identity, root = np.eye(network.port_count), np.diag(np.sqrt(z))
    transfer = np.empty_like(drive, dtype=complex)
    noise, excess = np.empty(y.shape, dtype=float), np.empty(y.shape, dtype=float)
    # Bounded batches reuse the same wave boundary algebra without a Python
    # solve loop per frequency or an unbounded all-frequency matrix temporary.
    for start in range(0, len(s), 128):
        section = slice(start, start + 128)
        matrix = s[section]
        load = (z * y[section])[:, :, None] * identity
        boundary = identity + load + (load - identity) @ matrix
        rhs = np.broadcast_to(root, boundary.shape)
        current_to_voltage = root @ (identity + matrix) @ np.linalg.solve(boundary, rhs)
        transfer[section] = current_to_voltage @ drive[section]
        psd_current = 4 * KB * (temperature + 273.15) * np.maximum(y[section].real, 0)
        gain_squared = np.abs(current_to_voltage) ** 2
        noise[section] = (gain_squared @ psd_current[..., None])[..., 0]
        excess[section] = (gain_squared @ excess_current[section, :, None])[..., 0]
    return transfer, noise, excess


def _time_study(network, transfer, sources, receivers, rate, bits):
    f = _frequency_grid(network.frequencies_hz)
    dt = 1 / ((2 * len(f) - 1) * (f[1] - f[0]))
    actual_samples = 1 / (rate * dt)
    samples = int(round(actual_samples))  # Nominal display count only.
    if actual_samples < 8 - 1e-9:
        raise ValueError("Time grid needs at least 8 samples/UI; adjust bandwidth/point count.")
    count = int(np.ceil(bits * actual_samples))
    if count > 1_048_576:
        raise ValueError("Time-domain study exceeds 1,048,576 waveform samples.")
    times = np.arange(count) * dt
    voltages = np.zeros((count, len(receivers)))
    stimuli, impulses = [], []
    for source_index, source in enumerate(sources):
        sequence = np.roll(_prbs7(bits), int(source["pattern_shift_bits"]))
        if source["delay_s"] >= (bits - 32) / rate:
            raise ValueError("Source delay exceeds the usable waveform record.")
        wave = sample_nrz_clock(sequence, times, rate, source)
        stimuli.append(sequence)
        source_impulses = []
        for rx_index, rx in enumerate(receivers):
            impulse = _real_impulse(transfer[:, rx["port"], source_index])
            voltages[:, rx_index] += _fft_convolve_prefix(wave, impulse)
            source_impulses.append(impulse)
        impulses.append(source_impulses)
    reports = []
    for rx_index, rx in enumerate(receivers):
        impulse = impulses[0][rx_index]
        cursor_s = int(np.argmax(np.abs(impulse))) * dt + sources[0]["delay_s"]
        highs, lows, traces = [], [], []
        for bit_index in range(16, bits - 2):
            begin = bit_index / rate + cursor_s
            if begin + 2 / rate > times[-1]:
                break
            center = np.interp(begin + .5 / rate, times, voltages[:, rx_index])
            (highs if stimuli[0][bit_index] else lows).append(float(center))
            if len(traces) < 128:
                phases = np.linspace(0, 2, 2 * min(samples, 128), endpoint=False)
                values = np.interp(begin + phases / rate, times, voltages[:, rx_index])
                traces.append({"phase_ui": phases.tolist(), "voltage_v": values.tolist()})
        if not highs or not lows:
            raise ValueError("Waveform record is too short for the selected receiver delay.")
        idx = np.unique(np.linspace(0, len(voltages) - 1, min(2048, len(voltages))).astype(int))
        reports.append({"port": rx["port"], "eye_height_v": min(highs) - max(lows),
                        "cursor_delay_s": cursor_s, "sampling_phase_ui": .5,
                        "high_margin_v": min(highs) - rx["vih_v"], "low_margin_v": rx["vil_v"] - max(lows),
                        "high_min_v": min(highs), "low_max_v": max(lows),
                        "overshoot_v": max(0.0, float(voltages[:, rx_index].max()) - sources[0]["high_v"]),
                        "undershoot_v": max(0.0, sources[0]["low_v"] - float(voltages[:, rx_index].min())),
                        "traces": traces, "waveform": [{"time_s": float(i * dt), "voltage_v": float(voltages[i, rx_index])} for i in idx]})
        if "cdr" in rx:
            # Timing recovery must see the full waveform, not the plot export.
            recovered = recover_nrz_clock(times, voltages[:, rx_index], rate, rx["cdr"])
            reports[-1]["clock_recovery"] = {
                key: value.tolist() if isinstance(value, np.ndarray) else value
                for key, value in recovered.items()}
    return {"status": "completed", "delta_t_s": dt, "samples_per_ui": samples,
            "actual_samples_per_ui": actual_samples, "clock_mode": "exact_symbol_boundaries",
            "represented_bit_rate_hz": rate, "bit_count": bits,
            "receivers": reports, "pattern": "PRBS7", "noise_in_waveform": False,
            "limitations": ["Finite-bandwidth Hermitian reconstruction, no causality repair or invented DC.",
                            "Exact source symbol boundaries; sampled edges and linear receiver interpolation still need time-grid convergence.",
                            "Eye thresholds reference the first source, with other sources as deterministic aggressors; optional CDR reports are separate and do not imply compliance or BER qualification."]}


def run_si_workflow(request: Mapping[str, Any], design=None) -> dict[str, Any]:
    checked(request, {"contract", "channel", "edits", "sources", "receivers", "passives", "bit_rate_hz",
                      "bit_count", "temperature_c", "run_time_domain", "export_format", "resonance_requests"}, "SI workflow")
    if request.get("contract") != REQUEST:
        raise ValueError(f"Expected {REQUEST}.")
    defaults = workflow_defaults()
    validate_resonance_requests(request.get("resonance_requests",[]))
    setup = {**defaults, **deepcopy(dict(request))}
    temperature = number(setup["temperature_c"], "temperature_c", -273.14, 500)
    rate = number(setup["bit_rate_hz"], "bit_rate_hz", 1, 1e14)
    bits = number(setup["bit_count"], "bit_count", 128, 2048)
    if int(bits) != bits or not isinstance(setup["run_time_domain"], bool):
        raise ValueError("bit_count must be integral and run_time_domain must be boolean.")
    if setup["export_format"] not in {"RI", "MA", "DB"}:
        raise ValueError("export_format must be RI, MA or DB.")
    original, extraction = acquire_network(setup["channel"], design)
    network, history = edit_network(original, setup["edits"])
    ports = network.port_count
    resonance_fits=workflow_resonance_reports(network,request.get("resonance_requests",[]))
    if "receivers" not in request:
        setup["receivers"] = [{"port": 2 if ports == 4 else 1, **RECEIVER}]
    sources, tx_evidence = _endpoints(setup["sources"], "source", ports)
    receivers, rx_evidence = _endpoints(setup["receivers"], "receiver", ports)
    if not setup["run_time_domain"] and any("cdr" in receiver for receiver in receivers):
        raise ValueError("Receiver CDR requires run_time_domain=true.")
    assignments = [m["port"] for m in sources + receivers]
    if len(set(assignments)) != len(assignments):
        raise ValueError("Each port may have only one source or receiver assignment.")
    y, drive, passives, receiver_factors, excess_current = _loads(network, sources, receivers, setup["passives"], temperature)
    if not all(np.all(np.isfinite(v)) for v in (y, drive, receiver_factors, excess_current)):
        raise ValueError("Endpoint/attachment resonance produced a singular ideal network; supply finite physical loss.")
    transfer, noise_psd, excess_psd = _loaded_response(network, y, drive, temperature, excess_current)
    if not all(np.all(np.isfinite(v)) for v in (transfer, noise_psd, excess_psd)):
        raise ValueError("Loaded network solution contains non-finite values.")
    f = network.frequencies_hz
    indices = np.unique(np.linspace(0, len(f) - 1, min(len(f), 1024)).astype(int))
    loaded = []
    receiver_ports = {receiver["port"] for receiver in receivers}
    for source_index, source in enumerate(sources):
        for port in range(ports):
            h = transfer[:, port, source_index]
            item = {"source_port": source["port"], "observed_port": port,
                    "trace": [{"frequency_hz": float(f[i]), "magnitude_db": float(20 * np.log10(max(abs(h[i]), 1e-15))),
                               "phase_deg": float(np.angle(h[i], deg=True)), "real": float(h[i].real), "imag": float(h[i].imag)} for i in indices]}
            if port in receiver_ports:
                die = h * receiver_factors[:, port]
                item["receiver_die_trace"] = [
                    {"frequency_hz": float(f[i]), "magnitude_db": float(20 * np.log10(max(abs(die[i]), 1e-15))),
                     "phase_deg": float(np.angle(die[i], deg=True)), "real": float(die[i].real), "imag": float(die[i].imag)}
                    for i in indices]
            loaded.append(item)
    integrate = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
    noise_rms = np.sqrt(np.maximum(integrate(noise_psd, f, axis=0), 0))
    positive = f > 0
    excess_rms = np.sqrt(np.maximum(integrate(excess_psd[positive], f[positive], axis=0), 0))
    time_result = {"status": "not_requested"}
    tdr = {"status": "not_requested"}
    if setup["run_time_domain"]:
        try:
            time_result = _time_study(network, transfer * receiver_factors[:, :, None], sources, receivers, rate, int(bits))
            time_result["voltage_reference"] = "Receiver die after endpoint series attachments and package R/L; loaded transfer plots use channel-facing port voltage."
            tdr = time_domain_report(network, incident_port=sources[0]["port"], observed_port=receivers[0]["port"])
        except ValueError as exc:
            time_result = {"status": "blocked", "reason": str(exc)}
            tdr = {"status": "blocked", "reason": str(exc)}
    warnings = [w for item in passives for w in item["warnings"]]
    text = None
    export_error = None
    try:
        text = touchstone_text(f, network.s_parameters(), network.reference_impedance_ohm,
                              data_format=setup["export_format"], comments=["SPIKE edited channel only; endpoint loading is reported separately.",
                              f"Request SHA256 {digest(setup)}", "Ports use the explicit edited network order."])
    except ValueError as exc:
        export_error = str(exc)
    return {"contract": RESULT, "status": "partial" if time_result["status"] == "blocked" or export_error else "completed", "model_status": "experimental", "production_qualified": False,
            "compliance_status": "not_evaluated", "request": setup, "request_sha256": digest(setup),
            "extraction": extraction, "network": analyze_network(network, trace_limit=1024),
            "edits": history, "sources": sources, "receivers": receivers, "passives": passives, "resonance_fits":resonance_fits,
            "ibis": tx_evidence + rx_evidence, "loaded_transfers": loaded, "time_domain": time_result,
            "tdr": tdr, "touchstone": {"name": f"si-channel.s{ports}p", "text": text, "error": export_error},
            "noise": {"band_hz": [float(f[0]), float(f[-1])], "thermal_rms_v_by_port": noise_rms.tolist(),
                      "excess_band_hz": [float(f[positive][0]), float(f[-1])] if np.any(positive) else None,
                      "excess_rms_v_by_port": excess_rms.tolist(),
                      "total_rms_v_by_port": np.sqrt(noise_rms ** 2 + excess_rms ** 2).tolist(),
                      "receiver_input_noise_rms_v": [{"port": r["port"], "rms_v": r["input_noise_rms_v"]} for r in receivers],
                      "scope": "Channel-facing port thermal and resistor 1/f excess noise. Receiver internal noise is listed separately; noise is not injected into eyes. Channel loss noise and receiver die noise transfer are excluded."},
            "unassigned_port_termination": "Each unassigned port is terminated in its real reference impedance.",
            "warnings": list(dict.fromkeys(warnings)),
            "limitations": ["Linear frequency-domain network and lumped endpoint/passive approximations; no nonlinear IBIS switching or power-aware co-simulation.",
                            "Crosstalk is the loaded transfer from a chosen source to an explicitly mapped victim port; imported networks carry no geometry extraction claim.",
                            "Time-domain outputs require explicit DC and a uniform grid; finite bandwidth and periodic impulse tails can affect results.",
                            "Passive grade defaults are editable assumptions, not guaranteed part behavior. Min/max are parameter envelopes, not statistical yield."]}


def run_series_component_impact(
    request: Mapping[str, Any],
    series_components: list[Mapping[str, Any]],
    *,
    source_port: int | None = None,
    receiver_port: int | None = None,
    design=None,
) -> dict[str, Any]:
    """Compare a loaded SI path before and after explicit endpoint series parts.

    The component models are the same bounded SI-unit resistor/capacitor models
    accepted by :func:`run_si_workflow`.  A resistor model is R-L with parallel
    parasitic C; a capacitor model is C with series ESR/ESL and parallel leakage.
    This helper does not synthesize a package, interconnect, nonlinear IBIS, or
    AMI model.
    """
    if not isinstance(request, Mapping):
        raise ValueError("SI request must be an object.")
    if not isinstance(series_components, list) or not 1 <= len(series_components) <= 16:
        raise ValueError("series_components must contain 1..16 explicit attachments.")

    baseline_request = deepcopy(dict(request))
    existing = baseline_request.get("passives", [])
    if not isinstance(existing, list):
        raise ValueError("request.passives must be an array.")
    additions = []
    existing_ids = {item.get("id") for item in existing if isinstance(item, Mapping) and item.get("id") is not None}
    for index, raw in enumerate(series_components):
        checked(raw, {"id", "port", "connection", "model"}, "series component")
        if raw.get("connection", "series") != "series":
            raise ValueError("Series-component impact accepts only connection='series'.")
        if "port" not in raw or "model" not in raw:
            raise ValueError("Each series component requires explicit port and model fields.")
        item = deepcopy(dict(raw))
        item["connection"] = "series"
        item.setdefault("id", f"series-impact-{index + 1}")
        if item["id"] in existing_ids or any(prior["id"] == item["id"] for prior in additions):
            raise ValueError("Series component ids must be unique across existing and added passives.")
        # Resolve before either run so units, finite bounds, positive passive
        # values, grade envelopes and the declared topology fail closed.
        resolve_passive(item["model"])
        additions.append(item)

    baseline = run_si_workflow(baseline_request, design)
    passivity = baseline["network"]["checks"]["passivity"]
    if passivity.get("status") != "pass":
        raise ValueError(
            "Series-component impact requires a passive input channel; "
            f"network check reported {passivity.get('status', 'unknown')}."
        )

    sources = [item["port"] for item in baseline["sources"]]
    receivers = [item["port"] for item in baseline["receivers"]]
    if source_port is None:
        if len(sources) != 1:
            raise ValueError("Select source_port explicitly when the workflow has multiple sources.")
        source_port = sources[0]
    if receiver_port is None:
        if len(receivers) != 1:
            raise ValueError("Select receiver_port explicitly when the workflow has multiple receivers.")
        receiver_port = receivers[0]
    if source_port not in sources or receiver_port not in receivers:
        raise ValueError("Impact ports must map to declared source and receiver endpoints.")
    endpoint_ports = set(sources + receivers)
    if any(item["port"] not in endpoint_ports for item in additions):
        raise ValueError("Every series component must map to a declared source or receiver endpoint port.")

    modified_request = deepcopy(baseline_request)
    modified_request["passives"] = deepcopy(existing) + additions
    modified = run_si_workflow(modified_request, design)

    def selected_trace(result):
        matches = [item.get("receiver_die_trace", item["trace"]) for item in result["loaded_transfers"]
                   if item["source_port"] == source_port and item["observed_port"] == receiver_port]
        if len(matches) != 1:
            raise ValueError("Selected source-to-receiver transfer did not resolve exactly once.")
        return matches[0]

    before_trace, after_trace = selected_trace(baseline), selected_trace(modified)
    if len(before_trace) != len(after_trace):
        raise ValueError("Before/after transfer grids do not match.")
    comparison = []
    for before_point, after_point in zip(before_trace, after_trace):
        if before_point["frequency_hz"] != after_point["frequency_hz"]:
            raise ValueError("Before/after transfer frequencies do not match.")
        before_complex = complex(before_point["real"], before_point["imag"])
        after_complex = complex(after_point["real"], after_point["imag"])
        comparison.append({
            "frequency_hz": before_point["frequency_hz"],
            "before_magnitude_db": before_point["magnitude_db"],
            "after_magnitude_db": after_point["magnitude_db"],
            "delta_magnitude_db": after_point["magnitude_db"] - before_point["magnitude_db"],
            "complex_delta_magnitude": float(abs(after_complex - before_complex)),
        })
    worst = min(comparison, key=lambda point: point["delta_magnitude_db"])
    return {
        "contract": SERIES_IMPACT_RESULT,
        "status": "completed" if baseline["status"] == modified["status"] == "completed" else "partial",
        "model_status": "experimental",
        "production_qualified": False,
        "source_port": source_port,
        "receiver_port": receiver_port,
        "series_components": additions,
        "validation": {
            "channel_passivity": passivity,
            "component_passivity": {
                "status": "pass",
                "method": "bounded positive R/L/C parameter and topology validation",
                "count": len(additions),
            },
            "port_mapping": "Explicit declared source and receiver ports; zero-based Touchstone/workflow order.",
            "component_units": "SI: ohm, henry, farad, volt, second and degrees Celsius.",
        },
        "comparison": comparison,
        "summary": {
            "worst_delta_magnitude_db": worst["delta_magnitude_db"],
            "worst_delta_frequency_hz": worst["frequency_hz"],
            "maximum_complex_transfer_change": max(point["complex_delta_magnitude"] for point in comparison),
        },
        "before": baseline,
        "after": modified,
        "limitations": [
            "Linear endpoint series attachments only; placement inside an imported channel requires an explicit cascaded network.",
            "IBIS endpoints, when present, use only the declared fixed DC-slope/ramp reduction; no nonlinear switching or IBIS-AMI execution.",
            "A passing sampled S-parameter passivity check is not causality, fixture-deembedding, measurement-correlation or compliance qualification.",
        ],
    }
