import type { ParsedBoard } from "./boardParser";

export type ThermalImportField = "reference" | "power_w" | "theta_top_c_per_w" | "theta_bottom_c_per_w";
export type ThermalImportMapping = Record<ThermalImportField, string>;
export type ThermalImportRow = { reference: string; power_w: number; theta_top_c_per_w: number; theta_bottom_c_per_w: number };
export type ThermalImportResult = { rows: ThermalImportRow[]; issues: string[] };

const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, "");
const aliases: Record<ThermalImportField, string[]> = {
  reference: ["reference", "references", "ref", "refdes", "designator", "designators", "componentreference"],
  power_w: ["powerw", "powermw", "powerwatts", "dissipationw", "dissipationmw", "dissipationwatts", "powerdissipationw", "heatw"],
  theta_top_c_per_w: ["rthtop", "rthtopkw", "rthtopcw", "thetatop", "thetatopkw", "thetatopcw", "thermalresistancetop", "thermalresistancetopkw", "thermalresistancetopcw"],
  theta_bottom_c_per_w: ["rthbottom", "rthbottomkw", "rthbottomcw", "thetabottom", "thetabottomkw", "thetabottomcw", "thermalresistancebottom", "thermalresistancebottomkw", "thermalresistancebottomcw"],
};

function splitDelimitedLine(line: string, separator: string): string[] {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < line.length; index++) {
    const char = line[index];
    if (char === '"') {
      if (quoted && line[index + 1] === '"') { cell += '"'; index++; }
      else quoted = !quoted;
    } else if (char === separator && !quoted) { cells.push(cell.trim()); cell = ""; }
    else cell += char;
  }
  if (quoted) throw new Error("BOM contains an unterminated quoted cell. Keep each record on one line.");
  cells.push(cell.trim());
  return cells;
}

export function parseThermalDelimited(text: string): { headers: string[]; records: Record<string, string>[] } {
  if (text.length > 5_000_000) throw new Error("BOM file exceeds the 5 MB import limit.");
  const lines = text.replace(/^\uFEFF/, "").split(/\r\n|\n|\r/).filter(line => line.trim());
  if (lines.length < 2 || lines.length > 10_001) throw new Error("BOM needs a header and 1–10,000 data rows.");
  const separator = ["\t", ",", ";"].sort((a, b) => splitDelimitedLine(lines[0], b).length - splitDelimitedLine(lines[0], a).length)[0];
  const headers = splitDelimitedLine(lines[0], separator);
  if (headers.length < 4 || headers.some(header => !header)) throw new Error("BOM needs named reference, power, top Rth, and bottom Rth columns.");
  if (new Set(headers.map(normalize)).size !== headers.length) throw new Error("BOM column names must be unique.");
  const records = lines.slice(1).map((line, index) => {
    const values = splitDelimitedLine(line, separator);
    if (values.length !== headers.length) throw new Error(`BOM row ${index + 2} has ${values.length} cells; expected ${headers.length}.`);
    return Object.fromEntries(headers.map((header, column) => [header, values[column]]));
  });
  return { headers, records };
}

export function suggestThermalMapping(headers: string[]): ThermalImportMapping {
  const find = (field: ThermalImportField) => headers.find(header => aliases[field].includes(normalize(header))) ?? "";
  return { reference: find("reference"), power_w: find("power_w"), theta_top_c_per_w: find("theta_top_c_per_w"), theta_bottom_c_per_w: find("theta_bottom_c_per_w") };
}

