// SPDX-License-Identifier: Apache-2.0
// KiCad action names and bindings are independently mapped to SPIKE capabilities.
// Reference: https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#actions-reference
export const shortcutDescriptors = {
  fit: { label: "Fit board / home view", key: "Home", group: "Viewport" },
  zoomIn: { label: "Zoom in at cursor", key: "F1", group: "Viewport" },
  zoomOut: { label: "Zoom out at cursor", key: "F2", group: "Viewport" },
  panMode: { label: "Pan mode", key: "P", group: "Viewport" },
  orbitMode: { label: "Orbit mode", key: "O", group: "Viewport" },
  panLeft: { label: "Pan left", key: "ArrowLeft", group: "Viewport" },
  panRight: { label: "Pan right", key: "ArrowRight", group: "Viewport" },
  panUp: { label: "Pan up", key: "ArrowUp", group: "Viewport" },
  panDown: { label: "Pan down", key: "ArrowDown", group: "Viewport" },
  panLeftFast: { label: "Pan left faster", key: "Shift+ArrowLeft", group: "Viewport" },
  panRightFast: { label: "Pan right faster", key: "Shift+ArrowRight", group: "Viewport" },
  panUpFast: { label: "Pan up faster", key: "Shift+ArrowUp", group: "Viewport" },
  panDownFast: { label: "Pan down faster", key: "Shift+ArrowDown", group: "Viewport" },
  focusSelection: { label: "Focus selected object", key: "Ctrl+F5", group: "Viewport" },
  centerCursor: { label: "Center view at cursor", key: "F4", group: "Viewport" },
  nextLayer: { label: "Next copper layer", key: "PageDown", group: "Visibility" },
  previousLayer: { label: "Previous copper layer", key: "PageUp", group: "Visibility" },
  focusLayer: { label: "Show focused copper layer", key: "Ctrl+Shift+J", group: "Visibility" },
  showAllLayers: { label: "Show all layers", key: "Ctrl+Shift+O", group: "Visibility" },
  viewTop: { label: "Top view", key: "Z", group: "Views" },
  viewBottom: { label: "Bottom view", key: "Shift+Z", group: "Views" },
  viewFront: { label: "Front view", key: "Y", group: "Views" },
  viewBack: { label: "Back view", key: "Shift+Y", group: "Views" },
  viewLeft: { label: "Left view", key: "Shift+X", group: "Views" },
  viewRight: { label: "Right view", key: "X", group: "Views" },
  viewIso: { label: "Isometric view", key: "I", group: "Views" },
  flipBoard: { label: "Flip board view", key: "F", group: "Views" },
  pivotCursor: { label: "Set rotation pivot at cursor", key: "Space", group: "Views" },
  toggleView: { label: "Toggle 2D / 3D", key: "V", group: "Views" },
  toggleModels: { label: "Show / hide 3D models", key: "M", group: "Visibility" },
  toggleSmd: { label: "Show / hide surface mount models", key: "S", group: "Visibility" },
  toggleTht: { label: "Show / hide through hole models", key: "T", group: "Visibility" },
  toggleAxes: { label: "Show / hide axes", key: "Shift+A", group: "Visibility" },
  toggleVias: { label: "Show / hide vias", key: "Shift+V", group: "Visibility" },
  toggleNetNames: { label: "Show / hide net names", key: "Shift+N", group: "Visibility" },
  highlightNet: { label: "Highlight selected net", key: "`", group: "Selection and nets" },
  toggleNetHighlight: { label: "Toggle net highlighting", key: "Ctrl+`", group: "Selection and nets" },
  clearNetHighlight: { label: "Clear net highlighting", key: "Shift+`", group: "Selection and nets" },
  isolateNet: { label: "Isolate selected net", key: "Shift+H", group: "Selection and nets" },
  filterAll: { label: "Select all object types", key: "Shift+1", group: "Selection and nets" },
  filterParts: { label: "Select components only", key: "Shift+2", group: "Selection and nets" },
  filterNets: { label: "Select nets only", key: "Shift+3", group: "Selection and nets" },
  addProbe: { label: "Add probe at cursor", key: "Shift+P", group: "Selection and nets" },
  showContextActions: { label: "Show actions at cursor", key: "Shift+F10", group: "Selection and nets" },
  toggleRibbon: { label: "Show / hide command ribbon", key: "R", group: "Workspace" },
  layerManager: { label: "Show / hide layer manager", key: "L", group: "Workspace" },
  toggleNavigator: { label: "Show / hide design navigator", key: "N", group: "Workspace" },
  toggleAnalysisPanel: { label: "Show / hide analysis panel", key: "A", group: "Workspace" },
  toggleResultsDock: { label: "Show / hide results dock", key: "D", group: "Workspace" },
  openSchematic: { label: "Open schematic viewer", key: "Ctrl+Shift+H", group: "Workspace" },
  openMeshWorkspace: { label: "Open shared Mesh workspace", key: "Ctrl+Shift+M", group: "Analysis" },
  openSolveWorkspace: { label: "Open shared Solve workspace", key: "Ctrl+Shift+U", group: "Analysis" },
  openPiSetup: { label: "Open power integrity setup", key: "Ctrl+Shift+P", group: "Analysis" },
  openSiSetup: { label: "Open signal integrity setup", key: "Ctrl+Shift+I", group: "Analysis" },
  openThermalSetup: { label: "Open thermal setup", key: "Ctrl+Shift+T", group: "Analysis" },
  openEmSetup: { label: "Open electromagnetic setup", key: "Ctrl+Shift+E", group: "Analysis" },
  openSpice: { label: "Open SPICE workbench", key: "Ctrl+Shift+B", group: "Analysis" },
  openStudies: { label: "Open study workspaces", key: "Ctrl+Shift+D", group: "Analysis" },
  toggleResultOverlay: { label: "Show / hide result overlay", key: "Ctrl+Shift+R", group: "Results" },
  playPauseResults: { label: "Play / pause transient results", key: "Ctrl+Space", group: "Results" },
  previousFrame: { label: "Previous result frame", key: "Ctrl+ArrowLeft", group: "Results" },
  nextFrame: { label: "Next result frame", key: "Ctrl+ArrowRight", group: "Results" },
  firstFrame: { label: "First result frame", key: "Ctrl+Home", group: "Results" },
  lastFrame: { label: "Last result frame", key: "Ctrl+End", group: "Results" },
  openResultPlots: { label: "Open result plots", key: "Ctrl+Shift+L", group: "Results" },
  toggleTraceValues: { label: "Show / hide trace values", key: "Ctrl+Shift+V", group: "Results" },
  openAssembly: { label: "Open assembly workspace", key: "Ctrl+Shift+A", group: "Assembly" },
  toggleExplode: { label: "Toggle exploded assembly", key: "Ctrl+Shift+X", group: "Assembly" },
  openHarness: { label: "Open harness manager", key: "Ctrl+Shift+W", group: "Assembly" },
  openContacts: { label: "Open thermal contacts", key: "Ctrl+Shift+Q", group: "Assembly" },
  cancelSimulation: { label: "Cancel active simulation", key: "Shift+Escape", group: "Analysis" },
  openProbeTable: { label: "Open probe table", key: "Ctrl+Shift+F", group: "Selection and nets" },
  shortcutWindow: { label: "Shortcut manager", key: "Ctrl+F1", group: "Application" },
} as const;

