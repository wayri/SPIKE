# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Fail-closed frozen-worker probe for the bundled experimental native CHT case."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REQUEST = "spike/native-cht-request/v1"
RESULT = "spike/native-cht-result/v1"
METHOD = "run_native_cht"


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _probe_request(**changes):
    return {"contract": REQUEST, "n": 8, "length_m": 1., "span_m": 1.,
            "lid_velocity_m_s": 0., "solid_conductivity_w_mk": .1,
            "fluid_conductivity_w_mk": .01, "hot_temperature_k": 310.,
            "cold_temperature_k": 300., "thermal_tolerance": 1e-10, **changes}


def verify_native_cht_runtime(executable, request):
    """Verify discovery and actual execution through a freshly frozen worker."""
    worker = Path(executable).resolve()
    _require(worker.is_file(), "Frozen worker executable is unavailable")
    catalog_response = request(worker, "cfd_capabilities", {})
    _require(isinstance(catalog_response, dict) and catalog_response.get("ok") is True,
             "Packaged native CHT catalog request failed")
    catalog = catalog_response.get("result")
    _require(isinstance(catalog, dict) and isinstance(catalog.get("engines"), dict),
             "Packaged native CHT catalog result is malformed")
    engine = catalog["engines"].get("spike.native_cht")
    _require(isinstance(engine, dict), "Packaged native CHT capability is malformed")
    _require(engine.get("available") is True
             and engine.get("contract") == REQUEST
             and engine.get("model_status") == "experimental"
             and engine.get("geometry") == "2d_square_cavity_between_two_solid_slabs"
             and engine.get("flow") == "constant_property_incompressible_laminar"
             and engine.get("thermal") is True
             and engine.get("conjugate_interfaces") is True,
             "Packaged native CHT capability is absent or incompatible")
    _require(engine.get("production_qualified") is False
             and engine.get("turbulence") is False
             and engine.get("assembly_geometry") is False
             and catalog.get("production_qualified") is False
             and catalog.get("assembly_cht_supported") is False,
             "Packaged native CHT capability was incorrectly promoted")
    native = Path(engine.get("executable", "")).resolve()
    _require(native.is_file() and native.parent == worker.parent / "_internal" / "native",
             "Packaged native CHT executable is outside the worker artifact")
    expected_name = "spike_native_cht.exe" if native.suffix.lower() == ".exe" else "spike_native_cht"
    _require(native.name == expected_name, "Packaged native CHT executable has an unexpected name")
    binary_sha256 = _sha256(native)

    supplied = _probe_request()
    response = request(worker, METHOD, {"request": supplied})
    _require(isinstance(response, dict) and response.get("ok") is True,
             "Packaged native CHT execution request failed")
    result = response.get("result")
    _require(isinstance(result, dict), "Packaged native CHT result is malformed")
    _require(result.get("contract") == RESULT and result.get("status") == "converged"
             and result.get("model_status") == "experimental"
             and result.get("production_qualified") is False,
             "Packaged native CHT result is malformed, incomplete, or promoted")
    _require(_sha256(native) == binary_sha256
             and result.get("provenance", {}).get("executable_sha256") == binary_sha256,
             "Packaged native CHT binary identity changed or was not retained")
    temperatures = result.get("fields", {}).get("thermal", {}).get("temperature_k")
    _require(isinstance(temperatures, list) and len(temperatures) == 96
             and all(type(value) in (int, float) and math.isfinite(value)
                     and 300. - 1e-7 <= value <= 310. + 1e-7 for value in temperatures),
             "Packaged native CHT returned invalid retained temperatures")
    expected_heat = 10. / (.5 / .1 + 1. / .01)
    diagnostics = result.get("diagnostics")
    _require(isinstance(diagnostics, dict), "Packaged native CHT diagnostics are malformed")
    interfaces = result.get("interfaces")
    _require(isinstance(interfaces, dict) and set(interfaces) == {"bottom", "top"},
             "Packaged native CHT omitted conjugate interfaces")
    flows = diagnostics.get("interface_heat_flow_w")
    _require(isinstance(flows, dict) and set(flows) == {"bottom", "top"}
             and all(type(value) in (int, float) and math.isfinite(value)
                     and math.isclose(value, expected_heat, rel_tol=0., abs_tol=1e-9)
                     for value in flows.values())
             and math.isclose(diagnostics.get("hot_input_w", math.nan), expected_heat,
                              rel_tol=0., abs_tol=1e-9)
             and math.isclose(diagnostics.get("cold_output_w", math.nan), expected_heat,
                              rel_tol=0., abs_tol=1e-9),
             "Packaged native CHT differs from the independent series-resistance oracle")

    failed_response = request(worker, METHOD, {"request": _probe_request(max_thermal_iterations=1)})
    failed = failed_response.get("result") if isinstance(failed_response, dict) else None
    _require(isinstance(failed_response, dict) and failed_response.get("ok") is True
             and isinstance(failed, dict) and failed.get("contract") == RESULT
             and failed.get("status") == "failed_to_converge"
             and failed.get("model_status") == "experimental"
             and failed.get("production_qualified") is False
             and failed.get("fields") is None and failed.get("interfaces") is None,
             "Packaged native CHT published partial fields for an incomplete solve")
    _require(_sha256(native) == binary_sha256
             and failed.get("provenance", {}).get("executable_sha256") == binary_sha256,
             "Packaged native CHT binary identity changed during failure-path execution")
    return {"status": "passed", "production_qualified": False, "method": METHOD,
            "request_contract": REQUEST, "result_contract": RESULT,
            "native_binary_sha256": binary_sha256, "conduction_heat_w": expected_heat,
            "incomplete_status": "failed_to_converge",
            "scope": "Frozen-runtime square-cavity/slab packaging oracle; not assembly or production CHT qualification"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from scripts.build_packaged_worker import _request
    report = verify_native_cht_runtime(args.worker, _request)
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps(report, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
