import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as THREE from "three";
import ts from "typescript";
import {
  adaptiveMaximumCameraDistance,
  adaptivePerspectiveClip,
  boardSceneVisibility,
  layerObjectVisible,
  PROCEDURAL_SOLDERMASK_OPACITY,
  selectionPulseFactor,
  solverResultOverlayActive,
  substrateZBounds,
  viewportRenderProfile,
  viewportRenderOrder,
  viewportSceneIdentity,
} from "../src/viewportScenePolicy.ts";
import { buildProceduralComponentInstances, updateProceduralComponentInstances } from "../src/proceduralComponentInstances.ts";

const layers = ["F.Cu", ...Array.from({ length: 30 }, (_, index) => `In${index + 1}.Cu`), "B.Cu"];

const placeholderRecords = Array.from({ length: 20_000 }, (_, index) => ({
  id: `component-${index}`, ref: `U${index}`, layer: index % 2 ? "B.Cu" : "F.Cu",
  mount: index % 3 ? "smd" : "tht", side: index % 2 ? -1 : 1, kind: "body",
  color: 0x242b2f, position: new THREE.Vector3(index % 200, Math.floor(index / 200), index % 2 ? -1 : 1),
  rotationZ: (index % 4) * Math.PI / 2, scale: new THREE.Vector3(1, 2, 0.5),
}));
const placeholderRoot = buildProceduralComponentInstances(placeholderRecords);
const placeholderBatches = [];
placeholderRoot.traverse(object => { if (object instanceof THREE.InstancedMesh) placeholderBatches.push(object); });
assert.ok(placeholderBatches.length <= 12, "20k procedural placeholders must use bounded instanced draw batches");
for (const batch of placeholderBatches) assert.equal(batch.material.color.getHex(), 0xffffff, "instance tint must not be multiplied by a colored base material");
const missingRefs = new Set(["U7", "U8", "U9"]);
assert.equal(updateProceduralComponentInstances(placeholderRoot, {
  showModels: true, showSmd: true, showTht: true, allowAll: false, missingRefs,
  selectedId: "component-8", hoverId: "component-9", separationForLayer: layer => layer === "F.Cu" ? 4 : -4,
}), 3, "partial model loading must retain only exact missing-reference placeholders");
assert.equal(placeholderRoot.visible, true, "a requested partial fallback root must remain visible");
const instanceMatrix = new THREE.Matrix4();
const instanceScale = new THREE.Vector3();
let visibleInstances = 0;
placeholderBatches.forEach(batch => { for (let index = 0; index < batch.count; index += 1) {
  batch.getMatrixAt(index, instanceMatrix); instanceScale.setFromMatrixScale(instanceMatrix);
  if (instanceScale.lengthSq() > 0) visibleInstances += 1;
} });
assert.equal(visibleInstances, 3, "hidden replacements must be zero-scaled without losing batch identity");
for (const expected of [{ id: "component-8", color: 0xffa51f }, { id: "component-9", color: 0xff38c7 }]) {
  const batch = placeholderBatches.find(candidate => candidate.userData.instances.some(instance => instance.id === expected.id));
  const index = batch.userData.instances.findIndex(instance => instance.id === expected.id);
  batch.getMatrixAt(index, instanceMatrix);
  const position = new THREE.Vector3().setFromMatrixPosition(instanceMatrix);
  assert.equal(position.z, placeholderRecords[Number(expected.id.split("-")[1])].position.z + (expected.id === "component-8" ? 4 : -4), "layer separation must update instance position");
  const renderedColor = new THREE.Color(); batch.getColorAt(index, renderedColor);
  assert.equal(renderedColor.getHex(), expected.color, "selection and hover colors must remain per reference");
}
assert.equal(updateProceduralComponentInstances(placeholderRoot, {
  showModels: true, showSmd: false, showTht: true, allowAll: false, missingRefs,
  separationForLayer: () => 0,
}), 1, "mount filters must apply within missing-reference batches");
assert.equal(updateProceduralComponentInstances(placeholderRoot, {
  showModels: false, showSmd: true, showTht: true, allowAll: true, missingRefs: new Set(),
  separationForLayer: () => 0,
}), 0, "model toggle must hide every placeholder instance");
assert.equal(placeholderRoot.visible, false, "model toggle must hide the placeholder root");
assert.ok(placeholderBatches.every(batch => !batch.visible), "empty batches must not submit draw calls");

