// SPDX-License-Identifier: Apache-2.0
/** Shape guards keep imported/draft JSON safe to render; physics stays in Python. */
type Row = Record<string, any>;
function object(value: any): value is Row { return value !== null && typeof value === "object" && !Array.isArray(value); }
function owner(value: Row): boolean { return (typeof value.board_id === "string") !== (typeof value.part_id === "string"); }
export function studyDraft(value: any, domain: string): Row {
  if (!object(value)) throw new Error("Study model must be an object.");
  const expected = domain === "thermal" ? "spike/multiboard-thermal-request/v1" : domain === "emi" ? "spike/multiboard-em-request/v1" : "spike/multiboard-circuit-request/v1";
  if (value.contract !== expected) throw new Error("Study contract does not match the selected domain.");
  const rows = (key: string, limit: number) => {
    if (!Array.isArray(value[key]) || value[key].length > limit || !value[key].every(object)) throw new Error(`Invalid ${key} table.`);
  };
  if (domain === "emi") {
    rows("loops", 128); rows("mutual_inductances", 8128); rows("connector_models", 4096);
    if (!value.loops.every((loop: Row) => typeof loop.loop_id === "string" && owner(loop))
      || !value.mutual_inductances.every((pair: Row) => typeof pair.loop_a === "string" && typeof pair.loop_b === "string")
      || !value.connector_models.every((contact: Row) => ["loop_id", "board_id", "connector_id", "pin"].every(key => typeof contact[key] === "string"))) throw new Error("Invalid magnetic loop or contact identity.");
    if (!Array.isArray(value.frequency_hz) || value.frequency_hz.length > 4096) throw new Error("Invalid frequency table.");
  } else {
    rows("board_models", 30);
    if (!value.board_models.every((board: Row) => typeof board.board_id === "string" && Array.isArray(board.elements) && board.elements.length <= 4096 && board.elements.every(object))) throw new Error("Invalid board model table.");
    if (value.part_models !== undefined) {
      rows("part_models", 5000);
      if (!value.part_models.every((part: Row) => typeof part.part_id === "string" && Array.isArray(part.elements) && part.elements.length <= 4096 && part.elements.every(object))) throw new Error("Invalid mechanical part model table.");
    }
    if (domain === "thermal") {
      rows("contact_models", 5000);
      if (!value.contact_models.every((contact: Row) => object(contact.from) && object(contact.to) && typeof contact.contact_id === "string" && owner(contact.from) && owner(contact.to))) throw new Error("Invalid thermal contact endpoints.");
    } else {
      if (value.domain !== domain || !object(value.ground) || !object(value.analysis)) throw new Error("Circuit requires its domain, ground and analysis records.");
      rows("link_models", 4096);
      if (!value.link_models.every((link: Row) => typeof link.link_id === "string" && typeof link.kind === "string" && Array.isArray(link.pins) && link.pins.length <= 512 && link.pins.every((pin: Row) => object(pin) && typeof pin.source_pin === "string" && typeof pin.target_pin === "string"))) throw new Error("Invalid connector pin property table.");
      if (!value.board_models.every((board: Row) => board.elements.every((element: Row) => typeof element.type === "string"))) throw new Error("Each circuit element requires a type.");
      if (value.part_models && !value.part_models.every((part: Row) => part.elements.every((element: Row) => typeof element.type === "string"))) throw new Error("Each mechanical circuit element requires a type.");
      if (!owner(value.ground)) throw new Error("Choose one ground board or mechanical part.");
      if (value.electrical_bond_models !== undefined) {
        rows("electrical_bond_models", 5000);
        if (!value.electrical_bond_models.every((bond: Row) => typeof bond.bond_id === "string" && object(bond.endpoint_a) && object(bond.endpoint_b) && owner(bond.endpoint_a) && owner(bond.endpoint_b))) throw new Error("Invalid electrical bond endpoints.");
      }
    }
  }
  const copy = structuredClone(value); delete copy.assembly;
  return copy;
}

