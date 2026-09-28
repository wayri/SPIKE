# SPDX-License-Identifier: Apache-2.0
"""Offline LM Studio and Ollama tool-calling client for SPIKE's MCP catalog."""

from __future__ import annotations

import argparse
import http.client
import json
import sys
from urllib.parse import urlsplit
from typing import Any

from .mcp_server import McpServer


MAX_HTTP_BYTES = 16 * 1024 * 1024
MAX_TOOL_ROUNDS = 8
MAX_TOOL_CALLS = 16
DEFAULT_ENDPOINTS = {"lmstudio": "http://127.0.0.1:1234", "ollama": "http://127.0.0.1:11434"}


class LocalModelError(RuntimeError):
    pass


def _endpoint(value: str) -> tuple[str, int]:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise LocalModelError("Local model endpoint must be a plain loopback HTTP origin")
    try:
        port = parsed.port
    except ValueError as exc:
        raise LocalModelError("Invalid local model port") from exc
    if port is None or not 1 <= port <= 65535:
        raise LocalModelError("Local model endpoint must include a port")
    return parsed.hostname, port


def _request(origin: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    host, port = _endpoint(origin)
    connection = http.client.HTTPConnection(host, port, timeout=120)
    payload = None if body is None else json.dumps(body, allow_nan=False, separators=(",", ":")).encode("utf-8")
    try:
        connection.request("GET" if payload is None else "POST", path, body=payload, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        data = response.read(MAX_HTTP_BYTES + 1)
        if len(data) > MAX_HTTP_BYTES:
            raise LocalModelError("Local model response exceeded 16 MiB")
        if response.status != 200:
            raise LocalModelError(f"Local model returned HTTP {response.status}: {data[:300].decode('utf-8', errors='replace')}")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise LocalModelError("Local model returned invalid JSON")
        return result
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalModelError(f"Local model request failed: {exc}") from exc
    finally:
        connection.close()


def list_models(provider: str, endpoint: str | None = None) -> list[str]:
    if provider not in DEFAULT_ENDPOINTS:
        raise LocalModelError("Provider must be lmstudio or ollama")
    origin = endpoint or DEFAULT_ENDPOINTS[provider]
    result = _request(origin, "/v1/models" if provider == "lmstudio" else "/api/tags")
    rows = result.get("data" if provider == "lmstudio" else "models")
    if not isinstance(rows, list):
        raise LocalModelError("Local model list has an unexpected shape")
    key = "id" if provider == "lmstudio" else "name"
    return [row[key] for row in rows if isinstance(row, dict) and isinstance(row.get(key), str)]


def _tool_arguments(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    function = call.get("function")
    if not isinstance(function, dict) or not isinstance(function.get("name"), str):
        raise LocalModelError("Model returned an invalid tool call")
    arguments = function.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise LocalModelError("Model returned invalid tool arguments") from exc
    if not isinstance(arguments, dict):
        raise LocalModelError("Model tool arguments must be an object")
    return function["name"], arguments


def chat(provider: str, model: str, prompt: str, *, endpoint: str | None = None,
         server: McpServer | None = None) -> str:
    if provider not in DEFAULT_ENDPOINTS:
        raise LocalModelError("Provider must be lmstudio or ollama")
    if not model.strip() or not prompt.strip():
        raise LocalModelError("Model and prompt are required")
    origin = endpoint or DEFAULT_ENDPOINTS[provider]
    _endpoint(origin)
    catalog = server or McpServer()
    tools = [{"type": "function", "function": {"name": tool["name"],
              "description": tool["description"], "parameters": tool["inputSchema"]}}
             for tool in catalog.tools()]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "You operate SPIKE using the supplied tools. Report tool errors and numerical qualification honestly."},
        {"role": "user", "content": prompt},
    ]
    calls_used = 0
    for _ in range(MAX_TOOL_ROUNDS + 1):
        body = {"model": model, "messages": messages, "tools": tools, "stream": False}
        response = _request(origin, "/v1/chat/completions" if provider == "lmstudio" else "/api/chat", body)
        if provider == "lmstudio":
            choices = response.get("choices")
            message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        else:
            message = response.get("message")
        if not isinstance(message, dict):
            raise LocalModelError("Local model returned no assistant message")
        tool_calls = message.get("tool_calls") or []
        if not isinstance(tool_calls, list):
            raise LocalModelError("Local model returned invalid tool calls")
        if not tool_calls:
            content = message.get("content")
            return content if isinstance(content, str) else ""
        if calls_used + len(tool_calls) > MAX_TOOL_CALLS:
            raise LocalModelError("Local model exceeded the tool-call limit")
        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
        for call in tool_calls:
            if not isinstance(call, dict):
                raise LocalModelError("Local model returned an invalid tool call")
            name, arguments = _tool_arguments(call)
            try:
                result = catalog.call_tool(name, arguments)
            except ValueError as exc:
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            content = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            if provider == "lmstudio":
                if not isinstance(call.get("id"), str):
                    raise LocalModelError("LM Studio tool call lacks an ID")
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
            else:
                messages.append({"role": "tool", "tool_name": name, "content": content})
            calls_used += 1
    raise LocalModelError("Local model exceeded the tool-round limit")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask an offline LM Studio or Ollama model to operate SPIKE tools")
    parser.add_argument("--provider", choices=("lmstudio", "ollama"), required=True)
    parser.add_argument("--model", help="Local model ID/name; defaults to first listed model")
    parser.add_argument("--endpoint", help="Override the local loopback origin")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("prompt", nargs="*", help="Prompt; omit for interactive mode")
    args = parser.parse_args(argv)
    try:
        if args.list_models:
            print("\n".join(list_models(args.provider, args.endpoint)))
            return 0
        models = [args.model] if args.model else list_models(args.provider, args.endpoint)
        if not models:
            raise LocalModelError("No local models found. Load a tool-capable model first.")
        if args.prompt:
            print(chat(args.provider, models[0], " ".join(args.prompt), endpoint=args.endpoint))
            return 0
        print(f"SPIKE local chat via {args.provider} ({models[0]}). Enter a blank line to exit.")
        while True:
            prompt = input("SPIKE> ").strip()
            if not prompt:
                break
            print(chat(args.provider, models[0], prompt, endpoint=args.endpoint))
        return 0
    except (LocalModelError, KeyboardInterrupt, EOFError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
