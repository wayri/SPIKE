// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync, unlinkSync, writeFileSync } from "node:fs";
import ts from "typescript";

async function load(sourceName, targetName) {
  const source = readFileSync(new URL(`../src/${sourceName}`, import.meta.url), "utf8"), target = new URL(targetName, import.meta.url);
  writeFileSync(target, ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText);
  try { return await import(target.href + `?${Date.now()}`); } finally { try { unlinkSync(target); } catch {} }
}

const syntax = await load("pythonSyntax.ts", ".test-pythonSyntax.mjs"), actions = await load("pythonEditorActions.ts", ".test-pythonEditorActions.mjs");
const code = ["@measure.trace", "async def sample(value: float = 1.25e-3):", "    note = f\"value={value} # data\"  # visible comment", "    block = rf\"\"\"first {value}", "# still string", "last\"\"\"", "    return print(note, block)"].join("\n");
let cache = syntax.updatePythonSyntaxCache(undefined, code);
const kinds = cache.entries.flatMap(entry => entry.tokens.map(token => ({ text: entry.text.slice(token.start, token.end), kind: token.kind })));
for (const expected of [["@measure.trace", "decorator"], ["async", "keyword"], ["sample", "definition"], ["value", "parameter"], ["1.25e-3", "number"], ["print", "builtin"]]) assert.ok(kinds.some(token => token.text === expected[0] && token.kind === expected[1]));
assert.equal(cache.entries[4].tokens[0].kind, "string");
assert.ok(cache.entries[2].tokens.some(token => token.kind === "comment"));
const changed = syntax.updatePythonSyntaxCache(cache, `${code}\nanswer = 0x2a`);
assert.ok(changed.reusedLines >= cache.lines.length - 1 && changed.tokenizedLines <= 2, "tail edits reuse lexical state");
const large = Array.from({ length: 20_000 }, (_, index) => `value_${index} = ${index}  # row`).join("\n"), largeCache = syntax.updatePythonSyntaxCache(undefined, large);
assert.equal(syntax.pythonHighlightWindow(largeCache, 10_000, 10_080).entries.length, 81, "large documents render only the requested viewport");
assert.deepEqual(actions.indentPythonSelection("a\nb", 0, 3), { code: "    a\n    b", start: 4, end: 11 });
assert.deepEqual(actions.insertPythonNewline("if ready:", 9, 9), { code: "if ready:\n    ", start: 14, end: 14 });
assert.equal(actions.togglePythonComment("  first\n  second", 2, 16).code, "  # first\n  # second");
let resolveLate; let current = true;
const stale = actions.boundedClipboardOperation(() => new Promise(resolve => { resolveLate = resolve; }), () => current, 50); current = false; resolveLate("late");
assert.deepEqual(await stale, { status: "stale" }, "late clipboard work cannot edit a changed document");
assert.deepEqual(await actions.boundedClipboardOperation(() => new Promise(() => {}), () => true, 5), { status: "timeout" });
const editor = readFileSync(new URL("../src/PythonCodeEditor.tsx", import.meta.url), "utf8");
assert.match(editor, /ActionContextMenu[\s\S]*title="Python editor"/);
assert.match(editor, /currentDocumentKey\.current === snapshotKey[\s\S]*currentCode\.current === snapshot[\s\S]*editor\.current\?\.value === snapshot/);
assert.match(editor, /pythonCompletion[\s\S]*has-breakpoint[\s\S]*python-syntax-layer/, "completion, breakpoints and highlighting remain integrated");
assert.match(readFileSync(new URL("../src/PythonWorkspace.tsx", import.meta.url), "utf8"), /PythonCodeEditor key=\{active\.id\} documentKey=\{active\.id\}/, "workspace supplies stable tab identity to asynchronous editor actions");
console.log("Python editor tokens, incremental viewport, edit actions and stale clipboard guard passed.");
