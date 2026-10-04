// SPDX-License-Identifier: Apache-2.0
export type PythonEditorEdit = { code: string; start: number; end: number };
export type BoundedClipboardResult<T> = { status: "ok"; value: T } | { status: "stale" } | { status: "timeout" } | { status: "failed"; error: unknown };
export const EDITOR_CLIPBOARD_TIMEOUT_MS = 3_000;

export async function boundedClipboardOperation<T>(task: () => Promise<T>, isCurrent: () => boolean, timeoutMs = EDITOR_CLIPBOARD_TIMEOUT_MS): Promise<BoundedClipboardResult<T>> {
  let timeoutHandle: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<BoundedClipboardResult<T>>(resolve => { timeoutHandle = setTimeout(() => resolve({ status: "timeout" }), timeoutMs); });
  const attempt = task().then<BoundedClipboardResult<T>, BoundedClipboardResult<T>>(value => ({ status: "ok", value }), error => ({ status: "failed", error }));
  const result = await Promise.race([attempt, timeout]);
  if (timeoutHandle !== undefined) clearTimeout(timeoutHandle);
  if (result.status !== "ok") return result;
  return isCurrent() ? result : { status: "stale" };
}

function selectedLineRange(code: string, start: number, end: number) {
  const lineStart = code.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
  const adjustedEnd = end > start && code[end - 1] === "\n" ? end - 1 : end;
  const nextBreak = code.indexOf("\n", adjustedEnd);
  return { lineStart, lineEnd: nextBreak < 0 ? code.length : nextBreak };
}

export function indentPythonSelection(code: string, start: number, end: number, outdent = false): PythonEditorEdit {
  if (start === end && !outdent) {
    const column = start - (code.lastIndexOf("\n", Math.max(0, start - 1)) + 1), insert = " ".repeat(4 - column % 4);
    return { code: code.slice(0, start) + insert + code.slice(end), start: start + insert.length, end: start + insert.length };
  }
  const range = selectedLineRange(code, start, end), source = code.slice(range.lineStart, range.lineEnd), lines = source.split("\n");
  let firstDelta = 0, totalDelta = 0;
  const changed = lines.map((line, index) => {
    let result: string, delta: number;
    if (outdent) { const remove = line.startsWith("\t") ? 1 : Math.min(4, line.match(/^ */)?.[0].length ?? 0); result = line.slice(remove); delta = -remove; }
    else { result = `    ${line}`; delta = 4; }
    if (index === 0) firstDelta = delta; totalDelta += delta; return result;
  }).join("\n");
  return { code: code.slice(0, range.lineStart) + changed + code.slice(range.lineEnd), start: Math.max(range.lineStart, start + firstDelta), end: Math.max(range.lineStart, end + totalDelta) };
}

export function insertPythonNewline(code: string, start: number, end: number): PythonEditorEdit {
  const lineStart = code.lastIndexOf("\n", Math.max(0, start - 1)) + 1, before = code.slice(lineStart, start);
  const base = before.match(/^[\t ]*/)?.[0] ?? "", indent = `${base}${before.trimEnd().endsWith(":") ? "    " : ""}`;
  const insertion = `\n${indent}`, caret = start + insertion.length;
  return { code: code.slice(0, start) + insertion + code.slice(end), start: caret, end: caret };
}

export function togglePythonComment(code: string, start: number, end: number): PythonEditorEdit {
  const range = selectedLineRange(code, start, end), source = code.slice(range.lineStart, range.lineEnd), lines = source.split("\n");
  const uncomment = lines.filter(line => line.trim()).every(line => /^\s*# ?/.test(line));
  let firstDelta = 0, totalDelta = 0;
  const changed = lines.map((line, index) => {
    if (!line.trim()) return line;
    const indent = line.match(/^\s*/)?.[0].length ?? 0;
    const next = uncomment ? line.slice(0, indent) + line.slice(indent).replace(/^# ?/, "") : `${line.slice(0, indent)}# ${line.slice(indent)}`;
    const delta = next.length - line.length; if (index === 0) firstDelta = delta; totalDelta += delta; return next;
  }).join("\n");
  return { code: code.slice(0, range.lineStart) + changed + code.slice(range.lineEnd), start: Math.max(range.lineStart, start + firstDelta), end: Math.max(range.lineStart, end + totalDelta) };
}
