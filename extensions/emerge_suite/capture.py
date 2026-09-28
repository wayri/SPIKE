# SPDX-License-Identifier: Apache-2.0
"""Small adapters for arrays returned by EMerge's public microwave API.

Call these after the engineer has built, meshed, and run an EMerge simulation.
They do not generate geometry, ports, meshes, or a radiation boundary.
"""

from __future__ import annotations

import math


def _pair(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _electric_farfield(value: object):
    """Read EMerge 2.8 tuples or 3.0 EHFieldFF public Cartesian samples."""
    import numpy as np

    if isinstance(value, tuple) and len(value) == 3:
        return np.asarray(value[0])
    if all(hasattr(value, axis) for axis in ("Ex", "Ey", "Ez")):
        return np.stack([value.Ex, value.Ey, value.Ez], axis=0)
    raise ValueError("EMerge returned an unsupported far-field format.")


def s_parameters(data: object, port_names: list[str], reference_impedance_ohm: float) -> dict:
    """Capture *solved* frequencies via grid.S, without vector-fit interpolation."""
    grid = data.scalar.grid
    frequencies = [float(value) for value in grid.freq]
    matrices = []
    for index in range(len(frequencies)):
        matrices.append([[_pair(grid.S(receive + 1, excited + 1)[index])
                          for excited in range(len(port_names))]
                         for receive in range(len(port_names))])
    return {"frequencies_hz": frequencies, "ports": list(port_names),
            "reference_impedance_ohm": reference_impedance_ohm, "values": matrices}


def theta_cut(field: object, faces: object, frequency_hz: float,
              angles_deg: list[float], *, phi_deg: float = 0.0,
              origin: tuple[float, float, float] | None = None) -> dict:
    """Project EMerge's Cartesian far field onto spherical theta/phi axes.

    EMerge takes radians. Projection uses the standard right-handed spherical
    basis: e_theta=(cos(t)cos(p),cos(t)sin(p),-sin(t)),
    e_phi=(-sin(p),cos(p),0). Input coordinates follow the model's units.
    """
    import numpy as np

    theta = np.asarray([math.radians(float(value)) for value in angles_deg])
    phi = np.full(theta.shape, math.radians(float(phi_deg)))
    electric = _electric_farfield(field.farfield(theta, phi, faces, origin=origin))
    e_theta = []
    e_phi = []
    for index, angle in enumerate(theta):
        ex, ey, ez = (electric[component, index] for component in range(3))
        e_theta.append(_pair(ex * math.cos(angle) * math.cos(phi[index])
                             + ey * math.cos(angle) * math.sin(phi[index])
                             - ez * math.sin(angle)))
        e_phi.append(_pair(-ex * math.sin(phi[index]) + ey * math.cos(phi[index])))
    return {"frequency_hz": float(frequency_hz), "angles_deg": list(angles_deg),
            "e_theta_v_m": e_theta, "e_phi_v_m": e_phi}


def sphere_pattern(field: object, faces: object, frequency_hz: float,
                   theta_deg: list[float], phi_deg: list[float],
                   *, origin: tuple[float, float, float] | None = None) -> dict:
    """Capture solved spherical field samples, theta-major and phi-minor.

    The sampled surface is intentionally coarse and is a visualization of the
    far field returned by EMerge, not an interpolated solver result.
    """
    import numpy as np

    theta = np.asarray([math.radians(t) for t in theta_deg for _ in phi_deg])
    phi = np.asarray([math.radians(p) for _ in theta_deg for p in phi_deg])
    electric = _electric_farfield(field.farfield(theta, phi, faces, origin=origin))
    cos_theta, sin_theta = np.cos(theta), np.sin(theta)
    cos_phi, sin_phi = np.cos(phi), np.sin(phi)
    e_theta = electric[0] * cos_theta * cos_phi + electric[1] * cos_theta * sin_phi - electric[2] * sin_theta
    e_phi = -electric[0] * sin_phi + electric[1] * cos_phi
    return {"frequency_hz": float(frequency_hz), "theta_deg": list(theta_deg),
            "phi_deg": list(phi_deg),
            "e_theta_v_m": [_pair(value) for value in e_theta],
            "e_phi_v_m": [_pair(value) for value in e_phi]}
