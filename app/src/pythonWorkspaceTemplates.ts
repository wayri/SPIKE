// SPDX-License-Identifier: Apache-2.0

export interface PythonTemplate {
  id: string;
  title: string;
  category: string;
  description: string;
  requirements: string[];
  code: string;
}

const entry = (id: string, title: string, category: string, description: string,
  requirements: string[], code: string): PythonTemplate => ({ id, title, category, description, requirements, code });

const requestRunner = (method: string, options: {
  attachDesign?: boolean; requiredKey: "spec" | "request" | "setup"; expectedMode?: string;
}): string => `# Execute ${method} from a reviewed worker-parameter JSON object.
# Relative paths resolve from the saved script's folder, or the selected workspace folder for an unsaved tab.
import json
from pathlib import Path

REQUEST_FILE = None  # Set to Path(r"C:\\path\\to\\reviewed-request.json")
PUBLISH_RESULT = False  # Publishes only a matching spike/v1 AnalysisResult.
MAX_REQUEST_BYTES = 4 * 1024 * 1024

def load_params(path_value):
    if path_value is None:
        return None
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Request file does not exist: {path}")
    data = path.read_bytes()
    if len(data) > MAX_REQUEST_BYTES:
        raise ValueError("Request JSON exceeds the 4 MiB template limit.")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Request file must be valid UTF-8 JSON.") from exc
    if not isinstance(value, dict):
        raise TypeError("Request JSON must contain one worker parameter object.")
    return value

def print_evidence(value):
    if not isinstance(value, dict):
        print("Worker returned:", value)
        return
    for key in ("contract", "status", "model_status", "summary", "issues", "provenance"):
        if key in value:
            print(f"{key}:", value[key])

def publish_if_requested(value):
    if not PUBLISH_RESULT:
        return
    if not isinstance(value, dict) or value.get("contract") != "spike/v1":
        raise ValueError("Worker response is not a publishable spike/v1 AnalysisResult.")
    if not isinstance(spike.design, dict):
        raise RuntimeError("A loaded design is required to publish a result.")
    expected = spike.design.get("design_id")
    provenance = value.get("provenance")
    actual = provenance.get("design_id") if isinstance(provenance, dict) else None
    if not expected or actual != expected:
        raise ValueError("Result provenance does not match the loaded design identity.")
    spike.publish_result(value)

params = load_params(REQUEST_FILE)
if params is None:
    print("Set REQUEST_FILE to a reviewed ${method} parameter JSON file; nothing was launched.")
else:
    if "${options.requiredKey}" not in params or not isinstance(params["${options.requiredKey}"], dict):
        raise ValueError("${method} parameters require an object field named ${options.requiredKey}.")
${options.expectedMode ? `    mode = params["spec"].get("mode")
    if mode != "${options.expectedMode}":
        raise ValueError("This runner requires spec.mode='${options.expectedMode}'.")
` : ""}${options.attachDesign ? `    loaded = spike.design
    if not isinstance(loaded, dict):
        raise RuntimeError("Load the design associated with this request first.")
    supplied = params.get("design")
    if supplied is not None:
        if not isinstance(supplied, dict):
            raise TypeError("Request design must be an object.")
        if supplied.get("design_id") != loaded.get("design_id"):
            raise ValueError("Request design_id differs from the loaded design; execution refused.")
    else:
        params["design"] = loaded
` : ""}    result = spike.call("${method}", params)
    print_evidence(result)
    publish_if_requested(result)
`;

