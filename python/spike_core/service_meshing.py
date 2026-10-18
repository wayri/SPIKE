# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Internal meshing worker methods, separate from external CAD mesh adapters."""
from .internal_meshing_engine import internal_mesh_capabilities, run_internal_meshing
from .service_helpers import error_response, operation_id


def handle_meshing_request(method, params, *, request_id=None):
    if method in {"import_sheet_definition", "preview_sheet_fold"}:
        from .service_sheet_folding import handle_sheet_folding_request
        return handle_sheet_folding_request(method, params)
    if method not in {"internal_mesh_capabilities", "run_internal_meshing", "prepare_pcb_volume_mesh",
                      "pcb_volume_mesh_capabilities"}:
        return None
    try:
        if not isinstance(params, dict):
            raise ValueError("Mesh worker parameters must be an object.")
        if method in {"internal_mesh_capabilities", "pcb_volume_mesh_capabilities"}:
            if params:
                raise ValueError("Mesh capability probe takes no parameters.")
            if method == "internal_mesh_capabilities":
                result = internal_mesh_capabilities()
            else:
                from .pcb_volume_mesh import pcb_volume_mesh_capabilities
                result = pcb_volume_mesh_capabilities()
        elif method == "prepare_pcb_volume_mesh":
            if set(params) != {"request"}:
                raise ValueError("PCB mesh worker accepts only a versioned request.")
            from .pcb_volume_mesh import prepare_pcb_volume_mesh
            result = prepare_pcb_volume_mesh(params["request"])
        else:
            if set(params) != {"request"}:
                raise ValueError("Mesh worker accepts only a versioned request.")
            result = run_internal_meshing(params["request"])
    except (ValueError, TypeError, OverflowError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001", "The internal meshing request is invalid.",
                              operation_id=operation_id(request_id), detail=str(exc),
                              context={"method": method, "boundary": "internal_meshing"},
                              error_type=type(exc).__name__)
    return {"ok": True, "result": result}