export function studyResultRows(result: Row, domain: string, point = 0): Array<{ board: string; owner_kind?: "part"; node: string; value: unknown; unit: string }> {
  if (result.status && result.status !== "completed") return [];
  if (domain === "thermal") return Object.entries(result.board_temperatures_c ?? {}).flatMap(([board, nodes]) => Object.entries(nodes as Row).map(([node, value]) => ({ board, node, value, unit: "°C" }))).concat(Object.entries(result.part_temperatures_c ?? {}).flatMap(([board, nodes]) => Object.entries(nodes as Row).map(([node, value]) => ({ board, owner_kind: "part" as const, node, value, unit: "°C" }))));
  if (domain === "emi") return (result.samples?.[point]?.loops ?? []).map((loop: Row) => ({ board: loop.board_id ?? loop.part_id, ...(loop.part_id ? { owner_kind: "part" as const } : {}), node: loop.loop_id, value: loop.current_magnitude_a, unit: "A RMS" }));
  const values = result.native_result?.data?.node_voltage_v ?? {};
  return [{ table: result.node_map ?? {}, part: false }, { table: result.part_node_map ?? {}, part: true }].flatMap(({table, part}) => Object.entries(table).flatMap(([board, nodes]) => Object.entries(nodes as Row).map(([node, key]) => {
    const value = values[key] ?? (key === result.ground_node ? 0 : undefined);
    return { board, ...(part ? { owner_kind: "part" as const } : {}), node, value: typeof value === "number" ? value : value?.magnitude?.[point], unit: result.analysis?.mode === "ac" ? "V magnitude" : "V" };
  })));
}

/** Read returned element quantities; never infer currents or power from artwork. */
export function studyElementResultRows(result: Row, point = 0): Array<{ board: string; owner_kind?: "part"; element: string; quantity: string; value: number; unit: string }> {
  if (result.status !== "completed") return [];
  const data = result.native_result?.data ?? {};
  const ac = result.analysis?.mode === "ac";
  const quantities = ac ? [
    ["element_current_a", "real", "Current, real", "A RMS"],
    ["element_current_a", "imaginary", "Current, imaginary", "A RMS"],
    ["element_complex_power_va", "real", "Active power", "W"],
    ["element_complex_power_va", "imaginary", "Reactive power", "var"],
  ] : [["element_current_a", "", "Current", "A"], ["element_power_w", "", "Power", "W"]];
  return [{ table: result.element_map ?? {}, part: false }, { table: result.part_element_map ?? {}, part: true }].flatMap(({ table, part }) =>
    Object.entries(table).flatMap(([board, elements]) => Object.entries(elements as Row).flatMap(([element, key]) =>
      quantities.flatMap(([field, component, quantity, unit]) => {
        const returned = data[field]?.[key];
        const value = ac ? returned?.[component]?.[point] : returned;
        return typeof value === "number" && Number.isFinite(value)
          ? [{ board, ...(part ? { owner_kind: "part" as const } : {}), element, quantity, value, unit }] : [];
      }))));
}

export function studyResultSummary(result: Row): Row {
  const sample = result.samples?.[0];
  return { contract: result.contract, status: result.status, model_status: result.model_status,
    summary: result.summary, limitations: result.limitations, issues: result.issues,
    provenance: result.provenance, native_diagnostics: result.native_result?.diagnostics,
    dc_link_losses: result.analysis?.mode === "operating_point" ? result.links : undefined,
    em_first_sample_balance: sample ? { source_real_power_w: sample.source_real_power_w,
      total_loss_w: sample.total_loss_w, power_balance_residual_w: sample.power_balance_residual_w,
      relative_linear_residual: sample.relative_linear_residual, condition_number: sample.condition_number } : undefined,
    minimum_normalized_energy_eigenvalue: result.minimum_normalized_energy_eigenvalue,
    contact_heat_flows: result.contact_heat_flows, electrical_bond_losses: result.electrical_bonds };
}
