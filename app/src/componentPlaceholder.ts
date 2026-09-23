// SPDX-License-Identifier: MIT

export type ComponentPlaceholderBounds = {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
};

type PlaceholderComponent = {
  ref: string;
  value?: string;
  library?: string;
  at: readonly [number, number];
  width?: number;
  height?: number;
  rotation?: number;
  bodyBounds?: ComponentPlaceholderBounds;
  courtyardBounds?: ComponentPlaceholderBounds;
  properties?: readonly { name?: unknown; values?: readonly unknown[] }[];
};

type PlaceholderPad = {
  at: readonly [number, number];
  width: number;
  height: number;
  rotation?: number;
};

export type ComponentPlaceholderDimensions = {
  widthMm: number;
  depthMm: number;
  heightMm: number;
  centerOffsetMm: [number, number];
  planarSource: "pads" | "body" | "courtyard" | "component" | "generic";
  heightSource: "metadata" | "default";
};

const MIN_PLANAR_MM = 0.2;
const MAX_PLANAR_MM = 200;
const MIN_HEIGHT_MM = 0.1;
const MAX_HEIGHT_MM = 50;

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum);
}

function usableBounds(bounds: ComponentPlaceholderBounds | undefined) {
  if (!bounds) return null;
  const values = [bounds.minX, bounds.minY, bounds.maxX, bounds.maxY];
  if (!values.every(Number.isFinite) || bounds.maxX <= bounds.minX || bounds.maxY <= bounds.minY) return null;
  const width = bounds.maxX - bounds.minX;
  const depth = bounds.maxY - bounds.minY;
  if (width > MAX_PLANAR_MM || depth > MAX_PLANAR_MM) return null;
  return {
    width: clamp(width, MIN_PLANAR_MM, MAX_PLANAR_MM),
    depth: clamp(depth, MIN_PLANAR_MM, MAX_PLANAR_MM),
    center: [(bounds.minX + bounds.maxX) / 2, (bounds.minY + bounds.maxY) / 2] as [number, number],
    minX: bounds.minX, minY: bounds.minY, maxX: bounds.maxX, maxY: bounds.maxY,
  };
}

type UsableBounds = NonNullable<ReturnType<typeof usableBounds>>;

function shrinkCourtyard(bounds: UsableBounds): UsableBounds {
  const width = Math.max(MIN_PLANAR_MM, bounds.width - Math.min(0.5, bounds.width * 0.2));
  const depth = Math.max(MIN_PLANAR_MM, bounds.depth - Math.min(0.5, bounds.depth * 0.2));
  return { width, depth, center: bounds.center,
    minX: bounds.center[0] - width / 2, maxX: bounds.center[0] + width / 2,
    minY: bounds.center[1] - depth / 2, maxY: bounds.center[1] + depth / 2 };
}

function boundedUnion(pads: UsableBounds, body: UsableBounds) {
  const overlaps = body.maxX >= pads.minX && body.minX <= pads.maxX
    && body.maxY >= pads.minY && body.minY <= pads.maxY;
  if (!overlaps) return null;
  const union = usableBounds({ minX: Math.min(pads.minX, body.minX), minY: Math.min(pads.minY, body.minY),
    maxX: Math.max(pads.maxX, body.maxX), maxY: Math.max(pads.maxY, body.maxY) });
  if (!union) return null;
  const widthLimit = Math.max(pads.width * 3, pads.width + 20);
  const depthLimit = Math.max(pads.depth * 3, pads.depth + 20);
  return union.width <= widthLimit && union.depth <= depthLimit ? union : null;
}

function padEnvelope(component: PlaceholderComponent, pads: readonly PlaceholderPad[]) {
  if (!pads.length) return null;
  const componentRotation = Number(component.rotation) || 0;
  const angle = componentRotation * Math.PI / 180;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  for (const pad of pads) {
    if (!pad.at.every(Number.isFinite) || !Number.isFinite(pad.width) || !Number.isFinite(pad.height)) continue;
    const dx = pad.at[0] - component.at[0];
    const dy = pad.at[1] - component.at[1];
    // Board coordinates use the inverse of the footprint rotation. Transform
    // pad centers back into the component-local frame before finding bounds.
    const localX = dx * cos - dy * sin;
    const localY = dx * sin + dy * cos;
    const relativeAngle = ((Number(pad.rotation) || 0) - componentRotation) * Math.PI / 180;
    const halfWidth = Math.abs(Math.cos(relativeAngle)) * Math.abs(pad.width) / 2
      + Math.abs(Math.sin(relativeAngle)) * Math.abs(pad.height) / 2;
    const halfDepth = Math.abs(Math.sin(relativeAngle)) * Math.abs(pad.width) / 2
      + Math.abs(Math.cos(relativeAngle)) * Math.abs(pad.height) / 2;
    minX = Math.min(minX, localX - halfWidth); maxX = Math.max(maxX, localX + halfWidth);
    minY = Math.min(minY, localY - halfDepth); maxY = Math.max(maxY, localY + halfDepth);
  }
  return usableBounds({ minX, minY, maxX, maxY });
}

