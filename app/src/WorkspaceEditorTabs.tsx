// SPDX-License-Identifier: Apache-2.0
import { CircuitBoard, FilePenLine } from "./icons";
import type { FocusToolPanel } from "./FocusToolDeck";
import "./buttonStandard.css";
import "./WorkspaceEditorTabs.css";

// Spatial inspectors stay next to geometry. Forms and editors get a document.
const inspectors = new Set(["leftOpen", "rightOpen", "studyNavigatorOpen", "bottomOpen", "resourceOpen", "layersOpen", "assemblyHandlingExpanded", "resultVisualizerOpen", "emResultManagerOpen", "searchQuery"]);
export function workspaceEditorPanels(panels: readonly FocusToolPanel[]): FocusToolPanel[] {
  return panels.map(panel => ({...panel, presentation: inspectors.has(panel.id) ? "panel" : "document"}));
}

export default function WorkspaceEditorTabs({panels, activeId, onActivate}: {
  panels: readonly FocusToolPanel[];
  activeId: string | null;
  onActivate: (id: string | null) => void;
}) {
  const documents = panels.filter(panel => panel.open && panel.presentation === "document");
  if (!documents.length) return null;
  const active = documents.find(panel => panel.id === activeId || panel.aliases?.includes(activeId ?? ""));
  return <nav className="workspace-editor-tabs" aria-label="Workspace editors">
    <div role="tablist" aria-label="Board and editors" onKeyDown={event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
      const index = buttons.indexOf(event.target as HTMLButtonElement); if (index < 0) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
      buttons[next]?.focus(); buttons[next]?.click();
    }}>
      <button type="button" role="tab" aria-controls="workspace-board-content" aria-selected={!active} tabIndex={active ? -1 : 0} onClick={() => onActivate(null)} title="Return to board and result views; retain editor drafts"><CircuitBoard size={14}/><span>Board & results</span></button>
      {documents.map(panel => <button key={panel.id} type="button" role="tab" aria-controls={`workspace-editor-panel-${panel.id}`} aria-selected={active?.id === panel.id} tabIndex={active?.id === panel.id ? 0 : -1} onClick={() => onActivate(panel.id)} title={panel.title}><FilePenLine size={14}/><span>{panel.title}</span></button>)}
    </div>
  </nav>;
}
