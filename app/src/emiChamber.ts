import * as THREE from "three";

export type EmiChamberSetup = {
  distance_m: number;
  table_height_m: number;
  antenna_height_m: number;
  azimuth_deg: number;
  orientation: "flat" | "upright" | "side";
  polarization: "horizontal" | "vertical";
  floor: "absorber" | "ground_plane";
  cutaway: boolean;
};

export type EmiCameraView = "isometric" | "top" | "bottom";

/** Camera positions use Z-up to match the physical chamber coordinate system. */
export function emiCameraPose(target: THREE.Vector3, span: number, view: EmiCameraView) {
  const distance = Math.max(span, .01);
  // OrbitControls caches the camera's up-axis when it is constructed. Keep that
  // axis Z-up for every preset; swapping to Y-up for the pole views makes the
  // next drag use a different basis and reverses/rolls the chamber unexpectedly.
  // A slight Y offset avoids the look-at singularity while remaining visually
  // indistinguishable from an orthogonal top or bottom view.
  if (view === "top") return { position: target.clone().add(new THREE.Vector3(0, -.025, 1).normalize().multiplyScalar(distance)), up: new THREE.Vector3(0, 0, 1) };
  if (view === "bottom") return { position: target.clone().add(new THREE.Vector3(0, .025, -1).normalize().multiplyScalar(distance)), up: new THREE.Vector3(0, 0, 1) };
  return { position: target.clone().add(new THREE.Vector3(-distance * .65, -distance, distance * .65)), up: new THREE.Vector3(0, 0, 1) };
}

/** Commands in the board coordinate system (for example orbit-target) deliberately do not map into the chamber. */
export function emiCameraCommandView(command: string): EmiCameraView | null {
  if (command.startsWith("view-top")) return "top";
  if (command.startsWith("view-bottom")) return "bottom";
  if (command.startsWith("view-iso")) return "isometric";
  return null;
}

export const defaultEmiChamber = (): EmiChamberSetup => ({
  distance_m: 3, table_height_m: 0.8, antenna_height_m: 1.5,
  azimuth_deg: 0, orientation: "flat", polarization: "horizontal", floor: "absorber", cutaway: true,
});

export function normalizeEmiChamber(raw: unknown): EmiChamberSetup {
  const fallback = defaultEmiChamber();
  const value = (raw && typeof raw === "object" ? raw : {}) as Partial<EmiChamberSetup>;
  const bounded = (key: keyof EmiChamberSetup, min: number, max: number) => {
    const v = value[key];
    return typeof v === "number" && Number.isFinite(v) ? Math.max(min, Math.min(max, v)) : fallback[key] as number;
  };
  return {
    distance_m: bounded("distance_m", 1, 10), table_height_m: bounded("table_height_m", 0.5, 1.5),
    antenna_height_m: bounded("antenna_height_m", 1, 4), azimuth_deg: bounded("azimuth_deg", 0, 360),
    orientation: value.orientation === "upright" || value.orientation === "side" ? value.orientation : "flat",
    polarization: value.polarization === "vertical" ? "vertical" : "horizontal",
    floor: value.floor === "ground_plane" ? "ground_plane" : "absorber",
    cutaway: typeof value.cutaway === "boolean" ? value.cutaway : true,
  };
}

/** A rigid transform of the whole DUT. Never rescale boards to fit a fixture. */
export function placeEmiDut(dut: THREE.Group, setup: EmiChamberSetup) {
  dut.position.set(0, 0, 0);
  dut.rotation.set(setup.orientation === "upright" ? Math.PI / 2 : 0,
    setup.orientation === "side" ? Math.PI / 2 : 0, THREE.MathUtils.degToRad(setup.azimuth_deg), "ZYX");
  dut.updateMatrixWorld(true);
  const bounds = new THREE.Box3().setFromObject(dut);
  if (bounds.isEmpty()) return null;
  const center = bounds.getCenter(new THREE.Vector3());
  dut.position.set(-center.x, -center.y, setup.table_height_m - bounds.min.z);
  dut.updateMatrixWorld(true);
  return new THREE.Box3().setFromObject(dut);
}

/** Disposes owned snapshot geometry/materials; source model textures remain owned by the board viewport. */
export function disposeEmiGeometry(root: THREE.Object3D) {
  root.traverse(object => {
    if (object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Points) {
      object.geometry.dispose();
      (Array.isArray(object.material) ? object.material : [object.material]).forEach(material => material.dispose());
    }
  });
}

