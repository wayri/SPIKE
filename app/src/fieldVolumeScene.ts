// SPDX-License-Identifier: Apache-2.0
// Presentation adapter only: converts admitted field traces into BoardViewport resources.
import * as THREE from "three";
import { fieldViewPlot, type FieldPoint, type FieldViewOptions, type FieldVolumeData } from "./fieldVolumeModel";
import { traceFieldGrid } from "./fieldStreamTracing";
import { thermalFieldColor } from "./thermalResultFields";

type Trace = Record<string, any>;
export type FieldVolumeSceneTransform = { centerX: number; centerY: number; scale: number };

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const valuesOf = (value: unknown): unknown[] => Array.isArray(value) ? value : ArrayBuffer.isView(value) ? Array.from(value as unknown as ArrayLike<unknown>) : [];
const mm = (value: number, unit: FieldVolumeData["lengthUnit"]) => value * (unit === "m" ? 1000 : 1);
function scenePoint(x: number, y: number, z: number, unit: FieldVolumeData["lengthUnit"], transform: FieldVolumeSceneTransform): FieldPoint | null {
  const point: FieldPoint = [(mm(x, unit) - transform.centerX) * transform.scale,
    (transform.centerY - mm(y, unit)) * transform.scale, mm(z, unit) * transform.scale];
  return point.every(value => Number.isFinite(value) && Math.abs(value) <= 3.402823466e38) ? point : null;
}

function traceRange(trace: Trace, fallback: [number, number]): [number, number] {
  const owner = trace.type === "scatter3d" ? trace.marker ?? trace.line ?? {} : trace;
  const low = finite(owner.cmin) ? owner.cmin : fallback[0];
  const high = finite(owner.cmax) ? owner.cmax : fallback[1];
  return [low, high > low ? high : low + 1];
}

function addColor(target: number[], value: unknown, range: [number, number], constant?: THREE.Color) {
  if (constant) { target.push(constant.r, constant.g, constant.b); return; }
  const [r, g, b] = thermalFieldColor(finite(value) ? value : range[0], range[0], range[1]);
  target.push(r, g, b);
}

function meshObject(trace: Trace, unit: FieldVolumeData["lengthUnit"], fallback: [number, number], transform: FieldVolumeSceneTransform) {
  const positions: number[] = [], colors: number[] = [];
  const range = traceRange(trace, fallback), constant = typeof trace.color === "string" || typeof trace.color === "number" ? new THREE.Color(trace.color) : undefined;
  const intensity = valuesOf(trace.intensity);
  // mesh3d defaults to vertex intensity when the mode is omitted. Explicit
  // voxel cell intensity remains face-colored.
  const vertexIntensity = trace.intensitymode === "vertex" || (trace.intensitymode == null && intensity.length === (trace.x?.length ?? -1));
  const faces = Math.min(trace.i?.length ?? 0, trace.j?.length ?? 0, trace.k?.length ?? 0);
  for (let face = 0; face < faces; face++) {
    const indices = [trace.i[face], trace.j[face], trace.k[face]];
    const points = indices.map(index => Number.isInteger(index) && finite(trace.x?.[index]) && finite(trace.y?.[index]) && finite(trace.z?.[index])
      ? scenePoint(trace.x[index], trace.y[index], trace.z[index], unit, transform) : null);
    if (points.some(point => !point)) continue;
    points.forEach((point, corner) => { positions.push(...point!); addColor(colors,
      vertexIntensity ? intensity[indices[corner]] : intensity[face], range, constant); });
  }
  if (!positions.length) return null;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  return new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide,
    transparent: true, opacity: finite(trace.opacity) ? Math.max(0, Math.min(1, trace.opacity)) : 1, depthWrite: false, toneMapped: false }));
}

function pointObject(trace: Trace, unit: FieldVolumeData["lengthUnit"], fallback: [number, number], transform: FieldVolumeSceneTransform) {
  const positions: number[] = [], colors: number[] = [], marker = trace.marker ?? {}, range = traceRange(trace, fallback);
  const values = valuesOf(marker.color);
  const constant = typeof marker.color === "string" || typeof marker.color === "number" ? new THREE.Color(marker.color) : undefined;
  const count = Math.min(trace.x?.length ?? 0, trace.y?.length ?? 0, trace.z?.length ?? 0);
  for (let index = 0; index < count; index++) if (finite(trace.x[index]) && finite(trace.y[index]) && finite(trace.z[index])) {
    const point = scenePoint(trace.x[index], trace.y[index], trace.z[index], unit, transform); if (!point) continue;
    positions.push(...point); addColor(colors, values[index], range, constant);
  }
  if (!positions.length) return null;
  const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3)); geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  return new THREE.Points(geometry, new THREE.PointsMaterial({ size: Math.max(1, Number(marker.size) || 4), sizeAttenuation: false,
    vertexColors: true, transparent: true, opacity: finite(marker.opacity) ? Math.max(0, Math.min(1, marker.opacity)) : 1, depthWrite: false, toneMapped: false }));
}

