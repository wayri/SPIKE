// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import * as THREE from "three";
import { resultVectorGlyphs } from "../src/resultVectorGlyphs.ts";
const origin=new THREE.Vector3(3,-2,5),color=new THREE.Color(0x79decf);
const directions=[new THREE.Vector3(1,0,0),new THREE.Vector3(0,-1,0),new THREE.Vector3(1,2,-3)];
const group=resultVectorGlyphs([...directions.map(direction=>({origin,direction,length:4,color})),{origin,direction:new THREE.Vector3(),length:4,color},{origin,direction:new THREE.Vector3(1,0,0),length:NaN,color}]);
assert.equal(group.children.length,2,"arbitrary field counts require only shaft/head batches");
for(const batch of group.children)assert.equal(batch.count,3,"invalid and zero vectors are not drawn");
const matrix=new THREE.Matrix4();
directions.forEach((direction,index)=>{
  const unit=direction.clone().normalize();
  group.children[0].getMatrixAt(index,matrix);
  const start=new THREE.Vector3(0,-.5,0).applyMatrix4(matrix);
  assert.ok(start.distanceTo(origin)<1e-6,"shaft begins at exact returned sample");
  group.children[1].getMatrixAt(index,matrix);
  const tip=new THREE.Vector3(0,.5,0).applyMatrix4(matrix);
  assert.ok(tip.distanceTo(origin.clone().addScaledVector(unit,4))<1e-6,"tip follows full 3D signed direction and bounded display length");
});
for(const batch of group.children){assert.ok(batch.boundingSphere.radius>0);batch.geometry.dispose();batch.material.dispose();}
assert.equal(resultVectorGlyphs([]).children.length,0);
console.log("Instanced result vectors preserve sample origins, signed directions, tips, bounds and empty/invalid recovery in two batches.");
