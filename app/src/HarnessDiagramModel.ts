// SPDX-License-Identifier: Apache-2.0

export type HarnessRecord = Record<string, any>;
export type HarnessEndpoint = { connector: string; pin: string } | { splice: string };
export type HarnessWireRole = "unspecified" | "power" | "return" | "signal" | "other" | "shield";
export type HarnessPairKind = "differential" | "twisted";

export type HarnessDiagramPin = { id: string; label: string; y: number };
export type HarnessDiagramNode = { kind: "connector" | "splice"; id: string; label: string; x: number; y: number; width: number; height: number; pins: HarnessDiagramPin[] };
export type HarnessDiagramWire = { id: string; path: string; labelX: number; labelY: number; role: HarnessWireRole; unresolved: boolean };
export type HarnessDiagramProjection = { width: number; height: number; nodes: HarnessDiagramNode[]; wires: HarnessDiagramWire[]; diagnostics: string[] };

const connectorId = (endpoint: unknown): string => endpoint && typeof endpoint === "object" && typeof (endpoint as HarnessRecord).connector === "string"
  ? (endpoint as HarnessRecord).connector : "";
const pinId = (endpoint: unknown): string => endpoint && typeof endpoint === "object" && typeof (endpoint as HarnessRecord).pin === "string"
  ? (endpoint as HarnessRecord).pin : "";
const spliceId = (endpoint: unknown): string => endpoint && typeof endpoint === "object" && typeof (endpoint as HarnessRecord).splice === "string"
  ? (endpoint as HarnessRecord).splice : "";
const records = (value: unknown): HarnessRecord[] => Array.isArray(value) ? value.filter(item => item && typeof item === "object" && !Array.isArray(item)) : [];

export function nextHarnessId(prefix: string, usedIds: Iterable<string>): string {
  const used = new Set(usedIds);
  let index = 1;
  while (used.has(`${prefix}${index}`)) index += 1;
  return `${prefix}${index}`;
}

function rewriteConnectorReferences(value: unknown, previousId: string, nextId: string): unknown {
  if (Array.isArray(value)) return value.map(item => rewriteConnectorReferences(item, previousId, nextId));
  if (!value || typeof value !== "object") return value;
  const item = value as HarnessRecord;
  const result: HarnessRecord = {};
  for (const [key, content] of Object.entries(item)) {
    result[key] = key === "connector" && content === previousId ? nextId : rewriteConnectorReferences(content, previousId, nextId);
  }
  return result;
}

export function renameHarnessConnector(document: HarnessRecord, previousId: string, nextId: string): HarnessRecord {
  if (!nextId.trim()) throw new Error("Connector ID cannot be blank.");
  const connectors = records(document.connectors);
  if (previousId !== nextId && connectors.some(item => item.id === nextId)) throw new Error("Connector ID already exists.");
  return rewriteConnectorReferences(document, previousId, nextId) as HarnessRecord;
}

function rewriteSpliceReferences(value: unknown, previousId: string, nextId: string): unknown {
  if (Array.isArray(value)) return value.map(item => rewriteSpliceReferences(item, previousId, nextId));
  if (!value || typeof value !== "object") return value;
  const result: HarnessRecord = {};
  for (const [key, content] of Object.entries(value as HarnessRecord)) {
    result[key] = key === "splice" && content === previousId ? nextId : rewriteSpliceReferences(content, previousId, nextId);
  }
  return result;
}

export function renameHarnessSplice(document: HarnessRecord, previousId: string, nextId: string): HarnessRecord {
  if (!nextId.trim()) throw new Error("Splice ID cannot be blank.");
  const splices = records(document.splices);
  if (previousId !== nextId && splices.some(item => item.id === nextId)) throw new Error("Splice ID already exists.");
  return rewriteSpliceReferences(document, previousId, nextId) as HarnessRecord;
}

