# SPDX-License-Identifier: Apache-2.0
"""Local stdio MCP adapter for selected SPIKE worker operations.

Only JSON-RPC frames are written to stdout. The worker remains the authority
for contracts, solver admission, capability status, and numerical results.
"""

from __future__ import annotations

import contextlib
from copy import deepcopy
import json
import math
import os
import socket
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from .automation import SpikeAutomation
from .mcp_protocol import McpProtocol, ProtocolError, decode_request, encode_response
from .mcp_protocol_catalog import CatalogPager
from .mcp_resources import SchemaResources


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

    integer_keys: tuple[str, ...] = ()
    number_keys: tuple[str, ...] = ()
    array_keys: tuple[str, ...] = ()
    property_schemas: dict[str, Any] = field(default_factory=dict)
    read_only: bool = False
    output_schema: dict[str, Any] | None = None

    def schema(self) -> dict[str, Any]:
        properties = {key: {"type": "string" if key in self.path_keys + self.string_keys else "integer" if key in self.integer_keys else "number" if key in self.number_keys else "array" if key in self.array_keys else "object"}
                      for key in self.required + self.optional}
        properties.update(deepcopy(self.property_schemas))
        for key, values in self.enums:
            properties[key]["enum"] = list(values)
        return {"type": "object", "properties": properties,
                "required": list(self.required), "additionalProperties": False}


