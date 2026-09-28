# SPDX-License-Identifier: Apache-2.0
"""Local stdio MCP adapter for selected SPIKE worker operations.

Only JSON-RPC frames are written to stdout. The worker remains the authority
for contracts, solver admission, capability status, and numerical results.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import socket
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from .automation import SpikeAutomation


PROTOCOL_VERSION = "2025-11-25"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class Tool:
    method: str
    description: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    path_keys: tuple[str, ...] = ()
    string_keys: tuple[str, ...] = ()
    enums: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def schema(self) -> dict[str, Any]:
        properties = {key: {"type": "string" if key in self.path_keys + self.string_keys else "object"}
                      for key in self.required + self.optional}
        for key, values in self.enums:
            properties[key]["enum"] = list(values)
        return {"type": "object", "properties": properties,
                "required": list(self.required), "additionalProperties": False}


# No arbitrary method dispatch, shell command, script, extension trust, or
# file-writing worker operation is reachable through this registry.
TOOLS: dict[str, Tool] = {
    "spike_capabilities": Tool("capabilities", "SPIKE capability and qualification status."),
    "spike_list_solvers": Tool("list_solvers", "Solver catalog and availability."),
    "spike_list_importers": Tool("list_importers", "Supported design importers."),
    "spike_load_design": Tool("load_design", "Load a local supported design file as DesignIR.", ("path",), path_keys=("path",)),
    "spike_validate_design": Tool("validate_design", "Validate a DesignIR design.", ("design",)),
    "spike_preflight_analysis": Tool("preflight_analysis", "Check an analysis setup and report readiness without solving.", ("design",), ("spec",)),
    "spike_run_preflighted_analysis": Tool("run_preflighted_analysis", "Preflight and run an admitted PI analysis; blocked setups remain blocked.", ("design",), ("spec",)),
    "spike_si_workflow_catalog": Tool("si_workflow_catalog", "Available SI workflow contract and capabilities."),
    "spike_run_si_workflow": Tool("run_si_workflow", "Run a versioned SI workflow request.", ("request",), ("design",)),
    "spike_validate_thermal": Tool("validate_thermal", "Validate a compact thermal scenario.", ("scenario",)),
    "spike_estimate_thermal": Tool("estimate_thermal", "Estimate a compact thermal scenario.", ("scenario",)),
    "spike_emi_preflight": Tool("emi_preflight", "Validate an EMI setup without claiming field solve or compliance.", ("design", "setup")),
    "spike_emi_screen": Tool("emi_screen", "Run an EMI screening estimate, subject to worker qualification status.", ("design", "setup")),
    "spike_gui_status": Tool("gui:status", "Inspect the running desktop state; requires the opt-in desktop bridge."),
    "spike_gui_select_workspace": Tool("gui:select_workspace", "Select a desktop workspace.", ("workspace",), string_keys=("workspace",), enums=(("workspace", ("PI", "SI", "EM", "Thermal", "Results", "Reports")),)),
    "spike_gui_set_view_mode": Tool("gui:set_view_mode", "Select the desktop 2D or 3D view.", ("mode",), string_keys=("mode",), enums=(("mode", ("2D", "3D")),)),
    "spike_gui_list_studies": Tool("gui:list_studies", "List studies in the running desktop project."),
    "spike_gui_create_study": Tool("gui:create_study", "Create a study in the running desktop project.", ("name",), string_keys=("name",)),
    "spike_gui_add_study_case": Tool("gui:add_study_case", "Add a PI, SI, EM, or thermal case to a study.", ("studyId", "type"), string_keys=("studyId", "type"), enums=(("type", ("pi", "si", "em", "thermal")),)),
    "spike_gui_activate_study_case": Tool("gui:activate_study_case", "Activate a study case in its desktop workspace.", ("studyId", "caseId"), string_keys=("studyId", "caseId")),
    "spike_gui_open_run_controls": Tool("gui:open_run_controls", "Open the active workspace run controls."),
}


def _call_gui(command: str, arguments: dict[str, Any]) -> Any:
    bridge_file = os.environ.get("SPIKE_MCP_BRIDGE_FILE", "")
    if not bridge_file:
        local_data = os.environ.get("LOCALAPPDATA", "")
        directory = Path(local_data) / "org.spike.integrity" / "mcp" if local_data else None
        candidates = []
        if directory and directory.is_dir():
            for candidate in directory.glob("bridge-*.json"):
                try:
                    candidates.append((candidate.stat().st_mtime, candidate))
                except OSError:  # The desktop may remove a rendezvous during shutdown.
                    continue
            candidates.sort(reverse=True)
        if not candidates:
            raise RuntimeError("SPIKE desktop bridge unavailable; enable it in the desktop app or set SPIKE_MCP_BRIDGE_FILE")
        bridge_file = str(candidates[0][1])
    path = Path(bridge_file)
    if not path.is_file() or path.stat().st_size > 16 * 1024:
        raise RuntimeError("SPIKE desktop bridge rendezvous file is unavailable or invalid")
    try:
        details = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(details, dict) or details.get("version") != 1
                or details.get("host") != "127.0.0.1"
                or not isinstance(details.get("port"), int)
                or not 1 <= details["port"] <= 65535
                or not isinstance(details.get("token"), str)
                or len(details["token"]) < 16):
            raise ValueError("invalid bridge rendezvous data")
        request_id = uuid.uuid4().hex
        payload = {"token": details["token"], "requestId": request_id,
                   "command": command, "args": arguments}
        with socket.create_connection(("127.0.0.1", details["port"]), timeout=3) as connection:
            connection.settimeout(10)
            connection.sendall((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
            with connection.makefile("rb") as response_stream:
                line = response_stream.readline(MAX_RESPONSE_BYTES + 1)
        if len(line) > MAX_RESPONSE_BYTES or not line.endswith(b"\n"):
            raise ValueError("desktop bridge response is missing or too large")
        response = json.loads(line)
        if not isinstance(response, dict) or response.get("requestId") != request_id or not isinstance(response.get("ok"), bool):
            raise ValueError("invalid desktop bridge response")
        if not response["ok"]:
            raise RuntimeError(str(response.get("error") or "desktop command failed"))
        return response.get("result")
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"SPIKE desktop bridge unavailable: {exc}") from exc


def _error(identifier: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier,
            "error": {"code": code, "message": message}}


def _result(identifier: Any, value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "result": value}


def _validate_arguments(tool: Tool, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("arguments must be an object")
    allowed = set(tool.required + tool.optional)
    if set(value) - allowed:
        raise ValueError("unknown argument: " + sorted(set(value) - allowed)[0])
    for key in tool.required:
        if key not in value:
            raise ValueError("missing required argument: " + key)
    for key, item in value.items():
        if key in tool.path_keys + tool.string_keys:
            if not isinstance(item, str) or not item.strip() or "\x00" in item or len(item) > 4096:
                raise ValueError(key + " must be a non-empty string")
        elif not isinstance(item, dict):
            raise ValueError(key + " must be an object")
        for enum_key, values in tool.enums:
            if key == enum_key and item not in values:
                raise ValueError(key + " must be one of: " + ", ".join(values))
    return value


class McpServer:
    def __init__(self, automation: SpikeAutomation | None = None) -> None:
        self.automation = automation
        self.initialized = False

    def tools(self) -> list[dict[str, Any]]:
        """Return the public MCP tool catalog for local clients."""
        return [{"name": name, "description": tool.description, "inputSchema": tool.schema()}
                for name, tool in TOOLS.items()]

    def call_tool(self, name: str, arguments: Any = None) -> dict[str, Any]:
        """Invoke one allowlisted tool, returning an MCP CallToolResult."""
        tool = TOOLS.get(name)
        if tool is None:
            raise ValueError("Unknown tool")
        args = _validate_arguments(tool, {} if arguments is None else arguments)
        try:
            if tool.method.startswith("gui:"):
                value = _call_gui(tool.method.removeprefix("gui:"), args)
            else:
                with contextlib.redirect_stdout(sys.stderr):
                    if self.automation is None:
                        self.automation = SpikeAutomation()
                    value = self.automation.call(tool.method, args)
            serialized = json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
            if len(serialized.encode("utf-8")) > MAX_RESPONSE_BYTES:
                raise ValueError("Worker result exceeds MCP response limit")
            return {"content": [{"type": "text", "text": serialized}], "isError": False}
        except Exception as exc:  # A tool error does not terminate the client session.
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}

    def handle(self, request: Any) -> dict[str, Any] | None:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return _error(None, -32600, "Invalid JSON-RPC request")
        method = request.get("method")
        identifier = request.get("id")
        if not isinstance(method, str) or ("id" in request and (isinstance(identifier, bool) or not isinstance(identifier, (str, int, float)) or (isinstance(identifier, float) and not math.isfinite(identifier)))):
            return _error(None, -32600, "Invalid JSON-RPC request")
        if "id" not in request:
            if method == "notifications/initialized" and self.initialized:
                return None
            return None  # Notifications never receive responses.
        if method == "initialize":
            params = request.get("params")
            if self.initialized or not isinstance(params, dict) or not isinstance(params.get("protocolVersion"), str):
                return _error(identifier, -32602, "Invalid initialize parameters")
            self.initialized = True
            return _result(identifier, {"protocolVersion": PROTOCOL_VERSION,
                                        "capabilities": {"tools": {"listChanged": False}},
                                        "serverInfo": {"name": "spike-local", "version": "1.0.0"}})
        if method == "ping":
            return _result(identifier, {})
        if not self.initialized:
            return _error(identifier, -32002, "Initialize first")
        if method == "tools/list":
            params = request.get("params", {})
            if not isinstance(params, dict) or params.get("cursor") is not None:
                return _error(identifier, -32602, "Invalid tools/list parameters")
            return _result(identifier, {"tools": self.tools()})
        if method == "tools/call":
            params = request.get("params")
            if not isinstance(params, dict) or not isinstance(params.get("name"), str):
                return _error(identifier, -32602, "Invalid tools/call parameters")
            try:
                result = self.call_tool(params["name"], params.get("arguments", {}))
            except ValueError as exc:
                return _error(identifier, -32602, str(exc))
            return _result(identifier, result)
        return _error(identifier, -32601, "Method not found")


def serve(input_stream: BinaryIO | None = None, output_stream: BinaryIO | None = None,
          automation: SpikeAutomation | None = None) -> None:
    source = input_stream or sys.stdin.buffer
    target = output_stream or sys.stdout.buffer
    server = McpServer(automation)
    while True:
        line = source.readline(MAX_REQUEST_BYTES + 1)
        if not line:
            return
        if len(line) > MAX_REQUEST_BYTES:
            response = _error(None, -32700, "Request exceeds size limit")
            # A partial line cannot be framed safely; terminate after error.
            target.write((json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8"))
            target.flush()
            return
        try:
            request = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
            response = _error(None, -32700, "Invalid JSON")
        else:
            response = server.handle(request)
        if response is not None:
            encoded = (json.dumps(response, allow_nan=False, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            target.write(encoded)
            target.flush()


if __name__ == "__main__":
    serve()
