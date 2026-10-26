// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { build } from "esbuild";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { zoneBoundaryGeometry, applyZoneDisplayScene, restoreZoneDisplayScene, zoneSvgStyle } = await importTestTypescript("zoneDisplay");
const square = new THREE.Shape([[0, 0], [10, 0], [10, 10], [0, 10]].map(point => new THREE.Vector2(...point)));
square.holes.push(new THREE.Path([[3, 3], [3, 7], [7, 7], [7, 3]].map(point => new THREE.Vector2(...point))));
const geometry = new THREE.ShapeGeometry(square);
const coincidentBatch = mergeGeometries([geometry, geometry], false);
coincidentBatch.userData.zoneTriangleEnds = [geometry.index.count, geometry.index.count * 2];
assert.equal(zoneBoundaryGeometry(coincidentBatch).getAttribute("position").count, 32, "batched coincident polygons retain both boundaries instead of cancelling each other");
for (const triangles of [geometry, geometry.toNonIndexed()]) {
  const boundary = zoneBoundaryGeometry(triangles).getAttribute("position");
  assert.equal(boundary.count, 16, "square outer perimeter plus square hole has eight edges, no triangulation diagonals");
  for (let i = 0; i < boundary.count; i += 2) {
    const a = [boundary.getX(i), boundary.getY(i)], b = [boundary.getX(i + 1), boundary.getY(i + 1)];
    assert(a[0] === b[0] || a[1] === b[1], "every perimeter edge is axis aligned in this independent fixture");
  }
}
const root = new THREE.Group();
const material = new THREE.MeshBasicMaterial({ color: 0xba1024, opacity: .8, side: THREE.DoubleSide });
const zone = new THREE.Mesh(geometry, material);
zone.userData = { spikeSceneIdentity: "spike:copper-zone:F.Cu:zone", layer: "F.Cu" };
const sharedZone = new THREE.Mesh(geometry, material);
sharedZone.userData = { sceneKind: "copper-zone", layer: "F.Cu" }; sharedZone.position.x = 12;
const track = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ color: 0xba1024, opacity: .7 }));
track.userData = { sceneKind: "copper-track", layer: "F.Cu" };
const result = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: 0x123456, opacity: .9 }));
result.userData = { sceneKind: "result", layer: "F.Cu" };
root.add(zone, sharedZone, track, result);
const copperGraphic = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ opacity: .6 }));
copperGraphic.userData = { sceneKind: "drawing", layer: "F.Cu" };
const silkscreen = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ opacity: .9 }));
silkscreen.userData = { sceneKind: "drawing", layer: "F.SilkS" }; root.add(copperGraphic, silkscreen);
const positions = geometry.getAttribute("position").array.slice();
applyZoneDisplayScene(root, "transparent");
assert.equal(material.opacity, .8 * .18, "shared zone materials are attenuated exactly once");
assert.equal(track.material.opacity, .7, "tracks retain their opacity");
assert.equal(copperGraphic.material.opacity, .6 * .18, "filled copper graphics share zone presentation");
assert.equal(silkscreen.material.opacity, .9, "non-copper graphics retain their presentation");
assert.equal(result.material.opacity, .9, "result colors and opacity remain independent");
assert.equal(result.material.color.getHex(), 0x123456);
const boundary = zone.children[0];
assert.equal(boundary.material.opacity, .8);
restoreZoneDisplayScene(root);
applyZoneDisplayScene(root, "outline");
assert.equal(zone.children[0], boundary, "mode changes reuse the cached perimeter geometry");
assert.equal(material.colorWrite, false); assert.equal(material.depthWrite, false);
root.updateMatrixWorld(true);
const raycaster = new THREE.Raycaster(new THREE.Vector3(1, 1, 5), new THREE.Vector3(0, 0, -1));
assert(raycaster.intersectObject(zone, false).length > 0, "outline mode retains zone surface picking");
raycaster.ray.origin.set(5, 5, 5);
assert.equal(raycaster.intersectObject(zone, false).length, 0, "a hole remains empty for picking");
restoreZoneDisplayScene(root);
applyZoneDisplayScene(root, "filled");
assert.equal(material.opacity, .8); assert.equal(material.colorWrite, true);
assert.equal(boundary.visible, false);
assert.deepEqual(geometry.getAttribute("position").array, positions, "display modes never mutate source buffers");

