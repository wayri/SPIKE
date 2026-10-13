// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import React from "react";
import ts from "typescript";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { importTestTypescript } from "./import-test-typescript.mjs";
const transientModel = await importTestTypescript("thermalTransientPresentation");
const model = await importTestTypescript("assemblyThermalVolumePlot");
const { assemblyThermalVolumePlot: plot, prepareThermalVolumeGeometry, thermalVolumeField, thermalVolumeSurface, renderThermalVolumePlot } = model;
const handoff = { handoff_digest: "h", request_digest: "r", assembly_digest: "a", mesh: { units: "m", vertices: [[0,0,0],[.01,0,0],[0,.01,0],[.02,0,0],[.03,0,0],[.02,.01,0]] },
  boundary_faces: [{ occurrence_id: "left", vertices: [0,1,2] }, { occurrence_id: "right", vertices: [3,4,5] }] };
const result = { contract: "spike/assembly-field-thermal-result/v1", model_status: "experimental", production_qualified: false, handoff_digest: "h", request_digest: "r", assembly_digest: "a", field_result: {
  status: "experimental", production_qualified: false, temperature_units: "K", node_temperatures_k: [300,301,302,310,311,312] } };
const before = JSON.stringify([handoff,result]);
let out = plot(handoff,result,"right","K");
assert.equal(out.hasTemperature,true);
assert.deepEqual(out.traces[0].x,[20,30,20]);
assert.deepEqual(out.traces[0].i,[0]);
assert.deepEqual(out.traces[0].j,[1]);
assert.deepEqual(out.traces[0].k,[2]);
assert.deepEqual(out.traces[0].intensity,[310,311,312]);
assert.equal(out.traces[0].cmin,300); // Global color range survives occurrence filtering.
assert.equal(out.traces[0].cmax,312);
out=plot(handoff,result,"","C");
assert.ok(Math.abs(out.traces[0].intensity[0]-26.85)<1e-10);
assert.match(out.traces[0].colorbar.title.text,/deg C/);
assert.equal(JSON.stringify([handoff,result]),before);
for (const invalid of [null,{...result,handoff_digest:"stale"},{...result,field_result:{...result.field_result,temperature_units:"C"}},
  {...result,field_result:{...result.field_result,node_temperatures_k:[300]}},
  {...result,field_result:{...result.field_result,node_temperatures_k:[NaN,301,302,310,311,312]}}]) {
  out=plot(handoff,invalid);
  assert.equal(Boolean(out.hasTemperature),false);
  assert.equal(out.traces[0].intensity,undefined);
}
assert.ok(plot({...handoff,mesh:{...handoff.mesh,units:"mm"}},result).error);
assert.ok(plot({...handoff,boundary_faces:[{occurrence_id:"bad",vertices:[0,1,99]}]},result).error);
assert.ok(plot(handoff,result,"missing").error);
console.log("Assembly thermal surface geometry, temperature binding, units and occurrence mapping passed.");

const external = {...result,contract:"spike/calculix-thermal-result/v1"};
assert.equal(plot(handoff,external,"right","K").hasTemperature,true);
assert.deepEqual(plot(handoff,external,"right","K").traces[0].intensity,[310,311,312]);
assert.equal(plot(handoff,{...external,assembly_digest:"stale"}).hasTemperature,false);
assert.match(plot(handoff,{...external,request_digest:"stale"}).notice,/mismatched request_digest/);

// Real interior topology includes a hot node absent from the selected surface.
const volume = { ...handoff, mesh: { ...handoff.mesh, vertices: [...handoff.mesh.vertices,[0,0,.01],[.02,0,.01]],
  cells: [{ vertices:[0,1,2,6] },{ vertices:[3,4,5,7] }] },
  source_traceability: [{occurrence_id:"left",vertex_range:[0,3]},{occurrence_id:"right",vertex_range:[3,8]}] };
