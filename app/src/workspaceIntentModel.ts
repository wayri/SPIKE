// SPDX-License-Identifier: Apache-2.0
/** Inert presentation drafts only. Existing setup and worker admission own execution. */
export type WorkspaceWorkflowKey = "si" | "thermal" | "electrothermal" | "assemblyCHT" | "referenceCHT" | "coupling" | "cfd" | "em" | "rf" | "import" | "assembly" | "mesh" | "results" | "studies" | "model-assignment" | "export";
export type WorkspaceIntentScope = "board" | "component" | "net" | "assembly" | "workspace" | "selection";
export type WorkspaceIntentEntity = { id: string; name: string; occurrenceId?: string };
export type WorkspaceIntentContext = {
  version: string;
  nets?: readonly WorkspaceIntentEntity[];
  components?: readonly WorkspaceIntentEntity[];
  occurrences?: readonly WorkspaceIntentEntity[];
  selectedNetIds?: readonly string[];
  selectedComponentIds?: readonly string[];
  selectedOccurrenceIds?: readonly string[];
};
export type WorkspaceIntentAmbiguity = { field: "netIds" | "componentIds" | "occurrenceIds"; input: string; candidates: WorkspaceIntentEntity[] };
export type WorkspaceIntentField = { key: string; label: string; unit: string; required: boolean; minimum?: number; exclusiveMinimum?: boolean };
export type WorkspaceIntentSchema = { workflowKey: WorkspaceWorkflowKey; domain: string; label: string; scopes: readonly WorkspaceIntentScope[]; fields: readonly WorkspaceIntentField[]; requiredBinding?: "netIds" | "componentIds" | "occurrenceIds"; limitation: string };
export type WorkspaceIntentDraft = {
  workflowKey: WorkspaceWorkflowKey;
  domain: string;
  scope: WorkspaceIntentScope;
  assemblyOperation?: "open" | "connect" | "move" | "rotate" | "place";
  contextVersion: string;
  suppliedText: string;
  bindings: { netIds: string[]; componentIds: string[]; occurrenceIds: string[] };
  roles?: { signalNetId?: string; referenceNetId?: string; sourceComponentId?: string; sinkComponentIds?: string[] };
  parameters: Record<string, number>;
  missing: string[];
  ambiguities: WorkspaceIntentAmbiguity[];
  issues: string[];
  availability: "review" | "unsupported";
  limitation: string;
};
export type WorkspaceIntentSuggestion = { id: string; label: string; completion: string; draft: WorkspaceIntentDraft };
export type WorkspaceIntentChoices={primaryNetId:string;referenceNetId:string;rfMode:"geometry"|"network";importKind:"kicad"|"normalized"|"odb++"|"ipc2581"|"harness"|"mcad"|"gerber"|"touchstone";assemblyAction:"workspace"|"placement"|"links";couplingMode:""|"electrothermal"|"field-circuit";exportKind:"report"|"results"|"step"|"touchstone"|"netlist";meshRoute:"board"|"volume";componentPowersW:Record<string,number>};
export type WorkspaceReviewedIntent={draft:WorkspaceIntentDraft;choices:WorkspaceIntentChoices};

