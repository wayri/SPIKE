# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Select the requested PEEC capacitance approximation at the worker boundary."""
from __future__ import annotations

from typing import Any, Sequence

from .contracts import AnalysisSpec, DesignIR
from .quasistatic_capacitance import zone_pad_mesh_dependence_issue


def estimate_branch_capacitance(design: DesignIR, spec: AnalysisSpec,
                                branches: Sequence[Any]):
    if spec.options.get("peec_volume_extraction") == "enabled":
        from .quasistatic_copper_area import estimate_branch_capacitance as estimator
    else:
        from .quasistatic_capacitance import estimate_branch_capacitance as estimator
    return estimator(design, spec, branches)