// Store disjoint, contiguous occurrence node ranges, as the worker does.
volume.mesh.vertices = [[0,0,0],[.01,0,0],[0,.01,0],[0,0,.01],[.02,0,0],[.03,0,0],[.02,.01,0],[.02,0,.01]];
volume.mesh.cells = [{kind:"tetrahedron",vertices:[0,1,2,3]},{kind:"tetrahedron",vertices:[4,5,6,7]}];
volume.boundary_faces = [{occurrence_id:"left",vertices:[0,1,2]},{occurrence_id:"right",vertices:[4,5,6]}];
volume.source_traceability = [{occurrence_id:"left",vertex_range:[0,4]},{occurrence_id:"right",vertex_range:[4,8]}];
const fieldResult = {...external,field_result:{...result.field_result,node_temperatures_k:[300,301,302,350,310,311,312,320]}};
const geometry = prepareThermalVolumeGeometry(volume), field = thermalVolumeField(geometry,fieldResult);
assert.equal(geometry.interiorAvailable,true);
assert.deepEqual(field.stats,[{occurrence:"left",count:4,minimum:300,maximum:350},{occurrence:"right",count:4,minimum:310,maximum:320}]);
const selected = thermalVolumeSurface(geometry,"right","volume");
out = renderThermalVolumePlot(geometry,field,selected,"K");
assert.equal(out.traces.length,3);
assert.equal(out.traces[0].opacity,.15);
assert.equal(out.traces[0].cmax,350,"global range includes another occurrence's interior hotspot");
assert.equal(out.traces[1].x.length,18,"one tetrahedron has six unique edges, each separated by null");
assert.deepEqual(out.traces[2].marker.color,[310,311,312,320]);
assert.equal(out.traces[2].marker.cmax,350);
assert.deepEqual(out.traces[2].customdata[3],["right",7,320,320]);
assert.match(out.traces[2].hovertemplate,/Occurrence/);
assert.strictEqual(out.traces[0].x,selected.surface.x,"render controls reuse geometry arrays");
assert.strictEqual(renderThermalVolumePlot(geometry,field,selected,"C").traces[0].x,out.traces[0].x);
out=plot(volume,fieldResult,"left","K",{mode:"geometry",edges:"volume"});
assert.equal(out.hasTemperature,true);
assert.equal(out.showTemperature,false);
assert.equal(out.traces[0].intensity,undefined);
assert.equal(typeof out.traces[2].marker.color,"string");
assert.equal(plot(handoff,result,"","K",{edges:"surface"}).traces[1].x.length,18);
assert.match(plot(handoff,result,"","K",{edges:"volume"}).notice,/Interior inspection requires/);
assert.ok(prepareThermalVolumeGeometry({...volume,source_traceability:[{occurrence_id:"left",vertex_range:[0,5]},{occurrence_id:"right",vertex_range:[4,8]}]}).error);
assert.equal(prepareThermalVolumeGeometry({...volume,mesh:{...volume.mesh,cells:Array(5001).fill(volume.mesh.cells[0])}}).interiorAvailable,false);
for(const invalid of [Infinity,-1,"300",null]) {
  const samples=[...fieldResult.field_result.node_temperatures_k]; samples[3]=invalid;
  assert.equal(plot(volume,{...fieldResult,field_result:{...fieldResult.field_result,node_temperatures_k:samples}},"right").hasTemperature,false,"invalid hidden occurrence sample withholds every overlay");
}
assert.equal(plot(volume,{...fieldResult,model_status:"qualified"}).hasTemperature,false);
assert.equal(plot(volume,{...fieldResult,production_qualified:true}).hasTemperature,false);
const sparseSamples=[...fieldResult.field_result.node_temperatures_k];delete sparseSamples[3];
assert.equal(plot(volume,{...fieldResult,field_result:{...fieldResult.field_result,node_temperatures_k:sparseSamples}}).hasTemperature,false);
const sparseVertices=[...volume.mesh.vertices];delete sparseVertices[3];
assert.ok(plot({...volume,mesh:{...volume.mesh,vertices:sparseVertices}},fieldResult).error);
assert.equal(prepareThermalVolumeGeometry({...volume,mesh:{...volume.mesh,cells:[{kind:"quadrilateral",vertices:[0,1,2,3]}]}}).interiorAvailable,false);
assert.ok(plot({...handoff,mesh:{...handoff.mesh,vertices:[[1e308,0,0],...handoff.mesh.vertices.slice(1)]}},result).error);
for(const kelvin of [0,300,Number.MAX_VALUE]) {
  out=plot(handoff,{...result,field_result:{...result.field_result,node_temperatures_k:Array(6).fill(kelvin)}},"","K");
  assert.ok(Number.isFinite(out.traces[0].cmin)&&Number.isFinite(out.traces[0].cmax)&&out.traces[0].cmin<out.traces[0].cmax,"isothermal scale stays finite and nonzero");
}
const many = {...handoff,mesh:{units:"m",vertices:Array.from({length:21000},(_,i)=>[i/1000,0,0])},boundary_faces:Array.from({length:7000},(_,i)=>({occurrence_id:"left",vertices:[3*i,3*i+1,3*i+2]}))};
out=plot(many,null,"","C",{edges:"surface"});
assert.equal(out.traces.length,1,"resource cap never creates a partial edge trace");
assert.match(out.notice,/20,000 unique edges/);
console.log("Global scale, interior samples, occurrence extrema, geometry reuse and bounded mesh inspection passed.");

