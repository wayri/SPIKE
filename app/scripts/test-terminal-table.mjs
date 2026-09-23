import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

const require = createRequire(import.meta.url);
let expanded = null;
const module = { exports: {} };
const compiled = ts.transpileModule(fs.readFileSync(new URL('../src/TerminalTable.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
new Function('require', 'module', 'exports', compiled)(name => name.endsWith('.css') ? {} : name === 'react'
  ? { ...React, useState: () => [expanded, value => { expanded = value; }] } : require(name), module, module.exports);
const Table = module.exports.default;
const rows = Array.from({ length: 100 }, (_, i) => ({ id: `s${i}`, name: `Source ${i}`, x: '1', y: '2', layer: 'auto', value: '3.3', contactResistance: '0', packageResistance: '0' }));
let details = 0;
const edits = [], removed = [];
const props = { rows, label: 'Voltage sources · VCC', layers: ['F.Cu', 'B.Cu'], valueLabel: 'Voltage (V)', onChange: (...args) => edits.push(args), onRemove: id => removed.push(id), renderDetails: item => { details++; return React.createElement('p', null, item.id); } };
const nodes = node => !node || typeof node !== 'object' ? [] : Array.isArray(node)
  ? node.flatMap(nodes) : [node, ...nodes(node.props?.children)];
let tree = Table(props);
let html = renderToStaticMarkup(tree);
assert.equal(details, 0, 'collapsed rows must not scan pads or render waveform editors');
assert.match(html, /<table/);
assert.equal((html.match(/<tr>/g) ?? []).length, 101);
assert.match(html, /Voltage sources · VCC · 100 terminals/);
nodes(tree).find(n => n.props?.['aria-label'] === 'Edit pads and details for Source 0').props.onClick();
tree = Table(props);
assert.equal(details, 1);
nodes(tree).find(n => n.props?.['aria-label'] === 'Voltage sources · VCC: Source 0 X (mm)').props.onChange({ target: { value: '12.5' } });
assert.deepEqual(edits.pop(), ['s0', { x: '12.5' }]);
nodes(tree).find(n => n.props?.['aria-label'] === 'Remove Source 0').props.onClick();
assert.deepEqual(removed, ['s0']);
nodes(tree).find(n => n.props?.['aria-label'] === 'Edit pads and details for Source 1').props.onClick();
details = 0; Table(props); assert.equal(details, 1, 'only one detail editor is mounted');
expanded = null;
html = renderToStaticMarkup(Table({ ...props, readOnlyValue: () => '1 A return' }));
assert.match(html, /1 A return/);
assert.ok(!html.includes('Source 0 Voltage (V)'));
html = renderToStaticMarkup(Table({ ...props, transient: true }));
assert.match(html, /Edit waveform/);
assert.ok(!html.includes('Source 0 Voltage (V)'));
assert.match(renderToStaticMarkup(Table({ ...props, rows: [] })), /No terminals/);
const app = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
assert.match(app, /rows=\{job\?\.\[kind\] \?\? setup\[kind\]\}/);
assert.match(app, /rows=\{setup\.returnPath\[kind\]\}/);
assert.ok(app.includes('"x" in patch || "y" in patch ? { anchorId: "", anchorType: "coordinate"'), 'coordinate edits must detach pad anchors');
console.log('Terminal table rendering, lazy 100-row detail editor, edits, remove, return, transient and batch wiring passed.');