# No arbitrary method dispatch, shell command, script, extension trust, or
# file-writing worker operation is reachable through this registry.
TOOLS: dict[str, Tool] = {
    "spike_run_harness_pi": Tool("run_harness_pi", "Solve explicit harness DC wires, returns, sources, loads and contact resistances; does not solve board fields.", ("request",)),
    "spike_run_harness_si": Tool("run_harness_si", "Compute a two-port harness signal/return or differential-mode network using explicit supplied RLGC; no automatic twist or crosstalk extraction.", ("request",)),
    "spike_run_harness_mtl": Tool("run_harness_mtl", "Solve a bounded branched multiconductor network with supplied sampled reciprocal RLGC and explicit ports; no radiation solve.", ("request",)),
    "spike_extract_harness_round_wire_rlgc": Tool("extract_harness_round_wire_rlgc", "Extract approximate straight round-wire RLGC above an explicit ideal plane in a homogeneous dielectric; no shields, bends or twist extraction.", ("request",)),
    "spike_prepare_harness_em": Tool("prepare_harness_em", "Inspect explicit harness geometry and EM requirements; readiness diagnostics do not execute a full-wave solve.", ("request",)),
    "spike_run_smps_converter": Tool("run_smps_converter", "Estimate supplied CCM converter power balance and component losses; steady average model, no control-loop transient solve.", ("request",)),
    "spike_validate_pwm_electrothermal": Tool("validate_pwm_electrothermal", "Preflight a bounded behavioral PWM buck with winding electrothermal feedback; admission is not qualification.", ("request",)),
    "spike_run_pwm_electrothermal": Tool("run_pwm_electrothermal", "Run the owned native closed-loop PWM buck reference with winding-only thermal feedback and energy accounting; no vendor switching-loss or EMI claim.", ("request",)),
    "spike_evaluate_capacitor_placement": Tool("evaluate_capacitor_placement", "Compare supplied capacitor candidates on a passive sampled impedance network; ranking is limited to supplied locations and frequencies.", ("request",)),
    "spike_plan_pi_return_path": Tool("plan_pi_return_path", "Find approximate resistance routes through admitted copper between explicitly selected return pads; does not route new copper.", ("design", "request")),
    "spike_discover_thermal_links": Tool("discover_assembly_thermal_links", "Discover exact conforming thermal interfaces; resistance is not inferred and review precedes linking.", ("request", "problem")),
    "spike_read_project": Tool("read_project_package", "Read a saved .spike package and embedded results without opening the GUI; large packages may exceed response limits.", ("path",), path_keys=("path",)),
    "spike_linked_assembly_nets": Tool("linked_assembly_nets", "Resolve occurrence-scoped assembly nets using retained explicit links.", ("request",)),
    "spike_prepare_multiboard_study": Tool("prepare_multiboard_study", "Admit an explicit reduced assembly study request; planning is not a completed solve.", ("request",)),
    "spike_run_multiboard_circuit": Tool("run_multiboard_circuit", "Run supplied reduced PI/SI circuit models; preserves approximate or unsupported status.", ("request",)),
    "spike_run_multiboard_thermal": Tool("run_multiboard_thermal", "Run supplied reduced multiboard thermal network, not an inferred spatial temperature field.", ("request",)),
    "spike_run_multiboard_em": Tool("run_multiboard_em", "Run supplied reduced assembly EM model; this does not establish full-wave validation.", ("request",)),
    "spike_prepare_assembly_field": Tool("prepare_assembly_field_handoff", "Prepare retained mechanical/board field handoff without inventing material or boundary data.", ("request",)),
    "spike_run_assembly_field_thermal": Tool("run_assembly_field_thermal", "Run explicitly supplied assembly thermal field inputs subject to worker admission.", ("request", "problem")),
    "spike_validate_thermal_time_refinement": Tool("validate_assembly_thermal_time_refinement", "Run three internal transient histories with halved steps; report solution-specific changes without production qualification.", ("request", "problem", "transient_settings", "tolerances")),
    "spike_prepare_volume_electrothermal": Tool("prepare_multiboard_volume_electrothermal", "Admit explicit native PI/SI resistor-to-volume thermal bindings; preparation is not a solve.", ("request",)),
    "spike_run_volume_electrothermal": Tool("run_multiboard_volume_electrothermal", "Run experimental steady native PI/SI and internal or CalculiX volume thermal feedback.", ("request",)),
    "spike_verify_volume_electrothermal": Tool("verify_multiboard_volume_electrothermal_result", "Offline saved co-simulation identity, circuit residual and loss admission; no solver rerun.", ("request", "result")),
    "spike_prepare_thermal_contact": Tool("prepare_assembly_thermal_contact_model", "Bind a retained contact total K/W resistance to conforming occurrence interface triangles.", ("request", "problem", "contact_id", "thermal_resistance_k_per_w"), string_keys=("contact_id",), number_keys=("thermal_resistance_k_per_w",)),
    "spike_run_assembly_electrothermal": Tool("run_assembly_electrothermal", "Run explicitly supplied coupled electrical/thermal assembly model, preserving experimental status.", ("request",)),
    "spike_import_assembly_field_study": Tool("import_assembly_field_study", "Validate a supplied saved field study record; no file write.", ("record",), ("current_request", "current_problem")),
    "spike_capabilities": Tool("capabilities", "SPIKE capability and qualification status."),
    "spike_parallel_pool": Tool("parallel_pool_catalog", "Report bounded local multicore pool and detected acceleration; no remote enrollment."),
    "spike_parallel_run": Tool("run_parallel_batch", "Run reviewed independent inline jobs in bounded fresh processes; no scripts, file paths or remote trust changes.", ("request",)),
    "spike_list_solvers": Tool("list_solvers", "Solver catalog and availability."),
    "spike_list_importers": Tool("list_importers", "Supported design importers."),
    "spike_thermal_capabilities": Tool("thermal_capabilities", "Thermal runtime availability and qualified or unsupported physics."),
    "spike_run_internal_airflow": Tool("run_internal_airflow", "Run experimental laminar heated-channel screening; no general geometry CFD or solved turbulence.", ("request",)),
    "spike_cfd_capabilities": Tool("cfd_capabilities", "Inspect configured native SPIKE and SU2 cavity CFD runtimes; excludes assembly CHT.", ()),
    "spike_run_native_cfd": Tool("run_native_cfd", "Run original experimental laminar cavity CFD in a bounded native worker.", ("request",)),
    "spike_run_su2_cfd": Tool("run_su2_cfd", "Run separately installed SU2 on an independently generated cavity benchmark.", ("request",)),
    "spike_run_su2_cht": Tool("run_su2_cht", "Run separately installed SU2 on a bounded fluid-solid conjugate heat-transfer case.", ("request",)),
    "spike_run_assembly_airflow": Tool("run_assembly_airflow", "Run experimental retained-solid assembly conjugate heat transfer with explicit air domain, materials and boundary conditions; requires an available OpenFOAM runtime.", ("request",)),
    "spike_read_assembly_airflow_setup": Tool("read_assembly_airflow_setup_in_project", "Read manifest-bound retained assembly solids for an airflow study.", ("project_path", "expected_manifest_payload_sha256", "assignments", "mesh_options"), path_keys=("project_path",), string_keys=("expected_manifest_payload_sha256",)),
    "spike_read_assembly_airflow_study": Tool("read_assembly_airflow_study_in_project", "Load saved assembly airflow fields only when their request and retained geometry still match.", ("project_path", "expected_manifest_payload_sha256"), path_keys=("project_path",), string_keys=("expected_manifest_payload_sha256",)),
    "spike_run_assembly_airflow_in_project": Tool("run_assembly_airflow_in_project", "Run and save manifest-bound assembly airflow fields with reviewed physical inputs.", ("project_path", "expected_manifest_payload_sha256", "assignments", "mesh_options", "request"), path_keys=("project_path",), string_keys=("expected_manifest_payload_sha256",)),
    "spike_extension_catalog": Tool("list_extensions", "Installed extension analysis contributions, input schemas, permissions and trust state; this does not grant trust."),
    "spike_load_design": Tool("load_design", "Load a local supported design file as SpiDeR.", ("path",), path_keys=("path",)),
    "spike_validate_design": Tool("validate_design", "Validate a SpiDeR design.", ("design",)),
    "spike_preflight_analysis": Tool("preflight_analysis", "Check an analysis setup and report readiness without solving.", ("design",), ("spec",)),
    "spike_run_preflighted_analysis": Tool("run_preflighted_analysis", "Preflight and run an admitted PI analysis; blocked setups remain blocked.", ("design",), ("spec",)),
    "spike_si_workflow_catalog": Tool("si_workflow_catalog", "Available SI workflow contract and capabilities."),
    "spike_run_si_workflow": Tool("run_si_workflow", "Run a versioned SI workflow request.", ("request",), ("design",)),
    "spike_validate_thermal": Tool("validate_thermal", "Validate a compact thermal scenario.", ("scenario",)),
    "spike_estimate_thermal": Tool("estimate_thermal", "Estimate a compact thermal scenario.", ("scenario",)),
    "spike_emi_preflight": Tool("emi_preflight", "Validate an EMI setup without claiming field solve or compliance.", ("design", "setup")),
    "spike_emi_screen": Tool("emi_screen", "Run an EMI screening estimate, subject to worker qualification status.", ("design", "setup")),
    "spike_contract_schema": Tool("schema:read", "List installed SPIKE contract schemas, or read one by its catalog filename. No arbitrary file read.", optional=("name",), string_keys=("name",)),
    "spike_validate_contract": Tool("schema:validate", "Validate supplied analysis inputs against an installed contract schema; validation does not establish solver readiness.", ("name", "document"), optional=("max_issues",), string_keys=("name",), integer_keys=("max_issues",), property_schemas={"max_issues":{"type":"integer","minimum":1,"maximum":500}}),
    "spike_gui_status": Tool("gui:status", "Inspect the running desktop state; requires the opt-in desktop bridge."),
    "spike_gui_select_workspace": Tool("gui:select_workspace", "Select a desktop workspace.", ("workspace",), string_keys=("workspace",), enums=(("workspace", ("PI", "SI", "EM", "Thermal", "Results", "Reports")),)),
    "spike_gui_set_view_mode": Tool("gui:set_view_mode", "Select the desktop 2D or 3D view.", ("mode",), string_keys=("mode",), enums=(("mode", ("2D", "3D")),)),
    "spike_gui_list_studies": Tool("gui:list_studies", "List studies in the running desktop project."),
    "spike_gui_create_study": Tool("gui:create_study", "Create a study in the running desktop project.", ("name",), string_keys=("name",)),
    "spike_gui_add_study_case": Tool("gui:add_study_case", "Add a PI, SI, EM, or thermal case to a study.", ("studyId", "type"), string_keys=("studyId", "type"), enums=(("type", ("pi", "si", "em", "thermal")),)),
    "spike_gui_activate_study_case": Tool("gui:activate_study_case", "Activate a study case in its desktop workspace.", ("studyId", "caseId"), string_keys=("studyId", "caseId")),
    "spike_gui_open_run_controls": Tool("gui:open_run_controls", "Open the active workspace run controls."),
    "spike_gui_analysis_view_result": Tool("gui:analysis_view_result", "Open an actual retained result by resultId in SPIKE. EM results accept bounded frequencyIndex, quantity and sampleIndex from actual data; no invented overlay.", ("resultId",), ("frequencyIndex", "quantity", "sampleIndex"), string_keys=("resultId", "quantity"), integer_keys=("frequencyIndex", "sampleIndex")),
    "spike_gui_analysis_generate_report": Tool("gui:analysis_generate_report", "Generate SPIKE's offline engineering report preview for the current loaded board and selected results. Does not export or overwrite files."),
    "spike_gui_analysis_context": Tool("gui:analysis_context", "Discover loaded board nets, pads, assembly scope, contributions and retained results. Optional query filters pads by net_names and pages them with pad_offset/pad_limit.", optional=("query",)),
    "spike_gui_analysis_describe": Tool("gui:analysis_describe", "Discover supported analysis paths, published contract names and qualification limits before preparing inputs.", optional=("kind",), string_keys=("kind",)),
    "spike_gui_analysis_prepare": Tool("gui:analysis_prepare", "Prepare an analysis bound to the loaded board/assembly. Supply explicit active_board or reduced_assembly scope; missing physics inputs remain missing.", ("kind", "scope"), ("parameters",), string_keys=("kind", "scope"), enums=(("scope", ("active_board", "reduced_assembly")),)),
    "spike_gui_analysis_patch": Tool("gui:analysis_patch", "Update a prepared case's parameter objects. This invalidates its preflight; no simulation runs.", ("caseId", "patch"), string_keys=("caseId",)),
    "spike_gui_analysis_preflight": Tool("gui:analysis_preflight", "Start asynchronous preparation/admission for an exact bound case revision. Returns a job ID; poll spike_gui_analysis_job.", ("caseId",), string_keys=("caseId",)),
    "spike_gui_analysis_run": Tool("gui:analysis_run", "Start an asynchronous run only after passing current-revision preparation. Returns a job ID; poll before interpreting solver evidence.", ("caseId",), string_keys=("caseId",)),
    "spike_gui_analysis_job": Tool("gui:analysis_job", "Inspect asynchronous preflight/solve status and qualification evidence without rerunning it.", ("jobId",), string_keys=("jobId",)),
    "spike_gui_analysis_evidence": Tool("gui:analysis_evidence", "Read actual returned result data by query path, offset and bounded limit. Missing samples are never invented.", ("jobId",), ("query",), string_keys=("jobId",)),
}


