// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import * as THREE from "three";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { createInfiniteViewportGrid } = await importTestTypescript("infiniteViewportGrid");
for (const background of ["dark","light","amoled"]) {
  const mesh=createInfiniteViewportGrid(-.65,background), geometry=mesh.geometry,material=mesh.material;
  assert.equal(geometry.index.count/3,2,"No growth with visible world area");
  assert.equal(material.transparent,false,"Background must draw before translucent results");
  assert.equal(material.depthWrite,false);assert.equal(material.depthTest,false);
  assert.equal(mesh.frustumCulled,false);
  const intersections=[];mesh.raycast(new THREE.Raycaster(),intersections);assert.equal(intersections.length,0);
  for(const Camera of [THREE.PerspectiveCamera,THREE.OrthographicCamera]) {
    const camera=new Camera();camera.position.set(10000,-10000,100);camera.updateMatrixWorld();
    for(let i=0;i<10000;i++) {
      camera.position.z=10**(i%10-3);camera.updateMatrixWorld();
      mesh.onBeforeRender(null,null,camera,null,null,null);
      assert.equal(mesh.geometry,geometry);assert.equal(mesh.material,material);
      assert.ok(Number.isFinite(material.uniforms.spacing.value)&&material.uniforms.spacing.value>0);
    }
    assert.deepEqual(material.uniforms.cameraWorld.value.elements,camera.matrixWorld.elements);
    assert.deepEqual(material.uniforms.inverseProjection.value.elements,camera.projectionMatrixInverse.elements);
  }
  let disposed=0;geometry.addEventListener("dispose",()=>disposed++);material.addEventListener("dispose",()=>disposed++);geometry.dispose();material.dispose();assert.equal(disposed,2);
}
console.log("Infinite grid: two triangles, no pick hits, correct background/depth queue, perspective/orthographic uniform updates and owned disposal passed (60,000 updates).");
