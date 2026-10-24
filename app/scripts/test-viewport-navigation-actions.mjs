// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import * as THREE from 'three';
import {importTestTypescript} from './import-test-typescript.mjs';
const {viewportNavigationGroups}=await importTestTypescript('viewportNavigationActions');
const {scopeViewportContextGroups}=await importTestTypescript('viewportContextPolicy');
const calls=[],point=[13,-7,2];
const context={viewMode:'3D',navigationMode:'pan',focusPoint:point,camera:v=>calls.push(['camera',v]),orbitAt:v=>calls.push(['pivot',v]),setMode:v=>calls.push(['mode',v]),setView:v=>calls.push(['view',v])};
let groups=viewportNavigationGroups(context),actions=groups.flatMap(g=>g.actions),find=id=>actions.find(a=>a.id===id);
point[0]=999;find('orbit-center').run();assert.deepEqual(calls.splice(0),[['pivot',[13,-7,2]],['mode','orbit']],'pivot uses original captured scene point, not menu pointer');
assert.equal(find('navigation-pan').checked,true);assert.equal(find('navigation-orbit').checked,false);
for(const view of ['top','bottom','front','back','left','right','iso']) {find(`camera-view-${view}`).run();assert.deepEqual(calls.pop(),['camera',`view-${view}`]);}
for(const [id,command] of [['fit','fit'],['navigation-zoom-in','zoom-in'],['navigation-zoom-out','zoom-out'],['navigation-reset','reset-view']]) {find(id).run();assert.deepEqual(calls.pop(),['camera',command]);}
find('camera-2d').run();assert.deepEqual(calls.pop(),['view','2D']);find('navigation-orbit').run();assert.deepEqual(calls.pop(),['mode','orbit']);
for(const workspace of ['Home','PI','HF / SI','Thermal','EM','Results']) {const scoped=scopeViewportContextGroups(groups,{activeWorkspace:workspace,selectionType:null,selectionHasNet:false,selectionOwnedByActiveBoard:false,hasSavedResult:false,hasThermalTarget:false,hasAssembly:false});assert.deepEqual(scoped.map(g=>g.id),['navigation','camera-views']);}
groups=viewportNavigationGroups({...context,viewMode:'2D'});actions=groups.flatMap(g=>g.actions);assert.equal(find('navigation-pan').checked,true);assert.ok(find('orbit-center').disabledReason);assert.ok(find('camera-view-top').disabledReason);find('orbit-center').run();find('navigation-orbit').run();find('camera-view-top').run();assert.equal(calls.length,0);
for(const focusPoint of [undefined,[1,2],[1,NaN,3],[1,Infinity,3]])assert.ok(viewportNavigationGroups({...context,focusPoint})[0].actions[0].disabledReason);
// Execute the actual renderer hit helper with distinct source and occurrence rays.
const source=readFileSync(new URL('../src/BoardViewport.tsx',import.meta.url),'utf8');
const snippet=source.slice(source.indexOf('    const scenePointAt ='),source.indexOf('    cursorPointRef.current ='));
const js=ts.transpileModule(snippet+'\nreturn scenePointAt;',{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
let sourceHit,occurrenceHit,surfaces=[];const fallback=new THREE.Vector3(8,9,0);
const pick=new Function('THREE','renderer','pointer','raycaster','activeCameraRef','hitAt','virtualBoardHitAt','boardGroup','sectionVisible','visibleInScene','viewModeRef','controls3d','controls2d','sectionHitVisible','sectionPlanesRef',js)(THREE,{domElement:{getBoundingClientRect:()=>({left:0,top:0,width:100,height:100})}},{},{setFromCamera(){},intersectObject:()=>surfaces,ray:{intersectPlane:()=>fallback}},{current:{}},()=>sourceHit?{hit:sourceHit}:undefined,()=>occurrenceHit,{},()=>true,()=>true,{current:'3D'},{target:new THREE.Vector3()},{target:new THREE.Vector3()},()=>true,{current:[]});
const hit=(distance,x)=>({distance,point:new THREE.Vector3(x,2,3),object:{userData:{}}});
sourceHit=hit(8,10);occurrenceHit=hit(2,20);surfaces=[hit(5,30)];assert.deepEqual(pick({clientX:50,clientY:50}).toArray(),[20,2,3],'nearest assembly occurrence supplies the pivot');
sourceHit=hit(1,40);assert.equal(pick({clientX:50,clientY:50}).x,40);sourceHit=occurrenceHit=undefined;surfaces=[];assert.equal(pick({clientX:50,clientY:50}),fallback);
console.log('Viewport navigation: clicked pivots, assembly hits, all standard views, mode state, 2D guards and workspace availability passed');
