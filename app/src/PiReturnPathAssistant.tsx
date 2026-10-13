// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { numericExtent } from "./numericRange";
import { runLocalWorker } from "./workerBridge";
import "./PiReturnPathAssistant.css";

export type PiReturnPathRequest = {
  contract: "spike/pi-return-path-request/v1";
  occurrence_id: string;
  forward_net: string;
  return_net: string;
  source_pad_id: string;
  load_pad_ids: string[];
  mesh_target_mm: number;
};
export type PiReturnPathSelection = { returnNet: string; sourcePadId: string; loadPadIds: string[] };
export type PiReturnPathIssue = string | { code?: string; severity?: string; message: string };
export type PiReturnPathResult = {
  contract: "spike/pi-return-path-result/v1";
  status: "connected" | "disconnected" | "blocked";
  paths: Array<{
    load_pad_id: string;
    connected: boolean;
    resistance_ohm: number | null;
    length_mm: number | null;
    points_mm: [number, number, number][];
  }>;
  issues: PiReturnPathIssue[];
  proposals?: Array<{
    kind: "review_copper_bridge";
    start_mm: [number, number, number];
    end_mm: [number, number, number];
    gap_mm: number;
  }>;
};
export type PiReturnPad = { id: string; net: string; label: string };
export type PiReturnPathAssistantProps = {
  workerAvailable: boolean;
  design: Record<string, unknown> | null;
  occurrenceId: string;
  forwardNet: string;
  onApply?: (selection: PiReturnPathSelection) => void;
  onStatus?: (message: string) => void;
};

const nonempty = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const point3 = (value: unknown): value is [number, number, number] => Array.isArray(value) && value.length === 3 && value.every(finite);

function designNetNames(design: Record<string, unknown>) {
  const result = new Map<string, string>();
  const nets = design.nets;
  if (Array.isArray(nets)) for (const raw of nets) {
    if (!raw || typeof raw !== "object") continue;
    const net = raw as Record<string, unknown>;
    if (nonempty(net.id) && nonempty(net.name)) result.set(net.id, net.name.trim());
  }
  if (nets && typeof nets === "object" && !Array.isArray(nets)) for (const [id, name] of Object.entries(nets)) {
    if (nonempty(name)) result.set(id, name.trim());
  }
  return result;
}

export function extractPiReturnPads(design: Record<string, unknown> | null): PiReturnPad[] {
  if (!design || !Array.isArray(design.pads)) return [];
  const netNames = designNetNames(design);
  const output: PiReturnPad[] = [];
  const seen = new Set<string>();
  for (const raw of design.pads) {
    if (!raw || typeof raw !== "object") continue;
    const pad = raw as Record<string, unknown>;
    if (!nonempty(pad.id)) continue;
    const id = pad.id.trim();
    if (seen.has(id)) continue;
    const directNet = nonempty(pad.net_name) ? pad.net_name : nonempty(pad.net) ? pad.net : "";
    const net = directNet.trim() || (nonempty(pad.net_id) ? netNames.get(pad.net_id) ?? "" : "");
    if (!net) continue;
    const component = [pad.component, pad.component_id, pad.reference, pad.ref].find(nonempty)?.trim() ?? "?";
    const number = [pad.number, pad.name, pad.pad_number].find(nonempty)?.trim() ?? id;
    const layer = [pad.layer, pad.layer_name].find(nonempty)?.trim()
      ?? (Array.isArray(pad.layers) && nonempty(pad.layers[0]) ? pad.layers[0].trim() : "layer unavailable");
    output.push({ id, net, label: `${component}.${number} · ${layer} · ${id}` });
    seen.add(id);
  }
  return output.sort((a, b) => a.net.localeCompare(b.net, undefined, { numeric: true }) || a.label.localeCompare(b.label, undefined, { numeric: true }));
}

