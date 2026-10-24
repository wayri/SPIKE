// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { scopeViewportContextGroups } = await importTestTypescript("viewportContextPolicy");
const action = (id, disabledReason) => ({ id, label: id, disabledReason, run() {} });
const groups = [
  { id: "suggested", label: "Suggested", actions: [action("pi-net"), action("si-eye"), action("thermal-history"), action("fit")] },
  { id: "workspace", label: "Workspace", actions: [action("open-project")] },
  { id: "inspect", label: "Inspect", actions: [action("inspect-object"), action("probe"), action("schematic"), action("isolate-net")] },
  { id: "view", label: "View", actions: [action("fit"), action("focus-layer")] },
  { id: "edit", label: "Clipboard", actions: [action("copy"), action("paste", "Nothing compatible to paste")] },
  { id: "pi-si", label: "Integrity", actions: [action("pi-net"), action("pi-DC IR Drop"), action("si-eye"), action("spice")] },
  { id: "thermal-em", label: "Fields", actions: [action("thermal-setup"), action("thermal-history", "Load a thermal result first"), action("em-net"), action("model-resolver"), action("engines")] },
  { id: "results", label: "Results", actions: [action("result-voltage"), action("result-plots", "Load a result first"), action("playback"), action("studies"), action("report")] },
  { id: "assembly", label: "Assembly", actions: [action("assembly-workspace"), action("links", "Create an assembly first")] },
  { id: "automation", label: "Automation", actions: [action("copy-context"), action("validate"), action("delete-terminal")] },
];
const base = { selectionType: "trace", selectionHasNet: true, selectionOwnedByActiveBoard: true, hasSavedResult: false, hasThermalTarget: false, hasAssembly: false };
const ids = scoped => scoped.flatMap(group => group.actions.map(item => item.id));
const search = (scoped, query) => scoped.flatMap(group => group.actions.filter(item => `${group.label} ${item.label}`.toLowerCase().includes(query)).map(item => item.id));

let scoped = scopeViewportContextGroups(groups, { ...base, activeWorkspace: "PI" });
assert(ids(scoped).includes("pi-DC IR Drop"));
assert.equal(scoped.find(group=>group.id==="pi-si").label,"Power integrity");
assert(!ids(scoped).includes("si-eye") && !ids(scoped).includes("thermal-setup") && !ids(scoped).includes("em-net"));
assert.deepEqual(search(scoped, "si-eye"), [], "search sees only the already scoped action inventory");
assert(ids(scoped).includes("copy") && ids(scoped).includes("paste"), "clipboard actions and disabled explanations remain");

scoped = scopeViewportContextGroups(groups, { ...base, activeWorkspace: "HF / SI", hasSavedResult: true });
assert(ids(scoped).includes("si-eye") && ids(scoped).includes("result-voltage"));
assert(!ids(scoped).includes("pi-net") && !ids(scoped).includes("thermal-setup") && !ids(scoped).includes("em-net"));

scoped = scopeViewportContextGroups(groups, { ...base, activeWorkspace: "Thermal", selectionType: "mechanical", selectionHasNet: false, hasThermalTarget: true, hasAssembly: true });
assert(ids(scoped).includes("thermal-setup") && ids(scoped).includes("thermal-history") && ids(scoped).includes("assembly-workspace"));
for (const hidden of ["probe", "schematic", "isolate-net", "focus-layer", "pi-net", "si-eye", "em-net", "delete-terminal"]) assert(!ids(scoped).includes(hidden), hidden);
assert.equal(scoped.find(group => group.id === "thermal-em").actions.find(item => item.id === "thermal-history").disabledReason, "Load a thermal result first");

scoped = scopeViewportContextGroups(groups, { ...base, activeWorkspace: "EM" });
assert(ids(scoped).includes("em-net") && !ids(scoped).includes("thermal-setup"));
scoped = scopeViewportContextGroups(groups, { ...base, activeWorkspace: "Results" });
assert(ids(scoped).includes("result-plots") && ids(scoped).includes("studies"));
scoped = scopeViewportContextGroups(groups, { ...base, activeWorkspace: "Mesh" });
assert(ids(scoped).includes("pi-net") && ids(scoped).includes("engines"));
scoped = scopeViewportContextGroups(groups, { ...base, activeWorkspace: "PI", selectionOwnedByActiveBoard: false });
assert(!ids(scoped).includes("pi-net"), "foreign board selections cannot expose PI actions");

console.log("Viewport context policy scopes workspace, selection, result, thermal and assembly actions before search while retaining relevant disabled actions.");
