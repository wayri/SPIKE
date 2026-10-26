// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import ActionContextMenu, { type ContextAction } from "./ActionContextMenu";
import { View3DIcon as Box, View2DIcon as CircuitBoard, FitViewIcon as Focus, PanIcon as Hand, SelectionIcon as MousePointer2, OrbitIcon as Orbit } from "./navigationIcons";
import "./buttonStandard.css";
import "./ViewportEssentialTools.css";
import { CameraBackIcon, CameraBottomIcon, CameraFrontIcon, CameraIsometricIcon, CameraLeftIcon, CameraRightIcon, CameraTopIcon } from "./CameraViewIcons";
import { Layers3, Highlighter, RouteOff } from "./icons";

export type ViewportEssentialToolsProps = {
  viewMode: "2D" | "3D";
  navigationMode: "orbit" | "pan";
  selectionFilter: "all" | "part" | "net";
  onMode: (mode: "2D" | "3D") => void;
  onNavigation: (mode: "orbit" | "pan") => void;
  onFilter: (filter: "all" | "part" | "net") => void;
  onCamera: (command: string) => void;
  translucent?:boolean;
  onTranslucent?:()=>void;
  hasGeometry?:boolean;
  analyzedNetCount?:number;
  analyzedHighlight?:boolean;
  analyzedIsolate?:boolean;
  onAnalyzedHighlight?:()=>void;
  onAnalyzedIsolate?:()=>void;
  analyzedIsolationAvailable?:boolean;
  navigationOnly?:boolean;
  resultToolsOnly?:boolean;
  selectionHighlight?:boolean;
  onSelectionHighlight?:()=>void;
};

type PopoverKind = "camera" | "filter";
type PopoverAnchor = { kind: PopoverKind; x: number; y: number; mode: "preview" | "pinned" };

const cameraViews = [
  ["top", "Top", CameraTopIcon],
  ["bottom", "Bottom", CameraBottomIcon],
  ["front", "Front", CameraFrontIcon],
  ["back", "Back", CameraBackIcon],
  ["left", "Left", CameraLeftIcon],
  ["right", "Right", CameraRightIcon],
  ["iso", "Isometric", CameraIsometricIcon],
] as const;

const selectionFilters: ReadonlyArray<{ value: ViewportEssentialToolsProps["selectionFilter"]; label: string; description: string }> = [
  { value: "all", label: "All objects", description: "Select parts and nets" },
  { value: "part", label: "Parts only", description: "Limit selection to components" },
  { value: "net", label: "Nets only", description: "Limit selection to electrical nets" },
];