export function buildPiReturnPathRequest(input: {
  design: Record<string, unknown> | null;
  occurrenceId: string;
  forwardNet: string;
  returnNet: string;
  sourcePadId: string;
  loadPadIds: string[];
  meshTargetMm: string;
}): PiReturnPathRequest {
  if (!input.design) throw new Error("Load a board design before planning a return path.");
  if (!input.occurrenceId.trim()) throw new Error("Board occurrence ID is required.");
  if (!input.forwardNet.trim()) throw new Error("Select a forward net before planning its return path.");
  if (!input.returnNet.trim()) throw new Error("Select an explicit return net.");
  if (input.returnNet.trim() === input.forwardNet.trim()) throw new Error("Forward and return nets must be different.");
  const rawPadIds = Array.isArray(input.design.pads) ? input.design.pads.map(raw => raw && typeof raw === "object" ? (raw as Record<string, unknown>).id : null).filter(nonempty) : [];
  if (new Set(rawPadIds).size !== rawPadIds.length) throw new Error("The loaded design contains duplicate pad IDs; return terminals are ambiguous.");
  const pads = extractPiReturnPads(input.design);
  const matching = new Map(pads.filter(pad => pad.net === input.returnNet).map(pad => [pad.id, pad]));
  if (!matching.has(input.sourcePadId)) throw new Error("Select a source return pad on the chosen return net.");
  const loadIds = input.loadPadIds.map(value => value.trim()).filter(Boolean);
  if (!loadIds.length || loadIds.length > 32) throw new Error("Select 1 to 32 load return pads.");
  if (new Set(loadIds).size !== loadIds.length) throw new Error("Load return pad IDs must be unique.");
  if (loadIds.includes(input.sourcePadId)) throw new Error("The source return pad cannot also be a load return pad.");
  if (loadIds.some(id => !matching.has(id))) throw new Error("Every load return pad must belong to the chosen return net.");
  if (!input.meshTargetMm.trim()) throw new Error("Mesh target is required.");
  const meshTarget = Number(input.meshTargetMm);
  if (!finite(meshTarget) || meshTarget < 0.05 || meshTarget > 1000) throw new Error("Mesh target must be a finite value from 0.05 to 1000 mm.");
  return { contract: "spike/pi-return-path-request/v1", occurrence_id: input.occurrenceId.trim(),
    forward_net: input.forwardNet.trim(), return_net: input.returnNet.trim(), source_pad_id: input.sourcePadId,
    load_pad_ids: loadIds, mesh_target_mm: meshTarget };
}

const issueValid = (value: unknown): value is PiReturnPathIssue => typeof value === "string" && value.length > 0
  || Boolean(value && typeof value === "object" && nonempty((value as Record<string, unknown>).message));
export function validPiReturnPathResult(raw: unknown, request?: PiReturnPathRequest | null): raw is PiReturnPathResult {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return false;
  const result = raw as PiReturnPathResult;
  if (result.contract !== "spike/pi-return-path-result/v1" || !["connected", "disconnected", "blocked"].includes(result.status)
    || !Array.isArray(result.paths) || !Array.isArray(result.issues) || !result.issues.every(issueValid)
    || result.proposals !== undefined && (!Array.isArray(result.proposals) || !result.proposals.every(proposal => proposal?.kind === "review_copper_bridge"
      && point3(proposal.start_mm) && point3(proposal.end_mm) && finite(proposal.gap_mm) && proposal.gap_mm >= 0))) return false;
  const ids = new Set<string>();
  for (const path of result.paths) {
    if (!path || !nonempty(path.load_pad_id) || ids.has(path.load_pad_id) || typeof path.connected !== "boolean"
      || path.resistance_ohm !== null && (!finite(path.resistance_ohm) || path.resistance_ohm < 0)
      || path.length_mm !== null && (!finite(path.length_mm) || path.length_mm < 0)
      || !Array.isArray(path.points_mm) || !path.points_mm.every(point3)
      || path.connected && (path.resistance_ohm === null || path.length_mm === null || path.points_mm.length < 2)) return false;
    ids.add(path.load_pad_id);
  }
  if (result.status === "connected" && (!result.paths.length || result.paths.some(path => !path.connected))) return false;
  if (result.status === "disconnected" && result.paths.length > 0 && result.paths.every(path => path.connected)) return false;
  if (request) {
    if (result.paths.some(path => !request.load_pad_ids.includes(path.load_pad_id))) return false;
    if (result.status !== "blocked" && (result.paths.length !== request.load_pad_ids.length || request.load_pad_ids.some(id => !ids.has(id)))) return false;
  }
  return true;
}

