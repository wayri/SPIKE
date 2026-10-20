// SPDX-License-Identifier: Apache-2.0
import { useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Plus, Boxes } from "./icons";
import ActionContextMenu from "./ActionContextMenu";
import type { WorkspaceViewCandidate, WorkspaceViewDescriptor } from "./workspaceViewModel";
import "./buttonStandard.css";
import "./WorkspaceViewTabs.css";

export const workspaceViewShouldMount = (view: WorkspaceViewDescriptor, activeViewId: string | null) => view.detached || view.id === activeViewId;

function WorkspaceTab({ view, active, onActive, onClose, onDetach }: {
  view: WorkspaceViewDescriptor; active: boolean; onActive: () => void; onClose: () => void;
  onDetach: (point?: { x: number; y: number }) => void;
}) {
  const drag = useRef<{ id: number; startX: number; startY: number; moved: boolean } | null>(null);
  const pointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0 || !event.isPrimary) return;
    drag.current = { id: event.pointerId, startX: event.clientX, startY: event.clientY, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const pointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const state = drag.current; if (!state || state.id !== event.pointerId) return;
    state.moved ||= Math.hypot(event.clientX - state.startX, event.clientY - state.startY) > 8;
    event.currentTarget.classList.toggle("workspace-view-tab-dragging", state.moved);
  };
  const finish = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const state = drag.current; drag.current = null; event.currentTarget.classList.remove("workspace-view-tab-dragging");
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (state?.moved && (event.clientX < 0 || event.clientY < 0 || event.clientX > window.innerWidth || event.clientY > window.innerHeight)) onDetach({ x: event.screenX - 30, y: event.screenY - 20 });
  };
  const cancel = (event: ReactPointerEvent<HTMLButtonElement>) => { drag.current = null; event.currentTarget.classList.remove("workspace-view-tab-dragging"); if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); };
  return <div className="workspace-view-tab-wrap">
    <button type="button" role="tab" aria-selected={active} tabIndex={active ? 0 : -1} className={active ? "workspace-view-tab active" : "workspace-view-tab"}
      onClick={onActive} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={finish} onPointerCancel={cancel} onLostPointerCapture={cancel}
      title={`${view.title} · drag outside SPIKE to detach`}><span>{view.title}</span>{view.detached && <small>Window</small>}</button>
    <button type="button" className="workspace-view-tab-action" aria-label={`Detach ${view.title}`} disabled={view.detached} onClick={() => onDetach()}>↗</button>
    <button type="button" className="workspace-view-tab-action" aria-label={`Close ${view.title}`} onClick={onClose}>×</button>
  </div>;
}

export default function WorkspaceViewTabs({ views, activeViewId, candidates, onMain, onActive, onAdd, onClose, onDetach }: {
  views: readonly WorkspaceViewDescriptor[];
  activeViewId: string | null;
  candidates: readonly WorkspaceViewCandidate[];
  onMain: () => void;
  onActive: (viewId: string) => void;
  onAdd: (candidate: WorkspaceViewCandidate) => void;
  onClose: (viewId: string) => void;
  onDetach: (viewId: string, point?: { x: number; y: number }) => void;
}) {
  const [addAnchor, setAddAnchor] = useState<{x:number;y:number}|null>(null);
  const keyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault(); const ids: Array<string | null> = [null, ...views.map(view => view.id)];
    const current = Math.max(0, ids.findIndex(id => id === activeViewId));
    const next = event.key === "Home" ? 0 : event.key === "End" ? ids.length - 1 : (current + (event.key === "ArrowRight" ? 1 : -1) + ids.length) % ids.length;
    ids[next] === null ? onMain() : onActive(ids[next]!);
    event.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')[next]?.focus();
  };
  return <nav className="workspace-view-tabs" aria-label="Assembly views"><div role="tablist" onKeyDown={keyDown}><button type="button" role="tab" aria-selected={activeViewId === null} tabIndex={activeViewId === null ? 0 : -1} className={activeViewId === null ? "workspace-view-main-tab active" : "workspace-view-main-tab"} onClick={onMain}>Main assembly</button>{views.map(view => <WorkspaceTab key={view.id} view={view} active={view.id === activeViewId} onActive={() => onActive(view.id)} onClose={() => onClose(view.id)} onDetach={point => onDetach(view.id, point)}/>)}</div>
    <button type="button" className="workspace-view-add spike-control--icon" aria-label="Add assembly view" title="Add assembly view" aria-haspopup="menu" aria-expanded={Boolean(addAnchor)} disabled={!candidates.length} onClick={event=>{const rect=event.currentTarget.getBoundingClientRect();setAddAnchor(addAnchor?null:{x:rect.left,y:rect.bottom+4});}}><Plus size={15}/></button>
    {addAnchor && <ActionContextMenu {...addAnchor} title="Add assembly view" actions={candidates.map(candidate=>({label:candidate.title,icon:Boxes,run:()=>onAdd(candidate)}))} onClose={()=>setAddAnchor(null)}/>}
  </nav>;
}