function explicitHeight(component: PlaceholderComponent) {
  for (const property of component.properties ?? []) {
    if (!/height/i.test(String(property.name ?? ""))) continue;
    for (const raw of property.values ?? []) {
      const match = String(raw).trim().match(/^([0-9]+(?:\.[0-9]+)?)\s*(mm|mil|in|inch|inches)?$/i);
      if (!match) continue;
      let value = Number(match[1]);
      const unit = match[2]?.toLowerCase();
      if (unit === "mil") value *= 0.0254;
      else if (unit === "in" || unit === "inch" || unit === "inches") value *= 25.4;
      if (Number.isFinite(value) && value >= MIN_HEIGHT_MM && value <= MAX_HEIGHT_MM) return value;
    }
  }
  return null;
}

function defaultHeight(component: PlaceholderComponent, width: number, depth: number, mount: "smd" | "tht") {
  const identity = `${component.ref} ${component.value ?? ""} ${component.library ?? ""}`.toUpperCase();
  const prefix = component.ref.match(/^[A-Z]+/i)?.[0]?.toUpperCase() ?? "";
  const smallerSide = Math.min(width, depth);
  if (/\b(CONN|CONNECTOR|HEADER|SOCKET|TERMINAL)\b/.test(identity) || prefix === "J" || prefix === "P") {
    return clamp(smallerSide * 0.75, 3, 12);
  }
  if (prefix === "C" || prefix === "R") return clamp(smallerSide * 0.75, 0.3, 2.5);
  if (prefix === "L") return clamp(smallerSide * 0.8, 1, 5);
  if (prefix === "D" || prefix === "Q") return clamp(smallerSide * 0.55, 0.6, 3.5);
  if (prefix === "U" || prefix === "IC") return clamp(smallerSide * 0.28, 0.7, 4);
  if (mount === "tht") return clamp(smallerSide * 0.55, 2, 10);
  return clamp(smallerSide * 0.4, 0.6, 4);
}

/**
 * Produce a conservative visual proxy for a component whose model is absent.
 * Dimensions describe a generic solid only; they do not imply model geometry.
 */
export function deriveComponentPlaceholder(
  component: PlaceholderComponent,
  pads: readonly PlaceholderPad[],
  mount: "smd" | "tht",
): ComponentPlaceholderDimensions {
  const padBounds = padEnvelope(component, pads);
  const bodyBounds = usableBounds(component.bodyBounds);
  const rawCourtyardBounds = usableBounds(component.courtyardBounds);
  const courtyardBounds = rawCourtyardBounds ? shrinkCourtyard(rawCourtyardBounds) : null;
  const legacyBounds = usableBounds({ minX: -(Number(component.width) || 0) / 2, minY: -(Number(component.height) || 0) / 2,
    maxX: (Number(component.width) || 0) / 2, maxY: (Number(component.height) || 0) / 2 });
  const identity = `${component.ref} ${component.value ?? ""} ${component.library ?? ""}`.toUpperCase();
  const connectorLike = /\b(CONN|CONNECTOR|HEADER|SOCKET|TERMINAL|FMC)\b/.test(identity) || /^[JP]/i.test(component.ref);
  const connectorBody = connectorLike && padBounds && bodyBounds ? boundedUnion(padBounds, bodyBounds) : null;
  const connectorCourtyard = connectorLike && padBounds && !connectorBody && courtyardBounds
    ? boundedUnion(padBounds, courtyardBounds) : null;
  const selected = connectorBody ?? connectorCourtyard ?? padBounds ?? bodyBounds ?? courtyardBounds ?? legacyBounds;
  const planarSource: ComponentPlaceholderDimensions["planarSource"] = connectorBody ? "body"
    : connectorCourtyard ? "courtyard" : padBounds ? "pads"
      : bodyBounds ? "body" : courtyardBounds ? "courtyard" : legacyBounds ? "component" : "generic";
  const width = selected?.width ?? 2;
  const depth = selected?.depth ?? 2;
  const metadataHeight = explicitHeight(component);
  return {
    widthMm: clamp(width, MIN_PLANAR_MM, MAX_PLANAR_MM),
    depthMm: clamp(depth, MIN_PLANAR_MM, MAX_PLANAR_MM),
    heightMm: metadataHeight ?? defaultHeight(component, width, depth, mount),
    centerOffsetMm: selected?.center ?? [0, 0],
    planarSource,
    heightSource: metadataHeight === null ? "default" : "metadata",
  };
}
