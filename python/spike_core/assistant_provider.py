# SPDX-License-Identifier: Apache-2.0
"""Bounded, explicit provider transport; model tool requests are inert data."""
from __future__ import annotations
import http.client
import ipaddress
import json
import math
import queue
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit
from . import assistant_credentials as credentials

REQUEST_LIMIT = 2 * 1024 * 1024
RESPONSE_LIMIT = 4 * 1024 * 1024
TIMEOUT = 120
CLOUD = {"openai": "api.openai.com", "anthropic": "api.anthropic.com"}
LOCAL = {"lmstudio": "http://127.0.0.1:1234", "ollama": "http://127.0.0.1:11434"}
PROVIDERS = set(CLOUD) | set(LOCAL)


class ProviderError(ValueError):
    """Safe, locally generated diagnostic, never provider response text."""


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProviderError("Provider JSON has duplicate object keys.")
        result[key] = value
    return result


def _validate_tree(value, depth=0, budget=None):
    if budget is None:
        budget = [100000]
    budget[0] -= 1
    if depth > 32 or budget[0] < 0:
        raise ProviderError("Assistant JSON exceeds nesting or collection limits.")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProviderError("Assistant JSON keys must be strings.")
            _validate_tree(item, depth + 1, budget)
    elif isinstance(value, list):
        for item in value:
            _validate_tree(item, depth + 1, budget)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ProviderError("Assistant JSON contains a non-finite number.")
    elif value is not None and not isinstance(value, (str, bool, int, float)):
        raise ProviderError("Assistant data must be JSON values.")


def strict_json(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_object_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ProviderError("Non-finite JSON is unsupported.")))
        _validate_tree(value)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ProviderError("Provider returned malformed JSON.") from exc


def _encode(value):
    _validate_tree(value)
    raw = json.dumps(value, allow_nan=False, ensure_ascii=False).encode("utf-8")
    if len(raw) > REQUEST_LIMIT:
        raise ProviderError("Assistant request exceeds the 2 MiB limit.")
    return raw


