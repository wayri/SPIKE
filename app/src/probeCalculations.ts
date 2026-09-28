// SPDX-License-Identifier: Apache-2.0
export type ProbeDimension = "1" | "V" | "A" | "ohm" | "W" | "A/mm2";

export type ProbeQuantity = { value: number; unit: ProbeDimension };
export type ProbeFormulaRow = { id: string; name: string; formula: string };
export type ProbeCalculation = ProbeFormulaRow & { result?: ProbeQuantity; error?: string };
export type ProbeReferenceValues = Record<string, Record<string, ProbeQuantity | undefined>>;
export type ProbeResultRow = {
  probe: ProbeInput;
  sourceId: string; id: string; name: string; kind: string; net?: string; layer?: string;
  status: string; message?: string; values: Record<string, ProbeQuantity | undefined>;
};

export type ProbeInput = { id: string; name: string; probeKind?: string; net?: string; layer?: string };
export type SolvedProbeInput = {
  id: string; status?: string; message?: string; voltage_v?: number; voltage_drop_v?: number;
  peak_adjacent_current_a?: number; adjacent_power_loss_w?: number;
  peak_adjacent_current_density_a_mm2?: number; local_series_resistance_ohm?: number;
};

type Token = { kind: "number" | "name" | "op" | "eof"; text: string; value?: number };
type Node =
  | { kind: "number"; value: number }
  | { kind: "reference"; row: string; field: string }
  | { kind: "unary"; op: "+" | "-"; value: Node }
  | { kind: "binary"; op: "+" | "-" | "*" | "/"; left: Node; right: Node }
  | { kind: "call"; name: string; args: Node[] };

export class ProbeFormulaError extends Error {}

const tokenize = (source: string): Token[] => {
  const tokens: Token[] = [];
  let index = 0;
  while (index < source.length) {
    const rest = source.slice(index);
    const space = /^\s+/.exec(rest);
    if (space) { index += space[0].length; continue; }
    const number = /^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?/.exec(rest);
    if (number) {
      const value = Number(number[0]);
      if (!Number.isFinite(value)) throw new ProbeFormulaError("Number is outside the supported range");
      tokens.push({ kind: "number", text: number[0], value });
      index += number[0].length;
      continue;
    }
    const name = /^[A-Za-z_][A-Za-z0-9_]*/.exec(rest);
    if (name) { tokens.push({ kind: "name", text: name[0] }); index += name[0].length; continue; }
    if ("+-*/(),.".includes(source[index])) {
      tokens.push({ kind: "op", text: source[index++] });
      continue;
    }
    throw new ProbeFormulaError(`Unexpected character '${source[index]}'`);
  }
  return [...tokens, { kind: "eof", text: "" }];
};

class Parser {
  private index = 0;
  constructor(private readonly tokens: Token[]) {}
  private current() { return this.tokens[this.index]; }
  private take(text?: string) {
    const token = this.current();
    if (text !== undefined && token.text !== text) throw new ProbeFormulaError(`Expected '${text}'`);
    this.index += 1;
    return token;
  }
  parse(): Node {
    const result = this.sum();
    if (this.current().kind !== "eof") throw new ProbeFormulaError(`Unexpected '${this.current().text}'`);
    return result;
  }
  private sum(): Node {
    let node = this.product();
    while (["+", "-"].includes(this.current().text)) {
      const op = this.take().text as "+" | "-";
      node = { kind: "binary", op, left: node, right: this.product() };
    }
    return node;
  }
  private product(): Node {
    let node = this.unary();
    while (["*", "/"].includes(this.current().text)) {
      const op = this.take().text as "*" | "/";
      node = { kind: "binary", op, left: node, right: this.unary() };
    }
    return node;
  }
  private unary(): Node {
    if (["+", "-"].includes(this.current().text)) {
      const op = this.take().text as "+" | "-";
      return { kind: "unary", op, value: this.unary() };
    }
    return this.primary();
  }
  private primary(): Node {
    const token = this.current();
    if (token.kind === "number") { this.take(); return { kind: "number", value: token.value! }; }
    if (token.text === "(") { this.take(); const node = this.sum(); this.take(")"); return node; }
    if (token.kind !== "name") throw new ProbeFormulaError("Expected a number, reference, or function");
    const name = this.take().text;
    if (this.current().text === ".") {
      this.take(".");
      const field = this.take();
      if (field.kind !== "name") throw new ProbeFormulaError("Expected a field after '.'");
      return { kind: "reference", row: name, field: field.text };
    }
    if (this.current().text === "(") {
      this.take("(");
      const args: Node[] = [];
      if (this.current().text !== ")") {
        do { args.push(this.sum()); if (this.current().text !== ",") break; this.take(","); } while (true);
      }
      this.take(")");
      return { kind: "call", name, args };
    }
    throw new ProbeFormulaError(`Reference '${name}' needs a field, for example ${name}.voltage`);
  }
}

