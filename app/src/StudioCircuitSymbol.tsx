// SPDX-License-Identifier: Apache-2.0
import type { StudioPart } from "./studioBoardCircuit";
export default function StudioCircuitSymbol({ part, unit }: {
    part: StudioPart;
    unit: number;
}) {
    const kind = part.model_binding.primitive ?? (/^R[0-9]/i.test(part.ref) ? "resistor" : /^C[0-9]/i.test(part.ref) ? "capacitor" : /^L[0-9]/i.test(part.ref) ? "inductor" : "block");
    return <g><g transform={`rotate(${part.placement.rotation_deg}) scale(${unit})`} fill="none" stroke="var(--spike-table-text)" strokeWidth={.65}>
  {kind === "resistor" ? <path d="M -5 0 H -3 L -2 -2 L -1 2 L 0 -2 L 1 2 L 2 -2 L 3 0 H 5"/> : kind === "capacitor" ? <path d="M -5 0 H -1 M -1 -3 V 3 M 1 -3 V 3 M 1 0 H 5"/> : kind === "inductor" ? <path d="M -5 0 H -3 C -3 -3 -1 -3 -1 0 C -1 -3 1 -3 1 0 C 1 -3 3 -3 3 0 H 5"/> : kind === "voltage_source" || kind === "current_source" ? <><circle r={3}/><path d="M -5 0 H -3 M 3 0 H 5"/><text x={0} y={1} textAnchor="middle" fontSize={3} stroke="none" fill="var(--spike-table-text)">{kind === "voltage_source" ? "+" : "→"}</text></> : <rect x={-4} y={-2.5} width={8} height={5}/>}
 </g><text y={-unit * 4} fontSize={unit * 3.5} textAnchor="middle" fill="var(--spike-table-text)">{part.ref}</text><text y={unit * 6} fontSize={unit * 2.8} textAnchor="middle" fill="var(--spike-table-muted)">{part.value.length > 20 ? part.value.slice(0, 19) + "…" : part.value}</text></g>;
}
