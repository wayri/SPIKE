// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { defaultShortcuts, fixedShortcuts, shortcutGroups, shortcutLabels, shortcutDescriptors, shortcutPresets, hydrateShortcuts, eventShortcutKey, normalizedShortcutKey, shortcutBindingIssue } from "../src/shortcutCatalog.ts";

const actions = Object.keys(defaultShortcuts);
assert.ok(actions.length >= 65);
for (const [name, preset] of Object.entries(shortcutPresets)) {
  assert.deepEqual(Object.keys(preset).sort(), [...actions].sort(), name);
  assert.ok(Object.values(preset).every(Boolean), `${name} must assign every action`);
  assert.equal(new Set(Object.values(preset)).size, actions.length, `${name} must have unique keys`);
  for (const key of Object.values(preset)) assert.equal(shortcutBindingIssue(key), null, `${name}: ${key}`);
}
assert.deepEqual(Object.keys(shortcutLabels).sort(), [...actions].sort());
assert.deepEqual(Object.keys(shortcutDescriptors).sort(), [...actions].sort());
const grouped = shortcutGroups.flatMap(group => group.actions);
assert.equal(grouped.length, actions.length);
assert.deepEqual([...grouped].sort(), [...actions].sort());
assert.equal(defaultShortcuts.fit, "Home"); assert.equal(defaultShortcuts.flipBoard, "F");
assert.equal(defaultShortcuts.zoomIn, "F1"); assert.equal(defaultShortcuts.zoomOut, "F2");
assert.equal(defaultShortcuts.shortcutWindow, "Ctrl+F1"); assert.equal(defaultShortcuts.focusSelection, "Ctrl+F5");
assert.equal(defaultShortcuts.viewTop, "Z"); assert.equal(defaultShortcuts.viewBottom, "Shift+Z");
assert.equal(defaultShortcuts.viewFront, "Y"); assert.equal(defaultShortcuts.viewBack, "Shift+Y");
assert.equal(defaultShortcuts.viewRight, "X"); assert.equal(defaultShortcuts.viewLeft, "Shift+X");
assert.equal(defaultShortcuts.pivotCursor, "Space");
for (const [input, expected] of [["?", "Shift+/"], ["+", "Shift+="], ["~", "Shift+`"], [" ", "Space"], ["Ctrl++", "Ctrl+Shift+="], ["shift+meta+a", "Ctrl+Shift+A"], ["Ctrl+Ctrl+A", "Ctrl+A"], ["bad key", ""], ["Control", ""], ["Alt+", ""]]) assert.equal(normalizedShortcutKey(input), expected, input);
const event = (key, flags = {}) => ({ key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...flags });
assert.equal(eventShortcutKey(event("p", { ctrlKey: true, shiftKey: true })), "Ctrl+Shift+P");
assert.equal(eventShortcutKey(event("p", { metaKey: true })), "Ctrl+P");
assert.equal(eventShortcutKey(event("?", { shiftKey: true })), "Shift+/");
assert.equal(eventShortcutKey(event("+", { shiftKey: true })), "Shift+=");
assert.equal(eventShortcutKey(event("~", { shiftKey: true })), "Shift+`");
assert.equal(eventShortcutKey(event("ArrowLeft", { shiftKey: true })), "Shift+ArrowLeft");
assert.equal(eventShortcutKey(event("Shift")), "");
assert.equal(eventShortcutKey(event("a", { isComposing: true })), "");
assert.equal(eventShortcutKey(event("a", { getModifierState: key => key === "AltGraph" })), "");
for (const fixed of fixedShortcuts) assert.ok(shortcutBindingIssue(fixed.key), fixed.key);
for (const raw of [undefined, null, [], "bad", 123]) assert.deepEqual(hydrateShortcuts(raw), defaultShortcuts);
const old = hydrateShortcuts({ fit: "F", viewTop: "T", shortcutWindow: "?", zoomIn: "=", zoomOut: "-" });
assert.equal(old.fit, "F"); assert.equal(old.flipBoard, "", "saved F fit wins over new F flip");
assert.equal(old.viewTop, "T"); assert.equal(old.toggleTht, "");
assert.equal(old.shortcutWindow, "Shift+/");
assert.equal(old.zoomIn, "="); assert.equal(old.zoomOut, "-");
const malformed = hydrateShortcuts({ fit: "Ctrl+K", zoomIn: {}, zoomOut: "Control", fakeAction: "A", viewTop: "", viewBottom: "P", orbitMode: "P" });
assert.equal(malformed.fit, "Home"); assert.equal(malformed.zoomIn, "F1");
assert.equal(malformed.viewTop, ""); assert.equal(malformed.orbitMode, "P"); assert.equal(malformed.viewBottom, "");
const valid = Object.values(malformed).filter(Boolean);
assert.equal(valid.length, new Set(valid).size);
assert.deepEqual(hydrateShortcuts(old), old, "saved blanks survive round trip");
console.log("shortcut catalog, event normalization and saved-map migration: passed");
