export type ConnectorPreset = {
  id: string;
  label: string;
  family: string;
  contactResistanceOhm?: number;
  pinWidthMm?: number;
  pinHeightMm?: number;
  note: string;
};

// Representative authoring estimates, deliberately not vendor-qualified limits.
export const CONNECTOR_PRESETS: ConnectorPreset[] = [
  { id: "unspecified", label: "Unspecified", family: "unspecified", note: "No electrical or dimensional estimate." },
  { id: "berg-254", label: "Berg / 2.54 mm header", family: "berg_header", contactResistanceOhm: 0.015, pinWidthMm: 0.64, pinHeightMm: 0.64, note: "Generic square-post estimate." },
  { id: "jumper-254", label: "2.54 mm jumper", family: "jumper", contactResistanceOhm: 0.03, pinWidthMm: 0.64, pinHeightMm: 0.64, note: "Generic shunt/jumper contact estimate." },
  { id: "dsub-signal", label: "D-sub signal", family: "d_sub", contactResistanceOhm: 0.01, pinWidthMm: 1.0, pinHeightMm: 1.0, note: "Representative signal-contact estimate." },
  { id: "xt-power", label: "XT power series", family: "xt_power", contactResistanceOhm: 0.0007, pinWidthMm: 3.5, pinHeightMm: 3.5, note: "Representative power-contact estimate; select the actual XT size during review." },
  { id: "harwin-datamate", label: "Harwin Datamate class", family: "datamate", contactResistanceOhm: 0.025, pinWidthMm: 0.5, pinHeightMm: 0.5, note: "Family-level estimate, not a Harwin datasheet guarantee." },
  { id: "harwin-gecko", label: "Harwin Gecko class", family: "gecko", contactResistanceOhm: 0.025, pinWidthMm: 0.4, pinHeightMm: 0.4, note: "Family-level estimate, not a Harwin datasheet guarantee." },
  { id: "micro-d-signal", label: "Micro-D signal", family: "micro_d", contactResistanceOhm: 0.02, pinWidthMm: 0.5, pinHeightMm: 0.5, note: "Representative Micro-D signal-contact estimate." },
  { id: "generic-power", label: "Generic power contact", family: "power", contactResistanceOhm: 0.001, pinWidthMm: 3.0, pinHeightMm: 3.0, note: "Starting estimate only; replace from the selected contact datasheet." },
  { id: "generic-signal", label: "Generic signal contact", family: "signal", contactResistanceOhm: 0.02, pinWidthMm: 0.5, pinHeightMm: 0.5, note: "Starting estimate only; replace from the selected contact datasheet." },
];

export function parsePinMappings(text: string): Record<string, string> {
  if (text.length > 1_000_000) throw new Error("Pin mapping text exceeds 1 MB.");
  const lines = text.split(/\r?\n/);
  if (lines.length > 100_000) throw new Error("Pin mapping text exceeds 100,000 lines.");
  const result: Record<string, string> = Object.create(null);
  const sources = new Set<string>(); const targets = new Set<string>();
  for (const [index, raw] of lines.entries()) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const parts = line.includes("=") ? line.split("=") : line.split(/[\t,]/);
    if (parts.length !== 2 || !parts[0].trim() || !parts[1].trim()) throw new Error(`Line ${index + 1}: expected source=destination.`);
    const source = parts[0].trim(); const target = parts[1].trim();
    if (sources.has(source)) throw new Error(`Line ${index + 1}: duplicate source pin ${source}.`);
    if (targets.has(target)) throw new Error(`Line ${index + 1}: duplicate destination pin ${target}.`);
    Object.defineProperty(result, source, { value: target, enumerable: true, configurable: true, writable: true });
    sources.add(source); targets.add(target);
  }
  return result;
}

export const formatPinMappings = (mapping: Record<string, string>) => Object.entries(mapping).map(([a, b]) => `${a}=${b}`).join("\n");

export function mergeConnectorPins(existing: Array<Record<string, unknown>>, ids: string[]): Array<Record<string, unknown>> {
  const prior = new Map(existing.map(pin => [String(pin.id), pin]));
  return ids.map(id => prior.get(id) ?? { id });
}

export function reconcilePairWires(wires: Array<Record<string, any>>, fromConnector: string, toConnector: string, mapping: Record<string, string>): Array<Record<string, any>> {
  const belongs = (wire: Record<string, any>) => (wire.from?.connector === fromConnector && wire.to?.connector === toConnector) || (wire.from?.connector === toConnector && wire.to?.connector === fromConnector);
  const pairWires = wires.filter(belongs); const retained = wires.filter(wire => !belongs(wire));
  const usedIds = new Set(wires.map(wire => String(wire.id)));
  const generated = Object.entries(mapping).map(([a, b]) => {
    const existing = pairWires.find(wire => (wire.from?.connector === fromConnector && String(wire.from?.pin) === a && wire.to?.connector === toConnector && String(wire.to?.pin) === b) || (wire.from?.connector === toConnector && String(wire.from?.pin) === b && wire.to?.connector === fromConnector && String(wire.to?.pin) === a));
    if (existing) return { ...existing, from: { connector: fromConnector, pin: a }, to: { connector: toConnector, pin: b } };
    const base = `${fromConnector}-${a}-${toConnector}-${b}`; let id = base; let suffix = 2;
    while (usedIds.has(id)) id = `${base}-${suffix++}`;
    usedIds.add(id); return { id, from: { connector: fromConnector, pin: a }, to: { connector: toConnector, pin: b } };
  });
  return [...retained, ...generated];
}
