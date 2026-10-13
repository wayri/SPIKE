// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import ts from "typescript";
import * as THREE from "three";
const code=ts.transpileModule(readFileSync(new URL("../src/copperSelectionOverlay.ts",import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const module={exports:{}};new Function("require","module","exports",code)(()=>THREE,module,module.exports);
const {updateCopperSelectionBoundary,copperSelectionOpacity}=module.exports;
const geometry=new THREE.BoxGeometry(2,3,.04);const material=new THREE.MeshBasicMaterial();const mesh=new THREE.Mesh(geometry,material);
const planes=[new THREE.Plane(new THREE.Vector3(1,0,0),0)];material.clippingPlanes=planes;
updateCopperSelectionBoundary(mesh,true,0xffc34e);const boundary=mesh.children[0];const edgeGeometry=boundary.geometry;
assert.equal(mesh.geometry,geometry);assert.equal(boundary.material.depthTest,false);assert.equal(boundary.material.depthWrite,false);assert.equal(boundary.material.toneMapped,false);assert.equal(boundary.material.clippingPlanes,planes);
assert.equal(boundary.material.color.getHex(),0xffc34e);assert.equal(boundary.renderOrder,392);
const hits=[];boundary.raycast(new THREE.Raycaster(),hits);assert.equal(hits.length,0);
updateCopperSelectionBoundary(mesh,true,0x39f5ed);assert.equal(mesh.children.length,1);assert.equal(mesh.children[0].geometry,edgeGeometry);assert.equal(boundary.material.color.getHex(),0x39f5ed);
let geometryDisposed=false,materialDisposed=false;edgeGeometry.addEventListener("dispose",()=>geometryDisposed=true);boundary.material.addEventListener("dispose",()=>materialDisposed=true);
updateCopperSelectionBoundary(mesh,false,0);assert.equal(mesh.children.length,0);assert(geometryDisposed&&materialDisposed);
assert(copperSelectionOpacity("trace",true,false)>.9);assert(copperSelectionOpacity("zone",false,false)<.3);assert(copperSelectionOpacity("trace",false,true)<.1);
geometry.dispose();material.dispose();console.log("Copper boundaries reuse geometry, respect clipping, avoid picking, dispose cleanly and preserve result colors.");