export const PYTHON_TEMPLATES: PythonTemplate[] = [
  entry("hello-context", "Workspace context", "Basics", "Show which SPIKE contexts are attached and query worker health.", [], `# Inspect the Python workspace context without changing the project.
print("Design attached:", spike.design is not None)
print("Result attached:", spike.results is not None)
health = spike.call("health")
print("Worker contract:", health.get("contract", "unknown"))
print("Worker version:", health.get("worker_version", "unknown"))
`),
  entry("design-summary", "Design summary", "Design inspection", "Count normalized board objects and report identity and units.", ["Loaded design"], `# Summarize the normalized spike/v1 design supplied by the desktop.
design = spike.design
if design is None:
    raise RuntimeError("Load a board before running this script.")
print("Name:", design.get("name", "unnamed"))
print("Design ID:", design.get("design_id", "missing"))
print("Contract:", design.get("contract", "missing"))
print("Units:", design.get("units", "missing"))
for key in ("layers", "nets", "tracks", "vias", "pads", "zones", "components", "issues"):
    value = design.get(key, [])
    print(f"{key}: {len(value) if isinstance(value, list) else 'unexpected shape'}")
`),
  entry("net-inventory", "Net inventory", "Design inspection", "List stable net identifiers and names from the loaded board.", ["Loaded design"], `# Print net identity without assuming source-format fields.
design = spike.design
if not isinstance(design, dict):
    raise RuntimeError("A loaded design is required.")
nets = design.get("nets", [])
if not isinstance(nets, list):
    raise RuntimeError("Design nets are not an array.")
for index, net in enumerate(nets):
    if isinstance(net, dict):
        print(index, net.get("id", "<no id>"), net.get("name", "<unnamed>"))
print("Net count:", len(nets))
`),
  entry("layer-stackup", "Layer and stackup inventory", "Design inspection", "Inspect imported layer and stackup records without inferring missing materials.", ["Loaded design"], `# Imported stackup data may be incomplete; print only supplied values.
design = spike.design
if not isinstance(design, dict):
    raise RuntimeError("Load a design first.")
for heading, records in (("LAYERS", design.get("layers", [])), ("STACKUP", design.get("stackup", []))):
    print(heading)
    if not isinstance(records, list) or not records:
        print("  no records supplied")
        continue
    for record in records:
        print(" ", record)
`),
  entry("geometry-bounds", "Copper geometry bounds", "Design inspection", "Find finite XY extents from common normalized copper geometry points.", ["Loaded design"], `# Derive a diagnostic bounding box from coordinates actually present in the design.
import math
design = spike.design
if not isinstance(design, dict):
    raise RuntimeError("Load a design first.")
points = []
def add_point(value):
    if isinstance(value, dict):
        x, y = value.get("x"), value.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and math.isfinite(x) and math.isfinite(y):
            points.append((float(x), float(y)))
for collection in ("tracks", "vias", "pads"):
    for item in design.get(collection, []):
        if isinstance(item, dict):
            for key in ("start", "end", "position", "center"):
                add_point(item.get(key))
if not points:
    print("No recognized finite XY points were supplied.")
else:
    xs, ys = zip(*points)
    print("Bounds (design units):", min(xs), min(ys), max(xs), max(ys))
    print("Sampled points:", len(points))
`),
  entry("design-issues", "Import issue review", "Design inspection", "Group importer issues by severity while preserving the original messages.", ["Loaded design"], `# Review reported import issues; absence of issues is not proof of complete import.
from collections import Counter
design = spike.design
if not isinstance(design, dict):
    raise RuntimeError("Load a design first.")
issues = design.get("issues", [])
issues = issues if isinstance(issues, list) else []
levels = Counter(str(item.get("severity", "unspecified")) for item in issues if isinstance(item, dict))
print("Issue severities:", dict(levels))
for item in issues:
    if isinstance(item, dict):
        print(f"[{item.get('severity', 'unspecified')}] {item.get('message', item)}")
`),
  entry("worker-capabilities", "Worker capability ledger", "Basics", "Print the worker's declared capability ledger for feature discovery.", [], `# Query declarations only; runtime dependencies can still make a path unavailable.
ledger = spike.call("capability_ledger")
print("Contract:", ledger.get("contract", "unknown") if isinstance(ledger, dict) else "unexpected")
if isinstance(ledger, dict):
    for key, value in sorted(ledger.items()):
        if key != "contract":
            print(key, value)
`),
  entry("solver-catalog", "Solver catalog", "Basics", "Inspect registered solver descriptors before preparing an analysis.", [], `# A catalog entry is not evidence that a runtime is installed or a model is validated.
catalog = spike.call("list_solvers")
print("Solver catalog:")
if isinstance(catalog, dict):
    for item in catalog.get("solvers", []):
        if isinstance(item, dict):
            print(item.get("id", "<unknown>"), item.get("status", item.get("model_status", "unspecified")))
else:
    print(catalog)
`),
  entry("dc-path-setup", "DC source-load setup", "PI - DC", "Create and validate an explicit DC setup draft without launching a solve.", ["Loaded design", "Source/load net and terminals"], `# Fill every TODO from the loaded design, then pass this object to the documented DC preflight workflow.
design = spike.design
if not isinstance(design, dict):
    raise RuntimeError("Load the target board first.")
setup = {
    "design_id": design.get("design_id"),
    "net_id": "TODO_NET_ID",
    "source": {"terminal_id": "TODO_SOURCE_TERMINAL", "voltage_v": None},
    "loads": [{"terminal_id": "TODO_LOAD_TERMINAL", "current_a": None}],
}
missing = []
if setup["net_id"].startswith("TODO_"): missing.append("net_id")
if setup["source"]["terminal_id"].startswith("TODO_"): missing.append("source terminal")
if setup["source"]["voltage_v"] is None: missing.append("source voltage_v")
if any(load["current_a"] is None for load in setup["loads"]): missing.append("load current_a")
print("DC setup draft:", setup)
print("Required values still missing:", ", ".join(missing) or "none")
`),
  entry("dc-result-review", "DC result review", "PI - DC", "Review status, model qualification, issues, and returned DC summary fields.", ["Selected DC result"], `# Read only fields returned by the selected analysis.
context = spike.results
if not isinstance(context, dict):
    raise RuntimeError("Select a result before running this script.")
print("Context complete:", context.get("complete", False))
result = context.get("result")
if not isinstance(result, dict):
    raise RuntimeError("The selected context has no complete result payload.")
print("Status:", result.get("status", "unknown"))
print("Mode:", result.get("mode", "unknown"))
print("Model status:", result.get("model_status", "unknown"))
print("Summary:", result.get("summary", {}))
for issue in result.get("issues", []):
    print("ISSUE", issue)
`),
  entry("dc-drop-samples", "Voltage drop sample review", "PI - DC", "Inspect returned scalar fields and report finite sample ranges without inventing interpolation.", ["Selected result with scalar fields"], `# Review explicit samples only; this script does not interpolate between them.
import math
context = spike.results
result = context.get("result") if isinstance(context, dict) else None
if not isinstance(result, dict):
    raise RuntimeError("Select a completed field result.")
visual = result.get("fields", {}).get("visualization", {})
fields = visual.get("scalar_fields", {}) if isinstance(visual, dict) else {}
for name, samples in fields.items() if isinstance(fields, dict) else []:
    values = [float(row["value"]) for row in samples if isinstance(row, dict) and isinstance(row.get("value"), (int, float)) and math.isfinite(row["value"])]
    print(name, "samples=", len(values), "range=", (min(values), max(values)) if values else "none")
`),
  entry("ac-pi-setup", "AC PI sweep setup", "PI - AC", "Prepare explicit frequency and impedance inputs for the AC PI workflow.", ["Loaded design", "Selected power net", "Validated source/load models"], `# Configuration draft only. Review units and replace every TODO before using the AC PI panel or worker contract.
design = spike.design
if not isinstance(design, dict):
    raise RuntimeError("Load the target board first.")
setup = {
    "design_id": design.get("design_id"),
    "net_id": "TODO_NET_ID",
    "frequencies_hz": [],
    "source_impedance_ohm": None,
    "load_model": "TODO_VALIDATED_LOAD_MODEL",
}
missing = [key for key, value in setup.items() if value is None or value == [] or str(value).startswith("TODO_")]
print(setup)
print("Required inputs still missing:", missing)
`),
  entry("pdn-target-draft", "PDN target draft", "PI - AC", "Calculate a target impedance from explicit voltage ripple and current-step requirements.", ["Engineering ripple/current requirements"], `# Enter engineering requirements; None prevents accidental use of example values.
ripple_v = None       # TODO: allowed rail ripple in volts
current_step_a = None # TODO: worst-case load step in amperes
if ripple_v is None or current_step_a is None:
    print("Set ripple_v and current_step_a from requirements.")
elif ripple_v <= 0 or current_step_a <= 0:
    raise ValueError("Both requirements must be positive.")
else:
    print("Target impedance (ohm):", ripple_v / current_step_a)
`),
  entry("circuit-workspace-draft", "Circuit workspace draft", "Circuits and parasitics", "Draft a bounded circuit analysis request with explicit netlist and analysis placeholders.", ["Reviewed circuit/netlist", "Chosen analysis limits"], `# This draft never runs until the netlist and analysis are deliberately supplied.
request = {
    "netlist": "TODO_REVIEWED_NETLIST",
    "analysis": {"kind": "TODO_DC_AC_OR_TRANSIENT", "limits": {}},
    "models": [],
}
missing = [key for key, value in (("netlist", request["netlist"]), ("analysis kind", request["analysis"]["kind"])) if str(value).startswith("TODO_")]
print("Circuit request:", request)
print("Missing:", missing)
`),
  entry("parasitic-inventory", "Parasitic capability inventory", "Circuits and parasitics", "Discover PEEC and external engine registrations without claiming extraction validity.", [], `# Registration and capability metadata do not establish convergence or correlation.
for method in ("list_solvers", "list_external_engines"):
    print("\\n", method)
    reply = spike.call(method)
    print(reply)
`),
  entry("result-network-review", "Network data review", "Circuits and parasitics", "Inspect returned network keys, ports, and frequency counts.", ["Selected network result"], `# Report the shape supplied by the solver; no missing network terms are synthesized.
context = spike.results
result = context.get("result") if isinstance(context, dict) else None
if not isinstance(result, dict):
    raise RuntimeError("Select a completed result.")
networks = result.get("networks", {})
if not isinstance(networks, dict) or not networks:
    print("No network data returned.")
else:
    for name, network in networks.items():
        if isinstance(network, dict):
            print(name, "keys=", sorted(network.keys()))
            for key in ("ports", "frequencies_hz"):
                value = network.get(key)
                if isinstance(value, list): print(" ", key, len(value))
`),
  entry("si-channel-setup", "Uniform channel setup", "SI - channels", "Prepare explicit channel dimensions, materials, termination, and sweep inputs.", ["Reviewed stackup", "Driver/receiver assumptions"], `# Replace None/TODO values before submitting through the SI workflow.
channel = {
    "length_mm": None,
    "width_mm": None,
    "height_to_reference_mm": None,
    "relative_permittivity": None,
    "loss_tangent": None,
    "source_ohm": None,
    "load_ohm": None,
    "frequencies_hz": [],
}
missing = [key for key, value in channel.items() if value is None or value == []]
print("Channel setup:", channel)
print("Required values still missing:", missing)
`),
  entry("crosstalk-setup", "Crosstalk setup", "SI - crosstalk", "Draft victim/aggressor selection and coupling assumptions for review.", ["Loaded design", "Victim and aggressor net IDs", "Validated geometry/model path"], `# Net names alone do not define coupling. Supply stable net IDs and a validated model path.
design = spike.design
if not isinstance(design, dict):
    raise RuntimeError("Load the target board first.")
setup = {
    "design_id": design.get("design_id"),
    "victim_net_id": "TODO_VICTIM_NET_ID",
    "aggressor_net_ids": ["TODO_AGGRESSOR_NET_ID"],
    "edge_time_s": None,
    "model_path": "TODO_SUPPORTED_MODEL_PATH",
}
print(setup)
print("This is a setup preview; no NEXT/FEXT solve was launched.")
`),
  entry("protocol-catalog", "SI workflow catalog", "SI - protocols", "Inspect supported SI workflows and protocol descriptors before selecting a test.", [], `# Catalog entries describe available orchestration; qualification remains result-specific.
catalog = spike.call("si_workflow_catalog")
print(catalog)
`),
  entry("eye-result-review", "Eye result evidence", "SI - protocols", "Review returned eye metadata, issues, and provenance without asserting protocol compliance.", ["Selected SI result"], `# Eye availability depends on a supported channel plus explicit timing and endpoint models.
context = spike.results
result = context.get("result") if isinstance(context, dict) else None
if not isinstance(result, dict):
    raise RuntimeError("Select a completed SI result.")
print("Model status:", result.get("model_status", "unknown"))
print("Summary:", result.get("summary", {}))
print("Network keys:", sorted(result.get("networks", {}).keys()) if isinstance(result.get("networks"), dict) else [])
print("Issues:")
for issue in result.get("issues", []): print(" ", issue)
`),
  entry("thermal-steady-setup", "Steady thermal setup", "Thermal - steady", "Draft explicit ambient, convection, power, and material inputs for a thermal case.", ["Loaded design", "Power map", "Boundary conditions"], `# Values are deliberately unset because guessed thermal boundaries produce misleading temperatures.
design = spike.design
if not isinstance(design, dict):
    raise RuntimeError("Load the target board first.")
setup = {
    "design_id": design.get("design_id"),
    "ambient_c": None,
    "top_convection_w_m2k": None,
    "bottom_convection_w_m2k": None,
    "component_power_w": {},
    "material_source": "TODO_REVIEWED_STACKUP_OR_COMPACT_MODEL",
}
print(setup)
print("Missing boundary values:", [k for k, v in setup.items() if v is None or str(v).startswith("TODO_")])
`),
  entry("thermal-transient-setup", "Transient thermal setup", "Thermal - transient", "Prepare duration, time step, initial condition, and power waveform placeholders.", ["Validated thermal model", "Power waveform", "Boundary conditions"], `# Setup preview only; stability and timestep limits belong to the selected solver contract.
setup = {
    "initial_temperature_c": None,
    "duration_s": None,
    "time_step_s": None,
    "power_waveform": [],
    "boundary_conditions": {},
}
missing = [key for key, value in setup.items() if value is None or value == [] or value == {}]
print("Transient thermal setup:", setup)
print("Required inputs still missing:", missing)
`),
  entry("board-thermal-review", "Board thermal field review", "Thermal - board", "Inspect explicit returned temperature samples and model status.", ["Selected board thermal result"], `# Board and layered thermal paths are approximate; retain the returned model status and issues.
import math
context = spike.results
result = context.get("result") if isinstance(context, dict) else None
if not isinstance(result, dict):
    raise RuntimeError("Select a thermal result.")
print("Model status:", result.get("model_status", "unknown"))
print("Summary:", result.get("summary", {}))
for issue in result.get("issues", []): print("ISSUE", issue)
fields = result.get("fields", {})
print("Returned field groups:", sorted(fields.keys()) if isinstance(fields, dict) else [])
`),
  entry("assembly-thermal-setup", "Assembly thermal setup", "Thermal - assembly", "Draft occurrence-specific power and interface assumptions for multiboard review.", ["Saved assembly", "Board occurrence IDs", "Interface conductances"], `# Equal net or board names do not establish assembly identity; use occurrence IDs from the saved assembly.
setup = {
    "assembly_id": "TODO_ASSEMBLY_ID",
    "board_occurrences": [],
    "power_by_occurrence_w": {},
    "interface_conductance_w_k": {},
    "ambient_c": None,
}
print(setup)
print("No assembly solve was launched; review contacts and occurrence identity first.")
`),
  entry("emi-preflight-draft", "EMI screening preflight draft", "EM and EMI", "Prepare geometry coverage, frequency, source, and observation inputs for screening.", ["Loaded design", "Explicit source and frequency plan"], `# Screening results are not compliance certification or full-wave qualification.
design = spike.design
if not isinstance(design, dict):
    raise RuntimeError("Load the target board first.")
setup = {
    "design_id": design.get("design_id"),
    "net_ids": [],
    "frequencies_hz": [],
    "source_definition": None,
    "observation_definition": None,
}
print(setup)
print("Required before preflight: net IDs, frequencies, source, observation definition.")
`),
  entry("em-result-review", "EM result evidence", "EM and EMI", "Review admitted E/H, Poynting, and radiation result keys with provenance.", ["Selected EM result"], `# Displayed contours are visualization products and do not add solved samples.
context = spike.results
result = context.get("result") if isinstance(context, dict) else None
if not isinstance(result, dict):
    raise RuntimeError("Select an admitted EM result.")
print("Status/model:", result.get("status"), result.get("model_status"))
print("Provenance:", result.get("provenance", {}))
fields = result.get("fields", {})
print("Field groups:", sorted(fields.keys()) if isinstance(fields, dict) else [])
print("Network groups:", sorted(result.get("networks", {}).keys()) if isinstance(result.get("networks"), dict) else [])
for issue in result.get("issues", []): print("ISSUE", issue)
`),
  entry("mesh-capabilities", "Mesh capability probes", "EM and EMI", "Inspect internal and focused-volume mesh capability responses.", [], `# A successful capability probe is preparation evidence, not field-solver convergence.
for method in ("internal_mesh_capabilities", "pcb_volume_mesh_capabilities"):
    try:
        print(method, spike.call(method))
    except Exception as exc:
        print(method, "unavailable:", exc)
`),
  entry("extension-catalog", "Extension catalog", "Extensions", "List installed contributions, trust state, permissions, and declared capabilities.", [], `# Extensions require session trust before invocation and retain their own validation status.
catalog = spike.extensions()
for extension in catalog.get("extensions", []) if isinstance(catalog, dict) else []:
    print("\\n", extension.get("id", "<unknown>"))
    print(" trusted:", extension.get("trusted", False))
    print(" permissions:", extension.get("permissions", []))
    print(" contributions:", extension.get("contributions", []))
`),
  entry("extension-invocation-draft", "Extension invocation draft", "Extensions", "Build an explicit trusted-extension invocation after reviewing its catalog entry.", ["Installed and session-trusted extension", "Reviewed contribution parameters"], `# Replace placeholders only after inspecting spike.extensions().
extension_id = "TODO_EXTENSION_ID"
contribution_id = "TODO_CONTRIBUTION_ID"
parameters = {}  # TODO: exact parameters declared by the contribution
if extension_id.startswith("TODO_") or contribution_id.startswith("TODO_"):
    print("Set extension_id and contribution_id from the installed catalog.")
else:
    reply = spike.invoke_extension(extension_id, contribution_id, parameters)
    print(reply)
`),
  entry("publish-field-draft", "Publish scalar field draft", "Extensions", "Validate user-provided samples before publishing an unvalidated board field.", ["Loaded design", "Actual finite field samples", "Known units and provenance"], `# Supply actual computed/imported samples. Never substitute illustrative values.
import math
name = "TODO_FIELD_NAME_WITH_UNITS"
samples = []  # TODO: [{'x_mm': ..., 'y_mm': ..., 'layer': 'F.Cu', 'value': ...}]
if spike.design is None:
    raise RuntimeError("Load the matching board before publishing.")
if name.startswith("TODO_") or not samples:
    print("Set a quantity name and actual samples; nothing was published.")
else:
    for row in samples:
        if not all(isinstance(row.get(k), (int, float)) and math.isfinite(row[k]) for k in ("x_mm", "y_mm", "value")):
            raise ValueError("Every sample needs finite x_mm, y_mm, and value.")
    spike.publish_scalar_field(name, samples, model_status="unvalidated", summary={"source": "user script"})
`),
  entry("multiboard-plan-draft", "Multiboard study draft", "Multiboard", "Prepare assembly identity, explicit connector mappings, and requested independent/coupled scope.", ["Saved assembly", "Occurrence IDs", "Explicit connector pin map"], `# Net-name equality does not connect boards. Preserve occurrence identity and explicit pin mappings.
study = {
    "assembly_id": "TODO_ASSEMBLY_ID",
    "board_occurrence_ids": [],
    "connector_pin_maps": [],
    "requested_scope": "TODO_INDEPENDENT_OR_SUPPORTED_REDUCED_COUPLING",
}
print(study)
print("This draft does not claim cross-board field coupling or launch an analysis.")
`),
  entry("multiboard-result-review", "Multiboard result review", "Multiboard", "Inspect board occurrence identity, execution strategy, qualification, and issues.", ["Selected multiboard result"], `# Review the returned scope; independent batches do not imply coupled assembly physics.
context = spike.results
result = context.get("result") if isinstance(context, dict) else None
if not isinstance(result, dict):
    raise RuntimeError("Select a multiboard result.")
print("Mode:", result.get("mode", "unknown"))
print("Model status:", result.get("model_status", "unknown"))
print("Summary:", result.get("summary", {}))
print("Provenance:", result.get("provenance", {}))
for issue in result.get("issues", []): print("ISSUE", issue)
`),
  entry("result-overview", "Selected result overview", "Result review", "Print the selected result contract, status, mode, summary, issues, and provenance.", ["Selected result"], `# A compact first-pass audit of the exact selected result.
context = spike.results
if not isinstance(context, dict):
    raise RuntimeError("Select a result first.")
print("Context contract:", context.get("contract", "unknown"))
print("Complete:", context.get("complete", False))
result = context.get("result")
if not isinstance(result, dict):
    print("Preview:", context.get("preview"))
else:
    for key in ("contract", "analysis_id", "status", "mode", "model_status", "summary", "provenance"):
        print(f"{key}:", result.get(key))
    print("Issues:", result.get("issues", []))
`),
  entry("result-json-export", "Export selected result JSON", "Export", "Write the selected complete result to a chosen local JSON path with finite-value validation.", ["Selected complete result", "Explicit writable output path"], `# Set an explicit destination. Scripts have ordinary local file access.
import json
from pathlib import Path
output_path = None  # TODO: Path(r"C:\\path\\to\\result.json")
context = spike.results
result = context.get("result") if isinstance(context, dict) else None
if not isinstance(result, dict):
    raise RuntimeError("Select a complete result before export.")
if output_path is None:
    print("Set output_path explicitly; no file was written.")
else:
    path = Path(output_path).expanduser().resolve()
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    path.write_text(payload + "\\n", encoding="utf-8")
    print("Wrote", path, "bytes=", len(payload.encode("utf-8")))
`),
  entry("scalar-field-csv-export", "Export scalar field CSV", "Export", "Export one explicit returned scalar field without interpolating or filling missing samples.", ["Selected result with scalar field", "Field name", "Explicit writable output path"], `# Set field_name and output_path after inspecting the result.
import csv
from pathlib import Path
field_name = "TODO_FIELD_NAME"
output_path = None  # TODO: Path(r"C:\\path\\to\\samples.csv")
context = spike.results
result = context.get("result") if isinstance(context, dict) else None
fields = result.get("fields", {}).get("visualization", {}).get("scalar_fields", {}) if isinstance(result, dict) else {}
samples = fields.get(field_name) if isinstance(fields, dict) else None
if not isinstance(samples, list):
    print("Available scalar fields:", sorted(fields.keys()) if isinstance(fields, dict) else [])
elif output_path is None:
    print("Set output_path explicitly; no file was written.")
else:
    keys = sorted({key for row in samples if isinstance(row, dict) for key in row})
    with Path(output_path).expanduser().resolve().open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader(); writer.writerows(samples)
    print("Wrote samples:", len(samples))
`),
  entry("parameter-sweep-plan", "Parameter sweep plan", "Parameter sweeps", "Create a bounded Cartesian sweep manifest without launching solver jobs.", ["Reviewed parameter ranges", "Supported worker request contract"], `# Keep sweeps bounded and bind each eventual run to the design revision and solver version.
from itertools import product
axes = {
    "TODO_PARAMETER_A": [],
    "TODO_PARAMETER_B": [],
}
if any(name.startswith("TODO_") or not values for name, values in axes.items()):
    print("Replace parameter names and provide reviewed values.")
else:
    names = list(axes)
    cases = [dict(zip(names, values)) for values in product(*(axes[name] for name in names))]
    if len(cases) > 100:
        raise ValueError("Sweep exceeds the 100-case workspace safety limit.")
    for index, case in enumerate(cases): print(index, case)
`),
  entry("sweep-result-compare", "Compare saved sweep summaries", "Parameter sweeps", "Compare finite scalar metrics from user-supplied result JSON files.", ["Result JSON files from equivalent analysis contracts"], `# Supply files from a controlled sweep; verify comparable design, solver, units, and model status.
import json, math
from pathlib import Path
paths = []  # TODO: [Path(r"..."), Path(r"...")]
metric_key = "TODO_SUMMARY_METRIC"
rows = []
for raw_path in paths:
    data = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    value = data.get("summary", {}).get(metric_key)
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{raw_path}: missing finite summary metric {metric_key}")
    rows.append((str(raw_path), value, data.get("model_status"), data.get("provenance", {})))
for row in rows: print(row)
if not rows: print("Set paths and metric_key; no comparison was performed.")
`),
  entry("batch-worker-preflight", "Batch preflight skeleton", "Parameter sweeps", "Run a chosen non-solving preflight method over explicit bounded cases.", ["Known registered preflight method", "Reviewed case payloads"], `# Use only a documented preflight/validation method. This skeleton refuses run/solve method names.
method = "TODO_PREFLIGHT_METHOD"
cases = []  # TODO: list of worker parameter dictionaries
if method.startswith("TODO_"):
    print("Set a registered preflight method and explicit cases.")
elif any(word in method.lower() for word in ("run", "solve", "execute")):
    raise ValueError("This template accepts preflight/validation methods only.")
elif len(cases) > 100:
    raise ValueError("Batch exceeds 100 cases.")
else:
    for index, params in enumerate(cases):
        print(index, spike.call(method, params))
`),
  entry("run-dc-request", "Run DC analysis from request file", "PI - DC", "Execute the registered analysis path using a reviewed DC AnalysisSpec JSON parameter object.", ["Loaded matching design", "Reviewed JSON with spec.mode dc and complete solver inputs"], requestRunner("run_analysis", { attachDesign: true, requiredKey: "spec", expectedMode: "dc" })),
  entry("run-ac-request", "Run AC analysis from request file", "PI - AC", "Execute the registered analysis path using a reviewed AC AnalysisSpec JSON parameter object.", ["Loaded matching design", "Reviewed JSON with spec.mode ac and complete solver inputs"], requestRunner("run_analysis", { attachDesign: true, requiredKey: "spec", expectedMode: "ac" })),
  entry("run-si-workflow-request", "Run SI workflow from request file", "SI - channels", "Run the validated SI workflow envelope from a reviewed request file.", ["Loaded matching design", "Reviewed JSON with request from the SI workflow"], requestRunner("run_si_workflow", { attachDesign: true, requiredKey: "request" })),
  entry("run-si-channel-request", "Run uniform SI channel from request file", "SI - channels", "Run quasi-TEM uniform-channel analysis from its reviewed request envelope.", ["Loaded matching design", "Reviewed uniform-channel request JSON", "Complete stackup and endpoint assumptions"], requestRunner("run_si_uniform_channel", { attachDesign: true, requiredKey: "request" })),
  entry("run-board-thermal-request", "Run board thermal analysis from request file", "Thermal - board", "Run the approximate board thermal path with reviewed power, material, and boundary inputs.", ["Loaded matching design", "Reviewed board thermal request JSON", "Power map and boundary conditions"], requestRunner("run_board_thermal", { attachDesign: true, requiredKey: "request" })),
  entry("run-emi-preflight-request", "Run EMI preflight from request file", "EM and EMI", "Validate a reviewed EMI screening setup against the loaded design and solver catalog.", ["Loaded matching design", "Reviewed JSON with EMI setup"], requestRunner("emi_preflight", { attachDesign: true, requiredKey: "setup" })),
  entry("run-emi-screen-request", "Run EMI screening from request file", "EM and EMI", "Execute the bounded EMI screening method after its reviewed setup passes worker validation.", ["Loaded matching design", "Reviewed JSON with complete EMI setup", "Accepted screening limitations"], requestRunner("emi_screen", { attachDesign: true, requiredKey: "setup" })),
  entry("run-multiboard-circuit-request", "Run multiboard circuit from request file", "Multiboard", "Run the reduced multiboard circuit contract from an occurrence-specific request.", ["Reviewed multiboard circuit request JSON", "Explicit connector and occurrence identity"], requestRunner("run_multiboard_circuit", { requiredKey: "request" })),
  entry("run-multiboard-si-request", "Run multiboard SI batch from request file", "Multiboard", "Run the independent per-board SI batch contract from a reviewed request.", ["Reviewed independent SI batch request JSON", "Per-board designs and cases"], requestRunner("run_multiboard_si_independent_batch", { requiredKey: "request" })),
  entry("run-multiboard-thermal-request", "Run multiboard thermal from request file", "Thermal - assembly", "Run the reduced multiboard thermal contract from reviewed occurrence and interface inputs.", ["Reviewed multiboard thermal request JSON", "Occurrence power and thermal interfaces"], requestRunner("run_multiboard_thermal", { requiredKey: "request" })),
  entry("run-multiboard-em-request", "Run multiboard EM from request file", "Multiboard", "Run the supported reduced multiboard EM contract without implying full-wave qualification.", ["Reviewed multiboard EM request JSON", "Explicit excitation and occurrence mapping", "Accepted model limitations"], requestRunner("run_multiboard_em", { requiredKey: "request" })),
  entry("working-directory", "Working directory and packages", "Basics", "Inspect the child process working directory and optional package availability.", [], `# Scripts run as local Python; package availability depends on the SPIKE runtime environment.
import importlib.util
from pathlib import Path
print("Working directory:", Path.cwd())
for package in ("numpy", "scipy", "pandas", "matplotlib"):
    print(package, "available" if importlib.util.find_spec(package) else "not installed")
`),
];

export const PYTHON_STARTER = PYTHON_TEMPLATES[0].code;
