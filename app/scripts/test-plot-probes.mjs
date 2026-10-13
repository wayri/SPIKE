// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const modules = new Map();
function load(name) {
  if (modules.has(name)) return modules.get(name);
  const js = ts.transpileModule(readFileSync(new URL(`../src/${name}.ts`, import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const module = { exports: {} };
  new Function('require', 'module', 'exports', js)(dep => load(dep.replace('./', '')), module, module.exports);
  modules.set(name, module.exports); return module.exports;
}
const { sampleProbe, probeDelta, probeTable } = load('plotProbes');
const data = [{ name: 'S21', x: new Float64Array([1,2]), y: [-3,-5] }, { name: '=pasted', x: [2], y: [4], yaxis: 'y2' }];
const layout = { xaxis: { title: 'Frequency (GHz)' }, yaxis: { title: { text: 'Magnitude (dB)' } }, yaxis2: { title: 'Voltage (V)' } };
const a = sampleProbe(data, layout, { curveNumber: 0, pointNumber: 0 }, 1);
const b = sampleProbe(data, layout, { curveNumber: 0, pointNumber: 1 }, 1);
assert.deepEqual(probeDelta([a,b]), { x: 1, y: -2 });
const pasted = sampleProbe(data, layout, { curveNumber: 1, pointNumber: 0 }, 1);
assert.equal(pasted.comparison, true); assert.equal(pasted.yLabel, 'Voltage (V)');
assert.equal(probeDelta([a,pasted]), null, 'incompatible axes cannot produce a delta');
assert.match(probeTable([pasted]), /'=pasted/);
assert.equal(sampleProbe([{ x: [1], y: [null] }], layout, { curveNumber: 0, pointNumber: 0 }, 1), null);
assert.equal(sampleProbe([{ type: 'heatmap', x: [1], y: [2] }], layout, { curveNumber: 0, pointNumber: 0 }, 1), null);
assert.equal(sampleProbe(data, layout, { curveNumber: 0, pointNumber: 99 }, 1), null);
const source = readFileSync(new URL('../src/InteractivePlot.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('plot.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let effect;
function visit(node) {
  if (ts.isCallExpression(node) && node.expression.getText(ast) === 'useEffect' && ts.isArrowFunction(node.arguments[0]) && node.arguments[0].body.getText(ast).includes('const click =')) effect = node.arguments[0].body.getText(ast);
  ts.forEachChild(node, visit);
}
visit(ast); assert.ok(effect);
let probes = [], clicked = 0, selected = [];
const handlers = new Map(), graph = { on: (event, fn) => handlers.set(event, fn), removeListener: event => handlers.delete(event) };
const compiledEffect = ts.transpileModule(`function mount(host,ready,state,controls,sampleProbe,setProbes) ${effect}`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
const mount = new Function(`${compiledEffect}; return mount;`)();
mount({current:graph}, 1, {loading:false}, {current:{data:[data[0]],comparisons:[data[1]],layout,onPointClick:()=>clicked++,onSelectSamples:ids=>selected=ids}}, sampleProbe, fn => {probes=fn(probes);});
handlers.get('plotly_click')({points:[{curveNumber:0,pointNumber:0,x:1,y:-3}]});
handlers.get('plotly_click')({points:[{curveNumber:0,pointNumber:1,x:2,y:-5}]});
assert.equal(probes.length, 2); assert.equal(clicked, 2); assert.deepEqual(selected, [1]);
handlers.get('plotly_click')({points:[{curveNumber:1,pointNumber:0,x:2,y:4}]});
assert.equal(probes.length, 1); assert.equal(probes[0].comparison, true); assert.equal(clicked, 2, 'comparison cannot select a solver sample');
console.log('exact pinned samples, compatible deltas, comparison isolation and production click handler passed');