const extrudedSubstrateBounds = bounds => {
  const shape = new THREE.Shape();
  shape.moveTo(0, 0); shape.lineTo(4, 0); shape.lineTo(4, 3); shape.lineTo(0, 3); shape.closePath();
  const geometry = new THREE.ExtrudeGeometry(shape, { depth: bounds.depth, bevelEnabled: false });
  geometry.translate(0, 0, bounds.bottom);
  geometry.computeBoundingBox();
  return geometry.boundingBox;
};
for (const testCase of [
  { name: "two-layer with finish", copper: [0.79, -0.79], thickness: 1.6, clearance: 0.012 },
  { name: "Marble 12-layer", copper: Array.from({ length: 12 }, (_, index) => 0.91 - index * 1.82 / 11), thickness: 1.82, clearance: 0.012 },
  { name: "32-layer", copper: Array.from({ length: 32 }, (_, index) => 1.55 - index * 3.1 / 31), thickness: 3.2, clearance: 0.012 },
]) {
  const bounds = substrateZBounds(testCase.copper[0], testCase.copper.at(-1), testCase.thickness, testCase.clearance);
  const box = extrudedSubstrateBounds(bounds);
  assert.ok(bounds.depth > 0 && box, `${testCase.name} substrate must have finite volume`);
  assert.ok(box.max.z <= testCase.copper[0] - testCase.clearance + 1e-6, `${testCase.name} top copper must remain above substrate`);
  assert.ok(box.min.z >= testCase.copper.at(-1) + testCase.clearance - 1e-6, `${testCase.name} bottom copper must remain below substrate`);
}
const singleCopper = 0;
const singleBounds = substrateZBounds(singleCopper, undefined, 1.6, 0.012);
const singleBox = extrudedSubstrateBounds(singleBounds);
assert.ok(singleBox && (singleCopper < singleBox.min.z || singleCopper > singleBox.max.z), "single copper layer must not be buried in the substrate");
const emptyBounds = substrateZBounds(undefined, undefined, 1.6, 0.012);
const emptyBox = extrudedSubstrateBounds(emptyBounds);
assert.ok(emptyBox && Math.abs(emptyBox.min.z + 0.8) < 1e-6 && Math.abs(emptyBox.max.z - 0.8) < 1e-6,
  "empty copper stack must retain a finite nominal substrate");

const scene = { is3D: true, boardReady: true, componentsReady: true, split: true,
  layerFiltered: false, exploded: false, isolated: false, analysisOnly: false,
  resultsOnly: false, showModels: true, categoryFiltered: false,
  resultModelsVisible: true, missingModels: false };
const scenePolicy = overrides => boardSceneVisibility({ ...scene, ...overrides });
assert.deepEqual(scenePolicy({}), { importedBoard: true, importedComponents: true,
  proceduralComponents: false, importedRoot: true, proceduralRoot: false });
for (const count of [2, 10, 32]) {
  const copper = ["F.Cu", ...Array.from({ length: count - 2 }, (_, i) => `In${i + 1}.Cu`), "B.Cu"];
  for (const hidden of [...copper, "F.Mask", "B.SilkS", "Dwgs.User"]) {
    const policy = scenePolicy({ layerFiltered: true });
    assert.equal(policy.importedBoard, false, hidden);
    assert.equal(policy.importedComponents, true, `${hidden} must preserve source component scene`);
    assert.equal(policy.importedRoot, true, `${hidden} must not hide the component parent`);
    assert.equal(policy.proceduralRoot, true, `${hidden} must leave independently filtered layers visible`);
  }
}
for (const overrides of [{ componentsReady: false }, { missingModels: true }]) {
  const policy = scenePolicy(overrides);
  assert.equal(policy.importedBoard, true, "component state must preserve the loaded board");
  assert.equal(policy.proceduralComponents, true, "available fallback models must not be hidden by their parent");
  assert.equal(policy.proceduralRoot, true);
}
assert.equal(scenePolicy({ categoryFiltered: true }).importedComponents, true,
  "SMD/THT filtering must retain the real models in independently classified batches");
assert.equal(scenePolicy({ showModels: false }).importedBoard, true);
assert.equal(scenePolicy({ showModels: false }).importedComponents, false);
assert.equal(scenePolicy({ split: false, showModels: false }).importedBoard, false,
  "legacy fused scenes cannot retain hidden component geometry");
