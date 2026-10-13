# SPDX-License-Identifier: Apache-2.0
"""Explicit lossless SpiDeR v2 admission for established v1-only worker APIs."""
from .spider_api import document_for_legacy_worker

LEGACY_DESIGN_METHODS = frozenset({
    "validate_design", "preview_mesh", "preflight_analysis", "mesh_convergence",
    "run_analysis", "run_preflighted_analysis", "emi_preflight", "emi_screen",
    "validate_spice_workspace", "compose_spice_workspace", "compile_spice_workspace_native_mna",
    "run_spice_workspace_native_mna", "validate_owned_spice_workspace", "run_owned_spice_workspace",
    "prepare_studio_board_context", "validate_studio_board_cosimulation", "run_studio_board_cosimulation",
    "extract_net_geometry", "extract_power_path",
})

def prepare_worker_design(request):
    """Detach only admitted v2 inputs; return (request, evidence, issue)."""
    if not isinstance(request, dict):
        return request, None, None
    params = request.get("params", {})
    document = params.get("design") if isinstance(params, dict) else None
    if request.get("method") not in LEGACY_DESIGN_METHODS or not isinstance(document, dict) or document.get("contract") != "spike/design-ir/v2":
        return request, None, None
    admitted = document_for_legacy_worker(document)
    if not admitted["ok"]:
        return request, admitted["report"], "SpiDeR v2 cannot be projected safely into this legacy worker operation"
    return {**request, "params": {**params, "design": admitted["document"]}}, admitted["report"], None


def dispatch_spider_request(request, dispatch):
    """Wrap a worker response without changing its solver-result contract."""
    from .service_helpers import error_response
    prepared, evidence, issue = prepare_worker_design(request)
    if issue:
        return error_response("SPIKE-BE-IPC-E-0001", issue, context={"spider": evidence}, error_type="SpiDeRProjectionError")
    response = dispatch(prepared)
    if evidence is not None:
        response = {**response, "meta": {**response.get("meta", {}), "spider": evidence}}
    return response