const issueText = (issue: PiReturnPathIssue) => typeof issue === "string" ? issue
  : [issue.severity, issue.code, issue.message].filter(Boolean).join(" · ");
const format = (value: number | null, digits = 5) => value === null ? "Unavailable" : value.toLocaleString(undefined, { maximumSignificantDigits: digits });
const requestIdentity = (value: PiReturnPathRequest | null) => value ? JSON.stringify(value) : "";

function RoutePreview({ result }: { result: PiReturnPathResult }) {
  const routes = result.paths.filter(path => path.points_mm.length >= 2);
  if (!routes.length) return <div className="pi-return-preview-empty">No connected route points were returned for preview.</div>;
  const all = routes.flatMap(route => route.points_mm);
  const xs = all.map(point => point[0]); const ys = all.map(point => point[1]);
  const xExtent = numericExtent(xs); const yExtent = numericExtent(ys);
  const minX = xExtent.minimum; const maxX = xExtent.maximum; const minY = yExtent.minimum; const maxY = yExtent.maximum;
  const spanX = Math.max(maxX - minX, 1e-9); const spanY = Math.max(maxY - minY, 1e-9);
  const x = (value: number) => 30 + 740 * (value - minX) / spanX;
  const y = (value: number) => 270 - 240 * (value - minY) / spanY;
  return <figure className="pi-return-preview"><svg viewBox="0 0 800 300" role="img" aria-labelledby="pi-return-preview-title pi-return-preview-description">
    <title id="pi-return-preview-title">Returned resistance-route points</title>
    <desc id="pi-return-preview-description">Polyline projection of worker-returned route points only. It is not a board copper rendering or a current-density field.</desc>
    {routes.map((route, index) => <polyline key={route.load_pad_id} className={route.connected ? "connected" : "disconnected"}
      points={route.points_mm.map(point => `${x(point[0])},${y(point[1])}`).join(" ")}><title>{`${route.load_pad_id}: ${route.points_mm.length} returned points, route ${index + 1}`}</title></polyline>)}
  </svg><figcaption>Plan view of returned x/y coordinates · z coordinates remain in the result but are not projected as height.</figcaption></figure>;
}

function ResultView({ result }: { result: PiReturnPathResult }) {
  return <div className="pi-return-results">
    <header><div><strong>{result.status.toUpperCase()}</strong><span>Approximate shortest-resistance route</span></div><span>{result.paths.filter(path => path.connected).length}/{result.paths.length} loads connected</span></header>
    <RoutePreview result={result} />
    <div className="pi-return-table-wrap"><table><thead><tr><th>Load return pad</th><th>Status</th><th>Route length</th><th>Resistance</th><th>Returned points</th></tr></thead><tbody>{result.paths.map(path => <tr key={path.load_pad_id}><td>{path.load_pad_id}</td><td>{path.connected ? "Connected" : "Disconnected"}</td><td>{format(path.length_mm)}{path.length_mm === null ? "" : " mm"}</td><td>{format(path.resistance_ohm)}{path.resistance_ohm === null ? "" : " ohm"}</td><td>{path.points_mm.length}</td></tr>)}</tbody></table></div>
    {result.issues.length > 0 && <section className="pi-return-issues"><h5>Planning issues</h5><ul>{result.issues.map((issue, index) => <li key={`${index}:${issueText(issue)}`}>{issueText(issue)}</li>)}</ul></section>}
    {(result.proposals?.length ?? 0) > 0 && <section className="pi-return-proposals"><h5>Review-only copper bridge proposals</h5><p>These suggestions do not modify the board.</p><ul>{result.proposals!.map((proposal, index) => <li key={index}>Gap {format(proposal.gap_mm)} mm · [{proposal.start_mm.map(value => format(value)).join(", ")}] to [{proposal.end_mm.map(value => format(value)).join(", ")}] mm</li>)}</ul></section>}
    <p className="pi-return-scope">This is an approximate shortest-resistance route over admitted copper geometry. It does not solve full return-current distribution, loop inductance, high-frequency field behavior, or layout qualification.</p>
  </div>;
}