function lineObjects(trace: Trace, unit: FieldVolumeData["lengthUnit"], fallback: [number, number], transform: FieldVolumeSceneTransform) {
  const result: THREE.Line[] = [], line = trace.line ?? {}, range = traceRange(trace, fallback);
  const values = valuesOf(line.color);
  const constant = typeof line.color === "string" || typeof line.color === "number" ? new THREE.Color(line.color) : undefined;
  let positions: number[] = [], colors: number[] = [];
  const flush = () => {
    if (positions.length >= 6) {
      const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3)); geometry.computeBoundingBox(); geometry.computeBoundingSphere();
      result.push(new THREE.Line(geometry, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true,
        opacity: finite(trace.opacity) ? Math.max(0, Math.min(1, trace.opacity)) : 1, depthWrite: false, toneMapped: false })));
    }
    positions = []; colors = [];
  };
  const count = Math.min(trace.x?.length ?? 0, trace.y?.length ?? 0, trace.z?.length ?? 0);
  for (let index = 0; index < count; index++) {
    if (!finite(trace.x[index]) || !finite(trace.y[index]) || !finite(trace.z[index])) { flush(); continue; }
    const point = scenePoint(trace.x[index], trace.y[index], trace.z[index], unit, transform);
    if (!point) { flush(); continue; }
    positions.push(...point); addColor(colors, values[index], range, constant);
  }
  flush(); return result;
}

function presentation(data: FieldVolumeData, options: FieldViewOptions) {
  const frame = data.frames[Math.max(0, Math.min(data.frames.length - 1, Math.trunc(options.frame)))];
  if (options.mode !== "streamtubes" || frame.streamlines?.length) return fieldViewPlot(data, options);
  const paths = traceFieldGrid(data, options);
  if (!paths.length) {
    const fallback = fieldViewPlot(data, options);
    const speeds = data.frames.flatMap(saved => saved.vectors?.map(vector => Math.hypot(...vector)) ?? []);
    const minimum = speeds.length ? speeds.reduce((low, value) => Math.min(low, value), Infinity) : 0;
    const maximum = speeds.length ? speeds.reduce((high, value) => Math.max(high, value), -Infinity) : 0;
    return { ...fallback, traces: [], streamCount: 0, minimum, maximum, unit: "m/s",
      streamNote: "No renderer-generated curves: this frame needs a supported, nondegenerate complete Cartesian fluid grid with velocity vectors." };
  }
  const selectedFrame = Math.max(0, Math.min(data.frames.length - 1, Math.trunc(options.frame)));
  const synthetic: FieldVolumeData = { contract: data.contract, id: `${data.id}:rendered-streams`, label: data.label, lengthUnit: data.lengthUnit,
    geometryNote: data.geometryNote, ...(data.geometry ? { geometry: data.geometry } : {}),
    cells: { centers: data.cells.centers.map(point => [...point] as FieldPoint) }, quantities: [{ id: "speed_m_s", label: "Speed", unit: "m/s" }],
    frames: data.frames.map((saved, index) => ({ timeS: saved.timeS,
      scalars: { speed_m_s: saved.vectors?.map(vector => Math.hypot(...vector)) ?? data.cells.centers.map(() => 0) },
      ...(index === selectedFrame ? { streamlines: paths } : {}) })) };
  const plot = fieldViewPlot(synthetic, { ...options, frame: selectedFrame, quantity: "speed_m_s", celsius: false, arrows: false });
  return { ...plot, streamNote: `Renderer-generated frozen-frame curves from the center seed plane; color is speed. ${plot.streamNote}` };
}

/** Build bounded, unlit field resources in the BoardViewport world frame (millimetres, inverted Y). */
export function buildFieldVolumeScene(data: FieldVolumeData, options: FieldViewOptions,
  transform: FieldVolumeSceneTransform = { centerX: 0, centerY: 0, scale: 1 }): THREE.Group {
  const plot = presentation(data, options), group = new THREE.Group();
  group.name = "field-volume-overlay"; group.userData.presentationOnly = true; group.userData.fieldVolumeOverlay = true;
  const generated = options.mode === "streamtubes" && !data.frames[Math.max(0, Math.min(data.frames.length - 1, Math.trunc(options.frame)))]?.streamlines?.length;
  group.userData.sourceLengthUnit = data.lengthUnit;
  group.userData.scalarLabel = generated ? "Speed" : data.quantities.find(quantity => quantity.id === options.quantity)?.label ?? options.quantity;
  group.userData.scalarUnit = plot.unit; group.userData.scalarRange = [plot.minimum, plot.maximum];
  group.userData.streamNote = plot.streamNote; group.userData.error = "";
  if (![transform.centerX, transform.centerY, transform.scale].every(Number.isFinite) || transform.scale <= 0) {
    group.userData.error = "Field volume needs a finite positive BoardViewport transform.";
    group.userData.fieldVolumeError = group.userData.error; return group;
  }
  const fallback: [number, number] = [plot.minimum, plot.maximum > plot.minimum ? plot.maximum : plot.minimum + 1];
  for (const trace of plot.traces as Trace[]) {
    if (trace.type === "mesh3d") { const object = meshObject(trace, data.lengthUnit, fallback, transform); if (object) group.add(object); }
    else if (trace.type === "scatter3d" && String(trace.mode).includes("markers")) { const object = pointObject(trace, data.lengthUnit, fallback, transform); if (object) group.add(object); }
    else if (trace.type === "scatter3d" && String(trace.mode).includes("lines")) lineObjects(trace, data.lengthUnit, fallback, transform).forEach(object => group.add(object));
  }
  if (!group.children.length && plot.traces.length) {
    group.userData.error = "Field coordinates cannot be represented by GPU float32 buffers.";
    group.userData.fieldVolumeError = group.userData.error;
  }
  return group;
}
