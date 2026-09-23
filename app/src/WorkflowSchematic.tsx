import { useState } from "react";
import type { WorkflowSchematic as Diagram } from "./workflowSchematics";
import "./workflowSchematic.css";

export default function WorkflowSchematic({ title, diagram, onSelect }: { title: string; diagram: Diagram; onSelect?: (target: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const counts = new Map<number, number>();
  const nodes = diagram.nodes.map(node => {
    const row = counts.get(node.column) ?? 0;
    counts.set(node.column, row + 1);
    return { ...node, x: 30 + node.column * 290, y: 35 + row * 110 };
  });
  const height = Math.max(220, ...nodes.map(node => node.y + 100));
  const activate = (id: string) => { const target = nodes.find(node => node.id === id)?.target; if (target && onSelect) { setExpanded(false); onSelect(target); } };
  return <details className={`workflow-schematic ${expanded ? "expanded" : ""}`} onKeyDown={event => { if (event.key === "Escape") { setExpanded(false); event.stopPropagation(); } }}>
    <summary>{title}<span>Generated from current inputs</span></summary>
    <div className="workflow-schematic-controls"><span>{nodes.length} symbols · {diagram.edges.length} connections</span><button onClick={() => setExpanded(value => !value)}>{expanded ? "Compact view" : "Expand sheet"}</button></div>
    <div className="workflow-schematic-sheet"><svg width="850" height={height} viewBox={`0 0 850 ${height}`} role="group" aria-label={title}>
      {diagram.edges.map((edge, index) => {
        const from = nodes.find(node => node.id === edge.from), to = nodes.find(node => node.id === edge.to);
        if (!from || !to) return null;
        const x1 = from.x + 200, y1 = from.y + 32, x2 = to.x, y2 = to.y + 32;
        const route = x2 > x1 ? `M ${x1} ${y1} H ${(x1 + x2) / 2} V ${y2} H ${x2}` : `M ${x1} ${y1} H ${x1 + 20} V ${Math.max(from.y, to.y) + 85} H ${x2 - 20} V ${y2} H ${x2}`;
        return <g key={`${edge.from}-${edge.to}-${index}`} className={edge.scope ? "scope" : ""}><title>{edge.label}</title><path d={route} /><text x={x1 + 8} y={y1 - 7} className="wire-label">{edge.label}</text></g>;
      })}
      {nodes.map(node => <g key={node.id} className={`workflow-symbol ${node.target ? "editable" : ""}`} role={node.target ? "button" : undefined} tabIndex={node.target ? 0 : undefined} aria-label={`${node.label}: ${node.detail}`} onClick={() => activate(node.id)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activate(node.id); } }}><title>{node.label} · {node.detail}</title><rect x={node.x} y={node.y} width="200" height="64" /><text x={node.x + 12} y={node.y + 24}>{node.label.length > 26 ? `${node.label.slice(0, 25)}…` : node.label}</text><text className="detail" x={node.x + 12} y={node.y + 46}>{node.detail.length > 29 ? `${node.detail.slice(0, 28)}…` : node.detail}</text><circle cx={node.x} cy={node.y + 32} r="3" /><circle cx={node.x + 200} cy={node.y + 32} r="3" /></g>)}
    </svg></div>
    {diagram.notes.map(note => <p key={note}>{note}</p>)}
    <details><summary>Connection list</summary><ul>{diagram.edges.map((edge, index) => <li key={index}>{nodes.find(node => node.id === edge.from)?.label} → {nodes.find(node => node.id === edge.to)?.label}: {edge.label}</li>)}</ul></details>
  </details>;
}
