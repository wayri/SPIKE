// SPDX-License-Identifier: Apache-2.0
import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ChevronDown, ChevronRight, FileChartColumn, FileCog, FolderOpen, History, ListTree, PanelLeftClose, Search, SquareArrowOutUpRight, X, type LucideIcon } from "./icons";
import type { SimulationStudy, SimulationStudyCase, StudyRun } from "./simulationStudies";
import "./studyNavigator.css";

export type StudyNavigatorProjectResult = { id: string; name: string; detail?: string; onOpen: () => void };
export type StudyNavigatorProps = {
  studies: SimulationStudy[];
  activeCaseId: string | null;
  projectResults?: StudyNavigatorProjectResult[];
  onActivateCase: (studyId: string, item: SimulationStudyCase) => void;
  onOpenRun: (studyId: string, item: SimulationStudyCase, run: StudyRun) => void;
  onManage: () => void;
  onClose: () => void;
  onFloat?: () => void;
  onDock?: () => void;
  docked: boolean;
};
type TreeNode = { id: string; name: string; detail?: string; icon: LucideIcon; children?: TreeNode[]; active?: boolean; onOpen?: () => void };
type VisibleNode = TreeNode & { level: number; parentId?: string; position: number; count: number };
const key = (...parts: string[]) => JSON.stringify(parts);
const captureTime = (value: string) => {
  const date = new Date(value);
  return Number.isFinite(date.valueOf()) ? date.toLocaleString() : "Capture time not recorded";
};
const hasEmbedded = (snapshot: unknown) => snapshot !== undefined && snapshot !== null;
const resultDetail = (snapshot: unknown, ref?: string) => hasEmbedded(snapshot) ? "Embedded captured payload" : ref ? "Locate required: external payload is not embedded" : "Setup capture only; no result payload";

