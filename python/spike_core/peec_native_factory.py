# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Native PEEC filament setup and dielectric defaults at the Python boundary."""

from __future__ import annotations

from typing import Any

from .contracts import AnalysisSpec, DesignIR
from .hybrid_mesh import HybridMesh


def make_native_solver(native: Any, mesh: HybridMesh, epsilon_r: float,
                       spec: AnalysisSpec | None = None) -> tuple[Any, Any]:
    config = native.PEECConfig()
    config.eps_r = epsilon_r
    conductor = spec.options.get("conductor_models", {}) if spec is not None else {}
    config.enable_skin_effect = bool(conductor.get("skin_effect", True))
    roughness_model = str(conductor.get("surface_roughness_model", "none")).lower()
    config.enable_hammerstad_roughness = roughness_model == "hammerstad"
    config.roughness_rms_um = max(float(conductor.get("rms_roughness_um", 0.0)), 0.0)
    solver = native.PEECSolver(config)
    for branch in mesh.branches:
        filament = native.Filament()
        filament.start = native.Point3D(*branch.start_mm)
        filament.end = native.Point3D(*branch.end_mm)
        filament.width = branch.width_mm
        filament.thickness = branch.thickness_mm
        filament.node_p = branch.node_p
        filament.node_n = branch.node_n
        filament.conductivity = branch.conductivity_s_m
        solver.add_filament(filament)
    return solver, config


def dielectric_epsilon(design: DesignIR) -> float:
    values = [
        float(layer.get("epsilon_r", layer.get("epsilonR")))
        for layer in design.stackup
        if not str(layer.get("name", "")).endswith(".Cu")
        and (layer.get("epsilon_r") is not None or layer.get("epsilonR") is not None)
    ]
    return sum(values) / len(values) if values else 4.2
