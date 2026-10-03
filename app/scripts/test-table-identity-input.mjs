// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import React from "react";
import loadIdentityInput from "./load-identity-input.mjs";

const hooks = [];
let cursor = 0;
let pendingEffects = [];
const fakeReact = {
  ...React,
  useState(initial) {
    const position = cursor++;
    if (!(position in hooks)) hooks[position] = typeof initial === "function" ? initial() : initial;
    return [hooks[position], value => { hooks[position] = typeof value === "function" ? value(hooks[position]) : value; }];
  },
  useEffect(effect, dependencies) {
    const position = cursor++;
    const previous = hooks[position];
    const changed = !previous || dependencies.some((value, index) => !Object.is(value, previous[index]));
    hooks[position] = dependencies;
    if (changed) pendingEffects.push(effect);
  },
};
const IdentityInput = loadIdentityInput(fakeReact);
let value = "source-1";
const commits = [];
let unrelated = "first";
const render = () => {
  cursor = 0;
  pendingEffects = [];
  const tree = IdentityInput({
    value,
    "aria-label": "Source ID",
    placeholder: unrelated,
    onCommit(next) { commits.push(next); value = next; },
    validate: next => !next.trim() ? "ID cannot be blank." : next === "source-2" ? "ID already exists." : "",
  });
  const effects = pendingEffects;
  pendingEffects = [];
  effects.forEach(effect => effect());
  return tree;
};
const input = tree => tree.props.children[0];
const alert = tree => tree.props.children[1];
const change = next => { let tree = render(); input(tree).props.onChange({ target: { value: next } }); return render(); };
const key = (tree, pressed, composing = false) => {
  let prevented = false;
  let stopped = false;
  input(tree).props.onKeyDown({ key: pressed, nativeEvent: { isComposing: composing }, preventDefault() { prevented = true; }, stopPropagation() { stopped = true; } });
  return { prevented, stopped };
};

let tree = render();
tree = change("s");
tree = change("source");
tree = change("source-final");
assert.equal(input(tree).props.value, "source-final");
assert.deepEqual(commits, [], "typing a multi-character ID remains a local draft");
input(tree).props.onBlur();
tree = render();
assert.deepEqual(commits, ["source-final"], "blur commits once");

tree = change("entered-id");
assert.equal(key(tree, "Enter").prevented, true, "Enter is consumed before DataTable navigation");
tree = render();
assert.deepEqual(commits, ["source-final", "entered-id"]);

tree = change("cancel-me");
const escaped = key(tree, "Escape");
assert.equal(escaped.prevented, true);
assert.equal(escaped.stopped, true, "local cancellation does not escape a parent dialog");
tree = render();
assert.equal(input(tree).props.value, "entered-id", "Escape restores the committed identity");
assert.deepEqual(commits, ["source-final", "entered-id"]);

tree = change("composition-in-progress");
assert.deepEqual(key(tree, "Enter", true), { prevented: false, stopped: false }, "IME composition keys are left to the native editor");
assert.deepEqual(commits, ["source-final", "entered-id"]);
key(tree, "Escape");
tree = render();

tree = change("   ");
input(tree).props.onBlur();
tree = render();
assert.deepEqual(commits, ["source-final", "entered-id"], "blank identity does not call the domain callback");
assert.equal(input(tree).props["aria-invalid"], true);
assert.match(alert(tree).props.children, /blank/);

tree = change("source-2");
input(tree).props.onBlur();
tree = render();
assert.deepEqual(commits, ["source-final", "entered-id"], "invalid duplicate does not call the domain callback");
assert.equal(input(tree).props["aria-invalid"], true);
assert.equal(alert(tree).props.role, "alert");

tree = change("staged-value");
assert.equal(tree.props["data-search-text"], "entered-id", "filtering uses the committed identity while a draft is incomplete");
unrelated = "changed";
tree = render();
assert.equal(input(tree).props.value, "staged-value", "unrelated prop changes preserve a staged edit");
value = "external-value";
render();
tree = render();
assert.equal(input(tree).props.value, "external-value", "an external value change replaces the local draft");
assert.match(input(tree).props.title, /Enter or leaving the field applies it/);

console.log("Table identity drafts, commit keys, cancellation, validation, and external synchronization passed.");
