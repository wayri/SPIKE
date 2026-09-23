export type MountClassificationPad = {
  ref?: string;
  drill: number;
};

/** Replace imported component picks in one pass, independent of part count. */
export function partitionComponentProxies<T extends { userData: { id?: string; type?: string } }>(
  proxies: readonly T[],
  replacementIds: ReadonlySet<string>,
): { retained: T[]; replaced: T[]; inspected: number } {
  const retained: T[] = [];
  const replaced: T[] = [];
  for (const proxy of proxies) {
    const data = proxy.userData;
    (data.type === "component" && data.id && replacementIds.has(data.id) ? replaced : retained).push(proxy);
  }
  return { retained, replaced, inspected: proxies.length };
}

/** Build once so component mount classification is O(pads + components). */
export function throughHoleComponentRefs(pads: readonly MountClassificationPad[]): Set<string> {
  const refs = new Set<string>();
  for (const pad of pads) {
    if (pad.drill > 0 && pad.ref) refs.add(pad.ref);
  }
  return refs;
}

/** First source object for each net, in caller-defined category priority. */
export function firstObjectByNet<T extends { net?: string }>(...groups: readonly (readonly T[])[]): Map<string, T> {
  const first = new Map<string, T>();
  for (const group of groups) for (const item of group) {
    if (item.net && !first.has(item.net)) first.set(item.net, item);
  }
  return first;
}

export function boundedMatches<T>(items: readonly T[], matches: (item: T) => boolean, maximum: number): T[] {
  const result: T[] = [];
  if (maximum <= 0) return result;
  for (const item of items) {
    if (matches(item)) result.push(item);
    if (result.length >= maximum) break;
  }
  return result;
}

/** Fixed-height window for large assembly lists; every row remains reachable. */
export function sceneRowWindow(count: number, scrollTop: number, height = 304, rowHeight = 38, overscan = 4) {
  const top = Math.max(0, Math.min(scrollTop, Math.max(0, count * rowHeight - height)));
  const start = Math.max(0, Math.floor(top / rowHeight) - overscan);
  const end = Math.min(count, Math.ceil((top + height) / rowHeight) + overscan);
  return { start, end, before: start * rowHeight, after: (count - end) * rowHeight };
}

/** Preserve first-seen display order while removing empty and repeated nets. */
export function uniqueViewportNets(values: readonly (string | null | undefined)[]): string[] {
  const nets: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    if (!value || seen.has(value)) continue;
    seen.add(value);
    nets.push(value);
  }
  return nets;
}

export class KeyedResourcePool<T> {
  private readonly values = new Map<string, T>();
  requests = 0;

  acquire(key: string, create: () => T): T {
    this.requests += 1;
    const existing = this.values.get(key);
    if (existing !== undefined) return existing;
    const value = create();
    this.values.set(key, value);
    return value;
  }

  get size(): number { return this.values.size; }
}

/**
 * Keep display work inside a hard GPU/CPU cost budget. The caller supplies a
 * conservative integer cost (for example rendered triangles). Items remain in
 * deterministic source order and at least one admissible item is retained.
 */
export function takeWithinCostBudget<T>(
  items: readonly T[],
  maximumCost: number,
  costOf: (item: T) => number,
): { items: T[]; cost: number; omitted: number } {
  const limit = Math.max(1, Math.floor(maximumCost));
  const retained: T[] = [];
  let cost = 0;
  for (const item of items) {
    const itemCost = Math.max(0, Math.floor(costOf(item)));
    if (retained.length && cost + itemCost > limit) continue;
    retained.push(item);
    cost += itemCost;
  }
  return { items: retained, cost, omitted: items.length - retained.length };
}

/**
 * Deterministically retain a bounded, spatially distributed display subset.
 * This affects only viewport proxies; callers keep the complete design for
 * solver input, reports, search, and exact exported geometry.
 */
export function evenlyBoundedDisplayItems<T>(items: readonly T[], maximum: number): T[] {
  const limit = Math.max(1, Math.floor(maximum));
  if (items.length <= limit) return [...items];
  if (limit === 1) return [items[0]];
  const retained: T[] = [];
  const stride = (items.length - 1) / (limit - 1);
  let previous = -1;
  for (let slot = 0; slot < limit; slot += 1) {
    const index = Math.min(items.length - 1, Math.round(slot * stride));
    if (index !== previous) retained.push(items[index]);
    previous = index;
  }
  return retained;
}


export type CopperNetLabel = { id: string; net: string; layer: string; x: number; y: number; angle: number; fontSize: number; kind: "trace" | "zone" };

