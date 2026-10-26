# SPDX-License-Identifier: Apache-2.0
"""Inert, bounded model-library discovery and explicit workspace import."""
from .service_helpers import error_response


def handle_model_library_request(method, params):
    if method not in {"inspect_spice_model_library", "import_spice_model"}:
        return None
    try:
        required = {"text", "name"}
        optional = set()
        if method == "import_spice_model":
            required.add("subcircuit_name")
            optional = {"source_locator", "license_note"}
        if not isinstance(params, dict) or not required <= set(params) or set(params) - required - optional:
            raise ValueError("Model-library request has missing or unexpected fields")
        from .spice_model_import import inspect_spice_model_library, import_spice_model
        if method == "inspect_spice_model_library":
            result = inspect_spice_model_library(params["text"], params["name"])
        else:
            notes = {}
            for key, limit in (("source_locator", 2048), ("license_note", 1024)):
                value = params.get(key, "")
                if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
                    raise ValueError(f"Invalid bounded {key}")
                notes[key] = value.strip()
            model = import_spice_model(params["text"], params["subcircuit_name"], params["name"])
            model["import_provenance"].update(notes)
            result = {"contract": "spike/spice-model-import/v1", "model": model,
                      "execution_admitted": False}
        return {"ok": True, "result": result}
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        return error_response("SPIKE-BE-IPC-E-0001", "Model-library import failed admission.",
                              detail=str(error), context={"method": method},
                              error_type=type(error).__name__)
