// SPDX-License-Identifier: Apache-2.0
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

/** The same small, named controls in the viewport ribbon and context menu. */
export default function ViewportEssentialTools(props: ViewportEssentialToolsProps) {
  return <div className="viewport-essential-tools" role="group" aria-label="Viewport camera and selection" onPointerDown={event => event.stopPropagation()}>
    {(["2D", "3D"] as const).map(mode => { const Icon = mode === "2D" ? CircuitBoard : Box; return <button key={mode} type="button" className="spike-control--icon" title={`${mode} view`} aria-label={`${mode} view`} aria-pressed={props.viewMode === mode} onClick={() => props.onMode(mode)}><Icon size={15}/></button>; })}
    <span className="viewport-essential-divider"/>
    <button type="button" className="spike-control--icon" title="Orbit (3D)" aria-label="Orbit" disabled={props.viewMode === "2D"} aria-pressed={props.viewMode === "3D" && props.navigationMode === "orbit"} onClick={() => props.onNavigation("orbit")}><Orbit size={15}/></button>
    <button type="button" className="spike-control--icon" title="Pan" aria-label="Pan" aria-pressed={props.viewMode === "2D" || props.navigationMode === "pan"} onClick={() => props.onNavigation("pan")}><Hand size={15}/></button>
    <button type="button" className="spike-control--icon" title="Fit scene" aria-label="Fit scene" onClick={() => props.onCamera("fit")}><Focus size={15}/></button>
    <label className="viewport-essential-picker" title="Camera view"><Box size={15}/><select aria-label="Camera view" value="" disabled={props.viewMode === "2D"} onChange={event => props.onCamera(`view-${event.target.value}`)}><option value="" disabled>View</option>{["top", "bottom", "front", "back", "left", "right", "iso"].map(view => <option key={view} value={view}>{view === "iso" ? "Isometric" : view[0].toUpperCase() + view.slice(1)}</option>)}</select></label>
    <label className="viewport-essential-picker" title="Selection filter"><MousePointer2 size={15}/><select aria-label="Selection filter" value={props.selectionFilter} onChange={event => props.onFilter(event.target.value as ViewportEssentialToolsProps["selectionFilter"])}><option value="all">All</option><option value="part">Parts</option><option value="net">Nets</option></select></label>
  </div>;
}
