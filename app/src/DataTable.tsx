// SPDX-License-Identifier: Apache-2.0
import { useId, useMemo, useRef, useState, type TableHTMLAttributes } from "react";
import { matchTableRows, renderTableBodies, tablePage, tableRowGroups } from "./dataTableModel";
import { onSpreadsheetKeyDown } from "./spreadsheetGrid";
import "./DataTable.css";

export type DataTableTheme = "professional-dark" | "light" | "high-contrast" | "system";
export type DataTableProps = TableHTMLAttributes<HTMLTableElement> & {
  label: string;
  showLabel?: boolean;
  searchable?: boolean;
  pageSize?: number;
  emptyMessage?: string;
  theme?: DataTableTheme;
};

/** Presentation only: validation, units, row identity and writes stay in each editor. */
export default function DataTable({ label, children, className = "", showLabel = true, searchable = true, pageSize = 100,
  emptyMessage = "No rows to display.", theme, onKeyDown, onFocusCapture, onBlurCapture, ...tableProps }: DataTableProps) {
  const [query, setQuery] = useState("");
  const [compact, setCompact] = useState(false);
  const [page, setPage] = useState(0);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const search = useRef<HTMLInputElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const id = useId();
  const groups = useMemo(() => tableRowGroups(children), [children]);
  const matches = useMemo(() => matchTableRows(groups, searchable ? query : "", activeKey), [groups, query, searchable, activeKey]);
  const view = tablePage(matches, page, pageSize);
  const changePage = (next: number) => {
    setActiveKey(null); setPage(next);
    if (viewport.current) viewport.current.scrollTop = 0;
  };
  return <div className={`spike-data-table${compact ? " spike-table-compact" : ""}`} data-table-theme={theme}>
    <div className="spike-table-toolbar" role="group" aria-label={`${label} table tools`}>
      {showLabel && <strong title={label}>{label}</strong>}
      {searchable && <input ref={search} className="spike-table-search" type="search" aria-label={`Find in ${label}`} placeholder="Find rows..." title="Match all words across a row. Use quotes for an exact phrase." value={query}
        onChange={event => { setQuery(event.target.value); setPage(0); setActiveKey(null); }} />}
      {searchable && query && <button type="button" onClick={() => { setQuery(""); setPage(0); search.current?.focus(); }}>Clear</button>}
      <span className="spike-table-count" role="status">{query && searchable ? `${matches.length} of ${groups.length}` : groups.length} rows</span>
      <button type="button" aria-pressed={compact} onClick={() => setCompact(value => !value)} title="Toggle compact row spacing">Compact</button>
      <details className="spike-table-help"><summary aria-label={`Keyboard help for ${label}`}>Help</summary>
        <p id={`${id}-keys`}>Tab / Shift+Tab: next / previous field. Enter / Shift+Enter: same column in the next / previous row. Alt+Arrow: move between cells. Arrow keys keep their normal editing behavior.</p>
      </details>
    </div>
    <div className="spike-table-field-guide" aria-label={`${label} field guide`}>
      <span><i className="spike-table-edit-cue" aria-hidden="true" />Editable</span>
      <span><i className="spike-table-choice-cue" aria-hidden="true" />Dropdown</span>
      <span><i className="spike-table-lock-cue" aria-hidden="true" />Read only / unavailable</span>
      <span><i className="spike-table-action-cue" aria-hidden="true">↗</i>Action</span>
    </div>
    <div ref={viewport} className="spike-table-viewport" role="region" aria-label={`${label} rows`} tabIndex={0}>
      <table {...tableProps} className={`spike-table ${className}`} aria-label={tableProps["aria-label"] ?? label}
        onFocusCapture={event => {
          const target = event.target as HTMLElement;
          if (target.closest("table") === event.currentTarget) setActiveKey(target.closest<HTMLTableRowElement>("tr[data-table-row]")?.dataset.tableRow ?? null);
          onFocusCapture?.(event);
        }}
        onBlurCapture={event => {
          if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) setActiveKey(null);
          onBlurCapture?.(event);
        }}
        onKeyDown={event => { onKeyDown?.(event); if (!event.defaultPrevented) onSpreadsheetKeyDown(event); }}>
        {renderTableBodies(children, view.rows)}
      </table>
      {!matches.length && <p className="spike-table-empty">{groups.length ? "No matching rows. Clear the search to see all rows." : emptyMessage}</p>}
    </div>
    {view.pages > 1 && <nav className="spike-table-pagination" aria-label={`${label} pages`}>
      <span>{view.start + 1}-{view.start + view.rows.length} of {matches.length} rows</span>
      <button type="button" disabled={view.page === 0} onClick={() => changePage(0)}>First</button>
      <button type="button" disabled={view.page === 0} onClick={() => changePage(view.page - 1)}>Previous</button>
      <span>Page {view.page + 1} of {view.pages}</span>
      <button type="button" disabled={view.page + 1 === view.pages} onClick={() => changePage(view.page + 1)}>Next</button>
      <button type="button" disabled={view.page + 1 === view.pages} onClick={() => changePage(view.pages - 1)}>Last</button>
    </nav>}
  </div>;
}
