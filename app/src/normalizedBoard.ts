import type { ParsedBoard, ParsedDrawing, Point } from "./boardParser";

// This is a display projection only. Exact imported geometry is retained in the
// snapshot and passed to solvers; display tessellation never becomes solver data.
export function normalizedDesignSnapshot(source: string): Record<string, any> {
  const raw = JSON.parse(source);
  if (raw?.contract !== "spike/design-snapshot/v1" || raw.design?.contract !== "spike/v1") throw new Error("Invalid normalized design snapshot.");
  return raw;
}

export function normalizedSolverDesign(source: string): Record<string, any> {
  const snapshot = normalizedDesignSnapshot(source);
  if (snapshot.canonical_design?.metadata?.transport_projection?.legacy_omitted_collections?.length) {
    throw new Error("Imported geometry has not finished transport hydration; reopen the board before analysis.");
  }
  return snapshot.design;
}

function arcPoints(start: Point, end: Point, center: Point, clockwise: boolean): Point[] {
  const radius = Math.hypot(start[0] - center[0], start[1] - center[1]);
  const a = Math.atan2(start[1] - center[1], start[0] - center[0]);
  const b = Math.atan2(end[1] - center[1], end[0] - center[0]);
  const tau = 2 * Math.PI;
  const sweep = ((clockwise ? a - b : b - a) % tau + tau) % tau || tau;
  const count = Math.min(4096, Math.max(8, Math.ceil(sweep / Math.max(.005, 2 * Math.acos(Math.max(-1, 1 - .01 / Math.max(radius, .01)))))));
  return Array.from({ length: count }, (_, i) => {
    const angle = a + (clockwise ? -1 : 1) * sweep * (i + 1) / count;
    return i === count - 1 ? end : [center[0] + radius * Math.cos(angle), center[1] + radius * Math.sin(angle)];
  });
}

function ringPoints(ring: any): Point[] {
  let current = ring.start_mm as Point;
  const output: Point[] = [current];
  for (const segment of ring.segments ?? []) {
    if (segment.kind === "arc") output.push(...arcPoints(current, segment.end_mm, segment.center_mm, segment.clockwise));
    else output.push(segment.end_mm);
    current = segment.end_mm;
  }
  return output;
}

function threePointArc(start: Point, middle: Point, end: Point): Point[] {
  const [x1, y1] = start;
  const [xm, ym] = middle;
  const [x2, y2] = end;
  const determinant = 2 * (x1 * (ym - y2) + xm * (y2 - y1) + x2 * (y1 - ym));
  if (Math.abs(determinant) < 1e-9) return [start, end];
  const center: Point = [
    ((x1 * x1 + y1 * y1) * (ym - y2) + (xm * xm + ym * ym) * (y2 - y1) + (x2 * x2 + y2 * y2) * (y1 - ym)) / determinant,
    ((x1 * x1 + y1 * y1) * (x2 - xm) + (xm * xm + ym * ym) * (x1 - x2) + (x2 * x2 + y2 * y2) * (xm - x1)) / determinant,
  ];
  const tau = 2 * Math.PI;
  const a = Math.atan2(start[1] - center[1], start[0] - center[0]);
  const m = ((Math.atan2(middle[1] - center[1], middle[0] - center[0]) - a) % tau + tau) % tau;
  const b = ((Math.atan2(end[1] - center[1], end[0] - center[0]) - a) % tau + tau) % tau;
  const sweep = m <= b ? b : b - tau;
  const radius = Math.hypot(start[0] - center[0], start[1] - center[1]);
  const count = Math.max(8, Math.ceil(Math.abs(sweep) / (Math.PI / 24)));
  return Array.from({ length: count + 1 }, (_, index) => index === count ? end : [
    center[0] + radius * Math.cos(a + sweep * index / count),
    center[1] + radius * Math.sin(a + sweep * index / count),
  ] as Point);
}

function projectedDrawing(row: any, index: number): ParsedDrawing | null {
  const type = row.type === "arc_3pt" ? "arc" : row.type;
  let points: Point[] = [];
  if (type === "line") points = [row.start, row.end];
  else if (type === "arc") points = threePointArc(row.start, row.mid, row.end);
  else if (type === "circle") {
    points = Array.from({ length: 65 }, (_, step) => {
      const angle = 2 * Math.PI * step / 64;
      return [row.center[0] + row.radius * Math.cos(angle), row.center[1] + row.radius * Math.sin(angle)] as Point;
    });
  } else if (type === "rect" || type === "poly") points = row.points ?? [];
  if (points.some(point => !Array.isArray(point) || point.length < 2)) return null;
  if (!points.length) return null;
  return { id: row.id ?? `normalized-drawing-${index}`, type, points, layer: row.layer ?? "Dwgs.User", width: row.width ?? 0.1 };
}

function drawingLoops(drawings: ParsedDrawing[]): Point[][] {
  const close = (a: Point, b: Point) => Math.hypot(a[0] - b[0], a[1] - b[1]) <= 0.015;
  const loops: Point[][] = [];
  const open: Point[][] = drawings.filter(row => row.layer === "Edge.Cuts").map(row => [...row.points]);
  while (open.length) {
    const path = open.shift()!;
    while (!close(path[0], path[path.length - 1])) {
      const index = open.findIndex(candidate => close(path[path.length - 1], candidate[0]) || close(path[path.length - 1], candidate[candidate.length - 1]));
      if (index < 0) break;
      const candidate = open.splice(index, 1)[0];
      path.push(...(close(path[path.length - 1], candidate[0]) ? candidate.slice(1) : candidate.slice(0, -1).reverse()));
    }
    if (path.length > 2 && close(path[0], path[path.length - 1])) {
      path[path.length - 1] = path[0];
      loops.push(path);
    }
  }
  return loops;
}

