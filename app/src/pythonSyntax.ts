// SPDX-License-Identifier: Apache-2.0
export type PythonTokenKind = "keyword" | "builtin" | "definition" | "class-name" | "parameter" | "decorator" | "module" | "number" | "string" | "comment" | "operator";
export type PythonToken = { start: number; end: number; kind: PythonTokenKind };
export type PythonLexState = { quote: "'" | '"' | null; triple: boolean; raw: boolean };
export type PythonLineTokens = { text: string; stateIn: PythonLexState; stateOut: PythonLexState; tokens: PythonToken[] };
export type PythonSyntaxCache = { code: string; lines: string[]; entries: PythonLineTokens[]; tokenizedLines: number; reusedLines: number };

const INITIAL_STATE: PythonLexState = { quote: null, triple: false, raw: false };
const KEYWORDS = new Set(["False", "None", "True", "and", "as", "assert", "async", "await", "break", "case", "class", "continue", "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "match", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield"]);
const BUILTINS = new Set(["abs", "all", "any", "bin", "bool", "breakpoint", "bytearray", "bytes", "callable", "chr", "classmethod", "compile", "complex", "delattr", "dict", "dir", "divmod", "enumerate", "eval", "exec", "filter", "float", "format", "frozenset", "getattr", "globals", "hasattr", "hash", "help", "hex", "id", "input", "int", "isinstance", "issubclass", "iter", "len", "list", "locals", "map", "max", "memoryview", "min", "next", "object", "oct", "open", "ord", "pow", "print", "property", "range", "repr", "reversed", "round", "set", "setattr", "slice", "sorted", "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip"]);
const copyState = (state: PythonLexState): PythonLexState => ({ ...state });
const sameState = (left: PythonLexState, right: PythonLexState) => left.quote === right.quote && left.triple === right.triple && left.raw === right.raw;
const identifierStart = (value: string) => /[A-Za-z_]/.test(value);
const identifierPart = (value: string) => /[A-Za-z0-9_]/.test(value);
function escaped(text: string, index: number) { let slashes = 0; for (let at = index - 1; at >= 0 && text[at] === "\\"; at--) slashes++; return slashes % 2 === 1; }
function scanString(text: string, contentStart: number, state: PythonLexState) {
  const marker = state.quote!.repeat(state.triple ? 3 : 1);
  for (let index = contentStart; index < text.length; index++) if (text.slice(index, index + marker.length) === marker && !escaped(text, index)) return { end: index + marker.length, state: copyState(INITIAL_STATE) };
  return { end: text.length, state: state.triple || text.endsWith("\\") && !escaped(text, text.length - 1) ? state : copyState(INITIAL_STATE) };
}
function stringOpening(text: string, index: number) {
  const match = text.slice(index).match(/^([rRuUbBfF]{0,3})("""|'''|"|')/); if (!match) return null;
  const prefix = match[1].toLowerCase();
  if (new Set(prefix).size !== prefix.length || prefix.includes("u") && (prefix.includes("b") || prefix.includes("f")) || prefix.includes("b") && prefix.includes("f")) return null;
  return { width: match[0].length, quote: match[2][0] as "'" | '"', triple: match[2].length === 3, raw: prefix.includes("r") };
}
function tokenizeLine(text: string, incoming: PythonLexState): PythonLineTokens {
  const stateIn = copyState(incoming), tokens: PythonToken[] = []; let state = copyState(incoming), index = 0, declaration: "function" | "class" | null = null, parameterDepth = 0, importMode = false;
  if (state.quote) { const result = scanString(text, 0, state); tokens.push({ start: 0, end: result.end, kind: "string" }); state = result.state; index = result.end; if (state.quote) return { text, stateIn, stateOut: copyState(state), tokens }; }
  while (index < text.length) {
    const char = text[index];
    if (char === "#") { tokens.push({ start: index, end: text.length, kind: "comment" }); break; }
    if (/\s/.test(char)) { index++; continue; }
    if (char === "@" && text.slice(0, index).trim() === "") { const match = text.slice(index).match(/^@[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*/); if (match) { tokens.push({ start: index, end: index + match[0].length, kind: "decorator" }); index += match[0].length; continue; } }
    const opening = (char === "'" || char === '"' || identifierStart(char)) ? stringOpening(text, index) : null;
    if (opening && (index === 0 || !identifierPart(text[index - 1]))) { state = { quote: opening.quote, triple: opening.triple, raw: opening.raw }; const result = scanString(text, index + opening.width, state); tokens.push({ start: index, end: result.end, kind: "string" }); state = result.state; index = result.end; continue; }
    const number = text.slice(index).match(/^(?:0[xX][0-9a-fA-F](?:_?[0-9a-fA-F])*|0[bB][01](?:_?[01])*|0[oO][0-7](?:_?[0-7])*|(?:\d(?:_?\d)*)?\.\d(?:_?\d)*(?:[eE][+-]?\d(?:_?\d)*)?|\d(?:_?\d)*(?:[eE][+-]?\d(?:_?\d)*)?)[jJ]?/);
    if (number) { tokens.push({ start: index, end: index + number[0].length, kind: "number" }); index += number[0].length; continue; }
    if (identifierStart(char)) {
      let end = index + 1; while (end < text.length && identifierPart(text[end])) end++;
      const word = text.slice(index, end), following = text.slice(end).match(/^\s*(.)/)?.[1]; let kind: PythonTokenKind | null = null;
      if (KEYWORDS.has(word)) kind = "keyword"; else if (declaration === "function") { kind = "definition"; declaration = null; } else if (declaration === "class") { kind = "class-name"; declaration = null; } else if (parameterDepth > 0) kind = "parameter"; else if (importMode) kind = "module"; else if (BUILTINS.has(word)) kind = "builtin"; else if (following === "(") kind = "definition";
      if (kind) tokens.push({ start: index, end, kind }); if (word === "def") declaration = "function"; else if (word === "class") declaration = "class"; if (word === "import" || word === "from") importMode = true; index = end; continue;
    }
    if (char === "(" && declaration === null && /\bdef\s+[A-Za-z_]\w*\s*$/.test(text.slice(0, index))) parameterDepth = 1; else if (parameterDepth > 0 && char === "(") parameterDepth++; else if (parameterDepth > 0 && char === ")") parameterDepth--;
    if (/[-+*/%=<>!&|^~:@.,;()[\]{}]/.test(char)) tokens.push({ start: index, end: index + 1, kind: "operator" }); index++;
  }
  return { text, stateIn, stateOut: copyState(state), tokens };
}
export function updatePythonSyntaxCache(previous: PythonSyntaxCache | undefined, code: string): PythonSyntaxCache {
  if (previous?.code === code) return previous;
  const lines = code.split("\n"), oldLines = previous?.lines ?? [], oldEntries = previous?.entries ?? []; let prefix = 0;
  while (prefix < lines.length && prefix < oldLines.length && lines[prefix] === oldLines[prefix]) prefix++;
  let suffix = 0; while (suffix < lines.length - prefix && suffix < oldLines.length - prefix && lines[lines.length - 1 - suffix] === oldLines[oldLines.length - 1 - suffix]) suffix++;
  const entries = oldEntries.slice(0, prefix); let currentState = prefix ? copyState(entries[prefix - 1].stateOut) : copyState(INITIAL_STATE), tokenizedLines = 0, reusedLines = prefix;
  for (let index = prefix; index < lines.length; index++) {
    const oldIndex = oldLines.length - (lines.length - index), old = suffix > 0 && index >= lines.length - suffix && oldIndex >= 0 ? oldEntries[oldIndex] : undefined;
    if (old && old.text === lines[index] && sameState(old.stateIn, currentState)) { for (let next = index; next < lines.length; next++) entries[next] = oldEntries[oldLines.length - (lines.length - next)]; reusedLines += lines.length - index; return { code, lines, entries, tokenizedLines, reusedLines }; }
    const entry = tokenizeLine(lines[index], currentState); entries[index] = entry; currentState = entry.stateOut; tokenizedLines++;
  }
  return { code, lines, entries, tokenizedLines, reusedLines };
}
export function pythonHighlightWindow(cache: PythonSyntaxCache, firstLine: number, lastLine: number) {
  const first = Math.max(1, Math.min(cache.lines.length, firstLine)), last = Math.max(first, Math.min(cache.lines.length, lastLine));
  return { firstLine: first, lastLine: last, entries: cache.entries.slice(first - 1, last) };
}
