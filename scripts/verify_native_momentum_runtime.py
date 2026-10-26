# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Require actual moving-lid momentum admission in a frozen JSON-line worker."""
import math
from pathlib import Path

from scripts.verify_native_cht_runtime import REQUEST, RESULT, _require, _sha256


def verify_native_momentum_runtime(executable, request):
    worker = Path(executable).resolve(strict=True)
    response = request(worker, "cfd_capabilities", {})
    catalog = response.get("result") if isinstance(response, dict) else None
    _require(isinstance(response, dict) and response.get("ok") is True
             and isinstance(catalog, dict) and isinstance(catalog.get("engines"), dict),
             "Moving-lid capability catalog is malformed")
    engine = catalog["engines"].get("spike.native_cht")
    _require(isinstance(engine, dict) and engine.get("available") is True
             and isinstance(engine.get("executable"), str), "Moving-lid kernel unavailable")
    native = Path(engine["executable"]).resolve(strict=True)
    _require(native.parent == worker.parent / "_internal" / "native"
             and native.name in {"spike_native_cht", "spike_native_cht.exe"},
             "Moving-lid kernel escapes worker artifact")
    digest = _sha256(native)
    supplied = {"contract": REQUEST, "n": 8, "lid_velocity_m_s": 1.,
                "hot_temperature_k": 300., "cold_temperature_k": 300.}
    response = request(worker, "run_native_cht", {"request": supplied})
    result = response.get("result") if isinstance(response, dict) else None
    _require(isinstance(response, dict) and response.get("ok") is True
             and isinstance(result, dict) and result.get("contract") == RESULT
             and result.get("status") == "converged"
             and result.get("model_status") == "experimental"
             and result.get("production_qualified") is False,
             "Moving-lid execution did not converge without promotion")
    settings, scales = result.get("settings"), result.get("scales")
    _require(isinstance(settings, dict) and settings.get("n") == 8
             and settings.get("lid_velocity_m_s") == 1.
             and isinstance(scales, dict) and scales.get("actual_reynolds") == 100.,
             "Moving-lid runtime returned a different operating case")
    diagnostics = result.get("diagnostics")
    _require(isinstance(diagnostics, dict)
             and diagnostics.get("independent_momentum_verified") is True
             and diagnostics.get("independent_momentum_arithmetic") == "exact_rational_binary_inputs",
             "Moving-lid independent momentum verification missing")
    residual = diagnostics.get("independent_momentum_residual_linf")
    limit = diagnostics.get("independent_momentum_residual_limit")
    _require(all(type(v) in (int, float) and math.isfinite(v) for v in (residual, limit))
             and 0 <= residual <= limit and limit > 0,
             "Moving-lid independent momentum residual exceeds its derived limit")
    fields = result.get("fields")
    fluid = fields.get("fluid") if isinstance(fields, dict) else None
    _require(isinstance(fluid, dict), "Moving-lid fluid fields missing")
    for key in ("u_m_s", "v_m_s", "gauge_pressure_pa"):
        values = fluid.get(key)
        _require(isinstance(values, list) and len(values) == 64
                 and all(type(v) in (int, float) and math.isfinite(v) for v in values),
                 "Moving-lid retained fluid field invalid")
    _require(any(value != 0 for value in fluid["u_m_s"]), "Moving lid returned zero flow")
    provenance = result.get("provenance")
    _require(_sha256(native) == digest and isinstance(provenance, dict)
             and provenance.get("executable_sha256") == digest,
             "Moving-lid native binary identity changed")
    return {"status": "passed", "production_qualified": False,
            "native_binary_sha256": digest, "n": 8, "reynolds": 100.,
            "independent_momentum_residual_linf": residual,
            "independent_momentum_residual_limit": limit,
            "scope": "Frozen-runtime discrete moving-lid momentum gate, not continuum or measured qualification"}
