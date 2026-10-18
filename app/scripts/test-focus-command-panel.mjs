// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { focusCommandsFromElements, searchFocusCommands, searchableFocusCommands } = await importTestTypescript("focusCommands");
const untouched = name => () => { throw new Error(`${name} component was invoked`); };
const MenuButton = untouched("MenuButton"), MenuSubmenu = untouched("MenuSubmenu");
const MenuItem = untouched("MenuItem"), ToolGroup = untouched("ToolGroup"), Tool = untouched("Tool");
const ToolbarMenu = untouched("ToolbarMenu");
const icon = untouched("Icon");
let opened = 0, blocked = 0, imported = 0;
const picker = React.createElement("label", { className: "file-picker" },
  React.createElement(icon), React.createElement("span", null, "Import project"),
  React.createElement("input", { type: "file", onChange: () => imported++ }));
const elements = React.createElement(React.Fragment, null,
  React.createElement(MenuButton, { label: "File" },
    React.createElement(MenuSubmenu, { label: "Open and import" }, [
      React.createElement(MenuItem, { key: "open", label: "Open project", shortcut: "Ctrl+O", icon, onClick: () => opened++ }),
      React.createElement(MenuItem, { key: "blocked", label: "Open recent", disabled: true, icon, onClick: () => blocked++ }),
      React.cloneElement(picker, { key: "picker" }),
    ])),
  React.createElement(ToolGroup, { label: "Analysis" },
    React.createElement(Tool, { label: "Run PI", icon, onClick: () => opened++ })),
  React.createElement("div", null,
    React.createElement("button", { title: "Fit active scene (F)", onClick: () => opened++ }, React.createElement(icon)),
    React.createElement("select", { "aria-label": "Result quantity", defaultValue: "voltage" }, React.createElement("option", { value: "voltage" }, "Voltage"))),
  React.createElement(ToolbarMenu, { label: "Navigate", icon, actions: [
    { label: "Orbit", icon, disabled: true, checked: false, radio: true, run: () => blocked++ },
    { label: "Pan", icon, checked: true, radio: true, run: () => opened++ },
  ] }));

const commands = focusCommandsFromElements(elements, "application");
assert.deepEqual(commands.map(command => command.label), ["File", "Analysis", "Fit active scene (F)", "Result quantity", "Navigate"]);
const file = commands[0], submenu = file.children[0];
assert.deepEqual(submenu.children.map(command => command.label), ["Open project", "Open recent", "Import project"], "nested arrays and fragments retain command names");
assert.equal(submenu.children[1].disabled, true, "disabled actions remain discoverable");
assert.equal(submenu.children[1].run instanceof Function, true, "disabled metadata does not discard its original handler");
submenu.children[0].run(); assert.equal(opened, 1, "extracted action invokes the original handler exactly once");
assert.equal(blocked, 0);
const fileCommand = submenu.children[2];
assert.equal(fileCommand.content.type, "label");
const input = React.Children.toArray(fileCommand.content.props.children).find(child => React.isValidElement(child) && child.type === "input");
assert.equal(input.props.type, "file", "file picker input is retained as live command content");
input.props.onChange(); assert.equal(imported, 1);
const disabledSearch = searchFocusCommands(commands, "file open recent");
assert.equal(disabledSearch.length, 1); assert.equal(disabledSearch[0].command.disabled, true, "search retains disabled state");
assert.deepEqual(disabledSearch[0].path, ["File", "Open and import", "Open recent"], "search matches full group paths");
assert.deepEqual(disabledSearch[0].ancestors.map(command => command.label), ["File", "Open and import"]);
assert.deepEqual(searchFocusCommands(commands, "analysis run pi").map(match => match.command.label), ["Run PI"]);
commands[2].run(); assert.equal(opened, 2, "native toolbar actions use their existing handler");
assert.equal(commands[3].content.type, "select", "named native controls remain live content");
assert.deepEqual(commands[4].children.map(command => [command.label, command.disabled, command.checked, command.radio]),
  [["Orbit", true, false, true], ["Pan", false, true, true]], "ToolbarMenu actions retain disabled and radio state");

