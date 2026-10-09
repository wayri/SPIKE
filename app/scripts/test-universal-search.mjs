// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import React from 'react';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const states = [], refs = [], effects = [];
let stateIndex = 0, refIndex = 0, mounting = true;
const body = {}, trigger = { isConnected: true, focus() { document.activeElement = this; } };
globalThis.document = { body, activeElement: trigger };
globalThis.requestAnimationFrame = fn => { fn(); return 1; };
globalThis.cancelAnimationFrame = () => {};
const module = { exports: {} };
const source = readFileSync(new URL('../src/UniversalSearch.tsx', import.meta.url), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
}}).outputText;
new Function('require', 'module', 'exports', code)(name => {
  if (name === 'react') return { ...React,
    useState(initial) { const index = stateIndex++; states[index] ??= initial; return [states[index], value => { states[index] = typeof value === 'function' ? value(states[index]) : value; }]; },
    useRef(initial) { return refs[refIndex++] ??= { current: initial }; },
    useMemo: callback => callback(), useEffect: callback => { if (mounting) effects.push(callback); },
  };
  if (name === './icons') return { ArrowRight: () => null, Search: () => null, X: () => null };
  return require(name);
}, module, module.exports);
const runs = [], closed = [];
const items = [
  { id: 'disabled', label: 'Run active PI analysis', category: 'Analysis', disabled: true, run: () => runs.push('disabled') },
  { id: 'ready', label: 'Open results', category: 'Results', run: () => runs.push('ready') },
];
const render = () => { stateIndex = 0; refIndex = 0; return module.exports.default({ open: true, items, onClose: () => closed.push('close') }); };
const descendants = element => !element || typeof element !== 'object' ? [] : [element, ...React.Children.toArray(element.props?.children).flatMap(descendants)];
let tree = render();
const first = { focus() { document.activeElement = this; } }, last = { focus() { document.activeElement = this; } };
const dialog = { contains: value => value === first || value === last, querySelectorAll: () => [first, last] };
refs[0].current = first; refs[1].current = dialog;
const cleanups = effects.map(effect => effect()); mounting = false;
assert.equal(document.activeElement, first, 'opening search focuses input');
const input = descendants(tree).find(item => item.type === 'input');
input.props.onChange({ target: { value: 'Run active PI analysis' } });
tree = render();
assert.equal(descendants(tree).filter(item => item.props?.role === 'option').length, 0, 'disabled commands never become exact-match keyboard targets');
input.props.onChange({ target: { value: 'Open results' } }); tree = render();
const option = descendants(tree).find(item => item.props?.role === 'option');
assert.equal(option.props['aria-selected'], true);
const section = descendants(tree).find(item => item.props?.role === 'dialog');
const event = (key, patch = {}) => ({ key, currentTarget: dialog, shiftKey: false, nativeEvent: { isComposing: false }, preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; }, ...patch });
document.activeElement = last;
const escape = event('Escape'); section.props.onKeyDown(escape);
assert.equal(closed.length, 1, 'Escape closes search from a result button');
assert.ok(escape.prevented && escape.stopped, 'Escape cannot clear underlying viewport selection');
const tab = event('Tab'); section.props.onKeyDown(tab);
assert.equal(document.activeElement, first, 'Tab wraps at last control');
const reverse = event('Tab', { shiftKey: true }); section.props.onKeyDown(reverse);
assert.equal(document.activeElement, last, 'Shift+Tab wraps at first control');
const currentInput = descendants(tree).find(item => item.type === 'input');
currentInput.props.onKeyDown(event('Enter', { nativeEvent: { isComposing: true } }));
assert.deepEqual(runs, [], 'IME composition cannot execute a command');
currentInput.props.onKeyDown(event('Enter'));
assert.deepEqual(runs, ['ready']);
document.activeElement = first; cleanups.forEach(cleanup => cleanup?.());
assert.equal(document.activeElement, trigger, 'dismissal restores the invoking control');
stateIndex = 0; refIndex = 0;
assert.equal(module.exports.default({ open: false, items: [{ get label() { throw new Error('closed search must not rank'); } }], onClose() {} }), null);
states[0] = ''; stateIndex = 0; refIndex = 0;
let checkedItems = 0;
const largeInventory = Array.from({ length: 50000 }, (_, id) => ({ id: String(id), label: `Net ${id}`, category: 'Nets',
  get disabled() { checkedItems++; return false; }, run() {} }));
const initialTree = module.exports.default({ open: true, items: largeInventory, onClose() {} });
assert.equal(descendants(initialTree).filter(item => item.props?.role === 'option').length, 14);
assert.equal(checkedItems, 28, 'only 14 suggestions are checked and rendered in a 50,000-item inventory');
console.log('Universal search availability, focus, keyboard, and composition tests passed');
