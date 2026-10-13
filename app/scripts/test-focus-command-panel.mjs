// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { focusCommandsFromElements, searchFocusCommands } = await importTestTypescript("focusCommands");
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