/** Clone visible scene content with independent GPU buffers and materials. Source transforms stay untouched. */
export function snapshotEmiDut(groups: THREE.Object3D[], unitsPerMm: number): THREE.Group {
  const snapshot = new THREE.Group();
  const cloneVisible = (object: THREE.Object3D): THREE.Object3D | null => {
    if (!object.visible) return null;
    const clone = object.clone(false);
    if (clone instanceof THREE.Mesh || clone instanceof THREE.Line || clone instanceof THREE.Points) {
      clone.geometry = clone.geometry.clone();
      const copyMaterial = (material: THREE.Material) => {
        const next = material.clone();
        next.clippingPlanes = null;
        return next;
      };
      clone.material = Array.isArray(clone.material) ? clone.material.map(copyMaterial) : copyMaterial(clone.material);
    }
    object.children.forEach(child => { const copy = cloneVisible(child); if (copy) clone.add(copy); });
    return clone;
  };
  groups.forEach(group => { const copy = cloneVisible(group); if (copy) snapshot.add(copy); });
  snapshot.scale.setScalar(1 / (Math.max(unitsPerMm, 1e-9) * 1000));
  return snapshot;
}

export function buildEmiChamber(setup: EmiChamberSetup, dutSize = new THREE.Vector3(.2, .15, .1)) {
  const root = new THREE.Group();
  root.name = "anechoic-chamber";
  const tableWidth = Math.max(1.2, dutSize.x + .2), tableDepth = Math.max(.8, dutSize.y + .2);
  const antennaX = setup.distance_m + dutSize.x / 2;
  const minX = -tableWidth / 2 - 1.2, maxX = antennaX + 1.8;
  const halfWidth = Math.max(2.5, tableDepth / 2 + 1.2), height = Math.max(4.8, setup.table_height_m + dutSize.z + 1);
  const box = (name: string, size: number[], position: number[], color: number, metalness = 0) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size as [number, number, number]), new THREE.MeshStandardMaterial({ color, roughness: .72, metalness }));
    mesh.name = name; mesh.position.set(...position as [number, number, number]); root.add(mesh); return mesh;
  };
  box("shielded floor", [maxX - minX, halfWidth * 2, .08], [(minX + maxX) / 2, 0, -.04], 0x354756, .5);
  box("rear shield", [maxX - minX, .08, height], [(minX + maxX) / 2, halfWidth, height / 2], 0x233340);
  box("end shield", [.08, halfWidth * 2, height], [maxX, 0, height / 2], 0x233340);
  const hidden = new THREE.Group(); hidden.name = "cutaway walls and ceiling"; root.add(hidden); hidden.visible = !setup.cutaway;
  [box("front shield", [maxX - minX, .08, height], [(minX + maxX) / 2, -halfWidth, height / 2], 0x233340),
    box("entry shield", [.08, halfWidth * 2, height], [minX, 0, height / 2], 0x233340),
    box("ceiling shield", [maxX - minX, halfWidth * 2, .08], [(minX + maxX) / 2, 0, height], 0x233340)].forEach(mesh => hidden.add(mesh));
  // Instancing keeps thousands of absorber pyramids in a handful of draw calls.
  const absorbers = (name: string, points: THREE.Vector3[], direction: THREE.Vector3, parent = root) => {
    const geometry = new THREE.ConeGeometry(.22, .38, 4); geometry.rotateY(Math.PI / 4);
    const mesh = new THREE.InstancedMesh(geometry, new THREE.MeshStandardMaterial({ color: 0x254c70, roughness: .94 }), points.length);
    mesh.name = name;
    const quaternion = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction);
    points.forEach((point, index) => mesh.setMatrixAt(index, new THREE.Matrix4().compose(point, quaternion, new THREE.Vector3(1, 1, 1))));
    mesh.instanceMatrix.needsUpdate = true; parent.add(mesh);
  };
  const rear: THREE.Vector3[] = [], end: THREE.Vector3[] = [], front: THREE.Vector3[] = [], entry: THREE.Vector3[] = [], ceiling: THREE.Vector3[] = [], floor: THREE.Vector3[] = [];
  for (let x = minX + .3; x < maxX - .2; x += .34) {
    for (let z = .3; z < height - .2; z += .34) { rear.push(new THREE.Vector3(x, halfWidth - .19, z)); front.push(new THREE.Vector3(x, -halfWidth + .19, z)); }
    for (let y = -halfWidth + .3; y < halfWidth - .2; y += .34) {
      ceiling.push(new THREE.Vector3(x, y, height - .19));
      if (!(Math.abs(x) < tableWidth / 2 + .25 && Math.abs(y) < tableDepth / 2 + .25) && !(Math.abs(x - antennaX) < .7 && Math.abs(y) < .7) && Math.abs(y) > .35) floor.push(new THREE.Vector3(x, y, .19));
    }
  }
  for (let y = -halfWidth + .3; y < halfWidth - .2; y += .34) for (let z = .3; z < height - .2; z += .34) { end.push(new THREE.Vector3(maxX - .19, y, z)); entry.push(new THREE.Vector3(minX + .19, y, z)); }
  absorbers("rear absorbers", rear, new THREE.Vector3(0, -1, 0)); absorbers("end absorbers", end, new THREE.Vector3(-1, 0, 0));
  absorbers("front absorbers", front, new THREE.Vector3(0, 1, 0), hidden); absorbers("entry absorbers", entry, new THREE.Vector3(1, 0, 0), hidden); absorbers("ceiling absorbers", ceiling, new THREE.Vector3(0, 0, -1), hidden);
  if (setup.floor === "absorber") absorbers("removable floor absorbers", floor, new THREE.Vector3(0, 0, 1));
  const turntable = new THREE.Mesh(new THREE.CylinderGeometry(Math.hypot(tableWidth, tableDepth) / 2 + .1, Math.hypot(tableWidth, tableDepth) / 2 + .1, .05, 96), new THREE.MeshStandardMaterial({ color: 0x687984, metalness: .4, roughness: .5 }));
  turntable.rotation.x = Math.PI / 2; turntable.position.z = .025; turntable.name = "turntable"; root.add(turntable);
  box("nonconductive test table", [tableWidth, tableDepth, .045], [0, 0, setup.table_height_m - .0225], 0xd3b98a);
  for (const x of [-1, 1]) for (const y of [-1, 1]) box("table leg", [.055, .055, setup.table_height_m - .095], [x * (tableWidth / 2 - .08), y * (tableDepth / 2 - .08), (setup.table_height_m + .005) / 2], 0xb39369);
  box("antenna mast", [.065, .065, 4.3], [antennaX + .35, 0, 2.15], 0xd4dce2, .5);
  box("mast base", [.7, .65, .09], [antennaX + .35, 0, .045], 0x677987, .5);
  const antenna = new THREE.Group(); antenna.name = "log periodic receive antenna"; antenna.position.set(antennaX, 0, setup.antenna_height_m); root.add(antenna);
  const boom = box("antenna boom", [1.1, .025, .025], [0, 0, 0], 0xd9e3e8, .7); antenna.add(boom);
  for (let i = 0; i < 11; i++) { const element = box("antenna element", [.012, .15 + i * .065, .012], [-.5 + i * .09, 0, 0], 0xc7d7e4, .7); antenna.add(element); }
  antenna.rotation.x = setup.polarization === "vertical" ? Math.PI / 2 : 0;
  const line = (name: string, points: THREE.Vector3[], color: number, dashed = false) => {
    const mesh = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), dashed ? new THREE.LineDashedMaterial({ color, dashSize: .08, gapSize: .05 }) : new THREE.LineBasicMaterial({ color }));
    mesh.name = name; mesh.computeLineDistances(); root.add(mesh);
  };
  line("coax to receiver", [new THREE.Vector3(antennaX + .4, 0, setup.antenna_height_m), new THREE.Vector3(antennaX + .4, 0, .12), new THREE.Vector3(antennaX + .9, -.9, .12), new THREE.Vector3(antennaX + .9, -.9, .7)], 0xe2b958);
  box("EMI receiver rack", [.45, .45, .85], [antennaX + .9, -.9, .425], 0x192633, .4);
  for (let i = 0; i < 3; i++) box("receiver display", [.3, .008, .13], [antennaX + .9, -1.13, .22 + i * .22], 0x53adb5);
  line("measurement distance", [new THREE.Vector3(dutSize.x / 2, -.65, .45), new THREE.Vector3(antennaX, -.65, .45)], 0xf1bf69, true);
  return { root, length: maxX - minX, center: new THREE.Vector3((minX + maxX) / 2, 0, 1.3), tableWidth, tableDepth };
}
