# SPDX-License-Identifier: Apache-2.0
"""Worker entry points for opt-in assistant providers and OS credentials."""
from . import assistant_credentials as credentials
from . import assistant_provider as provider

_METHOD_FIELDS = {
    "assistant_schema": {"name"},
    "assistant_validate_schema": {"name", "document"},
    "assistant_provider_status": {"provider"},
    "assistant_set_credential": {"provider", "key"},
    "assistant_delete_credential": {"provider"},
    "assistant_models": {"provider", "endpoint"},
    "assistant_turn": {"provider", "model", "endpoint", "messages", "tools", "system", "share_project_context", "allow_cloud"},
}


def handle_assistant_request(method, params, request_id=None):
    if not isinstance(method, str) or method not in _METHOD_FIELDS:
        return None
    try:
        if not isinstance(params, dict) or set(params) - _METHOD_FIELDS[method]:
            raise provider.ProviderError("Invalid assistant request parameters.")
        provider._encode(params)
        if method in {"assistant_schema", "assistant_validate_schema"}:
            from .contract_catalog import schema_operation
            return {"ok": True, "result": schema_operation("read" if method == "assistant_schema" else "validate", params)}
        selected = provider._provider(params)
        if method == "assistant_set_credential":
            credentials.set_credential(selected, params.get("key"))
            result = {"provider": selected, "credential_configured": True}
        elif method == "assistant_delete_credential":
            credentials.delete_credential(selected)
            result = {"provider": selected, "credential_configured": False}
        else:
            result = getattr(provider, method)(params)
        return {"ok": True, "result": result}
    except provider.ProviderError as exc:
        return {"ok": False, "error": str(exc), "type": "AssistantProviderError"}
    except Exception:
        # Credentials and remote bodies must never escape via exception messages.
        return {"ok": False, "error": "Assistant operation failed. Check provider settings and OS credential-store availability.", "type": "AssistantProviderError"}
