// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import { filterViewportNets, type ViewportNetRow } from "./viewportNetViewerModel";
import { minimizeTool, removeMinimizedTool } from "./minimizedTools";
import { ExpandControlIcon as ChevronDown, CollapseControlIcon as ChevronUp, HideControlIcon as EyeOff } from "./navigationIcons";
import "./buttonStandard.css";
import "./viewportNetViewer.css";

type Props = { boardKey: string; boardName: string; rows: readonly ViewportNetRow[]; assembly: boolean; available: boolean;
  selectedIds: readonly string[]; selectedName?: string | null; onSelect: (row: ViewportNetRow) => void };

export default function ViewportNetViewer({ boardKey, boardName, rows, assembly, available, selectedIds, selectedName, onSelect }: Props) {
  const [expanded, setExpanded] = useState(true);
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(100);
  const [collapsed, setCollapsed] = useState(false);
  const shelfId = "viewport-board-nets";
  const label = assembly ? boardName : "Board nets";
  useEffect(() => { setQuery(""); setLimit(100); }, [boardKey]);
  useEffect(() => () => removeMinimizedTool(shelfId), []);
  useEffect(() => {
    if (!expanded) minimizeTool({ id: shelfId, label, restore: () => setExpanded(true) });
  }, [expanded, label]);
  const minimize = () => {
    if (minimizeTool({ id: shelfId, label, restore: () => setExpanded(true) })) setExpanded(false);
  };
  const filtered = useMemo(() => filterViewportNets(rows, query), [rows, query]);
  if (!expanded) return null;
  return <aside className={`viewport-net-viewer${collapsed ? " viewport-net-viewer--collapsed" : ""}`} aria-label="Board net viewer" onPointerDown={event => event.stopPropagation()} onWheel={event => event.stopPropagation()} onKeyDown={event => event.stopPropagation()}>
    <header><strong title={boardName}>{assembly ? boardName : "BOARD NETS"}</strong><div className="viewport-net-viewer__controls">
      <button type="button" className="spike-control--icon" aria-expanded={!collapsed} aria-label={collapsed ? "Expand net viewer" : "Collapse net viewer"} title={collapsed ? "Expand net viewer" : "Collapse net viewer"} onClick={() => setCollapsed(value => !value)}>{collapsed ? <ChevronDown size={14}/> : <ChevronUp size={14}/>}</button>
      <button type="button" className="spike-control--icon" aria-label="Hide net viewer" title="Hide net viewer; restore with Show hidden tools" onClick={minimize}><EyeOff size={14}/></button>
    </div></header>
    <div className="viewport-net-viewer__body" hidden={collapsed}>
      {assembly && <small className="viewport-net-viewer__scope" title={boardName}>{boardKey === "assembly:no-selection" ? "No board selected" : "Selected board"}</small>}
      <input type="search" aria-label="Search board nets" placeholder="Search nets, pins or layers" value={query} disabled={!available} onChange={event => { setQuery(event.target.value); setLimit(100); }} />
      <small className="viewport-net-viewer__count" role="status">{available ? `${filtered.length} / ${rows.length} nets` : assembly ? "Click a board in the viewport to view its nets." : "Board data unavailable"}</small>
      <div className="viewport-net-viewer__list" aria-label="Board nets">
        {filtered.slice(0, limit).map(row => <button key={row.id} type="button" disabled={assembly && !row.canonical} aria-pressed={assembly ? selectedIds.includes(row.id) : row.name === selectedName}
          title={`${row.name} · ${row.source} · ${row.layer}${assembly && !row.canonical ? " · Canonical net identity unavailable" : ""}`} onClick={() => onSelect(row)}>
          <strong>{row.name}</strong><small>{[row.source, row.layer].filter(Boolean).join(" · ")}</small>
        </button>)}
        {available && !filtered.length && <p>No matching nets</p>}
        {filtered.length > limit && <button type="button" className="viewport-net-viewer__more" onClick={() => setLimit(value => value + 100)}>Show more ({filtered.length - limit})</button>}
      </div>
    </div>
  </aside>;
}
