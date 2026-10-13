// SPDX-License-Identifier: Apache-2.0
export const ASSEMBLY_CONDUCTORS_KEY = "spike.harness-conductors";
export const ASSEMBLY_CONDUCTORS_CONTRACT = "spike/assembly-harness-conductors/v1";
export type AssemblyHarnessRow = Record<string, any> & { id: string; endpoint_a: string; endpoint_b: string; pin_map: Record<string, string> };
const object = (value: unknown): value is Record<string, any> => Boolean(value && typeof value === "object" && !Array.isArray(value));
const wireKeys = ["id", "role", "return_wire_id", "length_mm", "area_mm2", "net", "color", "part_number", "material", "electrical", "properties", "extensions"];
const binding = (id: string) => {
  const split = id.indexOf("::");
  return split > 0 && split < id.length - 2 ? { board_id: id.slice(0, split), connector_id: id.slice(split + 2) } : undefined;
};

/** A presentation bridge over saved explicit pin mappings, never net-name inference. */
export function assemblyHarnessDocument(row: AssemblyHarnessRow): Record<string, any> {
  if (!row.endpoint_a || !row.endpoint_b || row.endpoint_a === row.endpoint_b) throw new Error("Choose two distinct board::connector endpoints first.");
  if (!object(row.pin_map)) throw new Error("Apply a valid connector pin map first.");
  const pins = Object.entries(row.pin_map);
  if (!pins.length || pins.length > 512 || pins.some(([a, b]) => !a || typeof b !== "string" || !b)
    || new Set(pins.map(([, b]) => b)).size !== pins.length) throw new Error("Apply 1–512 unique explicit pin pairs first.");
  const saved = row.extensions?.[ASSEMBLY_CONDUCTORS_KEY];
  if (saved !== undefined && (!object(saved) || saved.contract !== ASSEMBLY_CONDUCTORS_CONTRACT || !Array.isArray(saved.wires))) throw new Error("Saved conductor metadata is incompatible; review its contract before editing.");
  const previous = saved?.wires ?? [];
  if (saved !== undefined && (previous.length !== pins.length
    || new Set(previous.map((wire: any) => wire?.from_pin)).size !== pins.length
    || previous.some((wire: any) => !object(wire) || !Object.prototype.hasOwnProperty.call(row.pin_map, wire.from_pin) || row.pin_map[wire.from_pin] !== wire.to_pin))) {
    throw new Error("Saved conductors no longer match the pin map. Restore the map or explicitly clear conductor metadata.");
  }
  const route = row.extensions?.["spike.harness-routing"]?.route_mm;
  const routes = Array.isArray(route) && route.length >= 2 ? [{ id: `${row.id}:route`, frame_id: "assembly", points_mm: structuredClone(route) }] : [];
  const wires = pins.map(([from, to]) => {
    const prior = previous.find((wire: any) => wire.from_pin === from && wire.to_pin === to);
    const retained = Object.fromEntries(wireKeys.filter(key => prior?.[key] !== undefined).map(key => [key, structuredClone(prior[key])]));
    return { id: `${row.id}:wire:${encodeURIComponent(from)}`, ...(row.length_mm > 0 ? { length_mm: row.length_mm } : {}), ...retained,
      from: { connector: row.endpoint_a, pin: from }, to: { connector: row.endpoint_b, pin: to },
      ...(routes.length ? { route_id: routes[0].id } : {}) };
  });
  if (new Set(wires.map(wire => wire.id)).size !== wires.length) throw new Error("Saved conductor IDs must be unique.");
  return { contract: "spike/harness/v1", id: row.id, name: row.name || row.id,
    connectors: [row.endpoint_a, row.endpoint_b].map((id, index) => {
      const prior = saved?.connectors?.find((connector: any) => connector.id === id);
      return { ...(object(prior) ? structuredClone(prior) : {}), id, ...(binding(id) ? { board_binding: binding(id) } : {}),
        pins: pins.map(pair => ({ ...structuredClone(prior?.pins?.find((pin: any) => pin.id === pair[index]) ?? {}), id: pair[index] })) };
    }), wires, routes,
    cables: structuredClone(saved?.cables ?? [{ id: `${row.id}:bundle`, wire_ids: wires.map(wire => wire.id) }]), pairs: structuredClone(saved?.pairs ?? []),
    extensions: structuredClone(saved?.analysis_extensions ?? {}) };
}

export function retainAssemblyHarnessDocument(row: AssemblyHarnessRow, document: Record<string, any>): AssemblyHarnessRow {
  const initial = assemblyHarnessDocument(row);
  if (JSON.stringify(document.routes ?? []) !== JSON.stringify(initial.routes)) throw new Error("Edit physical routes with the assembly route planner; wiring edits retain the saved assembly route.");
  if (document.id !== row.id || document.connectors?.length !== 2
    || document.connectors.some((connector: any, index: number) => connector.id !== initial.connectors[index].id
      || JSON.stringify(connector.pins?.map((pin: any) => pin.id).sort()) !== JSON.stringify(initial.connectors[index].pins.map((pin: any) => pin.id).sort()))) {
    throw new Error("Edit assembly endpoints and pins in the saved pin-map table; the wiring editor retains those identities.");
  }
  if (!Array.isArray(document.wires) || document.wires.length !== initial.wires.length || document.wires.some((wire: any) =>
    wire.from?.connector !== row.endpoint_a || wire.to?.connector !== row.endpoint_b || row.pin_map[wire.from?.pin] !== wire.to?.pin)) {
    throw new Error("Edit connections in the assembly pin-map table before changing conductor endpoints or count.");
  }
  if (new Set(document.wires.map((wire: any) => wire.from.pin)).size !== document.wires.length) throw new Error("Each saved pin pair needs exactly one conductor.");
  const wires = document.wires.map((wire: any) => ({ from_pin: wire.from.pin, to_pin: wire.to.pin,
    ...Object.fromEntries(wireKeys.filter(key => wire[key] !== undefined).map(key => [key, structuredClone(wire[key])])) }));
  return { ...row, name: document.name, extensions: { ...(row.extensions ?? {}), [ASSEMBLY_CONDUCTORS_KEY]: {
    contract: ASSEMBLY_CONDUCTORS_CONTRACT, wires, pairs: structuredClone(document.pairs ?? []),
    connectors: structuredClone(document.connectors), cables: structuredClone(document.cables ?? []),
    analysis_extensions: structuredClone(document.extensions ?? {}) } } };
}