def _string(value, label, limit=65536, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ProviderError("Invalid " + label + ".")
    return value


def _provider(params):
    provider = params.get("provider")
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise ProviderError("Unsupported assistant provider.")
    return provider


def _destination(provider, endpoint):
    if provider in CLOUD:
        if endpoint not in (None, "", "https://" + CLOUD[provider], "https://" + CLOUD[provider] + "/v1"):
            raise ProviderError("Cloud endpoints are fixed to the official HTTPS host.")
        return "https", CLOUD[provider], 443
    if endpoint is not None and not isinstance(endpoint, str):
        raise ProviderError("Local endpoint must be a URL.")
    try:
        parsed = urlsplit(endpoint or LOCAL[provider])
        host = parsed.hostname
        if parsed.scheme != "http" or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or parsed.path not in ("", "/", "/v1") or not parsed.port:
            raise ValueError()
        # Numeric addresses avoid DNS rebinding. localhost is pinned explicitly.
        if host == "localhost":
            host = "127.0.0.1"
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError()
        return "http", host, parsed.port
    except (ValueError, TypeError):
        raise ProviderError("Local endpoint must use HTTP, a loopback address, and an explicit port.") from None


def _request(provider, endpoint, path, payload=None):
    scheme, host, port = _destination(provider, endpoint)
    headers = {"Accept": "application/json"}
    if provider in CLOUD:
        key = credentials.get_credential(provider)
        if not key:
            raise ProviderError("Save an API key in the OS credential store first.")
        if provider == "openai":
            headers["Authorization"] = "Bearer " + key
        else:
            headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    body = None if payload is None else _encode(payload)
    if body is not None:
        headers["Content-Type"] = "application/json"
    # No proxy environment, redirects, cookies, or SDK retries. TLS verifies host.
    connection = (http.client.HTTPSConnection(host, port, timeout=TIMEOUT, context=ssl.create_default_context())
                  if scheme == "https" else http.client.HTTPConnection(host, port, timeout=TIMEOUT))
    replies = queue.Queue(maxsize=1)
    stopped = threading.Event()
    deadline = time.monotonic() + TIMEOUT

    def exchange():
        response = None
        try:
            connection.request("GET" if body is None else "POST", path, body, headers)
            if stopped.is_set():
                return
            response = connection.getresponse()
            if response.status < 200 or response.status >= 300:
                raise ProviderError(f"Provider HTTP request failed (status {response.status}).")
            content_length = response.getheader("Content-Length")
            if content_length is not None and (not content_length.isdecimal() or int(content_length) > RESPONSE_LIMIT):
                raise ProviderError("Provider response exceeds the 4 MiB limit or has invalid length.")
            parts, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if stopped.is_set() or remaining <= 0:
                    raise ProviderError("Provider request timed out.")
                if connection.sock:
                    connection.sock.settimeout(remaining)
                part = response.read1(min(65536, RESPONSE_LIMIT + 1 - size))
                size += len(part)
                if size > RESPONSE_LIMIT:
                    raise ProviderError("Provider response exceeds the 4 MiB limit.")
                if not part:
                    break
                parts.append(part)
            replies.put((True, strict_json(b"".join(parts))))
        except ProviderError as exc:
            replies.put((False, exc))
        except Exception:
            replies.put((False, ProviderError("Provider connection failed; check the endpoint, credentials, and service.")))
        finally:
            if response is not None:
                response.close()
            connection.close()

    threading.Thread(target=exchange, name="spike-assistant-http", daemon=True).start()
    try:
        success, result = replies.get(timeout=TIMEOUT)
    except queue.Empty:
        stopped.set()
        if connection.sock:
            try:
                connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        connection.close()
        raise ProviderError("Provider request timed out.") from None
    if not success:
        raise result
    if not isinstance(result, dict):
        raise ProviderError("Provider response must be a JSON object.")
    return result


def _calls(value):
    if not isinstance(value, list) or len(value) > 8:
        raise ProviderError("At most eight tool calls are supported per message.")
    result, seen = [], set()
    for call in value:
        if not isinstance(call, dict):
            raise ProviderError("Malformed tool call.")
        identity = _string(call.get("id"), "tool call identifier", 256)
        name = _string(call.get("name"), "tool name", 128)
        arguments = call.get("arguments")
        if isinstance(arguments, str):
            arguments = strict_json(arguments)
        if not isinstance(arguments, dict) or identity in seen:
            raise ProviderError("Tool arguments must be an object and call identifiers must be unique.")
        _validate_tree(arguments)
        seen.add(identity)
        result.append({"id": identity, "name": name, "arguments": arguments})
    return result


def _history(params):
    messages = params.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 128:
        raise ProviderError("Assistant history requires 1–128 messages.")
    result, pending, used = [], {}, set()
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant", "tool"}:
            raise ProviderError("Unsupported conversation role.")
        role = message["role"]
        content = _string(message.get("content", ""), "message content", REQUEST_LIMIT, empty=True)
        record = {"role": role, "content": content}
        if role == "tool":
            identity = message.get("tool_call_id")
            if not isinstance(identity, str) or identity not in pending:
                raise ProviderError("Tool result does not match a pending tool call.")
            record.update(tool_call_id=identity, tool_name=pending.pop(identity))
        else:
            if pending:
                raise ProviderError("Conversation is missing tool results.")
            if role == "assistant":
                record["tool_calls"] = _calls(message.get("tool_calls", []))
                for call in record["tool_calls"]:
                    if call["id"] in used:
                        raise ProviderError("Tool call identifiers must be unique across history.")
                    pending[call["id"]] = call["name"]
                    used.add(call["id"])
        result.append(record)
    if pending:
        raise ProviderError("Conversation is missing tool results.")
    return result


def _tools(params):
    value = params.get("tools", [])
    if not isinstance(value, list) or len(value) > 32:
        raise ProviderError("At most 32 assistant tools are supported.")
    result, names = [], set()
    for tool in value:
        if not isinstance(tool, dict):
            raise ProviderError("Invalid tool descriptor.")
        name = _string(tool.get("name"), "tool name", 128)
        description = _string(tool.get("description", ""), "tool description", empty=True)
        schema = tool.get("parameters")
        if name in names or not isinstance(schema, dict) or schema.get("type") != "object":
            raise ProviderError("Tool names must be unique and parameters must use an object schema.")
        names.add(name)
        result.append({"name": name, "description": description, "parameters": schema})
    return result


def _payload(provider, model, history, tools, system):
    if provider == "openai":
        inputs = []
        for message in history:
            role = message["role"]
            if role == "tool":
                inputs.append({"type": "function_call_output", "call_id": message["tool_call_id"], "output": message["content"]})
            else:
                if message["content"]:
                    inputs.append({"role": role, "content": message["content"]})
                for call in message.get("tool_calls", []):
                    inputs.append({"type": "function_call", "call_id": call["id"], "name": call["name"], "arguments": json.dumps(call["arguments"], allow_nan=False)})
        return {"model": model, "instructions": system, "input": inputs, "store": False,
                "tools": [{"type": "function", **tool, "strict": False} for tool in tools]}
    if provider == "anthropic":
        messages = []
        for message in history:
            role = message["role"]
            if role == "tool":
                content = [{"type": "tool_result", "tool_use_id": message["tool_call_id"], "content": message["content"]}]
                role = "user"
            else:
                content = [{"type": "text", "text": message["content"]}] if message["content"] else []
                content += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["arguments"]} for c in message.get("tool_calls", [])]
            if messages and messages[-1]["role"] == role:
                messages[-1]["content"].extend(content)
            else:
                messages.append({"role": role, "content": content})
        return {"model": model, "system": system, "messages": messages, "max_tokens": 4096,
                "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]}
    messages = [{"role": "system", "content": system}] if system else []
    for message in history:
        item = {"role": message["role"], "content": message["content"]}
        if message["role"] == "tool":
            item.update({"tool_name": message["tool_name"]} if provider == "ollama" else {"tool_call_id": message["tool_call_id"]})
        calls = message.get("tool_calls", [])
        if calls:
            item["tool_calls"] = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] if provider == "ollama" else json.dumps(c["arguments"], allow_nan=False)}} for c in calls]
        messages.append(item)
    return {"model": model, "messages": messages, "stream": False,
            "tools": [{"type": "function", "function": tool} for tool in tools]}