export default function PiReturnPathAssistant({ workerAvailable, design, occurrenceId, forwardNet, onApply, onStatus }: PiReturnPathAssistantProps) {
  const [returnNet, setReturnNet] = useState("");
  const [sourcePadId, setSourcePadId] = useState("");
  const [loadPadIds, setLoadPadIds] = useState<string[]>([]);
  const [meshTargetMm, setMeshTargetMm] = useState("");
  const [result, setResult] = useState<PiReturnPathResult | null>(null);
  const [resultRequest, setResultRequest] = useState<PiReturnPathRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const runSequence = useRef(0);
  const resultDesign = useRef<Record<string, unknown> | null>(null);
  useEffect(() => () => { runSequence.current += 1; }, []);
  const pads = extractPiReturnPads(design);
  const returnNets = [...new Set(pads.map(pad => pad.net).filter(net => net !== forwardNet))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  const returnPads = pads.filter(pad => pad.net === returnNet);
  const toggleLoad = (id: string) => setLoadPadIds(current => current.includes(id) ? current.filter(value => value !== id) : current.length < 32 ? [...current, id] : current);
  const requestInput = { design, occurrenceId, forwardNet, returnNet, sourcePadId, loadPadIds, meshTargetMm };
  let currentRequest: PiReturnPathRequest | null = null;
  try { currentRequest = buildPiReturnPathRequest(requestInput); } catch { /* Run reports actionable validation. */ }
  const stale = Boolean(result && resultRequest && (resultDesign.current !== design || requestIdentity(resultRequest) !== requestIdentity(currentRequest)));
  const canApply = Boolean(onApply && result?.status === "connected" && currentRequest && resultRequest
    && resultDesign.current === design && requestIdentity(resultRequest) === requestIdentity(currentRequest) && validPiReturnPathResult(result, currentRequest));
  const run = async () => {
    const sequence = ++runSequence.current;
    let request: PiReturnPathRequest;
    try { request = buildPiReturnPathRequest(requestInput); }
    catch (caught) { const message = caught instanceof Error ? caught.message : String(caught); setError(message); onStatus?.(`Return-path input error: ${message}`); return; }
    setBusy(true); setError(""); onStatus?.("Planning approximate PI return paths…");
    try {
      const id = globalThis.crypto?.randomUUID?.() ?? `pi-return-path-${Date.now()}-${sequence}`;
      const response = await runLocalWorker({ id, method: "plan_pi_return_path", params: { design, request } });
      if (runSequence.current !== sequence) return;
      if (!response.ok || !response.result) throw new Error(response.error ?? "Return-path worker returned no result.");
      if (!validPiReturnPathResult(response.result, request)) throw new Error("Return-path worker returned a malformed or mismatched result.");
      setResult(response.result); setResultRequest(request); resultDesign.current = design;
      onStatus?.(`Return-path planning completed with status ${response.result.status}.`);
    } catch (caught) {
      if (runSequence.current !== sequence) return;
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(message); onStatus?.(`Return-path planning failed: ${message}`);
    } finally { if (runSequence.current === sequence) setBusy(false); }
  };
  const apply = () => {
    let request: PiReturnPathRequest;
    try { request = buildPiReturnPathRequest(requestInput); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); return; }
    if (!result || !resultRequest || result.status !== "connected" || resultDesign.current !== design || requestIdentity(resultRequest) !== requestIdentity(request)
      || !validPiReturnPathResult(result, request)) { setError("Run a connected plan for the current inputs before applying this selection."); return; }
    onApply?.({ returnNet: request.return_net, sourcePadId: request.source_pad_id, loadPadIds: [...request.load_pad_ids] });
    onStatus?.("Applied the reviewed PI return-path terminal selection.");
  };
  return <section className="pi-return-assistant" aria-labelledby="pi-return-heading">
    <header><div><p className="pi-return-eyebrow">Power integrity · geometry review</p><h4 id="pi-return-heading">Return-path assistant</h4></div><span className="pi-return-badge">Approximate route</span></header>
    <p className="pi-return-intro">Choose the actual return net and explicit source/load return pads for <strong>{forwardNet || "the selected forward net"}</strong>. Net names are presented from the loaded design without ground-name inference.</p>
    <fieldset disabled={busy || !design}><legend>Return-path terminals</legend>
      <div className="pi-return-controls"><label><span>Return net</span><select aria-label="Return net" value={returnNet} onChange={event => { setReturnNet(event.target.value); setSourcePadId(""); setLoadPadIds([]); }}><option value="">Select an actual design net…</option>{returnNets.map(net => <option key={net} value={net}>{net}</option>)}</select></label>
        <label><span>Source return pad</span><select aria-label="Source return pad" value={sourcePadId} disabled={!returnNet || busy} onChange={event => { setSourcePadId(event.target.value); setLoadPadIds(current => current.filter(id => id !== event.target.value)); }}><option value="">Select a pad on {returnNet || "the return net"}…</option>{returnPads.map(pad => <option key={pad.id} value={pad.id}>{pad.label}</option>)}</select></label>
        <label><span>Mesh target<small>mm</small></span><input aria-label="Return-path mesh target (mm)" type="number" min="0" step="any" value={meshTargetMm} onChange={event => setMeshTargetMm(event.target.value)} /></label>
      </div>
      <div className="pi-return-loads"><div><strong>Load return pads</strong><span>{loadPadIds.length}/32 selected</span></div>{returnPads.length ? <div className="pi-return-load-list">{returnPads.map(pad => <label key={pad.id} title={pad.label}><input type="checkbox" aria-label={`Load return pad ${pad.id}`} checked={loadPadIds.includes(pad.id)} disabled={busy || pad.id === sourcePadId || !loadPadIds.includes(pad.id) && loadPadIds.length >= 32} onChange={() => toggleLoad(pad.id)} /><span>{pad.label}</span></label>)}</div> : <p>Select a return net to list its exact pad IDs.</p>}</div>
    </fieldset>
    {!design && <p className="pi-return-notice">No loaded design is available. Open a board before configuring a return path.</p>}
    <div className="pi-return-actions"><button type="button" className="spike-control--primary" disabled={!workerAvailable || busy || !design} onClick={() => void run()}>{busy ? "Planning return paths…" : "Plan return paths"}</button><button type="button" disabled={!canApply || busy} onClick={apply}>Apply reviewed terminals</button><span aria-live="polite">{!workerAvailable ? "Local solver worker unavailable." : busy ? "Worker request in progress." : "Ready for explicit return-path review."}</span></div>
    {error && <p className="pi-return-error" role="alert">{error} {result ? "The last valid plan remains visible." : "Review the selected design terminals and try again."}</p>}
    {stale && <p className="pi-return-stale" role="status">Inputs differ from the planned setup. Apply is disabled until the current inputs are planned.</p>}
    {result ? <ResultView result={result} /> : <div className="pi-return-empty">Run the worker to review returned route points and connectivity. The browser does not draw inferred copper paths.</div>}
  </section>;
}