export type ShortcutAction = keyof typeof shortcutDescriptors;
export type ShortcutMap = Record<ShortcutAction, string>;
export type ShortcutPreset = "kicad" | "spike";
const actions = Object.keys(shortcutDescriptors) as ShortcutAction[];
export const shortcutLabels = Object.fromEntries(actions.map(action => [action, shortcutDescriptors[action].label])) as Record<ShortcutAction, string>;
export const defaultShortcuts = Object.fromEntries(actions.map(action => [action, shortcutDescriptors[action].key])) as ShortcutMap;
export const shortcutGroups = [...new Set(actions.map(action => shortcutDescriptors[action].group))].map(label => ({ label, actions: actions.filter(action => shortcutDescriptors[action].group === label) }));

export const fixedShortcuts = [
  { label: "New project", key: "Ctrl+N" },
  { label: "Open project", key: "Ctrl+O" },
  { label: "Save project", key: "Ctrl+S" },
  { label: "Save project as", key: "Ctrl+Shift+S" },
  { label: "Undo", key: "Ctrl+Z" },
  { label: "Redo", key: "Ctrl+Y" },
  { label: "Copy context", key: "Ctrl+C" },
  { label: "Paste context", key: "Ctrl+V" },
  { label: "Universal search", key: "Ctrl+K" },
  { label: "IPC editor", key: "Ctrl+Shift+C" },
  { label: "Clear selection or close", key: "Escape" },
] as const;