// Mixed native copper has only layer identity, so use retained source copper.
const native = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
native.userData.importedBoardLayer = "F.Cu"; root.add(native);
restoreZoneDisplayScene(root);
track.material.userData.assemblyBaseOpacity = 1;
track.material.opacity = 0; track.material.colorWrite = false;
applyZoneDisplayScene(root, "outline", { "F.Cu": .45 }, true);
assert.equal(native.visible, false);
assert.equal(track.material.opacity, .45); assert.equal(track.material.colorWrite, true);
assert.equal(material.colorWrite, false);
restoreZoneDisplayScene(root);
applyZoneDisplayScene(root, "filled", {}, true);
assert.equal(native.visible, true); assert.equal(track.material.opacity, 0); assert.equal(track.material.colorWrite, false);
assert.deepEqual(zoneSvgStyle("outline", "red", .4), { fill: "none", fillOpacity: 0, stroke: "red", strokeOpacity: .4, strokeWidth: .12, fillRule: "evenodd" });
assert.equal(zoneSvgStyle("transparent", "red", .4).fillOpacity, .4 * .18);
assert.equal(zoneSvgStyle("filled", "red", .4).fillOpacity, .4);

const require = createRequire(import.meta.url);
async function viewport(name) {
  const bundle = await build({ entryPoints: [fileURLToPath(new URL(`../src/${name}.tsx`, import.meta.url))], bundle: true,
    write: false, format: "cjs", platform: "node", jsx: "automatic", external: ["react", "three"], loader: { ".css": "empty" } });
  const module = { exports: {} };
  new Function("require", "module", "exports", bundle.outputFiles[0].text)(require, module, module.exports);
  return module.exports.default;
}
const board = { width: 10, height: 10, bounds: { minX: 0, minY: 0, maxX: 10, maxY: 10 },
  outlineLoops: [[[0, 0], [10, 0], [10, 10], [0, 10]]], layers: ["F.Cu"], layerDefinitions: [{ name: "F.Cu", kind: "signal" }],
  nets: { "1": "GND" }, drawings: [], tracks: [{ id: "t", start: [1, 1], end: [9, 1], width: .2, layer: "F.Cu", net: "GND" }],
  zones: [{ id: "z", points: [[0, 0], [10, 0], [10, 10], [0, 10]], holes: [[[3, 3], [3, 7], [7, 7], [7, 3]]], layer: "F.Cu", net: "GND" }],
  vias: [], pads: [], components: [], stackup: [], layoutViewBox: [0, 0, 10, 10], layoutLayerUrls: { "F.Cu": "blob:mixed-native-copper" } };
const Layout = await viewport("LayoutViewport");
const layout = (mode, opacity = .5, native = true) => renderToStaticMarkup(React.createElement(Layout, { board: native ? board : { ...board, layoutLayerUrls: {} }, visibleLayers: {}, layerOpacity: { "F.Cu": opacity },
  zoneDisplay: mode, selectedId: null, selectionFilter: "all", cameraCommand: "", onSelect() {} }));
