# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SPIKE contributors
"""Original supplied-network capacitor comparison, not geometry extraction.

V=ZI and Icap=Vc/Zcap give the rank-one shunt update directly. All ports
share an explicit reference return. See docs/CAPACITOR_PLACEMENT.md for
derivation, sampled passivity, independent tests and applicability limits.
"""
from __future__ import annotations

import math
from copy import deepcopy
import numpy as np

REQUEST_CONTRACT = "spike/capacitor-placement-request/v1"
RESULT_CONTRACT = "spike/capacitor-placement-result/v1"
MAX_PORTS = 32
MAX_FREQUENCIES = 1024
MAX_CANDIDATES = 256
MAX_MATRIX_ENTRIES = 262144
MAX_OUTPUT_POINTS = 131072
PASSIVITY_TOLERANCE = 1e-10
DENOMINATOR_TOLERANCE = 1e-10


class CapacitorPlacementError(ValueError):
    """Coded malformed-network or unsupported-study failure."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


def _require(condition, code, message):
    if not condition:
        raise CapacitorPlacementError(code, message)


def _keys(value, names, label):
    _require(isinstance(value, dict) and set(value) == set(names.split()),
             "invalid_fields", f"{label} has unexpected or missing fields.")


def _text(value, label):
    _require(isinstance(value, str) and 0 < len(value) <= 256 and value.strip() == value,
             "invalid_identity", f"{label} requires 1..256 characters without surrounding whitespace.")
    return value


def _number(value, label, minimum=0., positive=False):
    _require(type(value) in (int, float), "invalid_number", f"{label} requires a finite number.")
    try:
        result = float(value)
    except OverflowError as exc:
        raise CapacitorPlacementError("invalid_number", f"{label} is not representable.") from exc
    _require(math.isfinite(result) and result >= minimum and (not positive or result > 0),
             "invalid_number", f"{label} is outside its finite domain.")
    return result


def _list(value, label, maximum, minimum=1):
    _require(isinstance(value, list) and minimum <= len(value) <= maximum,
             "resource_budget", f"{label} requires {minimum}..{maximum} items.")
    return value


def _network(request, board):
    frequencies = [_number(f, "frequency_hz", positive=True)
                   for f in _list(request["frequencies_hz"], "frequencies", MAX_FREQUENCIES, 2)]
    _require(all(b > a for a, b in zip(frequencies, frequencies[1:])),
             "frequency_order", "Frequencies must be strictly increasing in Hz.")
    _require(1e-6 <= frequencies[0] < frequencies[-1] <= 1e12,
             "numeric_range", "Frequency range must lie within [1e-6, 1e12] Hz.")
    ports, ids = _list(request["ports"], "ports", MAX_PORTS), []
    for port in ports:
        _keys(port, "id occurrence_id", "port")
        identity = _text(port["id"], "port id")
        _require(identity not in ids, "duplicate_port", "Port IDs must be unique.")
        _require(port["occurrence_id"] == board, "board_binding", "All ports must belong to the declared board occurrence.")
        ids.append(identity)
    nf, np_ = len(frequencies), len(ids)
    _require(nf*np_*np_ <= MAX_MATRIX_ENTRIES, "resource_budget", "Sampled matrix exceeds its entry budget.")
    matrices = _list(request["z_ohm"], "z_ohm", nf, nf)
    converted = []
    for matrix in matrices:
        rows = _list(matrix, "matrix rows", np_, np_)
        decoded = []
        for row in rows:
            values = []
            for pair in _list(row, "matrix columns", np_, np_):
                _list(pair, "complex [real, imaginary] pair", 2, 2)
                value = complex(*[_number(v, "impedance_ohm", -math.inf) for v in pair])
                _require(abs(value) <= 1e12, "numeric_range", "Impedance magnitude exceeds 1e12 ohm.")
                values.append(value)
            decoded.append(values)
        converted.append(decoded)
    z = np.asarray(converted, dtype=complex)
    minimum_eigenvalue, reciprocity = math.inf, 0.
    for matrix in z:
        scale = max(float(np.max(np.abs(matrix))), 1e-300)
        normalized = matrix/scale
        eigenvalue = float(np.linalg.eigvalsh((normalized+normalized.conj().T)/2)[0])
        _require(eigenvalue >= -PASSIVITY_TOLERANCE, "nonpassive_network",
                 "A sampled Hermitian impedance part has a negative eigenvalue beyond tolerance.")
        minimum_eigenvalue = min(minimum_eigenvalue, eigenvalue)
        reciprocity = max(reciprocity, float(np.max(np.abs(normalized-normalized.T))))
    return np.asarray(frequencies), ids, z, {
        "sampled_passivity": "within_tolerance", "normalized_minimum_eigenvalue": minimum_eigenvalue,
        "passivity_tolerance": PASSIVITY_TOLERANCE, "maximum_reciprocity_residual": reciprocity,
        "causality": "not_evaluated"}


def _admit(request):
    _keys(request, "contract board_occurrence_id reference_return frequencies_hz ports z_ohm loads candidates "
          "dc_voltage_v target_impedance_ohm frequency_band_hz provenance", "placement request")
    _require(request["contract"] == REQUEST_CONTRACT, "contract", "Unsupported capacitor placement contract.")
    board = _text(request["board_occurrence_id"], "board occurrence")
    reference = request["reference_return"]
    _keys(reference, "occurrence_id net", "reference return")
    _require(reference["occurrence_id"] == board, "return_binding", "Reference return must belong to the same board occurrence.")
    _text(reference["net"], "return net")
    _keys(request["provenance"], "source_id conditions", "provenance")
    for key, value in request["provenance"].items():
        _text(value, key)
    frequency, ids, z, diagnostics = _network(request, board)
    loads, load_indices, amplitudes = [], [], []
    for load in _list(request["loads"], "loads", MAX_PORTS):
        _keys(load, "port_id current_a_rms", "load")
        port = _text(load["port_id"], "load port")
        _require(port in ids and port not in loads, "load_port", "Each load must name a distinct declared port.")
        loads.append(port)
        load_indices.append(ids.index(port))
        amplitude = _number(load["current_a_rms"], "load current", positive=True)
        _require(amplitude <= 1e6, "numeric_range", "Load ripple current exceeds 1e6 A RMS.")
        amplitudes.append(amplitude)
    candidates = _list(request["candidates"], "candidates", MAX_CANDIDATES)
    _require(len(candidates)*len(frequency)*len(loads) <= MAX_OUTPUT_POINTS,
             "resource_budget", "Candidate/frequency/load product exceeds 131072.")
    parsed, seen = [], set()
    for candidate in candidates:
        _keys(candidate, "id port_id occurrence_id x_mm y_mm capacitor", "candidate")
        identity = _text(candidate["id"], "candidate id")
        _require(identity not in seen, "duplicate_candidate", "Candidate IDs must be unique.")
        seen.add(identity)
        port = _text(candidate["port_id"], "candidate port")
        _require(port in ids and candidate["occurrence_id"] == board,
                 "candidate_binding", "Each candidate must bind a port on the declared board occurrence.")
        cap = candidate["capacitor"]
        _keys(cap, "capacitance_f esr_ohm esl_h voltage_rating_v ripple_current_rating_a_rms", "capacitor")
        cap = {key: _number(value, key, positive=key not in ("esr_ohm", "esl_h")) for key, value in cap.items()}
        _require(1e-18 <= cap["capacitance_f"] <= 1e3 and cap["esl_h"] <= 1e3 and cap["esr_ohm"] <= 1e12,
                 "numeric_range", "Capacitor values exceed the bounded SI envelope.")
        parsed.append({"id": identity, "port_id": port, "occurrence_id": board,
                       "x_mm": _number(candidate["x_mm"], "x_mm", -1e6),
                       "y_mm": _number(candidate["y_mm"], "y_mm", -1e6),
                       "capacitor": cap, "index": ids.index(port)})
        _require(max(abs(parsed[-1]["x_mm"]), abs(parsed[-1]["y_mm"])) <= 1e6,
                 "numeric_range", "Candidate coordinates exceed +/-1e6 mm.")
    dc = _number(request["dc_voltage_v"], "DC voltage", -1e6)
    _require(abs(dc) <= 1e6, "numeric_range", "DC voltage exceeds +/-1e6 V.")
    target = _number(request["target_impedance_ohm"], "target impedance", positive=True)
    _require(1e-15 <= target <= 1e12, "numeric_range", "Target impedance must be in [1e-15, 1e12] ohm.")
    band = [_number(v, "band edge", positive=True) for v in _list(request["frequency_band_hz"], "band", 2, 2)]
    mask = (frequency >= band[0]) & (frequency <= band[1])
    _require(frequency[0] <= band[0] < band[1] <= frequency[-1] and np.count_nonzero(mask) >= 2,
             "frequency_band", "Band must lie within the supplied sweep and contain at least two samples.")
    return frequency, z, loads, load_indices, np.asarray(amplitudes), parsed, dc, target, mask, diagnostics


def _curve(frequency, diagonal, target):
    magnitude = np.abs(diagonal)
    _require(np.all(np.isfinite(magnitude)), "numeric_range", "Impedance response is nonfinite.")
    return {"frequency_hz": float(frequency), "status": "computed",
            "load_impedance_ohm": [[float(v.real), float(v.imag)] for v in diagonal],
            "load_impedance_magnitude_ohm": magnitude.tolist(),
            "maximum_impedance_ohm": float(np.max(magnitude)),
            "maximum_target_ratio": float(np.max(magnitude)/target)}


def _summary(samples, mask):
    selected = [sample for sample, admitted in zip(samples, mask) if admitted]
    worst = max(selected, key=lambda item: item["maximum_target_ratio"])
    return {"worst_target_ratio": worst["maximum_target_ratio"],
            "peak_impedance_ohm": worst["maximum_impedance_ohm"],
            "peak_frequency_hz": worst["frequency_hz"],
            "meets_sampled_target": worst["maximum_target_ratio"] <= 1}


def _candidate(candidate, frequencies, z, indices, amplitudes, dc, target, mask, baseline_ratio):
    c = candidate["index"]
    cap = candidate["capacitor"]
    samples, issues, max_current, max_voltage, max_loss = [], [], 0., abs(dc), 0.
    for frequency, matrix in zip(frequencies, z):
        omega = 2*math.pi*float(frequency)
        zcap = complex(cap["esr_ohm"], omega*cap["esl_h"]-1/(omega*cap["capacitance_f"]))
        denominator = matrix[c, c]+zcap
        margin = abs(denominator)/max(abs(matrix[c, c]), abs(zcap), 1e-300)
        if margin <= DENOMINATOR_TOLERANCE:
            issues.append("ill_conditioned_shunt_resonance")
            samples.append({"frequency_hz": float(frequency), "status": "ill_conditioned_shunt_resonance",
                            "denominator_relative_margin": float(margin)})
            continue
        # Preserve both transfer directions; a reciprocal assumption is unnecessary.
        correction = matrix[indices, c]*matrix[c, indices]/denominator
        diagonal = matrix[indices, indices] - correction
        # At the mounted port use the parallel-product form to avoid catastrophic
        # cancellation for a capacitor approaching an ideal shunt short.
        for position, index in enumerate(indices):
            if index == c:
                diagonal[position] = matrix[c, c]*zcap/denominator
            else:
                scale = max(abs(matrix[index, index]), abs(correction[position]))
                if scale > 0 and abs(diagonal[position])/scale < 1e-12:
                    issues.append("ill_conditioned_update")
        if np.any(diagonal.real < -PASSIVITY_TOLERANCE*np.maximum(abs(diagonal), 1e-300)):
            issues.append("nonpassive_loaded_impedance")
        current = matrix[c, indices]/denominator*amplitudes
        terminal_voltage = current*zcap
        dielectric_voltage = abs(current)/(omega*cap["capacitance_f"])
        required_rating = abs(dc)+math.sqrt(2)*np.maximum(abs(terminal_voltage), dielectric_voltage)
        loss = abs(current)**2*cap["esr_ohm"]
        _require(np.all(np.isfinite(required_rating)) and np.all(np.isfinite(loss)),
                 "numeric_range", "Capacitor voltage/current/loss response is nonfinite.")
        max_current = max(max_current, float(np.max(abs(current))))
        max_voltage = max(max_voltage, float(np.max(required_rating)))
        max_loss = max(max_loss, float(np.max(loss)))
        sample = _curve(frequency, diagonal, target)
        sample.update(capacitor_current_a_rms=abs(current).tolist(),
                      capacitor_terminal_voltage_v_rms=abs(terminal_voltage).tolist(),
                      capacitor_dielectric_voltage_v_rms=dielectric_voltage.tolist(),
                      denominator_relative_margin=float(margin))
        samples.append(sample)
    if max_voltage > cap["voltage_rating_v"]:
        issues.append("capacitor_voltage_rating")
    if max_current > cap["ripple_current_rating_a_rms"]:
        issues.append("capacitor_ripple_current_rating")
    complete = all(sample["status"] == "computed" for sample in samples)
    summary = _summary(samples, mask) if complete else {
        "worst_target_ratio": None, "peak_impedance_ohm": None,
        "peak_frequency_hz": None, "meets_sampled_target": False}
    ratio = summary["worst_target_ratio"]
    return {key: value for key, value in candidate.items() if key != "index"} | {
        "status": "computed" if complete else "incomplete", "eligible": complete and not issues,
        "issues": sorted(set(issues)), "samples": samples, **summary,
        "color_metric": ratio, "color_metric_name": "worst_sampled_target_ratio_lower_is_better",
        "improvement_fraction": 1-ratio/baseline_ratio if ratio is not None and baseline_ratio > 0 else None,
        "maximum_capacitor_current_a_rms": max_current if complete else None,
        "required_voltage_rating_v": max_voltage if complete else None,
        "maximum_capacitor_esr_loss_w": max_loss if complete else None}


def evaluate_capacitor_placement(request):
    """Compare one added capacitor at a time; no implicit frequency interpolation."""
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _evaluate(request)
    except (OverflowError, FloatingPointError, ZeroDivisionError, np.linalg.LinAlgError) as exc:
        raise CapacitorPlacementError("numeric_range", "Network arithmetic or eigensolve exceeded its finite domain.") from exc


def _evaluate(request):
    frequency, z, loads, indices, amplitudes, candidates, dc, target, mask, diagnostics = _admit(request)
    baseline_samples = [_curve(f, matrix[indices, indices], target) for f, matrix in zip(frequency, z)]
    baseline = {"samples": baseline_samples, **_summary(baseline_samples, mask)}
    compared = [_candidate(c, frequency, z, indices, amplitudes, dc, target, mask,
                           baseline["worst_target_ratio"]) for c in candidates]
    ranked = sorted((c for c in compared if c["eligible"]), key=lambda c: (c["worst_target_ratio"], c["id"]))
    best = ranked[0] if ranked else None
    return {"contract": RESULT_CONTRACT, "model_status": "approximate", "status": "completed",
            "board_occurrence_id": request["board_occurrence_id"],
            "reference_return": dict(request["reference_return"]), "load_port_ids": loads,
            "frequency_band_hz": list(request["frequency_band_hz"]), "target_impedance_ohm": target,
            "baseline": baseline, "candidates": compared, "ranked_candidate_ids": [c["id"] for c in ranked],
            "best_candidate_id": best["id"] if best else None,
            "recommended_candidate_id": best["id"] if best and best["worst_target_ratio"] < baseline["worst_target_ratio"] else None,
            "network_diagnostics": diagnostics, "provenance": dict(request["provenance"]),
            "request_snapshot": deepcopy(request),
            "limitations": [
                "Best means best eligible supplied single-capacitor candidate at supplied frequencies, not a global spatial optimum.",
                "XY locations label supplied network ports; geometry, mounting/return inductance and board membership are not extracted.",
                "All ports share the declared return. Existing sources/loads must already have their intended small-signal boundary conditions.",
                "Sampled passivity does not prove broadband passivity, causality, mesh convergence or hardware accuracy.",
                "No interpolation or unsampled resonance search; refine the supplied network sweep before trusting peak or target coverage.",
                "Each load is a separate single-tone RMS scenario, not simultaneous loads or a summed harmonic spectrum.",
                "C/ESR/ESL and ratings are supplied operating values; DC bias, temperature, tolerance and aging are not inferred.",
                "Voltage screening uses DC plus the larger terminal/dielectric sinusoidal peak; ripple rating uses the worst supplied tone.",
                "No converter control stability, large-signal switching, insulation/clearance, busbar current capacity or high-power qualification."]}
