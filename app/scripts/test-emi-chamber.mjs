import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createRequire } from "node:module";
import ts from "typescript";
import * as THREE from "three";

const require = createRequire(import.meta.url);
function load(name) {
  const source = fs.readFileSync(new URL(`../src/${name}.ts`, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, { module, exports: module.exports, require: id => id === "three" ? THREE : require(id) });
  return module.exports;
}
const { defaultEmiChamber, normalizeEmiChamber, snapshotEmiDut, placeEmiDut, buildEmiChamber, disposeEmiGeometry, emiCameraPose, emiCameraCommandView } = load("emiChamber");
const workspaceSource = fs.readFileSync(new URL("../src/EmiChamberWorkspace.tsx", import.meta.url), "utf8");
const { validEmiFarField, emiSpectrum, fieldDbUvM } = load("emiFieldData");
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-8, `${a} != ${b}`);
const setup = defaultEmiChamber();
const cameraTarget = new THREE.Vector3(2, -1, .8);
const iso = emiCameraPose(cameraTarget, 4, "isometric");
[-.6, -5, 3.4].forEach((value, index) => close(iso.position.toArray()[index], value)); assert.deepEqual(iso.up.toArray(), [0, 0, 1]);
const top = emiCameraPose(cameraTarget, 4, "top");
assert.ok(top.position.y < cameraTarget.y); close(top.position.distanceTo(cameraTarget), 4); assert.ok(top.position.z > cameraTarget.z); assert.deepEqual(top.up.toArray(), [0, 0, 1]);
const bottom = emiCameraPose(cameraTarget, 4, "bottom");
assert.ok(bottom.position.y > cameraTarget.y); close(bottom.position.distanceTo(cameraTarget), 4); assert.ok(bottom.position.z < cameraTarget.z); assert.deepEqual(bottom.up.toArray(), [0, 0, 1]);
// Presets must not mutate the up-axis cached by OrbitControls. Switching from a
// pole view back to orbit is the regression that previously mirrored dragging.
for (const pose of [iso, top, bottom]) assert.deepEqual(pose.up.toArray(), [0, 0, 1]);
assert.equal(emiCameraCommandView("view-top-123"), "top");
assert.equal(emiCameraCommandView("view-bottom-123"), "bottom");
assert.equal(emiCameraCommandView("view-iso-123"), "isometric");
assert.equal(emiCameraCommandView("orbit-target:12,4,0"), null);
assert.equal(emiCameraCommandView("view-front-123"), null);
for (const label of ["Focus DUT", "Top", "Bottom", "Isometric", "Orbit", "Pan"]) assert.match(workspaceSource, new RegExp(`>${label}</button>`));
assert.match(workspaceSource, /const hasDut = Boolean\(source && hasBoard\)/);
assert.match(workspaceSource, /disabled=\{!hasDut\}/);
assert.match(workspaceSource, /controls\.mouseButtons\.LEFT = navigation === "pan" \? THREE\.MOUSE\.PAN : THREE\.MOUSE\.ROTATE/);
assert.match(workspaceSource, /cameraCommand = ""/);
assert.match(workspaceSource, /navigationMode\?: "orbit" \| "pan"/);
assert.match(workspaceSource, /const navigation = navigationMode \?\? localNavigation/);
assert.match(workspaceSource, /cameraCommand\.startsWith\("fit"\)/);
assert.match(workspaceSource, /cameraCommand\.startsWith\("pan-"\)/);
assert.match(workspaceSource, /cameraCommand\.startsWith\("zoom-in"\)/);
assert.equal(normalizeEmiChamber({ distance_m: Infinity, orientation: "invalid" }).distance_m, 3);
assert.equal(normalizeEmiChamber({ table_height_m: -1 }).table_height_m, .5);

