// SPDX-License-Identifier: Apache-2.0
import { useId, useState, type KeyboardEvent } from "react";
import ActionContextMenu, { type ContextAction } from "./ActionContextMenu";
import { View3DIcon as Box, View2DIcon as CircuitBoard, FitViewIcon as Focus, PanIcon as Hand, SelectionIcon as MousePointer2, OrbitIcon as Orbit } from "./navigationIcons";
import "./buttonStandard.css";
import "./ViewportEssentialTools.css";

export type ViewportEssentialToolsProps = {
  viewMode: "2D" | "3D";
  navigationMode: "orbit" | "pan";
  selectionFilter: "all" | "part" | "net";
  onMode: (mode: "2D" | "3D") => void;
  onNavigation: (mode: "orbit" | "pan") => void;
  onFilter: (filter: "all" | "part" | "net") => void;
  onCamera: (command: string) => void;
};

type PopoverKind = "camera" | "filter";
type PopoverAnchor = { kind: PopoverKind; x: number; y: number };

const cameraViews = [
  ["top", "Top"],
  ["bottom", "Bottom"],
  ["front", "Front"],
  ["back", "Back"],
  ["left", "Left"],
  ["right", "Right"],
  ["iso", "Isometric"],
] as const;

const selectionFilters: ReadonlyArray<{ value: ViewportEssentialToolsProps["selectionFilter"]; label: string; description: string }> = [
  { value: "all", label: "All objects", description: "Select parts and nets" },
  { value: "part", label: "Parts only", description: "Limit selection to components" },
  { value: "net", label: "Nets only", description: "Limit selection to electrical nets" },
];

/** The same small, named controls in the viewport ribbon and context menu. */
export default function ViewportEssentialTools(props: ViewportEssentialToolsProps) {
  const [popover, setPopover] = useState<PopoverAnchor | null>(null);
  const cameraMenuId = useId();
  const filterMenuId = useId();
  const activeFilter = selectionFilters.find(filter => filter.value === props.selectionFilter)!;
  const openPopover = (kind: PopoverKind, button: HTMLButtonElement) => {
    const bounds = button.getBoundingClientRect();
    setPopover({ kind, x: bounds.left, y: bounds.bottom + 4 });
  };
  const openPopoverFromKeyboard = (kind: PopoverKind, event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    event.stopPropagation();
    openPopover(kind, event.currentTarget);
  };
  const cameraActions: ContextAction[] = cameraViews.map(([value, label]) => ({
    label,
    icon: Box,
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
  return <div className="viewport-essential-tools" role="group" aria-label="Viewport camera and selection" onPointerDown={event => event.stopPropagation()}>
    {(["2D", "3D"] as const).map(mode => { const Icon = mode === "2D" ? CircuitBoard : Box; return <button key={mode} type="button" className="spike-control--icon" title={`${mode} view`} aria-label={`${mode} view`} aria-pressed={props.viewMode === mode} onClick={() => props.onMode(mode)}><Icon size={15}/></button>; })}
    <span className="viewport-essential-divider"/>
    <button type="button" className="spike-control--icon" title="Orbit (3D)" aria-label="Orbit" disabled={props.viewMode === "2D"} aria-pressed={props.viewMode === "3D" && props.navigationMode === "orbit"} onClick={() => props.onNavigation("orbit")}><Orbit size={15}/></button>
    <button type="button" className="spike-control--icon" title="Pan" aria-label="Pan" aria-pressed={props.viewMode === "2D" || props.navigationMode === "pan"} onClick={() => props.onNavigation("pan")}><Hand size={15}/></button>
    <button type="button" className="spike-control--icon" title="Fit scene" aria-label="Fit scene" onClick={() => props.onCamera("fit")}><Focus size={15}/></button>
    <button type="button" className="spike-control--icon viewport-essential-popover-trigger" title="Camera view" aria-label="Camera view" aria-haspopup="menu"
      aria-expanded={popover?.kind === "camera"} aria-controls={popover?.kind === "camera" ? cameraMenuId : undefined} disabled={props.viewMode === "2D"}
      onClick={event => openPopover("camera", event.currentTarget)} onKeyDown={event => openPopoverFromKeyboard("camera", event)} onMouseEnter={event => openPopover("camera", event.currentTarget)}><Box size={15}/></button>
    <button type="button" className="spike-control--icon viewport-essential-popover-trigger" title={`Selection filter: ${activeFilter.label}`} aria-label={`Selection filter: ${activeFilter.label}`} aria-haspopup="menu"
      aria-expanded={popover?.kind === "filter"} aria-controls={popover?.kind === "filter" ? filterMenuId : undefined} data-active-filter={props.selectionFilter}
      onClick={event => openPopover("filter", event.currentTarget)} onKeyDown={event => openPopoverFromKeyboard("filter", event)} onMouseEnter={event => openPopover("filter", event.currentTarget)}><MousePointer2 size={15}/></button>
    {popover?.kind === "camera" && <ActionContextMenu id={cameraMenuId} x={popover.x} y={popover.y} title="Camera view" actions={cameraActions} onClose={() => setPopover(null)}/>}
    {popover?.kind === "filter" && <ActionContextMenu id={filterMenuId} x={popover.x} y={popover.y} title="Selection filter" actions={filterActions} onClose={() => setPopover(null)}/>}
  </div>;
}
