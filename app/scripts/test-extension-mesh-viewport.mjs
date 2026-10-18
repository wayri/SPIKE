// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import * as THREE from "three";
import { boundedMeshDisplayIndices, buildExtensionMeshScene } from "../src/extensionMeshViewport.ts";
import { disposeScene } from "../src/sceneResourceCache.ts";

const admission = {contract:"spike/extension-mesh-admission/v1",design_bound:true,complete_connectivity:true,physics_validated:false,cross_engine_reuse:false};
const header = {status:"completed",solved:false,units:"mm",coordinate_frame:"design_top_copper",model_status:"unvalidated",admission};
const transform = {centerX:10,centerY:20,scale:2,zOffsetMm:.8};
const tetra = {...header,contract:"spike/emerge-mesh/v1",nodes_mm:[[10,20,0],[12,20,0],[10,24,0],[10,20,-1.6]],tetrahedra:[[0,1,2,3]]};
const original = JSON.stringify(tetra);
const scene = buildExtensionMeshScene(tetra,transform);
assert.equal(scene.children.length,1);
const edges = scene.children[0];
assert.ok(edges instanceof THREE.LineSegments,"tetrahedra are displayed as their actual six edges");
assert.equal(edges.geometry.attributes.position.count,12);
const coords = Array.from(edges.geometry.attributes.position.array);
for (const [offset,expected] of [[0,[0,0,1.6,4,0,1.6]],[6,[0,0,1.6,0,-8,1.6]],[12,[0,0,1.6,0,0,-1.6]]]) {
  const actual = coords.slice(offset,offset+6);
  expected.forEach((v,i)=>assert.ok(Math.abs(actual[i]-v)<1e-6,"mm transform inverts Y once and offsets top-copper Z by half board thickness"));
}
assert.equal(JSON.stringify(tetra),original,"display construction preserves complete solver arrays");
assert.equal(scene.userData.displaySubset,true);
assert.equal(scene.userData.solverInput,false);
assert.equal(scene.userData.total,1); assert.equal(scene.userData.shown,1);
assert.ok(!("tetrahedra" in scene.userData),"preview metadata never replaces complete topology");
let geometryDisposals=0, materialDisposals=0;
edges.geometry.addEventListener("dispose",()=>geometryDisposals++);
edges.material.addEventListener("dispose",()=>materialDisposals++);
disposeScene(scene);
assert.equal(geometryDisposals,1); assert.equal(materialDisposals,1);
assert.equal(scene.children.length,0);

const many = {...header,contract:"spike/emerge-mesh/v1",nodes_mm:[],tetrahedra:[]};
for(let i=0;i<6001;i++) {
  const base=many.nodes_mm.length;
  many.nodes_mm.push([i,0,0],[i+.5,0,0],[i,.5,0],[i,0,.5]);
  many.tetrahedra.push([base,base+1,base+2,base+3]);
}
const manyScene=buildExtensionMeshScene(many,transform);
assert.equal(manyScene.userData.total,6001);
assert.equal(manyScene.userData.shown,5000,"tetra preview fills its bounded display budget");
assert.ok(manyScene.userData.shown<many.tetrahedra.length);
assert.equal(manyScene.children[0].geometry.attributes.position.count,manyScene.userData.shown*12);
const displayedMaximum = manyScene.children[0].geometry.attributes.position.array.reduce(
  (maximum,value)=>Math.max(maximum,value),-Infinity);
assert.equal(displayedMaximum,11981,
  "bounded tetra preview retains the final cell and full displayed extent");
assert.equal(many.tetrahedra.length,6001,"bounded display never truncates the underlying mesh");
disposeScene(manyScene);

const justOverBudget = boundedMeshDisplayIndices(5001,5000);
assert.equal(justOverBudget.length,5000,"just-over-budget sampling does not discard half the visual budget");
assert.equal(new Set(justOverBudget).size,5000,"bounded sampling does not repeat cells");
assert.deepEqual([justOverBudget[0],justOverBudget.at(-1)],[0,5000],
  "bounded sampling retains both topology endpoints");
assert.deepEqual(boundedMeshDisplayIndices(4,5000),[0,1,2,3]);
assert.deepEqual(boundedMeshDisplayIndices(Infinity,5000),[]);

