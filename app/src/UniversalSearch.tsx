import { liveControlSearch } from "./liveControlSearch";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Search, X, SlidersHorizontal, MousePointer2 } from "./icons";
import type { LucideIcon } from "./icons";
import { scoreUniversalSearchItem } from "./universalSearchModel";
import { searchableFocusCommands, type FocusCommand } from "./focusCommands";

export type UniversalSearchItem = {
  id: string;
  label: string;
  category: string;
  description?: string;
  keywords?: string;
  icon?: LucideIcon;
  disabled?: boolean;
  completion?: string;
  shortcut?: string;
  run: () => void | Promise<void>;
};

type UniversalSearchProps = {
  open: boolean;
  items: UniversalSearchItem[];
  suggestCommands?: (query: string) => UniversalSearchItem[];
  commands?: readonly FocusCommand[];
  onClose: () => void;
  onRevealPanel?: (id: string) => void;
  searchDocuments?: () => readonly Document[];
};

export default function UniversalSearch({ open, items, suggestCommands, commands = [], onClose, onRevealPanel, searchDocuments }: UniversalSearchProps) {
  const [query, setQuery] = useState("");
  const [liveItems, setLiveItems] = useState<UniversalSearchItem[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open) { setLiveItems([]); return; }
    setError("");
    const documents = searchDocuments?.() ?? (typeof document === "undefined" ? [] : [document]);
    setLiveItems(documents.flatMap(owner => liveControlSearch(owner, onRevealPanel)).map(item => ({...item, icon:item.kind === "field" ? SlidersHorizontal : MousePointer2})));
  }, [open]);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const commandItems = useMemo<UniversalSearchItem[]>(() => searchableFocusCommands(commands).map(command => ({ ...command, icon: command.icon as LucideIcon | undefined })), [commands]);
  const results = useMemo(() => {
    const seen = new Set<string>();
    return [...(suggestCommands?.(query) ?? []), ...items, ...commandItems, ...liveItems]
    .map((item, index) => ({ item, index, rank: scoreUniversalSearchItem(item, query) }))
    .filter(entry => entry.rank > 0)
    .sort((a, b) => query.trim()
      ? b.rank - a.rank || a.item.category.localeCompare(b.item.category) || a.item.label.localeCompare(b.item.label)
      : a.index - b.index)
    .map(entry => entry.item)
    .filter(item => { const identity = `${item.category}\u0000${item.label}`.toLocaleLowerCase(); if (seen.has(identity)) return false; seen.add(identity); return true; })
    .slice(0, query.trim() ? 60 : 18);
  }, [items, commandItems, liveItems, query, suggestCommands]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActiveIndex(0);
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);
  useEffect(() => setActiveIndex(0), [query]);
  useEffect(() => {
    if (activeIndex < results.length) return;
    setActiveIndex(Math.max(0, results.length - 1));
  }, [activeIndex, results.length]);

  if (!open) return null;
  const execute = (item: UniversalSearchItem | undefined) => {
    if (!item || item.disabled) return;
    try {
      const result = item.run();
      if (result && typeof result.then === "function") void result.then(onClose).catch(cause => setError(String(cause)));
      else onClose();
    } catch (cause) { setError(String(cause)); }
  };
  const active = results[activeIndex];

  return <div className="universal-search-shade" role="presentation" onMouseDown={event => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <section className="universal-search-dialog" role="dialog" aria-modal="true" aria-label="Universal search">
      <div className="universal-search-input">
        <Search size={18} />
        <input
          maxLength={512}
          ref={inputRef}
          value={query}
          onChange={event => setQuery(event.target.value)}
          onKeyDown={event => {
            if (event.key === "Escape") { event.preventDefault(); onClose(); }
            if (event.key === "ArrowDown") { event.preventDefault(); setActiveIndex(index => Math.min(results.length - 1, index + 1)); }
            if (event.key === "ArrowUp") { event.preventDefault(); setActiveIndex(index => Math.max(0, index - 1)); }
            if (event.key === "Tab" && active?.completion) { event.preventDefault(); setQuery(active.completion); }
            if (event.key === "Enter") { event.preventDefault(); execute(active); }
          }}
          placeholder="Try: run PI on net netK-A1 · focus part R1 · show layer F.Cu"
          aria-label="Search all SPIKE commands and design objects"
          aria-controls="universal-search-results"
          aria-autocomplete="list"
        />
        {query && <button onClick={() => setQuery("")} title="Clear search"><X size={14} /></button>}
        <kbd>ESC</kbd>
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="universal-search-body">
        <div id="universal-search-results" className="universal-search-list" role="listbox">
          {results.map((item, index) => {
            const Icon = item.icon ?? Search;
            return <button
              key={item.id}
              className={index === activeIndex ? "active" : ""}
              disabled={item.disabled}
              role="option"
              aria-selected={index === activeIndex}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => execute(item)}
            >
              <Icon size={15} />
              <span><b>{item.label}</b><small>{item.description ?? item.category}</small></span>
              <em>{item.category}</em>
              {item.shortcut ? <kbd>{item.shortcut}</kbd> : <ArrowRight size={13} />}
            </button>;
          })}
          {!results.length && <div className="universal-search-empty"><Search size={20} /><b>No matching command or design object</b><span>Try “run PI on net …”, “focus part …”, “show layer …”, or a tool name.</span></div>}
        </div>
        {active && <footer><span>{active.category}</span><b>{active.label}</b><small>{active.description ?? "Press Enter to open"}</small></footer>}
      </div>
      <div className="universal-search-hints"><span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span><span><kbd>Tab</kbd> Complete</span><span><kbd>Enter</kbd> Execute</span><span><kbd>Ctrl</kbd><kbd>K</kbd> Search</span></div>
    </section>
  </div>;
}
