# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Loaded driving-point impedance; sampled extrema are not qualified resonances."""
import numpy as np


def analyze_impedance(network, *, termination_ohm=None, ports=None, trace_limit=2048, cancel_check=None):
    """Other ports have explicit real resistor loads, matched by default.

    The selected driving port's load entry is not applied to itself. Wave
    elimination avoids singular open-circuit Z matrices for ideal throughs.
    """
    s = np.asarray(network.s_parameters(), dtype=complex)
    f = np.asarray(network.frequencies_hz, dtype=float)
    z = np.asarray(network.reference_impedance_ohm, dtype=float)
    n = network.port_count
    if not 1 <= n <= 16 or f.ndim != 1 or not 1 <= len(f) <= 8193 or s.shape != (len(f), n, n):
        raise ValueError("Impedance supports 1..16 ports, 1..8193 frequency samples")
    if not np.all(np.isfinite(s)) or not np.all(np.isfinite(f)) or np.any(f < 0) or np.any(np.diff(f) <= 0):
        raise ValueError("Finite matrices and strictly increasing nonnegative frequencies required")
    if z.shape != (n,) or not np.all(np.isfinite(z)) or np.any(z <= 0):
        raise ValueError("Positive finite real reference impedances required")
    requested = list(range(n)) if ports is None else ports
    if not isinstance(requested, (list, tuple)) or not requested or any(type(p) is not int or not 0 <= p < n for p in requested) or len(set(requested)) != len(requested):
        raise ValueError("ports must contain unique zero-based indices")
    if len(f) * len(requested) > 65536:
        raise ValueError("Impedance sample-port work budget exceeded")
    if type(trace_limit) is not int or not 16 <= trace_limit <= 16384:
        raise ValueError("trace_limit must be in 16..16384")
    if termination_ohm is None:
        loads = z.copy()
    else:
        if not isinstance(termination_ohm, (list, tuple)) or len(termination_ohm) != n or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 1e-6 <= v <= 1e12 for v in termination_ohm):
            raise ValueError("One real load per port within 1e-6..1e12 ohm required")
        loads = np.asarray(termination_ohm, dtype=float)
    gamma_load = (loads-z)/(loads+z)
    reports = []
    for port in requested:
        other = [i for i in range(n) if i != port]
        coupled_loads = bool(other) and bool(np.any(gamma_load[other] != 0))
        rows = []
        for k, matrix in enumerate(s):
            if cancel_check is not None and cancel_check():
                raise ValueError("Impedance analysis cancelled")
            reflection = matrix[port, port]
            row = {"frequency_hz": float(f[k]), "status": "finite", "real_ohm": None, "imag_ohm": None, "magnitude_ohm": None}
            if coupled_loads:
                gamma = gamma_load[other]
                boundary = np.eye(len(other)) - gamma[:, None]*matrix[np.ix_(other, other)]
                if np.linalg.cond(boundary) > 1e12:
                    row["status"] = "ill_conditioned_termination"
                    rows.append(row)
                    continue
                incident = np.linalg.solve(boundary, gamma*matrix[other, port])
                reflection += matrix[port, other] @ incident
            if abs(1-reflection) <= 1e-12 * max(1, abs(reflection)):
                row["status"] = "open_or_pole"
            else:
                impedance = z[port]*(1+reflection)/(1-reflection)
                if not np.isfinite(impedance):
                    row["status"] = "numerically_unresolved"
                else:
                    row.update(real_ohm=float(impedance.real), imag_ohm=float(impedance.imag), magnitude_ohm=float(abs(impedance)))
            rows.append(row)
        candidates = []
        for k in range(1, len(rows)-1):
            triple = rows[k-1:k+2]
            if not all(row["status"] == "finite" for row in triple):
                continue
            a,b,c = [row["magnitude_ohm"] for row in triple]
            kind = "sampled_magnitude_peak" if b > max(a,c) else "sampled_magnitude_dip" if b < min(a,c) else None
            if kind:
                candidates.append({"kind": kind, "sample_index": k, "frequency_hz": float(f[k]), "magnitude_ohm": b,
                    "bracket_hz": [float(f[k-1]),float(f[k+1])]})
        for k in range(len(rows)-1):
            a,b = rows[k:k+2]
            if a["status"] == b["status"] == "finite" and ((a["imag_ohm"] < 0 < b["imag_ohm"]) or (b["imag_ohm"] < 0 < a["imag_ohm"])):
                candidates.append({"kind": "reactance_sign_change", "sample_index": k, "bracket_hz": [float(f[k]),float(f[k+1])]})
        indices = np.unique(np.linspace(0,len(f)-1,min(len(f),trace_limit)).astype(int))
        displayed = []
        previous = -1
        for k in indices:
            displayed.append({**rows[k], "sample_index": int(k),
                "gap_before": any(row["status"] != "finite" for row in rows[previous+1:k])})
            previous = int(k)
        reports.append({"port": port, "trace": displayed,
            "invalid_samples": [{"sample_index": k, "frequency_hz": float(f[k]), "status": row["status"]} for k,row in enumerate(rows) if row["status"] != "finite"],
            "sampled_candidates": candidates[:128], "candidate_count": len(candidates), "candidate_output_truncated": len(candidates)>128})
    return {"contract": "spike/si-driving-point-impedance/v1", "status": "completed", "ports": reports,
        "termination_ohm": loads.tolist(), "termination_mode": "matched" if termination_ohm is None else "explicit_resistive",
        "definition": "Driving-point impedance with all OTHER ports terminated; selected port load is excluded",
        "production_qualified": False, "physical_resonance_qualified": False,
        "limitations": ["Sampled extrema and reactance sign changes are candidates only; no Q, fitted pole or physical resonance claim.",
            "Frequency spacing can miss narrow resonances; finite bandwidth limits conclusions.",
            "Open/pole and ill-conditioned samples are null and explicitly masked, never replaced by large finite values."]}


def network_impedance_report(network, *, trace_limit=2048, cancel_check=None):
    """Optional bounded matched-load report for generic network summaries."""
    ports, frequencies = network.port_count, len(network.frequencies_hz)
    if not 1 <= ports <= 16 or not 1 <= frequencies <= 8193 or ports*frequencies > 65536:
        return {"contract": "spike/si-driving-point-impedance/v1", "status": "unsupported_budget",
            "ports": [], "production_qualified": False, "physical_resonance_qualified": False,
            "reason": "Matched summary supports at most 16 ports, 8193 frequencies and 65536 port-frequency pairs"}
    return analyze_impedance(network, trace_limit=trace_limit, cancel_check=cancel_check)