from .contract_catalog import schema_operation as _schema_operation
from .mcp_spider_tools import descriptors as _spider_descriptors
TOOLS.update({name: Tool(**descriptor) for name, descriptor in _spider_descriptors().items()})


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
        elif key in tool.integer_keys:
            if isinstance(item, bool) or not isinstance(item, int) or item < 0 or item > 10_000_000:
                raise ValueError(key + " must be a bounded nonnegative integer")
        elif key in tool.number_keys:
            if type(item) not in (int, float) or not math.isfinite(item):
                raise ValueError(key + " must be a finite number")
        elif key in tool.array_keys:
            if not isinstance(item, list):
                raise ValueError(key + " must be an array")
        elif not isinstance(item, dict):
            raise ValueError(key + " must be an object")
        for enum_key, values in tool.enums:
            if key == enum_key and item not in values:
                raise ValueError(key + " must be one of: " + ", ".join(values))
    if tool.property_schemas:
        import jsonschema
        try:
            jsonschema.Draft202012Validator(tool.schema()).validate(value)
        except jsonschema.ValidationError as exc:
            raise ValueError(f"Invalid tool argument at {list(exc.path)}: {exc.message}") from exc
    return value


class McpServer:
    def __init__(self, automation: SpikeAutomation | None = None) -> None:
        self.automation = automation
        self.protocol = McpProtocol()
        self.pager = CatalogPager()
        self.resources = SchemaResources(self.pager)

    @property
    def initialized(self) -> bool:
        return self.protocol.initialized

    def tools(self) -> list[dict[str, Any]]:
        """Deterministic, typed public catalog with honest operation hints."""
        read_methods = {"capabilities", "list_solvers", "list_importers", "thermal_capabilities", "list_extensions",
                        "parallel_pool_catalog", "cfd_capabilities", "si_workflow_catalog", "gui:status",
                        "gui:list_studies", "gui:analysis_context", "gui:analysis_describe", "gui:analysis_job", "gui:analysis_evidence"}
        result = []
        for name, tool in sorted(TOOLS.items()):
            descriptor = {"name": name, "title": name.removeprefix("spike_").replace("_", " ").title(),
                "description": tool.description, "inputSchema": tool.schema(),
                "annotations": {"readOnlyHint": tool.read_only or tool.method in read_methods or tool.method.startswith("schema:"),
                    "destructiveHint": False, "openWorldHint": False},
                "_meta": {"io.wayri.spike/workerMethod": tool.method,
                          "io.wayri.spike/transport": "desktop" if tool.method.startswith("gui:") else "schema" if tool.method.startswith("schema:") else "worker",
                          "io.wayri.spike/validationIsNotSolverAdmission": True}}
            if tool.output_schema is not None:
                descriptor["outputSchema"] = deepcopy(tool.output_schema)
            result.append(descriptor)
        return result

    def call_tool(self, name: str, arguments: Any = None) -> dict[str, Any]:
        """Invoke one allowlisted tool, returning an MCP CallToolResult."""
        tool = TOOLS.get(name)
        if tool is None:
            raise ValueError("Unknown tool")
        args = _validate_arguments(tool, {} if arguments is None else arguments)
        worker_meta = None
        try:
            if tool.method.startswith("schema:"):
                value = _schema_operation(tool.method.removeprefix("schema:"), args)
            elif tool.method.startswith("gui:"):
                value = _call_gui(tool.method.removeprefix("gui:"), args)
            else:
                with contextlib.redirect_stdout(sys.stderr):
                    if self.automation is None:
                        from .headless import run_request
                        timeout = float(os.environ.get("SPIKE_HEADLESS_TIMEOUT_SECONDS", "120"))
                        self.automation = SpikeAutomation(lambda request: run_request(request, timeout))
                    response = self.automation.call_response(tool.method, args)
                    value = response.get("result")
                    worker_meta = response.get("meta")
            serialized = json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
            if len(serialized.encode("utf-8")) > MAX_RESPONSE_BYTES:
                raise ValueError("Worker result exceeds MCP response limit")
            result = {"content": [{"type": "text", "text": serialized}], "isError": False}
            if isinstance(value, dict):
                if tool.output_schema is not None:
                    import jsonschema
                    jsonschema.Draft202012Validator(tool.output_schema).validate(value)
                result["structuredContent"] = value
            if isinstance(worker_meta, dict):
                result["_meta"] = {"io.wayri.spike/workerMetadata": worker_meta}
                if isinstance(worker_meta.get("spider"), dict):
                    result["content"].append({"type":"text", "text":json.dumps({"input_spider_binding":worker_meta["spider"]}, allow_nan=False)})
            if len(json.dumps(result, allow_nan=False, ensure_ascii=False).encode("utf-8")) > MAX_RESPONSE_BYTES:
                raise ValueError("Complete tool result exceeds MCP response limit; request a smaller page")
            return result
        except Exception as exc:  # A tool error does not terminate the client session.
            response = getattr(exc, "response", None)
            detail = response if isinstance(response, dict) else {"ok": False, "error": str(exc)}
            return {"content": [{"type": "text", "text": str(exc)}],
                    "structuredContent": detail, "isError": True}

    def handle(self, request: Any) -> dict[str, Any] | None:
        consumed, response = self.protocol.gate(request)
        if consumed:
            return response
        method = request["method"]
        params = request.get("params", {})
        try:
            if method == "tools/list":
                value = self.pager.page(self.tools(), params, "tools", "name")
            elif method == "resources/list":
                value = self.resources.list(params)
            elif method == "resources/read":
                value = self.resources.read(params)
            elif method == "tools/call":
                if set(params) - {"name", "arguments", "_meta"} or not isinstance(params.get("name"), str):
                    raise ValueError("Invalid tools/call parameters")
                value = self.call_tool(params["name"], params.get("arguments", {}))
            else:
                return self.protocol.error(request, -32601, "Method not found")
            return self.protocol.result(request, value)
        except ProtocolError as exc:
            return self.protocol.error(request, exc.code, str(exc))
        except (ValueError, KeyError, TypeError) as exc:
            return self.protocol.error(request, -32602, str(exc))
        except (OSError, RuntimeError) as exc:
            return self.protocol.error(request, -32603, str(exc))


def serve(input_stream: BinaryIO | None = None, output_stream: BinaryIO | None = None,
          automation: SpikeAutomation | None = None) -> None:
    source = input_stream or sys.stdin.buffer
    target = output_stream or sys.stdout.buffer
    server = McpServer(automation)
    while True:
        line = source.readline(MAX_REQUEST_BYTES + 1)
        if not line:
            return
        oversized = len(line) > MAX_REQUEST_BYTES
        try:
            request = decode_request(line, MAX_REQUEST_BYTES)
            response = server.handle(request)
        except ProtocolError as exc:
            response = server.protocol.error(None, exc.code, str(exc))
        if response is not None:
            try:
                encoded = encode_response(response, MAX_RESPONSE_BYTES)
            except ProtocolError as exc:
                encoded = encode_response(server.protocol.error(response, exc.code, str(exc)), MAX_RESPONSE_BYTES)
            target.write(encoded)
            target.flush()
        if oversized:
            return  # Oversized partial lines cannot be resynchronized safely.


if __name__ == "__main__":
    serve()
