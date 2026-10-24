// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { Link2, RefreshCw, Unlink } from "./icons";
import { optionMatchesQuery } from "./optionSearch";
import { runNativeProjectWorker, selectNativeImportFile, selectNativeMcadFile } from "./workerBridge";
import SectionHelpButton from "./SectionHelpButton";
import "./linkedSources.css";
export type LinkedSource = { target_kind: "board" | "model"; target_id: string; path: string; sha256: string };
export type SourceTarget = { kind: "board" | "model"; id: string; name: string; instances: number };
type Props = { projectPath: string | null; manifest: string | null; targets: SourceTarget[]; links: LinkedSource[]; disabledReason: string; onUpdated: () => Promise<void>; onStatus: (message: string) => void };
type SourceStatus = { status: string; sha256?: string; size_bytes?: number; path?: string };
export function normalizeLinkedSources(value: unknown): LinkedSource[] {
  if (!Array.isArray(value)) return [];
  return value.filter((row): row is LinkedSource => !!row && typeof row === "object" && ["board", "model"].includes(row.target_kind) && typeof row.target_id === "string" && typeof row.path === "string" && /^[a-f0-9]{64}$/.test(row.sha256));
}
export default function LinkedSourcesPanel(props: Props) {
  const [query, setQuery] = useState(""); const [selected, setSelected] = useState("");
  const [states, setStates] = useState<Record<string, SourceStatus>>({});
  const [watch, setWatch] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [review, setReview] = useState<{ target: SourceTarget; source: SourceStatus; summary: string } | null>(null);
  const epoch = useRef(0); const working = useRef(false); const latest = useRef(props); latest.current = props;
  const key = (row: SourceTarget | LinkedSource) => "kind" in row ? `${row.kind}:${row.id}` : `${row.target_kind}:${row.target_id}`;
  const target = props.targets.find(row => key(row) === selected);
  const link = target && props.links.find(row => key(row) === selected);
  const locked = props.disabledReason || (!props.projectPath || !props.manifest ? "Save the SPIKE project before linking sources." : "");
  useEffect(() => { epoch.current++; setReview(null); setStates({}); setError(""); }, [props.projectPath, props.manifest]);
  useEffect(() => () => { epoch.current++; }, []);
  const operate = async (action: (token: number) => Promise<void>) => {
    if (working.current) return; working.current = true; setBusy(true); setError(""); const token = epoch.current;
    try { await action(token); } catch (caught) { if (token === epoch.current) setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { working.current = false; setBusy(false); }
  };
  const check = () => operate(async token => {
    const checked: Record<string, SourceStatus> = {};
    for (const row of latest.current.links) {
      const response = await runNativeProjectWorker({ method: "linked_source_status", params: { project_path: props.projectPath, expected_manifest_payload_sha256: props.manifest, target_kind: row.target_kind, target_id: row.target_id, expected_sha256: row.sha256 } });
      if (token !== epoch.current) return;
      if (!response.ok) throw new Error(response.error || "Source check failed.");
      checked[key(row)] = response.result as SourceStatus;
    }
    setStates(checked);
  });
  useEffect(() => {
    if (!watch || locked) return;
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void check(); }, 15000);
    const focus = () => { void check(); }; window.addEventListener("focus", focus); void check();
    return () => { clearInterval(timer); window.removeEventListener("focus", focus); };
  }, [watch, locked, props.projectPath, props.manifest]);
  const mutate = async (method: string, params: Record<string, unknown>, token: number) => {
    if (latest.current.disabledReason) throw new Error(latest.current.disabledReason);
    const response = await runNativeProjectWorker({ method, params: { project_path: props.projectPath, expected_manifest_payload_sha256: props.manifest, ...params } });
    if (!response.ok) throw new Error(response.error || "Linked-source change failed.");
    if (token !== epoch.current) return;
    setReview(null); if (latest.current.disabledReason) throw new Error("Saved package updated, but local changes appeared during sync. Save them separately or discard them before reopening the updated package."); await props.onUpdated(); props.onStatus(method === "apply_linked_source_update" ? "Source geometry synced. Review study references and rerun affected simulations." : "Source link saved.");
  };
  const connect = () => operate(async token => {
    if (!target) return;
    const file = target.kind === "board" ? await selectNativeImportFile("board") : await selectNativeMcadFile();
    if (!file || token !== epoch.current) return;
    await mutate("link_project_source", { target_kind: target.kind, target_id: target.id, path: file.path }, token);
  });
  const prepare = () => operate(async token => {
    if (!target || !link) return;
    const response = await runNativeProjectWorker({ method: "prepare_linked_source_update", params: { project_path: props.projectPath, expected_manifest_payload_sha256: props.manifest, target_kind: target.kind, target_id: target.id, expected_sha256: link.sha256 } });
    if (token !== epoch.current) return;
    if (!response.ok) throw new Error(response.error || "Cannot prepare source update.");
    const result = response.result as any;
    const design = result.outcome?.design;
    const summary = design ? `${design.components?.length ?? 0} components · ${design.tracks?.length ?? design.conductors?.length ?? 0} routing objects. Import diagnostics are checked again on apply.` : "Replace this model's source geometry; keep each occurrence's placement. STEP requires visual preparation again.";
    if (!result.source?.sha256) throw new Error("Source preparation returned no review fingerprint.");
    setReview({ target, source: result.source, summary });
  });
  return <section className="linked-sources" aria-labelledby="linked-sources-title">
    <header><h3 id="linked-sources-title"><Link2 size={15}/> Linked CAD sources</h3><SectionHelpButton topic="doc:docs/LINKED_CAD_SOURCES.md" label="Linked CAD sources"/></header>
    <p>1. Link the original file. 2. Save changes in KiCad or your CAD tool. 3. Review and sync into SPIKE.</p>
    <small>Reads saved files only. SPIKE never writes back to the source. All instances sharing this design or model update together.</small>
    {locked && <p role="status">{locked}</p>}
    <label className="linked-source-search">Find a board or model<input type="search" value={query} maxLength={128} placeholder="Name or ID · * and ?" onChange={event => setQuery(event.target.value)}/></label>
    <div className="linked-source-targets">{props.targets.filter(row => optionMatchesQuery(`${row.name} ${row.kind} ${row.id}`, query)).map(row => {
      const entry = props.links.find(item => key(item) === key(row));
      return <button type="button" key={key(row)} aria-pressed={selected === key(row)} disabled={busy} onClick={() => { setSelected(key(row)); setReview(null); }} title={entry?.path ?? row.id}><b>{row.name}</b><small>{row.kind === "board" ? "PCB" : "Mechanical"} · {row.instances} instance(s) · {entry ? states[key(row)]?.status ?? "linked; unchecked" : "not linked"}</small></button>;
    })}</div>
    {target && <p className="linked-source-path" title={link?.path}>{link?.path ?? `Select the original source for ${target.name}. Its bytes must match the imported revision.`}</p>}
    <div className="linked-source-actions">
      <button type="button" disabled={!!locked || busy || !target} onClick={() => void connect()}><Link2 size={14}/>{link ? "Relocate source" : "Link source"}</button>
      <button type="button" disabled={!!locked || busy || !props.links.length} onClick={() => void check()}><RefreshCw size={14}/>Check changes</button>
      <button type="button" disabled={!!locked || busy || !link} onClick={() => void prepare()}>Review update</button>
      <button type="button" disabled={!!locked || busy || !link} onClick={() => void operate(token => mutate("link_project_source", { target_kind: target!.kind, target_id: target!.id, unlink: true }, token))}><Unlink size={14}/>Unlink</button>
    </div>
    <label><input type="checkbox" checked={watch} disabled={!!locked} onChange={event => setWatch(event.target.checked)}/> Check saved sources every 15 seconds while this manager is open</label>
    {review && <section className="linked-source-review" aria-label="Review source update"><h4>Sync {review.target.name}</h4><p>{review.summary}</p><p>This replaces source geometry for {review.target.instances} instance(s). Placements remain. Saved results are invalidated; references that cannot be retained block sync.</p><small>Reviewed SHA-256: {review.source.sha256}</small><div className="linked-source-actions"><button type="button" className="spike-control--primary" disabled={busy || !!locked} onClick={() => void operate(token => mutate("apply_linked_source_update", { target_kind: review.target.kind, target_id: review.target.id, expected_sha256: review.source.sha256, invalidate_results: true }, token))}>Apply update and invalidate results</button><button type="button" disabled={busy} onClick={() => setReview(null)}>Cancel</button></div></section>}
    {busy && <p role="status">Checking source or updating the saved package…</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
