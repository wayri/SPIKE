// SPDX-License-Identifier: Apache-2.0
import type { KeyboardEvent } from "react";
import { ShieldAlert, Table2, Network, Activity, Bell, Minus, Maximize2, Minimize2 } from "./icons";
import type { DockTabId } from "./workspaceState";
import "./buttonStandard.css";
export const dockTabs: readonly DockTabId[] = ["Issues", "Probe table", "Power tree", "Console", "Notifications"];
export type DockPanelView = { height: number; maximized: boolean };
export type DockPanelViews = Partial<Record<DockTabId, DockPanelView>>;
export function hydrateDockViews(raw: unknown): DockPanelViews {
  if (!raw || typeof raw !== "object") return {};
  const result: DockPanelViews = {};
  for (const tab of dockTabs) {
    const row = (raw as Record<string, unknown>)[tab];
    if (!row || typeof row !== "object") continue;
    const value = row as Record<string, unknown>;
    if (typeof value.height === "number" && Number.isFinite(value.height)) result[tab] = { height: Math.max(120, Math.min(600, value.height)), maximized: value.maximized === true };
  }
  return result;
}
export function adjacentDockTab(current: DockTabId, key: string): DockTabId | null {
  const index = dockTabs.indexOf(current);
  if (key === "Home") return dockTabs[0];
  if (key === "End") return dockTabs[dockTabs.length - 1];
  if (key === "ArrowLeft" || key === "ArrowRight") return dockTabs[(index + (key === "ArrowLeft" ? -1 : 1) + dockTabs.length) % dockTabs.length];
  return null;
}
const icons = { Issues: ShieldAlert, "Probe table": Table2, "Power tree": Network, Console: Activity, Notifications: Bell };
export function WorkspaceDockTabs({ active, open, counts, onOpen }: { active: DockTabId; open: boolean; counts: Partial<Record<DockTabId, number>>; onOpen: (tab: DockTabId) => void }) {
  const navigate = (event: KeyboardEvent<HTMLButtonElement>, tab: DockTabId) => {
    const next = adjacentDockTab(tab, event.key);
    if (!next) return;
    event.preventDefault(); event.stopPropagation(); onOpen(next);
    document.getElementById(`dock-tab-${next.replace(/ /g, "-")}`)?.focus();
  };
  return <div className="workspace-dock-tabs" role="tablist" aria-label="Workspace panels">{dockTabs.map(tab => {
    const Icon = icons[tab], selected = open && active === tab;
    return <button type="button" role="tab" id={`dock-tab-${tab.replace(/ /g, "-")}`} key={tab} aria-selected={selected}
      aria-controls="workspace-dock-panel" tabIndex={active === tab ? 0 : -1} title={selected ? `${tab} is open; use Minimize in its header to hide it` : `Restore ${tab}`}
      className={selected ? "selected" : ""} onClick={() => onOpen(tab)} onKeyDown={event => navigate(event, tab)}><Icon size={14} /><span>{tab}</span>{Boolean(counts[tab]) && <b>{counts[tab]}</b>}</button>;
  })}</div>;
}
export function WorkspaceDockHeader({ title, maximized, onMinimize, onMaximize }: { title: DockTabId; maximized: boolean; onMinimize: () => void; onMaximize: () => void }) {
  return <header className="workspace-dock-header"><strong>{title}</strong><span className="workspace-dock-actions">
    <button type="button" className="spike-control--compact" aria-label={`Minimize ${title}`} title={`Minimize ${title} to the tool taskbar`} onClick={onMinimize}><Minus size={14} /><span>Minimize</span></button>
    <button type="button" className="spike-control--compact" aria-label={`${maximized ? "Restore size of" : "Maximize"} ${title}`} title={maximized ? "Restore this panel to its previous size" : "Fill the workspace with this panel"} onClick={onMaximize}>{maximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}<span>{maximized ? "Restore size" : "Maximize"}</span></button>
  </span></header>;
}