const multiplyUnit = (left: ProbeDimension, right: ProbeDimension): ProbeDimension => {
  if (left === "1") return right;
  if (right === "1") return left;
  if ((left === "V" && right === "A") || (left === "A" && right === "V")) return "W";
  throw new ProbeFormulaError(`Cannot multiply ${left} by ${right}`);
};

const divideUnit = (left: ProbeDimension, right: ProbeDimension): ProbeDimension => {
  if (right === "1") return left;
  if (left === right) return "1";
  if (left === "V" && right === "A") return "ohm";
  if (left === "W" && right === "A") return "V";
  if (left === "W" && right === "V") return "A";
  throw new ProbeFormulaError(`Cannot divide ${left} by ${right}`);
};

const calculate = (node: Node, resolve: (row: string, field: string) => ProbeQuantity): ProbeQuantity => {
  if (node.kind === "number") return { value: node.value, unit: "1" };
  if (node.kind === "reference") return resolve(node.row, node.field);
  if (node.kind === "unary") {
    const item = calculate(node.value, resolve);
    return { ...item, value: node.op === "-" ? -item.value : item.value };
  }
  if (node.kind === "call") {
    if (!["abs", "min", "max"].includes(node.name)) throw new ProbeFormulaError(`Unknown function '${node.name}'`);
    const args = node.args.map(arg => calculate(arg, resolve));
    if (node.name === "abs") {
      if (args.length !== 1) throw new ProbeFormulaError("abs expects one argument");
      return { value: Math.abs(args[0].value), unit: args[0].unit };
    }
    if (args.length < 1) throw new ProbeFormulaError(`${node.name} expects at least one argument`);
    if (args.some(arg => arg.unit !== args[0].unit)) throw new ProbeFormulaError(`${node.name} arguments must have matching units`);
    let value = args[0].value;
    for (let index = 1; index < args.length; index++) value = node.name === "min" ? Math.min(value, args[index].value) : Math.max(value, args[index].value);
    return { value, unit: args[0].unit };
  }
  const left = calculate(node.left, resolve);
  const right = calculate(node.right, resolve);
  if (node.op === "+" || node.op === "-") {
    if (left.unit !== right.unit) throw new ProbeFormulaError(`Cannot ${node.op === "+" ? "add" : "subtract"} ${left.unit} and ${right.unit}`);
    return { value: node.op === "+" ? left.value + right.value : left.value - right.value, unit: left.unit };
  }
  if (node.op === "/" && right.value === 0) throw new ProbeFormulaError("Division by zero");
  return { value: node.op === "*" ? left.value * right.value : left.value / right.value,
    unit: node.op === "*" ? multiplyUnit(left.unit, right.unit) : divideUnit(left.unit, right.unit) };
};

const quantity = (value: number | undefined, unit: ProbeDimension): ProbeQuantity | undefined =>
  value === undefined || !Number.isFinite(value) ? undefined : { value, unit };

export const defaultProbeReferenceId = (id: string) => {
  if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(id)) return id;
  let hash = 2166136261;
  for (let index = 0; index < id.length; index++) hash = Math.imul(hash ^ id.charCodeAt(index), 16777619);
  return `P_${(hash >>> 0).toString(36)}`;
};

