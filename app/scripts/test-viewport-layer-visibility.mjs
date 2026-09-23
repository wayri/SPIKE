// SPDX-License-Identifier: Apache-2.0
// Execute actual renderer traversal and batching, not a parallel implementation.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
import * as THREE from 'three';
import {mergeGeometries} from 'three/examples/jsm/utils/BufferGeometryUtils.js';
const source=await readFile(new URL('../src/BoardViewport.tsx',import.meta.url),'utf8');
const ast=ts.createSourceFile('BoardViewport.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
let traversal;const functions={};
function visit(node){
 if(ts.isFunctionDeclaration(node)&&['identifySceneObject','batchProceduralGeometry'].includes(node.name?.text))functions[node.name.text]=node.getText(ast);
 if(ts.isCallExpression(node)&&node.expression.getText(ast)==='group.traverse'&&node.arguments[0]?.getText(ast).includes('const faceVisible'))traversal=node.arguments[0].getText(ast);
 ts.forEachChild(node,visit);
}
visit(ast);assert.ok(traversal);
const compile=s=>ts.transpileModule(s,{compilerOptions:{module:ts.ModuleKind.ES2022,target:ts.ScriptTarget.ES2022}}).outputText;
const policy=await import(`data:text/javascript;base64,${Buffer.from(compile(await readFile(new URL('../src/viewportScenePolicy.ts',import.meta.url),'utf8'))).toString('base64')}`);
const keys=['group','placeholderRoot','visibleLayers','copperLayers','viewMode','missingModelSet','showThtModels','showSmdModels','showModels','resultModelsVisible','proceduralModelsAllowed','authoritativeView','presentation','showVias','isolatedNet','analysisNetSet','analysisOnlyScene','resultVisualization','offsetForLayer','layerOpacity','selectedId','hoverPreview','hoverMaterials','selectionMaterials'];
const execute=new Function('THREE','env','layerObjectVisible','viaSpanVisible',compile(`const {${keys.join(',')}}=env; group.traverse(${traversal});`));
const batch=new Function('THREE','mergeGeometries','viewportSceneIdentity','viewportRenderOrder',compile(`${functions.identifySceneObject}\n${functions.batchProceduralGeometry}\nreturn batchProceduralGeometry;`))(THREE,mergeGeometries,policy.viewportSceneIdentity,policy.viewportRenderOrder);
const effective=o=>{for(let p=o;p;p=p.parent)if(!p.visible)return false;return true;};
for(const count of [2,6,12,16,32])for(const batched of [false,true]){
 const layers=['F.Cu',...Array.from({length:count-2},(_,i)=>`In${i+1}.Cu`),'B.Cu'];
 const all=[...layers,'F.Mask','B.Mask','Board body'];const group=new THREE.Group();
 const add=data=>{const m=new THREE.Mesh(new THREE.BoxGeometry(1,1,.01),new THREE.MeshStandardMaterial());m.userData=data;group.add(m);return m;};
 const substrate=add({substrate:true}), frontMask=add({layer:'F.Mask',surface:true}), backMask=add({layer:'B.Mask',surface:true}), component=add({model:true,mount:'smd',layer:'F.Cu'});
 for(const layer of layers)add({type:'trace',layer});
 const viaGroup=new THREE.Group();viaGroup.userData={type:'via',via:true,layer:'through'};group.add(viaGroup);
 const shared=new THREE.MeshStandardMaterial();
 for(const layer of layers){const face=add({type:'via',layer:'through',viaFaceLayer:layer});if(batched)face.material=shared;viaGroup.add(face);}
 for(let i=0;i<layers.length-1;i++){const barrel=add({type:'via',layer:'through',viaBarrel:true,viaStartLayer:layers[i],viaEndLayer:layers[i+1]});viaGroup.add(barrel);}
 for(const [start,end] of [[0,layers.length-1],[1,Math.max(1,layers.length-2)]]){if(end>=layers.length)continue;const barrel=add({type:'via',layer:'through',viaBarrel:true,viaStartLayer:layers[start],viaEndLayer:layers[end]});viaGroup.add(barrel);}
 if(batched)batch(group,layers);
 const env={group,placeholderRoot:null,copperLayers:layers,viewMode:'3D',missingModelSet:new Set(),showThtModels:true,showSmdModels:true,showModels:true,resultModelsVisible:true,proceduralModelsAllowed:true,authoritativeView:false,presentation:{proceduralComponents:true},showVias:true,isolatedNet:null,analysisNetSet:new Set(),analysisOnlyScene:false,resultVisualization:null,offsetForLayer:()=>0,layerOpacity:{},selectedId:null,hoverPreview:null,hoverMaterials:new Set(),selectionMaterials:new Set()};
 const run=()=>execute(THREE,env,policy.layerObjectVisible,policy.viaSpanVisible);
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
 env.showSmdModels=false;run();assert.equal(effective(component),false);assert.equal(effective(substrate),true);assert.equal(effective(frontMask),true);
 env.showSmdModels=true;env.showVias=false;run();assert.equal(effective(component),true);assert.equal(effective(substrate),true);
 group.traverse(o=>{if(o.userData.viaFaceLayer||o.userData.viaBarrel)assert.equal(effective(o),false);});
 const base={is3D:true,boardReady:true,componentsReady:true,split:true,layerAddressable:true,layerFiltered:false,exploded:false,isolated:false,analysisOnly:false,resultsOnly:false,showModels:true,categoryFiltered:false,resultModelsVisible:true,missingModels:false};
 for(const layerFiltered of [false,true])for(const exploded of [false,true]){const r=policy.boardSceneVisibility({...base,layerFiltered,exploded});assert.equal(r.importedBoard,false);assert.equal(r.proceduralRoot,true);assert.equal(r.importedComponents,true);}
 assert.equal(policy.boardSceneVisibility({...base,componentsReady:false,split:false}).proceduralComponents,true);
}
assert.match(source,/layerAddressable: copperLayers.length > 0/);
assert.doesNotMatch(source,/viasOnlyActive/,'All-off must not implicitly restore all via faces');
console.log('Actual renderer/batching: all-off then each layer on, independent layers/models/substrate, via spans/opacity, category gates and stable roots passed at 2/6/12/16/32 layers');
