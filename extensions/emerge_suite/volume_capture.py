# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Capture solved EMerge public E/H fields at owned volume/face quadrature.

No field normalization is assumed. The body-heating consumer independently
requires Poynting/loss closure and calibrates to a specified physical AC port.
"""
import numpy as np

from python.spike_core.em_body_heating import field_quadrature
from python.spike_core.em_network_ac import _digest


def capture_volume_fields(field, thermal_request, *, frequency_hz, loss_materials,
                          ac_source, port_faces, solver_run_digest):
    geometry = field_quadrature(thermal_request)
    def capture(points):
        points = np.asarray(points)
        solved = field.interpolate(points[:, 0], points[:, 1], points[:, 2], usenan=True)
        e = np.stack([solved.Ex, solved.Ey, solved.Ez], axis=1)
        h = np.stack([solved.Hx, solved.Hy, solved.Hz], axis=1)
        if (e.shape != (len(points), 3) or h.shape != e.shape or
                not np.isfinite(e).all() or not np.isfinite(h).all()):
            raise ValueError("EMERGE_VOLUME_CAPTURE: Missing/nonfinite solved samples; no zero fill or geometry shift")
        return {"e": np.stack([e.real, e.imag], axis=2).tolist(),
                "h": np.stack([h.real, h.imag], axis=2).tolist()}
    return {"context": {"frequency_hz": frequency_hz, "mesh_digest": _digest(thermal_request["mesh"]),
                "loss_materials_digest": _digest(loss_materials), "ac_source_digest": _digest(ac_source),
                "port_faces_digest": _digest(sorted(port_faces)), "solver_run_digest": solver_run_digest},
            "cells": {key: capture(rule["points_m"])["e"] for key, rule in geometry["cells"].items()},
            "boundary_faces": {key: capture(rule["points_m"]) for key, rule in geometry["boundary_faces"].items()}}
