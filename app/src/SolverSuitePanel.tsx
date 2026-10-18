// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import { Search, X } from "./icons";
import { filterSolverSuite, solverSuiteCatalog, solverSuiteGroups, solverSuiteStatusLabels, type SolverSuiteAction, type SolverSuiteGroup, type SolverSuiteStatus } from "./solverSuiteCatalog";
import { capabilitySolverIds, filterManagerCapabilities, runtimeSolverName, runtimeSolverOrigin, runtimeWorkflow, solverDisplayName, solverOrigin, solverOriginLabels, type RuntimeSolver, type SolverOrigin } from "./solverManagerModel";
import "./buttonStandard.css";
import "./SolverSuitePanel.css";
import SolverBlockPanel from "./SolverBlockPanel";

type Props = {
  initialQuery?: string;
  initialView?: "capabilities" | "blocks";
  runtimeSolvers?: readonly RuntimeSolver[];
  runtimeProbed?: boolean;
  onManageEngines?: () => void;
  onClose: () => void;
  onOpenWorkflow: (action: SolverSuiteAction, extensionId?: string, capabilityId?: string) => void;
};
export default function SolverSuitePanel({ onClose, onOpenWorkflow, onManageEngines, initialQuery = "", initialView = "blocks", runtimeSolvers = [], runtimeProbed = false }: Props) {
  const [view, setView] = useState(initialView);
  const [query, setQuery] = useState(initialQuery);
  const [group, setGroup] = useState<SolverSuiteGroup | "all">("all");
  const [status, setStatus] = useState<SolverSuiteStatus | "all">("all");
  const [origin, setOrigin] = useState<SolverOrigin | "all">("all");
  const entries = useMemo(() => filterManagerCapabilities(filterSolverSuite("", group, status), query, origin), [query, group, status, origin]);
  const runtimeEntries = runtimeSolvers.filter(item => (origin === "all" || runtimeSolverOrigin(item) === origin) && query.toLowerCase().trim().split(/\s+/).every(word => `${runtimeSolverName(item)} ${item.id} ${item.name} ${item.state}`.toLowerCase().includes(word)));
  const clear = () => { setQuery(""); setGroup("all"); setStatus("all"); setOrigin("all"); };
  return <section className="solver-suite-panel" aria-label="SPIKE solver manager">
    <header><div className="solver-suite-brand"><img src="/spike-solver-suite.png" alt="" aria-hidden="true" width="56" height="56" /><div><h2>Solver manager</h2><p>Named internal solvers, bounded models and external engine adapters, with their setup workflows.</p></div></div><button type="button" className="spike-control--icon" onClick={onClose} aria-label="Close solver manager" title="Close solver manager"><X size={16} /></button></header>
    <nav className="solver-suite-tabs" aria-label="Solver manager views"><button type="button" className="spike-control--compact" aria-pressed={view === "blocks"} onClick={() => setView("blocks")}>Blocks and install groups</button><button type="button" className="spike-control--compact" aria-pressed={view === "capabilities"} onClick={() => setView("capabilities")}>Capabilities and evidence</button></nav>
    {view === "blocks" ? <SolverBlockPanel initialQuery={initialQuery} /> : <>
    <p className="solver-suite-notice"><strong>{runtimeProbed ? "Worker catalog loaded; execution remains separately gated." : "Runtime availability has not been probed here."}</strong> Names organize existing capabilities and preserve stable IDs. This index opens setup only. Each workflow checks its own worker, model, extension trust and runtime before execution. Implemented workflows and external adapters retain the limits shown below.</p>
    {onManageEngines && <button type="button" className="spike-control--compact" onClick={onManageEngines}>Engine registration and tuning</button>}
    <div className="solver-suite-filters">
      <label><span><Search size={13} /> Search capabilities</span><input type="search" aria-label="Search solver capabilities" placeholder="Try PDK, CFD, charge, PWM or admittance" value={query} onChange={event => setQuery(event.target.value)} /></label>
      <label><span>Domain</span><select aria-label="Filter solver domain" value={group} onChange={event => setGroup(event.target.value as SolverSuiteGroup | "all")}><option value="all">All domains</option>{solverSuiteGroups.map(value => <option key={value}>{value}</option>)}</select></label>
      <label><span>Capability status</span><select aria-label="Filter solver status" value={status} onChange={event => setStatus(event.target.value as SolverSuiteStatus | "all")}><option value="all">All statuses</option>{Object.entries(solverSuiteStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label><span>Provider and role</span><select aria-label="Filter solver provider" value={origin} onChange={event => setOrigin(event.target.value as SolverOrigin | "all")}><option value="all">All providers and roles</option>{Object.entries(solverOriginLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    </div>
    <details className="solver-manager-runtime"><summary>Worker registry ({runtimeSolvers.length} entries)</summary><p>Registry state is reported separately from source capability status. Domain and capability-status filters below apply to workflow cards; search and provider apply here. A workspace-only entry is not a generic board solver.</p>{!runtimeProbed && <p>Catalog probe unavailable or pending; supplied fallback entries do not establish installed runtime availability.</p>}{!runtimeEntries.length && <p>No registry entries available for the current search and provider. The source capability index remains accessible below.</p>}{(["internal", "external"] as const).map(provider => <section key={provider}><h3>{solverOriginLabels[provider]}</h3>{runtimeEntries.filter(item => runtimeSolverOrigin(item) === provider).map(item => {
      const workflow = runtimeWorkflow(item);
      return <article className="solver-manager-runtime-row" key={item.id}><h4>{runtimeSolverName(item)}</h4><code>{item.id}</code><p>Reported state: {item.state}; model status: {item.model_status}. {item.runnable === false ? "Not runnable through the generic registry route." : "Execution admission required in workflow."}</p>{item.reason && <p>{item.reason}</p>}{workflow?.action && <button type="button" className="spike-control--compact" onClick={() => onOpenWorkflow(workflow.action!, workflow.extensionId, workflow.id)}>Open setup workflow</button>}</article>;
    })}</section>)}</details>
    <div className="solver-suite-count"><span role="status">{entries.length} of {solverSuiteCatalog.length} capabilities</span><button type="button" className="spike-control--compact" onClick={clear} disabled={!query && group === "all" && status === "all" && origin === "all"}>Clear filters</button></div>
    <div className="solver-suite-results">{!entries.length ? <p className="solver-suite-empty">No capabilities match these filters. Clear filters or search a broader term.</p> : (Object.keys(solverOriginLabels) as SolverOrigin[]).flatMap(provider => solverSuiteGroups.map(domain => {
      const rows = entries.filter(item => item.group === domain && solverOrigin(item) === provider);
      return rows.length ? <section className="solver-suite-group" key={`${provider}-${domain}`} aria-label={`${solverOriginLabels[provider]}: ${domain}`}><h3>{solverOriginLabels[provider]} / {domain} <small>{rows.length}</small></h3><div className="solver-suite-cards">{rows.map(item => <article className="solver-suite-card" key={item.id}>
        <header><h4>{solverDisplayName(item)}</h4><span className={`solver-suite-badge ${item.status}`}>{solverSuiteStatusLabels[item.status]}</span></header>
        <p className="solver-manager-role">{solverOriginLabels[solverOrigin(item)]} · {item.title}</p>
        <p>{item.summary}</p><p className="solver-suite-limits"><strong>Scope limit: </strong>{item.limits}</p>
        <details><summary>Evidence reference</summary><p>{item.reference}</p><p>Source: {item.source}</p><p>Capability ID: <code>{item.id}</code></p>{capabilitySolverIds[item.id] && <p>Registry IDs: {capabilitySolverIds[item.id].join(", ")}</p>}</details>
        <footer>{item.action ? <button type="button" className="spike-control--compact" onClick={() => onOpenWorkflow(item.action!, item.extensionId, item.id)} aria-label={`${item.entryLabel ?? "Open setup workflow"}: ${solverDisplayName(item)}`}>{item.entryLabel ?? "Open setup workflow"}</button> : <button type="button" className="spike-control--compact" disabled>Unavailable</button>}<small>{item.extensionId ?? (item.status === "planned" ? "No executable route" : "Availability checked in workflow")}</small></footer>
      </article>)}</div></section> : null;
    }))}</div>
    </>}
  </section>;
}