export function addHarnessSplice(document: HarnessRecord, id: string): HarnessRecord {
  if (!id.trim()) throw new Error("Splice ID cannot be blank.");
  if (records(document.splices).some(splice => splice.id === id)) throw new Error("Splice ID already exists.");
  return { ...document, splices: [...records(document.splices), { id }] };
}

function cleanHarnessPiAfterConnectorDelete(extensions: unknown, deletedId: string): unknown {
  if (!extensions || typeof extensions !== "object" || Array.isArray(extensions)) return extensions;
  const next = { ...(extensions as HarnessRecord) };
  const raw = next["spike.harness-pi"];
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return next;
  const setup = { ...(raw as HarnessRecord) };
  const uses = (endpoint: unknown) => connectorId(endpoint) === deletedId;
  if (uses(setup.ground)) delete setup.ground;
  if (Array.isArray(setup.terminals)) setup.terminals = setup.terminals.filter((item: HarnessRecord) => !uses(item?.positive) && !uses(item?.negative));
  if (Array.isArray(setup.contacts)) setup.contacts = setup.contacts.filter((item: HarnessRecord) => !uses(item?.from) && !uses(item?.to));
  next["spike.harness-pi"] = setup;
  return next;
}

function cleanHarnessPiAfterSpliceDelete(extensions: unknown, deletedId: string): unknown {
  if (!extensions || typeof extensions !== "object" || Array.isArray(extensions)) return extensions;
  const next = { ...(extensions as HarnessRecord) };
  const raw = next["spike.harness-pi"];
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return next;
  const setup = { ...(raw as HarnessRecord) };
  const uses = (endpoint: unknown) => spliceId(endpoint) === deletedId;
  if (uses(setup.ground)) delete setup.ground;
  if (Array.isArray(setup.terminals)) setup.terminals = setup.terminals.filter((item: HarnessRecord) => !uses(item?.positive) && !uses(item?.negative));
  if (Array.isArray(setup.contacts)) setup.contacts = setup.contacts.filter((item: HarnessRecord) => !uses(item?.from) && !uses(item?.to));
  next["spike.harness-pi"] = setup;
  return next;
}

function pruneWireMembership(document: HarnessRecord, removedWireIds: Set<string>): Pick<HarnessRecord, "pairs" | "cables"> {
  const pairs = records(document.pairs).filter(pair => Array.isArray(pair.wire_ids)
    && !pair.wire_ids.some((id: unknown) => removedWireIds.has(String(id))));
  const cables = records(document.cables).flatMap(cable => {
    if (!Array.isArray(cable.wire_ids)) return [cable];
    const wire_ids = cable.wire_ids.filter((id: unknown) => !removedWireIds.has(String(id)));
    return wire_ids.length ? [{ ...cable, wire_ids }] : [];
  });
  return { pairs, cables };
}

export function deleteHarnessWire(document: HarnessRecord, wireId: string): HarnessRecord {
  const removed = new Set([wireId]);
  const membership = pruneWireMembership(document, removed);
  const wires = records(document.wires).filter(wire => wire.id !== wireId).map(wire => {
    if (wire.return_wire_id !== wireId) return wire;
    const next = { ...wire };
    delete next.return_wire_id;
    return next;
  });
  return { ...document, wires, ...membership };
}

export function setHarnessWireRole(document: HarnessRecord, wireId: string, role: HarnessWireRole): HarnessRecord {
  const wires = records(document.wires).map(wire => {
    const next = { ...wire };
    if (wire.id === wireId) {
      if (role === "unspecified") delete next.role; else next.role = role;
    }
    if (role !== "return" && next.return_wire_id === wireId) delete next.return_wire_id;
    return next;
  });
  return { ...document, wires };
}