/** Presentation only: activation and payload admission stay in App. */
export default function StudyNavigator(props: StudyNavigatorProps) {
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const rows = useRef(new Map<string, HTMLDivElement>());
  const roots = useMemo(() => {
    const studies: TreeNode[] = props.studies.filter(study => showArchived || !study.archived).map(study => ({
      id: key("study", study.id), name: study.name, detail: `${study.cases.length} simulations${study.archived ? " - Archived" : ""}`, icon: FolderOpen,
      children: study.cases.map(item => ({
        id: key("case", study.id, item.id), name: item.name, detail: `${item.type.toUpperCase()}${item.mode ? ` / ${item.mode}` : ""}`, icon: FileCog,
        active: item.id === props.activeCaseId, onOpen: () => props.onActivateCase(study.id, item),
        children: [
          ...(hasEmbedded(item.resultSnapshot) || item.resultRef ? [{
            id: key("result", study.id, item.id), name: hasEmbedded(item.resultSnapshot) ? "Saved case result" : "External result - locate required",
            detail: resultDetail(item.resultSnapshot, item.resultRef), icon: FileChartColumn,
            onOpen: () => props.onActivateCase(study.id, item),
          }] : []),
          ...item.runs.map((run, index) => ({
            id: key("run", study.id, item.id, run.id), name: `Capture ${index + 1} - ${captureTime(run.capturedAt)}`,
            detail: [run.caseType.toUpperCase(), run.mode, run.facts.status, run.facts.modelStatus, resultDetail(run.resultSnapshot, run.resultRef)].filter(Boolean).join(" / "),
            icon: hasEmbedded(run.resultSnapshot) || run.resultRef ? FileChartColumn : History,
            onOpen: () => props.onOpenRun(study.id, item, run),
          })),
        ],
      })),
    }));
    return [...studies, { id: key("project-results"), name: "Project results", detail: `${props.projectResults?.length ?? 0} results`, icon: FileChartColumn,
      children: (props.projectResults ?? []).map(result => ({ id: key("project-result", result.id), name: result.name, detail: result.detail, icon: FileChartColumn, onOpen: result.onOpen })),
    }];
  }, [props.studies, props.activeCaseId, props.projectResults, props.onActivateCase, props.onOpenRun, showArchived]);
  const needle = query.trim().toLocaleLowerCase();
  const filter = (nodes: TreeNode[], parentMatches = false): TreeNode[] => nodes.flatMap(node => {
    const matches = parentMatches || `${node.name} ${node.detail ?? ""}`.toLocaleLowerCase().includes(needle);
    const children = node.children ? filter(node.children, matches) : undefined;
    return matches || children?.length ? [{ ...node, children }] : [];
  });
  const filtered = needle ? filter(roots) : roots;
  const visible: VisibleNode[] = [];
  const flatten = (nodes: TreeNode[], level: number, parentId?: string) => nodes.forEach((node, index) => {
    visible.push({ ...node, level, parentId, position: index + 1, count: nodes.length });
    if (node.children?.length && (needle || !collapsed.has(node.id))) flatten(node.children, level + 1, node.id);
  });
  flatten(filtered, 1);
  const focusId = visible.some(node => node.id === focusedId) ? focusedId : visible.find(node => node.active)?.id ?? visible[0]?.id;
  const toggle = (id: string) => setCollapsed(previous => {
    const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next;
  });
  const focus = (id?: string) => { if (id) { setFocusedId(id); rows.current.get(id)?.focus(); } };
  const open = (node: TreeNode) => { if (node.onOpen) node.onOpen(); else if (node.children?.length) toggle(node.id); };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>, node: VisibleNode, index: number) => {
    if (event.target !== event.currentTarget) return;
    const expanded = Boolean(needle || !collapsed.has(node.id));
    switch (event.key) {
      case "ArrowDown": focus(visible[Math.min(index + 1, visible.length - 1)]?.id); break;
      case "ArrowUp": focus(visible[Math.max(0, index - 1)]?.id); break;
      case "Home": focus(visible[0]?.id); break;
      case "End": focus(visible[visible.length - 1]?.id); break;
      case "ArrowRight": if (node.children?.length) { if (!expanded) toggle(node.id); else focus(visible[index + 1]?.id); } break;
      case "ArrowLeft": if (node.children?.length && expanded && !needle) toggle(node.id); else focus(node.parentId); break;
      case "Enter": case " ": if (!event.repeat) open(node); break;
      default: return;
    }
    event.preventDefault(); event.stopPropagation();
  };
  return <aside className={`study-tree-panel${props.docked ? " is-docked" : " is-floating"}`} aria-label="Study navigator">
    <header className="study-tree-header">
      <strong><ListTree size={17} /> Studies and results</strong>
      <div className="study-tree-actions">
        <button type="button" className="spike-control--icon" onClick={props.docked ? props.onFloat : props.onDock} disabled={props.docked ? !props.onFloat : !props.onDock} aria-label={props.docked ? "Float study navigator" : "Dock study navigator"} title={props.docked ? "Float study navigator" : "Dock study navigator"}>{props.docked ? <SquareArrowOutUpRight size={15} /> : <PanelLeftClose size={15} />}</button>
        <button type="button" className="spike-control--icon" onClick={props.onClose} aria-label="Close study navigator" title="Close study navigator"><X size={15} /></button>
      </div>
    </header>
    <div className="study-tree-tools">
      <label className="study-tree-search"><Search size={15} /><input type="search" value={query} onChange={event => setQuery(event.target.value)} aria-label="Search studies and results" placeholder="Search studies and results" /></label>
      <div className="study-tree-options"><label><input type="checkbox" checked={showArchived} onChange={event => setShowArchived(event.target.checked)} />Archived</label><button type="button" className="spike-control--compact" onClick={props.onManage}>Manage studies</button></div>
    </div>
    <div className="study-tree-content" role="tree" aria-label="Studies, simulations and results">
      {visible.map((node, index) => {
        const Icon = node.icon;
        const hasChildren = Boolean(node.children?.length);
        const expanded = Boolean(needle || !collapsed.has(node.id));
        return <div key={node.id} ref={element => { if (element) rows.current.set(node.id, element); else rows.current.delete(node.id); }}
          className={`study-tree-row${node.active ? " is-active" : ""}`} role="treeitem" aria-level={node.level} aria-posinset={node.position} aria-setsize={node.count}
          aria-expanded={hasChildren ? expanded : undefined} aria-selected={Boolean(node.active)} aria-label={`${node.name}${node.detail ? `. ${node.detail}` : ""}`}
          tabIndex={node.id === focusId ? 0 : -1} style={{ paddingLeft: 8 + (node.level - 1) * 17 }} title={`${node.name}${node.detail ? `\n${node.detail}` : ""}`}
          onFocus={() => setFocusedId(node.id)} onClick={event => { if (event.detail <= 1) open(node); }} onKeyDown={event => onKeyDown(event, node, index)}>
          {hasChildren ? <button type="button" className="study-tree-disclosure spike-control--bare" tabIndex={-1} aria-label={`${expanded ? "Collapse" : "Expand"} ${node.name}`} disabled={Boolean(needle)} onClick={event => { event.stopPropagation(); if (event.detail <= 1) toggle(node.id); }}>{expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</button> : <span className="study-tree-disclosure-space" />}
          <Icon className="study-tree-icon" size={15} aria-hidden="true" />
          <span className="study-tree-text"><span>{node.name}</span>{node.detail && <small>{node.detail}</small>}</span>
        </div>;
      })}
      {!visible.length && <p className="study-tree-empty" role="status">No matching studies or results.</p>}
      {!props.studies.length && !needle && <p className="study-tree-empty">Use Manage studies to create a study and save simulations.</p>}
    </div>
    <footer className="study-tree-footer">Select a simulation to load its saved setup and result. Captures do not establish a completed solve.</footer>
  </aside>;
}
