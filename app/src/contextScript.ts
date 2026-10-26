// SPDX-License-Identifier: Apache-2.0
export const CONTEXT_SCRIPT_EVENT = "spike-open-context-script";
export const MAX_CONTEXT_BYTES = 240_000;
export type ContextScript = { id: string; name: string; code: string; workingDirectory?: string };
export type ScriptContext = { kind: "selection" | "navigator" | "table" | "plot"; title: string; payload: unknown };

/** Opens a draft only. No execution, source mutation or solver admission is implied. */
export function contextScript(context: ScriptContext, id: string): ContextScript {
  if (!["selection", "navigator", "table", "plot"].includes(context.kind) || typeof context.title !== "string") throw new Error("Unsupported script context.");
  const json = JSON.stringify({ kind: context.kind, title: context.title, payload: context.payload });
  const bytes = new TextEncoder().encode(json);
  if (bytes.length > MAX_CONTEXT_BYTES) throw new Error("This context is too large to open as a script. Export the source data or select fewer samples; no samples were truncated.");
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const encoded = btoa(binary);
  const name = `${context.kind}-${context.title.replace(/[^\p{L}\p{N}_-]+/gu, "-").slice(0, 60) || "context"}.py`;
  return { id, name, code: `# UI context snapshot. Review and edit this unsaved draft before running.\n# Values keep their original labels and units; this does not run a solve.\nimport base64\nimport json\n\ncontext = json.loads(base64.b64decode('${encoded}').decode('utf-8'))\nprint(json.dumps(context, indent=2, ensure_ascii=False))\n\n# Current application inputs are available when you run this script.\n# The snapshot above can refer to an earlier view or selection.\ndesign = spike.design\nresults = spike.results\n` };
}

export function openContextScript(context: ScriptContext): void {
  // Admission happens before dispatch so a large context reports its own error.
  const document = contextScript(context, crypto.randomUUID());
  window.dispatchEvent(new CustomEvent(CONTEXT_SCRIPT_EVENT, { detail: document }));
}

export function admitContextScript(value: unknown): ContextScript | null {
  if (!value || typeof value !== "object") return null;
  const doc = value as Record<string, unknown>;
  return typeof doc.id === "string" && doc.id.length <= 100 && typeof doc.name === "string" && doc.name.endsWith(".py") && doc.name.length <= 100
    && typeof doc.code === "string" && new TextEncoder().encode(doc.code).length <= MAX_CONTEXT_BYTES * 2
    ? { id: doc.id, name: doc.name, code: doc.code } : null;
}

/** Snapshot sampled arrays on demand, rather than on every plot render. */
export function plotScriptContext(data: Record<string, unknown>[], layout: Record<string, unknown>, revision: string, sourceTraceCount = data.length): unknown {
  const keys = ["type", "name", "x", "y", "z", "r", "theta", "i", "j", "k", "u", "v", "w", "value", "text", "customdata", "xaxis", "yaxis", "subplot", "thetaunit"];
  let samples = 0;
  const visit = (value: unknown): unknown => {
    if (ArrayBuffer.isView(value)) return visit(Array.from(value as unknown as ArrayLike<number>));
    if (Array.isArray(value)) { samples += value.length; if (samples > 30_000) throw new Error("Select or export this large plot's source data. The script snapshot limit is 30,000 array entries; no samples were truncated."); return value.map(visit); }
    if (typeof value === "number" && !Number.isFinite(value)) return null;
    return value;
  };
  return { revision, source: "plot source traces and view comparisons", nonfinite_samples: "null represents a missing or nonfinite sample (gap)",
    axes: Object.fromEntries(["xaxis", "yaxis", "zaxis", "scene", "polar"].filter(key => layout[key] !== undefined).map(key => [key, layout[key]])),
    traces: data.map((trace, index) => ({ origin: index < sourceTraceCount ? "source" : "pasted view comparison", ...Object.fromEntries(keys.filter(key => trace[key] !== undefined).map(key => [key, visit(trace[key])])) })) };
}
