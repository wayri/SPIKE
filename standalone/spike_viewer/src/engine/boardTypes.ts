// SPDX-License-Identifier: Apache-2.0
/**
 * Normalized, renderer-facing board contract.
 *
 * The standalone viewer deliberately does not parse KiCad or any other EDA
 * source format. Hosts adapt their data to this contract before rendering.
 */
export type Point = [number, number];

export type ParsedTrack = {
  id: string;
  start: Point;
  end: Point;
  width: number;
  layer: string;
  net?: string;
};

export type ParsedVia = {
  id: string;
  at: Point;
  size: number;
  drill: number;
  layers: string[];
  net?: string;
};

export type ParsedPad = {
  id: string;
  name: string;
  at: Point;
  width: number;
  height: number;
  rotation: number;
  shape: string;
  customPolygon?: Point[];
  drill: number;
  drill_size?: [number, number];
  drill_shape?: "circle" | "oval";
  size?: [number, number];
  type?: string;
  pad_kind?: string;
  plated?: boolean;
  roundrect_rratio?: number;
  layers: string[];
  layer: string;
  net?: string;
  ref?: string;
};

export type ParsedFootprintModel = {
  path: string;
  offset: [number, number, number];
  scale: [number, number, number];
  rotation: [number, number, number];
  transform?: number[];
};

export type ParsedComponent = {
  id: string;
  ref: string;
  value: string;
  library: string;
  at: Point;
  width: number;
  height: number;
  rotation: number;
  layer: string;
  model?: boolean;
  modelPath?: string;
  modelPaths?: string[];
  modelUrl?: string;
  modelOffset: [number, number, number];
  modelScale: [number, number, number];
  modelRotation: [number, number, number];
  models?: ParsedFootprintModel[];
  bodyBounds?: { minX: number; minY: number; maxX: number; maxY: number };
  courtyardBounds?: { minX: number; minY: number; maxX: number; maxY: number };
  properties?: readonly { name?: unknown; values?: readonly unknown[] }[];
  vendor_properties?: Record<string, unknown>;
  bom_records?: readonly string[];
};

export type ParsedZone = {
  id: string;
  points: Point[];
  holes?: Point[][];
  layer: string;
  net?: string;
  source_kind?: string;
  filled_copper_state?: string;
  source_fill_provenance_complete?: boolean;
  source_fill_representation?: string;
};

export type ParsedDrawing = {
  id: string;
  type: "line" | "arc" | "circle" | "poly" | "rect";
  points: Point[];
  layer: string;
  width: number;
  ref?: string;
  filled?: boolean;
};

export type ParsedLayerDefinition = {
  id: number;
  name: string;
  kind: string;
  userName?: string;
};

export type ParsedStackupLayer = {
  name: string;
  type: string;
  color?: string;
  thickness?: number;
  material?: string;
  epsilonR?: number;
  lossTangent?: number;
};

export type ParsedBoardRegion = {
  id: string;
  name: string;
  kind: "rigid" | "flex" | "transition" | "stiffener";
  outline: Point[];
  sourceLayer: string;
  source: "kicad-user-layer" | "implicit-board-outline" | "project";
  stackup?: ParsedStackupLayer[];
};

export type ParsedBendLine = {
  id: string;
  name: string;
  points: Point[];
  sourceLayer: string;
  radiusMm?: number;
  angleDeg?: number;
};

export type ParsedBoard = {
  width: number;
  height: number;
  bounds: { minX: number; minY: number; maxX: number; maxY: number };
  outlineLoops: Point[][];
  tracks: ParsedTrack[];
  vias: ParsedVia[];
  pads: ParsedPad[];
  components: ParsedComponent[];
  zones: ParsedZone[];
  drawings: ParsedDrawing[];
  layers: string[];
  layerDefinitions: ParsedLayerDefinition[];
  stackup: ParsedStackupLayer[];
  nets: Record<string, string>;
  fullModelUrl?: string;
  boardModelUrl?: string;
  boardModelIncludesCopper?: boolean;
  componentModelUrl?: string;
  layoutLayerUrls?: Record<string, string>;
  layoutViewBox?: [number, number, number, number];
  modelManifestUrl?: string;
  technology?: "rigid" | "flex" | "rigid-flex";
  regions?: ParsedBoardRegion[];
  bendLines?: ParsedBendLine[];
};

const COPPER_LAYER_KINDS = new Set(["signal", "power", "mixed", "jumper"]);

export function isCopperLayerDefinition(layer: ParsedLayerDefinition): boolean {
  if (!layer.name || layer.name.includes("*")) return false;
  return layer.name.endsWith(".Cu") || COPPER_LAYER_KINDS.has(layer.kind.toLowerCase());
}

function fallbackCopperOrder(a: string, b: string): number {
  if (a === "F.Cu") return -1;
  if (b === "F.Cu") return 1;
  if (a === "B.Cu") return 1;
  if (b === "B.Cu") return -1;
  return a.localeCompare(b, undefined, { numeric: true });
}

export function orderedCopperLayerNames(
  definitions: ParsedLayerDefinition[],
  discovered: Iterable<string> = [],
  stackupNames: Iterable<string> = [],
): string[] {
  const tableOrder = [...definitions]
    .filter(isCopperLayerDefinition)
    .map(layer => layer.name);
  const stackOrder = [...new Set(stackupNames)]
    .filter(name => name.endsWith(".Cu") && !name.includes("*"));
  const stackSet = new Set(stackOrder);
  const ordered = tableOrder.length > 0 && tableOrder.every(name => stackSet.has(name))
    ? [...stackOrder, ...tableOrder.filter(name => !stackSet.has(name))]
    : tableOrder;
  const known = new Set(ordered);
  const recovered = [...new Set(discovered)]
    .filter(name => name.endsWith(".Cu") && !name.includes("*") && !known.has(name))
    .sort(fallbackCopperOrder);
  return [...ordered, ...recovered];
}
