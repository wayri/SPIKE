import { useEffect, useState } from "react";
import { Cable, CircuitBoard, Network, Plus, ShieldCheck } from "lucide-react";
import { placementFromTransform, transformFromPlacement, type AssemblyDesigns, type AssemblyIr, type AssemblyPlacement } from "./mcadAssembly";
import { runLocalWorker, runNativeProjectWorker, selectNativeMcadFile } from "./workerBridge";
import HarnessAutoPlanner from "./HarnessAutoPlanner";
import AssemblySiBatch from "./AssemblySiBatch";
import FreecadCollaboration from "./FreecadCollaboration";
import { formatPinMappings, parsePinMappings } from "./connectorPresets";

type Props = {
  projectPath: string | null;
  projectManifestDigest: string | null;
  assemblyIr: AssemblyIr;
  assemblyDesigns: AssemblyDesigns | null;
  onUpdated: () => Promise<void>;
  onStatus: (message: string) => void;
  onOpenHarnessEditor?: () => void;
};

type BoardRow = Record<string, unknown> & { id: string; name?: string; design_id: string; frame: { frame_id: string; parent_frame_id: string; transform: number[] } };
type HarnessRow = Record<string, unknown> & { id: string; name?: string; endpoint_a: string; endpoint_b: string; length_mm: number; pin_map: Record<string, string> };
type LinkRow = Record<string, unknown> & { id: string; name?: string; kind?: string; data?: Record<string, unknown> };
const identity = (prefix: string) => `${prefix}-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`;

function AssemblyPinMapEditor({ harnessId, value, onChange }: { harnessId: string; value: string; onChange: (value: string) => void }) {
  const [bulk, setBulk] = useState(""); const [error, setError] = useState("");
  let mapping: Record<string, string> = {}; let valid = true;
  try { const parsed = JSON.parse(value || "{}"); if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(); mapping = parsed; } catch { valid = false; }
  const replace = (next: Record<string, string>) => onChange(JSON.stringify(next));
  return <div className="assembly-pin-map-editor">
    {valid ? <table><thead><tr><th>Endpoint A pin</th><th>Endpoint B pin</th><th /></tr></thead><tbody>{Object.entries(mapping).map(([source, target]) => <tr key={source}>
      <td><input aria-label={`${harnessId} source pin ${source}`} value={source} onChange={event => { const next = { ...mapping }; delete next[source]; if (event.target.value) next[event.target.value] = target; replace(next); }} /></td>
      <td><input aria-label={`${harnessId} target pin ${source}`} value={target} onChange={event => replace({ ...mapping, [source]: event.target.value })} /></td>
      <td><button className="secondary-btn" onClick={() => { const next = { ...mapping }; delete next[source]; replace(next); }}>Remove</button></td>
    </tr>)}</tbody></table> : <p role="alert">Pin-map JSON is invalid; repair it below.</p>}
    <button className="secondary-btn" disabled={!valid} onClick={() => { let index = Object.keys(mapping).length + 1; while (String(index) in mapping) index++; replace({ ...mapping, [String(index)]: String(index) }); }}>Add pin pair</button>
    <details><summary>Bulk / text pin mapping</summary><textarea aria-label={`${harnessId} bulk pin mappings`} rows={5} placeholder={'1=1\n2=2'} value={bulk} onChange={event => setBulk(event.target.value)} /><button className="secondary-btn" disabled={!valid} onClick={() => setBulk(formatPinMappings(mapping))}>Load table</button> <button className="secondary-btn" onClick={() => { try { replace(parsePinMappings(bulk)); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); } }}>Apply text</button>{error && <p role="alert">{error}</p>}</details>
    <details><summary>Raw JSON</summary><textarea aria-label={`${harnessId} pin map JSON`} value={value} onChange={event => onChange(event.target.value)} /></details>
  </div>;
}