/** View-dependent, bounded presentation labels. Coordinates and widths are mm. */
export function copperNetLabels(
  tracks: readonly { id: string; net?: string; layer: string; start: [number, number]; end: [number, number]; width: number }[],
  zones: readonly { id: string; net?: string; layer: string; points: [number, number][]; holes?: [number, number][][] }[],
  view: { minX: number; minY: number; maxX: number; maxY: number; unitsPerPixel: number },
  limit = 400,
): CopperNetLabel[] {
  const output: CopperNetLabel[] = [];
  const unit = view.unitsPerPixel;
  if (!(unit > 0) || !Number.isFinite(unit)) return output;
  const occupied = new Map<string, { x: number; y: number; w: number; h: number }[]>();
  const cell = unit * 64;
  const add = (label: CopperNetLabel) => {
    if (output.length >= limit) return;
    const textWidth = label.fontSize * (label.net.length * 0.65 + 1);
    const radians = label.angle * Math.PI / 180;
    const w = Math.abs(Math.cos(radians)) * textWidth + Math.abs(Math.sin(radians)) * label.fontSize;
    const h = Math.abs(Math.sin(radians)) * textWidth + Math.abs(Math.cos(radians)) * label.fontSize;
    const x = label.x - w / 2, y = label.y - h / 2;
    if (x < view.minX || y < view.minY || x + w > view.maxX || y + h > view.maxY) return;
    const keys: string[] = [];
    for (let ix = Math.floor(x / cell); ix <= Math.floor((x + w) / cell); ix++) {
      for (let iy = Math.floor(y / cell); iy <= Math.floor((y + h) / cell); iy++) {
        const key = `${ix}:${iy}`;
        if ((occupied.get(key) ?? []).some(b => x < b.x + b.w && x + w > b.x && y < b.y + b.h && y + h > b.y)) return;
        keys.push(key);
      }
    }
    const box = { x, y, w, h };
    for (const key of keys) occupied.set(key, [...(occupied.get(key) ?? []), box]);
    output.push(label);
  };
  // Scanline intervals handle concave zones and holes without labeling empty space.
  for (const zone of zones) {
    if (!zone.net || zone.net.length > 160 || output.length >= limit || zone.points.length < 3) continue;
    let lo = Infinity, hi = -Infinity;
    for (const point of zone.points) { lo = Math.min(lo, point[1]); hi = Math.max(hi, point[1]); }
    lo = Math.max(lo, view.minY); hi = Math.min(hi, view.maxY);
    const fontSize = unit * 11;
    if (hi - lo < fontSize * 2) continue;
    const intervals = (y: number) => {
      const hits: number[] = [];
      for (const ring of [zone.points, ...(zone.holes ?? [])]) for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const a = ring[j], b = ring[i];
        if ((a[1] > y) !== (b[1] > y)) hits.push(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]));
      }
      hits.sort((a, b) => a - b);
      return hits.flatMap((x, i) => i % 2 ? [] : [[Math.max(x, view.minX), Math.min(hits[i + 1] ?? x, view.maxX)]]);
    };
    const needed = fontSize * (zone.net.length * 0.65 + 1);
    let best: { x: number; y: number; width: number } | undefined;
    for (const t of [0.5, 0.25, 0.75]) {
      const y = lo + (hi - lo) * t;
      for (const [left, right] of intervals(y)) {
        const x = (left + right) / 2;
        if (right - left < needed || best && right - left <= best.width) continue;
        if ([-0.6, 0.6].every(d => intervals(y + fontSize * d).some(([a, b]) => x - needed / 2 >= a && x + needed / 2 <= b)))
          best = { x, y, width: right - left };
      }
    }
    if (best) add({ id: zone.id, net: zone.net, layer: zone.layer, kind: "zone", x: best.x, y: best.y, angle: 0, fontSize });
  }
  for (const track of tracks) {
    if (!track.net || track.net.length > 160 || output.length >= limit) continue;
    const fontSize = Math.min(unit * 11, track.width * 0.8);
    if (fontSize < unit * 7) continue;
    const dx = track.end[0] - track.start[0], dy = track.end[1] - track.start[1];
    let t0 = 0, t1 = 1;
    // Clip to the visible rectangle before positioning a label on a long trace.
    for (const [p, q] of [[-dx, track.start[0] - view.minX], [dx, view.maxX - track.start[0]], [-dy, track.start[1] - view.minY], [dy, view.maxY - track.start[1]]]) {
      if (p === 0) { if (q < 0) t1 = -1; }
      else if (p < 0) t0 = Math.max(t0, q / p);
      else t1 = Math.min(t1, q / p);
    }
    if (t1 <= t0 || Math.hypot(dx, dy) * (t1 - t0) < fontSize * (track.net.length * 0.65 + 1)) continue;
    const t = (t0 + t1) / 2;
    let angle = Math.atan2(dy, dx) * 180 / Math.PI;
    if (angle > 90) angle -= 180;
    if (angle < -90) angle += 180;
    add({ id: track.id, net: track.net, layer: track.layer, kind: "trace", x: track.start[0] + dx * t, y: track.start[1] + dy * t, angle, fontSize });
  }
  return output;
}