export function deleteHarnessConnector(document: HarnessRecord, deletedId: string): HarnessRecord {
  const removedWireIds = new Set(records(document.wires)
    .filter(wire => connectorId(wire.from) === deletedId || connectorId(wire.to) === deletedId)
    .map(wire => String(wire.id)));
  const membership = pruneWireMembership(document, removedWireIds);
  const wires = records(document.wires).filter(wire => !removedWireIds.has(String(wire.id))).map(wire => {
    const next = { ...wire };
    if (removedWireIds.has(String(next.return_wire_id))) delete next.return_wire_id;
    if (next.electrical && typeof next.electrical === "object" && connectorId(next.electrical.reference) === deletedId) {
      next.electrical = { ...next.electrical };
      delete next.electrical.reference;
      if (!Object.keys(next.electrical).length) delete next.electrical;
    }
    return next;
  });
  const cables = membership.cables.map((cable: HarnessRecord) => {
    if (!Array.isArray(cable.shield?.terminations)) return cable;
    return { ...cable, shield: { ...cable.shield, terminations: cable.shield.terminations.filter((item: unknown) => connectorId(item) !== deletedId) } };
  });
  return {
    ...document,
    connectors: records(document.connectors).filter(connector => connector.id !== deletedId),
    wires,
    pairs: membership.pairs,
    cables,
    extensions: cleanHarnessPiAfterConnectorDelete(document.extensions, deletedId),
  };
}

export function deleteHarnessSplice(document: HarnessRecord, deletedId: string): HarnessRecord {
  const removedWireIds = new Set(records(document.wires)
    .filter(wire => spliceId(wire.from) === deletedId || spliceId(wire.to) === deletedId)
    .map(wire => String(wire.id)));
  const membership = pruneWireMembership(document, removedWireIds);
  const wires = records(document.wires).filter(wire => !removedWireIds.has(String(wire.id))).map(wire => {
    const next = { ...wire };
    if (removedWireIds.has(String(next.return_wire_id))) delete next.return_wire_id;
    if (next.electrical && typeof next.electrical === "object" && spliceId(next.electrical.reference) === deletedId) {
      next.electrical = { ...next.electrical };
      delete next.electrical.reference;
      if (!Object.keys(next.electrical).length) delete next.electrical;
    }
    return next;
  });
  const cables = membership.cables.map((cable: HarnessRecord) => {
    if (!Array.isArray(cable.shield?.terminations)) return cable;
    return { ...cable, shield: { ...cable.shield, terminations: cable.shield.terminations.filter((item: unknown) => spliceId(item) !== deletedId) } };
  });
  return {
    ...document,
    splices: records(document.splices).filter(splice => splice.id !== deletedId),
    wires,
    pairs: membership.pairs,
    cables,
    extensions: cleanHarnessPiAfterSpliceDelete(document.extensions, deletedId),
  };
}

export function addHarnessWire(document: HarnessRecord, id: string, from: HarnessEndpoint, to: HarnessEndpoint): HarnessRecord {
  if (!id.trim()) throw new Error("Wire ID cannot be blank.");
  if (records(document.wires).some(wire => wire.id === id)) throw new Error("Wire ID already exists.");
  const endpointAvailable = (endpoint: HarnessEndpoint) => "connector" in endpoint
    ? records(document.connectors).some(connector => connector.id === endpoint.connector && records(connector.pins).some(pin => String(pin.id) === endpoint.pin))
    : records(document.splices).some(splice => splice.id === endpoint.splice);
  if (!endpointAvailable(from) || !endpointAvailable(to)) throw new Error("Wire endpoints must reference existing connector pins or splices.");
  if (connectorId(from) && connectorId(from) === connectorId(to) && pinId(from) === pinId(to)) throw new Error("Choose two different endpoints.");
  if (spliceId(from) && spliceId(from) === spliceId(to)) throw new Error("Choose two different endpoints.");
  return { ...document, wires: [...records(document.wires), { id, from: { ...from }, to: { ...to } }] };
}

function connectorSpan(wire: HarnessRecord): string {
  const ids = [connectorId(wire.from), connectorId(wire.to)];
  return ids.every(Boolean) ? ids.sort().join("\u0000") : "";
}

function cableMembership(document: HarnessRecord, wireId: string): string {
  return records(document.cables).filter(cable => Array.isArray(cable.wire_ids) && cable.wire_ids.includes(wireId)).map(cable => String(cable.id)).sort().join("\u0000");
}

