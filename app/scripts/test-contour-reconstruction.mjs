// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const compiled = name => ts.transpileModule(readFileSync(new URL(`../src/${name}.ts`, import.meta.url), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const url = text => `data:text/javascript;base64,${Buffer.from(text).toString('base64')}`;
const numericUrl = url(compiled('numericRange'));
const { interpolateDisplayValue, buildContourGrid, connectedContourSampleGroups, contourGridTriangleSamples, matchViaStressSamples, sampleFaceSupport, viaStressAnnulusPath } = await import(url(compiled('contourField').replace('"./numericRange"', JSON.stringify(numericUrl))));
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
const masked=buildContourGrid(samples,{maximumGridVertices:400,supportsPoint:(x,y)=>x<=.6&&y<=.9});
assert.ok(masked && masked.vertices.filter(Boolean).every(vertex=>vertex.xMm<=.6&&vertex.yMm<=.9),'display grid is clipped by conductor support');
const triangles=contourGridTriangleSamples(masked,samples[0]);
assert.ok(triangles.length>0 && triangles.every(sample=>sample.vertices_mm.length===3),'clipped grid emits triangle display samples');
assert.ok(triangles.every(sample=>sample.value>=2&&sample.value<=5.5),'display triangles remain inside solver extrema');
const vias=[{id:'via-4',at:[10,20],size:1,drill:.4,net:'PWR'},{id:'via-40',at:[30,20],size:1,drill:.4,net:'PWR'}];
const viaGlyphs=matchViaStressSamples([
  {x_mm:10.45,y_mm:20,value:2,net:'PWR',element_id:'via-4:barrel:1:face:1'},
  {x_mm:10,y_mm:20.45,value:7,net:'PWR',element_id:'via-4:barrel:1:face:2'},
  {x_mm:30.45,y_mm:20,value:3,net:'PWR'},
  {x_mm:99,y_mm:99,value:100,net:'PWR'},
],vias);
assert.equal(viaGlyphs.length,2,'only samples belonging to board vias become footprints');
assert.equal(viaGlyphs.find(entry=>entry.via.id==='via-4').value,7,'via footprint retains peak returned barrel stress');
assert.equal(viaGlyphs.find(entry=>entry.via.id==='via-4').sampleCount,2,'barrel faces collapse into one via footprint');
const annulus=viaStressAnnulusPath({id:'v',at:[10,20],size:2,drill:.8});
assert.match(annulus,/^M9,20a1,1/,'outer stress path uses the exact via diameter');
assert.match(annulus,/ M9\.6,20a0\.4,0\.4/,'inner stress path uses the exact drill diameter');
assert.equal((annulus.match(/Z/g)??[]).length,2,'via stress is a ring with a drill contour');
const face=(x0,x1)=>({x_mm:(x0+x1)/2,y_mm:.5,value:x0,net:'N',layer:'F.Cu',vertices_mm:[[x0,0,0],[x1,0,0],[x1,1,0],[x0,1,0]]});
const connected=[face(0,1),face(1,2)];
const separated=face(3,4);
const groups=connectedContourSampleGroups([...connected,separated]);
assert.deepEqual(groups.map(group=>group.length).sort((a,b)=>a-b),[1,2],'only complete shared edges establish smoothing connectivity');
const faceMask=sampleFaceSupport(connected);
assert.equal(faceMask(.5,.5),true); assert.equal(faceMask(1.5,.5),true);
assert.equal(faceMask(2.5,.5),false,'smooth coverage cannot cross a solver face void');
console.log('Contour reconstruction: affine/exact/connectivity/mask/range/budget/source/annular-via preservation passed');