// Off-origin multi-board + enclosure: preserve all internal transforms and real scale.
const assembly = new THREE.Group(); assembly.position.set(320, -210, 14);
const board = new THREE.Mesh(new THREE.BoxGeometry(100, 80, 1.6), new THREE.MeshStandardMaterial());
const second = board.clone(); second.geometry = board.geometry.clone(); second.position.set(35, 12, 30);
const enclosure = new THREE.Mesh(new THREE.BoxGeometry(170, 140, 60), new THREE.MeshStandardMaterial()); enclosure.position.z = 20;
assembly.add(board, second, enclosure);
const before = assembly.matrix.clone();
for (const orientation of ["flat", "upright", "side"]) for (const azimuth_deg of [0, 35, 90, 270]) {
  const snapshot = snapshotEmiDut([assembly], 1);
  const dut = new THREE.Group(); dut.add(snapshot);
  const bounds = placeEmiDut(dut, { ...setup, orientation, azimuth_deg });
  close(bounds.min.z, .8); close(bounds.getCenter(new THREE.Vector3()).x, 0); close(bounds.getCenter(new THREE.Vector3()).y, 0);
  close(snapshot.scale.x, .001);
  assert.deepEqual(assembly.matrix.elements, before.elements);
  assert.notEqual(snapshot.children[0].children[0].geometry, board.geometry);
  disposeEmiGeometry(snapshot);
}
const chamber = buildEmiChamber(setup, new THREE.Vector3(2, 1, .5));
assert.ok(chamber.tableWidth >= 2.2);
const mast = chamber.root.getObjectByName("antenna mast"); close(mast.position.x - .35 - 1, setup.distance_m);
assert.equal(chamber.root.getObjectByName("cutaway walls and ceiling").visible, false);
assert.ok(chamber.root.getObjectByName("rear absorbers").isInstancedMesh);
assert.ok(chamber.root.getObjectByName("removable floor absorbers"));
disposeEmiGeometry(chamber.root);
const semi = buildEmiChamber({ ...setup, floor: "ground_plane", cutaway: false, polarization: "vertical" });
assert.equal(semi.root.getObjectByName("removable floor absorbers"), undefined);
close(semi.root.getObjectByName("log periodic receive antenna").rotation.x, Math.PI / 2);
disposeEmiGeometry(semi.root);

const field = {
  contract: "spike/openems-far-field-result/v1", frequencies_hz: [30e6, 100e6], theta_deg: [0, 180], phi_deg: [-180, 180],
  shape: [2, 2, 2], radius_m: 3, center_mm: [0, 0, 0], validation_status: "unvalidated",
  e_field_v_m: { magnitude: [1e-6, 2e-6, 4e-6, 0, 1e-5, 0, 0, 0] },
  directivity: { linear: Array(8).fill(1), maximum_linear: [1, 1] }, radiated_power: { total_w: [1e-9, 1e-8] },
};
assert.ok(validEmiFarField(field));
close(fieldDbUvM(1e-6), 0); assert.equal(fieldDbUvM(0), null);
const spectrum = emiSpectrum(field); close(spectrum[0].db, 20 * Math.log10(4)); close(spectrum[1].db, 20);
assert.equal(spectrum[0].theta, 180); assert.equal(spectrum[0].phi, -180);
for (const bad of [{ ...field, shape: [2, 2, 3] }, { ...field, radius_m: 0 }, { ...field, e_field_v_m: { magnitude: [NaN] } }, { ...field, frequencies_hz: [100e6, 30e6] }]) assert.equal(validEmiFarField(bad), false);
const chamberCss = fs.readFileSync(new URL('../src/emiChamber.css', import.meta.url), 'utf8');
const chromeCss = fs.readFileSync(new URL('../src/WorkbenchChrome.css', import.meta.url), 'utf8');
assert.match(chromeCss, /\.app-shell \.canvas-area \{[^}]*grid-template-rows:/);
assert.match(chamberCss, /\.app-shell \.canvas-area:has\(\.emi-chamber-workspace\) \{ grid-template-rows: var\(--ui-context-toolbar-height, 34px\) minmax\(0, 1fr\); \}/, 'chamber layout must outrank the chrome grid and reserve the remaining height for WebGL');
assert.match(chamberCss, /> :not\(\.board-canvas\):not\(\.result-mode-toolbar\)/, 'EM controls remain accessible in chamber mode');
assert.match(chamberCss, /> \.board-canvas \{ grid-row: 2;/, 'DUT canvas cannot occupy the short toolbar track');
const appSource = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const notificationTools = appSource.slice(appSource.indexOf('const notificationWorkspaceTools'), appSource.indexOf('return <div className={`app-shell'));
assert.ok(!notificationTools.includes('emi-viewport-bar'), 'EM tools must not be rendered inside notifications');
assert.match(appSource, /label: "EM tools", restore: \(\) => \{ setTab\("EM"\); setEmToolsMinimized\(false\); \}/, 'minimized EM controls restore from the bottom tool shelf');
assert.match(appSource, /aria-label="Minimize EM tools to bottom bar"/);
console.log("EMI chamber: rigid placement, snapshots, fields, layout reservation and bottom-bar EM tools passed");