export function pairCandidateWires(document: HarnessRecord, wireId: string): HarnessRecord[] {
  const wires = records(document.wires);
  const selected = wires.find(wire => wire.id === wireId);
  if (!selected) return [];
  const span = connectorSpan(selected);
  const membership = cableMembership(document, wireId);
  return wires.filter(wire => wire.id !== wireId && span && connectorSpan(wire) === span && cableMembership(document, String(wire.id)) === membership);
}

export function wirePair(document: HarnessRecord, wireId: string): HarnessRecord | undefined {
  return records(document.pairs).find(pair => Array.isArray(pair.wire_ids) && pair.wire_ids.includes(wireId));
}

export function assignHarnessPair(document: HarnessRecord, wireId: string, mateId: string, kind: HarnessPairKind | "none", options: { twisted?: boolean; twistPitchMm?: number } = {}, id?: string): HarnessRecord {
  const pairs = records(document.pairs);
  const current = wirePair(document, wireId);
  const withoutMembers = pairs.filter(pair => !Array.isArray(pair.wire_ids) || (!pair.wire_ids.includes(wireId) && !pair.wire_ids.includes(mateId)));
  if (kind === "none") return { ...document, pairs: pairs.filter(pair => !Array.isArray(pair.wire_ids) || !pair.wire_ids.includes(wireId)) };
  if (!pairCandidateWires(document, wireId).some(wire => wire.id === mateId)) throw new Error("Pair members must span the same connectors and cable assignment.");
  const pairId = id ?? (current && current.wire_ids?.includes(mateId) ? String(current.id) : nextHarnessId("PAIR", pairs.map(pair => String(pair.id))));
  const pair: HarnessRecord = current && current.wire_ids?.includes(mateId) ? { ...current } : { id: pairId };
  pair.id = pairId;
  pair.wire_ids = [wireId, mateId];
  pair.kind = kind;
  if (kind === "twisted") pair.twisted = true;
  else if (options.twisted) pair.twisted = true;
  else delete pair.twisted;
  if (pair.twisted && options.twistPitchMm !== undefined && Number.isFinite(options.twistPitchMm) && options.twistPitchMm > 0) pair.twist_pitch_mm = options.twistPitchMm;
  else delete pair.twist_pitch_mm;
  let wires = records(document.wires);
  if (kind === "differential") {
    const members = new Set([wireId, mateId]);
    wires = wires.map(wire => {
      const next: HarnessRecord = members.has(String(wire.id)) ? { ...wire, role: "signal" } : { ...wire };
      if (members.has(String(next.return_wire_id))) delete next.return_wire_id;
      return next;
    });
  }
  return { ...document, wires, pairs: [...withoutMembers, pair] };
}

export function updateHarnessPair(document: HarnessRecord, pairId: string, update: { twisted?: boolean; twistPitchMm?: number }): HarnessRecord {
  const pairs = records(document.pairs).map(pair => {
    if (pair.id !== pairId) return pair;
    const next = { ...pair };
    const twisted = pair.kind === "twisted" || Boolean(update.twisted);
    if (twisted) next.twisted = true; else delete next.twisted;
    if (twisted && update.twistPitchMm !== undefined && Number.isFinite(update.twistPitchMm) && update.twistPitchMm > 0) next.twist_pitch_mm = update.twistPitchMm;
    else delete next.twist_pitch_mm;
    return next;
  });
  return { ...document, pairs };
}