const shiftedSymbols: Record<string, string> = { "~": "`", "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/" };
const modifiers = new Set(["Control", "Ctrl", "Meta", "Alt", "Shift", "AltGraph"]);
const namedKeys = new Set(["Home", "End", "PageUp", "PageDown", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter", "Escape", "Tab", "Backspace", "Delete", "Insert", "Space", "ContextMenu"]);

/** Canonical browser key chord. Invalid and standalone modifier keys return blank. */
export function normalizedShortcutKey(raw: string): string {
  if (raw === " ") return "Space";
  const input = raw.trim();
  if (!input) return "";
  let rest = input;
  const flags = new Set<string>();
  let prefix: RegExpMatchArray | null;
  while ((prefix = rest.match(/^(Ctrl|Control|Meta|Shift|Alt)\+/i))) {
    const modifier = prefix[1].toLowerCase();
    flags.add(modifier === "control" || modifier === "meta" || modifier === "ctrl" ? "Ctrl" : modifier === "shift" ? "Shift" : "Alt");
    rest = rest.slice(prefix[0].length);
  }
  if (modifiers.has(rest) || !rest) return "";
  if (shiftedSymbols[rest]) { flags.add("Shift"); rest = shiftedSymbols[rest]; }
  if (rest === " " || rest === "Spacebar") rest = "Space";
  if (rest === "Esc") rest = "Escape";
  if (rest.length === 1) {
    if (!/^[a-z0-9`=\-\[\]\\;',./]$/i.test(rest)) return "";
    rest = rest.toUpperCase();
  } else if (!namedKeys.has(rest) && !/^F(?:[1-9]|1[0-9]|2[0-4])$/.test(rest)) return "";
  return [...["Ctrl", "Alt", "Shift"].filter(flag => flags.has(flag)), rest].join("+");
}

export type ShortcutKeyEvent = Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey"> & { isComposing?: boolean; getModifierState?: (key: "AltGraph") => boolean };
export function eventShortcutKey(event: ShortcutKeyEvent): string {
  if (event.isComposing || event.getModifierState?.("AltGraph") || modifiers.has(event.key)) return "";
  return normalizedShortcutKey(`${event.ctrlKey || event.metaKey ? "Ctrl+" : ""}${event.altKey ? "Alt+" : ""}${event.shiftKey ? "Shift+" : ""}${event.key === " " ? "Space" : event.key}`);
}

/** Validate user assignments before mutation; blank is an explicit unassignment. */
export function shortcutBindingIssue(raw: string): string | null {
  if (!raw.trim()) return null;
  const key = normalizedShortcutKey(raw);
  if (!key) return "Press a key with optional Ctrl, Shift or Alt modifiers.";
  const fixed = fixedShortcuts.find(item => item.key === key);
  if (fixed) return `${key} is reserved for ${fixed.label.toLowerCase()}.`;
  if (/^Alt\+[FEVARPTXH]$/.test(key)) return `${key} is reserved for the application menu.`;
  if (["Ctrl+R", "Ctrl+W", "Ctrl+T", "Ctrl+L", "Alt+F4", "F5", "F11", "F12"].includes(key)) return `${key} is reserved by the host window.`;
  return null;
}

/** Saved bindings win over added defaults. Conflicting new actions stay unassigned. */
export function hydrateShortcuts(raw: unknown): ShortcutMap {
  const result = Object.fromEntries(actions.map(action => [action, ""])) as ShortcutMap;
  const used = new Set<string>();
  const explicit = new Set<ShortcutAction>();
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    for (const action of actions) {
      if (!Object.prototype.hasOwnProperty.call(raw, action)) continue;
      const value = (raw as Record<string, unknown>)[action];
      if (typeof value !== "string" || shortcutBindingIssue(value)) continue;
      const key = normalizedShortcutKey(value);
      // Duplicate saved assignments are admitted once, with a visible blank for the other.
      explicit.add(action);
      if (key && !used.has(key)) { result[action] = key; used.add(key); }
    }
  }
  for (const action of actions) {
    if (explicit.has(action)) continue;
    const key = defaultShortcuts[action];
    if (!used.has(key)) { result[action] = key; used.add(key); }
  }
  return result;
}

const legacyShortcuts = {
  "fit": "F",
  "zoomIn": "=",
  "zoomOut": "-",
  "panMode": "P",
  "orbitMode": "O",
  "panLeft": "ArrowLeft",
  "panRight": "ArrowRight",
  "panUp": "ArrowUp",
  "panDown": "ArrowDown",
  "viewTop": "T",
  "viewBottom": "B",
  "viewIso": "I",
  "toggleView": "V",
  "toggleRibbon": "R",
  "layerManager": "L",
  "toggleNavigator": "N",
  "toggleAnalysisPanel": "A",
  "toggleResultsDock": "D",
  "toggleModels": "M",
  "openMeshWorkspace": "G",
  "openSolveWorkspace": "U",
  "shortcutWindow": "Shift+/"
};
export const shortcutPresets: Record<ShortcutPreset, ShortcutMap> = {
  kicad: { ...defaultShortcuts },
  spike: hydrateShortcuts({ ...legacyShortcuts, flipBoard: "Shift+F", toggleTht: "Shift+T" }),
};
