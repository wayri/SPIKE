// SPDX-License-Identifier: Apache-2.0
import { useRef, useState, type ReactNode } from "react";
import { extensionWorkspaceRoutes, extensionScalarFields, extensionScalarParameters, type ExtensionWorkspace, type ExtensionWorkspaceRoute } from "./ExtensionWorkspaceRoutes";
import { useGuidedRunAdapter } from "./useGuidedRunAdapter";
import type { GuidedSimulationRequirement } from "./guidedSimulationModel";
import "./ExtensionWorkspacePanel.css";
export type ExtensionWorkspacePanelProps = {
  extensions: unknown[]; workspace: ExtensionWorkspace; operation?: "mesh" | "solve"; selectedRouteId?: string;
  selectedSolverRouteId?: string; selectedMeshRouteId?: string; onSelectMeshRoute?: (key: string) => void;
  boardLoaded: boolean; requiresBoard?: boolean; busy?: boolean; onSelectRoute: (key: string) => void;
  onConfigure: (extensionId: string, contributionId: string) => void;
  onPreview?: (extensionId: string, contributionId: string, parameters: Record<string, unknown>) => void | Promise<void>;
  onRun?: (extensionId: string, contributionId: string, parameters: Record<string, unknown>) => void | Promise<void>;
  renderSetup?: (route: ExtensionWorkspaceRoute) => ReactNode;
  parameters?: Record<string, unknown>; dedicatedExecution?: boolean;
  contextKey?: string;
};
export default function ExtensionWorkspacePanel(props: ExtensionWorkspacePanelProps) {
  const routes = extensionWorkspaceRoutes(props.extensions, props.workspace, props.operation);
  const selected = routes.find(route => route.key === props.selectedRouteId);
  const solverKey = props.selectedSolverRouteId ?? (selected?.operation === "solve" ? selected.key : "");
  const meshKey = props.selectedMeshRouteId ?? (selected?.operation === "mesh" ? selected.key : "");
  const [values, setValues] = useState<Record<string, Record<string, string>>>({});
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const panelRef = useRef<HTMLElement>(null);
  const schema = extensionScalarFields(selected?.schema ?? null);
  const busy = props.busy || working;
  const requiresBoard = props.requiresBoard ?? selected?.requiresBoard ?? true;
  const allowed = Boolean(selected?.trusted && selected.enabled && (props.boardLoaded || !requiresBoard) && !busy);
  const inlineReady = props.renderSetup ? props.parameters !== undefined : !schema.requiresDedicatedGui;
  const act = async (preview: boolean) => {
    if (!selected || !allowed || !inlineReady || !preview && (props.dedicatedExecution || !props.onRun)) {
      if (!preview) throw new Error("This engine is not ready for execution. Recheck its route, trust, required geometry and setup.");
      return;
    }
    setError(""); setWorking(true);
    try {
      const parameters = props.parameters ?? extensionScalarParameters(selected.schema, values[selected.key] ?? {});
      if (preview && selected.previewContributionId) await props.onPreview?.(selected.extensionId, selected.previewContributionId, parameters);
      else if (!preview) await props.onRun?.(selected.extensionId, selected.contributionId, parameters);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); if (!preview) throw cause; }
    finally { setWorking(false); }
  };
  const workspace = { mesh: "Mesh", pi: "PI", si: "HF / SI", em: "EM", thermal: "Thermal" }[props.workspace];
  const revision = JSON.stringify({ route: props.selectedRouteId, solverKey, meshKey, schema: selected?.schema, parameters: props.parameters, values: selected ? values[selected.key] : undefined, trusted: selected?.trusted, enabled: selected?.enabled, boardLoaded: props.boardLoaded, requiresBoard, inlineReady, dedicated: props.dedicatedExecution, runnable: Boolean(props.onRun) });
  const requirements = (): GuidedSimulationRequirement[] => {
    const rows: GuidedSimulationRequirement[] = [];
    const missing = (id: string, title: string, detail: string, route = "extension-fields") => rows.push({ id, title, detail, severity: "blocker", route });
    if (!selected) missing("engine", "Choose an extension engine", "Choose the engine route to configure, or use the built-in workspace workflow.", "extension-engine");
    else {
      if (!selected.trusted) missing("trust", "Review extension trust", "Review and trust this extension in Extensions before execution. Trust does not qualify its numerical methods.", "extension-engine");
      if (!selected.enabled) missing("enabled", "Enable the extension", "This extension is disabled or unavailable. Review its status in Extensions.", "extension-engine");
      if (requiresBoard && !props.boardLoaded) missing("board", "Load the required board", "Load the board geometry required by this declared engine route before running.", "extension-engine");
      if (props.dedicatedExecution || !props.onRun) missing("dedicated", "Use the engine's dedicated run controls", "This route is executed through its dedicated setup. Open its configuration, complete the required inputs and use its run controls.", "extension-config");
      if (!inlineReady) missing("structured", "Complete the engine setup", "Configure the structured geometry, materials, ports or source results in the extension GUI and apply its parameters.", "extension-config");
      else {
        try {
          if (props.parameters === undefined) extensionScalarParameters(selected.schema, values[selected.key] ?? {});
          else if (!schema.requiresDedicatedGui) extensionScalarParameters(selected.schema, Object.fromEntries(Object.entries(props.parameters).map(([key, value]) => [key, value == null ? "" : String(value)])));
        }
        catch (cause) { missing("parameters", "Complete the engine values", cause instanceof Error ? cause.message : String(cause)); }
      }
    }
    if (busy) missing("busy", "Wait for the active operation", "An operation is already running. Wait for it to finish, then recheck this setup.", "extension-engine");
    rows.push({ id: "engine-admission", title: "Engine validation occurs on Run", detail: "This guide checks declared route prerequisites and scalar values only. The engine performs authoritative numerical and runtime admission when Run is requested; it may reject additional missing or incompatible inputs.", severity: "warning" });
    return rows;
  };
  const openGuide = useGuidedRunAdapter({
    id: `extension-${props.workspace}`,
    context: { key: `${props.contextKey ?? "extension"}:${props.workspace}`, revision, workspace, title: selected ? `${selected.extensionName} · ${selected.label}` : "Extension engine setup" },
    check: async (_context, signal) => { if (signal.aborted) throw new Error("Setup check cancelled."); return { requirements: requirements(), summary: "Declared extension prerequisites checked; numerical admission remains with the selected engine." }; },
    fix: requirement => {
      setError(requirement.detail);
      if (requirement.route === "extension-config" && selected && allowed) { props.onConfigure(selected.extensionId, selected.setupContributionId); return; }
      const panel = panelRef.current;
      const candidates = panel ? [...panel.querySelectorAll<HTMLInputElement | HTMLSelectElement>("input, select")] : [];
      const field = requirement.route === "extension-fields" ? candidates.find(node => !node.disabled && node.getAttribute("aria-label") !== "Extension engine" && node.getAttribute("aria-label") !== "Extension mesher") : candidates.find(node => node.getAttribute("aria-label") === "Extension engine");
      field?.focus(); field?.scrollIntoView({ block: "nearest" });
    },
    run: async (_context, signal) => { if (signal.aborted) throw new Error("Run request cancelled."); const blocker = requirements().find(row => row.severity === "blocker"); if (blocker) throw new Error(blocker.detail); await act(false); },
    tutorSteps: [
      { id: "engine", title: "Choose the engine", detail: "Choose a compatible engine and review its trust, availability and qualification status.", route: "extension-engine" },
      { id: "values", title: "Configure required inputs", detail: "Fill declared scalar values, or open the extension GUI for structured geometry and materials.", route: "extension-fields" },
      { id: "review", title: "Review and run", detail: "Recheck setup, review remaining warnings and request Run. The engine retains final numerical and runtime admission.", route: "extension-fields" },
    ],
  });
  return <section ref={panelRef} className="extension-workspace-panel" aria-label="Extension workspace engines">
    <h3>{props.operation === "mesh" || props.workspace === "mesh" ? "Extension meshing engine" : "Extension solver engine"}</h3>
    <p>Choose a declared workspace route. Runtime availability and numerical admission are checked when preparing or running its case.</p>
    <label>{props.workspace === "mesh" ? "Mesher" : "Solver"}<select aria-label="Extension engine" value={props.workspace === "mesh" ? selected?.key ?? "" : solverKey} disabled={busy} onChange={event => { setError(""); props.onSelectRoute(event.target.value); }}>
      <option value="">Built-in workflow</option>{routes.filter(route => props.workspace === "mesh" || route.operation === "solve").map(route => <option key={route.key} value={route.key}>{route.extensionName} · {route.label}{!route.trusted ? " · trust required" : !route.enabled ? " · disabled" : ""}</option>)}
    </select></label>
    {props.workspace !== "mesh" && <label>Mesher<select aria-label="Extension mesher" value={meshKey} disabled={busy} onChange={event => { setError(""); (props.onSelectMeshRoute ?? props.onSelectRoute)(event.target.value); }}>
      <option value="">Built-in meshing</option>{routes.filter(route => route.operation === "mesh").map(route => <option key={route.key} value={route.key}>{route.extensionName} · {route.label}{!route.trusted ? " · trust required" : !route.enabled ? " · disabled" : ""}</option>)}
    </select></label>}
    {props.workspace !== "mesh" && <div className="extension-workspace-actions"><button type="button" disabled={busy || !solverKey} onClick={() => props.onSelectRoute(solverKey)}>Solver setup</button><button type="button" disabled={busy || !meshKey} onClick={() => (props.onSelectMeshRoute ?? props.onSelectRoute)(meshKey)}>Mesher setup</button></div>}
    {!routes.length && <p>No extension declares a compatible route for this workspace. Refresh the extension catalog or install an appropriate extension.</p>}
    {selected && <>
      <dl><dt>Extension</dt><dd>{selected.extensionName} · {selected.state}</dd><dt>Trust</dt><dd>{selected.trusted ? "Trusted" : "Trust required in Extensions"}</dd><dt>Qualification</dt><dd>{selected.modelStatus}</dd>{selected.meshKind && <><dt>Mesh</dt><dd>{selected.meshKind}</dd></>}{selected.compatibleSolverIds.length > 0 && <><dt>Declared solver compatibility</dt><dd>{selected.compatibleSolverIds.join(", ")}</dd></>}</dl>
      {!props.boardLoaded && requiresBoard && <p role="status">Load a board before configuring this workflow.</p>}
      {selected.requiresBoard === false && <p role="status">This workflow uses its own reference geometry independently of any loaded board.</p>}
      {props.renderSetup ? props.renderSetup(selected) : schema.requiresDedicatedGui ? <p>This route uses structured inputs. Open its GUI setup for materials, geometry, ports, or source results.</p> : <div className="extension-workspace-inputs">{schema.fields.map(field => <label key={field.name}>{field.label}{field.required ? " *" : ""}
        {field.choices || field.type === "boolean" ? <select aria-label={field.label} disabled={!allowed} value={values[selected.key]?.[field.name] ?? ""} onChange={event => setValues(current => ({ ...current, [selected.key]: { ...current[selected.key], [field.name]: event.target.value } }))}><option value="">Choose a value</option>{(field.choices ?? [true, false]).map(choice => <option key={String(choice)} value={String(choice)}>{String(choice)}</option>)}</select>
        : <input aria-label={field.label} type={field.type === "string" ? "text" : "number"} step={field.type === "integer" ? 1 : "any"} min={field.minimum} max={field.maximum} disabled={!allowed} value={values[selected.key]?.[field.name] ?? ""} onChange={event => setValues(current => ({ ...current, [selected.key]: { ...current[selected.key], [field.name]: event.target.value } }))} />}
        {field.description && <small>{field.description}</small>}
      </label>)}</div>}
      <div className="extension-workspace-actions"><button disabled={!allowed} onClick={() => props.onConfigure(selected.extensionId, selected.setupContributionId)}>Configure in extension GUI</button>
        {props.onPreview && (requiresBoard || selected.requiresBoard === false) && selected.previewContributionId && <button disabled={!allowed || !inlineReady} onClick={() => void act(true)}>Preview generated case</button>}
        {props.onRun && !props.dedicatedExecution && <button disabled={busy} onClick={openGuide}>{selected.operation === "mesh" ? "Generate mesh" : "Run selected engine"}</button>}
      </div>
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