export function buildHarnessDiagram(document: HarnessRecord): HarnessDiagramProjection {
  const connectors = records(document.connectors);
  const splices = records(document.splices);
  const items = [
    ...connectors.map(item => ({ kind: "connector" as const, item })),
    ...splices.map(item => ({ kind: "splice" as const, item })),
  ];
  const width = 920;
  const columns = items.length > 4 ? 3 : 2;
  const nodeHeights = items.map(({ kind, item }) => kind === "connector" ? Math.max(76, 48 + records(item.pins).length * 25) : 58);
  const rowHeights: number[] = [];
  nodeHeights.forEach((height, index) => { const row = Math.floor(index / columns); rowHeights[row] = Math.max(rowHeights[row] ?? 0, height); });
  const rowTops: number[] = [];
  rowHeights.reduce((top, height, row) => { rowTops[row] = top; return top + height + 36; }, 28);
  const columnWidth = width / columns;
  const nodes: HarnessDiagramNode[] = items.map(({ kind, item }, index) => {
    const pins = kind === "connector" ? records(item.pins) : [];
    const height = nodeHeights[index];
    const column = index % columns;
    const row = Math.floor(index / columns);
    const y = rowTops[row];
    return {
      kind, id: String(item.id), label: kind === "connector" ? String(item.name || item.id) : `Splice ${String(item.id)}`,
      x: 38 + column * columnWidth, y, width: kind === "connector" ? Math.min(210, columnWidth - 76) : Math.min(130, columnWidth - 76), height,
      pins: pins.map((pin, pinIndex) => ({ id: String(pin.id), label: String(pin.name || pin.net || pin.id), y: y + 48 + pinIndex * 25 })),
    };
  });
  const nodeIndex = new Map(nodes.map(node => [`${node.kind}:${node.id}`, node]));
  const diagnostics: string[] = [];
  const duplicateCounts = new Map<string, number>();
  const wires = records(document.wires).map(wire => {
    const fromConnector = connectorId(wire.from), toConnector = connectorId(wire.to);
    const fromSplice = spliceId(wire.from), toSplice = spliceId(wire.to);
    const fromNode = nodeIndex.get(fromConnector ? `connector:${fromConnector}` : `splice:${fromSplice}`);
    const toNode = nodeIndex.get(toConnector ? `connector:${toConnector}` : `splice:${toSplice}`);
    const fromPin = fromNode?.kind === "splice" ? { id: "", label: "", y: fromNode.y + fromNode.height / 2 } : fromNode?.pins.find(pin => pin.id === pinId(wire.from));
    const toPin = toNode?.kind === "splice" ? { id: "", label: "", y: toNode.y + toNode.height / 2 } : toNode?.pins.find(pin => pin.id === pinId(wire.to));
    const unresolved = !fromNode || !toNode || !fromPin || !toPin;
    if (unresolved) diagnostics.push(`Wire ${String(wire.id)} has an endpoint that is not available in the connector pin or splice list.`);
    if (unresolved) return { id: String(wire.id), path: "", labelX: 0, labelY: 0, role: (wire.role ?? "unspecified") as HarnessWireRole, unresolved };
    const key = [fromConnector || `splice:${fromSplice}`, pinId(wire.from), toConnector || `splice:${toSplice}`, pinId(wire.to)].join("\u0000");
    const offset = (duplicateCounts.get(key) ?? 0) * 7;
    duplicateCounts.set(key, (duplicateCounts.get(key) ?? 0) + 1);
    const fromX = fromNode.x < toNode.x ? fromNode.x + fromNode.width : fromNode.x;
    const toX = fromNode.x < toNode.x ? toNode.x : toNode.x + toNode.width;
    const fromY = fromPin.y + offset, toY = toPin.y + offset;
    const bend = Math.max(52, Math.abs(toX - fromX) * .45);
    const direction = toX >= fromX ? 1 : -1;
    return {
      id: String(wire.id),
      path: `M ${fromX} ${fromY} C ${fromX + bend * direction} ${fromY}, ${toX - bend * direction} ${toY}, ${toX} ${toY}`,
      labelX: (fromX + toX) / 2, labelY: (fromY + toY) / 2 - 5 - offset,
      role: (wire.role ?? "unspecified") as HarnessWireRole, unresolved,
    };
  });
  const bottom = nodes.reduce((max, node) => Math.max(max, node.y + node.height), 170);
  return { width, height: Math.max(280, bottom + 30), nodes, wires, diagnostics };
}
