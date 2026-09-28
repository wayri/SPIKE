// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const compile=s=>ts.transpileModule(s,{compilerOptions:{module:ts.ModuleKind.ES2022,target:ts.ScriptTarget.ES2022}}).outputText;
const load=async s=>import(`data:text/javascript;base64,${Buffer.from(compile(s)).toString('base64')}`);
const source=await readFile(new URL('../src/LayoutViewport.tsx',import.meta.url),'utf8');
const ast=ts.createSourceFile('LayoutViewport.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
const fn=ast.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text==='layoutFeatureAnnotations');assert.ok(fn);
const keyFn=ast.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text==='annotationRenderKey');assert.ok(keyFn);
const annotationKey=new Function(`${compile(keyFn.getText(ast))};return annotationRenderKey;`)();
assert.notEqual(annotationKey({kind:'pad',id:'pad-SH1-1'},0),annotationKey({kind:'pad',id:'pad-SH1-1'},1),'duplicate source pad IDs need distinct React keys');
assert.equal(annotationKey({kind:'pad',id:'pad-SH1-1'},0),'pad:pad-SH1-1:0','selection source ID remains intact');
const copper=await load(await readFile(new URL('../src/copperLayerSelection.ts',import.meta.url),'utf8'));
const performanceApi=await load(await readFile(new URL('../src/viewportPerformance.ts',import.meta.url),'utf8'));
const annotate=new Function('resolveBoardCopperLayers',compile(fn.getText(ast))+';return layoutFeatureAnnotations;')(copper.resolveBoardCopperLayers);
const view={minX:0,minY:0,maxX:100,maxY:100,unitsPerPixel:.025};
const pad=(id,x,y,name,layer='F.Cu')=>({id,ref:id,at:[x,y],name,layer,layers:[layer],width:3,height:1.5,rotation:0,net:'VCC'});
const board={layers:['F.Cu','In1.Cu','B.Cu'],pads:[pad('U1',5,5,'1'),pad('J1',10,5,'01'),pad('U2',15,5,'A1'),pad('U3',20,5,'2'),pad('U4',25,5,'1','B.Cu')]};
const traces=[{id:'trace',layer:'F.Cu',net:'VCC',start:[10,15],end:[30,15],width:1}];
const zones=[{id:'zone',layer:'F.Cu',net:'GND',points:[[40,40],[60,40],[60,60],[40,60]]}];
const labels=performanceApi.copperNetLabels(traces,zones,view);
const detailed=annotate(board,view,{},'All',null,true,labels);
assert.equal(detailed.pinOne.length,4);assert.equal(detailed.labels.filter(l=>l.kind==='pad').length,5);
assert.ok(detailed.labels.some(l=>l.kind==='trace'));assert.ok(detailed.labels.some(l=>l.kind==='zone'));
assert.ok(detailed.labels.find(l=>l.id==='U1').text.includes('VCC'));
assert.equal(annotate(board,view,{},'All',null,false,[]).labels.find(l=>l.id==='U1').text,'1');
assert.equal(annotate(board,view,{'F.Cu':false,'B.Cu':false},'All',null,true,[]).pinOne.length,0);
assert.equal(annotate(board,view,{},'F.Cu',null,true,[]).pinOne.length,3);
assert.equal(annotate(board,view,{},'All','GND',true,[]).labels.length,0);
const overview=annotate(board,{...view,unitsPerPixel:1},{},'All',null,true,[]);assert.equal(overview.labels.filter(l=>l.kind==='pad').length,0);assert.ok(overview.labels.some(l=>l.kind==='net-callout'));assert.equal(overview.pinOne.length,4);
const overlap={...board,pads:[pad('a',5,5,'1'),pad('b',5,5,'2')]};assert.equal(annotate(overlap,view,{},'All',null,true,[]).labels.filter(l=>l.kind==='pad').length,1);
const many={...board,pads:Array.from({length:10000},(_,i)=>pad(`P${i}`,4+(i%100)*5,4+Math.floor(i/100)*5,'1'))};
const bounded=annotate(many,{...view,maxX:510,maxY:510},{},'All',null,false,[]);assert.equal(bounded.labels.length,600);assert.equal(bounded.pinOne.length,10000,'Pin markers must not silently truncate components to text budget');
assert.match(source,/return layoutFeatureAnnotations\(board/);assert.match(source,/data-pin-one-count=/);
console.log('Actual2D annotation function: pad numbers/nets, trace/zone labels, pin1/A1, visible-layer/isolated-net filters, zoom, collisions and600text budget passed');
const numeric=await readFile(new URL('../src/numericRange.ts',import.meta.url),'utf8');
const parser=(await readFile(new URL('../src/boardParser.ts',import.meta.url),'utf8')).replace('import { numericExtent } from "./numericRange";','');
const {parseKicadBoard}=await load(numeric+'\n'+parser);
for(const path of process.argv.slice(2)){
 const real=parseKicadBoard(await readFile(path,'utf8'));
 const padIds=new Set();let repeatedPadIds=0;
 for(const pad of real.pads) {if(padIds.has(pad.id)) repeatedPadIds++;padIds.add(pad.id);}
 if(path.includes('esp32')) assert.ok(repeatedPadIds>0,'ESP32 source reproduces duplicate fallback pad IDs');
 const filledCopperGraphics=real.drawings.filter(d=>d.layer==='F.Cu'&&d.filled&&d.points.length>=3);
 if(path.includes('esp32')) assert.ok(filledCopperGraphics.length>=3,'ESP32 antenna source copper polygons must survive import');
 const base={minX:real.bounds.minX,minY:real.bounds.minY,maxX:real.bounds.maxX,maxY:real.bounds.maxY,unitsPerPixel:Math.max(real.width/1000,real.height/700)};
 if(path.includes('esp32')) {
  const narrow={...base,unitsPerPixel:real.width/200};
  const compact=annotate(real,narrow,{},'All',null,true,[]);
  assert.equal(compact.labels.length,0,'board-fit width near 200 px must not cover copper with text');
  assert.ok(compact.legend.length>=4&&compact.legend.length<=8,'narrow fit uses a bounded net legend');
  assert.equal(new Set(compact.legend.map(item=>item.net)).size,compact.legend.length,'legend entries identify distinct nets');
  for(let i=0;i<compact.legend.length;i++) for(let j=0;j<i;j++)
   assert.ok(Math.hypot(compact.legend[i].at[0]-compact.legend[j].at[0],compact.legend[i].at[1]-compact.legend[j].at[1])/narrow.unitsPerPixel>=38,'numbered board markers stay separated in projected pixels');
 }
 const samples=[];
 for(const [name,v] of [['fit',base],['detail',{minX:real.pads[0].at[0]-5,minY:real.pads[0].at[1]-5,maxX:real.pads[0].at[0]+5,maxY:real.pads[0].at[1]+5,unitsPerPixel:10/700}]]){
  const start=performance.now();const net=performanceApi.copperNetLabels(real.tracks,real.zones,v);const result=annotate(real,v,{},'All',null,true,net);const ms=performance.now()-start;
  assert.ok(result.labels.length<=600);assert.ok(result.labels.every(l=>Number.isFinite(l.x+l.y+l.fontSize)));
  if(name==='fit'&&path.includes('esp32')) {
   const callouts=result.labels.filter(l=>l.kind==='net-callout');
   assert.ok(callouts.length>=10||result.legend.length>=4,'board-fit view needs readable distributed nets');
   assert.ok(new Set([...callouts.map(l=>l.text),...result.legend.map(l=>l.net)]).size>=4,'board-fit labels must cover distinct nets');
  }
  samples.push({name,milliseconds:ms,labels:result.labels.length,padLabels:result.labels.filter(l=>l.kind==='pad').length,netCallouts:result.labels.filter(l=>l.kind==='net-callout').length,legendNets:result.legend.length,pinOneMarkers:result.pinOne.length});
 }
 console.log(JSON.stringify({path,pads:real.pads.length,components:real.components.length,filledCopperGraphics:filledCopperGraphics.length,samples}));
}
