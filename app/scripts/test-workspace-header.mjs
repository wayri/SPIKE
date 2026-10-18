// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const states = [];
let hookIndex = 0;
const react = {
  useState(initial) {
    const index = hookIndex++;
    if (!(index in states)) states[index] = typeof initial === "function" ? initial() : initial;
    return [states[index], value => {
      states[index] = typeof value === "function" ? value(states[index]) : value;
    }];
  },
  useId() {
    return "workspace-header-file-menu";
  },
};
const jsx = {
  Fragment: Symbol("Fragment"),
  jsx: (type, props) => ({ type, props }),
  jsxs: (type, props) => ({ type, props }),
};
const Icon = props => ({ type: "mock-icon", props });
const ActionContextMenu = props => ({ type: "mock-action-menu", props });
const CommandStrip = props => ({ type: "mock-command-strip", props });

const source = readFileSync(new URL("../src/WorkspaceHeader.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", compiled)(name => {
  if (name === "react") return react;
  if (name === "react/jsx-runtime") return jsx;
  if (name === "./icons") return { ChevronDown: Icon, FolderOpen: Icon, PanelLeft: Icon, Search: Icon };
  if (name === "./ActionContextMenu") return { __esModule: true, default: ActionContextMenu };
  if (name === "./CommandStrip") return { __esModule: true, default: CommandStrip };
  throw new Error(`Unexpected dependency: ${name}`);
}, module, module.exports);

const calls = { files: 0, menu: 0, search: 0, workspaces: [] };
const workspaceSwitcher = { type: "mock-switcher", props: { id: "switcher" } };
const utilities = { type: "mock-utilities", props: { id: "utilities" } };
const fileActions = [{ label: "Open project", run() {} }, { label: "Save project", run() {} }];
const workspaces = [{ name: "PCB", icon: Icon }, { name: "Simulation", icon: Icon }];
const props = {
  projectName: "Control board",
  fileActions,
  onFilesOpen: () => calls.files++,
  workspaces,
  activeWorkspace: "PCB",
  onWorkspace: name => calls.workspaces.push(name),
  showWorkspaceBar: true,
  workspaceSwitcher,
  utilities,
  menuOpen: false,
  onMenu: () => calls.menu++,
  searchOpen: false,
  onSearch: () => calls.search++,
};
const render = (overrides = {}) => {
  hookIndex = 0;
  return module.exports.default({ ...props, ...overrides });
};
const find = (tree, predicate) => {
  if (!tree || typeof tree !== "object") return null;
  if (Array.isArray(tree)) {
    for (const child of tree) {
      const result = find(child, predicate);
      if (result) return result;
    }
    return null;
  }
  if (predicate(tree)) return tree;
  return find(tree.props?.children, predicate);
};
const findAll = (tree, predicate, results = []) => {
  if (!tree || typeof tree !== "object") return results;
  if (Array.isArray(tree)) {
    tree.forEach(child => findAll(child, predicate, results));
    return results;
  }
  if (predicate(tree)) results.push(tree);
  findAll(tree.props?.children, predicate, results);
  return results;
};
const text = tree => tree == null ? "" : typeof tree === "string" ? tree : Array.isArray(tree)
  ? tree.map(text).join(" ")
  : text(tree.props?.children);

let tree = render();
const menuButton = find(tree, node => node.props?.id === "focus-menu-toggle");
assert.equal(menuButton.props["aria-expanded"], false);
assert.equal(menuButton.props["aria-controls"], "focus-command-panel");
menuButton.props.onClick();
assert.equal(calls.menu, 1, "menu trigger preserves owner wiring");

const projectButton = find(tree, node => node.props?.className?.includes("workspace-project-trigger"));
assert.equal(projectButton.props["aria-label"], "Project files: Control board");
assert.equal(projectButton.props["aria-expanded"], false);
const anchor = { getBoundingClientRect: () => ({ left: 41, bottom: 73 }) };
projectButton.props.onClick({ currentTarget: anchor });
tree = render();
assert.equal(calls.files, 1, "opening project actions retains the owner callback");
const contextMenu = find(tree, node => node.type === ActionContextMenu);
assert.ok(contextMenu, "project trigger renders the context action menu");
assert.equal(contextMenu.props.x, 41);
assert.equal(contextMenu.props.y, 77);
assert.equal(contextMenu.props.actions, fileActions, "file action identity and callbacks are preserved");
assert.equal(contextMenu.props.id, "workspace-header-file-menu");
contextMenu.props.onClose();
tree = render();
assert.equal(find(tree, node => node.type === ActionContextMenu), null);

let prevented = false;
find(tree, node => node.props?.className?.includes("workspace-project-trigger")).props.onKeyDown({
  key: "ArrowDown",
  currentTarget: anchor,
  preventDefault: () => { prevented = true; },
});
tree = render();
assert.equal(prevented, true, "ArrowDown prevents page scrolling");
assert.equal(calls.files, 2, "ArrowDown opens the same project action flow");
assert.ok(find(tree, node => node.type === ActionContextMenu));

tree = render({ menuOpen: true, searchOpen: true });
assert.equal(find(tree, node => node.props?.id === "focus-menu-toggle").props["aria-expanded"], true);
const searchButton = find(tree, node => node.props?.className?.includes("workspace-header-search"));
assert.equal(searchButton.props["aria-expanded"], true);
assert.match(searchButton.props.className, /\bactive\b/);
assert.equal(searchButton.props["aria-keyshortcuts"], "Control+K Meta+K");
searchButton.props.onClick();
assert.equal(calls.search, 1, "search trigger preserves owner wiring");

const navigation = find(tree, node => node.props?.["aria-label"] === "Workspaces");
assert.ok(navigation, "workspace quick navigation renders when requested");
const strip = find(navigation, node => node.type === CommandStrip);
assert.equal(strip.props.label, "Workspace shortcuts");
const workspaceButtons = findAll(strip, node => node.type === "button");
assert.equal(workspaceButtons.length, 2);
assert.equal(workspaceButtons[0].props["aria-pressed"], true);
assert.equal(workspaceButtons[1].props["aria-pressed"], false);
assert.match(text(workspaceButtons[1]), /Simulation/);
workspaceButtons[1].props.onClick();
assert.deepEqual(calls.workspaces, ["Simulation"], "quick navigation forwards the exact workspace name");
assert.equal(find(tree, node => node === workspaceSwitcher), workspaceSwitcher);
assert.equal(find(tree, node => node === utilities), utilities);

tree = render({ showWorkspaceBar: false });
assert.equal(find(tree, node => node.props?.["aria-label"] === "Workspaces"), null);
assert.ok(find(tree, node => node.props?.className?.includes("workspace-header-main")), "classic mode retains the main header");

const css = readFileSync(new URL("../src/WorkspaceHeader.css", import.meta.url), "utf8");
assert.match(css, /^\/\* SPDX-License-Identifier: Apache-2\.0 \*\//);
assert.match(css, /workspace-header-search>span\s*\{[^}]*text-overflow:ellipsis/);
assert.match(css, /@media\(max-width:900px\)[\s\S]*workspace-header-search>kbd\s*\{\s*display:none/);
assert.match(css, /@media\(max-width:900px\)[\s\S]*workspace-header-search>span\s*\{\s*display:block/);

console.log("Workspace header actions, menus, quick navigation, search wiring, and responsive contracts passed.");
