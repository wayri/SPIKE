// SPDX-License-Identifier: MIT
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import type { ParasiticResult, ScalarSample, SolverResultBundle } from "./analysisResults";
import { buildImpedancePlot, buildTracePlot, resultPlotFields, resultTraceGroups } from "./traceResultPlots";
import "./traceResultsWorkbench.css";

const PlotlyChart = lazy(() => import("./PlotlyChart"));
type PlotField = { key: string; label: string; unit: string; scale?: number; samples: ScalarSample[]; impedance?: ParasiticResult[] };
type TraceGroup = { id: string; net: string; layer: string; elementId: string; label: string; count: number };

export default function TraceResultsWorkbench({ result, domain, targetOhm, targetNet, onClose, onDetach }: { result: SolverResultBundle | null; domain: "pi" | "si"; targetOhm?: number; targetNet?: string; onClose?: () => void; onDetach?: () => void }) {
  const fields = useMemo(() => resultPlotFields(result, domain) as PlotField[], [result, domain]);
  const [fieldKey, setFieldKey] = useState("");
  const field = fields.find(candidate => candidate.key === fieldKey) ?? fields[0];
  const impedance = field?.key === "impedance_sweep";
  const groups = useMemo(() => resultTraceGroups(field?.samples ?? []) as TraceGroup[], [field]);
  const networks = field?.impedance ?? [];
  const nets = useMemo(() => impedance
    ? [...new Set(networks.map(network => network.net ?? ""))]
    : [...new Set(groups.map(group => group.net ?? ""))], [groups, impedance, networks]);
  const [net, setNet] = useState("");
  const [mode, setMode] = useState<"spatial" | "height" | "samples">("spatial");
  const [openTabs, setOpenTabs] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState("overview");
  const [comparisons, setComparisons] = useState<string[]>([]);
  const [groupQuery, setGroupQuery] = useState("");
  const [groupLimit, setGroupLimit] = useState(160);
  useEffect(() => { if (field && field.key !== fieldKey) setFieldKey(field.key); }, [field, fieldKey]);
  useEffect(() => { setNet(current => nets.includes(current) ? current : nets[0] ?? ""); setOpenTabs([]); setActiveTab("overview"); setComparisons([]); }, [field?.key, nets.join("\u0001")]);
  useEffect(() => { setOpenTabs([]); setActiveTab("overview"); setComparisons([]); setGroupQuery(""); setGroupLimit(160); }, [net]);
  useEffect(() => { if (impedance && mode !== "samples") setMode("samples"); }, [impedance, mode]);
  const netGroups = groups.filter(group => group.net === net);
  const filteredGroups = netGroups.filter(group => `${group.label} ${group.layer} ${group.elementId}`.toLowerCase().includes(groupQuery.toLowerCase()));
  const activeGroup = activeTab === "overview" ? undefined : groups.find(group => group.id === activeTab);
  const plot = useMemo(() => {
    if (!field || !nets.includes(net)) return null;
    if (impedance) return buildImpedancePlot(networks, net, domain === "pi" && targetNet === net ? targetOhm : undefined);
    const groupIds = activeGroup ? [activeGroup.id] : comparisons.length ? comparisons : undefined;
    return buildTracePlot(field.samples, { net, groupIds, mode, label: field.label, unit: field.unit, scale: field.scale, maxSamples: 20_000 });
  }, [field, net, impedance, networks, activeGroup, comparisons, mode, domain, targetOhm, targetNet]);
  const open = (id: string) => { setOpenTabs(tabs => tabs.includes(id) ? tabs : [...tabs.slice(-15), id]); setActiveTab(id); };
  if (!result) return <section className="trace-results-workbench"><header><div><small>{domain.toUpperCase()} RESULTS</small><h2>Trace graphs</h2></div>{onClose && <button onClick={onClose}>Close</button>}</header><div className="trace-empty">Run or load an analysis to inspect trace results.</div></section>;
  if (!fields.length) return <section className="trace-results-workbench"><header><div><small>{domain.toUpperCase()} RESULTS</small><h2>Trace graphs</h2></div>{onClose && <button onClick={onClose}>Close</button>}</header><div className="trace-empty">This result contains no plottable {domain.toUpperCase()} trace fields.</div></section>;
  return <section className={`trace-results-workbench${impedance ? " trace-results-frequency" : ""}`} aria-label={`${domain.toUpperCase()} trace result graphs`}>
    <header><div><small>{domain.toUpperCase()} RESULTS</small><h2>Trace graphs</h2></div><span>Status: {result.status} · Model: {result.model_status} · {plot?.shown ?? 0} of {plot?.total ?? 0} samples</span>{onDetach && <button onClick={onDetach}>Open in window</button>}{onClose && <button onClick={onClose}>Close</button>}</header>
    <div className="trace-toolbar">
      <label>Metric<select value={field.key} onChange={event => setFieldKey(event.target.value)}>{fields.map(item => <option key={item.key} value={item.key}>{item.label} ({item.unit})</option>)}</select></label>
      <label>Net<select value={net} onChange={event => setNet(event.target.value)}>{nets.map(item => <option key={item || "__unassigned__"} value={item}>{item || "Unassigned net"}</option>)}</select></label>
      <fieldset disabled={impedance}><legend>Plot mode</legend><button className={mode === "spatial" ? "active" : ""} aria-pressed={mode === "spatial"} onClick={() => setMode("spatial")}>3D spatial</button><button className={mode === "height" ? "active" : ""} aria-pressed={mode === "height"} onClick={() => setMode("height")}>3D field height</button><button className={mode === "samples" ? "active" : ""} aria-pressed={mode === "samples"} onClick={() => setMode("samples")}>2D samples</button></fieldset>
    </div>
    {!impedance && <aside className="trace-selector" aria-label="Trace comparison selection"><b>Traces and elements</b><input aria-label="Filter traces and elements" value={groupQuery} onChange={event => { setGroupQuery(event.target.value); setGroupLimit(160); }} placeholder="Filter identifier or layer" />{!filteredGroups.length && <span>No matching trace identifiers on this net.</span>}{filteredGroups.slice(0, groupLimit).map(group => <div key={group.id}><label><input type="checkbox" checked={comparisons.includes(group.id)} disabled={!comparisons.includes(group.id) && comparisons.length >= 16} onChange={() => setComparisons(current => current.includes(group.id) ? current.filter(id => id !== group.id) : current.length < 16 ? [...current, group.id] : current)} />{group.label} <small>{group.count} samples</small></label><button onClick={() => open(group.id)}>Open</button></div>)}{filteredGroups.length > groupLimit && <button onClick={() => setGroupLimit(limit => limit + 160)}>Show 160 more</button>}</aside>}
    <div className="trace-tabs" role="tablist" aria-label="Open result graphs"><button role="tab" aria-selected={activeTab === "overview"} onClick={() => setActiveTab("overview")}>Net overview</button>{openTabs.map(id => { const group = groups.find(item => item.id === id); return <span key={id}><button role="tab" aria-selected={activeTab === id} onClick={() => setActiveTab(id)}>{group?.label ?? id}</button><button aria-label={`Close ${group?.label ?? id}`} onClick={() => { setOpenTabs(tabs => tabs.filter(tab => tab !== id)); if (activeTab === id) setActiveTab("overview"); }}>×</button></span>; })}</div>
    <div className="trace-active-plot" role="tabpanel">{impedance && domain === "pi" && targetNet === net && Number.isFinite(targetOhm) && Number(targetOhm) > 0 && <p className="trace-notice">Dashed line: {targetOhm} ohm PDN screening target for this net. The target is a design limit, not a solved field.</p>}{mode === "spatial" && field.samples.some(sample => sample.z_mm === undefined) && <p className="trace-notice">Samples without Z coordinates are displayed at z = 0. Hover values remain the exact returned source samples; smooth face colors are a display reconstruction.</p>}{plot && plot.shown > 0 ? <Suspense fallback={<div className="trace-empty">Loading graph renderer…</div>}><PlotlyChart data={plot.data} layout={plot.layout} revision={`${field.key}:${net}:${activeTab}:${comparisons.join(",")}:${mode}:${targetNet ?? ""}:${targetOhm ?? ""}`} /></Suspense> : <div className="trace-empty">No samples match this metric, net, and trace selection.</div>}</div>
  </section>;
}
