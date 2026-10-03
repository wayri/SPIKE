// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

export default function PythonCodeEditor({ code, breakpoints, executionLine, locked, focusLine, onChange, onBreakpoint, onCursor, onShortcut }: {
  code: string; breakpoints: number[]; executionLine?: number; locked: boolean;
  focusLine?: { line: number; revision: number };
  onChange: (code: string) => void; onBreakpoint: (line: number) => void;
  onCursor: (line: number, column: number) => void; onShortcut: (event: KeyboardEvent) => void;
}) {
  const editor = useRef<HTMLTextAreaElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [height, setHeight] = useState(400);
  const lineCount = code.split("\n").length;
  const firstLine = Math.max(1, Math.floor(scrollTop / 18) - 3);
  const lastLine = Math.min(lineCount, firstLine + Math.ceil(height / 18) + 8);
  useEffect(() => {
    const element = editor.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setHeight(element.clientHeight));
    observer.observe(element); return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const element = editor.current;
    if (!element || !focusLine) return;
    const lines = code.split("\n");
    const offset = lines.slice(0, focusLine.line - 1).reduce((sum, line) => sum + line.length + 1, 0);
    element.focus(); element.selectionStart = element.selectionEnd = offset;
    element.scrollTop = Math.max(0, (focusLine.line - 1) * 18 - element.clientHeight / 3);
    setScrollTop(element.scrollTop);
  }, [focusLine?.revision]);
  const cursor = () => {
    const element = editor.current;
    if (!element) return;
    const preceding = code.slice(0, element.selectionStart).split("\n");
    onCursor(preceding.length, preceding[preceding.length - 1].length + 1);
  };
  return <div className="python-code-editor">
    <div className="python-line-gutter" aria-label="Breakpoint gutter">
      <div style={{ transform: `translateY(${12 + (firstLine - 1) * 18 - scrollTop}px)` }}>
        {Array.from({ length: Math.max(0, lastLine - firstLine + 1) }, (_, index) => firstLine + index).map(line => <button key={line} type="button" className={`${breakpoints.includes(line) ? "has-breakpoint" : ""} ${executionLine === line ? "execution-line" : ""}`} aria-label={`${breakpoints.includes(line) ? "Remove" : "Add"} breakpoint at line ${line}`} aria-pressed={breakpoints.includes(line)} onClick={() => onBreakpoint(line)} title={`Line ${line} · Click to toggle breakpoint`}><span>{executionLine === line ? "➜" : breakpoints.includes(line) ? "●" : ""}</span>{line}</button>)}
      </div>
    </div>
    <textarea ref={editor} aria-label="Python script editor" value={code} spellCheck={false} wrap="off" readOnly={locked} onChange={event => onChange(event.target.value)} onSelect={cursor} onScroll={event => setScrollTop(event.currentTarget.scrollTop)} onKeyDown={event => {
      onShortcut(event);
      if (event.defaultPrevented || locked) return;
      if (event.key === "Tab") {
        event.preventDefault();
        const element = event.currentTarget, start = element.selectionStart, end = element.selectionEnd;
        onChange(`${code.slice(0, start)}    ${code.slice(end)}`);
        requestAnimationFrame(() => { element.selectionStart = element.selectionEnd = start + 4; cursor(); });
      }
    }} />
  </div>;
}