/** Builds the one shared display/export/detached-window model from authoritative solver probes. */
export function buildProbeRows(
  probes: readonly ProbeInput[],
  result: { probes: readonly SolvedProbeInput[] } | null,
  referenceIds: Readonly<Record<string, string>> = {},
): ProbeResultRow[] {
  return probes.map(probe => {
    const solved = result?.probes.find(item => item.id === probe.id || probe.id.endsWith(item.id));
    const mapped = solved?.status === "mapped";
    return {
      probe,
      sourceId: probe.id,
      id: referenceIds[probe.id] ?? defaultProbeReferenceId(probe.id),
      name: probe.name,
      kind: probe.probeKind ?? "universal",
      net: probe.net,
      layer: probe.layer,
      status: solved?.status ?? "not run",
      message: solved?.message,
      values: {
        voltage: mapped ? quantity(solved.voltage_v, "V") : undefined,
        drop: mapped ? quantity(solved.voltage_drop_v, "V") : undefined,
        current: mapped ? quantity(solved.peak_adjacent_current_a, "A") : undefined,
        power: mapped ? quantity(solved.adjacent_power_loss_w, "W") : undefined,
        density: mapped ? quantity(solved.peak_adjacent_current_density_a_mm2, "A/mm2") : undefined,
        impedance: mapped ? quantity(solved.local_series_resistance_ohm, "ohm") : undefined,
      },
    };
  });
}

export function evaluateProbeFormulas(rows: readonly ProbeFormulaRow[], probeValues: ProbeReferenceValues): ProbeCalculation[] {
  const duplicateIds = new Set<string>();
  const seen = new Set<string>();
  for (const row of rows) { if (seen.has(row.id)) duplicateIds.add(row.id); seen.add(row.id); }
  const byId = new Map(rows.map(row => [row.id, row]));
  const cache = new Map<string, ProbeQuantity>();
  const active = new Set<string>();
  const evaluateRow = (id: string): ProbeQuantity => {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(id)) throw new ProbeFormulaError(`Invalid calculated row identifier '${id}'`);
    if (duplicateIds.has(id)) throw new ProbeFormulaError(`Duplicate calculated row identifier '${id}'`);
    if (Object.prototype.hasOwnProperty.call(probeValues, id)) throw new ProbeFormulaError(`Calculated row identifier '${id}' conflicts with a probe identifier`);
    const cached = cache.get(id); if (cached) return cached;
    const row = byId.get(id); if (!row) throw new ProbeFormulaError(`Unknown row '${id}'`);
    if (active.has(id)) throw new ProbeFormulaError(`Cyclic reference involving '${id}'`);
    active.add(id);
    try {
      if (!row.formula.trim()) throw new ProbeFormulaError("Formula is empty");
      const tree = new Parser(tokenize(row.formula)).parse();
      const result = calculate(tree, (reference, field) => {
        if (byId.has(reference)) {
          if (field !== "value") throw new ProbeFormulaError(`Calculated row '${reference}' only exposes .value`);
          return evaluateRow(reference);
        }
        const probe = probeValues[reference];
        if (!probe) throw new ProbeFormulaError(`Unknown probe '${reference}'`);
        const quantity = probe[field];
        if (!quantity) throw new ProbeFormulaError(`Probe '${reference}' has no mapped '${field}' value`);
        return quantity;
      });
      if (!Number.isFinite(result.value)) throw new ProbeFormulaError("Result is outside the supported range");
      cache.set(id, result);
      return result;
    } finally { active.delete(id); }
  };
  return rows.map(row => {
    try { return { ...row, result: evaluateRow(row.id) }; }
    catch (error) { return { ...row, error: error instanceof Error ? error.message : "Invalid formula" }; }
  });
}

export function probeResultsCsv(
  probes: readonly { id: string; name: string; kind: string; net?: string; layer?: string; status: string; values: Record<string, ProbeQuantity | undefined> }[],
  formulas: readonly ProbeCalculation[],
) {
  const quote = (value: unknown) => `"${String(value ?? "").replace(/"/g, '""')}"`;
  const columns = ["row_type", "id", "name", "kind", "net", "layer", "status", "voltage_v", "voltage_drop_v", "current_a", "power_w", "density_a_mm2", "impedance_ohm", "formula", "value", "unit", "error"];
  const lines = probes.map(probe => ["probe", probe.id, probe.name, probe.kind, probe.net, probe.layer, probe.status,
    probe.values.voltage?.value, probe.values.drop?.value, probe.values.current?.value, probe.values.power?.value,
    probe.values.density?.value, probe.values.impedance?.value, "", "", "", ""]);
  lines.push(...formulas.map(row => ["formula", row.id, row.name, "calculated", "", "", row.error ? "error" : "calculated",
    "", "", "", "", "", "", row.formula, row.result?.value, row.result?.unit, row.error]));
  return [columns, ...lines].map(line => line.map(quote).join(",")).join("\r\n");
}
