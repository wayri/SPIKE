// SPDX-License-Identifier: Apache-2.0
// Presentation adapters only. Renderer-generated paths are not solver output.
import type { FieldPoint, FieldVolumeData } from "./fieldVolumeModel";
import type { PlotTrace } from "./plotClipboard";
export type FieldStreamline = { points: FieldPoint[]; scalars: Record<string, number[]> };
export function cartesianFluidGrid(data: FieldVolumeData, frameIndex: number) {
  if (data.cells.flowDomain !== "complete-cartesian-fluid") return null;
  const centers = data.cells.centers, vectors = data.frames[frameIndex]?.vectors;
  if (!vectors || centers.length > 40_000) return null;
  const axes = [0, 1, 2].map(axis => [...new Set(centers.map(p => p[axis]))].sort((a, b) => a - b));
  if (axes.some(a => a.length < 2) || axes.reduce((n, a) => n * a.length, 1) !== centers.length) return null;
  const lookup = new Map(centers.map((p, i) => [p.join(":"), i]));
  if (lookup.size !== centers.length) return null;
  const order: number[] = [];
  for (const x of axes[0]) for (const y of axes[1]) for (const z of axes[2]) {
    const index = lookup.get([x, y, z].join(":"));
    if (index === undefined) return null;
    order.push(index);
  }
  return { axes, order };
}
export function fieldStreamAvailability(data: FieldVolumeData, frame: number) {
  const saved = data.frames[frame];
  return { supplied: Boolean(saved?.streamlines?.length), grid: Boolean(cartesianFluidGrid(data, frame)) };
}
type Options = { mode: "streamlines" | "streamtubes"; frame: number; quantity: string; unit: string; celsius: boolean;
  minimum: number; maximum: number; opacity: number; budget: number; seedAxis: "x" | "y" | "z"; density: number; width: number };