function numberWithUnit(raw: string, field: Exclude<ThermalImportField, "reference">, header: string): number | null {
  const value = raw.trim();
  const match = /^([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\s*(mW|W|K\/W|C\/W|°C\/W)?$/i.exec(value);
  if (!match) return null;
  const number = Number(match[1]);
  if (!Number.isFinite(number) || number < 0) return null;
  const unit = (match[2] ?? "").toLowerCase();
  if (field === "power_w") {
    if (unit && unit !== "w" && unit !== "mw") return null;
    // Explicit cell units take precedence over the column's default unit.
    return unit === "mw" || (!unit && normalize(header).endsWith("mw")) ? number / 1000 : number;
  }
  if (unit && !["k/w", "c/w", "°c/w"].includes(unit)) return null;
  return number > 0 ? number : null;
}

function references(raw: string): string[] {
  return raw.split(/[\s,;]+/).map(value => value.trim()).filter(Boolean);
}

export function mapThermalRecords(records: Record<string, string>[], mapping: ThermalImportMapping, board: ParsedBoard | null): ThermalImportResult {
  const issues: string[] = [];
  if (Object.values(mapping).some(value => !value) || new Set(Object.values(mapping)).size !== 4) return { rows: [], issues: ["Choose four different BOM columns before applying values."] };
  const known = new Set(board?.components.map(component => component.ref.toUpperCase()) ?? []);
  const used = new Set<string>();
  const rows: ThermalImportRow[] = [];
  records.forEach((record, index) => {
    const power = numberWithUnit(record[mapping.power_w] ?? "", "power_w", mapping.power_w);
    const top = numberWithUnit(record[mapping.theta_top_c_per_w] ?? "", "theta_top_c_per_w", mapping.theta_top_c_per_w);
    const bottom = numberWithUnit(record[mapping.theta_bottom_c_per_w] ?? "", "theta_bottom_c_per_w", mapping.theta_bottom_c_per_w);
    const refs = references(record[mapping.reference] ?? "");
    if (!refs.length || power === null || top === null || bottom === null) { issues.push(`Row ${index + 2}: reference, nonnegative W, and positive top/bottom K/W are required.`); return; }
    refs.forEach(reference => {
      const key = reference.toUpperCase();
      if (!known.has(key)) { issues.push(`Row ${index + 2}: ${reference} is not on the loaded board.`); return; }
      if (used.has(key)) { issues.push(`Row ${index + 2}: duplicate assignment for ${reference}.`); return; }
      used.add(key);
      rows.push({ reference, power_w: power, theta_top_c_per_w: top, theta_bottom_c_per_w: bottom });
    });
  });
  return { rows, issues };
}

export function thermalRowsFromOdb(board: ParsedBoard | null): ThermalImportResult {
  if (!board) return { rows: [], issues: ["Load an ODB++ board first."] };
  const records: Record<string, string>[] = board.components.map(component => {
    const values: Record<string, string> = { Reference: component.ref };
    const assign = (name: string, value: string) => {
      const key = normalize(name);
      if (aliases.power_w.includes(key)) values["Power W"] = key.endsWith("mw") && !/[a-z°]/i.test(value.replace(/e[+-]?\d+/gi, "")) ? `${value} mW` : value;
      else if (aliases.theta_top_c_per_w.includes(key)) values["Rth top K/W"] = value;
      else if (aliases.theta_bottom_c_per_w.includes(key)) values["Rth bottom K/W"] = value;
    };
    for (const property of component.properties ?? []) {
      if (typeof property.name === "string" && Array.isArray(property.values) && property.values.length === 1) assign(property.name, String(property.values[0]));
    }
    for (const [name, value] of Object.entries(component.vendor_properties ?? {})) {
      if (typeof value === "string" || typeof value === "number") assign(name, String(value));
    }
    return values;
  });
  const headers = Array.from(new Set(records.flatMap(record => Object.keys(record))));
  const mapping = suggestThermalMapping(headers);
  if (Object.values(mapping).some(value => !value)) return { rows: [], issues: ["ODB++ component properties do not contain named power W, top Rth K/W, and bottom Rth K/W values. Import a BOM or enter them in the GUI."] };
  return mapThermalRecords(records.filter(record => Object.values(mapping).slice(1).some(key => record[key])), mapping, board);
}
