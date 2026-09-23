import CircuitSymbol from "./CircuitSymbol";
import { type TopologyModel, topologyPorts } from "./powerTree";
import { schematicHeight, schematicWire, schematicPort } from "./schematicGeometry";

export default function TopologyPreview({ model }: { model: TopologyModel }) {
  const width = Math.max(400, ...model.nodes.map(node => node.x + 240));
  const height = Math.max(180, ...model.nodes.map(node => node.y + schematicHeight(node, model.domain) + 25));
  return <div className="topology-preview"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Generated schematic preview">
    {model.edges.map(edge => { const route = schematicWire(edge, model.nodes, model.domain); return route && <path key={edge.id} d={route.d} />; })}
    {model.nodes.map(node => <g key={node.id}><title>{node.label} · {node.net} · {node.kind}</title>{topologyPorts(node, model.domain).map(port => { const point = schematicPort(node, model.domain, port.id, port.side); return <path key={port.id} d={`M ${point.x} ${point.y} H ${node.x + (port.side === "left" ? 48 : 162)}`} />; })}<rect x={node.x + 48} y={node.y + 8} width="114" height={schematicHeight(node, model.domain) - 16} /><g transform={`translate(${node.x + 74}, ${node.y + schematicHeight(node, model.domain) / 2 - 31})`}><CircuitSymbol node={node} size={62} /></g><text x={node.x + 105} y={node.y - 9} textAnchor="middle">{node.label}</text></g>)}
  </svg><details><summary>Review connections</summary><ul>{model.edges.map(edge => <li key={edge.id}>{model.nodes.find(node => node.id === edge.from)?.label} → {model.nodes.find(node => node.id === edge.to)?.label}{edge.net ? ` · ${edge.net}` : ""}</li>)}</ul></details></div>;
}
