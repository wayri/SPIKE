// SPDX-License-Identifier: Apache-2.0
import React, { useId, useMemo, useRef, useState } from "react";
import type { PowerTreeBudget, TopologyModel } from "./powerTree";
import { POWER_CARD_HEIGHT as H, POWER_CARD_WIDTH as W, presentPowerTree } from "./powerTreePresentation";
import "./powerTreeOverview.css";

const metric = (value: number | undefined, unit: string) => value === undefined || !Number.isFinite(value) ? "Not set" : `${Number(value.toPrecision(4))} ${unit}`;
export default function PowerTreeOverview({ model, budget, query = "", selectedId, onSelect, onEdit }: {
  model: TopologyModel; budget: PowerTreeBudget; query?: string; selectedId: string;
  onSelect: (id: string) => void; onEdit?: () => void;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [showShunts, setShowShunts] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [focus, setFocus] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const markerId = `power-arrow-${useId().replace(/:/g, "")}`;
  const graph = useMemo(() => presentPowerTree(model, collapsed, showShunts, true), [model, collapsed, showShunts]);
  const byId = new Map(graph.nodes.map(node => [node.id, node]));
  const selected = model.nodes.find(node => node.id === selectedId);
  const selectedBudget = selected ? budget.nodes[selected.id] : undefined;
  const selectedEdges = model.edges.filter(edge => edge.from === selectedId || edge.to === selectedId);
  const seeds = [selectedId, ...graph.edges.filter(edge => edge.viaRailIds?.includes(selectedId)).flatMap(edge => [edge.from,edge.to])];
  const related = new Set(seeds);
  // Highlight ancestors and descendants separately: sibling branches stay quiet.
  for (const direction of ["up", "down"]) {
    const seen = new Set(seeds), queue = [...seeds];
    for (let i = 0; i < queue.length; i++) for (const edge of graph.edges) {
      const id = direction === "up" && edge.to === queue[i] ? edge.from : direction === "down" && edge.from === queue[i] ? edge.to : null;
      if (id && !seen.has(id)) { seen.add(id); related.add(id); queue.push(id); }
    }
  }
  const matches = (id: string) => {
    const node = byId.get(id);
    return !query.trim() || `${node?.label} ${node?.ref} ${node?.net} ${node?.value}`.toLowerCase().includes(query.toLowerCase());
  };
  const toggle = (id: string) => setCollapsed(current => { const next = new Set(current); next.has(id) ? next.delete(id) : next.add(id); return next; });
  return <section className="power-overview" aria-label="Power distribution overview">
    <header className="power-overview-tools">
      <div><strong>Power distribution</strong><small>Supply → conversion → rails → loads</small></div>
      <button type="button" onClick={() => setZoom(value => Math.max(.4, value - .2))} aria-label="Zoom out power tree">−</button>
      <output aria-label="Power tree zoom">{Math.round(zoom * 100)}%</output>
      <button type="button" onClick={() => setZoom(value => Math.min(2, value + .2))} aria-label="Zoom in power tree">+</button>
      <button type="button" onClick={() => { setZoom(1); setCollapsed(new Set()); }}>Reset view</button>
      <button type="button" onClick={() => setZoom(Math.max(.4, Math.min(1.4, ((scrollRef.current?.clientWidth ?? 800) - 24) / graph.width)))}>Fit tree</button>
      <label><input type="checkbox" checked={showShunts} onChange={event => setShowShunts(event.target.checked)} /> Bypass / shunt parts ({graph.shuntCount})</label>
      <label><input type="checkbox" checked={focus} onChange={event => setFocus(event.target.checked)} /> Focus selected path</label>
    </header>
    <div className="power-overview-status" role="status">
      <span>{graph.nodes.length} blocks · {graph.inlineRailCount ?? 0} rails on wires · {graph.hiddenCount} collapsed · budget {budget.status}</span>
      <span>Solid: explicit mapping · dashed: inferred mapping · review badges: pending checks</span>
      {graph.cyclicIds.size > 0 && <strong>Cycle or cycle-dependent branch: {graph.cyclicIds.size} elements. Review in wiring editor.</strong>}
    </div>
    <div className="power-overview-body">
      <div ref={scrollRef} className="power-overview-scroll" tabIndex={0} aria-label="Scrollable power tree diagram">
        {graph.error ? <p role="alert">{graph.error}</p> : <div className="power-overview-sheet" style={{width: graph.width * zoom, height: graph.height * zoom}}>
          <svg width={graph.width * zoom} height={graph.height * zoom} style={{width:graph.width * zoom,height:graph.height * zoom,maxWidth:"none",maxHeight:"none"}} viewBox={`0 0 ${graph.width} ${graph.height}`} role="img" aria-label="Directed power connections">
            <defs><marker id={markerId} markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="currentColor" /></marker></defs>
            {graph.edges.map(edge => {
              const from = byId.get(edge.from)!, to = byId.get(edge.to)!, x1 = from.viewX + W, x2 = to.viewX;
              const y1 = from.viewY + H / 2, y2 = to.viewY + H / 2, mid = x1 + Math.max(22, (x2 - x1) / 2);
              const explicit = edge.inference?.confidence === "explicit" || (!edge.inference && edge.origin === "user" && edge.portBinding === "explicit");
              return <g key={edge.id} role={edge.viaRailIds?.length ? "button" : undefined} tabIndex={edge.viaRailIds?.length ? 0 : undefined}
                aria-label={edge.viaRailLabels?.length ? `Inspect rail ${edge.viaRailLabels.join(", ")}` : undefined}
                onClick={() => { if(edge.viaRailIds?.[0]) onSelect(edge.viaRailIds[0]); }}
                onKeyDown={event => { if(edge.viaRailIds?.[0] && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); onSelect(edge.viaRailIds[0]); } }}
                className={`power-overview-wire ${explicit ? "explicit" : "inferred"} ${focus && (!related.has(edge.from) || !related.has(edge.to)) ? "muted" : ""}`}>
                <title>{`${from.label} → ${to.label}${edge.net ? ` · ${edge.net}` : ""}. ${edge.inference?.evidence.join("; ") ?? "Direction has no retained inference evidence."}`}</title>
                <path d={`M${x1},${y1} H${mid} V${y2} H${x2}`} markerEnd={`url(#${markerId})`} />
                {edge.viaRailLabels?.length ? <text x={x1 + 5} y={y1 - 10}>{edge.viaRailLabels.join(" / ").slice(0,24)}</text> : null}
              </g>;
            })}
          </svg>
          {graph.nodes.map(node => {
            const value = budget.nodes[node.id], isSelected = node.id === selectedId;
            const review = node.inference?.reviewRequired ?? node.origin === "extracted";
            return <article key={node.id} className={`power-overview-card kind-${node.kind} ${isSelected ? "selected" : ""} ${!matches(node.id) || (focus && !related.has(node.id)) ? "muted" : ""}`}
              style={{left: node.viewX * zoom, top: node.viewY * zoom, width: W * zoom, height: H * zoom, fontSize: `${zoom}em`}}>
              <button type="button" className="power-overview-node" aria-pressed={isSelected} aria-label={`Select ${node.label}${node.ref ? ` ${node.ref}` : ""}`} onClick={() => onSelect(node.id)}>
                <span className="power-overview-kind">{node.kind} {review && <span title="Review retained inference evidence">· review</span>}</span>
                <strong title={node.label}>{node.label}</strong><span className="power-overview-part" title={node.value || node.net}>{node.value || node.net || "Unassigned device"}</span>
                <span className="power-overview-metrics">{metric(node.voltageV ?? value?.voltageV, "V")} <span>{value && (value.outputPowerW > 0 || node.loadPowerW !== undefined || node.loadCurrentA !== undefined) ? `${metric(value.outputPowerW, "W")}${budget.status === "complete" ? "" : " · partial"}` : "Demand not set"}</span></span>
              </button>
              {graph.edges.some(edge => edge.from === node.id) || collapsed.has(node.id) ? <button type="button" className="power-overview-collapse" aria-label={`${collapsed.has(node.id) ? "Expand" : "Collapse"} branch ${node.label}`} aria-expanded={!collapsed.has(node.id)} onClick={() => toggle(node.id)}>{collapsed.has(node.id) ? "+" : "−"}</button> : null}
            </article>;
          })}
        </div>}
      </div>
      <aside className="power-overview-inspector" aria-label="Power tree selection evidence">
        {selected ? <><small>SELECTED ELEMENT</small><h3>{selected.label}</h3><p>{selected.value || selected.net || selected.kind}</p>
          <dl><dt>Voltage</dt><dd>{metric(selected.voltageV ?? selectedBudget?.voltageV, "V")}</dd><dt>Assigned current</dt><dd>{metric(selected.loadCurrentA, "A")}</dd><dt>Assigned power</dt><dd>{metric(selected.loadPowerW, "W")}</dd><dt>Efficiency</dt><dd>{metric(selected.efficiencyPercent, "%")}</dd></dl>
          {selectedBudget && (selectedBudget.outputPowerW > 0 || selected.loadPowerW !== undefined || selected.loadCurrentA !== undefined) && <><h4>Operating-case estimate</h4><dl><dt>Input voltage</dt><dd>{metric(selectedBudget.inputVoltageV,"V")}</dd><dt>Output current</dt><dd>{metric(selectedBudget.currentA,"A")}</dd><dt>Input power</dt><dd>{metric(selectedBudget.inputPowerW,"W")}</dd><dt>Output power</dt><dd>{metric(selectedBudget.outputPowerW,"W")}</dd><dt>Loss</dt><dd>{metric(selectedBudget.lossW,"W")}</dd></dl>{budget.status !== "complete" && <small>Partial budget: only assigned loads and conversion assumptions are included.</small>}</>}
          {onEdit && <button type="button" onClick={onEdit}>Edit selected element</button>}
          <h4>Inference evidence</h4><p>{selected.inference?.confidence ?? (selected.origin === "user" ? "User authored" : "Legacy inference; review required")}</p>
          <ul>{(selected.inference?.evidence ?? ["No retained pin-role evidence. Verify source, input/output direction, voltage and demand before using this tree."]).map((evidence, index) => <li key={index}>{evidence}</li>)}</ul>
          <h4>Connections ({selectedEdges.length})</h4><ul>{selectedEdges.map(edge => <li key={edge.id}>{model.nodes.find(node => node.id === edge.from)?.label} → {model.nodes.find(node => node.id === edge.to)?.label}<small>{edge.net} · {edge.inference?.confidence ?? edge.portBinding ?? "unreviewed"}</small>{edge.inference?.evidence?.map((evidence, index) => <small key={index}>{evidence}</small>)}</li>)}</ul>
        </> : <p>Select a source, converter, rail or load to inspect its electrical identity and evidence.</p>}
        <details><summary>Study notices ({budget.warnings.length})</summary><ul>{budget.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>
        <p className="power-overview-note">Power estimates reuse SPIKE's existing tree budget. They are not SPICE results. Parallel-source sharing and switching behaviour require explicit circuit models and a solver run.</p>
      </aside>
    </div>
  </section>;
}
