# SPDX-License-Identifier: Apache-2.0
"""Neutral board identity and worker progress boundary for Studio feedback."""
from .contracts import SpiDeR
from .cosimulation import bounded_digest, identity
from .service_helpers import error_response, operation_id
from .spice_workspace import _safe_instance_name
from .studio_board_coupling import validate_studio_board_cosimulation, run_studio_board_cosimulation


def prepare_studio_board_context(design):
    normalized = SpiDeR(**design)
    if normalized.contract != "spike/v1" or normalized.units != "mm":
        raise ValueError("Expected neutral SPIKE design in mm")
    components, ids, refs = [], set(), set()
    if not isinstance(normalized.components,list):
        raise ValueError("Board components must be an array")
    for part in normalized.components:
        if not isinstance(part,dict):
            raise ValueError("Board component must be an object")
        reference = identity(part.get("reference") or part.get("ref"))
        identifier = identity(part.get("id") or reference)
        if identifier in ids or reference in refs:
            raise ValueError("Board component identities/references must be unique")
        ids.add(identifier); refs.add(reference)
        components.append({"id":identifier,"ref":reference,"reference":reference,
                           "element_id":_safe_instance_name("R",reference)})
    return {"contract":"spike/studio-board-context/v1","board_revision":bounded_digest(normalized.to_dict()),
            "components":components}


def handle_studio_board_cosimulation_request(method, params, *, request_id=None):
    if method not in {"prepare_studio_board_context","validate_studio_board_cosimulation","run_studio_board_cosimulation"}:
        return None
    try:
        expected = {"design"} if method == "prepare_studio_board_context" else {"design","request"}
        if not isinstance(params,dict) or set(params) != expected:
            raise ValueError("Unexpected/missing Studio board method fields")
        context = prepare_studio_board_context(params["design"])
        if method == "prepare_studio_board_context":
            return {"ok":True,"result":context}
        if not isinstance(params["request"],dict):
            raise ValueError("Coupling request must be an object")
        aliases = {p["id"]:p["element_id"] for p in context["components"]}
        for binding in params["request"].get("bindings",[]):
            if not isinstance(binding,dict) or aliases.get(binding.get("component_id")) != binding.get("element_id"):
                raise ValueError("Resistor binding disagrees with the board component's canonical Studio alias")
        binding_context={"board_revision":context["board_revision"],"component_ids":list(aliases)}
        if method.startswith("validate_"):
            result=validate_studio_board_cosimulation(params["request"],board_binding_context=binding_context)
        else:
            from .worker_progress import emit_worker_progress
            token=operation_id(request_id)
            result=run_studio_board_cosimulation(params["request"],board_binding_context=binding_context,
                progress=(lambda frame:emit_worker_progress(token,method,{"accepted_frame":frame})) if token else None)
        return {"ok":True,"result":result}
    except (ValueError,TypeError,KeyError,OverflowError,RuntimeError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001","Studio board coupling request is invalid.",
                              detail=str(exc),context={"method":method},error_type=type(exc).__name__)