def _normalize(provider, result, turn):
    content, calls = [], []
    if provider == "openai":
        if result.get("status") not in (None, "completed") or result.get("error"):
            raise ProviderError("Provider did not complete the requested turn.")
        for item in result["output"]:
            if item.get("type") == "function_call":
                calls.append({"id": item["call_id"], "name": item["name"], "arguments": item["arguments"]})
            elif item.get("type") == "message":
                content.extend(block["text"] for block in item["content"] if block.get("type") == "output_text")
    elif provider == "anthropic":
        if result.get("stop_reason") not in ("end_turn", "tool_use", "stop_sequence"):
            raise ProviderError("Provider did not complete the requested turn.")
        for block in result["content"]:
            if block.get("type") == "text":
                content.append(block["text"])
            elif block.get("type") == "tool_use":
                calls.append({"id": block["id"], "name": block["name"], "arguments": block["input"]})
    else:
        if provider == "lmstudio":
            choice = result["choices"][0]
            if choice.get("finish_reason") not in ("stop", "tool_calls"):
                raise ProviderError("Provider did not complete the requested turn.")
            message = choice["message"]
        else:
            if result.get("done") is not True:
                raise ProviderError("Provider returned an incomplete turn.")
            message = result["message"]
        content.append(message.get("content") or "")
        for index, call in enumerate(message.get("tool_calls", [])):
            calls.append({"id": call.get("id") or f"call_{turn}_{index}", "name": call["function"]["name"], "arguments": call["function"]["arguments"]})
    if any(not isinstance(part, str) for part in content):
        raise ProviderError("Provider message content must be text.")
    normalized = {"role": "assistant", "content": "\n".join(content), "tool_calls": _calls(calls)}
    if not normalized["content"] and not normalized["tool_calls"]:
        raise ProviderError("Provider returned no supported text or tool calls.")
    return normalized


def assistant_turn(params):
    _encode(params)
    provider = _provider(params)
    if type(params.get("share_project_context", False)) is not bool or type(params.get("allow_cloud", False)) is not bool:
        raise ProviderError("Cloud and project sharing choices must be booleans.")
    if provider in CLOUD and params.get("allow_cloud") is not True:
        raise ProviderError("Confirm sending this conversation to the selected cloud provider first.")
    model = _string(params.get("model"), "model identifier", 256)
    history, tools = _history(params), _tools(params)
    system = _string(params.get("system", ""), "system instructions", REQUEST_LIMIT, empty=True)
    payload = _payload(provider, model, history, tools, system)
    paths = {"openai": "/v1/responses", "anthropic": "/v1/messages", "lmstudio": "/v1/chat/completions", "ollama": "/api/chat"}
    result = _request(provider, params.get("endpoint"), paths[provider], payload)
    try:
        message = _normalize(provider, result, len(history))
        allowed = {tool["name"] for tool in tools}
        if any(call["name"] not in allowed for call in message["tool_calls"]):
            raise ProviderError("Provider requested an unavailable tool.")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ProviderError("Provider returned an unsupported response shape.") from None
    return {"provider": provider, "model": model, "message": message}


def assistant_models(params):
    provider = _provider(params)
    response = _request(provider, params.get("endpoint"), "/api/tags" if provider == "ollama" else "/v1/models")
    try:
        items = response["models" if provider == "ollama" else "data"]
        if not isinstance(items, list) or len(items) > 4096:
            raise ProviderError("Invalid provider model list.")
        models = [_string(item["name" if provider == "ollama" else "id"], "model identifier", 256) for item in items]
        return {"provider": provider, "models": sorted(set(models))}
    except (KeyError, TypeError):
        raise ProviderError("Provider returned an unsupported model list.") from None


def assistant_provider_status(params):
    provider = _provider(params)
    supported = credentials.sys.platform == "win32"
    configured = bool(credentials.get_credential(provider)) if provider in CLOUD and supported else False
    return {"provider": provider, "cloud": provider in CLOUD, "credential_configured": configured,
            "credential_store_supported": supported, "network_probed": False,
            "endpoint": "https://" + CLOUD[provider] if provider in CLOUD else LOCAL[provider]}