export function streamPresentation(data: FieldVolumeData, options: Options): { traces: PlotTrace[]; note: string; count: number } {
  const frame = data.frames[options.frame], paths = frame.streamlines;
  const scale = { colorscale: "Viridis", cmin: options.minimum, cmax: options.maximum > options.minimum ? options.maximum : options.minimum + 1,
    showscale: true, colorbar: { thickness: 16, title: { text: `${data.quantities.find(q => q.id === options.quantity)?.label.slice(0, 40)} (${options.unit})`, side: "right" } } };
  if (paths?.length) {
    const selected: FieldStreamline[] = [];
    let vertices = 0;
    for (const path of paths) {
      if (selected.length >= 128 || vertices + path.points.length > Math.min(16_000, Math.max(500, options.budget * 2))) break;
      vertices += path.points.length; selected.push(path);
    }
    if (!selected.length) return { traces: [], count: 0, note: "Supplied paths exceed the display budget; increase the budget. Paths are never partially joined or spliced." };
    const value = (v: number) => options.celsius && options.unit === "°C" ? v - 273.15 : v;
    if (options.mode === "streamlines") {
      // One trace with gap separators keeps source path boundaries intact.
      const points: (FieldPoint | null)[] = [], colors: number[] = [];
      for (const path of selected) { path.points.forEach((p, i) => { points.push(p); colors.push(value(path.scalars[options.quantity][i])); }); points.push(null); colors.push(options.minimum); }
      return { traces: [{ type: "scatter3d", mode: "lines", name: "Supplied streamlines", x: points.map(p => p?.[0] ?? null), y: points.map(p => p?.[1] ?? null), z: points.map(p => p?.[2] ?? null),
        connectgaps: false, opacity: options.opacity, line: { width: options.width, color: colors, ...scale }, hoverinfo: "skip", showlegend: false }], count: selected.length,
        note: "Supplied curves: original points and scalar values; separate curves are never connected. Line width is cosmetic." };
    }
    let span = 0;
    for (let axis = 0; axis < 3; axis++) { let low = Infinity, high = -Infinity; for (const path of selected) for (const p of path.points) { low = Math.min(low, p[axis]); high = Math.max(high, p[axis]); } span = Math.max(span, high - low); }
    const radius = Math.max(span, 1e-12) * .0015 * options.width;
    const x: number[] = [], y: number[] = [], z: number[] = [], intensity: number[] = [], i: number[] = [], j: number[] = [], k: number[] = [];
    for (const path of selected) {
      const start = x.length;
      path.points.forEach((p, n) => {
        const a = path.points[Math.max(0, n - 1)], b = path.points[Math.min(path.points.length - 1, n + 1)];
        let direction = b.map((v, axis) => v - a[axis]); let norm = Math.hypot(...direction);
        if (!norm) { direction = [1, 0, 0]; norm = 1; }
        direction = direction.map(v => v / norm);
        const reference = Math.abs(direction[2]) < .9 ? [0, 0, 1] : [0, 1, 0];
        const u = [direction[1] * reference[2] - direction[2] * reference[1], direction[2] * reference[0] - direction[0] * reference[2], direction[0] * reference[1] - direction[1] * reference[0]];
        const unorm = Math.hypot(...u); for (let axis = 0; axis < 3; axis++) u[axis] /= unorm;
        const v = [direction[1] * u[2] - direction[2] * u[1], direction[2] * u[0] - direction[0] * u[2], direction[0] * u[1] - direction[1] * u[0]];
        for (let ring = 0; ring < 8; ring++) {
          const angle = ring * Math.PI / 4, point = p.map((value, axis) => value + radius * (u[axis] * Math.cos(angle) + v[axis] * Math.sin(angle)));
          x.push(point[0]); y.push(point[1]); z.push(point[2]); intensity.push(value(path.scalars[options.quantity][n]));
        }
        if (n > 0) for (let ring = 0; ring < 8; ring++) { const prev = start + (n - 1) * 8, current = start + n * 8, next = (ring + 1) % 8;
          i.push(prev + ring, prev + ring); j.push(current + ring, current + next); k.push(current + next, prev + next); }
      });
    }
    return { traces: [{ type: "mesh3d", name: "Supplied streamtubes", x, y, z, i, j, k, intensity, intensitymode: "vertex", opacity: options.opacity, ...scale,
      hovertemplate: `%{intensity:.6g} ${options.unit}<extra>Supplied curve</extra>` }], count: selected.length, note: "Supplied curves rendered as cosmetic-radius tubes. Radius does not encode mass flow or physical pipe diameter." };
  }
  const grid = cartesianFluidGrid(data, options.frame);
  if (options.mode !== "streamtubes" || !grid) return { traces: [], count: 0, note: "This frame has no supplied curves or complete 3D fluid grid. Sparse points and 2D sheets cannot establish safe connected 3D paths." };
  const seedAxis = { x: 0, y: 1, z: 2 }[options.seedAxis], sideAxes = [0, 1, 2].filter(a => a !== seedAxis);
  const density = Math.max(2, Math.min(8, Math.trunc(options.density)));
  const starts: FieldPoint[] = [];
  for (let a = 0; a < density; a++) for (let b = 0; b < density; b++) {
    const p = [0, 0, 0] as FieldPoint; p[seedAxis] = grid.axes[seedAxis][0];
    for (let n = 0; n < 2; n++) { const axis = sideAxes[n], values = grid.axes[axis], fraction = ((n === 0 ? a : b) + .5) / density;
      p[axis] = values[0] + fraction * (values[values.length - 1] - values[0]); }
    starts.push(p);
  }
  let maxSpeed = 0;
  for (const saved of data.frames) if (saved.vectors) for (const v of saved.vectors) maxSpeed = Math.max(maxSpeed, Math.hypot(...v));
  if (maxSpeed === 0) return { traces: [], count: 0, note: "Zero velocity: no renderer-generated streamtubes." };
  return { traces: [{ type: "streamtube", name: "Renderer-generated velocity streamtubes", ...Object.fromEntries(["x", "y", "z"].map((axis, n) => [axis, grid.order.map(i => data.cells.centers[i][n])])),
    ...Object.fromEntries(["u", "v", "w"].map((axis, n) => [axis, grid.order.map(i => frame.vectors![i][n])])),
    starts: { x: starts.map(p => p[0]), y: starts.map(p => p[1]), z: starts.map(p => p[2]) }, maxdisplayed: Math.max(2, Math.min(256, Math.floor(options.budget / starts.length))), sizeref: options.width * .08,
    colorscale: "Viridis", cmin: 0, cmax: maxSpeed, opacity: options.opacity, showscale: true, colorbar: { title: { text: "Velocity (m/s)", side: "right" }, thickness: 16 }, hoverinfo: "x+y+z+norm" }], count: starts.length,
    note: "Preview streamtubes traced by the plot renderer from the declared complete fluid grid. Color is speed, not the selected scalar. Tube radius is a renderer glyph, not physical flow area. Frozen-time streamlines are not transient particle paths." };
}
