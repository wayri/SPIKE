// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import { Boxes, GitBranch, Package, Search } from "./icons";
import snapshot from "./solverBlockCatalogSnapshot.json";
import { filterSolverBlocks, readSolverBlockCatalog, type SolverBlockCatalog, type SolverBlockSelection } from "./solverBlockModel";
import { runLocalWorker } from "./workerBridge";
import "./buttonStandard.css";
import "./SolverBlockPanel.css";

const bundledCatalog = readSolverBlockCatalog(snapshot);
const deliveryLabels = { bundled: "Included in full distribution", external: "Separate external runtime", planned: "Planned / unavailable" };
type Props = { initialQuery?: string; initialCatalog?: SolverBlockCatalog; loadPlan?: (selection: SolverBlockSelection) => Promise<unknown> };
async function workerPlan(selection: SolverBlockSelection): Promise<unknown> {
  const response = await runLocalWorker({ method: "solver_blocks", params: selection });
  if (!response.ok) throw new Error(typeof response.error === "string" ? response.error : "Worker dependency planning is unavailable. Retry with a matching desktop worker.");
  return response.result;
}
export default function SolverBlockPanel({ initialQuery = "", initialCatalog = bundledCatalog, loadPlan = workerPlan }: Props) {
  const [catalog, setCatalog] = useState(initialCatalog);
  const [requested, setRequested] = useState<SolverBlockSelection>({});
  const [applied, setApplied] = useState<SolverBlockSelection>({});
  const [busy, setBusy] = useState(false);
  const [probed, setProbed] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [query, setQuery] = useState(initialQuery);
  const [group, setGroup] = useState("all");
  useEffect(() => {
    let current = true;
    setBusy(true); setError("");
    void loadPlan(requested).then(value => {
      const next = readSolverBlockCatalog(value);
      if (current) { setCatalog(next); setApplied(requested); setProbed(true); }
    }).catch(reason => { if (current) setError(reason instanceof Error ? reason.message : "Could not refresh dependency preview."); })
      .finally(() => { if (current) setBusy(false); });
    return () => { current = false; };
  }, [requested, retry, loadPlan]);
  const rows = useMemo(() => filterSolverBlocks(catalog, query, group), [catalog, query, group]);
  const names = new Map(catalog.blocks.map(block => [block.id, block.name]));
  const roots = new Set(catalog.plan.requested_blocks);
  const required = new Set(catalog.plan.required_blocks);
  const included = new Set(catalog.plan.ordered_blocks);
  const unresolved = new Set(catalog.plan.blocked_blocks);
  const toggleBlock = (id: string) => {
    const next = new Set(roots);
    if (next.has(id)) next.delete(id); else next.add(id);
    setRequested({ selected_blocks: [...next] });
  };
  const toggleGroup = (id: string) => {
    const next = new Set(applied.selected_groups ?? []);
    if (next.has(id)) next.delete(id); else next.add(id);
    setRequested({ selected_groups: [...next], selected_blocks: applied.selected_blocks ?? [] });
  };
  return <section className="solver-block-panel" aria-label="Solver blocks and install groups" aria-busy={busy}>
    <header><div><h3><Boxes size={16} /> Solver blocks</h3><p>All first-party blocks ship together by default. Choose blocks or whole sections to preview their dependencies.</p></div><span className="solver-block-tag">Full distribution · all bundled</span></header>
    <p className="solver-block-policy">Previewing a selection does not install, remove or download files. All bundled blocks stay included; external engines require separate admission.</p>
    <div className="solver-block-groups" role="group" aria-label="Bulk solver groups">{catalog.groups.map(item => <button type="button" className="spike-control--compact" key={item.id} disabled={busy} aria-pressed={applied.selected_groups?.includes(item.id) ?? false} onClick={() => toggleGroup(item.id)} title={`Preview all blocks in ${item.name}, including required dependencies`}><Package size={13} />{item.name}</button>)}</div>
    <div className="solver-block-toolbar"><button type="button" className="spike-control--compact" disabled={busy} onClick={() => setRequested({})}>Preview all bundled</button><button type="button" className="spike-control--compact" disabled={busy} onClick={() => setRequested({ selected_blocks: [] })}>Preview base only</button><button type="button" className="spike-control--compact" disabled={busy} onClick={() => setRetry(value => value + 1)}>Refresh dependency plan</button></div>
    <p role="status">{busy ? "Updating dependency preview…" : probed ? "Worker dependency plan loaded; installed runtime availability is checked separately." : "Bundled catalog snapshot; worker dependency preview has not been confirmed."}</p>
    {error && <details className="solver-block-error"><summary role="alert">Dependency worker unavailable. The previous plan remains shown.</summary><p>{error} Retry after the worker is available; source capabilities remain accessible in the Capabilities tab.</p></details>}
    <div className="solver-block-filters"><label><span><Search size={13} /> Find a block or dependency</span><input aria-label="Find solver block" type="search" placeholder="CHT, harness, circuit-native…" value={query} onChange={event => setQuery(event.target.value)} /></label><label><span>Show section</span><select aria-label="Show solver block section" value={group} onChange={event => setGroup(event.target.value)}><option value="all">All sections</option>{catalog.groups.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
    <details className="solver-block-plan"><summary><GitBranch size={14} /> Dependency plan · {roots.size} requested · {required.size} required · {unresolved.size} prerequisite-gated</summary><p>Required blocks are included automatically, once, before their dependents. Optional links do not expand the plan. Gated entries include external runtime requirements and dependent workflows; this is not an installation probe.</p><ol>{catalog.plan.ordered_blocks.map(id => <li key={id}><strong>{names.get(id)}</strong> <code>{id}</code>{required.has(id) ? " · required automatically" : ""}{unresolved.has(id) ? " · prerequisite not established" : ""}</li>)}</ol>{catalog.plan.warnings.map(warning => <p key={warning}>{warning}</p>)}</details>
    <p>{rows.length} of {catalog.blocks.length} blocks · {catalog.blocks.filter(block => block.delivery === "bundled").length} bundled · catalog {catalog.catalog_version} · no managed downloads yet</p>
    <div className="solver-block-grid">{rows.length ? rows.map(block => <article className="solver-block-card" key={block.id}>
      <header><label><input type="checkbox" aria-label={`Include block: ${block.name}`} checked={included.has(block.id)} disabled={busy || block.id === "core" || required.has(block.id) || block.delivery === "planned"} onChange={() => toggleBlock(block.id)} /><strong>{block.name}</strong></label><span className="solver-block-tag">{deliveryLabels[block.delivery]}</span>{required.has(block.id) && <span className="solver-block-tag">Required automatically</span>}</header>
      <code>{block.id}</code><p>{block.description}</p><small>{block.groups.map(id => catalog.groups.find(item => item.id === id)?.name ?? id).join(" · ")}</small>
      <div className="solver-block-links"><strong><GitBranch size={13} /> Requires</strong>{block.requires.length ? block.requires.map(id => <button type="button" className="spike-control--compact" key={id} onClick={() => { setQuery(id); setGroup("all"); }} title={`Find required block: ${names.get(id)}`}>{names.get(id)}</button>) : <span>No other blocks</span>}</div>
      {block.optional.length > 0 && <div className="solver-block-links"><strong>Optional links</strong>{block.optional.map(id => <button type="button" className="spike-control--compact" key={id} onClick={() => { setQuery(id); setGroup("all"); }} title="Optional integration; not automatically included">{names.get(id)}</button>)}</div>}
      {unresolved.has(block.id) && <p className="solver-block-gated">Prerequisite not established; runtime admission remains required.</p>}
    </article>) : <p>No matching blocks. Clear the search or choose another section.</p>}</div>
  </section>;
}
