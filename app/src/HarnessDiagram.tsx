// SPDX-License-Identifier: Apache-2.0
import { useMemo, type KeyboardEvent } from "react";
import { buildHarnessDiagram, type HarnessRecord } from "./HarnessDiagramModel";
import "./HarnessDiagram.css";

export type HarnessDiagramSelection = { kind: "connector" | "splice" | "wire"; id: string } | null;

type Props = {
  document: HarnessRecord;
  selection: HarnessDiagramSelection;
  onSelect: (selection: HarnessDiagramSelection) => void;
};

const activate = (event: KeyboardEvent<SVGGElement | SVGPathElement>, action: () => void) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  action();
};

export default function HarnessDiagram({ document, selection, onSelect }: Props) {
  const identity = JSON.stringify([document.connectors, document.splices, document.wires]);
  const projection = useMemo(() => buildHarnessDiagram(document), [identity]);
  return <section className="harness-diagram" aria-label="Harness wiring diagram">
    <header><div><h4>Wiring diagram</h4><p>Select a connector, splice, or individual wire to inspect and edit it.</p></div><div className="harness-diagram-legend" aria-label="Wire role legend"><span data-role="power">Power</span><span data-role="return">Return</span><span data-role="signal">Signal</span><span data-role="other">Other</span></div></header>
    {!projection.nodes.length ? <p className="harness-diagram-empty">Add connectors or splices to create individual wires.</p> : <div className="harness-diagram-scroll"><svg viewBox={`0 0 ${projection.width} ${projection.height}`} role="img" aria-label={`${projection.nodes.length} endpoints and ${projection.wires.length} individual wires`}>
      <g className="harness-diagram-wires">{projection.wires.filter(wire => !wire.unresolved).map(wire => <g key={wire.id}>
        <path className="harness-wire-hit" d={wire.path} role="button" tabIndex={0} aria-label={`Select wire ${wire.id}`} aria-pressed={selection?.kind === "wire" && selection.id === wire.id} onClick={() => onSelect({ kind: "wire", id: wire.id })} onKeyDown={event => activate(event, () => onSelect({ kind: "wire", id: wire.id }))} />
        <path className={`harness-wire harness-wire--${wire.role}${selection?.kind === "wire" && selection.id === wire.id ? " is-selected" : ""}`} d={wire.path} aria-hidden="true" />
        <text x={wire.labelX} y={wire.labelY} textAnchor="middle">{wire.id}</text>
      </g>)}</g>
      <g className="harness-diagram-connectors">{projection.nodes.map(node => <g key={`${node.kind}:${node.id}`} className={`harness-node harness-node--${node.kind}${selection?.kind === node.kind && selection.id === node.id ? " is-selected" : ""}`} role="button" tabIndex={0} aria-label={`Select ${node.kind} ${node.id}`} aria-pressed={selection?.kind === node.kind && selection.id === node.id} onClick={() => onSelect({ kind: node.kind, id: node.id })} onKeyDown={event => activate(event, () => onSelect({ kind: node.kind, id: node.id }))}>
        <rect x={node.x} y={node.y} width={node.width} height={node.height} rx={8} />
        <text className="harness-node-title" x={node.x + 12} y={node.y + 23}>{node.label}</text>
        <text className="harness-node-id" x={node.x + 12} y={node.y + 39}>{node.id}</text>
        {node.pins.map(pin => <g key={pin.id}><circle cx={node.x + 8} cy={pin.y} r={4} /><circle cx={node.x + node.width - 8} cy={pin.y} r={4} /><text x={node.x + 18} y={pin.y + 4}>{pin.id}{pin.label !== pin.id ? ` · ${pin.label}` : ""}</text></g>)}
      </g>)}</g>
    </svg></div>}
    {projection.diagnostics.length > 0 && <div className="harness-diagram-diagnostics" role="alert"><b>{projection.diagnostics.length} wire endpoint issue{projection.diagnostics.length === 1 ? "" : "s"}</b><ul>{projection.diagnostics.slice(0, 8).map(item => <li key={item}>{item}</li>)}</ul></div>}
  </section>;
}
