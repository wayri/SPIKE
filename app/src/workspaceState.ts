export type ViewMode = "2D" | "3D";
export type DockTabId = "Issues" | "Probe table" | "Power tree" | "Console";
export type Vector3Tuple = [number, number, number];

export type Viewport3DCameraState = {
  contract: "spike/viewport-camera/v1";
  position: Vector3Tuple;
  target: Vector3Tuple;
  up: Vector3Tuple;
};

export type Viewport2DState = {
  contract: "spike/layout-view/v1";
  x: number;
  y: number;
  width: number;
  height: number;
};

export type WorkspaceState = {
  contract: "spike/workspace-state/v1";
  viewMode: ViewMode;
  docks: {
    leftOpen: boolean;
    rightOpen: boolean;
    bottomOpen: boolean;
    sidePanelsPinned: boolean;
    bottomPinned: boolean;
    leftWidthPx: number;
    rightWidthPx: number;
    bottomHeightPx: number;
    activeBottomDock: DockTabId;
  };
  viewports: { threeD?: Viewport3DCameraState; twoD?: Viewport2DState };
};

export type ViewportRestoreCommand = {
  token: number;
  threeD?: Viewport3DCameraState;
  twoD?: Viewport2DState;
};

const dockTabs = new Set<DockTabId>(["Issues", "Probe table", "Power tree", "Console"]);
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const clamp = (value: unknown, fallback: number, minimum: number, maximum: number) =>
  Math.max(minimum, Math.min(maximum, finite(value) ? value : fallback));
const tuple = (value: unknown): Vector3Tuple | null => {
  if (!Array.isArray(value) || value.length !== 3 || !value.every(finite)) return null;
  return [value[0], value[1], value[2]];
};

function normalize3D(value: unknown): Viewport3DCameraState | undefined {
  if (!value || typeof value !== "object") return undefined;
  const raw = value as Record<string, unknown>;
  const position = tuple(raw.position);
  const target = tuple(raw.target);
  const up = tuple(raw.up);
  if (raw.contract !== "spike/viewport-camera/v1" || !position || !target || !up) return undefined;
  if (Math.hypot(...up) < 1e-9 || Math.hypot(position[0] - target[0], position[1] - target[1], position[2] - target[2]) < 1e-9) return undefined;
  return { contract: "spike/viewport-camera/v1", position, target, up };
}

function normalize2D(value: unknown): Viewport2DState | undefined {
  if (!value || typeof value !== "object") return undefined;
  const raw = value as Record<string, unknown>;
  if (raw.contract !== "spike/layout-view/v1" || !finite(raw.x) || !finite(raw.y) || !finite(raw.width) || !finite(raw.height)) return undefined;
  if (raw.width <= 0 || raw.height <= 0 || raw.width > 1e9 || raw.height > 1e9) return undefined;
  return { contract: "spike/layout-view/v1", x: raw.x, y: raw.y, width: raw.width, height: raw.height };
}

export function normalizeWorkspaceState(value: unknown): WorkspaceState | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  if (raw.contract !== "spike/workspace-state/v1") return null;
  const docks = raw.docks && typeof raw.docks === "object" ? raw.docks as Record<string, unknown> : {};
  const viewports = raw.viewports && typeof raw.viewports === "object" ? raw.viewports as Record<string, unknown> : {};
  return {
    contract: "spike/workspace-state/v1",
    viewMode: raw.viewMode === "2D" ? "2D" : "3D",
    docks: {
      leftOpen: docks.leftOpen !== false,
      rightOpen: docks.rightOpen !== false,
      bottomOpen: docks.bottomOpen !== false,
      sidePanelsPinned: docks.sidePanelsPinned !== false,
      bottomPinned: docks.bottomPinned !== false,
      leftWidthPx: clamp(docks.leftWidthPx, 224, 180, 520),
      rightWidthPx: clamp(docks.rightWidthPx, 272, 210, 620),
      bottomHeightPx: clamp(docks.bottomHeightPx, 178, 72, 440),
      activeBottomDock: dockTabs.has(docks.activeBottomDock as DockTabId) ? docks.activeBottomDock as DockTabId : "Issues",
    },
    viewports: { threeD: normalize3D(viewports.threeD), twoD: normalize2D(viewports.twoD) },
  };
}
