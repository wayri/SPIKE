// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, unlinkSync, existsSync } from "node:fs";
import ts from "typescript";
import * as THREE from "three";
const names = ["importedBoardLayers", "boardSurfaceMaterials"];
try {
  for (const name of names) writeFileSync(new URL(`./.test-${name}.mjs`, import.meta.url), ts.transpileModule(readFileSync(new URL(`../src/${name}.ts`, import.meta.url), "utf8"), {compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText.replaceAll('"./boardSurfaceMaterials"','"./.test-boardSurfaceMaterials.mjs"'));
  const {tagImportedBoardLayers, importedBoardLayerVisible} = await import("./.test-importedBoardLayers.mjs");
  const {configureImportedMaterial, classifyBoardSurface} = await import("./.test-boardSurfaceMaterials.mjs");
  for (const rgb of [[.0062745097,.1850980371,.5082352757], [.5,.03,.02]]) {
    const material = new THREE.MeshStandardMaterial({color:new THREE.Color(...rgb),opacity:.83,transparent:true,roughness:.6});
    assert.equal(classifyBoardSurface(material,"=>0117"),"soldermask","unnamed colored KiCad masks retain their surface identity");
    const maskRoot = new THREE.Group();
    const body = new THREE.Mesh(new THREE.BoxGeometry(.02,.0016,.01),new THREE.MeshStandardMaterial({roughness:.8})); body.name="substrate";
    const mask = new THREE.Mesh(new THREE.PlaneGeometry(.02,.01),material); mask.rotation.x=Math.PI/2; mask.position.y=.00085;
    maskRoot.add(body,mask);
    assert.ok(tagImportedBoardLayers(maskRoot).has("F.Mask"),"colored mask stays addressable for visibility and opacity controls");
  }
  assert.equal(classifyBoardSurface(new THREE.MeshStandardMaterial({color:0x808080,opacity:.83,roughness:.6}),"unnamed"),"unknown","neutral translucent surfaces do not imply soldermask");
  const root = new THREE.Group();
  const copperMaterial = new THREE.MeshStandardMaterial({metalness:1});
  const surface = (name,y,material,height=.00004) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(.02,height,.01),material); mesh.name=name; mesh.position.y=y; root.add(mesh); return mesh;
  };
  const body = surface("substrate",.0008,new THREE.MeshStandardMaterial({roughness:.8}),.0016);
  const front = surface("copper",.00162,copperMaterial), back = surface("copper",-.00002,copperMaterial);
  const maskMaterial = new THREE.MeshStandardMaterial({color:0x08623c,opacity:.83,transparent:true});
  const fm = surface("soldermask",.00164,maskMaterial), bm = surface("soldermask",-.00004,maskMaterial);
  const silk = surface("silkscreen",.00166,new THREE.MeshStandardMaterial({color:0xffffff,opacity:.9}));
  const via = surface("copper",.0008,copperMaterial,.0017);
  root.position.set(20,30,40); root.rotation.z=1; root.scale.setScalar(2);
  const layers = tagImportedBoardLayers(root);
  assert.deepEqual([...layers].sort(),["Board body","F.Cu","B.Cu","F.Mask","B.Mask","F.SilkS","through"].sort());
  assert.equal(front.userData.importedBoardLayer,"F.Cu"); assert.equal(back.userData.importedBoardLayer,"B.Cu");
  assert.notEqual(front.material,back.material,"shared exporter material is independent by side");
  fm.material.opacity=.1; assert.equal(bm.material.opacity,.83,"mask opacity cannot bleed across sides");
  assert.equal(importedBoardLayerVisible("F.Cu",{"B.Mask":false},["F.Cu","B.Cu"],true),true);
  assert.equal(importedBoardLayerVisible("through",{},["F.Cu","B.Cu"],false),false);
  assert.equal(importedBoardLayerVisible("through",{"F.Cu":false,"B.Cu":false},["F.Cu","B.Cu"],true),false);
  for (const mesh of [body,front,back,fm,bm,silk,via]) {
    const first=configureImportedMaterial(mesh.material,"board",mesh.name);
    assert.equal(configureImportedMaterial(mesh.material,"board",mesh.name),first,"surface policy is idempotent");
  }
  const combinedRoot = new THREE.Group();
  const combinedBody = new THREE.Mesh(new THREE.BoxGeometry(.02,.0016,.01),new THREE.MeshStandardMaterial({roughness:.8})); combinedBody.name="substrate"; combinedRoot.add(combinedBody);
  const combined = new THREE.Mesh(new THREE.BoxGeometry(.02,.0018,.01),new THREE.MeshStandardMaterial({metalness:1})); combined.name="copper"; combinedRoot.add(combined);
  const originalTriangles=combined.geometry.index.count;
  tagImportedBoardLayers(combinedRoot);
  const parts=combinedRoot.children.filter(mesh=>mesh.userData.importedBoardSurface==="copper");
  assert.deepEqual(parts.map(mesh=>mesh.userData.importedBoardLayer).sort(),["F.Cu","B.Cu","through"].sort(),"a single consolidated copper mesh is split by actual triangle height");
  assert.equal(parts.reduce((sum,mesh)=>sum+mesh.geometry.index.count,0),originalTriangles,"splitting preserves every triangle once");
  assert.ok(parts.every(mesh=>mesh.material!==combined.material),"split copper ranges own their layer materials");
  // Exercise the actual exported primitive bounds/materials, rather than only
  // ideal centered fixtures. KiCad uses Y=0..thickness and fragmented surfaces.
  const modelPath=new URL("../public/demo/models/ebrake1_board.glb",import.meta.url);
  const bytes=existsSync(modelPath)?readFileSync(modelPath):null;
  const glb=bytes?JSON.parse(bytes.subarray(20,20+bytes.readUInt32LE(12)).toString("utf8")):JSON.parse(readFileSync(new URL("./fixtures/kicad-board-layer-fragments.json",import.meta.url),"utf8"));
  const real = new THREE.Group();
  const materials=glb.materials.map(m=> {const p=m.pbrMetallicRoughness;return new THREE.MeshStandardMaterial({color:new THREE.Color(...p.baseColorFactor.slice(0,3)),metalness:p.metallicFactor,roughness:p.roughnessFactor,opacity:p.baseColorFactor[3],transparent:m.alphaMode==="BLEND"});});
  for (const source of glb.meshes) for (const primitive of source.primitives) {
    const bounds=glb.accessors[primitive.attributes.POSITION]; if(!bounds.min||!bounds.max) continue;
    const geometry=new THREE.BufferGeometry(); geometry.setAttribute("position",new THREE.Float32BufferAttribute([...bounds.min,...bounds.max],3));
    const mesh=new THREE.Mesh(geometry,materials[primitive.material]); mesh.name=source.name; real.add(mesh);
  }
  const realLayers=tagImportedBoardLayers(real);
  for(const layer of ["F.Cu","B.Cu","F.Mask","B.Mask","F.SilkS","B.SilkS","Board body"]) assert.ok(realLayers.has(layer),`actual KiCad fragments address ${layer}`);
  console.log(`Imported layer classification passed on ${real.children.length} real KiCad fragments and transformed synthetic surfaces`);
} finally {for(const name of names) try {unlinkSync(new URL(`./.test-${name}.mjs`,import.meta.url));} catch {}}