/** The same small, named controls in the viewport ribbon and context menu. */
export default function ViewportEssentialTools(props: ViewportEssentialToolsProps) {
  const [popover, setPopover] = useState<PopoverAnchor | null>(null);
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cameraMenuId = useId();
  const filterMenuId = useId();
  const activeFilter = selectionFilters.find(filter => filter.value === props.selectionFilter)!;
  const cancelDismiss = () => {
    if (dismissTimer.current !== null) clearTimeout(dismissTimer.current);
    dismissTimer.current = null;
  };
  useEffect(() => () => {
    if (dismissTimer.current !== null) clearTimeout(dismissTimer.current);
  }, []);
  const anchorPopover = (kind: PopoverKind, button: HTMLButtonElement, mode: PopoverAnchor["mode"]) => {
    const bounds = button.getBoundingClientRect();
    setPopover({ kind, x: bounds.left, y: bounds.bottom + 4, mode });
  };
  const previewPopover = (kind: PopoverKind, button: HTMLButtonElement) => {
    if ((kind === "camera" && props.viewMode === "2D") || popover?.mode === "pinned") return;
    cancelDismiss();
    anchorPopover(kind, button, "preview");
  };
  const clickPopover = (kind: PopoverKind, button: HTMLButtonElement) => {
    cancelDismiss();
    if (popover?.kind === kind && popover.mode === "pinned") setPopover(null);
    else anchorPopover(kind, button, "pinned");
  };
  const schedulePreviewDismiss = () => {
    if (popover?.mode !== "preview") return;
    cancelDismiss();
    dismissTimer.current = setTimeout(() => setPopover(current => current?.mode === "preview" ? null : current), 120);
  };
  const openPopoverFromKeyboard = (kind: PopoverKind, event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    event.stopPropagation();
    anchorPopover(kind, event.currentTarget, "pinned");
  };
  const cameraActions: ContextAction[] = cameraViews.map(([value, label, icon]) => ({
    label,
    icon,
    run: () => props.onCamera(`view-${value}`),
  }));
  const filterActions: ContextAction[] = selectionFilters.map(filter => ({
    label: filter.label,
    description: filter.description,
    icon: MousePointer2,
    checked: props.selectionFilter === filter.value,
    radio: true,
    run: () => props.onFilter(filter.value),
  }));
  return <div className={`viewport-essential-tools${props.resultToolsOnly ? " viewport-result-tools" : ""}`} role="group" aria-label={props.resultToolsOnly ? "Net and result inspection" : "Viewport camera and selection"} onPointerDown={event => event.stopPropagation()}>
    {!props.resultToolsOnly && <>
    <span className="viewport-essential-section viewport-essential-view-modes">
      {(["2D", "3D"] as const).map(mode => { const Icon = mode === "2D" ? CircuitBoard : Box; return <button key={mode} type="button" className="spike-control--icon viewport-essential-mode" title={`${mode} view`} aria-label={`${mode} view`} aria-pressed={props.viewMode === mode} onClick={() => props.onMode(mode)}><Icon size={15}/><span>{mode}</span></button>; })}
    </span>
    <span className="viewport-essential-divider"/>
    <span className="viewport-essential-section viewport-essential-navigation">
    <button type="button" className="spike-control--icon" title="Orbit (3D)" aria-label="Orbit" disabled={props.viewMode === "2D"} aria-pressed={props.viewMode === "3D" && props.navigationMode === "orbit"} onClick={() => props.onNavigation("orbit")}><Orbit size={15}/></button>
    <button type="button" className="spike-control--icon" title="Pan" aria-label="Pan" aria-pressed={props.viewMode === "2D" || props.navigationMode === "pan"} onClick={() => props.onNavigation("pan")}><Hand size={15}/></button>
    <button type="button" className="spike-control--icon" title="Fit scene" aria-label="Fit scene" onClick={() => props.onCamera("fit")}><Focus size={15}/></button>
    <button type="button" className="spike-control--icon viewport-essential-popover-trigger" title="Camera view" aria-label="Camera view" aria-haspopup="menu"
      aria-expanded={popover?.kind === "camera"} aria-controls={popover?.kind === "camera" ? cameraMenuId : undefined} disabled={props.viewMode === "2D"}
      onClick={event => clickPopover("camera", event.currentTarget)} onKeyDown={event => openPopoverFromKeyboard("camera", event)} onMouseEnter={event => previewPopover("camera", event.currentTarget)} onMouseLeave={schedulePreviewDismiss}><CameraIsometricIcon size={15}/></button>
    </span>
    <span className="viewport-essential-divider"/>
    <button type="button" className="spike-control--icon viewport-essential-popover-trigger" title={`Selection filter: ${activeFilter.label}`} aria-label={`Selection filter: ${activeFilter.label}`} aria-haspopup="menu"
      aria-expanded={popover?.kind === "filter"} aria-controls={popover?.kind === "filter" ? filterMenuId : undefined} data-active-filter={props.selectionFilter}
      onClick={event => clickPopover("filter", event.currentTarget)} onKeyDown={event => openPopoverFromKeyboard("filter", event)} onMouseEnter={event => previewPopover("filter", event.currentTarget)} onMouseLeave={schedulePreviewDismiss}><MousePointer2 size={15}/></button>
    {popover?.kind === "camera" && <ActionContextMenu id={cameraMenuId} x={popover.x} y={popover.y} title="Camera view" actions={cameraActions} onClose={() => setPopover(null)} preview={popover.mode === "preview"} onPointerEnter={cancelDismiss} onPointerLeave={schedulePreviewDismiss}/>}
    {popover?.kind === "filter" && <ActionContextMenu id={filterMenuId} x={popover.x} y={popover.y} title="Selection filter" actions={filterActions} onClose={() => setPopover(null)} preview={popover.mode === "preview"} onPointerEnter={cancelDismiss} onPointerLeave={schedulePreviewDismiss}/>}
    </>}
    {!props.navigationOnly && <>
    {props.onSelectionHighlight && <button type="button" className="viewport-labeled-toggle" aria-label="Highlight selected net" aria-pressed={Boolean(props.selectionHighlight)} disabled={props.hasGeometry===false} title="Highlight the selected net or explicitly linked component nets" onClick={props.onSelectionHighlight}><Highlighter size={14}/><span>Highlight selected net</span></button>}
  {props.onTranslucent&&<><span className="viewport-essential-divider"/><button type="button" className="viewport-labeled-toggle viewport-translucency-toggle" aria-label="Transparent board context" title={props.translucent ? "Restore opaque board context" : "Make board context transparent while preserving result and highlighted conductor geometry"} aria-pressed={Boolean(props.translucent)} disabled={props.hasGeometry===false} onClick={props.onTranslucent}><Layers3 size={15}/><span>{props.translucent ? "Transparent" : "Opaque"}</span></button></>}
  {(props.onAnalyzedHighlight || props.onAnalyzedIsolate) && <><span className="viewport-essential-divider"/>
    {props.onAnalyzedHighlight && <button type="button" className="viewport-labeled-toggle" aria-label="Highlight analyzed nets" aria-pressed={Boolean(props.analyzedHighlight)} disabled={!props.analyzedNetCount} title={props.analyzedNetCount ? `Highlight ${props.analyzedNetCount} analyzed nets independently of object selection` : "No occurrence-bound analyzed nets are available in the displayed result"} onClick={props.onAnalyzedHighlight}><Highlighter size={14}/><span>Highlight analyzed nets</span></button>}
    {props.onAnalyzedIsolate && <button type="button" className="viewport-labeled-toggle" aria-label="Isolate analyzed nets" aria-pressed={Boolean(props.analyzedIsolate)} disabled={!props.analyzedNetCount || props.analyzedIsolationAvailable === false} title={props.analyzedIsolationAvailable === false ? "Analyzed-net isolation requires a single-board viewport; scoped assembly isolation is not available" : props.analyzedIsolate ? "Restore complete board context" : props.analyzedNetCount ? "Show only the displayed result's analyzed conductors; selection does not add nets" : "No occurrence-bound analyzed nets are available in the displayed result"} onClick={props.onAnalyzedIsolate}><RouteOff size={14}/><span>Isolate analyzed nets</span></button>}
  </>}
    </>}
  </div>;
}
