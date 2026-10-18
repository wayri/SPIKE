// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import type { ParsedBoard, ParsedPad, Point } from "./boardParser";

type Polygon = THREE.Vector2[];
type Bounds = { minX: number; minY: number; maxX: number; maxY: number };
export type ProceduralDrillReport = {
  added: number; duplicates: number;
  diagnostics: { id: string; reason: "invalid-drill" | "outline-intersection" | "overlapping-drill" }[];
};
const EPS = 1e-7;
const bounds = (points: Polygon): Bounds => points.reduce((b, p) => ({ minX: Math.min(b.minX, p.x), minY: Math.min(b.minY, p.y), maxX: Math.max(b.maxX, p.x), maxY: Math.max(b.maxY, p.y) }), { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity });
const intersectsBounds = (a: Bounds, b: Bounds) => a.minX <= b.maxX + EPS && a.maxX >= b.minX - EPS && a.minY <= b.maxY + EPS && a.maxY >= b.minY - EPS;
function cross(a: THREE.Vector2, b: THREE.Vector2, c: THREE.Vector2) { return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x); }
function onEdge(p: THREE.Vector2, a: THREE.Vector2, b: THREE.Vector2) {
  return Math.abs(cross(a, b, p)) <= EPS && p.x >= Math.min(a.x, b.x) - EPS && p.x <= Math.max(a.x, b.x) + EPS && p.y >= Math.min(a.y, b.y) - EPS && p.y <= Math.max(a.y, b.y) + EPS;
}
function inside(point: THREE.Vector2, polygon: Polygon) {
  let result = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[j], b = polygon[i];
    if (onEdge(point, a, b)) return true;
    if ((a.y > point.y) !== (b.y > point.y) && point.x < (b.x - a.x) * (point.y - a.y) / (b.y - a.y) + a.x) result = !result;
  }
  return result;
}
function boundariesMeet(a: Polygon, b: Polygon) {
  for (let i = 0; i < a.length; i++) for (let j = 0; j < b.length; j++) {
    const p = a[i], q = a[(i + 1) % a.length], r = b[j], s = b[(j + 1) % b.length];
    if (onEdge(p, r, s) || onEdge(q, r, s) || onEdge(r, p, q) || onEdge(s, p, q)
      || cross(p, q, r) * cross(p, q, s) < 0 && cross(r, s, p) * cross(r, s, q) < 0) return true;
  }
  return false;
}

/** Display-only drill polygons in source board mm. Rotation follows pad display
 * semantics: source Y is down, and the viewport reflects it before rotating. */
export function proceduralPadDrillPoints(at: Point, width: number, height: number, rotation: number): Point[] {
  const radius = Math.min(width, height) / 2, half = Math.abs(width - height) / 2;
  const vertical = height > width, angle = -rotation * Math.PI / 180;
  const result: Point[] = [];
  // Two semicircles form a routed slot; equal dimensions form a round bore.
  for (let side = 0; side < 2; side++) for (let step = 0; step <= 16; step++) {
    const theta = -Math.PI / 2 + side * Math.PI + step * Math.PI / 16;
    let x = (side ? -half : half) + radius * Math.cos(theta), y = radius * Math.sin(theta);
    if (vertical) [x, y] = [-y, x];
    result.push([at[0] + x * Math.cos(angle) - y * Math.sin(angle), at[1] + x * Math.sin(angle) + y * Math.cos(angle)]);
  }
  return result;
}

/** Local pad copper cutout; the mesh owns pad placement and rotation. Invalid
 * dimensions produce no cutout rather than a fabricated clamped drill. */
export function proceduralPadDrillPath(pad: Pick<ParsedPad, "drill" | "drill_shape" | "drill_size">, scale: number): THREE.Path | null {
  const size = pad.drill_size ?? [pad.drill, pad.drill];
  if (!Number.isFinite(scale) || scale <= 0 || !size.every(value => Number.isFinite(value) && value > 0)) return null;
  return new THREE.Path(proceduralPadDrillPoints([0, 0], size[0], pad.drill_shape === "oval" ? size[1] : size[0], 0)
    .map(([x, y]) => new THREE.Vector2(x * scale, -y * scale)));
}