assert.equal(scenePolicy({ split: false, showModels: false }).proceduralRoot, true);
assert.equal(scenePolicy({ is3D: false }).importedRoot, false);
assert.equal(scenePolicy({ is3D: false }).proceduralRoot, true);
assert.equal(scenePolicy({ exploded: true }).importedComponents, true);
assert.equal(scenePolicy({ analysisOnly: true }).importedBoard, false);
assert.equal(scenePolicy({ analysisOnly: true }).importedComponents, true);
assert.equal(scenePolicy({ resultsOnly: true }).importedRoot, false);
assert.equal(scenePolicy({ resultsOnly: true }).proceduralRoot, false);
assert.equal(scenePolicy({ isolated: true }).importedRoot, false);
assert.equal(scenePolicy({ boardReady: false }).proceduralRoot, true);
assert.equal(scenePolicy({ boardReady: false }).importedComponents, true,
  "an unavailable board export must not discard successfully loaded components");

const fMaskHidden = { "F.Cu": true, "F.Mask": false };
const fMaskShown = { "F.Cu": true, "F.Mask": true };
assert.equal(layerObjectVisible("F.Cu", false, fMaskHidden), true);
assert.equal(layerObjectVisible("F.Cu", false, fMaskShown), true);
assert.equal(layerObjectVisible("F.Mask", false, fMaskHidden), false);
assert.equal(layerObjectVisible("F.Mask", false, fMaskShown), true);

assert.equal(
  layerObjectVisible("B.Cu", true, { "B.Cu": false }),
  true,
  "component model visibility must not inherit B.Cu visibility",
);
assert.equal(layerObjectVisible("B.Cu", false, { "B.Cu": false }), false);

assert.equal(solverResultOverlayActive({}, { visible: true, mode: "voltage_drop" }), true);
assert.equal(solverResultOverlayActive({}, { visible: true, mode: "geometry" }), false);
assert.equal(solverResultOverlayActive({}, { visible: true, mode: "impedance" }), false, "port impedance is not a spatial board overlay");
assert.equal(solverResultOverlayActive(null, { visible: true, mode: "voltage_drop" }), false);
assert.equal(selectionPulseFactor(1234, false, true), 1);
assert.equal(selectionPulseFactor(1234, false, false, false), 1, "disabled selection blinking must preserve a steady highlight");
assert.notEqual(selectionPulseFactor(1234, false, false), 1);

const renderKeys = layers.flatMap(layer => ["copper-zone", "copper-track", "copper-pad", "via-face"]
  .map(kind => viewportRenderOrder(kind, layer, layers)));
assert.equal(new Set(renderKeys).size, renderKeys.length, "32-layer render orders must remain independent");
assert.notEqual(
  viewportRenderOrder("mask", "F.Mask", layers),
  viewportRenderOrder("copper-zone", "F.Cu", layers),
);
assert.notEqual(
  viewportSceneIdentity("mask", "F.Mask", "surface"),
  viewportSceneIdentity("copper-zone", "F.Cu", "surface"),
);
assert.ok(PROCEDURAL_SOLDERMASK_OPACITY <= 0.25, "procedural mask must preserve visible copper context");

const closeClip = adaptivePerspectiveClip({ radius: 40, cameraDistance: 18 });
assert.ok(closeClip.near > 0 && closeClip.near < 1, "close board views need a conservative near plane");
assert.ok(closeClip.far > 180, "visible auxiliary volumes need a sufficiently distant far plane");
assert.ok(closeClip.far > closeClip.near * 100, "perspective range must remain valid");

const assemblyClip = adaptivePerspectiveClip({ radius: 5_000, cameraDistance: 20_000, cameraToBoundsCenter: 24_000 });
assert.ok(assemblyClip.far > 50_000, "large offset assemblies must remain inside the far plane");
assert.ok(assemblyClip.near <= 0.25, "logarithmic depth must preserve close inspection in a large scene");
assert.ok(adaptiveMaximumCameraDistance(5_000) >= 800_000, "large scenes need a proportional dolly range");