// Exercise the real component's controls and memo boundaries without a WebGL mock result.
const require = createRequire(import.meta.url);
let slots = [], cursor = 0, effects = [];
const hooks = {
  useState(initial) { const i=cursor++; slots[i] ??= {value:initial}; return [slots[i].value,next=>{slots[i].value=typeof next==="function"?next(slots[i].value):next;}]; },
  useMemo(fn,deps) { const i=cursor++; if(!slots[i]||deps.some((v,j)=>v!==slots[i].deps[j])) slots[i]={deps,value:fn()}; return slots[i].value; },
  useEffect(fn,deps) { const i=cursor++; if(!slots[i]||deps.some((v,j)=>v!==slots[i].deps[j])) {slots[i]={deps};effects.push(fn);} },
  useRef(initial) { const i=cursor++; slots[i] ??= {value:{current:initial}}; return slots[i].value; },
};
const source=readFileSync(new URL("../src/AssemblyThermalVolumeViewer.tsx",import.meta.url),"utf8");
assert.match(source,/maximumFrames: 160/,"800 x 500 thermal GIF capture stays within the 256 MiB raw-frame bound");
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const component={exports:{}};
new Function("require","module","exports",code)(name=>name==="react"?hooks:name==="./assemblyThermalVolumePlot"?model:
  name==="./thermalTransientPresentation"?transientModel:name==="./PlotlyChart"?{default:"plotly-chart"}:name==="./DataTable"?{default:"data-table"}:
  name==="./SavedFramePlaybackControls"?{default:"saved-frame-playback"}:name==="./animationExport"?{captureGifFrames:()=>{},captureWebM:()=>{}}:
  name==="./transientPlayback"?{buildAnimationExportPlan:()=>({frames:[]}),gifDelayCentiseconds:()=>[],throwIfCancelled:()=>{}}:
  name==="./plotAnimationCapture"?{capturePlotlySurface:()=>{},waitForPlotlyRender:()=>Promise.resolve()}:
  name==="./gifExport"?{encodeGif:()=>({})}:name.endsWith(".css")?{}:require(name),component,component.exports);
