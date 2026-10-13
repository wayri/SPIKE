// SPDX-License-Identifier: Apache-2.0
// Execute actual renderer traversal and batching, not a parallel implementation.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
import * as THREE from 'three';
import {mergeGeometries} from 'three/examples/jsm/utils/BufferGeometryUtils.js';
const source=await readFile(new URL('../src/BoardViewport.tsx',import.meta.url),'utf8');
const ast=ts.createSourceFile('BoardViewport.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
let traversal,importedTraversal;const functions={};
function visit(node){
 if(ts.isFunctionDeclaration(node)&&['identifySceneObject','batchProceduralGeometry'].includes(node.name?.text))functions[node.name.text]=node.getText(ast);
 if(ts.isCallExpression(node)&&node.expression.getText(ast)==='group.traverse'&&node.arguments[0]?.getText(ast).includes('const faceVisible'))traversal=node.arguments[0].getText(ast);
 if(ts.isCallExpression(node)&&node.expression.getText(ast).includes('accurateBoardRef.current?.traverse'))importedTraversal=node.arguments[0]?.getText(ast);
 ts.forEachChild(node,visit);
}
visit(ast);assert.ok(traversal);assert.ok(importedTraversal);
const compile=s=>ts.transpileModule(s,{compilerOptions:{module:ts.ModuleKind.ES2022,target:ts.ScriptTarget.ES2022}}).outputText;
const importedLayerSource=await readFile(new URL('../src/importedBoardLayers.ts',import.meta.url),'utf8');
const importedLayerAst=ts.createSourceFile('importedBoardLayers.ts',importedLayerSource,ts.ScriptTarget.Latest,true,ts.ScriptKind.TS);
let importedVisibilityFunction;importedLayerAst.forEachChild(node=>{if(ts.isFunctionDeclaration(node)&&node.name?.text==='importedBoardLayerVisible')importedVisibilityFunction=node.getText(importedLayerAst);});
assert.ok(importedVisibilityFunction);const importedBoardLayerVisible=new Function(compile(`${importedVisibilityFunction.replace(/^export\s+/,'')}\nreturn importedBoardLayerVisible;`))();
const policy=await import(`data:text/javascript;base64,${Buffer.from(compile(await readFile(new URL('../src/viewportScenePolicy.ts',import.meta.url),'utf8'))).toString('base64')}`);
const netFocusPolicy=await import(`data:text/javascript;base64,${Buffer.from(compile(await readFile(new URL('../src/netFocusMaterial.ts',import.meta.url),'utf8'))).toString('base64')}`);
const keys=['group','placeholderRoot','visibleLayers','copperLayers','viewMode','missingModelSet','importedBoardLayers','showThtModels','showSmdModels','showModels','resultModelsVisible','proceduralModelsAllowed','authoritativeView','presentation','showVias','isolatedNet','analysisNetSet','analysisOnlyScene','resultVisualization','offsetForLayer','layerOpacity','selectedId','hoverPreview','hoverMaterials','selectionMaterials','netFocusActive'];
const execute=new Function('THREE','env','layerObjectVisible','viaSpanVisible','applyNetFocusColor',compile(`const {${keys.join(',')}}=env; group.traverse(${traversal});`));
const batch=new Function('THREE','mergeGeometries','viewportSceneIdentity','viewportRenderOrder',compile(`${functions.identifySceneObject}\n${functions.batchProceduralGeometry}\nreturn batchProceduralGeometry;`))(THREE,mergeGeometries,policy.viewportSceneIdentity,policy.viewportRenderOrder);
const effective=o=>{for(let p=o;p;p=p.parent)if(!p.visible)return false;return true;};
const importedRoot=new THREE.Group();
const importedMesh=(layer,unaddressable=false)=>{const mesh=new THREE.Mesh(new THREE.BoxGeometry(1,1,.01),new THREE.MeshStandardMaterial());mesh.userData=layer?{importedBoardLayer:layer}:{importedBoardUnaddressable:unaddressable};importedRoot.add(mesh);return mesh;};
const importedFront=importedMesh('F.Cu'),importedBack=importedMesh('B.Cu'),importedBody=importedMesh('Board body'),importedUnknown=importedMesh(undefined,true);
const applyImported=new Function('THREE','root','visibleLayers','copperLayers','showVias','importedCopperUnavailable','importedBoardLayerVisible',compile(`root.traverse(${importedTraversal});`));
applyImported(THREE,importedRoot,{'F.Cu':true,'B.Cu':false,'Board body':true},['F.Cu','B.Cu'],true,false,importedBoardLayerVisible);
assert.equal(importedFront.visible,true);assert.equal(importedBack.visible,false);assert.equal(importedBody.visible,true);assert.equal(importedUnknown.visible,false,'Unaddressable imported aggregate must not override retained layer geometry');
applyImported(THREE,importedRoot,{'F.Cu':true,'B.Cu':true,'Board body':true},['F.Cu','B.Cu'],true,true,importedBoardLayerVisible);
assert.equal(importedFront.visible,false,'A partial board export must not replace retained front copper');assert.equal(importedBack.visible,false,'A partial board export must not replace retained back copper');assert.equal(importedBody.visible,true,'A partial board export may retain its addressable board body');
for(const count of [2,6,12,16,32])for(const batched of [false,true]){
 const layers=['F.Cu',...Array.from({length:count-2},(_,i)=>`In${i+1}.Cu`),'B.Cu'];
 const all=[...layers,'F.Mask','B.Mask','Board body'];const group=new THREE.Group();
 const add=data=>{const m=new THREE.Mesh(new THREE.BoxGeometry(1,1,.01),new THREE.MeshStandardMaterial());m.userData=data;group.add(m);return m;};
 const substrate=add({substrate:true}), frontMask=add({layer:'F.Mask',surface:true}), backMask=add({layer:'B.Mask',surface:true}), component=add({model:true,mount:'smd',layer:'F.Cu'});
 const traces=new Map();for(const layer of layers)traces.set(layer,add({type:'trace',layer}));
 const viaGroup=new THREE.Group();viaGroup.userData={type:'via',via:true,layer:'through'};group.add(viaGroup);
 const shared=new THREE.MeshStandardMaterial();
 for(const layer of layers){const face=add({type:'via',layer:'through',viaFaceLayer:layer});if(batched)face.material=shared;viaGroup.add(face);}
 for(let i=0;i<layers.length-1;i++){const barrel=add({type:'via',layer:'through',viaBarrel:true,viaStartLayer:layers[i],viaEndLayer:layers[i+1]});viaGroup.add(barrel);}
 for(const [start,end] of [[0,layers.length-1],[1,Math.max(1,layers.length-2)]]){if(end>=layers.length)continue;const barrel=add({type:'via',layer:'through',viaBarrel:true,viaStartLayer:layers[start],viaEndLayer:layers[end]});viaGroup.add(barrel);}
 if(batched)batch(group,layers);
 const env={netFocusActive:false,group,placeholderRoot:null,copperLayers:layers,viewMode:'3D',missingModelSet:new Set(),importedBoardLayers:new Set(),showThtModels:true,showSmdModels:true,showModels:true,resultModelsVisible:true,proceduralModelsAllowed:true,authoritativeView:false,presentation:{proceduralComponents:true},showVias:true,isolatedNet:null,analysisNetSet:new Set(),analysisOnlyScene:false,resultVisualization:null,offsetForLayer:()=>0,layerOpacity:{},selectedId:null,hoverPreview:null,hoverMaterials:new Set(),selectionMaterials:new Set()};
 const run=()=>execute(THREE,env,policy.layerObjectVisible,policy.viaSpanVisible,netFocusPolicy.applyNetFocusColor);
 const check=()=>group.traverse(object=>{
  const d=object.userData;if(d.model||d.substrate)return;
  if(d.viaBarrel){const span=layers.slice(layers.indexOf(d.viaStartLayer),layers.indexOf(d.viaEndLayer)+1);assert.equal(effective(object),span.some(l=>env.visibleLayers[l]!==false),`${count}/${batched} barrel span`);}
  else {const layer=d.viaFaceLayer??d.layer;if(all.includes(layer))assert.equal(effective(object),env.visibleLayers[layer]!==false,`${count}/${batched} layer ${layer}`);}
 });
 for(const hidden of layers){env.visibleLayers=Object.fromEntries(all.map(l=>[l,l!==hidden]));run();check();for(const o of [substrate,frontMask,backMask,component])assert.equal(effective(o),true);}
 // Exact requested sequence: all off, then one on; reset to all off each time.
 for(const selected of [null,...all]){
  env.visibleLayers=Object.fromEntries(all.map(l=>[l,false]));run();check();
  if(selected)env.visibleLayers[selected]=true;run();check();
  assert.equal(effective(substrate),selected==='Board body');assert.equal(effective(component),true);
 }
 // Copper changes preserve the independently selected body state in both directions.
 for(const body of [false,true]) for(const layer of layers){
  env.visibleLayers={'Board body':body,[layer]:false};run();assert.equal(effective(substrate),body);
  env.visibleLayers[layer]=true;run();assert.equal(effective(substrate),body);
 }
 env.visibleLayers={};env.layerOpacity={'F.Cu':.3};env.resultVisualization={sceneMode:'translucent',boardOpacity:.4};run();
 assert.equal(substrate.material.opacity,.4);assert.equal(component.material.opacity,1);
 env.layerOpacity['Board body']=.5;run();assert.equal(substrate.material.opacity,.2);
 delete env.layerOpacity['Board body'];run();
 group.traverse(o=>{if(o.userData.viaFaceLayer)assert.ok(Math.abs(o.material.opacity-(o.userData.viaFaceLayer==='F.Cu'?.12:.4))<1e-12,'Pooled via opacity must remain independent');});
 env.netFocusActive=true;run();
 group.traverse(o=>{if(o instanceof THREE.Mesh && o.userData.layer?.endsWith('.Cu') && !o.userData.model){assert.equal(o.material.color.getHex(),0x667076,'actual copper traversal desaturates unselected context');}});
 env.netFocusActive=false;run();
 group.traverse(o=>{if(o instanceof THREE.Mesh && o.userData.layer?.endsWith('.Cu') && !o.userData.model){assert.equal(o.material.color.getHex(),0xffffff,'clear focus restores the original copper material');}});
 env.showSmdModels=false;run();assert.equal(effective(component),false);assert.equal(effective(substrate),true);assert.equal(effective(frontMask),true);
 env.showSmdModels=true;env.showVias=false;run();assert.equal(effective(component),true);assert.equal(effective(substrate),true);
 group.traverse(o=>{if(o.userData.viaFaceLayer||o.userData.viaBarrel)assert.equal(effective(o),false);});
 env.showVias=true;env.authoritativeView=true;env.importedBoardLayers=new Set(['F.Cu','Board body']);env.visibleLayers={};run();
 assert.equal(effective(substrate),false,'Imported board body suppresses only its procedural duplicate');
 if(!batched){assert.equal(effective(traces.get('F.Cu')),false,'Imported front copper suppresses its procedural duplicate');
 assert.equal(effective(traces.get('B.Cu')),true,'Uncovered back copper retains procedural geometry');}
 const base={is3D:true,boardReady:true,componentsReady:true,split:true,layerAddressable:true,layerFiltered:false,exploded:false,isolated:false,analysisOnly:false,resultsOnly:false,showModels:true,categoryFiltered:false,resultModelsVisible:true,missingModels:false};
 for(const layerFiltered of [false,true])for(const exploded of [false,true]){const r=policy.boardSceneVisibility({...base,layerFiltered,exploded});assert.equal(r.importedBoard,false);assert.equal(r.proceduralRoot,true);assert.equal(r.importedComponents,true);}
 assert.equal(policy.boardSceneVisibility({...base,componentsReady:false,split:false}).proceduralComponents,true);
}
assert.match(source,/layerAddressable: importedBoardLayers\.size > 0/);
assert.doesNotMatch(source,/viasOnlyActive/,'All-off must not implicitly restore all via faces');
console.log('Actual renderer/batching: all-off then each layer on, independent layers/models/substrate, via spans/opacity, category gates and stable roots passed at 2/6/12/16/32 layers');

const nativeBase={is3D:true,boardReady:true,componentsReady:true,split:true,layerAddressable:true,preferAuthoritativeBoard:true,layerFiltered:false,exploded:false,isolated:false,analysisOnly:false,resultsOnly:false,showModels:true,categoryFiltered:false,resultModelsVisible:true,missingModels:false};
assert.equal(policy.boardSceneVisibility(nativeBase).importedBoard,true,"assembled unfiltered view uses verified KiCad surfaces");
assert.equal(policy.boardSceneVisibility({...nativeBase,layerFiltered:true}).importedBoard,true,"layer edits retain independently addressable imported surfaces");
assert.equal(policy.boardSceneVisibility({...nativeBase,exploded:true}).importedBoard,false,"explosion preserves addressable layer rendering");
assert.equal(policy.boardSceneVisibility({...nativeBase,layerAddressable:false}).importedBoard,false,"an entirely unaddressable import uses retained geometry");