const standardProfile = viewportRenderProfile(500, 2);
const largeProfile = viewportRenderProfile(20_000, 2);
const ultraDenseProfile = viewportRenderProfile(500_000, 2);
assert.equal(standardProfile.largeScene, false);
assert.equal(largeProfile.largeScene, true);
assert.ok(largeProfile.fullPixelRatio <= standardProfile.fullPixelRatio);
assert.ok(largeProfile.interactionPixelRatio <= largeProfile.fullPixelRatio);
assert.ok(largeProfile.shadowMapSize < standardProfile.shadowMapSize);
assert.equal(largeProfile.dynamicShadowUpdates, false);
assert.equal(standardProfile.targetFps, 60);
assert.equal(largeProfile.targetFps, 45);
assert.equal(ultraDenseProfile.targetFps, 30);

const renderDirectory = mkdtempSync(join(process.cwd(), ".tmp-layout-render-"));
try {
  const emitted = new Set();
  const emit = name => {
    if (emitted.has(name)) return;
    emitted.add(name);
    const tsPath = new URL(`../src/${name}.ts`, import.meta.url);
    let source;
    try { source = readFileSync(tsPath, "utf8"); }
    catch { source = readFileSync(new URL(`../src/${name}.tsx`, import.meta.url), "utf8"); }
    let code = ts.transpileModule(source, { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
    }}).outputText;
    code = code.replace(/require\("\.\/([^"]+)"\)/g, (_, dependency) => {
      emit(dependency);
      return `require("./${dependency}.cjs")`;
    });
    writeFileSync(join(renderDirectory, `${name}.cjs`), code);
  };
  emit("LayoutViewport");
  const LayoutViewport = createRequire(import.meta.url)(join(renderDirectory, "LayoutViewport.cjs")).default;
  const board = {
    width: 20, height: 10, bounds: { minX: 0, minY: 0, maxX: 20, maxY: 10 },
    outlineLoops: [[[0,0],[20,0],[20,10],[0,10],[0,0]]],
    layers: ["F.Cu", "In1.Cu", "B.Cu"],
    layerDefinitions: ["F.Cu", "In1.Cu", "B.Cu", "F.Mask", "B.Mask", "F.Paste", "B.Paste", "F.SilkS", "B.SilkS", "F.Fab", "B.Fab", "Edge.Cuts"]
      .map((name, id) => ({ id, name, kind: name.endsWith(".Cu") ? "signal" : "user" })),
    stackup: [], nets: { 1: "VCC" }, components: [],
    tracks: [
      { id: "front-track", start: [1,1], end: [6,1], width: .25, layer: "F.Cu", net: "VCC" },
      { id: "inner-track", start: [1,2], end: [6,2], width: .2, layer: "In1.Cu", net: "VCC" },
      { id: "back-track", start: [1,3], end: [6,3], width: .3, layer: "B.Cu", net: "VCC" },
    ],
    vias: [{ id: "via-1", at: [5,5], size: .8, drill: .4, layers: ["F.Cu", "B.Cu"], net: "VCC" }],
    pads: [{ id: "pad-1", name: "1", at: [8,5], width: 2, height: 1, rotation: 0, shape: "rect", drill: 0,
      layers: ["*.Cu", "*.Mask", "F.Paste", "B.Paste"], layer: "F.Cu", net: "VCC", ref: "U1" }],
    zones: [{ id: "zone-1", points: [[10,2],[14,2],[14,5],[10,5]], layer: "F.Cu", net: "VCC" }],
    drawings: [
      { id: "silk-1", type: "line", points: [[2,8],[7,8]], layer: "F.SilkS", width: .15 },
      { id: "back-silk-1", type: "line", points: [[8,8],[13,8]], layer: "B.SilkS", width: .15 },
      { id: "fab-1", type: "line", points: [[2,9],[7,9]], layer: "F.Fab", width: .1 },
      { id: "back-fab-1", type: "line", points: [[8,9],[13,9]], layer: "B.Fab", width: .1 },
      { id: "edge-1", type: "rect", points: [[0,0],[20,0],[20,10],[0,10],[0,0]], layer: "Edge.Cuts", width: .05 },
    ],
  };
  const props = {
    board, visibleLayers: {}, layerOpacity: {}, showVias: true, selectedId: null,
    cameraCommand: "", selectionFilter: "all", onSelect() {}, showAxes: false,
  };
  const render = overrides => renderToStaticMarkup(React.createElement(LayoutViewport, { ...props, ...overrides }));
  const allLayers = render({});
  const independentlyToggleableLayers = ["F.Cu", "In1.Cu", "B.Cu", "F.Mask", "B.Mask", "F.Paste", "B.Paste", "F.SilkS", "B.SilkS", "F.Fab", "B.Fab"];
  for (const layer of [...independentlyToggleableLayers, "Edge.Cuts"]) {
    assert.ok(allLayers.includes(`aria-label="${layer} native vector geometry"`), `${layer} must render through the native fallback`);
  }
  for (const hidden of independentlyToggleableLayers) {
    const markup = render({ visibleLayers: { [hidden]: false } });
    assert.ok(!markup.includes(`aria-label="${hidden} native vector geometry"`), `${hidden} toggle must hide only its native geometry`);
    for (const preserved of independentlyToggleableLayers.filter(layer => layer !== hidden)) {
      assert.ok(markup.includes(`aria-label="${preserved} native vector geometry"`), `${hidden} toggle must preserve unrelated native ${preserved} geometry`);
    }
  }
  for (const transparent of independentlyToggleableLayers) {
    const markup = render({ layerOpacity: { [transparent]: 0 } });
    assert.match(markup, new RegExp(`opacity="0"[^>]*aria-label="${transparent} native vector geometry"`), `${transparent} zero opacity must apply only to its native group`);
    for (const preserved of independentlyToggleableLayers.filter(layer => layer !== transparent)) {
      assert.doesNotMatch(markup, new RegExp(`opacity="0"[^>]*aria-label="${preserved} native vector geometry"`), `${transparent} zero opacity must preserve unrelated native ${preserved} geometry`);
    }
  }
  assert.match(allLayers, /M4\.6,5a0\.4,0\.4/, "visible vias must contribute their annulus geometry");
  assert.doesNotMatch(render({ showVias: false }), /M4\.6,5a0\.4,0\.4/, "the via toggle must remove native via geometry");
  const hiddenTechnical = render({ visibleLayers: { "F.SilkS": false, "F.Fab": false, "F.Mask": false } });
  for (const layer of ["F.SilkS", "F.Fab", "F.Mask"]) {
    assert.ok(!hiddenTechnical.includes(`aria-label="${layer} native vector geometry"`), `${layer} visibility must suppress actual rendered geometry`);
  }
  assert.ok(hiddenTechnical.includes('aria-label="F.Paste native vector geometry"'), "independently visible paste geometry must remain rendered");
  const plottedUrls = Object.fromEntries(independentlyToggleableLayers.map(layer => [layer, `/plots/${layer}.svg`]));
  const plottedBoard = { ...board, layoutLayerUrls: plottedUrls };
  const plottedAll = render({ board: plottedBoard });
  for (const layer of independentlyToggleableLayers) assert.ok(plottedAll.includes(`href="/plots/${layer}.svg"`), `${layer} supplied plot must render`);
  for (const hidden of independentlyToggleableLayers) {
    const markup = render({ board: plottedBoard, visibleLayers: { [hidden]: false } });
    assert.ok(!markup.includes(`href="/plots/${hidden}.svg"`), `${hidden} toggle must hide only its supplied plot`);
    for (const preserved of independentlyToggleableLayers.filter(layer => layer !== hidden)) {
      assert.ok(markup.includes(`href="/plots/${preserved}.svg"`), `${hidden} toggle must preserve unrelated supplied ${preserved} plot`);
    }
  }
  for (const transparent of independentlyToggleableLayers) {
    const markup = render({ board: plottedBoard, layerOpacity: { [transparent]: 0 } });
    const imageTags = markup.match(/<image\b[^>]*>/g) ?? [];
    const target = imageTags.find(tag => tag.includes(`href="/plots/${transparent}.svg"`));
    assert.ok(target?.includes('opacity="0"'), `${transparent} zero opacity must apply to its supplied plot`);
    for (const preserved of independentlyToggleableLayers.filter(layer => layer !== transparent)) {
      const tag = imageTags.find(candidate => candidate.includes(`href="/plots/${preserved}.svg"`));
      assert.ok(tag && !tag.includes('opacity="0"'), `${transparent} zero opacity must preserve unrelated supplied ${preserved} plot`);
    }
  }
  assert.doesNotMatch(allLayers, /data-net-label="(?:trace|zone)"/, "net labels are optional");
  assert.match(allLayers, /data-net-label="pad"[^>]*><title>U1\.1: VCC<\/title>1<\/text>/, "pad numbers remain visible with net names off");
  assert.match(render({ showNetNames: true }), /data-net-label="trace"/, "net labels render on tracks");
  assert.match(render({ showNetNames: true }), /data-net-label="zone"/, "net labels render on zones");
  const allOff = Object.fromEntries(board.layerDefinitions.map(layer => [layer.name, false]));
  assert.doesNotMatch(render({ visibleLayers: allOff, showNetNames: true }), /data-net-label=/, "hidden layers cannot leave labels behind");
  const genericNames = { "F.Cu": "top", "In1.Cu": "signal1", "B.Cu": "bottom" };
  const rename = name => genericNames[name] ?? name;
  const genericBoard = { ...board, layers: board.layers.map(rename),
    layerDefinitions: board.layerDefinitions.map(l => ({ ...l, name: rename(l.name) })),
    tracks: board.tracks.map(t => ({ ...t, layer: rename(t.layer) })),
    pads: board.pads.map(p => ({ ...p, layers: p.layers.map(rename), layer: rename(p.layer) })),
    zones: board.zones.map(z => ({ ...z, layer: rename(z.layer) })),
    vias: board.vias.map(v => ({ ...v, layers: v.layers.map(rename) })),
  };
  const generic = render({ board: genericBoard });
  assert.match(generic, /aria-label="signal1 native vector geometry"/);
  assert.match(generic, /M4\.6,5a0\.4,0\.4/, "arbitrary ODB conductor names retain vias");
  const viasOnly = render({ visibleLayers: allOff });
  assert.match(viasOnly, /aria-label="Vias only"/, 'show-only-vias must remain visible when every layer is off');
  assert.doesNotMatch(viasOnly, /aria-label="F.Cu native vector geometry"/);
  assert.doesNotMatch(render({ visibleLayers: allOff, showVias: false }), /aria-label="Vias only"/);
  const innerOnly = render({ visibleLayers: { ...allOff, 'In1.Cu': true } });
  assert.match(innerOnly, /aria-label="In1.Cu native vector geometry"/);
  assert.match(innerOnly, /opacity="0\.9"[^>]*aria-label="In1.Cu native vector geometry"/, "isolated copper must remain legible without the multi-layer opacity reduction");
  assert.doesNotMatch(innerOnly, /aria-label="F.Cu native vector geometry"/);
  assert.doesNotMatch(innerOnly, /aria-label="B.Cu native vector geometry"/);
  const hiddenSelectedNet = render({ visibleLayers: allOff, showVias: false, selectedNet: "VCC" });
  assert.doesNotMatch(hiddenSelectedNet, /stroke="#55e5d5"|fill="#55e5d5"/, "a selected net must not resurrect hidden copper");
  const hiddenPreviewNet = render({ visibleLayers: allOff, showVias: false, hoverPreview: { kind: "net", net: "VCC" } });
  assert.doesNotMatch(hiddenPreviewNet, /stroke="#ff38c7"|fill="#ff38c7"/, "net hover must not resurrect hidden copper");
  for (const filename of process.argv.slice(2)) {
    const normalized = filename.endsWith(".json");
    emit(normalized ? "normalizedBoard" : "boardParser");
    const parser = createRequire(import.meta.url)(join(renderDirectory, `${normalized ? "normalizedBoard" : "boardParser"}.cjs`));
    const realBoard = (normalized ? parser.parseNormalizedBoard : parser.parseKicadBoard)(readFileSync(filename, "utf8"));
    const visibleLayers = Object.fromEntries(realBoard.layerDefinitions.map(l => [l.name, realBoard.layers.includes(l.name)]));
    const realRender = render({ board: realBoard, visibleLayers, showNetNames: true });
    assert.doesNotMatch(realRender, /(?:NaN|Infinity)/, "real import must render finite geometry");
    for (const layer of realBoard.layers) assert.ok(realRender.includes(`aria-label="${layer} native vector geometry"`), `${layer} must remain drawable`);
    assert.match(realRender, /data-net-label=/, "real board must expose readable net labels");
    console.log(JSON.stringify({file:filename,renderedBytes:realRender.length,copperLayers:realBoard.layers.length,labels:(realRender.match(/data-net-label=/g) ?? []).length}));
  }
} finally {
  rmSync(renderDirectory, { recursive: true, force: true });
}

console.log("viewport scene policy: all assertions passed");
