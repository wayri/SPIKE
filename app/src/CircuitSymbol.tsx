import type { TopologyNode, TopologyNodeKind } from "./powerTree";

type SymbolCode = "R" | "C" | "L" | "D" | "Q" | "U" | "T" | "J" | "V" | "GND" | "RAIL" | "LOAD" | "REG" | "HARNESS" | "DRIVER" | "CHANNEL" | "TERM" | "RECEIVER";

export function circuitSymbolCode(node: Pick<TopologyNode, "ref" | "kind" | "simulationModel">): SymbolCode {
  const primitive: Record<string, SymbolCode> = { resistor: "R", capacitor: "C", inductor: "L", diode: "D", mosfet: "Q" };
  if (node.simulationModel && primitive[node.simulationModel]) return primitive[node.simulationModel];
  const prefix = node.ref?.match(/^[A-Za-z]+/)?.[0].toUpperCase() ?? "";
  if (prefix.startsWith("R")) return "R";
  if (prefix.startsWith("C")) return "C";
  if (prefix.startsWith("L") || prefix.startsWith("FB")) return "L";
  if (prefix.startsWith("D")) return "D";
  if (prefix.startsWith("Q")) return "Q";
  if (prefix.startsWith("U") || prefix.startsWith("IC")) return "U";
  if (prefix.startsWith("T") || node.kind === "transformer") return "T";
  if (/^(J|P|CN)/.test(prefix) || node.kind === "connector") return "J";
  if (node.kind === "source") return "V";
  if (node.kind === "regulator") return "REG";
  if (node.kind === "return") return "GND";
  if (node.kind === "rail") return "RAIL";
  if (node.kind === "harness") return "HARNESS";
  if (node.kind === "driver") return "DRIVER";
  if (node.kind === "channel") return "CHANNEL";
  if (node.kind === "termination") return "TERM";
  if (node.kind === "receiver") return "RECEIVER";
  return "LOAD";
}

export default function CircuitSymbol({ node, size = 26 }: { node: Pick<TopologyNode, "ref" | "kind" | "simulationModel">; size?: number }) {
  const code = circuitSymbolCode(node);
  return <svg className={`circuit-symbol symbol-${code.toLowerCase()}`} width={size} height={size} viewBox="0 0 32 24" role="img" aria-label={`${code} circuit symbol`}>
    {code === "R" && <path d="M1 12h4l2.2-5 3.5 10 3.5-10 3.5 10 3.5-10 3.5 10 2.2-5H31" />}
    {code === "C" && <><path d="M1 12h11M20 12h11M12 4v16M20 4v16" /></>}
    {code === "L" && <path d="M1 12h4c0-7 6-7 6 0 0-7 6-7 6 0 0-7 6-7 6 0 0-7 6-7 6 0h2" />}
    {code === "D" && <><path d="M1 12h8M23 12h8M9 5v14l14-7zM23 5v14" /></>}
    {code === "Q" && <><path d="M3 12h7M10 5v14M17 7v10M17 9l10-5v6M17 15l10 5v-6" /><path className="filled" d="m23 17 4 3-1-5z" /></>}
    {code === "U" && <><rect x="8" y="3" width="16" height="18" rx="1" /><path d="M2 7h6M2 12h6M2 17h6M24 7h6M24 12h6M24 17h6" /><text x="16" y="15">U</text></>}
    {code === "T" && <><path d="M2 12h4c0-7 5-7 5 0 0-7 5-7 5 0M16 12c0-7 5-7 5 0 0-7 5-7 5 0h4M15 3v18M18 3v18" /></>}
    {code === "J" && <><path d="M2 6h9M2 12h9M2 18h9M21 6h9M21 12h9M21 18h9" /><rect x="11" y="3" width="10" height="18" rx="1" /><circle cx="16" cy="7" r="1" /><circle cx="16" cy="12" r="1" /><circle cx="16" cy="17" r="1" /></>}
    {code === "V" && <><path d="M1 12h6M25 12h6" /><circle cx="16" cy="12" r="9" /><path d="M12 9h8M16 5v8M12 17h8" /></>}
    {code === "GND" && <><path d="M16 2v8M7 10h18M10 14h12M13 18h6M15 22h2" /></>}
    {code === "RAIL" && <><path d="M1 12h30M7 7v10M16 7v10M25 7v10" /><circle cx="7" cy="12" r="2" /><circle cx="16" cy="12" r="2" /><circle cx="25" cy="12" r="2" /></>}
    {code === "LOAD" && <><path d="M1 12h7M24 12h7" /><rect x="8" y="4" width="16" height="16" rx="1" /><path d="M11 16l4-8 3 8 3-5" /></>}
    {code === "REG" && <><path d="M1 12h6M25 12h6" /><rect x="7" y="4" width="18" height="16" rx="2" /><path d="M10 14l4-5 4 6 4-6" /></>}
    {code === "HARNESS" && <><path d="M1 7h5c5 0 5 10 10 10s5-10 10-10h5M1 17h5c5 0 5-10 10-10s5 10 10 10h5" /></>}
    {code === "DRIVER" && <><path d="M1 12h7M24 12h7M8 4l16 8-16 8z" /><text x="15" y="15">D</text></>}
    {code === "CHANNEL" && <><path d="M1 12h5l3-5 5 10 5-10 4 5h8" /><path d="M3 5h26M3 19h26" /></>}
    {code === "TERM" && <><path d="M1 12h7M24 12h7" /><path d="M8 12l3-6 3 12 3-12 3 12 4-6" /><path d="M27 5v14" /></>}
    {code === "RECEIVER" && <><path d="M1 12h7M24 12h7M24 4L8 12l16 8z" /><text x="17" y="15">R</text></>}
  </svg>;
}

export function paletteSymbol(kind: TopologyNodeKind) {
  return <CircuitSymbol node={{ kind, ref: kind === "passive" ? "R" : undefined }} size={22} />;
}