/** Append safe through bores to an existing board outline in projected display
 * coordinates. Coincident drills and drills already inside outline cutouts are
 * omitted. Intersections needing a polygon boolean are reported and omitted;
 * they must not be fed to Earcut as overlapping hole rings. No hole-count cap.
 * The caller surfaces diagnostics or chooses authoritative geometry instead.
 */
export function appendProceduralDrillHoles(shape: THREE.Shape, board: Pick<ParsedBoard, "pads" | "vias">,
  project: (point: Point) => THREE.Vector2): ProceduralDrillReport {
  const report: ProceduralDrillReport = { added: 0, duplicates: 0, diagnostics: [] };
  const outer = shape.getPoints(16), existing = shape.holes.map(path => path.getPoints(16));
  const existingBounds = existing.map(bounds);
  const candidates: { id: string; polygon: Polygon; box: Bounds }[] = [];
  for (const item of [...board.pads, ...board.vias]) {
    const pad = "rotation" in item;
    // Span evidence is required: inner-only, blind and unknown spans do not
    // remove material through the whole laminate.
    if (!pad && !(item.layers.includes("F.Cu") && item.layers.includes("B.Cu") || item.layers.includes("*.Cu") || item.layers.includes("F&B.Cu"))) continue;
    const size = pad && item.drill_size ? item.drill_size : [item.drill, item.drill];
    if (!(item.drill > 0) && !size.some(value => value > 0)) continue;
    if (!size.every(value => Number.isFinite(value) && value > 0) || !item.at.every(Number.isFinite) || pad && !Number.isFinite(item.rotation)) {
      report.diagnostics.push({ id: item.id, reason: "invalid-drill" }); continue;
    }
    const polygon = proceduralPadDrillPoints(item.at, size[0], pad && item.drill_shape === "oval" ? size[1] : size[0], pad ? item.rotation : 0).map(project);
    candidates.push({ id: item.id, polygon, box: bounds(polygon) });
  }
  // Largest first makes a coincident smaller drill redundant. Grid cells are at
  // least as wide as every candidate, so each drill occupies at most four cells.
  candidates.sort((a, b) => (b.box.maxX - b.box.minX) * (b.box.maxY - b.box.minY) - (a.box.maxX - a.box.minX) * (a.box.maxY - a.box.minY));
  const cell = candidates.reduce((maximum, row) => Math.max(maximum, row.box.maxX - row.box.minX, row.box.maxY - row.box.minY), EPS);
  const bins = new Map<string, number[]>(), accepted: typeof candidates = [];
  const keys = (b: Bounds) => {
    const result: string[] = [];
    for (let x = Math.floor(b.minX / cell); x <= Math.floor(b.maxX / cell); x++) for (let y = Math.floor(b.minY / cell); y <= Math.floor(b.maxY / cell); y++) result.push(`${x}:${y}`);
    return result;
  };
  for (const row of candidates) {
    if (existing.some((hole, i) => intersectsBounds(existingBounds[i], row.box) && row.polygon.every(p => inside(p, hole)))) { report.duplicates++; continue; }
    if (!row.polygon.every(point => inside(point, outer)) || boundariesMeet(row.polygon, outer)
      || existing.some((hole, i) => intersectsBounds(existingBounds[i], row.box) && (boundariesMeet(row.polygon, hole) || inside(hole[0], row.polygon)))) {
      report.diagnostics.push({ id: row.id, reason: "outline-intersection" }); continue;
    }
    const cells = keys(row.box), nearby = new Set(cells.flatMap(key => bins.get(key) ?? []));
    const touching = [...nearby].map(i => accepted[i]).filter(other => intersectsBounds(other.box, row.box));
    if (touching.some(other => row.polygon.every(point => inside(point, other.polygon)))) { report.duplicates++; continue; }
    if (touching.some(other => boundariesMeet(row.polygon, other.polygon) || inside(other.polygon[0], row.polygon))) {
      report.diagnostics.push({ id: row.id, reason: "overlapping-drill" }); continue;
    }
    const index = accepted.push(row) - 1;
    cells.forEach(key => { const entries = bins.get(key) ?? []; entries.push(index); bins.set(key, entries); });
    shape.holes.push(new THREE.Path(row.polygon)); report.added++;
  }
  return report;
}