assert.match(layout("filled"), /href="blob:mixed-native-copper"/, "default presentation retains native source artwork");
const outlineSvg = layout("outline");
assert.doesNotMatch(outlineSvg, /href="blob:mixed-native-copper"/, "mixed native copper is replaced for alternate zone modes");
assert.match(outlineSvg, /fill="none" fill-opacity="0" stroke="[^"]+" stroke-opacity="0.5"/, "2D zone outline preserves layer opacity");
assert.match(layout("filled", 1, false), /fill-opacity="1" stroke="none"/, "retained filled zones are opaque at full layer opacity");
assert.match(layout("filled", .5, false), /fill-opacity="0.5" stroke="none"/, "retained filled zones preserve explicit half layer opacity");
assert.match(layout("transparent", .5, false), /fill-opacity="0.09"/, "transparent zones use .18 times explicit layer opacity");
assert.match(outlineSvg, /Z M3,3 L3,7 L7,7 L7,3 Z|Z M3,3 L3,7 L7,7 L7,3Z/, "2D outline retains the hole boundary");
assert.match(outlineSvg, /stroke-width="0.2" stroke-linecap="round"/, "tracks retain solid source-width strokes");
const AssemblyLayout = await viewport("AssemblyLayoutViewport");
const visual = { id: "a", designId: "design", name: "Board", active: true, widthMm: 10, heightMm: 10, localCenterMm: [5, 5, 0],
  transform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] };
const assemblySvg = renderToStaticMarkup(React.createElement(AssemblyLayout, { designs: { design: board }, boards: [visual, { ...visual, id: "b" }],
  harnesses: [], selectedBoardId: null, linkedNets: {}, visibleLayers: {}, layerOpacity: {}, assemblyLayerOpacity: { a: { "F.Cu": .5 } },
  zoneDisplay: "filled", assemblyZoneDisplay: { a: "outline" }, showVias: true, onBoardSelect() {}, onNetSelect() {} }));
const firstBoard = assemblySvg.split('data-board-id="a"')[1].split('data-board-id="b"')[0];
const secondBoard = assemblySvg.split('data-board-id="b"')[1];
assert.match(firstBoard, /fill="none" fill-opacity="0" stroke="[^"]+" stroke-opacity="0.5"/, "fixed occurrence overrides global zone mode and retains opacity");
assert.match(secondBoard, /fill-opacity="1" stroke="none"/, "sibling occurrence retains opaque filled zones");
console.log("zone display: boundaries/holes, cached buffers, picking, opacity, native fallback, result isolation passed");
const {normalizeZoneDisplay,normalizeAssemblyZoneDisplay}=await importTestTypescript("zoneDisplaySettings");
assert.equal(normalizeZoneDisplay(undefined),"filled");assert.equal(normalizeZoneDisplay("wireframe"),"filled");
assert.deepEqual(normalizeAssemblyZoneDisplay({A:"outline",B:"transparent",bad:["filled"],unknown:"wireframe"}),{A:"outline",B:"transparent"});
const {mergeProjectSnapshot,withoutSavedResults}=await importTestTypescript("projectSnapshotState");
const displaySnapshot={analysis:{zone_display:"filled",assembly_zone_display:{A:"outline",B:"transparent"},layer_opacity:{"F.Cu":.4},assembly_layer_opacity:{A:{"F.Cu":.7}},latest_result:{discard:true}}};
assert.deepEqual(withoutSavedResults(displaySnapshot).analysis.assembly_zone_display,displaySnapshot.analysis.assembly_zone_display);
assert.equal(mergeProjectSnapshot(displaySnapshot,{analysis:{zone_display:"transparent"}}).analysis.assembly_zone_display.A,"outline");
const appSource=(await import("node:fs")).readFileSync(new URL("../src/App.tsx",import.meta.url),"utf8");
for(const key of ["zone_display","assembly_zone_display"])assert.ok(appSource.includes(`analysis.${key}`)&&appSource.includes(`${key}:`),`${key} is saved and loaded by App`);
assert.ok(appSource.includes('setZoneDisplay(normalizeZoneDisplay(next.zoneDisplay))')&&appSource.includes('assemblyZoneDisplay: { ...assemblyZoneDisplay }'),"display undo snapshot retains mode and occurrence overrides");
console.log("Zone display defaults, malformed settings, project persistence and copy-without-results retention passed.");