export default function AssemblyStructureEditor({ projectPath, projectManifestDigest, assemblyIr, assemblyDesigns, onUpdated, onStatus, onOpenHarnessEditor }: Props) {
  const [boards, setBoards] = useState<BoardRow[]>([]);
  const [harnesses, setHarnesses] = useState<HarnessRow[]>([]);
  const [pinMapDrafts, setPinMapDrafts] = useState<Record<string, string>>({});
  const [connectorMappings, setConnectorMappings] = useState<LinkRow[]>([]);
  const [rigidFlexLinks, setRigidFlexLinks] = useState<LinkRow[]>([]);
  const [linkDrafts, setLinkDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [planDomain, setPlanDomain] = useState<"pi" | "si">("pi");
  const [planMode, setPlanMode] = useState<"independent_board_batch" | "coupled_harness_network">("independent_board_batch");
  const [planSummary, setPlanSummary] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    setBoards(structuredClone(assemblyIr.boards as BoardRow[]));
    setHarnesses(structuredClone((assemblyIr.harnesses ?? []) as HarnessRow[]));
    setPinMapDrafts(Object.fromEntries(((assemblyIr.harnesses ?? []) as HarnessRow[]).map(item => [item.id, JSON.stringify(item.pin_map)])));
    const connectors = structuredClone((assemblyIr.connector_mappings ?? []) as LinkRow[]);
    const flex = structuredClone((assemblyIr.rigid_flex_links ?? []) as LinkRow[]);
    setConnectorMappings(connectors); setRigidFlexLinks(flex);
    setLinkDrafts(Object.fromEntries([...connectors, ...flex].map(item => [item.id, JSON.stringify(item.data ?? {})])));
  }, [assemblyIr]);
  const patchBoard = (id: string, update: Partial<BoardRow>) => setBoards(current => current.map(item => item.id === id ? { ...item, ...update } : item));
  const patchBoardPlacement = (row: BoardRow, field: keyof AssemblyPlacement, raw: string) => {
    const placement = placementFromTransform(row.frame.transform);
    placement[field] = Number(raw);
    if (!Number.isFinite(placement[field])) return;
    patchBoard(row.id, { frame: { ...row.frame, transform: transformFromPlacement(placement) } });
  };
  const patchHarness = (id: string, update: Partial<HarnessRow>) => setHarnesses(current => current.map(item => item.id === id ? { ...item, ...update } : item));
  const dirty = JSON.stringify(boards) !== JSON.stringify(assemblyIr.boards)
    || JSON.stringify(harnesses) !== JSON.stringify(assemblyIr.harnesses ?? [])
    || JSON.stringify(connectorMappings) !== JSON.stringify(assemblyIr.connector_mappings ?? [])
    || JSON.stringify(rigidFlexLinks) !== JSON.stringify(assemblyIr.rigid_flex_links ?? [])
    || harnesses.some(h => pinMapDrafts[h.id] !== JSON.stringify(h.pin_map))
    || [...connectorMappings, ...rigidFlexLinks].some(h => linkDrafts[h.id] !== JSON.stringify(h.data ?? {}));
  const importSource = async () => {
    if (!projectPath || !projectManifestDigest || busy || dirty) return;
    setBusy(true);
    try {
      const source = await selectNativeMcadFile();
      if (!source) return;
      if (!/\.(spikeassembly|kicad_pcb|ipc2581)$/i.test(source.path)) throw new Error("Select a .spikeassembly, .kicad_pcb or .ipc2581 file. Use Attach part for a single STEP/GLB enclosure piece.");
      const response = await runNativeProjectWorker({ method: "import_into_assembly_project", params: {
        project_path: projectPath, source_path: source.path, expected_manifest_payload_sha256: projectManifestDigest,
      } });
      if (!response.ok) throw new Error(response.error || "Assembly import failed.");
      await onUpdated();
      onStatus(`Imported ${source.fileName}; assembly now contains ${response.result?.board_count} boards and ${response.result?.part_count} mechanical parts.`);
    } catch (error) { onStatus(String(error)); }
    finally { setBusy(false); }
  };
  const plannerAssembly = (() => {
    try {
      return { ...assemblyIr, boards, harnesses: harnesses.map(h => ({ ...h, pin_map: JSON.parse(pinMapDrafts[h.id] ?? "{}") })),
        connector_mappings: connectorMappings.map(m => ({ ...m, data: JSON.parse(linkDrafts[m.id] ?? "{}") })) };
    } catch { return null; }
  })();
  const save = async () => {
    if (!projectPath || !projectManifestDigest || busy) return;
    setBusy(true);
    try {
      const canonicalHarnesses = harnesses.map(item => {
        const pinMap = JSON.parse(pinMapDrafts[item.id] ?? "{}");
        if (!pinMap || typeof pinMap !== "object" || Array.isArray(pinMap)) throw new Error(`Harness ${item.id} pin map must be a JSON object.`);
        return { ...item, pin_map: pinMap };
      });
      const parseLinks = (items: LinkRow[]) => items.map(item => {
        const data = JSON.parse(linkDrafts[item.id] ?? "{}");
        if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error(`${item.id} data must be a JSON object.`);
        return { ...item, data };
      });
      const response = await runNativeProjectWorker({ method: "update_assembly_structure_in_project", params: {
        project_path: projectPath, expected_manifest_payload_sha256: projectManifestDigest,
        boards, harnesses: canonicalHarnesses,
        connector_mappings: parseLinks(connectorMappings),
        rigid_flex_links: parseLinks(rigidFlexLinks),
      } });
      if (!response.ok) throw new Error(response.error ?? "Assembly structure update was rejected.");
      await onUpdated();
      onStatus(`Saved ${boards.length} board instances and ${harnesses.length} harnesses against retained DesignIR identities. Independent SI batching is available with explicit per-board lane jobs; coupled physics remains disabled.`);
    } catch (error) {
      onStatus(error instanceof Error ? `Assembly structure update failed: ${error.message}` : "Assembly structure update failed");
    } finally { setBusy(false); }
  };
  const planAnalysis = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const canonicalHarnesses = harnesses.map(item => {
        const pinMap = JSON.parse(pinMapDrafts[item.id] ?? "{}");
        if (!pinMap || typeof pinMap !== "object" || Array.isArray(pinMap)) throw new Error(`Harness ${item.id} pin map must be a JSON object.`);
        return { ...item, pin_map: pinMap };
      });
      const canonicalLinks = (items: LinkRow[]) => items.map(item => {
        const data = JSON.parse(linkDrafts[item.id] ?? "{}");
        if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error(`${item.id} data must be a JSON object.`);
        return { ...item, data };
      });
      const designs = Object.fromEntries((assemblyDesigns?.designs ?? []).map(design => [design.design_id, design]));
      const response = await runLocalWorker({ method: "plan_multiboard_analysis", params: { request: {
        contract: "spike/multiboard-analysis-request/v1",
        domain: planDomain,
        mode: planMode,
        assembly: {
          ...assemblyIr, boards, harnesses: canonicalHarnesses,
          connector_mappings: canonicalLinks(connectorMappings),
          rigid_flex_links: canonicalLinks(rigidFlexLinks),
        },
        designs,
      } } });
      if (!response.ok || !response.result) throw new Error(response.error ?? "Multi-board planner returned no result.");
      setPlanSummary(response.result);
      const issues = Array.isArray(response.result.issues) ? response.result.issues as Array<Record<string, unknown>> : [];
      const firstIssue = issues.find(issue => issue.severity === "error")?.message;
      onStatus(response.result.independent_jobs_admissible
        ? `${planDomain.toUpperCase()} multi-board plan admits ${boards.length} board instance${boards.length === 1 ? "" : "s"}${planDomain === "si" ? " for sequential independent-SI batch execution" : " for caller-controlled single-board dispatch"}; harness coupling is excluded.`
        : String(firstIssue ?? `${planDomain.toUpperCase()} multi-board plan is blocked.`));
    } catch (error) {
      setPlanSummary(null);
      onStatus(error instanceof Error ? `Multi-board planning failed: ${error.message}` : "Multi-board planning failed");
    } finally { setBusy(false); }
  };
  return <section className="mcad-semantics-editor assembly-structure-editor">
    <h3><CircuitBoard size={15} /> Board instances and harnesses</h3>
    <p className="mcad-gate"><ShieldCheck size={13} /> Board design IDs must resolve in the retained DesignIR set. Up to 30 boards and 32 copper layers per board are admitted subject to resource budgets. Independent SI suite jobs can run sequentially. Coupled analysis remains disabled until reviewed board-port and harness-network models reach a qualified solver.</p>
    <h4>Board instances</h4>
    <FreecadCollaboration projectPath={projectPath} manifestDigest={projectManifestDigest} disabled={busy || dirty} onUpdated={onUpdated} onStatus={onStatus} />
    <button className="secondary-btn" disabled={busy || dirty || !projectPath || !projectManifestDigest} onClick={() => void importSource()}>Import board / external assembly</button>
    <p>Import additional KiCad or IPC-2581 boards, or a portable .spikeassembly with board files and placed STEP/GLB enclosure pieces. {dirty ? "Save structure edits before importing another source." : "The active board and existing assembly are retained."}</p>
    <table className="data-table"><thead><tr><th>ID / name</th><th>Retained design ID</th><th>XYZ (mm)</th><th>Rotation XYZ (deg)</th><th /></tr></thead><tbody>{boards.map(row => {
      const placement = placementFromTransform(row.frame.transform);
      return <tr key={row.id}>
        <td><input value={row.name ?? row.id} onChange={event => patchBoard(row.id, { name: event.target.value })} /><small>{row.id}</small></td>
        <td>{assemblyDesigns
          ? <select aria-label={`${row.id} retained design`} value={row.design_id} onChange={event => patchBoard(row.id, { design_id: event.target.value })}>
            {assemblyDesigns.designs.map(design => <option key={design.design_id} value={design.design_id}>{String(design.name || design.design_id)} · {design.design_id}</option>)}
          </select>
          : <input aria-label={`${row.id} active design`} value={row.design_id} readOnly title="This package retains only the active DesignIR." />}</td>
        <td>{(["xMm", "yMm", "zMm"] as const).map(field => <input key={field} aria-label={`${row.id} ${field}`} type="number" step="any" value={placement[field]} onChange={event => patchBoardPlacement(row, field, event.target.value)} />)}</td>
        <td>{(["rxDeg", "ryDeg", "rzDeg"] as const).map(field => <input key={field} aria-label={`${row.id} ${field}`} type="number" step="any" value={placement[field]} onChange={event => patchBoardPlacement(row, field, event.target.value)} />)}</td>
        <td><button className="secondary-btn" onClick={() => setBoards(current => current.filter(item => item.id !== row.id))}>Remove</button></td>
      </tr>;
    })}</tbody></table>
    <button className="secondary-btn" disabled={boards.length >= 30} onClick={() => {
      const id = identity("board");
      setBoards(current => [...current, { id, name: "Board", design_id: assemblyDesigns?.active_design_id ?? current[0]?.design_id ?? "", frame: { frame_id: `${id}-frame`, parent_frame_id: assemblyIr.frame?.frame_id || "assembly", transform: transformFromPlacement({ xMm: 0, yMm: 0, zMm: 0, rxDeg: 0, ryDeg: 0, rzDeg: 0 }) } }]);
    }}><Plus size={13} /> Add board instance</button>
    <h4><Cable size={14} /> Harnesses</h4>
    <p className="mcad-gate">These rows place compact AssemblyIR board-to-board links. Author detailed connectors, wires, sources, loads, and explicit contact resistance in the project harness document.{onOpenHarnessEditor && <> <button className="secondary-btn" onClick={onOpenHarnessEditor}>Open Harness PI editor</button></>}</p>
    <table className="data-table"><thead><tr><th>ID / name</th><th>Endpoint A</th><th>Endpoint B</th><th>Length (mm)</th><th>Connector-to-connector pin map</th><th /></tr></thead><tbody>{harnesses.map(row => <tr key={row.id}>
      <td><input value={row.name ?? row.id} onChange={event => patchHarness(row.id, { name: event.target.value })} /><small>{row.id}</small></td>
      <td><input value={row.endpoint_a} onChange={event => patchHarness(row.id, { endpoint_a: event.target.value })} /></td>
      <td><input value={row.endpoint_b} onChange={event => patchHarness(row.id, { endpoint_b: event.target.value })} /></td>
      <td><input type="number" min="0" step="any" value={row.length_mm} onChange={event => patchHarness(row.id, { length_mm: Number(event.target.value) })} /></td>
      <td><AssemblyPinMapEditor harnessId={row.id} value={pinMapDrafts[row.id] ?? "{}"} onChange={next => setPinMapDrafts(current => ({ ...current, [row.id]: next }))} /></td>
      <td><button className="secondary-btn" onClick={() => setHarnesses(current => current.filter(item => item.id !== row.id))}>Remove</button></td>
    </tr>)}</tbody></table>
    <button className="secondary-btn" onClick={() => { const id = identity("harness"); setHarnesses(current => [...current, { id, name: "Harness", endpoint_a: "", endpoint_b: "", length_mm: 0, pin_map: {} }]); setPinMapDrafts(current => ({ ...current, [id]: "{}" })); }}><Plus size={13} /> Add harness</button>
    {plannerAssembly && <HarnessAutoPlanner assembly={plannerAssembly} designs={assemblyDesigns} onStatus={onStatus} onApply={plan => {
      setHarnesses(current => [...current, ...plan.harnesses as HarnessRow[]]);
      setPinMapDrafts(current => ({ ...current, ...Object.fromEntries(plan.harnesses.map(h => [String(h.id), JSON.stringify(h.pin_map)])) }));
      const existing = new Set(connectorMappings.map(m => `${m.data?.board_id}::${m.data?.connector_id}`));
      const additions = (plan.connector_mappings as LinkRow[]).filter(m => !existing.has(`${m.data?.board_id}::${m.data?.connector_id}`));
      setConnectorMappings(current => [...current, ...additions]);
      setLinkDrafts(current => ({ ...current, ...Object.fromEntries(additions.map(m => [m.id, JSON.stringify(m.data)])) }));
      onStatus("Harnesses and connector mappings added to the draft. Save board and harness structure to persist them.");
    }} />}
    {([[
      "Connector mappings", connectorMappings, setConnectorMappings, "connector-map",
    ], [
      "Rigid/flex links", rigidFlexLinks, setRigidFlexLinks, "rigid-flex-link",
    ]] as const).map(([label, rows, setter, prefix]) => <div key={label}>
      <h4>{label}</h4>
      <table className="data-table"><thead><tr><th>ID</th><th>Name</th><th>Kind</th><th>Typed data JSON</th><th /></tr></thead><tbody>{rows.map(row => <tr key={row.id}>
        <td><code>{row.id}</code></td>
        <td><input value={row.name ?? ""} onChange={event => setter(current => current.map(item => item.id === row.id ? { ...item, name: event.target.value } : item))} /></td>
        <td><input value={row.kind ?? prefix} onChange={event => setter(current => current.map(item => item.id === row.id ? { ...item, kind: event.target.value } : item))} /></td>
        <td><textarea value={linkDrafts[row.id] ?? "{}"} onChange={event => setLinkDrafts(current => ({ ...current, [row.id]: event.target.value }))} /></td>
        <td><button className="secondary-btn" onClick={() => setter(current => current.filter(item => item.id !== row.id))}>Remove</button></td>
      </tr>)}</tbody></table>
      <button className="secondary-btn" onClick={() => { const id = identity(prefix); setter(current => [...current, { id, name: label.slice(0, -1), kind: prefix, data: {} }]); setLinkDrafts(current => ({ ...current, [id]: "{}" })); }}><Plus size={13} /> Add {label.slice(0, -1).toLowerCase()}</button>
    </div>)}
    {assemblyDesigns && <AssemblySiBatch key={projectManifestDigest ?? "unsaved"} assembly={assemblyIr} designs={assemblyDesigns} disabled={busy || dirty} onStatus={onStatus} />}
    <h4><Network size={14} /> PI/SI multi-board planning</h4>
    <div className="field-row">
      <label>Domain <select value={planDomain} onChange={event => setPlanDomain(event.target.value as "pi" | "si")}><option value="pi">Power integrity</option><option value="si">Signal integrity</option></select></label>
      <label>Scope <select value={planMode} onChange={event => setPlanMode(event.target.value as typeof planMode)}><option value="independent_board_batch">Independent board batch</option><option value="coupled_harness_network">Coupled harness network</option></select></label>
      <button className="secondary-btn" disabled={busy || !assemblyDesigns} onClick={() => void planAnalysis()}><Network size={13} /> Validate multi-board plan</button>
    </div>
    {planSummary && <p className="mcad-gate" data-state={String(planSummary.state ?? "blocked")}>
      {String(planSummary.state ?? "blocked").toUpperCase()} · {String(planSummary.execution_strategy ?? "none").replace(/_/g, " ")} · graph {String(planSummary.graph_digest ?? "").slice(0, 12)} · coupled physics {planSummary.coupled_physics ? "enabled" : "not enabled"}
    </p>}
    <div><button className="run-btn" disabled={!projectPath || !projectManifestDigest || busy} onClick={() => void save()}>{busy ? "Saving assembly structure..." : "Save board and harness structure"}</button></div>
  </section>;
}
