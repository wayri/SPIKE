# SPDX-License-Identifier: Apache-2.0
"""Bound and label numerical data returned by an engineer's EMerge model."""

from __future__ import annotations

import math


MAX_FREQUENCIES = 512
MAX_PATTERN_SAMPLES = 100_000
MAX_PORTS = 32


def _relative_db(magnitudes: list[float]) -> tuple[list[float], int]:
    if not all(math.isfinite(value) for value in magnitudes):
        raise ValueError("Radiation field amplitude exceeds the finite range.")
    peak = max(magnitudes)
    return ([20 * math.log10(value / peak) if value > 0 and peak > 0 else -300.0
             for value in magnitudes], magnitudes.index(peak))


def _number(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite.")
    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError(f"{label} must be finite.") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    if positive and number <= 0:
        raise ValueError(f"{label} must be positive.")
    return number


def _complex(value: object, label: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} must be a [real, imaginary] pair.")
    return [_number(value[0], label), _number(value[1], label)]


def _frequencies(value: object) -> list[float]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_FREQUENCIES:
        raise ValueError("frequencies_hz must contain 1 to 512 samples.")
    frequencies = [_number(item, "frequency_hz", positive=True) for item in value]
    if any(a >= b for a, b in zip(frequencies, frequencies[1:])):
        raise ValueError("frequencies_hz must be strictly increasing.")
    return frequencies


def radiation(raw: object) -> tuple[dict, dict]:
    """Keep complex field samples and derive only relative amplitude in dB."""
    if not isinstance(raw, dict):
        raise ValueError("radiation must be an object.")
    frequencies = _frequencies(raw.get("frequencies_hz"))
    cuts = raw.get("cuts")
    if not isinstance(cuts, list) or len(cuts) != len(frequencies):
        raise ValueError("radiation.cuts needs one cut per frequency.")
    normalized = []
    count = 0
    for frequency, cut in zip(frequencies, cuts):
        if not isinstance(cut, dict) or _number(cut.get("frequency_hz"), "cut frequency") != frequency:
            raise ValueError("Radiation cut frequency does not match the sweep.")
        angles = cut.get("angles_deg")
        etheta = cut.get("e_theta_v_m")
        ephi = cut.get("e_phi_v_m")
        if not isinstance(angles, list) or not 2 <= len(angles) <= MAX_PATTERN_SAMPLES:
            raise ValueError("Radiation cut needs 2 to 100000 angles.")
        if not isinstance(etheta, list) or not isinstance(ephi, list) or len(etheta) != len(angles) or len(ephi) != len(angles):
            raise ValueError("Radiation field arrays must match angle count.")
        count += len(angles)
        if count > MAX_PATTERN_SAMPLES:
            raise ValueError("Radiation result exceeds 100000 angular samples.")
        angles = [_number(item, "angle_deg") for item in angles]
        if any(a >= b for a, b in zip(angles, angles[1:])):
            raise ValueError("Radiation angles must be strictly increasing.")
        etheta = [_complex(value, "E_theta") for value in etheta]
        ephi = [_complex(value, "E_phi") for value in ephi]
        magnitudes = [math.hypot(*a, *b) for a, b in zip(etheta, ephi)]
        relative_db, peak_index = _relative_db(magnitudes)
        normalized.append({"frequency_hz": frequency, "angles_deg": angles,
                           "e_theta_v_m": etheta, "e_phi_v_m": ephi,
                           "relative_amplitude_db": relative_db,
                           "peak_angle_deg": angles[peak_index]})
    patterns = raw.get("patterns_3d")
    normalized_patterns = []
    if patterns is not None:
        if not isinstance(patterns, list) or len(patterns) != len(frequencies):
            raise ValueError("radiation.patterns_3d needs one pattern per frequency.")
        for frequency, pattern in zip(frequencies, patterns):
            if not isinstance(pattern, dict) or _number(pattern.get("frequency_hz"), "pattern frequency") != frequency:
                raise ValueError("3D radiation pattern frequency does not match the sweep.")
            theta = pattern.get("theta_deg")
            phi = pattern.get("phi_deg")
            if not isinstance(theta, list) or not isinstance(phi, list) or len(theta) < 3 or len(phi) < 4:
                raise ValueError("3D radiation pattern needs theta and phi grids.")
            size = len(theta) * len(phi)
            count += size
            if count > MAX_PATTERN_SAMPLES:
                raise ValueError("Radiation result exceeds 100000 angular samples.")
            theta = [_number(value, "theta_deg") for value in theta]
            phi = [_number(value, "phi_deg") for value in phi]
            if (theta[0] != 0 or theta[-1] != 180 or phi[0] != 0 or phi[-1] != 360
                    or any(a >= b for a, b in zip(theta, theta[1:]))
                    or any(a >= b for a, b in zip(phi, phi[1:]))):
                raise ValueError("3D radiation grid must increase from theta 0..180 and phi 0..360 degrees.")
            etheta = pattern.get("e_theta_v_m")
            ephi = pattern.get("e_phi_v_m")
            if not isinstance(etheta, list) or not isinstance(ephi, list) or len(etheta) != size or len(ephi) != size:
                raise ValueError("3D radiation field arrays must match the angular grid.")
            etheta = [_complex(value, "3D E_theta") for value in etheta]
            ephi = [_complex(value, "3D E_phi") for value in ephi]
            relative_db, peak_index = _relative_db([math.hypot(*a, *b) for a, b in zip(etheta, ephi)])
            normalized_patterns.append({"frequency_hz": frequency, "theta_deg": theta,
                                        "phi_deg": phi, "e_theta_v_m": etheta,
                                        "e_phi_v_m": ephi, "relative_amplitude_db": relative_db,
                                        "peak_direction_deg": [theta[peak_index // len(phi)],
                                                               phi[peak_index % len(phi)]]})
    return {"contract": "spike/emerge-radiation-cuts/v1", "frequencies_hz": frequencies,
            "cuts": normalized, "patterns_3d": normalized_patterns,
            "normalization": "each cut and sphere independently peak-normalized to 0 dB"}, {
                "cut_count": len(cuts), "pattern_count": len(normalized_patterns),
                "angular_sample_count": count}


def network(raw: object) -> tuple[dict, dict]:
    if not isinstance(raw, dict):
        raise ValueError("s_parameters must be an object.")
    frequencies = _frequencies(raw.get("frequencies_hz"))
    ports = raw.get("ports")
    values = raw.get("values")
    if not isinstance(ports, list) or not 1 <= len(ports) <= MAX_PORTS or any(not isinstance(p, str) or not p for p in ports) or len(set(ports)) != len(ports):
        raise ValueError("S-parameters need 1 to 32 uniquely named ports.")
    if not isinstance(values, list) or len(values) != len(frequencies):
        raise ValueError("S-parameter sweep must match frequencies.")
    if len(frequencies) * len(ports) ** 2 > MAX_PATTERN_SAMPLES:
        raise ValueError("S-parameter result exceeds 100000 complex values.")
    samples = []
    for matrix in values:
        if not isinstance(matrix, list) or len(matrix) != len(ports):
            raise ValueError("Each S-parameter matrix must be square.")
        rows = []
        for row in matrix:
            if not isinstance(row, list) or len(row) != len(ports):
                raise ValueError("Each S-parameter matrix must be square.")
            rows.append([_complex(value, "S-parameter") for value in row])
        samples.append(rows)
    z0 = _number(raw.get("reference_impedance_ohm"), "reference_impedance_ohm", positive=True)
    return {"contract": "spike/emerge-s-parameters/v1", "frequencies_hz": frequencies,
            "ports": ports, "reference_impedance_ohm": z0, "values": samples,
            "matrix_order": "values[frequency][receive_port][excited_port]"}, {
                "frequency_count": len(frequencies), "port_count": len(ports)}
