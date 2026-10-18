import { liveControlSearch } from "./liveControlSearch";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Search, X, SlidersHorizontal, MousePointer2 } from "./icons";
import type { LucideIcon } from "./icons";
import { normalizeSearchText, scoreUniversalSearchItem } from "./universalSearchModel";
import { searchableFocusCommands, type FocusCommand } from "./focusCommands";
import { emptySearchPreferences, frequentSearchActionIds, loadSearchPreferences, recentSearchActionIds, recordSearchAction, searchPreferenceRank, toggleSearchPin } from "./searchPreferences";
import "./UniversalSearch.css";

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
  const [preferences, setPreferences] = useState(emptySearchPreferences);
  const [summaryMode, setSummaryMode] = useState<"recent" | "frequent">("recent");
  const [busyIds, setBusyIds] = useState<Set<string>>(() => new Set());
  const pendingActions = useRef(new Set<string>());
  useEffect(() => {
    if (!open) { setLiveItems([]); return; }
    setError("");
    const documents = searchDocuments?.() ?? (typeof document === "undefined" ? [] : [document]);
    setLiveItems(documents.flatMap(owner => liveControlSearch(owner, onRevealPanel)).map(item => ({...item, icon:item.kind === "field" ? SlidersHorizontal : MousePointer2})));
  }, [open]);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const commandItems = useMemo<UniversalSearchItem[]>(() => searchableFocusCommands(commands).map(command => ({ ...command, icon: command.icon as LucideIcon | undefined })), [commands]);
  const storage = () => { try { return typeof localStorage === "undefined" ? null : localStorage; } catch { return null; } };
  const results = useMemo(() => {
    const seen = new Set<string>();
    const term = normalizeSearchText(query);
    return [...(suggestCommands?.(query) ?? []), ...items, ...commandItems, ...liveItems]
    .map((item, index) => { const rank = scoreUniversalSearchItem(item, query); return { item: item.completion || !term || !normalizeSearchText(item.label).startsWith(term) ? item : { ...item, completion: item.label }, index,
      rank, tier: rank >= 1000 ? 4 : rank >= 850 ? 3 : rank >= 700 ? 2 : 1, preference: searchPreferenceRank(preferences, item.id) }; })
    .filter(entry => entry.rank > 0)
    .sort((a, b) => query.trim()
      ? b.tier - a.tier || b.rank + b.preference - a.rank - a.preference || a.item.category.localeCompare(b.item.category) || a.item.label.localeCompare(b.item.label)
      : Number(preferences.pins.includes(b.item.id)) - Number(preferences.pins.includes(a.item.id)) || b.preference - a.preference || a.index - b.index)
    .map(entry => entry.item)
    .filter(item => { const identity = `${item.category}\u0000${item.label}`.toLocaleLowerCase(); if (seen.has(identity)) return false; seen.add(identity); return true; })
    .slice(0, query.trim() ? 60 : 18);
  }, [items, commandItems, liveItems, query, suggestCommands, preferences]);

  const availableById = useMemo(() => new Map([...(suggestCommands?.("") ?? []), ...items, ...commandItems, ...liveItems].map(item => [item.id, item])), [items, commandItems, liveItems, suggestCommands]);
  const recent = useMemo(() => recentSearchActionIds(preferences).flatMap(id => availableById.get(id) ?? []), [preferences, availableById]);
  const frequent = useMemo(() => frequentSearchActionIds(preferences).flatMap(id => availableById.get(id) ?? []), [preferences, availableById]);
  const summaryItems = summaryMode === "recent" ? recent : frequent;

  useEffect(() => {
    if (!open) return;
    setPreferences(loadSearchPreferences(storage()));
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
    if (!item || item.disabled || pendingActions.current.has(item.id)) return;
    try {
      const result = item.run();
      const complete = () => { pendingActions.current.delete(item.id); setBusyIds(current => { const next = new Set(current); next.delete(item.id); return next; }); setPreferences(current => recordSearchAction(current, item.id, Date.now(), storage())); onClose(); };
      if (result && typeof result.then === "function") {
        pendingActions.current.add(item.id);
        setBusyIds(current => new Set(current).add(item.id));
        void result.then(complete).catch(cause => { pendingActions.current.delete(item.id); setBusyIds(current => { const next = new Set(current); next.delete(item.id); return next; }); setError(String(cause)); });
      }
      else complete();
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
        <div className="universal-search-summary" aria-label="Recent and most used search actions">
          {!query.trim() && (recent.length > 0 || frequent.length > 0) && <><span className="universal-search-summary-modes"><button aria-pressed={summaryMode === "recent"} onClick={() => setSummaryMode("recent")}>Recent</button><button aria-pressed={summaryMode === "frequent"} onClick={() => setSummaryMode("frequent")}>Most used</button></span>
          {summaryItems.map(item => <button key={`${summaryMode}:${item.id}`} disabled={busyIds.has(item.id)} onClick={() => execute(item)} title={item.label}>{item.label}</button>)}</>}
        </div>
        <div id="universal-search-results" className="universal-search-list" role="listbox">
          {results.map((item, index) => {
            const Icon = item.icon ?? Search;
            const pinned = preferences.pins.includes(item.id);
            return <div key={item.id} className={`universal-search-row${index === activeIndex ? " active" : ""}`} role="presentation" onMouseEnter={() => setActiveIndex(index)}>
              <button disabled={item.disabled || busyIds.has(item.id)} role="option" aria-selected={index === activeIndex} onClick={() => execute(item)}>
                <Icon size={15} />
                <span><b>{item.label}</b><small>{item.description ?? item.category}</small></span>
                <em>{item.category}</em>
                {item.shortcut ? <kbd>{item.shortcut}</kbd> : <ArrowRight size={13} />}
              </button>
              <button className="universal-search-pin" aria-label={`${pinned ? "Unpin" : "Pin"} ${item.label}`} aria-pressed={pinned} onClick={() => setPreferences(current => toggleSearchPin(current, item.id, storage()))}>{pinned ? "Pinned" : "Pin"}</button>
            </div>;
          })}
          {!results.length && <div className="universal-search-empty"><Search size={20} /><b>No matching command or design object</b><span>Try “run PI on net …”, “focus part …”, “show layer …”, or a tool name.</span></div>}
        </div>
        {active && <footer><span>{active.category}</span><b>{active.label}</b><small>{active.description ?? "Press Enter to open"}</small></footer>}
      </div>
      <div className="universal-search-hints"><span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span><span><kbd>Tab</kbd> Complete</span><span><kbd>Enter</kbd> Execute</span><span><kbd>Ctrl</kbd><kbd>K</kbd> Search</span></div>
    </section>
  </div>;
}