const field = (key: string, label: string, unit: string, required = false, minimum = 0, exclusiveMinimum = true): WorkspaceIntentField => ({ key, label, unit, required, minimum, exclusiveMinimum });
const frequencyFields = [field("frequencyStartHz", "Start frequency", "Hz", true, 0, false), field("frequencyStopHz", "Stop frequency", "Hz", true)];
/** Setup field descriptions, not a second solver contract or availability registry. */
export const WORKSPACE_INTENT_SCHEMAS: readonly WorkspaceIntentSchema[] = [
  { workflowKey: "si", domain: "Signal integrity", label: "Review signal integrity setup", scopes: ["net", "board", "selection"], requiredBinding: "netIds", fields: [...frequencyFields, field("riseTimeS", "Rise time", "s"), field("impedanceOhm", "Reference impedance", "ohm")], limitation: "Bounded approximate channel models; the geometry-derived SI route requires a DC start of 0 Hz. Review reference, ports and model eligibility in SI setup." },
  { workflowKey: "thermal", domain: "Thermal", label: "Review thermal setup", scopes: ["component", "board", "assembly", "selection"], fields: [field("powerW", "Total supplied heat", "W", true, 0, false), field("ambientC", "Ambient temperature", "C", true, -273.15), field("durationS", "Duration", "s")], limitation: "Review heat allocation, material, cooling and mesh assumptions. Component markers are not a spatial temperature field." },
  { workflowKey: "electrothermal", domain: "Coupled electrothermal", label: "Review electrothermal setup", scopes: ["board", "component", "assembly", "selection"], fields: [field("ambientC", "Ambient temperature", "C", true, -273.15), field("durationS", "Duration", "s")], limitation: "Explicit mapped circuit losses and thermal feedback only; supply circuit, loss bindings and admitted thermal geometry in setup." },
  { workflowKey: "coupling", domain: "Coupling", label: "Review hybrid coupling choice", scopes: ["board", "component", "assembly", "workspace", "selection"], fields: [field("ambientC", "Ambient temperature", "C", false, -273.15), field("durationS", "Duration", "s")], limitation: "Choose the intended electrical/thermal/field coupling and supply explicit models; hybrid alone does not identify physics." },
  { workflowKey: "referenceCHT", domain: "CHT reference", label: "Review fixed CHT reference", scopes: ["workspace"], fields: [], limitation: "Explicit SU2 hot-solid/fluid/cold-solid cavity reference only; not workspace geometry, general assembly CHT or qualification." },
  { workflowKey: "assemblyCHT", domain: "CHT", label: "Review requested assembly CHT", scopes: ["assembly", "board", "component", "selection"], fields: [], limitation: "General board/assembly CHT is unsupported. SU2's fixed hot-solid/fluid/cold-solid reference does not accept arbitrary workspace geometry; no reference case is substituted." },
  { workflowKey: "cfd", domain: "CFD", label: "Review CFD scope", scopes: ["assembly", "board", "workspace", "selection"], fields: [], limitation: "Native CFD is an isothermal 2D square-cavity reference. General assembly airflow and CAD support are unavailable." },
  { workflowKey: "em", domain: "Electromagnetics", label: "Review electromagnetic setup", scopes: ["board", "net", "assembly", "selection"], fields: frequencyFields, limitation: "External runtime, reviewed geometry, materials, ports and capability admission are required; arbitrary full-wave qualification is unavailable." },
  { workflowKey: "rf", domain: "RF networks", label: "Review RF network setup", scopes: ["net", "board", "assembly", "selection"], requiredBinding: "netIds", fields: [...frequencyFields, field("impedanceOhm", "Reference impedance", "ohm")], limitation: "Review geometry/network source and explicit ports. Sampled S-parameter processing does not validate extraction." },
  { workflowKey: "import", domain: "Import", label: "Review import source", scopes: ["workspace"], fields: [], limitation: "Choose a source file and review importer quality and unsupported objects." },
  { workflowKey: "assembly", domain: "Assembly", label: "Review assembly setup", scopes: ["assembly", "selection"], fields: [], limitation: "Review occurrences and placement in assembly setup; connections require explicit connector/pin mappings. Placement does not establish electrical or thermal connections." },
  { workflowKey: "mesh", domain: "Mesh", label: "Review mesh setup", scopes: ["board", "assembly", "component", "selection"], fields: [field("meshSizeM", "Mesh size", "m")], limitation: "Select geometry, materials and mesh route; mesh admission and quality remain separate checks." },
  { workflowKey: "results", domain: "Results", label: "Review retained results", scopes: ["workspace", "board", "assembly", "selection"], fields: [], limitation: "Choose a retained result and preserve its provenance and status." },
  { workflowKey: "studies", domain: "Studies", label: "Review study setup", scopes: ["workspace", "board", "assembly", "selection"], fields: [], limitation: "Choose the study, explicit variables, ranges and admitted analysis before execution." },
  { workflowKey: "model-assignment", domain: "Models", label: "Review model assignment", scopes: ["component", "selection", "workspace"], requiredBinding: "componentIds", fields: [], limitation: "Choose the exact model and review pin, material or geometry mapping before assignment." },
  { workflowKey: "export", domain: "Export", label: "Review export", scopes: ["workspace", "board", "assembly", "selection"], fields: [], limitation: "Choose the artifact, format and destination before export." },
];
export const workspaceIntentSchemas = WORKSPACE_INTENT_SCHEMAS;
const fold = (value: string) => value.toLowerCase();
const unquote = (value: string) => value.replace(/^(["'])(.*)\1$/, "$2");
function near(a: string, b: string): boolean {
  if (a === b) return true;
  if (a.length > 32 || Math.abs(a.length - b.length) > 1) return false;
  if (a.length === b.length) {
    const mismatches = [...a].map((value, index) => value === b[index] ? -1 : index).filter(index => index >= 0);
    if (mismatches.length === 2 && mismatches[1] === mismatches[0] + 1 && a[mismatches[0]] === b[mismatches[1]] && a[mismatches[1]] === b[mismatches[0]]) return true;
  }
  let i = 0, j = 0, edits = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; continue; }
    if (++edits > 1) return false;
    if (a.length >= b.length) i++;
    if (b.length >= a.length) j++;
  }
  return edits + Number(i < a.length || j < b.length) <= 1;
}
function detect(text: string): WorkspaceWorkflowKey | undefined {
  const words = fold(text).replace(/[-_]/g, " ").split(/\s+/);
  const has = (...terms: string[]) => terms.some(term => words.some(word => word === term || (term.length >= 6 && near(word, term))));
  if (has("import", "load") && /\b(step|stp|board|kicad|odb|ipc|gerber|file|cad|touchstone|snp|s\d+p)\b/i.test(text)) return "import";
  if (has("open", "move", "rotate", "place") && has("board", "boards", "assembly", "occurrence", "occurrences")) return "assembly";
  if (has("assign", "map") && has("model", "material", "models")) return "model-assignment";
  if (has("export", "save") && has("export", "report", "csv", "touchstone", "step", "results")) return "export";
  if (/\b(cht|conjugate\s+heat\s+transfer)\b/i.test(text)) return /\b(reference|benchmark|cavity)\b/i.test(text) ? "referenceCHT" : "assemblyCHT";
  if (/\bhybrid\b/i.test(text)) return "coupling";
  if (/\b(electrothermal|electro thermal)\b/i.test(text) || /\bcoupled\b/i.test(text) && /\b(electrical|thermal)\b/i.test(text)) return "electrothermal";
  if (has("thermal", "temperature", "cool", "cooling", "heat")) return "thermal";
  if (has("cfd", "airflow", "fluid")) return "cfd";
  if (has("rf") || /\bs\s*[- ]?parameters?\b/i.test(text)) return "rf";
  if (has("si", "crosstalk", "impedance", "eye") || (has("signal") && has("integrity"))) return "si";
  if (has("em", "emi", "electromagnetic", "antenna", "radiation")) return "em";
  if (has("mesh", "meshing")) return "mesh";
  if (has("results", "result", "plot", "waveforms")) return "results";
  if (has("study", "studies", "sweep", "optimization")) return "studies";
  if (has("connect", "assemble", "assembly", "harness", "mate")) return "assembly";
  return undefined;
}
const valuePattern = "[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:e[+-]?\\d+)?";
const prefixes: Record<string, number> = { "": 1, p: 1e-12, n: 1e-9, u: 1e-6, m: 1e-3, k: 1e3, K: 1e3, M: 1e6, G: 1e9 };
/** Parse only dimensioned values; no guessed unit or physical setup default. */
export function parseWorkspaceIntentValue(text: string, unit: string): number | undefined {
  const match = new RegExp(`^(${valuePattern})\\s*([a-zA-Z]+)$`).exec(text.trim().replace(/[\u00b5\u03bc]/g, "u"));
  if (!match) return undefined;
  const supplied = match[2];
  let scale: number | undefined;
  if (supplied === unit || (unit === "ohm" && /^(ohms?)$/i.test(supplied)) || (unit === "C" && /^(degC|celsius)$/i.test(supplied))) scale = 1;
  else if (unit !== "C" && supplied.endsWith(unit)) scale = prefixes[supplied.slice(0, -unit.length)];
  const value = Number(match[1]) * (scale ?? NaN);
  return Number.isFinite(value) ? value : undefined;
}
const aliases: Record<string, string> = { power: "powerW", heat: "powerW", powerw: "powerW", ambient: "ambientC", ambientc: "ambientC", temperature: "ambientC", rise: "riseTimeS", risetime: "riseTimeS", duration: "durationS", impedance: "impedanceOhm", z0: "impedanceOhm", fstart: "frequencyStartHz", fstop: "frequencyStopHz", startfrequency: "frequencyStartHz", stopfrequency: "frequencyStopHz", meshsize: "meshSizeM" };
function readParameters(text: string, schema: WorkspaceIntentSchema, issues: string[]): Record<string, number> {
  const values: Record<string, number> = {};
  const seen = new Set<string>();
  const accept = (key: string, raw: string) => {
    const spec = schema.fields.find(item => item.key === key);
    if (!spec) { issues.push(`Parameter ${key} is not supported by this setup.`); return; }
    const repeated = seen.has(key); seen.add(key);
    const value = parseWorkspaceIntentValue(raw, spec.unit);
    if (repeated || value === undefined || (spec.minimum !== undefined && (spec.exclusiveMinimum ? value <= spec.minimum : value < spec.minimum))) {
      delete values[key]; issues.push(`${repeated ? "Repeated" : "Invalid"} ${spec.label}: ${raw}. Supply one value in ${spec.unit}.`);
    } else values[key] = value;
  };
  let remainder = text.replace(/[\u00b5\u03bc]/g, "u").replace(/\b(powerW|power|heat|ambientC|ambient|temperature|riseTime|rise|duration|impedance|z0|fstart|fstop|startFrequency|stopFrequency|meshSize)\s*(?:=|:)?\s*([^\s,;]+)(?:\s+([pnumkMG]?Hz|[pnumkMG]?W|C|degC|[pnumkMG]?s|ohms?|[pnumkMG]?m)\b)?/gi, (_all, key: string, raw: string, unit?: string) => { accept(aliases[fold(key)], `${raw}${unit ?? ""}`); return " "; });
  const frequencies: string[] = [];
  remainder = remainder.replace(new RegExp(`(${valuePattern})\\s*([pnumkMG]?Hz|[pnumkMG]?W|degC|C|ohms?|[pnumkMG]?s|mm|um)\\b`, "g"), (_all, value: string, unit: string) => {
    if (unit.endsWith("Hz")) frequencies.push(`${value}${unit}`);
    else {
      const key = unit.endsWith("W") ? "powerW" : /^(C|degC)$/.test(unit) ? "ambientC" : unit.startsWith("ohm") ? "impedanceOhm" : /^(mm|um)$/.test(unit) ? "meshSizeM" : schema.workflowKey === "si" ? "riseTimeS" : "durationS";
      accept(key, `${value}${unit}`);
    }
    return " ";
  });
  frequencies.forEach((raw, index) => accept(index === 0 ? "frequencyStartHz" : "frequencyStopHz", raw));
  // Retain malformed supplied quantities as blocking diagnostics, including NaN/Infinity.
  if (/\b(?:NaN|Infinity)\s*(?:W|Hz|C|s)\b|(?<![\w.])[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?\s*[a-zA-Z]+\b/i.test(remainder)) issues.push("Invalid or unsupported quantity; enter a dimensioned setup value.");
  if (values.frequencyStartHz !== undefined && values.frequencyStopHz !== undefined && values.frequencyStopHz <= values.frequencyStartHz) issues.push("Stop frequency must exceed start frequency.");
  return values;
}
const entityPatterns = new WeakMap<readonly WorkspaceIntentEntity[], { entity: WorkspaceIntentEntity; expression: RegExp }[]>();
function cachedEntityPatterns(pool: readonly WorkspaceIntentEntity[]) {
  let entries = entityPatterns.get(pool);
  if (!entries) {
    entries = [...pool].filter(item => item.name.length > 0 && item.name.length <= 512).sort((a, b) => b.name.length - a.name.length).map(entity => {
      const escaped = entity.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return { entity, expression: new RegExp(`(^|[\\s,;])${escaped}(?=$|[\\s,;])`, "i") };
    });
    entityPatterns.set(pool, entries);
  }
  return entries;
}
const quotePattern = '"[^"\\r\\n]+"|\'[^\'\\r\\n]+\'|[^\\s,;]+';
function referenceInputs(text: string, kind: "net" | "component" | "occurrence", pool: readonly WorkspaceIntentEntity[]): string[] {
  const inputs = new Set<string>();
  // Known whole names may include spaces/punctuation. No identifier fuzzy matching.
  let unquoted = text.replace(/"([^"\r\n]+)"|'([^'\r\n]+)'/g, (_all, double: string, single: string) => {
    const name = double ?? single;
    if (pool.some(item => fold(item.name) === fold(name))) inputs.add(name);
    return " ";
  });
  for (const { entity, expression } of cachedEntityPatterns(pool)) {
    if (expression.test(unquoted)) { inputs.add(entity.name); unquoted = unquoted.replace(expression, " "); }
  }
  const marker = kind === "net" ? "nets?" : kind === "component" ? "components?|parts?" : "occurrences?";
  const marked = new RegExp(`\\b(?:${marker})\\s+(${quotePattern})`, "gi");
  for (const match of text.matchAll(marked)) if (!/^(and|on|with|from|to|assembly|board|selected)$/i.test(match[1])) inputs.add(unquote(match[1]));
  if (kind === "component") for (const match of text.matchAll(/\b(?:U|R|C|L|D|Q|J|P|TP|SW|F|Y|X)\d+[A-Za-z]?\b/gi)) if (!/^\d/.test(match[0])) inputs.add(match[0]);
  return [...inputs];
}
function resolve(inputs: string[], pool: readonly WorkspaceIntentEntity[], field: WorkspaceIntentAmbiguity["field"], draft: WorkspaceIntentDraft) {
  for (const input of inputs) {
    const candidates = pool.filter(item => fold(item.name) === fold(input) || item.id === input);
    if (candidates.length === 1) { if (!draft.bindings[field].includes(candidates[0].id)) draft.bindings[field].push(candidates[0].id); }
    else if (candidates.length > 1) draft.ambiguities.push({ field, input, candidates: [...candidates] });
    else draft.issues.push(`Unknown ${field === "netIds" ? "net" : field === "componentIds" ? "component" : "occurrence"}: ${input}. Choose an explicit identity.`);
  }
}
export function workspaceIntentMissing(draft: WorkspaceIntentDraft): string[] {
  const schema = WORKSPACE_INTENT_SCHEMAS.find(item => item.workflowKey === draft.workflowKey)!;
  const missing = schema.fields.filter(item => item.required && draft.parameters[item.key] === undefined).map(item => `${item.label} (${item.unit})`);
  if (schema.requiredBinding && !draft.bindings[schema.requiredBinding].length) missing.push(`Choose ${schema.requiredBinding === "netIds" ? "a net" : "a component"}.`);
  if (draft.workflowKey === "thermal" && draft.scope === "component" && !draft.bindings.componentIds.length) missing.push("Choose a component.");
  if (draft.workflowKey === "coupling") missing.push("Choose the coupling workflow and participating physics.");
  if (draft.workflowKey === "assembly") {
    if (draft.assemblyOperation === "connect" && draft.bindings.occurrenceIds.length < 2) missing.push("Choose at least two board occurrences and connector endpoints.");
    if (["move", "rotate", "place"].includes(draft.assemblyOperation ?? "")) {
      if (!draft.bindings.occurrenceIds.length) missing.push("Choose a board occurrence for placement.");
      missing.push("Review the requested placement and transform in assembly setup.");
    }
  }
  return missing;
}
/** Deterministic lexical planning, bounded to 512 characters. Never dispatches work. */
export function suggestWorkspaceIntents(query: string, context: WorkspaceIntentContext): WorkspaceIntentSuggestion[] {
  if (!query.trim() || query.length > 512) return [];
  const key = detect(query);
  if (!key) return [];
  const schema = WORKSPACE_INTENT_SCHEMAS.find(item => item.workflowKey === key)!;
  const draft: WorkspaceIntentDraft = { workflowKey: key, domain: schema.domain, scope: "workspace", contextVersion: context.version, suppliedText: query, bindings: { netIds: [], componentIds: [], occurrenceIds: [] }, parameters: {}, missing: [], ambiguities: [], issues: [], availability: key === "assemblyCHT" ? "unsupported" : "review", limitation: schema.limitation };
  if (key === "assembly") {
    const operation = /\b(connect|mate|harness|move|rotate|place|open)\b/i.exec(query)?.[1].toLowerCase();
    draft.assemblyOperation = operation === "move" || operation === "rotate" || operation === "place" ? operation : operation === "open" ? "open" : "connect";
  }
  draft.parameters = schema.fields.length ? readParameters(query, schema, draft.issues) : {};
  const netInputs = referenceInputs(query, "net", context.nets ?? []);
  // SI and RF accept an explicit unmarked name after "on" without substring fallback.
  if (!netInputs.length && ["si", "rf"].includes(key)) {
    const match = new RegExp(`\\bon\\s+(${quotePattern})`, "i").exec(query);
    if (match && !/^(board|assembly|selected|selection|the)$/i.test(match[1])) netInputs.push(unquote(match[1]));
  }
  const componentInputs = referenceInputs(query, "component", context.components ?? []).filter(input => !netInputs.some(net => fold(net) === fold(input)));
  if (!componentInputs.length && ["thermal", "electrothermal", "model-assignment"].includes(key)) {
    const match = new RegExp(`\\bon\\s+(${quotePattern})`, "i").exec(query);
    if (match && !/^(board|assembly|selected|selection|the)$/i.test(match[1])) componentInputs.push(unquote(match[1]));
  }
  const occurrenceInputs = referenceInputs(query, "occurrence", context.occurrences ?? []);
  resolve(occurrenceInputs, context.occurrences ?? [], "occurrenceIds", draft);
  const components = (context.components ?? []).filter(item => !item.occurrenceId || !draft.bindings.occurrenceIds.length || draft.bindings.occurrenceIds.includes(item.occurrenceId));
  resolve(netInputs, context.nets ?? [], "netIds", draft);
  resolve(componentInputs, components, "componentIds", draft);
  const role = (input: string | undefined, pool: readonly WorkspaceIntentEntity[], field: WorkspaceIntentAmbiguity["field"]) => {
    if (!input || /^(board|assembly|selected|selection|the)$/i.test(input)) return undefined;
    const choices = pool.filter(item => fold(item.name) === fold(unquote(input)) || item.id === unquote(input));
    if (choices.length === 1) return choices[0].id;
    if (!choices.length && !draft.issues.some(issue => issue.includes(input))) draft.issues.push(`Unknown role identity: ${input}. Choose an explicit ${field}.`);
    if (choices.length > 1 && !draft.ambiguities.some(item => item.field === field && item.input === unquote(input))) draft.ambiguities.push({ field, input: unquote(input), candidates: choices });
    return undefined;
  };
  const signal = new RegExp(`\\b(?:on|signal)\\s+(?:net\\s+)?(${quotePattern})`, "i").exec(query);
  const reference = new RegExp(`\\b(?:return|reference)\\s+(?:net\\s+)?(${quotePattern})`, "i").exec(query);
  const source = new RegExp(`\\bfrom\\s+(${quotePattern})`, "i").exec(query);
  const sink = new RegExp(`\\bto\\s+(${quotePattern})`, "i").exec(query);
  draft.roles = {};
  if (["si", "rf", "em"].includes(key)) {
    draft.roles.signalNetId = role(signal?.[1], context.nets ?? [], "netIds");
    draft.roles.referenceNetId = role(reference?.[1], context.nets ?? [], "netIds");
    if (source && sink && !/^[+-]?[\d.]/.test(source[1])) {
      draft.roles.sourceComponentId = role(source[1], components, "componentIds");
      const sinkId = role(sink[1], components, "componentIds");
      if (sinkId) draft.roles.sinkComponentIds = [sinkId];
      let tail = query.slice(sink.index + sink[0].length);
      const additional = new RegExp(`^\\s*(?:,|and)\\s*(${quotePattern})`, "i");
      for (let next = additional.exec(tail); next; next = additional.exec(tail)) {
        const id = role(next[1], components, "componentIds");
        if (id) draft.roles.sinkComponentIds = [...(draft.roles.sinkComponentIds ?? []), id];
        tail = tail.slice(next[0].length);
      }
    }
  }
  const selected = /\b(selected|selection)\b/i.test(query);
  if (selected) {
    if (!netInputs.length) draft.bindings.netIds = [...(context.selectedNetIds ?? [])];
    if (!componentInputs.length) draft.bindings.componentIds = [...(context.selectedComponentIds ?? [])];
    if (!occurrenceInputs.length) draft.bindings.occurrenceIds = [...(context.selectedOccurrenceIds ?? [])];
  }
  draft.scope = /\bassembly\b/i.test(query) || key === "assembly" ? "assembly" : /\bboard\b/i.test(query) ? "board" : componentInputs.length ? "component" : netInputs.length ? "net" : occurrenceInputs.length ? "assembly" : selected ? "selection" : schema.scopes[0];
  if (key === "referenceCHT" && (draft.scope !== "workspace" || draft.bindings.netIds.length || draft.bindings.componentIds.length || draft.bindings.occurrenceIds.length)) {
    draft.workflowKey = "assemblyCHT"; draft.domain = "CHT"; draft.availability = "unsupported";
    draft.limitation = WORKSPACE_INTENT_SCHEMAS.find(item => item.workflowKey === "assemblyCHT")!.limitation;
    draft.issues.push("The fixed reference cannot accept the requested geometry scope.");
  }
  if (key === "cfd") {
    const geometryRequested = Boolean(netInputs.length || componentInputs.length || occurrenceInputs.length || draft.bindings.netIds.length || draft.bindings.componentIds.length || draft.bindings.occurrenceIds.length || /\b(board|boards|assembly|components?|parts?|nets?|occurrences?|selected|selection)\b/i.test(query));
    const explicitReference = /\b(workspace|cavity|reference|benchmark)\b/i.test(query);
    if (explicitReference && !geometryRequested) draft.scope = "workspace";
    if (draft.scope !== "workspace" || geometryRequested) draft.availability = "unsupported";
  }
  if (!schema.scopes.includes(draft.scope)) {
    draft.availability = "unsupported";
    draft.issues.push(`Requested ${draft.scope} scope is not supported by this workflow.`);
  }
  draft.missing = workspaceIntentMissing(draft);
  if (draft.bindings.componentIds.length > 1 && draft.parameters.powerW !== undefined) draft.missing.push("Review allocation of the supplied total heat across components.");
  const finalSchema = WORKSPACE_INTENT_SCHEMAS.find(item => item.workflowKey === draft.workflowKey)!;
  return [{ id: `workspace-intent:${draft.workflowKey}`, label: finalSchema.label, completion: query, draft }];
}
