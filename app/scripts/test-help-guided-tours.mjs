// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url), cache = new Map();
let state = { flowId: null, step: 0 };
let reducerInitial;
function load(file) {
  if (cache.has(file)) return cache.get(file);
  const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', output)(name => {
    if (name.endsWith('.css')) return {};
    if (name === 'react') return { ...React, useReducer: (reducer, initialState) => { reducerInitial = initialState; return [state, action => { state = reducer(state, action); }]; }, useEffect: () => {}, useRef: value => ({ current: value }) };
    if (!name.startsWith('.')) return require(name);
    const base = path.resolve(path.dirname(file), name);
    return load(['.ts', '.tsx'].map(ext => base + ext).find(candidate => fs.existsSync(candidate)) ?? base);
  }, mod, mod.exports);
  cache.set(file, mod.exports);
  return mod.exports;
}
const { helpGuidedFlows: flows, helpGuideReducer: reducer, initialHelpGuideState: initial } = load(path.join(root, 'src/helpGuidedFlows.ts'));
const { default: Tours, HelpGuideStepContent } = load(path.join(root, 'src/HelpGuidedTours.tsx'));
function elements(node) {
  if (!React.isValidElement(node)) return [];
  return [node, ...React.Children.toArray(node.props.children).flatMap(elements)];
}
function button(tree, label) {
  return elements(tree).find(element => element.type === 'button' && React.Children.toArray(element.props.children).join('') === label);
}
assert.equal(new Set(flows.map(flow => flow.id)).size, flows.length);
assert.equal(flows.length, 8);
assert.deepEqual(reducer(initial, { type: 'next' }), initial);
assert.deepEqual(reducer(initial, { type: 'choose', flowId: 'missing' }), initial);
Tours({ initialFlow: flows[1].id });
assert.deepEqual(reducerInitial, { flowId: flows[1].id, step: 0 });
Tours({ initialFlow: 'missing' });
assert.deepEqual(reducerInitial, initial);
const chooser = Tours({});
assert.match(renderToStaticMarkup(chooser), /What would you like to do/);
const cards = elements(chooser).filter(element => element.props.className === 'help-guide-task');
assert.equal(cards.length, flows.length);
cards[0].props.onClick();
assert.equal(state.flowId, flows[0].id);
assert.equal(state.step, 0);
assert.equal(button(Tours({}), 'Back').props.disabled, true);
button(Tours({}), 'Next step').props.onClick();
assert.equal(state.step, 1);
button(Tours({}), 'Back').props.onClick();
assert.equal(state.step, 0);

for (const flow of flows) {
  assert.ok(flow.prerequisites.length && flow.outcome);
  state = reducer(state, { type: 'choose', flowId: flow.id });
  state = reducer(state, { type: 'back' });
  assert.equal(state.step, 0, 'Back must not move before first step');
  state = reducer(state, { type: 'step', index: 999 });
  assert.equal(state.step, flow.steps.length - 1, 'Step must stay in bounds');
  state = reducer(state, { type: 'next' });
  assert.equal(state.step, flow.steps.length - 1, 'Next must not move past last step');
  assert.deepEqual(reducer(state, { type: 'step', index: NaN }), state);
  assert.ok(button(Tours({}), 'Choose another task'));
  const last = Tours({});
  assert.equal(elements(last).filter(element => element.props['aria-current'] === 'step').length, 1);
  button(last, 'Choose another task').props.onClick();
  assert.deepEqual(state, initial);
  for (const [index, step] of flow.steps.entries()) {
    assert.ok(step.action && step.expected && step.recovery && step.image.alt && step.image.caption && step.references.length);
    const imagePath = step.image.src;
    assert.match(imagePath, /^\/help\/(?:guides-current|ui-current)\/[a-z-]+\.jpg$/);
    assert.ok(fs.existsSync(path.join(root, 'public', imagePath)), `Missing screenshot ${imagePath}`);
    const bounds = step.image.highlight;
    for (const value of [bounds.x, bounds.y, bounds.width, bounds.height]) assert.ok(Number.isFinite(value));
    assert.ok(bounds.x >= 0 && bounds.y >= 0 && bounds.width > 0 && bounds.height > 0);
    assert.ok(bounds.x + bounds.width <= 100 && bounds.y + bounds.height <= 100, `${flow.id} highlight outside screenshot`);
    assert.ok(bounds.label);
    const props = { step, number: index + 1 };
    const markup = renderToStaticMarkup(React.createElement(HelpGuideStepContent, props));
    for (const label of ['Do this', 'What you should see', 'If you get stuck', 'data-help-image', 'Enlarge screenshot:', 'aria-hidden="true"']) assert.ok(markup.includes(label));
    assert.ok(markup.includes(`Highlight ${index + 1}: ${bounds.label}`), 'Highlight needs a visible text equivalent');
    for (const ref of step.references) {
      if (ref.topic.startsWith('doc:')) assert.ok(fs.existsSync(path.resolve(root, '..', ref.topic.slice(4))), `Missing reference ${ref.topic}`);
    }
    let destination;
    const tree = HelpGuideStepContent({ ...props, onNavigate: (...args) => { destination = args; } });
    const link = elements(tree).find(element => element.type === 'a');
    let prevented = false, stopped = false;
    link.props.onClick({ preventDefault() { prevented = true; }, stopPropagation() { stopped = true; } });
    assert.deepEqual(destination, [step.references[0].topic, step.references[0].anchor]);
    assert.ok(prevented && stopped, 'Reference callback must prevent duplicate parent navigation');
  }
}
console.log('Guided Help: task selection, next/back boundaries, reset, reference navigation, accessible step content and screenshot bounds passed.');

const manifest = JSON.parse(fs.readFileSync(path.join(root, 'public/help/guides-current/manifest.json'), 'utf8'));
const names = new Set(manifest.captures.map(item => item.file));
for (const item of manifest.captures) {
  const bytes = fs.readFileSync(path.join(root, 'public/help/guides-current', item.file));
  assert.equal(createHash('sha256').update(bytes).digest('hex'), item.sha256, `Stale capture provenance: ${item.file}`);
  assert.equal(bytes.readUInt16BE(0), 0xffd8, `Expected original JPEG: ${item.file}`);
  assert.equal(item.pixel_edits, false);
  assert.equal(item.numerical_solve_demonstrated, false);
}
for (const flow of flows) for (const step of flow.steps) assert.ok(names.has(path.basename(step.image.src)), `Guide screenshot missing provenance: ${step.image.src}`);
const center = fs.readFileSync(path.join(root, 'src/HelpCenter.tsx'), 'utf8');
assert.ok(center.includes('...helpGuidedFlows.map'), 'Every guided task must be indexed in Help search');
assert.ok(center.includes('"../../docs/PICTURE_WALKTHROUGHS.md"'), 'Offline Help must include the illustrated guide');
console.log('Capture hashes, original JPEG provenance and offline Help integration passed.');
