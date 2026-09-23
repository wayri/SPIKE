import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { viewportSceneIdentity, viewportRenderOrder } from '../src/viewportScenePolicy.ts';
import { resolveBoardCopperLayers } from '../src/copperLayerSelection.ts';

// Exercise the production preparation functions without mounting the entire UI.
const source = readFileSync(new URL('../src/BoardViewport.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('BoardViewport.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const names = new Set(['classifyBoardSurface', 'consolidateStaticModel', 'prepareImportedScene', 'padPath', 'capsulePath', 'roundedRectanglePath']);
const declarations = ast.statements.filter(node => ts.isFunctionDeclaration(node) && names.has(node.name?.text));
assert.equal(declarations.length, names.size);
const js = ts.transpileModule(declarations.map(node => node.getText(ast)).join('\n'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText;
const prepare = new Function('THREE', 'mergeGeometries', 'viewportSceneIdentity', 'viewportRenderOrder',
  `${js}\nreturn prepareImportedScene;`)(THREE, mergeGeometries, viewportSceneIdentity, viewportRenderOrder);
const padPath = new Function('THREE', `${js}\nreturn padPath;`)(THREE);
const customPad = padPath({width:2,height:2,drill:0,shape:'custom',customPolygon:[[-1,0],[0,1],[1,0],[0,-1]]},2);
assert.ok(Math.abs(Math.abs(THREE.ShapeUtils.area(customPad.getPoints())) - 8) < 1e-6, 'custom pad must retain polygon area instead of its rectangular bounds');
assert.deepEqual(customPad.getPoints().slice(0,4).map(p=>[p.x || 0,p.y || 0]),[[-2,0],[0,-2],[2,0],[0,2]]);
for (const scale of [.05, 1, 20]) {
  const shape = padPath({ width: .08, height: .06, drill: .02, shape: 'rect' }, scale);
  const geometry = new THREE.ShapeGeometry(shape);
  geometry.computeBoundingBox();
  const size = geometry.boundingBox.getSize(new THREE.Vector3());
  assert.ok(Math.abs(size.x - .08 * scale) < 1e-6, 'dense pad width must remain in physical units');
  assert.ok(Math.abs(size.y - .06 * scale) < 1e-6, 'dense pad height must not be enlarged to a display floor');
  assert.ok(Math.abs(shape.holes[0].getPoint(0).length() - .01 * scale) < 1e-9, 'drill radius must not be enlarged');
  geometry.dispose();
}

const classified = new THREE.Group();
const classifiedGeometry = new THREE.BoxGeometry(.001, .002, .003);
const classifiedMaterial = new THREE.MeshStandardMaterial();
for (const componentMount of ['smd', 'tht']) for (const componentSide of [-1, 1]) {
  for (let index = 0; index < 8; index++) {
    const mesh = new THREE.Mesh(classifiedGeometry, classifiedMaterial);
    mesh.userData = { componentMount, componentSide };
    mesh.position.set(index * .004, componentSide * .003, componentMount === 'smd' ? 0 : .02);
    classified.add(mesh);
  }
}
const classifiedResult = prepare(classified, 'components');
assert.equal(classifiedResult.displayMeshes, 4, 'mount categories and board sides must not merge together');
assert.deepEqual(new Set(classifiedResult.model.children.map(mesh => `${mesh.userData.componentMount}:${mesh.userData.componentSide}`)),
  new Set(['smd:-1', 'smd:1', 'tht:-1', 'tht:1']));

const layers = ['F.Cu', ...Array.from({ length: 30 }, (_, i) => `In${i + 1}.Cu`), 'B.Cu'];
assert.deepEqual(resolveBoardCopperLayers(layers, ['*.Cu', '*.Mask']), layers);
assert.deepEqual(resolveBoardCopperLayers(layers, ['F&B.Cu']), ['F.Cu', 'B.Cu']);
assert.doesNotMatch(source, /evenlyBoundedDisplayItems\(activeBoard\./,
  'dense boards must retain all tracks, pads, vias and components');
assert.match(source, /resolveBoardCopperLayers\(activeBoard\.layers, pad\.layers\)/,
  'the fallback must draw through-hole pads on all declared copper layers');

const scene = new THREE.Group();
const geometry = new THREE.BoxGeometry(0.002, 0.001, 0.001);
const materials = Array.from({ length: 8 }, () => new THREE.MeshStandardMaterial());
for (let i = 0; i < 2000; i++) {
  const component = new THREE.Group();
  component.name = `U${i + 1}`;
  component.position.set((i % 50) * .004, Math.floor(i / 50) * .003, i % 2 ? -.002 : .002);
  component.add(new THREE.Mesh(geometry, materials[i % materials.length]));
  scene.add(component);
}
const before = new THREE.Box3().setFromObject(scene);
const started = performance.now();
const result = prepare(scene, 'components');
const after = new THREE.Box3().setFromObject(result.model);
assert.equal(result.sourceMeshes, 2000);
assert.equal(result.displayMeshes, 8);
assert.ok(before.min.distanceTo(after.min) < 1e-7 && before.max.distanceTo(after.max) < 1e-7,
  'merging must preserve every placed component, including both board sides');
assert.equal(result.model.children.reduce((sum, mesh) => sum + mesh.geometry.index.count / 3 * (mesh.isInstancedMesh ? mesh.count : 1), 0), 24000);
assert.ok(result.model.children.every(mesh => mesh.isInstancedMesh), 'repeated static parts should share instance geometry');
assert.equal(new Set(result.model.children.map(mesh => mesh.geometry)).size, 1);
assert.equal(result.model.children.reduce((sum, mesh) => sum + mesh.instanceMatrix.array.byteLength, 0), 2000 * 64);
console.log(`2000 component scene: ${result.sourceMeshes} meshes -> ${result.displayMeshes} batches; ${Math.round(performance.now() - started)} ms; all triangles retained`);

// High part count with a tessellated model: do not allocate a transformed copy
// of every vertex for each occurrence. Verify instance matrices as well as bounds.
const dense = new THREE.Group();
const detailedGeometry = new THREE.SphereGeometry(.001, 32, 16);
const detailedMaterial = new THREE.MeshStandardMaterial();
for (let i = 0; i < 20_000; i++) {
  const mesh = new THREE.Mesh(detailedGeometry, detailedMaterial);
  mesh.position.set(i % 200 * .004, Math.floor(i / 200) * .004, (i % 3) * .006);
  mesh.rotation.set(i % 7 * .1, i % 5 * .1, i % 11 * .1);
  dense.add(mesh);
}
dense.updateMatrixWorld(true);
const expectedMatrices = dense.children.map(mesh => mesh.matrixWorld.clone());
const vertexBytes = Object.values(detailedGeometry.attributes).reduce((sum, attr) => sum + attr.array.byteLength, 0)
  + detailedGeometry.index.array.byteLength;
const denseStart = performance.now();
const preparedDense = prepare(dense, 'components');
assert.equal(preparedDense.sourceMeshes, 20_000);
assert.equal(preparedDense.displayMeshes, 10);
const matrix = new THREE.Matrix4();
let occurrenceIndex = 0;
for (const mesh of preparedDense.model.children) {
  assert.ok(mesh.isInstancedMesh && mesh.count <= 2048);
  for (let i = 0; i < mesh.count; i++) {
    mesh.getMatrixAt(i, matrix);
    const expected = expectedMatrices[occurrenceIndex++];
    assert.ok(matrix.elements.every((value, index) => Math.abs(value - expected.elements[index]) < 1e-6));
  }
}
assert.equal(occurrenceIndex, 20_000);
assert.equal(new Set(preparedDense.model.children.map(mesh => mesh.geometry)).size, 1);
console.log(JSON.stringify({ parts: 20_000, drawBatches: preparedDense.displayMeshes,
  expandedGeometryBytes: vertexBytes * 20_000, instancedGeometryAndMatrixBytes: vertexBytes + 20_000 * 64,
  preparationMs: Math.round(performance.now() - denseStart) }));

const sorted = new THREE.Group();
const transparent = new THREE.MeshStandardMaterial({ transparent: true, opacity: .4 });
for (let i = 0; i < 4; i++) sorted.add(new THREE.Mesh(new THREE.BoxGeometry(), transparent));
assert.ok(prepare(sorted, 'components').model.children.every(mesh => !mesh.isInstancedMesh),
  'transparent objects retain independent sorting');

// Optional local fixture: the user's project stays outside committed test data.
for (const filename of process.argv.slice(2)) {
  const bytes = readFileSync(filename);
  const loaded = await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '');
  const originalBounds = new THREE.Box3().setFromObject(loaded.scene);
  const refs = loaded.scene.children.map(item => item.name);
  const prepared = prepare(loaded.scene, /components/i.test(filename) ? 'components' : 'board');
  const preparedBounds = new THREE.Box3().setFromObject(prepared.model);
  assert.ok(!preparedBounds.isEmpty());
  assert.ok(originalBounds.min.distanceTo(preparedBounds.min) < 1e-5);
  assert.ok(originalBounds.max.distanceTo(preparedBounds.max) < 1e-5);
  console.log(JSON.stringify({ filename, sourceMeshes: prepared.sourceMeshes, displayMeshes: prepared.displayMeshes, roots: refs.length }));
}
