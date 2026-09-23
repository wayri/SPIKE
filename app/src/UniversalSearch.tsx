import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Search, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type UniversalSearchItem = {
  id: string;
  label: string;
  category: string;
  description?: string;
  keywords?: string;
  icon?: LucideIcon;
  disabled?: boolean;
  run: () => void;
};

type UniversalSearchProps = {
  open: boolean;
  items: UniversalSearchItem[];
  onClose: () => void;
};

function score(item: UniversalSearchItem, query: string) {
  if (!query) return item.disabled ? -1 : 1;
  const term = query.toLowerCase().trim();
  const label = item.label.toLowerCase();
  const category = item.category.toLowerCase();
  const description = item.description?.toLowerCase() ?? "";
  const keywords = item.keywords?.toLowerCase() ?? "";
  if (label === term) return 100;
  if (label.startsWith(term)) return 80;
  if (label.includes(term)) return 60;
  if (category.includes(term)) return 40;
  if (`${description} ${keywords}`.includes(term)) return 25;
  const tokens = term.split(/\s+/).filter(Boolean);
  return tokens.every(token => `${label} ${category} ${description} ${keywords}`.includes(token)) ? 15 : 0;
}

export default function UniversalSearch({ open, items, onClose }: UniversalSearchProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const results = useMemo(() => items
    .map((item, index) => ({ item, index, rank: score(item, query) }))
    .filter(entry => entry.rank > 0)
    .sort((a, b) => query.trim()
      ? b.rank - a.rank || a.item.category.localeCompare(b.item.category) || a.item.label.localeCompare(b.item.label)
      : a.index - b.index)
    .slice(0, query.trim() ? 40 : 14)
    .map(entry => entry.item), [items, query]);

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
    item.run();
    onClose();
  };
  const active = results[activeIndex];

  return <div className="universal-search-shade" role="presentation" onMouseDown={event => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <section className="universal-search-dialog" role="dialog" aria-modal="true" aria-label="Universal search">
      <div className="universal-search-input">
        <Search size={18} />
        <input
          ref={inputRef}
          value={query}
          onChange={event => setQuery(event.target.value)}
          onKeyDown={event => {
            if (event.key === "Escape") { event.preventDefault(); onClose(); }
            if (event.key === "ArrowDown") { event.preventDefault(); setActiveIndex(index => Math.min(results.length - 1, index + 1)); }
            if (event.key === "ArrowUp") { event.preventDefault(); setActiveIndex(index => Math.max(0, index - 1)); }
            if (event.key === "Enter") { event.preventDefault(); execute(active); }
          }}
          placeholder="Search commands, settings, nets, parts, pads, layers..."
          aria-label="Search all SPIKE commands and design objects"
          aria-controls="universal-search-results"
        />
        {query && <button onClick={() => setQuery("")} title="Clear search"><X size={14} /></button>}
        <kbd>ESC</kbd>
      </div>
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
              <ArrowRight size={13} />
            </button>;
          })}
          {!results.length && <div className="universal-search-empty"><Search size={20} /><b>No matching command or design object</b><span>Try a tool name, net, component reference, pad, layer, or setting.</span></div>}
        </div>
        {active && <footer><span>{active.category}</span><b>{active.label}</b><small>{active.description ?? "Press Enter to open"}</small></footer>}
      </div>
      <div className="universal-search-hints"><span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span><span><kbd>Enter</kbd> Open</span><span><kbd>Ctrl</kbd><kbd>K</kbd> Search</span></div>
    </section>
  </div>;
}
