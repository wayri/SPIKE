import {
  AlertTriangle, Boxes, CircuitBoard, FileOutput, FolderOpen, Link2, ListChecks,
  Network, Play, Plus, Search, ShieldCheck, Trash2, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { normalizeSolverResult, SolverResultBundle } from "./analysisResults";
import type { ParsedBoard } from "./boardParser";
import type { BoardObject } from "./BoardViewport";
import { previewViewportTarget } from "./BoardViewport";
import { numericExtent } from "./numericRange";
import { OwnedCircuitResultView, parseOwnedProbeDescriptors, type OwnedCircuitResult } from "./OwnedSpiceResult";
import {
  componentPads, createSpiceAssignment, parasiticsFromResult, SpiceAssignment,
  SpiceModel, SpiceNetlistPreview, SpiceParasitic, SpiceWorkspace,
} from "./spiceWorkspace";
import { openNativeTextFile, runLocalWorker, saveNativeTextFile } from "./workerBridge";
import type { AssemblyAnalysisScope, AssemblyWorkload } from "./assemblyAdmission";

type Page = "setup" | "models" | "assignments" | "parasitics" | "run";
type RunEngine = "native_mna" | "peec_mna" | "owned_spice" | "ngspice";
const numberOrZero = (value: string) => Number.isFinite(Number(value)) ? Number(value) : 0;
const humanize = (value: string | undefined) => value?.replace(/_/g, " ") ?? "";
const modelLabel = (model: SpiceModel) => model.kind === "primitive" ? humanize(model.primitive) : model.subcircuit_name;
const runEngineLabel: Record<RunEngine, string> = {
  native_mna: "SPIKE native MNA",
  peec_mna: "PEEC + native MNA",
  owned_spice: "SPIKES owned engine",
  ngspice: "External ngspice",
};
const ownedLimits = {
  maximum_netlist_bytes: 2 * 1024 * 1024,
  maximum_result_bytes: 64 * 1024 * 1024,
  maximum_probes: 256,
};

export default function SpiceWorkbench({
  design, board, selection, workspace, setWorkspace, analysisResult, onRequireAdmission, onResult, onStatus, onClose, initialEngine = "native_mna",
}: {
  design: Record<string, unknown> | null;
  board: ParsedBoard | null;
  selection: BoardObject | null;
  workspace: SpiceWorkspace;
  setWorkspace: (workspace: SpiceWorkspace) => void;
  analysisResult: SolverResultBundle | null;
  onRequireAdmission: (workload: AssemblyWorkload) => Promise<AssemblyAnalysisScope | null>;
  onResult: (result: SolverResultBundle) => void;
  onStatus: (message: string) => void;
  onClose: () => void;
  initialEngine?: RunEngine;
}) {
  const [page, setPage] = useState<Page>("setup");
  const [query, setQuery] = useState("");
  const [selectedModelId, setSelectedModelId] = useState(workspace.models[0]?.id ?? "");
  const [selectedComponentRef, setSelectedComponentRef] = useState(selection?.ref ?? board?.components[0]?.ref ?? "");
  const [selectedAssignmentId, setSelectedAssignmentId] = useState(workspace.assignments[0]?.id ?? "");
  const [preview, setPreview] = useState<SpiceNetlistPreview | null>(null);
  const [timeout, setTimeoutValue] = useState(120);
  const [runEngine, setRunEngine] = useState<RunEngine>(initialEngine);
  const [overlayEnabled, setOverlayEnabled] = useState(true);
  const [overlayVector, setOverlayVector] = useState("v(out)");
  const [overlayQuantity, setOverlayQuantity] = useState("voltage_v");
  const [ownedProbeText, setOwnedProbeText] = useState("");
  const [ownedResult, setOwnedResult] = useState<OwnedCircuitResult | null>(null);
  const [running, setRunning] = useState(false);
  const workspaceRef = useRef(workspace);
  const activeRunId = useRef<string | null>(null);
  const [diagnostic, setDiagnostic] = useState("Compose the workspace to validate models, pin mappings, parasitic endpoints, and analysis limits.");
  const selectedModel = workspace.models.find(model => model.id === selectedModelId) ?? workspace.models[0];
  const selectedAssignment = workspace.assignments.find(item => item.id === selectedAssignmentId);
  const selectedComponent = board?.components.find(component => component.ref === selectedComponentRef);
  const boardNets = useMemo(() => [...new Set(Object.values(board?.nets ?? {}).filter(Boolean))].sort(), [board]);
  const filteredComponents = useMemo(() => board?.components.filter(component =>
    `${component.ref} ${component.value} ${component.library}`.toLowerCase().includes(query.toLowerCase())).slice(0, 1000) ?? [], [board, query]);
  useEffect(() => { workspaceRef.current = workspace; }, [workspace]);
  useEffect(() => () => { activeRunId.current = null; }, []);
  const set = (patch: Partial<SpiceWorkspace>) => {
    if (activeRunId.current) { setDiagnostic("Workspace editing is locked while a circuit run is active."); return; }
    setWorkspace({ ...workspace, ...patch }); setPreview(null); setOwnedResult(null);
  };
  const patchModel = (patch: Partial<SpiceModel>) => {
    if (!selectedModel) return;
    set({ models: workspace.models.map(model => model.id === selectedModel.id ? { ...model, ...patch } : model) });
  };
  const patchAssignment = (patch: Partial<SpiceAssignment>) => {
    if (!selectedAssignment) return;
    set({ assignments: workspace.assignments.map(item => item.id === selectedAssignment.id ? { ...item, ...patch } : item) });
  };
  const patchParasitic = (id: string, patch: Partial<SpiceParasitic>) =>
    set({ parasitics: workspace.parasitics.map(item => item.id === id ? { ...item, ...patch } : item) });

  const importSubcircuit = async () => {
    const file = await openNativeTextFile("netlist");
    if (!file) return;
    const declaration = file.contents.match(/^\s*\.subckt\s+([^\s]+)\s+(.+)$/im);
    if (!declaration) { setDiagnostic("The selected file does not contain a .subckt declaration."); return; }
    const name = declaration[1];
    const model: SpiceModel = {
      id: `model_${crypto.randomUUID().replace(/-/g, "_")}`,
      name: file.fileName,
      kind: "subcircuit",
      subcircuit_name: name,
      pins: declaration[2].trim().split(/\s+/),
      source: file.contents,
      origin: "imported",
    };
    set({ models: [...workspace.models, model] });
    setSelectedModelId(model.id); setPage("models"); setDiagnostic(`Imported inline subcircuit ${name}; compose to run security and pin checks.`);
  };
  const addProjectModel = () => {
    const model: SpiceModel = { id: `model_${crypto.randomUUID().replace(/-/g, "_")}`, name: "New subcircuit", kind: "subcircuit", subcircuit_name: "new_model", pins: ["in", "out", "gnd"], source: ".subckt new_model in out gnd\n* Add reviewed elements here\n.ends new_model", origin: "project" };
    set({ models: [...workspace.models, model] }); setSelectedModelId(model.id);
  };
  const assignModel = () => {
    if (!board || !selectedComponent || !selectedModel) { setDiagnostic("Select a board component and a model first."); return; }
    const assignment = createSpiceAssignment(board, selectedComponent, selectedModel);
    set({ assignments: [...workspace.assignments.filter(item => item.component_ref !== selectedComponent.ref), assignment] });
    setSelectedAssignmentId(assignment.id); setPage("assignments");
  };
  const changeAssignmentModel = (modelId: string) => {
    if (!board || !selectedAssignment) return;
    const component = board.components.find(item => item.ref === selectedAssignment.component_ref);
    const model = workspace.models.find(item => item.id === modelId);
    if (!component || !model) return;
    const replacement = { ...createSpiceAssignment(board, component, model), id: selectedAssignment.id, ratings: selectedAssignment.ratings, vectors: selectedAssignment.vectors };
    set({ assignments: workspace.assignments.map(item => item.id === selectedAssignment.id ? replacement : item) });
  };
  const updatePin = (pin: string, patch: Partial<SpiceAssignment["pin_bindings"][number]>) => {
    if (!selectedAssignment) return;
    patchAssignment({ pin_bindings: selectedAssignment.pin_bindings.map(binding => binding.model_pin === pin ? { ...binding, ...patch } : binding) });
  };
  const usePad = (pin: string, padId: string) => {
    const pad = board?.pads.find(item => item.id === padId);
    updatePin(pin, { pad_id: padId, board_net: pad?.net ?? "", circuit_node: pad?.net ?? "" });
  };
  const importParasitics = () => {
    const imported = parasiticsFromResult(analysisResult, workspace.ground_node);
    if (!imported.length) { setDiagnostic("The current result has no explicit RLC extraction records."); return; }
    const ids = new Set(workspace.parasitics.map(item => item.id));
    set({ parasitics: [...workspace.parasitics, ...imported.filter(item => !ids.has(item.id))] });
    setDiagnostic(`Imported ${imported.length} RLC records. Review source/load circuit endpoints before running.`);
  };
  const compose = async (): Promise<SpiceNetlistPreview | null> => {
    if (!design) { onStatus("Import a design before composing circuit co-simulation"); return null; }
    try {
      const response = await runLocalWorker({ method: "compose_spice_workspace", params: { design, workspace } });
      const next = response.result as SpiceNetlistPreview | undefined;
      if (!response.ok || !next) throw new Error(response.error ?? "SPICE workspace composition returned no result");
      setPreview(next);
      const first = next.validation.issues[0] ?? next.validation.warnings[0];
      setDiagnostic(first?.message ?? `Netlist ready: ${next.validation.counts.assignments} assignments and ${next.validation.counts.parasitics} parasitic blocks.`);
      return next;
    } catch (error) {
      const message = error instanceof Error ? error.message : "SPICE workspace composition failed";
      setDiagnostic(message); onStatus(message); return null;
    }
  };
  const save = async () => {
    const next = preview?.status === "ready" ? preview : await compose();
    if (!next?.netlist) return;
    const path = await saveNativeTextFile("spike-circuit.cir", next.netlist, "netlist");
    if (path) setDiagnostic(`Saved ${path}`);
  };
  const exportOwnedResult = async () => {
    if (!ownedResult) return;
    const path = await saveNativeTextFile("spikes-owned-circuit-result.json", JSON.stringify(ownedResult, null, 2), "result");
    if (path) setDiagnostic(`Saved full owned circuit result to ${path}`);
  };
  const run = async () => {
    if (!design) { onStatus("Import a design before running circuit analysis"); return; }
    if (activeRunId.current) return;
    if (runEngine === "ngspice" && overlayEnabled && !selection?.position) {
      onStatus("Select a board point or disable viewport binding before running ngspice");
      return;
    }
    const runId = crypto.randomUUID();
    const workspaceSnapshot = JSON.stringify(workspace);
    activeRunId.current = runId;
    setRunning(true);
    onStatus(`Running ${runEngineLabel[runEngine]}`);
    try {
      const assemblyScope = await onRequireAdmission(workspace.analysis.mode === "operating_point" ? "pi_dc" : "pi_ac");
      if (activeRunId.current !== runId || workspaceSnapshot !== JSON.stringify(workspaceRef.current)) return;
      if (runEngine === "native_mna") {
        const response = await runLocalWorker({
          method: "run_spice_workspace_native_mna",
          params: { design, workspace, resource_limits: { time_limit_s: timeout }, assembly_scope: assemblyScope },
        });
        if (activeRunId.current !== runId || workspaceSnapshot !== JSON.stringify(workspaceRef.current)) return;
        const payload = response.result as Record<string, unknown> | undefined;
        if (!response.ok || !payload) throw new Error(response.error ?? "Native MNA returned no result");
        const result = normalizeSolverResult(payload.analysis_result);
        if (!result) {
          const compile = payload.compile as Record<string, unknown> | undefined;
          const issues = Array.isArray(compile?.issues) ? compile.issues as Array<Record<string, unknown>> : [];
          throw new Error(String(issues[0]?.message ?? "Native MNA workspace compilation was blocked"));
        }
        onResult(result);
        const issue = result.issues[0]?.message;
        setDiagnostic(issue ?? `SPIKE native MNA returned ${result.status}.`);
        onStatus(issue ?? `SPIKE native MNA ${result.status}`);
        return;
      }

      if (runEngine === "peec_mna") {
        const enabled = workspace.parasitics.filter(item => item.enabled);
        const sourceIds = new Set(enabled.map(item => item.source_result_id).filter(Boolean));
        const mappingsReady = enabled.length > 0 && enabled.every(item =>
          item.endpoint_reviewed && Number.isInteger(item.source_network_index));
        if (!analysisResult || sourceIds.size !== 1 || !sourceIds.has(analysisResult.analysis_id) || !mappingsReady) {
          throw new Error("PEEC-MNA iteration requires reviewed parasitics imported from one current PEEC extraction with preserved network mappings.");
        }
        const frequencies = analysisResult.parasitics.flatMap(item => item.impedance?.map(point => point.frequency_hz) ?? [])
          .filter(value => Number.isFinite(value) && value > 0);
        const frequencyExtent = numericExtent(frequencies, 1e3, 1e9);
        const extractedStartHz = frequencyExtent.minimum;
        const extractedStopHz = frequencyExtent.maximum;
        const startHz = workspace.analysis.mode === "ac" ? workspace.analysis.start_hz : extractedStartHz;
        const stopHz = workspace.analysis.mode === "ac" ? workspace.analysis.stop_hz : extractedStopHz;
        const frequencyPoints = Math.max(2, new Set(frequencies).size || 101);
        const response = await runLocalWorker({
          method: "run_field_circuit_cosimulation",
          params: {
            assembly_scope: assemblyScope,
            design,
            workspace,
            field_analysis_spec: {
              contract: "spike/v1",
              analysis_id: analysisResult.analysis_id,
              mode: "broadband_hf",
              solver_id: "spike.peec_2_5d",
              formulation: "peec_2_5d",
              required_capabilities: ["rlcg_extraction", "frequency_dependent_impedance"],
              net_names: [...new Set(enabled.map(item => item.net))],
              frequency_start_hz: startHz,
              frequency_stop_hz: stopHz,
              frequency_points: frequencyPoints,
              options: { extraction: "rlcg", return_visualization: true, network_contract: "spike/rlgc-network/v1" },
            },
            request: {
              contract: "spike/field-circuit-cosimulation-request/v1",
              request_id: `field-circuit-${Date.now()}`,
              maximum_iterations: 8,
              minimum_iterations: 2,
              relaxation: 0.5,
              parameter_relative_tolerance: 1e-3,
              circuit_relative_tolerance: 1e-3,
              absolute_floor: 1e-15,
              time_limit_s: timeout,
              resource_limits: { time_limit_s: timeout },
            },
          },
        });
        if (activeRunId.current !== runId || workspaceSnapshot !== JSON.stringify(workspaceRef.current)) return;
        const payload = response.result as Record<string, unknown> | undefined;
        if (!response.ok || !payload) throw new Error(response.error ?? "PEEC-MNA co-simulation returned no result");
        const circuit = payload.circuit as Record<string, unknown> | undefined;
        const result = normalizeSolverResult(circuit?.analysis_result);
        if (!result) {
          const issues = Array.isArray(payload.issues) ? payload.issues as Array<Record<string, unknown>> : [];
          throw new Error(String(issues[0]?.message ?? `PEEC-MNA co-simulation ${payload.status ?? "failed"}`));
        }
        onResult(result);
        const iterations = Number(payload.iteration_count ?? (Array.isArray(payload.iterations) ? payload.iterations.length : 0));
        const message = `${payload.converged ? "Converged" : "Stopped"} after ${iterations} PEEC-MNA iterations (${payload.model_status ?? "experimental"}).`;
        setDiagnostic(message); onStatus(message);
        return;
      }

      if (runEngine === "owned_spice") {
        const probes = parseOwnedProbeDescriptors(ownedProbeText);
        if (probes.length > ownedLimits.maximum_probes) throw new Error(`SPIKES owned engine accepts at most ${ownedLimits.maximum_probes} explicit probes.`);
        const request = {
          contract: "spike/owned-spice-workspace-request/v1",
          request_id: `owned-spice-${Date.now()}`,
          workspace,
          probes,
          resource_limits: ownedLimits,
        };
        const validation = await runLocalWorker({ method: "validate_owned_spice_workspace", params: { design, assembly_scope: assemblyScope, request } });
        const validated = validation.result as Record<string, unknown> | undefined;
        if (!validation.ok || !validated?.valid) {
          const issues = Array.isArray(validated?.issues) ? validated.issues as Array<Record<string, unknown>> : [];
          throw new Error(String(issues[0]?.message ?? validation.error ?? "SPIKES owned workspace validation was blocked"));
        }
        if (activeRunId.current !== runId || workspaceSnapshot !== JSON.stringify(workspaceRef.current)) return;
        const response = await runLocalWorker({ method: "run_owned_spice_workspace", params: { design, assembly_scope: assemblyScope, request } });
        const payload = response.result as OwnedCircuitResult | undefined;
        if (activeRunId.current !== runId || workspaceSnapshot !== JSON.stringify(workspaceRef.current)) return;
        if (!response.ok || !payload) throw new Error(response.error ?? "SPIKES owned engine returned no result");
        setOwnedResult(payload);
        const issue = payload.issues?.[0]?.message;
        setDiagnostic(issue ?? `SPIKES owned engine returned ${payload.status ?? "unknown"}. Circuit results are not projected onto the board.`);
        onStatus(issue ?? `SPIKES owned engine ${payload.status ?? "unknown"}`);
        return;
      }

      const composed = preview?.status === "ready" ? preview : await compose();
      if (!composed || composed.status !== "ready") { setPage("run"); return; }
      if (activeRunId.current !== runId || workspaceSnapshot !== JSON.stringify(workspaceRef.current)) return;
      const stressBindings = workspace.assignments.filter(item => item.enabled).map(item => ({
        component_id: item.id, reference: item.component_ref,
        voltage_vector: item.vectors?.voltage ?? "", current_vector: item.vectors?.current ?? "", power_vector: item.vectors?.power ?? "",
        ratings: item.ratings ?? {},
      }));
      const response = await runLocalWorker({ method: "run_analysis", params: { design, assembly_scope: assemblyScope, spec: {
        contract: "spike/v1", analysis_id: `spice-${Date.now()}`, mode: "spice", solver_id: "spike.ngspice",
        formulation: "modified_nodal_analysis", required_capabilities: ["spice_netlist"], options: {
          spice_netlist: composed.netlist,
          spice_workspace: { contract: workspace.contract, domain: workspace.domain, composer: composed.provenance, validation: composed.validation },
          timeout_seconds: timeout,
          component_stress_bindings: stressBindings,
          spice_overlay_bindings: overlayEnabled && selection?.position ? [{
            vector: overlayVector.trim(), quantity: overlayQuantity,
            x_mm: selection.position[0], y_mm: selection.position[1], z_mm: 0,
            layer: selection.layer ?? "", net: selection.net ?? "", element_id: selection.id,
          }] : [],
        },
      } } });
      if (activeRunId.current !== runId || workspaceSnapshot !== JSON.stringify(workspaceRef.current)) return;
      const result = normalizeSolverResult(response.result);
      if (!result) throw new Error(response.error ?? "ngspice returned no compatible result");
      onResult(result);
      const issue = result.issues[0]?.message;
      setDiagnostic(issue ?? `ngspice returned ${result.status}`); onStatus(issue ?? `ngspice ${result.status}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "ngspice execution failed";
      setDiagnostic(message); onStatus(message);
    } finally {
      if (activeRunId.current === runId) { activeRunId.current = null; setRunning(false); }
    }
  };

  const pages: { id: Page; label: string; icon: typeof CircuitBoard }[] = [
    { id: "setup", label: "Circuit", icon: Network }, { id: "models", label: "Models", icon: Boxes },
    { id: "assignments", label: "Parts & pins", icon: Link2 }, { id: "parasitics", label: "Parasitics", icon: CircuitBoard },
    { id: "run", label: "Validate & run", icon: ListChecks },
  ];
  const analysis = workspace.analysis;
  return <div className="modal-shade" role="dialog" aria-modal="true" aria-label="SPICE model assistant"><section className="spice-workbench spice-assistant">
    <header><div><CircuitBoard size={18} /><span><b>SPICE MODEL ASSISTANT</b><small>{workspace.contract} | shared PI / SI circuit co-simulation</small></span></div><button className="canvas-icon" disabled={running} onClick={onClose}><X size={16} /></button></header>
    <div className="spice-toolbar">
      {pages.map(item => { const Icon = item.icon; return <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => setPage(item.id)}><Icon size={13} />{item.label}</button>; })}
      <button onClick={() => void importSubcircuit()}><FolderOpen size={13} /> Import model</button>
      <button onClick={() => void save()}><FileOutput size={13} /> Export netlist</button>
      <span><ShieldCheck size={13} /> isolated execution</span>
    </div>

    <div className="spice-assistant-body">
      {page === "setup" && <section className="spice-setup-page">
        <div className="spice-section-heading"><div><b>Circuit definition</b><small>Choose domain, reference node, and analysis. Models and pin maps remain shared between PI and SI.</small></div></div>
        <div className="spice-form-grid">
          <label>Workspace name<input value={workspace.name} onChange={event => set({ name: event.target.value })} /></label>
          <label>Domain<select value={workspace.domain} onChange={event => set({ domain: event.target.value as "pi" | "si" })}><option value="pi">Power integrity</option><option value="si">Signal integrity</option></select></label>
          <label>Ground / return node<select value={workspace.ground_node} onChange={event => set({ ground_node: event.target.value })}><option value="">Select return</option>{boardNets.map(net => <option key={net}>{net}</option>)}</select></label>
          <label>Analysis<select value={analysis.mode} onChange={event => {
            const mode = event.target.value;
            set({ analysis: mode === "ac" ? { mode: "ac", start_hz: 1e3, stop_hz: 1e9, points_per_decade: 50 } : mode === "transient" ? { mode: "transient", time_step_s: 1e-6, stop_time_s: 10e-3 } : { mode: "operating_point" } });
          }}><option value="operating_point">Operating point</option><option value="ac">AC sweep</option><option value="transient">Transient</option></select></label>
          {analysis.mode === "ac" && <><label>Start frequency (Hz)<input type="number" min="0" value={analysis.start_hz} onChange={event => set({ analysis: { ...analysis, start_hz: numberOrZero(event.target.value) } })} /></label><label>Stop frequency (Hz)<input type="number" min="0" value={analysis.stop_hz} onChange={event => set({ analysis: { ...analysis, stop_hz: numberOrZero(event.target.value) } })} /></label><label>Points / decade<input type="number" min="1" max="10000" value={analysis.points_per_decade} onChange={event => set({ analysis: { ...analysis, points_per_decade: numberOrZero(event.target.value) } })} /></label></>}
          {analysis.mode === "transient" && <><label>Time step (s)<input type="number" min="0" step="any" value={analysis.time_step_s} onChange={event => set({ analysis: { ...analysis, time_step_s: numberOrZero(event.target.value) } })} /></label><label>Stop time (s)<input type="number" min="0" step="any" value={analysis.stop_time_s} onChange={event => set({ analysis: { ...analysis, stop_time_s: numberOrZero(event.target.value) } })} /></label></>}
        </div>
        <div className="spice-flow-summary"><div><b>{workspace.models.length}</b><span>models</span></div><i /><div><b>{workspace.assignments.length}</b><span>assigned parts</span></div><i /><div><b>{workspace.parasitics.length}</b><span>RLC blocks</span></div><i /><div><b>{humanize(analysis.mode)}</b><span>analysis</span></div></div>
      </section>}

      {page === "models" && <section className="spice-split-page">
        <aside><div className="spice-list-heading"><b>MODEL LIBRARY</b><button onClick={addProjectModel} title="Add project subcircuit"><Plus size={13} /></button></div>{workspace.models.map(model => <button key={model.id} className={selectedModel?.id === model.id ? "selected" : ""} onClick={() => setSelectedModelId(model.id)}><b>{model.name}</b><small>{modelLabel(model)} | {humanize(model.origin)}</small></button>)}</aside>
        <main>{selectedModel ? <><div className="spice-section-heading"><div><b>{selectedModel.name}</b><small>{selectedModel.id}</small></div>{selectedModel.origin !== "built_in" && <button className="danger-text" onClick={() => { set({ models: workspace.models.filter(model => model.id !== selectedModel.id), assignments: workspace.assignments.filter(item => item.model_id !== selectedModel.id) }); setSelectedModelId(workspace.models[0]?.id ?? ""); }}><Trash2 size={13} /> Delete</button>}</div><div className="spice-form-grid">
          <label>Name<input value={selectedModel.name} onChange={event => patchModel({ name: event.target.value })} /></label>
          <label>Type<select value={selectedModel.kind} disabled={selectedModel.origin === "built_in"} onChange={event => patchModel({ kind: event.target.value as SpiceModel["kind"] })}><option value="primitive">Primitive</option><option value="subcircuit">Subcircuit</option></select></label>
          <label>Pins<input value={selectedModel.pins.join(", ")} onChange={event => patchModel({ pins: event.target.value.split(",").map(value => value.trim()).filter(Boolean) })} /></label>
          {selectedModel.kind === "primitive" ? <><label>Primitive<select value={selectedModel.primitive} onChange={event => patchModel({ primitive: event.target.value as SpiceModel["primitive"] })}><option value="resistor">Resistor</option><option value="capacitor">Capacitor</option><option value="inductor">Inductor</option><option value="voltage_source">Voltage source</option><option value="current_source">Current source</option><option value="diode">Diode</option></select></label><label>Value / source expression<input value={selectedModel.value ?? ""} placeholder="10k or PULSE(...)" onChange={event => patchModel({ value: event.target.value })} /></label></> : <><label>Subcircuit name<input value={selectedModel.subcircuit_name ?? ""} onChange={event => patchModel({ subcircuit_name: event.target.value })} /></label><label className="spice-wide">Inline model source<textarea spellCheck={false} value={selectedModel.source ?? ""} onChange={event => patchModel({ source: event.target.value })} /></label></>}
        </div></> : <p>No model is selected.</p>}</main>
      </section>}

      {page === "assignments" && <section className="spice-assignment-page">
        <aside><label className="spice-search"><Search size={13} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Find reference or value" /></label>{filteredComponents.map(component => <button key={component.id} className={selectedComponentRef === component.ref ? "selected" : ""} onMouseEnter={() => previewViewportTarget({ kind: "object", type: "component", ref: component.ref, label: component.ref })} onMouseLeave={() => previewViewportTarget(null)} onClick={() => setSelectedComponentRef(component.ref)}><b>{component.ref}</b><small>{component.value}</small></button>)}</aside>
        <main><div className="spice-assign-command"><label>Model<select value={selectedModel?.id ?? ""} onChange={event => setSelectedModelId(event.target.value)}>{workspace.models.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label><button onClick={assignModel}><Link2 size={13} /> Assign to {selectedComponentRef || "component"}</button></div><div className="spice-assignment-list">{workspace.assignments.map(item => <button key={item.id} className={selectedAssignmentId === item.id ? "selected" : ""} onMouseEnter={() => previewViewportTarget({ kind: "object", type: "component", ref: item.component_ref, label: item.component_ref })} onMouseLeave={() => previewViewportTarget(null)} onClick={() => setSelectedAssignmentId(item.id)}><b>{item.component_ref}</b><span>{workspace.models.find(model => model.id === item.model_id)?.name ?? "Missing model"}</span><small>{item.pin_bindings.length} pins</small></button>)}</div></main>
        <aside className="spice-assignment-inspector">{selectedAssignment ? <><div className="spice-section-heading"><div><b>{selectedAssignment.component_ref}</b><small>component model and pin mapping</small></div><button className="danger-text" onClick={() => set({ assignments: workspace.assignments.filter(item => item.id !== selectedAssignment.id) })}><Trash2 size={13} /></button></div><label>Simulation model<select value={selectedAssignment.model_id} onChange={event => changeAssignmentModel(event.target.value)}>{workspace.models.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label><label className="check-row"><input type="checkbox" checked={selectedAssignment.enabled} onChange={event => patchAssignment({ enabled: event.target.checked })} /> Include in simulation</label><div className="spice-pin-table"><header><span>Model pin</span><span>Board pad</span><span>Circuit node</span></header>{selectedAssignment.pin_bindings.map(binding => <div key={binding.model_pin}><b>{binding.model_pin}</b><select value={binding.pad_id} onChange={event => usePad(binding.model_pin, event.target.value)}><option value="">Unmapped</option>{componentPads(board, selectedAssignment.component_ref).map(pad => <option key={pad.id} value={pad.id}>{pad.name} | {pad.net || "no net"} | {pad.layer}</option>)}</select><input value={binding.circuit_node} onChange={event => updatePin(binding.model_pin, { circuit_node: event.target.value })} /></div>)}</div><div className="spice-rating-grid"><label>Rated voltage (V)<input type="number" min="0" value={selectedAssignment.ratings?.voltage_v ?? ""} onChange={event => patchAssignment({ ratings: { ...selectedAssignment.ratings, voltage_v: numberOrZero(event.target.value) } })} /></label><label>Rated current (A)<input type="number" min="0" value={selectedAssignment.ratings?.current_a ?? ""} onChange={event => patchAssignment({ ratings: { ...selectedAssignment.ratings, current_a: numberOrZero(event.target.value) } })} /></label><label>Rated power (W)<input type="number" min="0" value={selectedAssignment.ratings?.power_w ?? ""} onChange={event => patchAssignment({ ratings: { ...selectedAssignment.ratings, power_w: numberOrZero(event.target.value) } })} /></label><label>Voltage vector<input value={selectedAssignment.vectors?.voltage ?? ""} placeholder="v(node)" onChange={event => patchAssignment({ vectors: { ...selectedAssignment.vectors, voltage: event.target.value } })} /></label><label>Current vector<input value={selectedAssignment.vectors?.current ?? ""} placeholder="i(device)" onChange={event => patchAssignment({ vectors: { ...selectedAssignment.vectors, current: event.target.value } })} /></label><label>Power vector<input value={selectedAssignment.vectors?.power ?? ""} onChange={event => patchAssignment({ vectors: { ...selectedAssignment.vectors, power: event.target.value } })} /></label></div></> : <p>Assign a model or select an existing assignment.</p>}</aside>
      </section>}

      {page === "parasitics" && <section className="spice-parasitics-page"><div className="spice-section-heading"><div><b>Explicit geometry parasitics</b><small>RLC values are never inferred here. Imported endpoint placeholders are blocked until explicitly reviewed.</small></div><button onClick={importParasitics} disabled={!analysisResult?.parasitics.length}><Plus size={13} /> Import current result</button></div><div className="spice-parasitic-table"><header><span>Use</span><span>Net / provenance</span><span>From node</span><span>To node</span><span>Reference</span><span>R (ohm)</span><span>L (H)</span><span>C (F)</span><span>Reviewed</span><span /></header>{workspace.parasitics.map(item => <div key={item.id}><input type="checkbox" checked={item.enabled} onChange={event => patchParasitic(item.id, { enabled: event.target.checked })} /><label><b>{item.net}</b><small>{item.source_result_id} | {item.model_status}</small></label><input value={item.from_node} onChange={event => patchParasitic(item.id, { from_node: event.target.value, endpoint_reviewed: false })} /><input value={item.to_node} onChange={event => patchParasitic(item.id, { to_node: event.target.value, endpoint_reviewed: false })} /><input value={item.reference_node} onChange={event => patchParasitic(item.id, { reference_node: event.target.value, endpoint_reviewed: false })} /><input type="number" step="any" value={item.resistance_ohm} onChange={event => patchParasitic(item.id, { resistance_ohm: numberOrZero(event.target.value) })} /><input type="number" step="any" value={item.inductance_h} onChange={event => patchParasitic(item.id, { inductance_h: numberOrZero(event.target.value) })} /><input type="number" step="any" value={item.capacitance_f} onChange={event => patchParasitic(item.id, { capacitance_f: numberOrZero(event.target.value) })} /><label className="spice-review-check"><input type="checkbox" checked={item.endpoint_reviewed} onChange={event => patchParasitic(item.id, { endpoint_reviewed: event.target.checked })} /><span>{item.endpoint_reviewed ? "Mapped" : "Review"}</span></label><button onClick={() => set({ parasitics: workspace.parasitics.filter(value => value.id !== item.id) })}><Trash2 size={13} /></button></div>)}</div>{!workspace.parasitics.length && <div className="spice-empty"><CircuitBoard size={24} /><b>No parasitic network attached</b><span>Run an RLC extraction, then import and map its source/load circuit nodes.</span></div>}</section>}

      {page === "run" && <section className="spice-run-page"><div className="spice-run-controls"><label>Engine<select value={runEngine} disabled={running} onChange={event => setRunEngine(event.target.value as RunEngine)}><option value="native_mna">SPIKE native MNA (linear)</option><option value="peec_mna">Iterative PEEC + native MNA (experimental)</option><option value="owned_spice">SPIKES owned engine (experimental)</option><option value="ngspice">External ngspice (nonlinear/subcircuits)</option></select></label><button disabled={running} onClick={() => void compose()}><ListChecks size={13} /> Compose & validate</button><button disabled={running || !ownedResult} onClick={() => void exportOwnedResult()}><FileOutput size={13} /> Export owned result</button><label>Timeout <input type="number" min={1} max={3600} disabled={running || runEngine === "owned_spice"} value={timeout} onChange={event => setTimeoutValue(Math.max(1, Math.min(3600, Number(event.target.value))))} /> s</label><label><input type="checkbox" checked={overlayEnabled} disabled={running} onChange={event => setOverlayEnabled(event.target.checked)} /> Viewport vector</label><input value={overlayVector} disabled={!overlayEnabled || runEngine !== "ngspice" || running} onChange={event => setOverlayVector(event.target.value)} placeholder="v(out)" /><select value={overlayQuantity} disabled={!overlayEnabled || runEngine !== "ngspice" || running} onChange={event => setOverlayQuantity(event.target.value)}><option value="voltage_v">Voltage</option><option value="voltage_drop_v">Voltage drop</option><option value="current_a">Current</option><option value="current_density_a_mm2">Current density</option></select></div>{runEngine === "owned_spice" && <div className="spice-owned-controls"><label>Explicit probe descriptors (one per line, session-only)<textarea value={ownedProbeText} disabled={running} onChange={event => setOwnedProbeText(event.target.value)} placeholder={"V(out)\nV(vplus,vminus)\nI(V1)\nP(V1)"} /></label><small>Commas are retained inside differential descriptors. Probe text and results are session-only; the reviewed workspace itself persists with the project. The release-owned SPIKES engine accepts only this workspace, not raw netlists or caller-selected libraries. Up to 256 probes, 2 MiB netlist, and 64 MiB result; it has no caller timeout control. Results remain circuit data and are never mapped onto the board.</small></div>}{preview && <div className={`spice-validation-summary ${preview.status}`}><b>{preview.status === "ready" ? "NETLIST READY" : "NETLIST BLOCKED"}</b><span>{preview.validation.issues.length} errors | {preview.validation.warnings.length} warnings | {preview.validation.model_status}</span></div>}<div className="spice-run-layout"><textarea readOnly spellCheck={false} value={preview?.netlist ?? "Compose the workspace to generate the deterministic self-contained netlist."} aria-label="Generated SPICE netlist" /><aside>{runEngine === "native_mna" && <p>Native MNA supports reviewed linear R, L, C, independent sources, dependent sources, operating point, AC, and transient analyses.</p>}{runEngine === "peec_mna" && <p>Experimental fixed-point coupling requires reviewed PEEC RLCG records from one current extraction. Topology changes and inferred endpoints are blocked.</p>}{runEngine === "owned_spice" && <p>The owned SPIKES route is structured-workspace-only and experimental. It validates the exact probe set before execution, records the composed-netlist digest, and has no caller timeout control.</p>}{runEngine === "ngspice" && <p>External ngspice runs the composed netlist for nonlinear devices and reviewed subcircuits.</p>}{[...(preview?.validation.issues ?? []), ...(preview?.validation.warnings ?? [])].map((issue, index) => <div key={`${issue.code}-${index}`} className={issue.severity}><AlertTriangle size={13} /><span><b>{issue.code}</b>{issue.message}<small>{issue.path}</small></span></div>)}{preview && !preview.validation.issues.length && !preview.validation.warnings.length && <p>No workspace validation issues.</p>}<OwnedCircuitResultView result={ownedResult} /></aside></div></section>}
    </div>
    <div className="spice-diagnostic">{diagnostic}</div>
    <footer><span>{selection?.position ? `Viewport binding: ${selection.name} at ${selection.position[0].toFixed(3)}, ${selection.position[1].toFixed(3)} mm` : "No viewport point selected. Model and pin assignments remain project data."}</span><button className="run-btn" onClick={() => void run()} disabled={running}><Play size={14} />{running ? "Running..." : `Run ${runEngineLabel[runEngine]}`}</button></footer>
  </section></div>;
}
