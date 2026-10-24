// SPDX-License-Identifier: Apache-2.0
import type { ContextMenuGroup } from "./ViewportActionMenu";
export type ViewportNavigationContext = {
  viewMode: "2D" | "3D"; navigationMode: "orbit" | "pan";
  focusPoint?: readonly number[];
  camera: (command: string) => void;
  orbitAt: (point: [number, number, number]) => void;
  setMode: (mode: "orbit" | "pan") => void;
  setView: (mode: "2D" | "3D") => void;
};
/** Camera-only actions remain available in every analysis workspace. */
export function viewportNavigationGroups(context: ViewportNavigationContext): ContextMenuGroup[] {
  const point = context.focusPoint?.length === 3 && context.focusPoint.every(Number.isFinite)
    ? [...context.focusPoint] as [number, number, number] : null;
  const planar = context.viewMode === "2D";
  return [{ id: "navigation", label: "Navigate viewport", actions: [
    { id: "orbit-center", label: "Orbit around clicked point", description: "Set the pivot at the original right-click point and activate Orbit.", disabledReason: planar ? "Orbit requires the 3D view" : !point ? "Right-click a point in the 3D viewport first" : undefined, run: () => { if (!planar && point) { context.orbitAt([...point]); context.setMode("orbit"); } } },
    { id: "navigation-orbit", label: "Orbit", checked: !planar && context.navigationMode === "orbit", disabledReason: planar ? "Orbit requires the 3D view" : undefined, description: "Left drag rotates; Shift + left drag pans.", run: () => { if (!planar) context.setMode("orbit"); } },
    { id: "navigation-pan", label: "Pan", checked: planar || context.navigationMode === "pan", description: "Left drag moves the view; 2D always pans.", run: () => context.setMode("pan") },
    { id: "fit", label: "Fit all visible objects", run: () => context.camera("fit") },
    { id: "navigation-zoom-in", label: "Zoom in", run: () => context.camera("zoom-in") },
    { id: "navigation-zoom-out", label: "Zoom out", run: () => context.camera("zoom-out") },
    { id: "navigation-reset", label: "Reset camera", description: "Restore the default camera and fit the visible scene.", run: () => context.camera("reset-view") },
  ] }, { id: "camera-views", label: "Views", actions: [
    ...(["2D", "3D"] as const).map(mode => ({ id: `camera-${mode.toLowerCase()}`, label: `${mode} view`, checked: context.viewMode === mode, run: () => context.setView(mode) })),
    ...([ ["top", "Top"], ["bottom", "Bottom"], ["front", "Front"], ["back", "Back"], ["left", "Left"], ["right", "Right"], ["iso", "Isometric"] ] as const).map(([view, label]) => ({ id: `camera-view-${view}`, label, description: "Standard 3D camera direction", disabledReason: planar ? "Switch to 3D to use this camera direction" : undefined, run: () => { if (!planar) context.camera(`view-${view}`); } })),
  ] }];
}