const grid={...header,contract:"spike/openems-grid/v1",lines_mm:{x:[10,12,16],y:[20,24],z:[-1.6,0]}};
const gridScene=buildExtensionMeshScene(grid,transform);
assert.ok(gridScene.children[0] instanceof THREE.LineSegments);
assert.equal(gridScene.children[0].geometry.index,null,"Cartesian grid is not fabricated tetrahedral connectivity");
assert.equal(gridScene.userData.total,7);
assert.equal(gridScene.userData.shown,7);
assert.equal(gridScene.children[0].geometry.attributes.position.count,28,"each displayed Cartesian coordinate draws two domain-face lines");
const gridCoords=Array.from(gridScene.children[0].geometry.attributes.position.array.slice(0,6));
assert.ok(gridCoords.every((v,i)=>Math.abs(v-[0,0,-1.6,0,0,1.6][i])<1e-6));
disposeScene(gridScene);
const dense={...grid,lines_mm:{...grid.lines_mm,x:Array.from({length:10000},(_,i)=>i)}};
const denseScene=buildExtensionMeshScene(dense,transform);
assert.ok(denseScene.userData.shown<=129*3,"Cartesian display samples each axis independently with both domain endpoints retained");
assert.equal(dense.lines_mm.x.length,10000);
disposeScene(denseScene);

for(const patch of [{admission:undefined},{admission:{...admission,design_bound:"true"}},{admission:{...admission,complete_connectivity:false}},
  {admission:{...admission,physics_validated:true}},{admission:{...admission,cross_engine_reuse:true}},
  {units:"m"},{coordinate_frame:"unknown"},{status:"failed"},{solved:true},{contract:"other"},
  {nodes_mm:[null]},{tetrahedra:[null]},{tetrahedra:[[0,1,2,2]]},{tetrahedra:[[0,1,2,-1]]},{nodes_mm:[[Infinity,0,0],...tetra.nodes_mm.slice(1)]}]) {
  assert.equal(buildExtensionMeshScene({...tetra,...patch},transform).children.length,0,"unadmitted, unsupported and malformed payloads draw nothing");
}
for(const axes of [{x:[10,9],y:[20,24],z:[-1.6,0]},{x:[10,10],y:[20,24],z:[-1.6,0]},
  {x:[10,Infinity],y:[20,24],z:[-1.6,0]},{x:new Array(100001).fill(0),y:[20,24],z:[-1.6,0]}])
  assert.equal(buildExtensionMeshScene({...grid,lines_mm:axes},transform).children.length,0);
for(const invalid of [{scale:0},{scale:NaN},{centerX:Infinity},{zOffsetMm:NaN}])
  assert.equal(buildExtensionMeshScene(tetra,{...transform,...invalid}).children.length,0);
assert.equal(buildExtensionMeshScene({...tetra,nodes_mm:[[1e300,0,0],...tetra.nodes_mm.slice(1)]},transform).children.length,0,"finite doubles that overflow GPU float storage are rejected");
assert.equal(buildExtensionMeshScene(null,transform).children.length,0);
assert.equal(buildExtensionMeshScene(tetra,null).children.length,0);

// Integration ownership remains BoardViewport; this assertion guards removal
// and resource cleanup on mesh/board/view changes without mounting WebGL in Node.
const viewport=await readFile(new URL("../src/BoardViewport.tsx",import.meta.url),"utf8");
const effect=viewport.slice(viewport.indexOf("const group = buildExtensionMeshScene"),viewport.indexOf("}, [activeBoard, extensionMesh, viewMode]")+60);
assert.match(effect,/zOffsetMm: boardThicknessMm\(activeBoard\) \/ 2/);
assert.match(effect,/scene\.remove\(group\); clearGroup\(group\); extensionMeshGroupRef\.current = null/);
assert.match(viewport,/const clearGroup = disposeScene/);
console.log("Extension mesh viewport: actual topology/grid coordinates, top-copper offset, bounded display-only subsets, admission gates and cleanup passed.");

const gmsh = {...tetra,contract:"spike/gmsh-mesh/v1",coordinate_frame:"normalized_board_local_mm",model_status:"experimental"};
const gmshScene=buildExtensionMeshScene(gmsh,transform);
assert.equal(gmshScene.children.length,1);
assert.equal(gmshScene.children[0].geometry.attributes.position.array[2],0,"normalized solid datum must not acquire a legacy top-copper offset");
assert.equal(buildExtensionMeshScene({...gmsh,coordinate_frame:"design_top_copper"},transform).children.length,0);
disposeScene(gmshScene);
