// SPDX-License-Identifier: Apache-2.0
/** Presentation-only, bounded sentence planning. Every result requires setup review. */
import type { ParsedBoard } from "./boardParser";
import { eligibleComponentSupplyPads } from "./piPinLoads";

export type PiIntentEndpoint = { ref: string; padIds: string[] };
export type PiIntentAmbiguity = { field: string; input: string; candidates: { id: string; name: string }[] };
export type PiSetupIntentDraft = {
  netId?: string;
  netName?: string;
  source?: PiIntentEndpoint;
  sources?: PiIntentEndpoint[];
  sourceInputs?: string[];
  sinkInputs?: string[];
  sinks: PiIntentEndpoint[];
  voltageV?: number;
  sourceCurrentA?: number;
  /** One explicitly supplied total sink current; distribution remains a setup decision. */
  sinkCurrentA?: number;
  missing: string[];
  ambiguities: PiIntentAmbiguity[];
  assumptions: string[];
};
export type PiSetupIntentSuggestion = { id: string; label: string; completion: string; draft: PiSetupIntentDraft };
type Choice = { id: string; name: string; fuzzy?: boolean };
const lower = (text: string) => text.toLowerCase();
const unquote = (text: string) => text.trim().replace(/^(["'])(.*)\1$/, "$2");

function distance(a: string, b: string): number {
  if (a.length > 96 || b.length > 96 || Math.abs(a.length - b.length) > 2) return 99;
  let row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const next = [i];
    for (let j = 1; j <= b.length; j++) next[j] = Math.min(next[j - 1] + 1, row[j] + 1, row[j - 1] + Number(a[i - 1] !== b[j - 1]));
    if (next.every(value => value > 2)) return 99;
    row = next;
  }
  return row[b.length];
}
function choices(input: string, pool: Choice[]): Choice[] {
  const term = lower(unquote(input));
  const exact = pool.filter(item => item.name === unquote(input));
  if (exact.length) return exact.slice(0, 20);
  const folded = pool.filter(item => lower(item.name) === term);
  if (folded.length) return folded.slice(0, 20);
  if (!term) return [];
  return pool.map(item => ({ item, score: distance(term, lower(item.name)) }))
    .filter(({ item, score }) => score <= (term.length >= 7 ? 2 : 1) || lower(item.name).startsWith(term))
    .sort((a, b) => a.score - b.score || a.item.name.localeCompare(b.item.name) || a.item.id.localeCompare(b.item.id))
    .slice(0, 6).map(({ item }) => ({ ...item, fuzzy: true }));
}
function hasPiVerb(text: string): string | null {
  const match = /^(\S+)\s+(.+)$/.exec(text);
  if (!match) return null;
  const verb = lower(match[1]);
  if (!["run", "simulate", "solve", "analyze", "analyse", "calculate", "configure"].some(word => distance(verb, word) <= 1)) return null;
  const rest = match[2].replace(/^a\s+/i, "");
  const alias = /^(pi|power\s+integrity|dc(?:\s+ir\s+drop)?|dcir|voltage\s+drop)(?=\s|$)/i.exec(rest);
  if (alias) return rest.slice(alias[0].length);
  const words = /^(\S+)\s+(\S+)(.*)$/.exec(rest);
  return words && distance(lower(words[1]), "power") <= 1 && distance(lower(words[2]), "integrity") <= 2 ? words[3] : null;
}

/** Uses only this board's canonical identities and endpoint pad membership. Never runs PI. */
export function suggestPiSetupIntents(query: string, board: ParsedBoard): PiSetupIntentSuggestion[] {
  if (!query.trim() || query.length > 512) return [];
  const text = query.trim().replace(/^(?:please\s+|(?:can|could|would) you\s+|i want to\s+)/i, "")
    .replace(/^on\s+(?:the\s+)?board\s*[:,]?\s*/i, "").replace(/^set\s+up\s+/i, "configure ");
  let body = hasPiVerb(text);
  if (body === null) return [];
  body = body.replace(/^\s+(?:analysis|simulation|check)\b/i, "");
  const missing: string[] = [];
  const assumptions = ["Review this PI setup before running; component roles are taken from your sentence."];
  const electrical: Pick<PiSetupIntentDraft, "voltageV" | "sourceCurrentA" | "sinkCurrentA"> = {};
  const seen = new Set<string>();
  // Capture the complete value token so malformed units cannot be silently ignored.
  body = body.replace(/\b(Vsup|Isup|Isink)\s*(?:=|:)?\s*([^\s,;]+)(?:\s+((?:[munpkM]?A|[munpkM]?V))\b)?/gi, (_all, rawKey: string, token: string, spacedUnit?: string) => {
    const key = lower(rawKey);
    const field = key === "vsup" ? "voltageV" : key === "isup" ? "sourceCurrentA" : "sinkCurrentA";
    if (seen.has(key)) { delete electrical[field]; missing.push(`Repeated ${rawKey}; enter one value in setup.`); return " "; }
    seen.add(key);
    const match = /^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)([a-zA-Z\u00b5\u03bc]*)$/i.exec(token);
    const unit = match ? (match[2] || spacedUnit || (key === "vsup" ? "V" : "A")) : "";
    const base = key === "vsup" ? "V" : "A";
    const scales: Record<string, number> = { "": 1, m: 1e-3, u: 1e-6, "\u00b5": 1e-6, "\u03bc": 1e-6, n: 1e-9, p: 1e-12, k: 1e3, M: 1e6 };
    const prefix = unit.slice(0, -1);
    const value = match ? Number(match[1]) * scales[prefix] : NaN;
    if (!match || unit.slice(-1).toUpperCase() !== base || !Number.isFinite(value) || value < 0 || (key !== "isink" && value === 0)) {
      missing.push(`Invalid ${rawKey}: ${token}${spacedUnit ? ` ${spacedUnit}` : ""}. Enter a valid ${base} value.`);
    } else {
      electrical[field] = value;
      if (!match[2] && !spacedUnit) assumptions.push(`${rawKey} without a unit was read as ${base}.`);
    }
    return " ";
  });
  body = body.replace(/\s+(?:with|at)\s*$/i, "").trim().replace(/[,;]\s*$/, "").trim();
  const endpoints = /^(.*?)\bfrom\s+(.+?)\s+to\s+(.+)$/i.exec(body);
  let netInput = (endpoints ? endpoints[1] : body).trim().replace(/^(?:on|for)\s+/i, "").replace(/^(?:the\s+)?net\s+/i, "").trim();
  // "netx" is a legal net name; never strip the letters "net" from a name.
  netInput = unquote(netInput);
  const sourceInputs = endpoints ? endpoints[2].split(/\s*(?:,|;|\band\b|&)\s*/i).map(unquote).filter(Boolean) : [];
  const sinkInputs = endpoints ? endpoints[3].split(/\s*(?:,|;|\band\b|&)\s*/i).map(unquote).filter(Boolean) : [];
  if (sinkInputs.length > 12 || sourceInputs.length > 12) return [];
  const refs = [...new Set(board.components.map(component => component.ref))];
  const refPool = refs.map(ref => ({ id: ref, name: ref }));
  const sourceChoices = sourceInputs.map(input => choices(input, refPool));
  const sinkChoices = sinkInputs.map(input => choices(input, refPool));
  const ambiguities: PiIntentAmbiguity[] = [];
  function record(field: string, input: string, options: Choice[]) {
    if (input && (!options.length || options.length > 1 || options[0].fuzzy)) ambiguities.push({ field, input, candidates: options.map(({ id, name }) => ({ id, name })) });
  }
  sourceInputs.forEach((input, i) => record(sourceInputs.length === 1 ? "source" : `source ${i + 1}`, input, sourceChoices[i]));
  sinkInputs.forEach((input, i) => record(`sink ${i + 1}`, input, sinkChoices[i]));
  if (!sourceInputs.length) missing.push("Choose a source component.");
  sourceInputs.forEach((input, i) => { if (!sourceChoices[i].length) missing.push(`Unknown source component ${input}.`); });
  if (!sinkInputs.length) missing.push("Choose sink components.");
  sinkInputs.forEach((input, i) => { if (!sinkChoices[i].length) missing.push(`Unknown sink component ${input}.`); });
  const netPool = Object.entries(board.nets).filter(([id]) => id !== "0").map(([id, name]) => ({ id, name }));
  let nets = netInput ? choices(netInput, netPool) : [];
  if (netInput) record("net", netInput, nets);
  const allEndpointChoices = [...sourceChoices, ...sinkChoices];
  const resolvedEndpoints = !!sourceInputs.length && !!sinkInputs.length && allEndpointChoices.every(options => options.length === 1 && !options[0].fuzzy);
  if (!netInput && resolvedEndpoints) {
    nets = netPool.filter(net => allEndpointChoices.every(options => eligibleComponentSupplyPads(board, options[0].name, net.name).length > 0));
    if (nets.length === 1) assumptions.push(`Net ${nets[0].name} was inferred from the unique shared endpoint pad membership; review it.`);
    else if (nets.length > 1) record("net", "shared endpoint nets", nets);
  }
  if (!nets.length) missing.push(netInput ? `Unknown net ${netInput}.` : "Choose a net; endpoint membership did not establish one unique net.");
  // Ambiguous or approximate component identities stay unresolved until explicit setup review.
  const sourceRefs = sourceChoices.flatMap(options => options.length === 1 && !options[0].fuzzy ? [options[0].name] : []);
  const sinkRefs = sinkChoices.flatMap(options => options.length === 1 && !options[0].fuzzy ? [options[0].name] : []);
  if (sourceChoices.some(options => options.some(choice => choice.fuzzy) || options.length > 1)) missing.push("Confirm source component spellings.");
  if (sinkChoices.some(options => options.some(choice => choice.fuzzy) || options.length > 1)) missing.push("Confirm sink component spellings.");
  if (electrical.voltageV === undefined) missing.push("Enter Vsup (V).");
  if (electrical.sourceCurrentA === undefined) missing.push("Enter Isup (A).");
  if (electrical.sinkCurrentA === undefined) missing.push("Enter Isink (A).");
  if (sourceInputs.length > 1) assumptions.push("Review voltage and current capacity separately for every source; sentence values do not assign per-source settings.");
  if (sinkInputs.length > 1 && electrical.sinkCurrentA !== undefined) assumptions.push("Isink is a total for all sinks; review its distribution in setup.");
  return (nets.length ? nets : [undefined]).slice(0, 20).map(net => {
    const localMissing = [...missing];
    const endpoint = (ref: string): PiIntentEndpoint => ({ ref, padIds: net ? eligibleComponentSupplyPads(board, ref, net.name).map(pad => pad.id) : [] });
    const sources = [...new Set(sourceRefs)].map(endpoint);
    const source = sources[0];
    const sinks = [...new Set(sinkRefs)].map(endpoint);
    if (net) {
      for (const entry of [...sources, ...sinks]) if (!entry.padIds.length) localMissing.push(`${entry.ref} has no pad on ${net.name}.`);
    }
    const localAssumptions = [...assumptions];
    if (net?.fuzzy) localAssumptions.push(`Suggested net spelling ${net.name} for ${netInput}; selecting this suggestion confirms that choice.`);
    if (net && nets.length > 1) localAssumptions.push(`Choose ${net.name} (${net.id}) explicitly from the net candidates.`);
    const draft: PiSetupIntentDraft = { netId: net?.id, netName: net?.name, source, sources, sourceInputs, sinkInputs, sinks, ...electrical, missing: localMissing, ambiguities, assumptions: localAssumptions };
    const label = `Review PI setup${net ? ` on ${net.name} (${net.id})` : ""}${sources.length ? ` from ${sources.map(entry => entry.ref).join(", ")}` : ""}${sinks.length ? ` to ${sinks.map(sink => sink.ref).join(", ")}` : ""}`;
    return { id: `pi-setup:${net?.id ?? "unresolved"}:${sourceInputs.join(",")}:${sinkInputs.join(",")}`, label, completion: query, draft };
  });
}


