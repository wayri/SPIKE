// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const options = { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 };
const interaction = ts.transpileModule(readFileSync(new URL('../src/plotInteraction.ts', import.meta.url), 'utf8'), { compilerOptions: options }).outputText;
const helpers = await import(`data:text/javascript;base64,${Buffer.from(interaction).toString('base64')}`);
const source = readFileSync(new URL('../src/InteractivePlot.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('InteractivePlot.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let body;
function visit(node) {
  if (ts.isCallExpression(node) && node.expression.getText(ast) === 'useEffect' && ts.isArrowFunction(node.arguments[0]) && node.arguments[0].body.getText(ast).includes('const wheel =')) body = node.arguments[0].body.getText(ast);
  ts.forEachChild(node, visit);
}
visit(ast); assert.ok(body, 'the production wheel effect is exercised');
const js = ts.transpileModule(`export function mount(deps) { const {host,plotlyRef,controls,zoom,update,setNotice,ownerWindow,plotWheelTarget,plotZoomChanges,plotPanChanges,wheelPlotFactor}=deps; ${body.slice(1,-1)} }`, { compilerOptions: options }).outputText;
const { mount } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
class Element {
  constructor(cls = '') { this.cls=cls; this.parentElement=null; this.classList={contains: cls2 => cls===cls2}; }
  getAttribute() { return this.cls; }
  closest(selector) { return selector.split(',').some(cls => cls.slice(1)===this.cls) ? this : null; }
}
const xa={_name:'xaxis',range:[0,10],_offset:60,_length:400},ya={_name:'yaxis',range:[-5,5],_offset:30,_length:200};
const graph=new Element(),listeners=new Map(),calls=[],frames=[];
graph._fullLayout={xaxis:xa,yaxis:ya,_plots:{xy:{xaxis:xa,yaxis:ya}}};
graph.getBoundingClientRect=()=>({left:10,top:20});
graph.addEventListener=(type,fn,opts)=>{ assert.equal(opts.capture,true); assert.equal(opts.passive,false); listeners.set(type,fn); };
graph.removeEventListener=(type,fn,capture)=>{assert.equal(listeners.get(type),fn);assert.equal(capture,true);listeners.delete(type);};
const ownerWindow={ResizeObserver:class{observe(){} disconnect(){}},Element,requestAnimationFrame:fn=>{frames.push(fn);return frames.length;},cancelAnimationFrame(){}};
const controls={current:{wheelZoom:true,wheelTarget:'auto',data:[{type:'scatter'}]}}, cleanup=mount({ ...helpers,host:{current:graph},plotlyRef:{current:{Plots:{resize(){}}}},controls,ownerWindow,
  zoom:(factor,target)=>calls.push(helpers.plotZoomChanges(graph._fullLayout,factor,target)),update:changes=>calls.push(changes),setNotice:message=>{throw Error(message);} });
const fire=(x,y,target=graph,extra={})=>{let prevented=false,stopped=false;listeners.get('wheel')({clientX:x+10,clientY:y+20,deltaY:-120,deltaX:0,deltaMode:0,target,preventDefault(){prevented=true;},stopPropagation(){stopped=true;},...extra});return {prevented,stopped};};
const flush=()=>{while(frames.length)frames.shift()();};
assert.deepEqual(fire(260,130),{prevented:true,stopped:true});flush();assert.ok(calls[0]['xaxis.range']);assert.ok(calls[0]['yaxis.range'],'plain wheel zooms by default');
calls.length=0;fire(140,250);flush();assert.deepEqual(Object.keys(calls[0]),['xaxis.range','xaxis.autorange']);
calls.length=0;const tick=new Element('ytick');tick.parentElement=graph;fire(35,130,tick);flush();assert.deepEqual(Object.keys(calls[0]),['yaxis.range','yaxis.autorange']);
calls.length=0;const legend=new Element('legend');assert.equal(fire(260,130,legend).prevented,false);flush();assert.equal(calls.length,0,'legends retain scrolling');
controls.current.wheelZoom=false;assert.equal(fire(260,130).prevented,false);assert.equal(fire(260,130,graph,{ctrlKey:true}).prevented,true);flush();
controls.current.wheelZoom=true;calls.length=0;fire(260,130,graph,{shiftKey:true});assert.deepEqual(Object.keys(calls[0]),['xaxis.range','xaxis.autorange'],'shift wheel remains horizontal pan');
calls.length=0;assert.equal(fire(520,290).prevented,false);assert.equal(calls.length,0);
cleanup();assert.equal(listeners.size,0,'unmount removes the capture listener');
console.log('Production wheel event routing, axis targeting, modifiers, cancellation and cleanup passed.');
