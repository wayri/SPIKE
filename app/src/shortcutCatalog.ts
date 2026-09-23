export type ShortcutAction =
  | "fit"
  | "zoomIn"
  | "zoomOut"
  | "panMode"
  | "orbitMode"
  | "panLeft"
  | "panRight"
  | "panUp"
  | "panDown"
  | "viewTop"
  | "viewBottom"
  | "viewIso"
  | "toggleView"
  | "toggleRibbon"
  | "layerManager"
  | "toggleNavigator"
  | "toggleAnalysisPanel"
  | "toggleResultsDock"
  | "toggleModels"
  | "openMeshWorkspace"
  | "openSolveWorkspace"
  | "shortcutWindow";

export const shortcutLabels: Record<ShortcutAction, string> = {
  fit: "Fit board",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
  panMode: "Pan mode",
  orbitMode: "Orbit mode",
  panLeft: "Pan left",
  panRight: "Pan right",
  panUp: "Pan up",
  panDown: "Pan down",
  viewTop: "Top view",
  viewBottom: "Bottom view",
  viewIso: "Isometric view",
  toggleView: "Toggle 2D / 3D",
  toggleRibbon: "Show / hide command ribbon",
  layerManager: "Show / hide layer manager",
  toggleNavigator: "Show / hide design navigator",
  toggleAnalysisPanel: "Show / hide analysis panel",
  toggleResultsDock: "Show / hide results dock",
  toggleModels: "Show / hide 3D models",
  openMeshWorkspace: "Open shared Mesh workspace",
  openSolveWorkspace: "Open shared Solve workspace",
  shortcutWindow: "Shortcut manager",
};

export const defaultShortcuts: Record<ShortcutAction, string> = {
  fit: "F",
  zoomIn: "=",
  zoomOut: "-",
  panMode: "P",
  orbitMode: "O",
  panLeft: "ArrowLeft",
  panRight: "ArrowRight",
  panUp: "ArrowUp",
  panDown: "ArrowDown",
  viewTop: "T",
  viewBottom: "B",
  viewIso: "I",
  toggleView: "V",
  toggleRibbon: "R",
  layerManager: "L",
  toggleNavigator: "N",
  toggleAnalysisPanel: "A",
  toggleResultsDock: "D",
  toggleModels: "M",
  openMeshWorkspace: "G",
  openSolveWorkspace: "U",
  shortcutWindow: "?",
};

export const shortcutGroups: { label: string; actions: ShortcutAction[] }[] = [
  {
    label: "Viewport",
    actions: ["fit", "zoomIn", "zoomOut", "panMode", "orbitMode", "panLeft", "panRight", "panUp", "panDown", "viewTop", "viewBottom", "viewIso", "toggleView"],
  },
  {
    label: "Workspace",
    actions: ["toggleRibbon", "layerManager", "toggleNavigator", "toggleAnalysisPanel", "toggleResultsDock", "toggleModels", "openMeshWorkspace", "openSolveWorkspace"],
  },
  { label: "Application", actions: ["shortcutWindow"] },
];

export const fixedShortcuts = [
  { label: "New project", key: "Ctrl+N" },
  { label: "Open project", key: "Ctrl+O" },
  { label: "Save project", key: "Ctrl+S" },
  { label: "Save project as", key: "Ctrl+Shift+S" },
  { label: "Undo", key: "Ctrl+Z" },
  { label: "Redo", key: "Ctrl+Y" },
  { label: "Copy context", key: "Ctrl+C" },
  { label: "Paste context", key: "Ctrl+V" },
  { label: "Clear selection or close", key: "Escape" },
] as const;

export const normalizedShortcutKey = (key: string) => key.length === 1 ? key.toUpperCase() : key;