let props={handoff:volume,result:fieldResult},tree;
function render(){cursor=0;tree=component.exports.default(props);const queued=effects;effects=[];queued.forEach(fn=>fn());}
function nodes(node){return !node||typeof node!=="object"?[]:[node,...React.Children.toArray(node.props?.children).flatMap(nodes)];}
const control=label=>nodes(tree).find(n=>n.type==="select"&&n.props["aria-label"]===label);
const chart=()=>nodes(tree).find(n=>n.type==="plotly-chart");
render();render();
assert.equal(control("Thermal volume display").props.value,"temperature");
assert.equal(control("Thermal volume mesh inspection").props.value,"none");
assert.ok(nodes(tree).some(n=>n.type==="data-table"&&n.props.pageSize===25));
const originalX=chart().props.data[0].x, originalLayout=chart().props.layout;
control("Thermal volume temperature units").props.onChange({target:{value:"K"}});render();
assert.strictEqual(chart().props.data[0].x,originalX,"unit control does not rebuild topology");
assert.strictEqual(chart().props.layout,originalLayout,"unit control preserves camera layout identity");
control("Thermal volume display").props.onChange({target:{value:"geometry"}});render();
assert.equal(chart().props.data[0].intensity,undefined);
assert.strictEqual(chart().props.data[0].x,originalX);
control("Thermal volume display").props.onChange({target:{value:"temperature"}});
control("Thermal volume occurrence").props.onChange({target:{value:"right"}});
control("Thermal volume mesh inspection").props.onChange({target:{value:"volume"}});render();
assert.equal(chart().props.data[0].cmax,350);
assert.equal(chart().props.data.length,3);
assert.equal(chart().props.layout.scene.uirevision,"h");
props={handoff:volume,result:{...fieldResult,request_digest:"stale"}};render();
assert.equal(chart().props.data[0].intensity,undefined);
assert.equal(nodes(tree).filter(n=>n.type==="data-table").length,0);
assert.equal(React.Children.toArray(control("Thermal volume display").props.children)[0].props.disabled,true);
props={handoff:{...volume,handoff_digest:"new"},result:null};render();render();
assert.equal(control("Thermal volume occurrence").props.value,"");
assert.equal(control("Thermal volume mesh inspection").props.value,"none");
assert.equal(chart().props.data.length,1);
props={handoff:null,result:null};render();
assert.equal(chart(),undefined);
console.log("Viewer controls, memo reuse, occurrence reset and stale-result withholding passed.");

assert.equal(transientModel.thermalPlaybackIndex([{time_s:0},{time_s:2},{time_s:5}],3),1);
assert.deepEqual(transientModel.thermalFrames({field_result:{frames:[{time_s:-.5,node_temperatures_k:[300]}]}}),[]);

// Playback exposes solved physical timestamps through the one shared control.
const history=[{time_s:0,node_temperatures_k:Array(8).fill(300)},
  {time_s:2,node_temperatures_k:Array(8).fill(310)}, {time_s:5,node_temperatures_k:Array(8).fill(320)}];
props={handoff:volume,result:{...fieldResult,contract:"spike/assembly-field-transient-result/v1",result_digest:"history",field_result:{...fieldResult.field_result,frames:history}}};
render();render();
assert.equal(chart().props.data[0].cmax,320,"all solved frames share a fixed color range");
const playback=()=>nodes(tree).find(n=>n.type==="saved-frame-playback");
assert.deepEqual(playback().props.timesS,[0,2,5]);
assert.equal(typeof playback().props.onExport,"function","volume viewer exports its dedicated plot surface");
playback().props.onFrame(transientModel.thermalPlaybackIndex(history,3));render();
assert.deepEqual(chart().props.data[0].intensity,Array(6).fill(310));
playback().props.onFrame(transientModel.thermalPlaybackIndex(history,6));render();
assert.deepEqual(chart().props.data[0].intensity,Array(6).fill(320));
playback().props.onFrame(0);render();
assert.equal(chart().props.data[0].cmax,320,"scrubbing cannot rescale temperature changes");
console.log("Physical-time playback adapter, dedicated export surface, scrubbing and fixed history temperature scale passed.");
