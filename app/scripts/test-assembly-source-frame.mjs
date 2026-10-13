// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";
import * as THREE from "three";

// Optional private-fixture path: no native source or confidential project is
// copied into the repository. The checked-in synthetic regression always runs.
const generated = new URL(`./.test-source-frame-${process.pid}/`, import.meta.url);
mkdirSync(generated);
const compiled = new Set();
function compile(name) {
  if (compiled.has(name)) return;
  compiled.add(name);
  const text = readFileSync(new URL(`../src/${name}.ts`, import.meta.url), "utf8");
  let output = ts.transpileModule(text, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  output = output.replace(/from "\.\/([^".]+)"/g, (_, dependency) => {
    compile(dependency); return `from "./${dependency}.mjs"`;
  });
  writeFileSync(new URL(`${name}.mjs`, generated), output);
}
try {
  for (const name of ["assemblyCanonicalBoard", "assemblyBoardScene", "assemblySceneVisibility", "harnessVisualization", "boardParser"]) compile(name);
  const { projectAssemblyCanonicalBoard } = await import(new URL("assemblyCanonicalBoard.mjs", generated));
  const { boardInstanceScene, mountKiCadScenes, kiCadLaminateMidplaneMm } = await import(new URL("assemblyBoardScene.mjs", generated));
  const { applyAssemblySceneVisibility } = await import(new URL("assemblySceneVisibility.mjs", generated));
  const { buildVirtualBoardVisualization } = await import(new URL("harnessVisualization.mjs", generated));
  const { parseKicadBoard } = await import(new URL("boardParser.mjs", generated));
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const source = {
    bounds: { minX: 40, minY: 30, maxX: 60, maxY: 40 }, width: 20, height: 10,
    outlineLoops: [[[40,30],[60,30],[60,40],[40,40]]],
    layers: ["F.Cu", "B.Cu"], layerDefinitions: [], nets: {}, zones: [], vias: [], drawings: [],
    stackup: [{name:"F.Mask",thickness:.01},{name:"F.Cu",thickness:.07},{name:"core",thickness:1.44},{name:"B.Cu",thickness:.07},{name:"B.Mask",thickness:.01}],
    tracks: [{id:"t",start:[42,32],end:[48,32],width:1,layer:"F.Cu"}],
    pads: [{id:"p",at:[45,35],width:2,height:1,layers:["F.Cu"],layer:"F.Cu",rotation:30,shape:"rect",ref:"U1"}],
    components: [false,true].map((back,i)=>({id:`c${i}`,ref:`U${i+1}`,at:[45,35],width:3,height:2,rotation:30,layer:back?"B.Cu":"F.Cu"})),
    boardModelIncludesCopper: false,
  };
  const visual = { id:"base",designId:"base",localCenterMm:[50,35,0],transform:identity,widthMm:20,heightMm:10 };
  const canonical = {contract:"spike/design-ir/v2",design_id:"canonical",metadata:{board_bounds_mm:[40,30,60,40],"spike.v1.stackup":source.stackup},
    layers:[{id:"top",name:"F.Cu",layer_type:"copper"},{id:"back",name:"B.Cu",layer_type:"copper"}],nets:[{id:"n",name:"GND"}],models:[],zones:[],vias:[],
    tracks:[{id:"track",start_mm:[42,32],end_mm:[48,32],width_mm:1,layer_id:"top",net_id:"n"}],
    components:[{id:"canonical-part",reference:"U7",position_mm:[46,36],rotation_deg:30,side:"bottom",model_ids:[]}],
    pads:[{id:"canonical-pad",center_mm:[46,36],size_mm:[2,1],drill_size_mm:[.4,.4],component_id:"canonical-part",layer_ids:["*.Cu"],shape:"rect",net_id:"n",extensions:{"spike.v1":{rotation:30}}}]};
  const canonicalView=projectAssemblyCanonicalBoard(canonical);
  assert.equal(canonicalView.pads[0].at,canonical.pads[0].center_mm,"display shares immutable canonical coordinates");
  assert.equal(canonicalView.components[0].at,canonical.components[0].position_mm);
  assert.equal(canonicalView.components[0].layer,"B.Cu");
  assert.equal(canonicalView.pads[0].ref,"U7");
  assert.equal(canonicalView.tracks[0].net,"GND");
  assert.throws(()=>projectAssemblyCanonicalBoard({...canonical,metadata:{}}),/native bounds/);
  const scene = boardInstanceScene(visual, false, [], {source});
  const exported = new THREE.Group();
  const laminate = new THREE.Mesh(new THREE.BoxGeometry(.02,.00144,.01), new THREE.MeshStandardMaterial({color:0x315f45}));
  laminate.name="board substrate"; laminate.position.set(.05,.00072,.035); exported.add(laminate);
  const components = new THREE.Group();
  const model = new THREE.Group(); model.name="U1"; model.position.set(.045,.00156,.035);
  const offset = new THREE.Mesh(new THREE.BoxGeometry(.001,.001,.001),new THREE.MeshStandardMaterial());
  offset.position.set(.0003,.0002,.0004); model.add(offset); components.add(model);
  const unresolvedGroup=new THREE.Group(); unresolvedGroup.name="U2"; components.add(unresolvedGroup);
  mountKiCadScenes(scene, visual, source, exported, components);
  applyAssemblySceneVisibility(scene.group,source,{}, {}, true);
  scene.group.updateMatrixWorld(true);
  assert.equal(kiCadLaminateMidplaneMm(source), .72);
  const copper = scene.pickables.find(mesh=>mesh.userData.sceneKind==="copper-pad");
  const copperZ = copper.getWorldPosition(new THREE.Vector3()).z;
  assert.ok(Math.abs(copper.rotation.z+Math.PI/6)<1e-10,"native pad angle is not mirrored in source XY");
  const bodyBounds = new THREE.Box3().setFromObject(laminate);
  assert.ok(copperZ > bodyBounds.max.z, "fallback top copper must not be buried in native GLB laminate");
  assert.deepEqual(model.getWorldPosition(new THREE.Vector3()).toArray(),[45,35,1.56],"native mount datum is not recentered or fitted to component bounds");
  const modelOffset = offset.getWorldPosition(new THREE.Vector3()).sub(model.getWorldPosition(new THREE.Vector3()));
  assert.ok(modelOffset.distanceTo(new THREE.Vector3(.3,.4,.2))<1e-8,"native model-local offsets survive exact axis conversion and parenting");
  const bottom = scene.pickables.find(mesh=>mesh.userData.componentRef==="U2");
  assert.ok(Math.abs(bottom.rotation.z+Math.PI/6)<1e-10,"native fallback component angle matches the source frame");
  assert.ok(bottom.getWorldPosition(new THREE.Vector3()).z + .625 < bodyBounds.min.z,"backside fallback remains below the native board");
  assert.equal(bottom.userData.geometryStatus,"fallback-not-cad");
  assert.equal(bottom.visible,true,"an empty named CAD group cannot erase unresolved fallback geometry");
  assert.equal(copper.material.colorWrite,true,"lightweight native board cannot suppress retained copper");
  assert.equal(scene.pickables.filter(mesh=>mesh.userData.sceneKind==="component-placeholder").length,2);

  if (process.argv[2]) {
    const root = resolve(process.argv[2]);
    const retained = JSON.parse(readFileSync(resolve(root,"design/assembly-designs.json"),"utf8"));
    const assembly = JSON.parse(readFileSync(resolve(root,"design/assembly-ir.json"),"utf8"));
    const projection = buildVirtualBoardVisualization(assembly,retained);
    assert.equal(projection.visuals.length,5);
    const reports = [];
    for (const [i,design] of retained.designs.entries()) {
      const start=performance.now();
      const parsed=projectAssemblyCanonicalBoard(design);
      const projectionMs=performance.now()-start;
      const native=parseKicadBoard(readFileSync(resolve(root,"sources",`${design.source.source_digest}.kicad_pcb`),"utf8"));
      const byRef=new Map(native.components.map(component=>[component.ref,component]));
      assert.equal(parsed.components.length,i===0?434:1752);
      const originDifferences=[];
      for (const component of parsed.components) {
        const original=byRef.get(component.ref); assert.ok(original,component.ref);
        assert.deepEqual(component.at,design.components.find(row=>row.reference===component.ref).position_mm,`retained component origin ${component.ref}`);
        if(Math.hypot(component.at[0]-original.at[0],component.at[1]-original.at[1])>1e-7)
          originDifferences.push({ref:component.ref,retained:component.at,native:original.at});
        assert.equal(component.rotation,original.rotation,`native component angle ${component.ref}`);
        assert.equal(component.layer,original.layer,`native component side ${component.ref}`);
      }
      assert.equal(parsed.tracks.length,design.tracks.length);
      assert.equal(parsed.pads.length,design.pads.length);
      for (let n=0;n<parsed.pads.length;n++) assert.deepEqual(parsed.pads[n].at,design.pads[n].center_mm);
      const b=parsed.bounds;
      const offboard=parsed.components.filter(c=>c.at[0]<b.minX||c.at[0]>b.maxX||c.at[1]<b.minY||c.at[1]>b.maxY);
      assert.equal(offboard.length,i===0?83:56,"off-outline inventory is source-native, not renderer displacement");
      assert.deepEqual(offboard.map(c=>c.ref).sort(),native.components.filter(c=>c.at[0]<b.minX||c.at[0]>b.maxX||c.at[1]<b.minY||c.at[1]>b.maxY).map(c=>c.ref).sort());
      if(i===0) assert.equal(offboard.filter(c=>/^R13(?:0\d|1\d|20)$/.test(c.ref)).length,21);
      const visual=projection.visuals.find(row=>row.designId===design.design_id);
      const sceneStart=performance.now();
      const rendered=boardInstanceScene(visual,false,[],{source:parsed});
      rendered.group.updateMatrixWorld(true);
      const matrix=new THREE.Matrix4().set(...visual.transform);
      const parts=rendered.pickables.filter(mesh=>mesh.userData.sceneKind==="component-placeholder");
      assert.equal(parts.length,parsed.components.length);
      for(let n=0;n<parts.length;n++) {
        const component=parsed.components[n], height=parts[n].geometry.parameters.depth;
        const thickness=parsed.stackup.reduce((sum,row)=>sum+(row.thickness??0),0)||1.6;
        const z=kiCadLaminateMidplaneMm(parsed)+(component.layer.startsWith("B.")?-1:1)*(thickness/2+height/2+.012);
        const expected=new THREE.Vector3(...component.at,z).applyMatrix4(matrix);
        assert.ok(parts[n].getWorldPosition(new THREE.Vector3()).distanceTo(expected)<1e-8);
      }
      reports.push({designId:design.design_id,components:parts.length,tracks:parsed.tracks.length,pads:parsed.pads.length,zones:parsed.zones.length,offboard:offboard.map(c=>c.ref),originDifferenceCount:originDifferences.length,originDifferenceExamples:originDifferences.slice(0,5),projectionMs,sceneMs:performance.now()-sceneStart});
      const geometries=new Set(),materials=new Set();
      rendered.group.traverse(object=>{if(object.geometry)geometries.add(object.geometry);if(object.material)for(const material of Array.isArray(object.material)?object.material:[object.material])materials.add(material);});
      geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());
    }
    console.log(JSON.stringify({fixture:root,occurrences:projection.visuals.length,reports,maxRssKiB:process.resourceUsage().maxRSS},null,2));
  }
  console.log("Assembly source-frame, native datum, fallback copper and component parenting regressions passed.");
} finally {
  rmSync(generated,{recursive:true,force:true});
}
