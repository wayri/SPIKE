// SPDX-License-Identifier: Apache-2.0
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import ActionContextMenu from "./ActionContextMenu";
import { contextMenuTrigger } from "./contextMenuTrigger";
import { boundedClipboardOperation, EDITOR_CLIPBOARD_TIMEOUT_MS, indentPythonSelection, insertPythonNewline, togglePythonComment, type BoundedClipboardResult, type PythonEditorEdit } from "./pythonEditorActions";
import { applyPythonCompletion, pythonBaseSuggestions, pythonCompletion, pythonSymbols, type PythonCompletion } from "./pythonCompletions";
import { pythonHighlightWindow, updatePythonSyntaxCache, type PythonLineTokens, type PythonSyntaxCache } from "./pythonSyntax";
import { pythonBoardNets, type PythonWorkspaceContext } from "./pythonWorkspaceContext";
import { PYTHON_CODE_LIMIT } from "./pythonWorkspaceModel";
import { PYTHON_TEMPLATES } from "./pythonWorkspaceTemplates";
import "./pythonCompletions.css";

const EMPTY_WORKSPACE: PythonWorkspaceContext = { boards: [], selected_board_id: null, assembly: null };
const LINE_HEIGHT = 18;
type EditorMenu = { x: number; y: number; start: number; end: number };
const byteLength = (value: string) => new TextEncoder().encode(value).byteLength;
const clipboardError = (error: unknown) => error instanceof Error ? error.message : String(error);

function HighlightedLine({ entry }: { entry: PythonLineTokens }) {
  const parts: ReactNode[] = []; let offset = 0;
  entry.tokens.forEach((token, index) => {
    if (token.start > offset) parts.push(entry.text.slice(offset, token.start));
    parts.push(<span className={`python-token-${token.kind}`} key={`${token.start}:${index}`}>{entry.text.slice(token.start, token.end)}</span>);
    offset = token.end;
  });
  if (offset < entry.text.length) parts.push(entry.text.slice(offset));
  return <div className="python-syntax-line">{parts.length ? parts : "\u200b"}</div>;
}

