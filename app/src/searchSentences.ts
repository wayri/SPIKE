// SPDX-License-Identifier: Apache-2.0
/** Bounded command grammar; never evaluates text or dispatches arbitrary worker methods. */
export type SearchTargetKind = "net" | "component" | "layer";
export type SearchCommandAction = "run-pi" | "configure-pi" | "select" | "focus" | "isolate" | "show-layer" | "hide-layer";
export type SearchTarget = { id: string; name: string; kind: SearchTargetKind };
export type SearchSentence = { action: SearchCommandAction; kind: SearchTargetKind; target: string };
export type SearchCommandSuggestion = SearchSentence & { id: string; name: string; completion: string; label: string };
export function parseSearchSentence(query: string): SearchSentence | null {
  if (query.length > 512) return null;
  const text = query.trim().replace(/^(?:please\s+|(?:can|could|would) you\s+|i want to\s+)/i, "");
  const pi = /^(run|simulate|solve|analy[sz]e|calculate|configure|set up)\s+(?:a\s+)?(?:pi|power integrity|dc(?: ir drop)?|dcir|voltage drop)(?=\s|$)(?:\s+(?:analysis|simulation|check))?(?:\s+(?:on|for))?(?:\s+(?:the\s+)?net)?(?:\s+(.*))?$/i.exec(text);
  const object = /^(select|highlight|focus|zoom to|isolate|find|show|hide)\s+(?:the\s+)?(net|part|component|layer)(?:\s+(.*))?$/i.exec(text);
  const match = pi ?? object;
  if (!match) return null;
  const kind: SearchTargetKind = pi ? "net" : object![2].toLowerCase() === "part" ? "component" : object![2].toLowerCase() as SearchTargetKind;
  const verb = match[1].toLowerCase();
  const action: SearchCommandAction = pi ? /configure|set up/.test(verb) ? "configure-pi" : "run-pi"
    : kind === "layer" && verb === "hide" ? "hide-layer" : kind === "layer" && verb === "show" ? "show-layer"
    : /focus|zoom to/.test(verb) ? "focus" : verb === "isolate" ? "isolate" : "select";
  if (kind === "component" && action === "isolate" || kind !== "layer" && verb === "hide") return null;
  let target = (pi ? pi[2] : object![3])?.trim() ?? "";
  if (target.startsWith('"') && target.endsWith('"')) {
    try { target = JSON.parse(target); } catch { return null; }
  } else if (target.startsWith("'") && target.endsWith("'")) target = target.slice(1, -1);
  return { action, kind, target };
}
const actionText: Record<SearchCommandAction, string> = { "run-pi": "Run PI on net", "configure-pi": "Configure PI on net", select: "Select", focus: "Focus", isolate: "Isolate", "show-layer": "Show layer", "hide-layer": "Hide layer" };
export function suggestSearchCommands(query: string, targets: SearchTarget[], preferredTargetId?: string): SearchCommandSuggestion[] {
  const sentence = parseSearchSentence(query);
  if (!sentence) return [];
  const term = sentence.target.toLocaleLowerCase();
  return targets.filter(target => target.kind === sentence.kind).map(target => {
    const name = target.name.toLocaleLowerCase();
    const score = !term && target.id === preferredTargetId ? 5 : target.name === sentence.target ? 4 : name === term ? 3 : name.startsWith(term) ? 2 : name.includes(term) ? 1 : 0;
    return { target, score };
  }).filter(row => row.score > 0).sort((a, b) => b.score - a.score || a.target.name.localeCompare(b.target.name) || a.target.id.localeCompare(b.target.id)).slice(0, 20).map(({ target }) => {
    const prefix = sentence.action === "run-pi" || sentence.action === "configure-pi" || sentence.action === "show-layer" || sentence.action === "hide-layer" ? actionText[sentence.action] : `${actionText[sentence.action]} ${sentence.kind}`;
    return { ...sentence, id: `sentence:${sentence.action}:${target.kind}:${target.id}`, name: target.name, target: target.id, label: `${prefix} ${target.name}`, completion: `${prefix} ${JSON.stringify(target.name)}` };
  });
}
