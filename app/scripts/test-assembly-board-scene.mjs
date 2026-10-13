import assert from "node:assert/strict";
import { readFileSync, writeFileSync, unlinkSync, existsSync } from "node:fs";
import ts from "typescript";

const generated = ["componentPlaceholder","assemblyBoardScene", "assemblyNetIdentity", "assemblyCopperBatches", "assemblyImportedBatches", "assemblySceneVisibility", "boardParser", "kikakukaFlex", "numericRange", "boardSurfaceMaterials", "componentSceneIndex", "importedBoardLayers", "mergedGeometryTransforms"];
try {
  for (const name of generated) {
    let source = readFileSync(new URL(`../src/${name}.ts`, import.meta.url), "utf8");
    let output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
    output = output.replaceAll('"./assemblyCopperBatches"', '"./.test-assemblyCopperBatches.mjs"').replaceAll('"./boardParser"', '"./.test-boardParser.mjs"').replaceAll('"./numericRange"', '"./.test-numericRange.mjs"').replaceAll('"./harnessVisualization"', '"./.test-harnessVisualization.mjs"');
    for (const dependency of ["componentPlaceholder","importedBoardLayers", "assemblyNetIdentity", "boardSurfaceMaterials", "componentSceneIndex", "assemblyImportedBatches", "kikakukaFlex", "mergedGeometryTransforms"]) output = output.replaceAll(`"./${dependency}"`, `"./.test-${dependency}.mjs"`);
    writeFileSync(new URL(`./.test-${name}.mjs`, import.meta.url), output);
  }
  const THREE = await import("three");
  const { boardInstanceScene, mountKiCadScenes } = await import(`./.test-assemblyBoardScene.mjs?${Date.now()}`);
  const board = { id: "occ-7", name: "Board", designId: "design", active: true, widthMm: 20, heightMm: 10, localCenterMm: [20, 15, 0], transform: [1, 0, 0, 100, 0, 1, 0, 200, 0, 0, 1, 30, 0, 0, 0, 1], thicknessMm: 2, netIdsByName: { GND: "net-uuid-1" } };
  const source = {
    width: 20, height: 10, bounds: { minX: 10, minY: 10, maxX: 30, maxY: 20 },
    outlineLoops: [[[10, 10], [30, 10], [30, 20], [10, 20], [10, 10]], [[18, 13], [22, 13], [22, 17], [18, 17], [18, 13]]],
    tracks: [{ id: "t1", start: [12, 12], end: [28, 12], width: 1.2, layer: "F.Cu", net: "GND" }],
    vias: [{ id: "v1", at: [15, 15], size: 1, drill: .4, layers: ["F.Cu", "B.Cu"], net: "1" }],
    pads: [{ id: "p1", name: "1", at: [25, 15], width: 2, height: 1, rotation: 0, shape: "rect", drill: 0, layers: ["F.Cu"], layer: "F.Cu", net: "1", ref: "U1" }],
    components: [{ id: "c1", ref: "U1", value: "IC", library: "x", at: [25, 15], width: 4, height: 3, rotation: 0, layer: "F.Cu", modelOffset: [0, 0, 0], modelScale: [1, 1, 1], modelRotation: [0, 0, 0] }],
    zones: [{ id: "z1", points: [[11, 11], [14, 11], [14, 14]], holes: [], layer: "B.Cu", net: "1" }],
    drawings: [{ id: "d1", type: "line", points: [[11, 19], [29, 19]], layer: "F.SilkS", width: .2 }],
    layers: ["F.Cu", "B.Cu"], layerDefinitions: [{ id: 0, name: "F.Cu", kind: "signal" }, { id: 31, name: "B.Cu", kind: "signal" }], stackup: [], nets: { "1": "GND" }, boardModelIncludesCopper: true,
  };
  const metadataSource={...source,components:[{...source.components[0],properties:{Height:"6.5mm"}}]};
  const metadataScene=boardInstanceScene(board,false,[],{source:metadataSource});
  const heightBlock=metadataScene.pickables.find(mesh=>mesh.userData.sceneKind==="component-placeholder");
  assert.equal(heightBlock.geometry.parameters.depth,6.5,"assembly stand-in honors supplied physical height");
  assert.equal(heightBlock.userData.placeholderHeightSource,"metadata");
  const bottomScene=boardInstanceScene(board,false,[],{source:{...metadataSource,components:[{...metadataSource.components[0],layer:"B.Cu"}]}});
  const bottomBlock=bottomScene.pickables.find(mesh=>mesh.userData.sceneKind==="component-placeholder");
  assert.equal(bottomBlock.geometry.parameters.depth,6.5); assert(bottomBlock.position.z < heightBlock.position.z,"bottom stand-in remains on the bottom side");
  for(const scene of [metadataScene,bottomScene]) scene.group.traverse(object=>{object.geometry?.dispose(); if(object.material) for(const material of Array.isArray(object.material)?object.material:[object.material]) material.dispose();});
  const result = boardInstanceScene(board, false, ["net-uuid-1"], { source, showSmd: true });
  const { updateAssemblySceneSelection, applyAssemblySceneVisibility } = await import("./.test-assemblySceneVisibility.mjs");
  const highlightedTrack = result.pickables.find(item => item.userData.sourceObjectId === "t1");
  assert.equal(highlightedTrack.material.color.getHex(),0x55e5d5,"initial linked copper uses SPIKE net highlight color");
  updateAssemblySceneSelection(result.group,false,[]);
  assert.equal(highlightedTrack.material.color.getHex(),0xc47b2b,"clearing an initial net selection restores copper material");
  let substrate;
  result.group.traverse(object => { if (object.userData.sourceObjectId === "board-substrate") substrate = object; });
  assert.equal(substrate.geometry.parameters.shapes.holes.length, 1, "inner outline must cut a board hole");
  const track = result.pickables.find(x => x.userData.sourceObjectId === "t1");
  track.geometry.computeBoundingBox();
  assert.ok(Math.abs(track.geometry.boundingBox.max.y - track.geometry.boundingBox.min.y - 1.2) < 1e-6, "track mesh retains imported width");
  assert.equal(track.userData.boardOccurrenceId, "occ-7");
  assert.equal(track.userData.canonicalNetId, "net-uuid-1");
  assert.equal(result.pickables.find(x => x.userData.sceneKind === "copper-pad").userData.canonicalNetId, "net-uuid-1", "numeric parser nets resolve through the canonical name mapping");
  assert.equal(track.position.x, 0, "board feature coordinates are centered locally");
  assert.equal(result.group.userData.boardLocalCenterMm, board.localCenterMm, "placement pivot remains available to the viewport");
  assert.ok(result.pickables.some(x => x.userData.sceneKind === "component-placeholder"));
  const boardModel = new THREE.Group(), modelMesh = new THREE.Mesh(new THREE.BoxGeometry(.02, .0016, .01), new THREE.MeshBasicMaterial()); boardModel.add(modelMesh);
  const componentModel = new THREE.Group();
  const componentRoot = new THREE.Group(); componentRoot.name = "U1_body";
  const componentMesh = new THREE.Mesh(new THREE.BoxGeometry(.001, .002, .003), new THREE.MeshBasicMaterial());
  componentRoot.add(componentMesh); componentModel.add(componentRoot);
  mountKiCadScenes(result, board, source, boardModel, componentModel);
  assert.equal(boardModel.scale.x, 1, "normalization preserves imported root transforms");
  assert.equal(boardModel.rotation.x, 0, "normalization preserves imported root orientation");
  const boardFrame = boardModel.parent;
  const componentFrame = componentModel.parent;
  assert.equal(boardFrame.userData.kiCadSceneKind, "board", "baked board roots remain distinguishable for layer visibility");
  assert.equal(componentFrame.userData.kiCadSceneKind, "components", "component roots remain independently visible");
  const modelPath = new URL("../public/demo/models/ebrake1_board.glb", import.meta.url);
  const realGlb = existsSync(modelPath) ? readFileSync(modelPath) : null;
  const glbJson = realGlb ? JSON.parse(realGlb.subarray(20, 20 + realGlb.readUInt32LE(12)).toString("utf8"))
    : JSON.parse(readFileSync(new URL("./fixtures/kicad-board-layer-fragments.json", import.meta.url), "utf8"));
  const realPosition = glbJson.accessors.find(accessor => accessor.type === "VEC3" && accessor.min)?.min;
  assert.ok(realPosition, "checked-in KiCad GLB must expose position bounds");
  const sourcePoint = new THREE.Vector3(...realPosition);
  const boardLocal = sourcePoint.clone().applyMatrix4(boardFrame.matrix);
  const normalViewport = new THREE.Vector3(
    sourcePoint.x * 1000 - board.localCenterMm[0],
    board.localCenterMm[1] - sourcePoint.z * 1000,
    sourcePoint.y * 1000 - board.localCenterMm[2],
  );
  const assemblyViewport = boardLocal.clone(); assemblyViewport.y *= -1;
  assert.deepEqual(assemblyViewport.toArray().map(value => Math.round(value * 1e9) / 1e9), normalViewport.toArray().map(value => Math.round(value * 1e9) / 1e9), "normal and assembly views map an actual KiCad GLB mesh bound identically");
  assert.equal(track.visible, true, "linked net overlay remains visible over authoritative copper");
  assert.ok(result.pickables.includes(modelMesh), "authoritative geometry participates in occurrence picking");
  assert.equal(componentMesh.userData.componentRef, "U1", "component identity is inherited by unnamed GLB mesh descendants");
  assert.equal(componentMesh.userData.sceneKind, "component-model");
  assert.equal(result.group.children.find(x => x.userData.sceneKind === "component-placeholder")?.visible, false, "only resolved component placeholders are hidden");
  const placeholder = result.group.children.find(x => x.userData.sceneKind === "component-placeholder");
  const unresolved = placeholder.clone();
  unresolved.userData = { ...placeholder.userData, componentRef: "U2", replacedByResolvedModel: false };
  result.group.add(unresolved);
  for (const layerSettings of [{}, { "F.Cu": false }, { "F.Cu": true }]) {
    updateAssemblySceneSelection(result.group, true, ["net-uuid-1"]);
    applyAssemblySceneVisibility(result.group, source, layerSettings, { "F.Cu": .5 }, true);
    assert.equal(placeholder.visible, false, "resolved stand-in stays hidden after layer/selection updates");
    assert.equal(unresolved.visible, true, "footprint copper layer never hides unresolved component stand-ins");
    assert.equal(componentMesh.visible, true, "resolved component remains rendered");
    assert.equal(unresolved.material.opacity, 1, "copper opacity never changes component stand-ins");
  }
  const secondOccurrence = boardInstanceScene({ ...board, id: "occ-8" }, false, [], { source });
  applyAssemblySceneVisibility(secondOccurrence.group, source, {}, {}, true);
  assert.equal(secondOccurrence.group.children.find(x => x.userData.sceneKind === "component-placeholder")?.visible, true,
    "resolution in one occurrence never hides another occurrence's fallback");
  const denseSource = { ...source, tracks: Array.from({length: 1000}, (_, i) => ({...source.tracks[0], id: `dense-${i}`, start: [12, 10 + i / 100], end: [28, 10 + i / 100]})) };
  const dense = boardInstanceScene(board, false, [], {source: denseSource});
  const stats = dense.group.children[0].userData.copperDrawCalls;
  assert.equal(stats.before, 1004);
  assert.equal(stats.after, 5, "1000 same-net tracks are one rendering batch, all other categories retained");
  assert.equal(dense.pickables.filter(mesh => mesh.userData.sceneKind === "copper-track").length, 1000, "every exact source pick survives batching");
  assert.equal(new Set(dense.pickables.filter(mesh => mesh.userData.sceneKind === "copper-track").map(mesh => mesh.material)).size, 1,
    "same occurrence/kind/layer/net shares one nonrendering source material");
  dense.group.updateMatrixWorld(true);
  const proxy = dense.pickables.find(mesh => mesh.userData.sourceObjectId === "dense-0");
  assert.equal(proxy.material.visible, false, "source proxies do not submit draw calls");
  const ray = new THREE.Raycaster(new THREE.Vector3(120, 210, 40), new THREE.Vector3(0, 0, -1));
  ray.layers.enable(31);
  assert.ok(ray.intersectObject(proxy).length, "nonrendered exact proxy remains raycastable after world placement");
  let trackBatch;
  dense.group.traverse(mesh => { if(mesh.userData.assemblyCopperBatch && mesh.userData.sceneKind === "copper-track") trackBatch = mesh; });
  assert.equal(trackBatch.userData.sourceObjectCount, 1000);
  assert.equal(trackBatch.userData.canonicalNetId, "net-uuid-1");
  trackBatch.geometry.computeBoundingBox();
  assert.ok(trackBatch.geometry.boundingBox.min.x < -8 && trackBatch.geometry.boundingBox.max.x > 8, "all imported track widths and positions enter batch geometry");
  console.log(`Copper batching: ${stats.before} -> ${stats.after} draw calls; 1000 exact track picks preserved.`);
  const copperLayers = ["F.Cu", ...Array.from({ length: 28 }, (_, i) => `In${i + 1}.Cu`), "B.Cu"];
  const multilayerSource = { ...source, tracks: [], vias: [], zones: [], components: [], drawings: [],
    layers: copperLayers, layerDefinitions: copperLayers.map((name, id) => ({ name, id, kind: "signal" })),
    pads: Array.from({ length: 64 }, (_, i) => ({ ...source.pads[0], id: `p${i}`, at: [12 + i % 8 * 2, 11 + Math.floor(i / 8)],
      layers: ["*.Cu"], rotation: i % 4 * 90, net: i % 2 ? "OTHER" : "GND" })) };
  const multilayer = boardInstanceScene(board, false, [], { source: multilayerSource });
  const padPicks = multilayer.pickables.filter(mesh => mesh.userData.sceneKind === "copper-pad");
  assert.equal(padPicks.length, 64 * 30, "all pad/layer identities survive sharing");
  assert.equal(new Set(padPicks.map(mesh => mesh.geometry)).size, 64, "each pad is tessellated once across all 30 layers");
  assert.equal(new Set(padPicks.map(mesh => mesh.material)).size, 60, "materials stay scoped to both nets on every layer");
  const uniqueBytes = geometries => [...geometries].reduce((sum, geometry) => sum
    + Object.values(geometry.attributes).reduce((bytes, attribute) => bytes + attribute.array.byteLength, 0)
    + (geometry.index?.array.byteLength ?? 0), 0);
  const sourceBytes = uniqueBytes(new Set(padPicks.map(mesh => mesh.geometry)));
  const expandedBytes = padPicks.reduce((sum, mesh) => sum + uniqueBytes([mesh.geometry]), 0);
  assert.equal(expandedBytes, sourceBytes * 30);
  for (let i = 0; i < 64; i++) {
    const picks = padPicks.filter(mesh => mesh.userData.sourceObjectId.startsWith(`p${i}:`));
    assert.equal(picks.length, 30);
    assert.equal(new Set(picks.map(mesh => mesh.position.z)).size, 30, "each physical copper plane stays distinct");
    assert.ok(picks.every(mesh => mesh.rotation.z === -multilayerSource.pads[i].rotation * Math.PI / 180));
  }
  applyAssemblySceneVisibility(multilayer.group, multilayerSource, { "F.Cu": false }, { "B.Cu": .35 }, true);
  updateAssemblySceneSelection(multilayer.group, false, ["net-uuid-1"]);
  applyAssemblySceneVisibility(multilayer.group, multilayerSource, { "F.Cu": false }, { "B.Cu": .35 }, true);
  assert.ok(padPicks.filter(mesh => mesh.userData.layer === "F.Cu").every(mesh => !mesh.visible));
  assert.ok(padPicks.filter(mesh => mesh.userData.layer === "B.Cu").every(mesh => mesh.material.opacity === .35 * (mesh.userData.linkedAssemblyNet ? 1 : .28)));
  assert.ok(padPicks.filter(mesh => mesh.userData.layer === "In1.Cu").every(mesh => mesh.visible && mesh.material.opacity === (mesh.userData.linkedAssemblyNet ? 1 : .28)));
  assert.ok(padPicks.filter(mesh => mesh.userData.canonicalNetId === "net-uuid-1").every(mesh => mesh.material.color.getHex() === 0x55e5d5));
  assert.ok(padPicks.filter(mesh => mesh.userData.canonicalNetId !== "net-uuid-1").every(mesh => mesh.material.color.getHex() === 0x667076));
  updateAssemblySceneSelection(multilayer.group,false,[]);
  applyAssemblySceneVisibility(multilayer.group,multilayerSource,{"F.Cu":false},{"B.Cu":.35},true);
  assert.ok(padPicks.filter(mesh=>mesh.userData.layer==="B.Cu").every(mesh=>mesh.material.opacity===.35));
  assert.ok(padPicks.every(mesh=>mesh.material.color.getHex()===0xc47b2b),"clear net focus restores all material colors");
  const sibling = boardInstanceScene({ ...board, id: "multilayer-sibling" }, false, [], { source: multilayerSource });
  assert.ok(sibling.pickables.filter(mesh => mesh.userData.sceneKind === "copper-pad").every(mesh =>
    !padPicks.some(pick => pick.material === mesh.material || pick.geometry === mesh.geometry)), "live occurrences own their procedural resources");
  applyAssemblySceneVisibility(sibling.group, multilayerSource, {}, {}, true);
  assert.ok(sibling.pickables.every(mesh => mesh.visible && mesh.material.opacity === 1), "display edits never leak to sibling occurrences");
  const { disposeScene } = await import('../src/sceneResourceCache.ts');
  const disposals = new Map();
  for (const geometry of new Set(padPicks.map(mesh => mesh.geometry))) {
    disposals.set(geometry, 0);
    geometry.addEventListener('dispose', () => disposals.set(geometry, disposals.get(geometry) + 1));
  }
  disposeScene(multilayer.group);
  assert.ok([...disposals.values()].every(count => count === 1), "shared pad geometry is disposed exactly once on occurrence teardown");
  sibling.group.updateMatrixWorld(true);
  const siblingPad = sibling.pickables.find(mesh => mesh.userData.sourceObjectId === 'p0:F.Cu');
  const padCenter = new THREE.Vector3().setFromMatrixPosition(siblingPad.matrixWorld);
  const siblingRay = new THREE.Raycaster(padCenter.clone().add(new THREE.Vector3(0, 0, 10)), new THREE.Vector3(0, 0, -1));
  siblingRay.layers.enable(31);
  assert.ok(siblingRay.intersectObject(siblingPad).length, "closing an occurrence preserves exact sibling pad picking");
  disposeScene(sibling.group);
  console.log(JSON.stringify({ kind: "synthetic-30-layer-pad-resources", padLayerPicks: padPicks.length,
    sourceGeometries: 64, sourceMaterials: 60, sourceGeometryBytes: sourceBytes, unsharedSourceGeometryBytes: expandedBytes }));
  const implementation = readFileSync(new URL("../src/assemblyBoardScene.ts", import.meta.url), "utf8");
  assert.doesNotMatch(implementation, /tracks\.slice\s*\(/, "assembly tracks must not be truncated");
  console.log("Assembly board complete-scene assertions passed.");
} finally {
  for (const name of generated) { try { unlinkSync(new URL(`./.test-${name}.mjs`, import.meta.url)); } catch {} }
}