const panel = readFileSync(new URL("../src/FocusCommandPanel.tsx", import.meta.url), "utf8");
assert.match(panel, /id="focus-menu-toggle"|getElementById\("focus-menu-toggle"\)/, "close restores the focus-menu toggle");
assert.match(panel, /event\.key === "Escape"/); assert.match(panel, /focus-command-back/);
assert.match(panel, /match\?\.ancestors\.some\(ancestor => ancestor\.onEnter\)/, "workspace search routes through onEnter before exposing a live leaf");
assert.match(panel, /\[initialSection\]/, "mounted panel follows menu-section changes");
assert.match(panel, /id="focus-command-panel"/); assert.match(panel, /menuitemradio/);
assert.match(panel, /className="focus-command-row focus-command-content"/, "custom command content has a panel row");
console.log("Focus commands: nested extraction, disabled state, handlers, file picker content, path search and panel focus contract passed.");

const preservedIcon = React.createElement(icon, { size: 15 });
const nativeIconButton = React.createElement("button", { title: "Open layer visibility and stack controls", onClick: () => opened++ }, preservedIcon, " Layers");
const nativeRadio = React.createElement("button", { role: "radio", "aria-checked": true, onClick: () => {} }, preservedIcon, "3D");
const nativeRows = focusCommandsFromElements([nativeIconButton, nativeRadio], "native-icons");
assert.equal(nativeRows[0].label, "Layers", "Visible short text must not become a verbose tooltip");
assert.equal(nativeRows[0].description, "Open layer visibility and stack controls");
assert.equal(nativeRows[0].iconNode, preservedIcon, "Native icons retain their original React element without invocation");
assert.equal(nativeRows[1].checked, true);
assert.equal(nativeRows[1].radio, true);
const beforeNativeClick = opened; nativeRows[0].run(); assert.equal(opened, beforeNativeClick + 1, "Restored icon metadata preserves action binding");

assert.equal(searchFocusCommands(nativeRows, "visibility stack")[0].command.label, "Layers", "Descriptions remain searchable after shortening the label");

let enteredWorkspace = 0, ranWorkspaceCommand = 0;
const searchable = searchableFocusCommands([{ id: "workspaces", label: "Workspaces", children: [
  { id: "workspace:pi", label: "PI", onEnter: () => { enteredWorkspace++; }, children: [
    { id: "run-pi", label: "Run PI", shortcut: "Ctrl+R", run: () => { ranWorkspaceCommand++; } },
    { id: "blocked", label: "Blocked action", disabled: true, run: () => { throw new Error("must remain gated"); } },
  ] },
] }]);
const workspaceRow = searchable.find(row => row.id === "command:workspace:pi");
assert.equal(workspaceRow.category, "Workspaces");
assert.match(workspaceRow.keywords, /workspace tab ribbon/);
await workspaceRow.run(); assert.equal(enteredWorkspace, 1, "workspace rows execute their live entry callback");
const runRow = searchable.find(row => row.id === "command:run-pi");
assert.equal(runRow.shortcut, "Ctrl+R"); assert.match(runRow.description, /Workspaces \/ PI \/ Run PI/);
await runRow.run(); assert.deepEqual([enteredWorkspace, ranWorkspaceCommand], [2, 1], "nested commands enter their workspace before using the original handler");
assert.equal(searchable.find(row => row.id === "command:blocked").disabled, true, "unavailable command gating survives search projection");
const inheritedGate = searchableFocusCommands([{ id: "offline", label: "Offline workspace", disabled: true, children: [
  { id: "offline-run", label: "Run offline action", run: () => { throw new Error("must remain gated"); } },
] }]);
assert.equal(inheritedGate[0].disabled, true, "a disabled parent gates descendants projected into universal search");