export default function PythonCodeEditor({ code, documentKey, breakpoints, executionLine, locked, focusLine, insertion, workspace = EMPTY_WORKSPACE, onInserted, onChange, onBreakpoint, onCursor, onShortcut }: {
  code: string; documentKey?: string; breakpoints: number[]; executionLine?: number; locked: boolean;
  workspace?: PythonWorkspaceContext; focusLine?: { line: number; revision: number }; insertion?: { text: string; revision: number };
  onInserted?: () => void; onChange: (code: string) => void; onBreakpoint: (line: number) => void;
  onCursor: (line: number, column: number) => void; onShortcut: (event: KeyboardEvent) => void;
}) {
  const editor = useRef<HTMLTextAreaElement>(null), container = useRef<HTMLDivElement>(null), popup = useRef<HTMLDivElement>(null), mirror = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(), syntaxCache = useRef<PythonSyntaxCache>();
  const rightClickSelection = useRef<{ start: number; end: number } | null>(null), active = useRef(true), currentCode = useRef(code), currentDocumentKey = useRef(documentKey);
  currentCode.current = code; currentDocumentKey.current = documentKey;
  const [completion, setCompletion] = useState<PythonCompletion | null>(null), [choice, setChoice] = useState(0);
  const [anchor, setAnchor] = useState({ left: 65, top: 12, width: 340 });
  const [viewport, setViewport] = useState({ top: 0, left: 0, height: 400 });
  const [menu, setMenu] = useState<EditorMenu | null>(null), [clipboardPending, setClipboardPending] = useState(false), [clipboardStatus, setClipboardStatus] = useState("");
  const base = useMemo(() => pythonBaseSuggestions(PYTHON_TEMPLATES), []), deferredCode = useDeferredValue(code), highlightingPending = deferredCode !== code;
  const symbols = useMemo(() => pythonSymbols(deferredCode), [deferredCode]), nets = useMemo(() => pythonBoardNets(workspace), [workspace]);
  const syntax = useMemo(() => { syntaxCache.current = updatePythonSyntaxCache(syntaxCache.current, deferredCode); return syntaxCache.current; }, [deferredCode]);
  const lineCount = code.split("\n").length, firstLine = Math.max(1, Math.floor(viewport.top / LINE_HEIGHT) - 3), lastLine = Math.min(lineCount, firstLine + Math.ceil(viewport.height / LINE_HEIGHT) + 8);
  const windowed = pythonHighlightWindow(syntax, firstLine, lastLine);
  const reportCursor = (source = code, offset = editor.current?.selectionStart ?? 0) => { const preceding = source.slice(0, offset).split("\n"); onCursor(preceding.length, preceding[preceding.length - 1].length + 1); };
  const apply = (edit: PythonEditorEdit) => {
    if (byteLength(edit.code) > PYTHON_CODE_LIMIT) { setClipboardStatus("Edit exceeds the 512 KB script limit."); reportCursor(); return false; }
    onChange(edit.code); setCompletion(null);
    requestAnimationFrame(() => { const element = editor.current; if (!element) return; element.focus(); element.setSelectionRange(edit.start, edit.end); reportCursor(edit.code, edit.start); });
    return true;
  };
  const restoreSelection = (start: number, end: number) => requestAnimationFrame(() => { const element = editor.current; if (!element) return; element.focus({ preventScroll: true }); element.setSelectionRange(start, end); reportCursor(code, start); });
  const place = () => {
    const element = editor.current, root = container.current, measuring = mirror.current; if (!element || !root || !measuring) return;
    const style = getComputedStyle(element); Object.assign(measuring.style, { font: style.font, letterSpacing: style.letterSpacing, lineHeight: style.lineHeight, padding: style.padding, tabSize: style.tabSize });
    measuring.textContent = element.value.slice(0, element.selectionStart); const marker = document.createElement("span"); marker.textContent = "\u200b"; measuring.appendChild(marker);
    const point = marker.getBoundingClientRect(), bounds = measuring.getBoundingClientRect(), editorLeft = element.parentElement?.offsetLeft ?? element.offsetLeft;
    const x = editorLeft + point.left - bounds.left - element.scrollLeft, y = point.top - bounds.top - element.scrollTop;
    const width = Math.min(380, Math.max(180, root.clientWidth - editorLeft - 8)), popupHeight = Math.min(300, Math.max(110, root.clientHeight - 16));
    setAnchor({ left: Math.min(Math.max(editorLeft + 4, x), Math.max(editorLeft + 4, root.clientWidth - width - 4)), top: Math.max(4, y + 20 + popupHeight > root.clientHeight ? y - popupHeight : y + 20), width });
  };
  const suggest = (value = editor.current?.value ?? code, explicit = false) => {
    const element = editor.current; if (!element || locked || clipboardPending || element.selectionStart !== element.selectionEnd) { setCompletion(null); return; }
    const found = pythonCompletion(value, element.selectionStart, base, symbols, nets, workspace, explicit); setCompletion(found?.items.length ? found : null); setChoice(0); place();
  };
  const accept = (index: number) => {
    if (!completion || locked || clipboardPending) return;
    const replacement = applyPythonCompletion(code, completion, completion.items[index]); clearTimeout(timer.current);
    apply({ code: replacement.code, start: replacement.selection?.start ?? replacement.caret, end: replacement.selection?.end ?? replacement.caret });
  };
  const openMenu = (x: number, y: number) => { const element = editor.current; if (!element) return; const selection = rightClickSelection.current ?? { start: element.selectionStart, end: element.selectionEnd }; rightClickSelection.current = null; setCompletion(null); setMenu({ x, y, ...selection }); };
  const trigger = contextMenuTrigger(openMenu), isCurrent = (snapshot: string, snapshotKey: string | undefined) => active.current && currentDocumentKey.current === snapshotKey && currentCode.current === snapshot && editor.current?.value === snapshot;
  const failureStatus = (label: string, result: Exclude<BoundedClipboardResult<unknown>, { status: "ok" }>) => result.status === "stale" ? `${label} cancelled: the script changed before clipboard access completed.` : result.status === "timeout" ? `${label} failed: clipboard did not respond within ${EDITOR_CLIPBOARD_TIMEOUT_MS / 1_000} seconds.` : `${label} failed: ${clipboardError(result.error)}`;
  const finishFailure = (label: string, result: Exclude<BoundedClipboardResult<unknown>, { status: "ok" }>, snapshot: string, snapshotKey: string | undefined, selection: EditorMenu) => { if (!active.current) return; setClipboardStatus(failureStatus(label, result)); if (result.status !== "stale" && isCurrent(snapshot, snapshotKey)) restoreSelection(selection.start, selection.end); };
  const copy = (selection: EditorMenu) => void (async () => {
    const snapshot = code, snapshotKey = documentKey; setClipboardPending(true); setClipboardStatus("");
    const result = await boundedClipboardOperation(async () => { if (!navigator.clipboard?.writeText) throw new Error("Clipboard access is unavailable."); await navigator.clipboard.writeText(snapshot.slice(selection.start, selection.end)); }, () => isCurrent(snapshot, snapshotKey));
    if (result.status === "ok") { if (active.current) { setClipboardStatus("Copied selected Python source."); restoreSelection(selection.start, selection.end); } } else finishFailure("Copy", result, snapshot, snapshotKey, selection); if (active.current) setClipboardPending(false);
  })();
  const cut = (selection: EditorMenu) => void (async () => {
    const snapshot = code, snapshotKey = documentKey; setClipboardPending(true); setClipboardStatus("");
    const result = await boundedClipboardOperation(async () => { if (!navigator.clipboard?.writeText) throw new Error("Clipboard access is unavailable."); await navigator.clipboard.writeText(snapshot.slice(selection.start, selection.end)); }, () => isCurrent(snapshot, snapshotKey));
    if (result.status === "ok") { apply({ code: snapshot.slice(0, selection.start) + snapshot.slice(selection.end), start: selection.start, end: selection.start }); setClipboardStatus("Cut selected Python source."); } else finishFailure("Cut", result, snapshot, snapshotKey, selection); if (active.current) setClipboardPending(false);
  })();
  const paste = (selection: EditorMenu) => void (async () => {
    const snapshot = code, snapshotKey = documentKey; setClipboardPending(true); setClipboardStatus("");
    const result = await boundedClipboardOperation(async () => { if (!navigator.clipboard?.readText) throw new Error("Clipboard access is unavailable."); return navigator.clipboard.readText(); }, () => isCurrent(snapshot, snapshotKey));
    if (result.status === "ok") { const caret = selection.start + result.value.length; if (apply({ code: snapshot.slice(0, selection.start) + result.value + snapshot.slice(selection.end), start: caret, end: caret })) setClipboardStatus("Pasted Python source."); } else finishFailure("Paste", result, snapshot, snapshotKey, selection); if (active.current) setClipboardPending(false);
  })();
  useEffect(() => { const element = editor.current; if (!element || !insertion || locked) return; const start = element.selectionStart, end = element.selectionEnd; apply({ code: code.slice(0, start) + insertion.text + code.slice(end), start: start + insertion.text.length, end: start + insertion.text.length }); onInserted?.(); }, [insertion?.revision]);
  useEffect(() => { const element = editor.current; if (!element) return; const update = () => setViewport(current => ({ ...current, height: element.clientHeight })); update(); const observer = new ResizeObserver(update); observer.observe(element); return () => observer.disconnect(); }, []);
  useEffect(() => { active.current = true; return () => { active.current = false; clearTimeout(timer.current); }; }, []);
  useEffect(() => { if (locked) { clearTimeout(timer.current); setCompletion(null); } }, [locked]);
  useEffect(() => { clearTimeout(timer.current); setCompletion(null); }, [workspace]);
  useEffect(() => { popup.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" }); }, [choice]);
  useEffect(() => { const element = editor.current; if (!element || !focusLine) return; const lines = code.split("\n"), offset = lines.slice(0, focusLine.line - 1).reduce((sum, line) => sum + line.length + 1, 0); element.focus(); element.selectionStart = element.selectionEnd = offset; element.scrollTop = Math.max(0, (focusLine.line - 1) * LINE_HEIGHT - element.clientHeight / 3); setViewport(current => ({ ...current, top: element.scrollTop })); }, [focusLine?.revision]);
  const locallyReadOnly = locked || clipboardPending;
  return <div ref={container} className={`python-code-editor ${highlightingPending ? "highlight-pending" : ""} ${locked ? "read-only" : ""} ${clipboardPending ? "clipboard-pending" : ""}`} aria-busy={clipboardPending}>
    <div ref={mirror} className="python-caret-mirror" aria-hidden="true" />
    <div className="python-line-gutter" aria-label="Breakpoint gutter"><div style={{ transform: `translateY(${12 + (firstLine - 1) * LINE_HEIGHT - viewport.top}px)` }}>{Array.from({ length: Math.max(0, lastLine - firstLine + 1) }, (_, index) => firstLine + index).map(line => <button key={line} type="button" className={`${breakpoints.includes(line) ? "has-breakpoint" : ""} ${executionLine === line ? "execution-line" : ""}`} aria-label={`${breakpoints.includes(line) ? "Remove" : "Add"} breakpoint at line ${line}`} aria-pressed={breakpoints.includes(line)} onClick={() => onBreakpoint(line)} title={`Line ${line} · Click to toggle breakpoint`}><span>{executionLine === line ? "➜" : breakpoints.includes(line) ? "●" : ""}</span>{line}</button>)}</div></div>
    <div className="python-editor-surface"><div className="python-syntax-layer" aria-hidden="true"><div className="python-syntax-window" style={{ transform: `translate(${-viewport.left}px, ${12 + (windowed.firstLine - 1) * LINE_HEIGHT - viewport.top}px)` }}>{windowed.entries.map((entry, index) => <HighlightedLine entry={entry} key={windowed.firstLine + index} />)}</div></div>
      <textarea ref={editor} aria-label="Python script editor" aria-autocomplete="list" aria-controls={completion ? "python-suggestions" : undefined} aria-expanded={Boolean(completion)} aria-activedescendant={completion ? `python-suggestion-${choice}` : undefined} value={code} spellCheck={false} wrap="off" readOnly={locallyReadOnly}
        onPointerDown={event => { if (event.button === 2) rightClickSelection.current = { start: event.currentTarget.selectionStart, end: event.currentTarget.selectionEnd }; }} onContextMenu={trigger.onContextMenu}
        onChange={event => { const value = event.target.value; onChange(value); reportCursor(value, event.target.selectionStart); setCompletion(null); clearTimeout(timer.current); timer.current = setTimeout(() => suggest(value), 70); }} onBlur={() => { clearTimeout(timer.current); setCompletion(null); }} onClick={() => { clearTimeout(timer.current); setCompletion(null); reportCursor(); }} onSelect={() => reportCursor()}
        onScroll={event => { clearTimeout(timer.current); setViewport({ top: event.currentTarget.scrollTop, left: event.currentTarget.scrollLeft, height: event.currentTarget.clientHeight }); setCompletion(null); }} onKeyDown={event => {
          trigger.onKeyDown(event); if (event.defaultPrevented) return; if (["Escape", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) clearTimeout(timer.current);
          if (!locallyReadOnly && (event.ctrlKey || event.metaKey) && event.code === "Space") { event.preventDefault(); event.stopPropagation(); suggest(code, true); return; }
          if (completion && !locallyReadOnly) { if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); event.stopPropagation(); setChoice(current => (current + (event.key === "ArrowDown" ? 1 : -1) + completion.items.length) % completion.items.length); return; } if (event.key === "Tab" || event.key === "Enter") { event.preventDefault(); event.stopPropagation(); accept(choice); return; } if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setCompletion(null); return; } }
          onShortcut(event); if (event.defaultPrevented || locallyReadOnly) return; const start = event.currentTarget.selectionStart, end = event.currentTarget.selectionEnd;
          if (event.key === "Tab") { event.preventDefault(); apply(indentPythonSelection(code, start, end, event.shiftKey)); } else if (event.key === "Enter") { event.preventDefault(); apply(insertPythonNewline(code, start, end)); } else if ((event.ctrlKey || event.metaKey) && event.key === "/") { event.preventDefault(); apply(togglePythonComment(code, start, end)); }
        }} />
    </div>
    {completion && <div className="python-completion-popup" style={{ ...anchor, maxHeight: Math.max(100, Math.min(300, viewport.height - 8)) }} onPointerDown={event => event.preventDefault()}><div ref={popup} id="python-suggestions" role="listbox" aria-label="Python suggestions">{completion.items.map((item, index) => <button type="button" role="option" id={`python-suggestion-${index}`} key={`${item.label}:${index}`} aria-selected={choice === index} tabIndex={-1} onMouseEnter={() => setChoice(index)} onClick={() => accept(index)}><small>{item.kind}</small><span>{item.label}</span>{item.kind === "net" && <em>{item.detail}</em>}</button>)}</div><div className="python-completion-detail"><span>{completion.items[choice]?.detail}</span><small>↑ ↓ choose · Tab / Enter insert · Esc dismiss</small></div></div>}
    <span className="python-editor-status" role="status" aria-live="polite">{clipboardStatus}</span>
    {menu && <ActionContextMenu x={menu.x} y={menu.y} title="Python editor" onClose={() => setMenu(null)} actions={[{ label: "Cut", disabled: locked || clipboardPending || menu.start === menu.end, run: () => cut(menu) }, { label: "Copy", disabled: clipboardPending || menu.start === menu.end, run: () => copy(menu) }, { label: "Paste", disabled: locked || clipboardPending, run: () => paste(menu) }, { label: "Select all", run: () => restoreSelection(0, code.length) }, { label: "Indent", disabled: locked || clipboardPending, run: () => apply(indentPythonSelection(code, menu.start, menu.end)) }, { label: "Dedent", disabled: locked || clipboardPending, run: () => apply(indentPythonSelection(code, menu.start, menu.end, true)) }, { label: "Toggle comment", disabled: locked || clipboardPending, run: () => apply(togglePythonComment(code, menu.start, menu.end)) }]} />}
  </div>;
}
