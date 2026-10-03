import { useEffect, useState } from "react";
import DataTable from "./DataTable";
import TableIdentityInput from "./TableIdentityInput";
import { Cable, CircuitBoard, Network, Plus, ShieldCheck } from "lucide-react";
import { placementFromTransform, transformFromPlacement, type AssemblyDesigns, type AssemblyIr, type AssemblyPlacement } from "./mcadAssembly";
import { runLocalWorker, runNativeProjectWorker, selectNativeAssemblySources } from "./workerBridge";
import HarnessAutoPlanner from "./HarnessAutoPlanner";
import ConnectorGraphEditor from "./ConnectorGraphEditor";
import type { GraphConnector } from "./connectorGraphModel";
import AssemblySiBatch from "./AssemblySiBatch";
import MultiboardStudyEditor from "./MultiboardStudyEditor";
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
    {valid ? <DataTable label="Connector pin mapping"><thead><tr><th>Endpoint A pin</th><th>Endpoint B pin</th><th /></tr></thead><tbody>{Object.entries(mapping).map(([source, target]) => <tr key={source}>
      <td><TableIdentityInput aria-label={`${harnessId} source pin ${source}`} value={source} onCommit={value => { const next = { ...mapping }; delete next[source]; next[value] = target; replace(next); }} validate={value => !value.trim() ? "Source pin cannot be blank." : value !== source && Object.prototype.hasOwnProperty.call(mapping, value) ? "Source pin already exists." : ""} /></td>
      <td><input aria-label={`${harnessId} target pin ${source}`} value={target} onChange={event => replace({ ...mapping, [source]: event.target.value })} /></td>
      <td><button className="secondary-btn" onClick={() => { const next = { ...mapping }; delete next[source]; replace(next); }}>Remove</button></td>
    </tr>)}</tbody></DataTable> : <p role="alert">Pin-map JSON is invalid; repair it below.</p>}
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
  const [planDomain, setPlanDomain] = useState<"pi" | "si" | "thermal" | "emi">("pi");
  const [planMode, setPlanMode] = useState<"independent_board_batch" | "coupled_harness_network" | "coupled_assembly">("independent_board_batch");
  const [planSummary, setPlanSummary] = useState<Record<string, unknown> | null>(null);
  const [importSummary, setImportSummary] = useState<Array<{ source_name: string; board_count: number; part_count: number }>>([]);
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
  const mateData = (id: string): Record<string, unknown> => {
    try { const value = JSON.parse(linkDrafts[id] ?? "{}"); return value && typeof value === "object" && !Array.isArray(value) ? value : {}; }
    catch { return {}; }
  };
  const patchMate = (id: string, update: Record<string, unknown>) => setLinkDrafts(current => {
    let prior: Record<string, unknown> = {};
    try { const value = JSON.parse(current[id] ?? "{}"); if (value && typeof value === "object" && !Array.isArray(value)) prior = value; }
    catch { /* Save validation reports malformed drafts. */ }
    return { ...current, [id]: JSON.stringify({ ...prior, ...update }) };
  });
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
      const sources = await selectNativeAssemblySources();
      if (!sources?.length) return;
      const response = await runNativeProjectWorker({ method: "import_into_assembly_project", params: {
        project_path: projectPath, source_paths: sources.map(source => source.path), expected_manifest_payload_sha256: projectManifestDigest,
      } });
      if (!response.ok) throw new Error(response.error || "Assembly import failed.");
      await onUpdated();
      setImportSummary(Array.isArray(response.result?.sources) ? response.result.sources as Array<{ source_name: string; board_count: number; part_count: number }> : []);
      onStatus(`Imported ${sources.length} source${sources.length === 1 ? "" : "s"}; assembly now contains ${response.result?.board_count} boards and ${response.result?.part_count} mechanical parts.`);
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
      onStatus(`Saved ${boards.length} board instances, ${mateCount} direct connector mates, and ${harnesses.length} harnesses. Independent SI batching remains available; coupled physics requires explicit models.`);
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
        ? `${planDomain.toUpperCase()} multi-board plan admits ${boards.length} board instance${boards.length === 1 ? "" : "s"}${planDomain === "si" ? " for sequential independent-SI batch execution" : " for caller-controlled single-board dispatch"}; connector, harness, and cross-board coupling are excluded.`
        : String(firstIssue ?? `${planDomain.toUpperCase()} multi-board plan is blocked.`));
    } catch (error) {
      setPlanSummary(null);
      onStatus(error instanceof Error ? `Multi-board planning failed: ${error.message}` : "Multi-board planning failed");
    } finally { setBusy(false); }
  };
  const linkManagerEnabled = boards.length > 1 || harnesses.length > 0 || connectorMappings.length > 0 || rigidFlexLinks.length > 0;
  const mateCount = connectorMappings.filter(row => row.kind === "connector-mate").length;
  const applyHarnessPlan = (plan: { harnesses: Array<Record<string, unknown>>; connector_mappings: Array<Record<string, unknown>> }) => {
    setHarnesses(current => [...current, ...plan.harnesses as HarnessRow[]]);
    setPinMapDrafts(current => ({ ...current, ...Object.fromEntries(plan.harnesses.map(h => [String(h.id), JSON.stringify(h.pin_map)])) }));
    const existing = new Set(connectorMappings.filter(m => m.kind !== "connector-mate").map(m => `${m.data?.board_id}::${m.data?.connector_id}`));
    const additions = (plan.connector_mappings as LinkRow[]).filter(m => !existing.has(`${m.data?.board_id}::${m.data?.connector_id}`));
    setConnectorMappings(current => [...current, ...additions]);
    setLinkDrafts(current => ({ ...current, ...Object.fromEntries(additions.map(m => [m.id, JSON.stringify(m.data)])) }));
    onStatus("Virtual harness and connector mappings added to the draft. Save boards and links to persist the route.");
  };
  const addGraphMate = (endpointA: string, endpointB: string, pinMap: Record<string, string>, connectors: GraphConnector[]) => {
    const id = identity("connector-mate");
    const data = { endpoint_a: endpointA, endpoint_b: endpointB, pin_map: pinMap };
    const mapped = new Set(connectorMappings.filter(m => m.kind !== "connector-mate").map(m => `${m.data?.board_id}::${m.data?.connector_id}`));
    const additions: LinkRow[] = connectors.filter(connector => !mapped.has(connector.key) && connector.positionMm).map(connector => ({
      id: identity("connector-map"), name: connector.key, kind: "connector",
      data: { board_id: connector.boardId, connector_id: connector.connectorId, position_mm: connector.positionMm, pins: connector.pins },
    }));
    setConnectorMappings(current => [...current, ...additions, { id, name: `${endpointA} ↔ ${endpointB}`, kind: "connector-mate", data }]);
    setLinkDrafts(current => ({ ...current, ...Object.fromEntries(additions.map(row => [row.id, JSON.stringify(row.data)])), [id]: JSON.stringify(data) }));
    onStatus("Direct connector mate added to the draft. Save boards and links to persist it; contact impedance and return behavior still need explicit models.");
  };
  return <section className="mcad-semantics-editor assembly-structure-editor">
    <h3><CircuitBoard size={15} /> Board instances</h3>
    <p className="mcad-gate"><ShieldCheck size={13} /> Board design IDs must resolve in the retained SpiDeR set. Up to 30 boards and 32 copper layers per board are admitted subject to resource budgets. Independent SI suite jobs can run sequentially. Coupled analysis remains disabled until reviewed board-port and harness-network models reach a qualified solver.</p>
    <h4>Board instances</h4>
    <FreecadCollaboration projectPath={projectPath} manifestDigest={projectManifestDigest} disabled={busy || dirty} onUpdated={onUpdated} onStatus={onStatus} />
    <button className="secondary-btn" disabled={busy || dirty || !projectPath || !projectManifestDigest} onClick={() => void importSource()}>Import boards / external assemblies…</button>
    <p>Select one or more KiCad or IPC-2581 boards, or portable .spikeassembly files, in one import. Native boards receive separated starter placements; edit XYZ and rotation below. {dirty ? "Save structure edits before importing another source." : "The active board and existing assembly are retained."}</p>
    {importSummary.length > 0 && <div className="mcad-gate" role="status"><b>Last import</b><ul>{importSummary.map((source, index) => <li key={`${source.source_name}:${index}`}>{source.source_name}: {source.board_count} board{source.board_count === 1 ? "" : "s"}, {source.part_count} mechanical part{source.part_count === 1 ? "" : "s"}</li>)}</ul></div>}
    <DataTable label="Assembly boards" className="data-table"><thead><tr><th>ID / name</th><th>Retained design ID</th><th>XYZ (mm)</th><th>Rotation XYZ (deg)</th><th /></tr></thead><tbody>{boards.map(row => {
      const placement = placementFromTransform(row.frame.transform);
      return <tr key={row.id}>
        <td><input value={row.name ?? row.id} onChange={event => patchBoard(row.id, { name: event.target.value })} /><small>{row.id}</small></td>
        <td>{assemblyDesigns
          ? <select aria-label={`${row.id} retained design`} value={row.design_id} onChange={event => patchBoard(row.id, { design_id: event.target.value })}>
            {assemblyDesigns.designs.map(design => <option key={design.design_id} value={design.design_id}>{String(design.name || design.design_id)} · {design.design_id}</option>)}
          </select>
          : <input aria-label={`${row.id} active design`} value={row.design_id} readOnly title="This package retains only the active SpiDeR." />}</td>
        <td>{(["xMm", "yMm", "zMm"] as const).map(field => <input key={field} aria-label={`${row.id} ${field}`} type="number" step="any" value={placement[field]} onChange={event => patchBoardPlacement(row, field, event.target.value)} />)}</td>
        <td>{(["rxDeg", "ryDeg", "rzDeg"] as const).map(field => <input key={field} aria-label={`${row.id} ${field}`} type="number" step="any" value={placement[field]} onChange={event => patchBoardPlacement(row, field, event.target.value)} />)}</td>
        <td><button className="secondary-btn" onClick={() => setBoards(current => current.filter(item => item.id !== row.id))}>Remove</button></td>
      </tr>;
    })}</tbody></DataTable>
    <button className="secondary-btn" disabled={boards.length >= 30} onClick={() => {
      const id = identity("board");
      setBoards(current => [...current, { id, name: "Board", design_id: assemblyDesigns?.active_design_id ?? current[0]?.design_id ?? "", frame: { frame_id: `${id}-frame`, parent_frame_id: assemblyIr.frame?.frame_id || "assembly", transform: transformFromPlacement({ xMm: 0, yMm: 0, zMm: 0, rxDeg: 0, ryDeg: 0, rzDeg: 0 }) } }]);
    }}><Plus size={13} /> Add board instance</button>
    {linkManagerEnabled ? <section className="assembly-link-manager" aria-label="Multi-board Link Manager">
    <h3><Network size={15} /> Link Manager</h3>
    <p className="mcad-gate">{boards.length} boards · {mateCount} direct connector mate{mateCount === 1 ? "" : "s"} · {harnesses.length} cable harness{harnesses.length === 1 ? "" : "es"}. Define every connector pair and pin map here, then save the project to retain the verified assembly graph.</p>
    {plannerAssembly && <ConnectorGraphEditor assembly={plannerAssembly} designs={assemblyDesigns} version={projectManifestDigest} onAddMate={addGraphMate} onAddConnector={(boardId, connectorId, positionMm, pins) => {
      const id = identity("connector-map"); const data = { board_id: boardId, connector_id: connectorId, position_mm: positionMm, pins };
      setConnectorMappings(current => [...current, { id, name: `${boardId}::${connectorId}`, kind: "connector", data }]);
      setLinkDrafts(current => ({ ...current, [id]: JSON.stringify(data) }));
    }} onApplyHarness={applyHarnessPlan} onRemoveLink={(id, kind) => {
      if (kind === "harness") setHarnesses(current => current.filter(row => row.id !== id));
      else setConnectorMappings(current => current.filter(row => row.id !== id));
      onStatus(`Removed ${kind === "mate" ? "direct mate" : "virtual harness"} ${id} from the draft. Save boards and links to persist the change.`);
    }} onStatus={onStatus} />}
    <details className="assembly-link-details"><summary>Review and edit all link records</summary>
    <h4><Cable size={14} /> Harnesses</h4>
    <p className="mcad-gate">These rows place compact AssemblyIR board-to-board links. Author detailed connectors, wires, sources, loads, and explicit contact resistance in the project harness document.{onOpenHarnessEditor && <> <button className="secondary-btn" onClick={onOpenHarnessEditor}>Open Harness PI editor</button></>}</p>
    <DataTable label="Assembly harnesses" className="data-table"><thead><tr><th>ID / name</th><th>Endpoint A</th><th>Endpoint B</th><th>Length (mm)</th><th>Connector-to-connector pin map</th><th /></tr></thead><tbody>{harnesses.map(row => <tr key={row.id}>
      <td><input value={row.name ?? row.id} onChange={event => patchHarness(row.id, { name: event.target.value })} /><small>{row.id}</small></td>
      <td><input value={row.endpoint_a} onChange={event => patchHarness(row.id, { endpoint_a: event.target.value })} /></td>
      <td><input value={row.endpoint_b} onChange={event => patchHarness(row.id, { endpoint_b: event.target.value })} /></td>
      <td><input type="number" min="0" step="any" value={row.length_mm} onChange={event => patchHarness(row.id, { length_mm: Number(event.target.value) })} /></td>
      <td><AssemblyPinMapEditor harnessId={row.id} value={pinMapDrafts[row.id] ?? "{}"} onChange={next => setPinMapDrafts(current => ({ ...current, [row.id]: next }))} /></td>
      <td><button className="secondary-btn" onClick={() => setHarnesses(current => current.filter(item => item.id !== row.id))}>Remove</button></td>
      </tr>)}</tbody></DataTable>
    <button className="secondary-btn" onClick={() => { const id = identity("harness"); setHarnesses(current => [...current, { id, name: "Harness", endpoint_a: "", endpoint_b: "", length_mm: 0, pin_map: {} }]); setPinMapDrafts(current => ({ ...current, [id]: "{}" })); }}><Plus size={13} /> Add harness</button>
    <h4>Stacked board connector mates</h4>
    <p className="mcad-gate">Declare direct mated connectors separately from cable harnesses. Enter both board::connector identities and an explicit pin map; placement alone does not establish a connection or contact impedance.</p>
    <DataTable label="Assembly connector mates" className="data-table"><thead><tr><th>Name</th><th>Connector A</th><th>Connector B</th><th>Pin map JSON</th><th /></tr></thead><tbody>{connectorMappings.filter(row => row.kind === "connector-mate").map(row => {
      const data = mateData(row.id);
      return <tr key={row.id}>
        <td><input value={row.name ?? ""} onChange={event => setConnectorMappings(current => current.map(item => item.id === row.id ? { ...item, name: event.target.value } : item))} /></td>
        <td><input aria-label={`${row.id} connector A`} value={String(data.endpoint_a ?? "")} placeholder="board-a::J1" onChange={event => patchMate(row.id, { endpoint_a: event.target.value })} /></td>
        <td><input aria-label={`${row.id} connector B`} value={String(data.endpoint_b ?? "")} placeholder="board-b::J2" onChange={event => patchMate(row.id, { endpoint_b: event.target.value })} /></td>
        <td><AssemblyPinMapEditor harnessId={row.id} value={JSON.stringify(data.pin_map ?? {})} onChange={next => { try { patchMate(row.id, { pin_map: JSON.parse(next) }); } catch { /* Keep the last valid map. */ } }} /></td>
        <td><button className="secondary-btn" onClick={() => setConnectorMappings(current => current.filter(item => item.id !== row.id))}>Remove</button></td>
      </tr>;
    })}</tbody></DataTable>
    <button className="secondary-btn" onClick={() => { const id = identity("connector-mate"); setConnectorMappings(current => [...current, { id, name: "Mated connector", kind: "connector-mate", data: { endpoint_a: "", endpoint_b: "", pin_map: {} } }]); setLinkDrafts(current => ({ ...current, [id]: JSON.stringify({ endpoint_a: "", endpoint_b: "", pin_map: {} }) })); }}><Plus size={13} /> Add stacked connector mate</button>
    {plannerAssembly && <HarnessAutoPlanner assembly={plannerAssembly} designs={assemblyDesigns} onStatus={onStatus} onApply={applyHarnessPlan} />}
    {([[
      "Connector mappings", connectorMappings.filter(row => row.kind !== "connector-mate"), setConnectorMappings, "connector-map",
    ], [
      "Rigid/flex links", rigidFlexLinks, setRigidFlexLinks, "rigid-flex-link",
    ]] as const).map(([label, rows, setter, prefix]) => <div key={label}>
      <h4>{label}</h4>
      <DataTable label={label} className="data-table"><thead><tr><th>ID</th><th>Name</th><th>Kind</th><th>Typed data JSON</th><th /></tr></thead><tbody>{rows.map(row => <tr key={row.id}>
        <td><code>{row.id}</code></td>
        <td><input value={row.name ?? ""} onChange={event => setter(current => current.map(item => item.id === row.id ? { ...item, name: event.target.value } : item))} /></td>
        <td><input value={row.kind ?? prefix} onChange={event => setter(current => current.map(item => item.id === row.id ? { ...item, kind: event.target.value } : item))} /></td>
        <td><textarea value={linkDrafts[row.id] ?? "{}"} onChange={event => setLinkDrafts(current => ({ ...current, [row.id]: event.target.value }))} /></td>
        <td><button className="secondary-btn" onClick={() => setter(current => current.filter(item => item.id !== row.id))}>Remove</button></td>
    </tr>)}</tbody></DataTable>
      <button className="secondary-btn" onClick={() => { const id = identity(prefix); setter(current => [...current, { id, name: label.slice(0, -1), kind: prefix, data: {} }]); setLinkDrafts(current => ({ ...current, [id]: "{}" })); }}><Plus size={13} /> Add {label.slice(0, -1).toLowerCase()}</button>
    </div>)}
    </details>
    </section> : <p className="mcad-gate">Add a second board instance to enable the Link Manager for direct connector mates and harnesses.</p>}
    {assemblyDesigns && <AssemblySiBatch key={projectManifestDigest ?? "unsaved"} assembly={assemblyIr} designs={assemblyDesigns} disabled={busy || dirty} onStatus={onStatus} />}
    {boards.length > 1 && <MultiboardStudyEditor assembly={assemblyIr} projectPath={projectPath} manifestDigest={projectManifestDigest} disabled={busy || dirty} onUpdated={onUpdated} onStatus={onStatus} />}
    <h4><Network size={14} /> Multi-board analysis planning</h4>
    <div className="field-row">
      <label>Domain <select value={planDomain} onChange={event => { const domain = event.target.value as typeof planDomain; setPlanDomain(domain); setPlanMode("independent_board_batch"); }}><option value="pi">Power integrity</option><option value="si">Signal integrity</option><option value="thermal">Thermal</option><option value="emi">EM</option></select></label>
      <label>Scope <select value={planMode} onChange={event => setPlanMode(event.target.value as typeof planMode)}><option value="independent_board_batch">Independent board batch</option>{planDomain === "pi" || planDomain === "si" ? <option value="coupled_harness_network">Coupled connector/harness network</option> : <option value="coupled_assembly">Coupled assembly</option>}</select></label>
      <button className="secondary-btn" disabled={busy || !assemblyDesigns} onClick={() => void planAnalysis()}><Network size={13} /> Validate multi-board plan</button>
    </div>
    {planSummary && <p className="mcad-gate" data-state={String(planSummary.state ?? "blocked")}>
      {String(planSummary.state ?? "blocked").toUpperCase()} · {String(planSummary.execution_strategy ?? "none").replace(/_/g, " ")} · graph {String(planSummary.graph_digest ?? "").slice(0, 12)} · coupled physics {planSummary.coupled_physics ? "enabled" : "not enabled"}
    </p>}
    <div><button className="run-btn" disabled={!projectPath || !projectManifestDigest || busy} onClick={() => void save()}>{busy ? "Saving assembly structure..." : "Save boards and links"}</button></div>
  </section>;
}