export function parseNormalizedBoard(source: string): ParsedBoard {
  const { design: d, canonical_design: canonical } = normalizedDesignSnapshot(source);
  const nets: Record<string, string> = Object.fromEntries(d.nets.map((n: any) => [String(n.id), n.name]));
  const net = (row: any) => nets[String(row.net_id)] ?? row.net_name ?? "";
  const layerDefinitions = d.layers.map((l: any, index: number) => ({ id: index, name: l.name, kind: l.type === "power_ground" ? "power" : l.type }));
  const layers = layerDefinitions.filter((l: any) => ["signal", "power", "copper", "conductor", "mixed"].includes(l.kind) || (!l.kind && l.name.endsWith(".Cu"))).map((l: any) => l.name);
  const drawings = (d.metadata.board_outline_drawings ?? []).map(projectedDrawing).filter((row: ParsedDrawing | null): row is ParsedDrawing => Boolean(row));
  const outlineLoops = d.metadata.board_outline_rings?.length
    ? d.metadata.board_outline_rings.map(ringPoints)
    : drawingLoops(drawings);
  const bounds = d.metadata.board_bounds_mm ?? [0, 0, 1, 1];
  const artwork = d.metadata.odb_artwork ?? canonical?.metadata?.odb_artwork ?? [];
  const canonicalLayerNames = new Map((canonical?.layers ?? []).map((layer: any) => [layer.id, layer.name]));
  const canonicalNetNames = new Map((canonical?.nets ?? []).map((entry: any) => [entry.id, entry.name]));
  const omittedZones = canonical?.metadata?.transport_projection?.legacy_omitted_collections?.includes("zones");
  if (omittedZones && !Array.isArray(canonical?.zones)) throw new Error("Normalized snapshot is missing its canonical zone geometry.");
  const zoneRows = omittedZones ? canonical.zones.flatMap((zone: any) => zone.layer_ids.map((id: string) => ({
    ...zone, id: zone.source_id || zone.id, layer: canonicalLayerNames.get(id), net_name: canonicalNetNames.get(zone.net_id) ?? "",
  }))) : d.zones;
  const tracks = [...d.tracks, ...artwork.filter((r: any) => r.kind === "track")].map((r: any) => ({ ...r, net: net(r) }));
  for (const arc of [...(d.metadata.arcs ?? []), ...artwork.filter((r: any) => r.kind === "arc")]) {
    if (!arc.center) continue;
    const points = [arc.start, ...arcPoints(arc.start, arc.end, arc.center, arc.clockwise)];
    points.slice(1).forEach((end, i) => tracks.push({ id: `${arc.id}:display:${i}`, start: points[i], end, width: arc.width, layer: arc.layer, net: net(arc) }));
  }
  return {
    width: bounds[2] - bounds[0], height: bounds[3] - bounds[1], bounds: { minX: bounds[0], minY: bounds[1], maxX: bounds[2], maxY: bounds[3] }, outlineLoops,
    tracks, layers, layerDefinitions, nets,
    vias: d.vias.map((v: any) => ({ ...v, size: v.diameter, net: net(v) })),
    pads: [...d.pads, ...artwork.filter((r: any) => r.kind === "pad")].map((p: any) => { const size = p.size ?? p.size_mm ?? [1, 1]; return ({ ...p, customPolygon: p.custom_geometry?.status === "supported" ? p.custom_geometry.positive_filled_polygon : undefined, at: p.at ?? p.center_mm, name: p.number ?? p.name ?? "", width: size[0], height: size[1], drill: p.drill ?? p.drill_size_mm?.[0] ?? 0, rotation: p.rotation ?? p.rotation_deg ?? 0, net: net(p), ref: p.component ?? p.component_id }); }),
    components: d.components.map((c: any) => ({ ...c, ref: c.reference, at: c.at ?? c.position_mm, rotation: c.rotation ?? c.rotation_deg ?? 0, library: c.footprint ?? c.library ?? "",
      width: (c.odb_package_ref ?? c.odb_package)?.bounds_mm ? (c.odb_package_ref ?? c.odb_package).bounds_mm[2] - (c.odb_package_ref ?? c.odb_package).bounds_mm[0] : 2,
      height: (c.odb_package_ref ?? c.odb_package)?.bounds_mm ? (c.odb_package_ref ?? c.odb_package).bounds_mm[3] - (c.odb_package_ref ?? c.odb_package).bounds_mm[1] : 2,
      layer: c.side === "bottom" ? layers[layers.length - 1] : c.side === "top" ? layers[0] : c.layer ?? layers[0], modelOffset: [0,0,0], modelScale: [1,1,1], modelRotation: [0,0,0] })),
    zones: [...zoneRows, ...artwork.filter((r: any) => r.kind === "zone")].map((z: any) => ({ id: z.id, layer: z.layer, net: net(z), points: z.boundary_rings?.length ? ringPoints(z.boundary_rings[0]) : z.points ?? z.outlines_mm?.[0] ?? [], holes: z.boundary_rings?.length ? z.boundary_rings.slice(1).map(ringPoints) : z.holes_mm ?? [] })),
    drawings, stackup: d.stackup.map((s: any) => ({ ...s, epsilonR: s.epsilon_r, lossTangent: s.loss_tangent })), technology: d.technology ?? "rigid",
  };
}
