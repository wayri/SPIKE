// SPDX-License-Identifier: MIT
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const compiled = name => ts.transpileModule(readFileSync(new URL(`../src/${name}.ts`, import.meta.url), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const url = text => `data:text/javascript;base64,${Buffer.from(text).toString('base64')}`;
const numericUrl = url(compiled('numericRange'));
const { interpolateDisplayValue, buildContourGrid } = await import(url(compiled('contourField').replace('"./numericRange"', JSON.stringify(numericUrl))));
const plane = (x, y) => 2 + 3 * x + 0.5 * y;
const samples = [[0,0], [1,0], [0,1], [1,1]].map(([x_mm,y_mm]) => ({x_mm,y_mm,value:plane(x_mm,y_mm),width_mm:1}));
assert.ok(Math.abs(interpolateDisplayValue(samples,.25,.4)-plane(.25,.4)) < 1e-10, 'affine display field reproduced inside support');
assert.equal(interpolateDisplayValue(samples,0,0),2,'original sample exact');
assert.equal(interpolateDisplayValue([],0,0),undefined);
assert.ok(Number.isFinite(interpolateDisplayValue(samples.slice(0,2),.4,0)), 'collinear fit safely falls back');
assert.ok(interpolateDisplayValue(samples,3,3) <= 5.5, 'no extrapolated extrema');
const dense=Array.from({length:1000},(_,i)=>({x_mm:i%40,y_mm:Math.floor(i/40),value:i===523?1e3:i===512?-500:1,width_mm:1}));
const before=JSON.stringify(dense);
const grid=buildContourGrid(dense,{maximumSourceSamples:100,maximumGridVertices:100});
assert.ok(grid && grid.vertices.length<=100);
assert.equal(grid.maximum,1000); assert.equal(grid.minimum,-500);
assert.equal(grid.sourceSamples.length,1000,'cursor retains all original source samples');
assert.equal(JSON.stringify(dense),before,'solver data unchanged');
console.log('Contour reconstruction: affine/exact/degenerate/range/budget/source preservation passed');
