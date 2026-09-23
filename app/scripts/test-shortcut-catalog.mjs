import assert from "node:assert/strict";
import {
  defaultShortcuts,
  fixedShortcuts,
  shortcutGroups,
  shortcutLabels,
} from "../src/shortcutCatalog.ts";

const actions = Object.keys(defaultShortcuts);
assert.ok(actions.length >= 20, "the configurable shortcut catalog should cover the main viewport and workspace commands");
assert.deepEqual(new Set(Object.values(defaultShortcuts)).size, actions.length, "default shortcut keys must be unique");
assert.deepEqual(Object.keys(shortcutLabels).sort(), [...actions].sort(), "every shortcut action needs a label");

const groupedActions = shortcutGroups.flatMap(group => group.actions);
assert.deepEqual(groupedActions.length, actions.length, "every shortcut action must appear in exactly one group");
assert.deepEqual(new Set(groupedActions).size, groupedActions.length, "shortcut groups cannot repeat an action");
assert.deepEqual([...groupedActions].sort(), [...actions].sort(), "shortcut groups must cover the complete catalog");

assert.ok(fixedShortcuts.some(item => item.key === "Ctrl+S"), "file shortcuts should be documented");
assert.ok(fixedShortcuts.some(item => item.key === "Escape"), "selection clearing should be documented");

console.log("shortcut catalog: all assertions passed");
