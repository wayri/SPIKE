export type Point = [number, number];
export type ParsedTrack = { id: string; start: Point; end: Point; width: number; layer: string; net?: string };
export type ParsedVia = { id: string; at: Point; size: number; drill: number; layers: string[]; net?: string };
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
  bodyBounds?: { minX: number; minY: number; maxX: number; maxY: number };
  courtyardBounds?: { minX: number; minY: number; maxX: number; maxY: number };
  properties?: readonly { name?: unknown; values?: readonly unknown[] }[];
  vendor_properties?: Record<string, unknown>;
  bom_records?: readonly string[];
};
export type ParsedZone = { id: string; points: Point[]; holes?: Point[][]; layer: string; net?: string;
  source_kind?: string; filled_copper_state?: string; source_fill_provenance_complete?: boolean; source_fill_representation?: string };
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
  /** Optional finish color supplied by the source board stackup. */
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
  return layer.name.endsWith(".Cu")
    || COPPER_LAYER_KINDS.has(layer.kind.toLowerCase());
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

type SExpr = string | SExpr[];
type Node = SExpr[];

const EPSILON = 0.015;

function isNode(value: SExpr | undefined): value is Node {
  return Array.isArray(value);
}

function tokenize(source: string): string[] {
  const tokens: string[] = [];
  let current = "";
  let quoted = false;
  let quotedToken = false;
  let escaped = false;
  const flush = () => {
    if (current || quotedToken) tokens.push(current);
    current = "";
    quotedToken = false;
  };

  for (const char of source) {
    if (escaped) {
      current += char;
      escaped = false;
    } else if (quoted && char === "\\") {
      escaped = true;
    } else if (char === "\"") {
      if (!quoted) quotedToken = true;
      quoted = !quoted;
    } else if (quoted) {
      current += char;
    } else if (char === "(" || char === ")") {
      flush();
      tokens.push(char);
    } else if (/\s/.test(char)) {
      flush();
    } else {
      current += char;
    }
  }
  flush();
  return tokens;
}

function parseSExpression(tokens: string[]): Node {
  const root: Node = [];
  const stack: Node[] = [root];
  for (const token of tokens) {
    if (token === "(") {
      const node: Node = [];
      stack[stack.length - 1].push(node);
      stack.push(node);
    } else if (token === ")") {
      if (stack.length > 1) stack.pop();
    } else {
      stack[stack.length - 1].push(token);
    }
  }
  const document = root.find(isNode);
  return document ?? [];
}

function child(node: Node, key: string): Node | undefined {
  return node.find((value): value is Node => isNode(value) && value[0] === key);
}

function children(node: Node, key: string): Node[] {
  return node.filter((value): value is Node => isNode(value) && value[0] === key);
}

function numberAt(node: Node | undefined, index: number, fallback = 0): number {
  const value = Number(node?.[index]);
  return Number.isFinite(value) ? value : fallback;
}

function stringAt(node: Node | undefined, index: number, fallback = ""): string {
  const value = node?.[index];
  return typeof value === "string" ? value : fallback;
}

function pointAt(node: Node | undefined, key: string): Point | undefined {
  const value = node ? child(node, key) : undefined;
  if (!value || value.length < 3) return undefined;
  return [numberAt(value, 1), numberAt(value, 2)];
}

function xyzAt(node: Node | undefined, key: string, fallback: [number, number, number]): [number, number, number] {
  const xyz = child(child(node ?? [], key) ?? [], "xyz");
  if (!xyz) return fallback;
  return [numberAt(xyz, 1, fallback[0]), numberAt(xyz, 2, fallback[1]), numberAt(xyz, 3, fallback[2])];
}

function pointsAt(node: Node | undefined): Point[] {
  const pointsNode = node ? child(node, "pts") : undefined;
  if (!pointsNode) return [];
  return children(pointsNode, "xy").map((value) => [numberAt(value, 1), numberAt(value, 2)]);
}

function nodeId(node: Node, fallback: string): string {
  return stringAt(child(node, "uuid"), 1, fallback);
}

function layerOf(node: Node, fallback = "F.Cu"): string {
  return stringAt(child(node, "layer"), 1, stringAt(child(node, "layers"), 1, fallback));
}

function propertyOf(node: Node, name: string): string {
  return children(node, "property").find((value) => stringAt(value, 1).toLowerCase() === name.toLowerCase())?.[2] as string ?? "";
}

function transformPoint(point: Point, origin: Point, rotation: number, mirrored: boolean): Point {
  const x = mirrored ? -point[0] : point[0];
  const angle = -rotation * Math.PI / 180;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  return [origin[0] + x * cos - point[1] * sin, origin[1] + x * sin + point[1] * cos];
}

function circumcircle(start: Point, middle: Point, end: Point): { center: Point; radius: number; sweep: number; startAngle: number } | null {
  const [x1, y1] = start;
  const [xm, ym] = middle;
  const [x2, y2] = end;
  const determinant = 2 * (x1 * (ym - y2) + xm * (y2 - y1) + x2 * (y1 - ym));
  if (Math.abs(determinant) < 1e-9) return null;
  const centerX = ((x1 * x1 + y1 * y1) * (ym - y2) + (xm * xm + ym * ym) * (y2 - y1) + (x2 * x2 + y2 * y2) * (y1 - ym)) / determinant;
  const centerY = ((x1 * x1 + y1 * y1) * (x2 - xm) + (xm * xm + ym * ym) * (x1 - x2) + (x2 * x2 + y2 * y2) * (xm - x1)) / determinant;
  const startAngle = Math.atan2(y1 - centerY, x1 - centerX);
  const middleAngle = Math.atan2(ym - centerY, xm - centerX);
  const endAngle = Math.atan2(y2 - centerY, x2 - centerX);
  const tau = Math.PI * 2;
  const positive = (value: number) => ((value % tau) + tau) % tau;
  const middleSweep = positive(middleAngle - startAngle);
  const endSweep = positive(endAngle - startAngle);
  const sweep = middleSweep <= endSweep ? endSweep : endSweep - tau;
  return { center: [centerX, centerY], radius: Math.hypot(x1 - centerX, y1 - centerY), sweep, startAngle };
}

function arcPoints(start: Point, middle: Point, end: Point): Point[] {
  const circle = circumcircle(start, middle, end);
  if (!circle) return [start, end];
  const steps = Math.max(8, Math.ceil(Math.abs(circle.sweep) / (Math.PI / 24)));
  return Array.from({ length: steps + 1 }, (_, index) => {
    const angle = circle.startAngle + circle.sweep * index / steps;
    return [circle.center[0] + circle.radius * Math.cos(angle), circle.center[1] + circle.radius * Math.sin(angle)] as Point;
  });
}

function circlePoints(center: Point, end: Point): Point[] {
  const radius = Math.hypot(end[0] - center[0], end[1] - center[1]);
  return Array.from({ length: 65 }, (_, index) => {
    const angle = Math.PI * 2 * index / 64;
    return [center[0] + radius * Math.cos(angle), center[1] + radius * Math.sin(angle)] as Point;
  });
}

function drawingFromNode(node: Node, id: string, transform?: (point: Point) => Point, ref?: string): ParsedDrawing | null {
  const head = stringAt(node, 0);
  const layer = layerOf(node, "Dwgs.User");
  const stroke = child(node, "stroke");
  const width = numberAt(child(stroke ?? node, "width"), 1, 0.12);
  const apply = transform ?? ((point: Point) => point);
  let type: ParsedDrawing["type"];
  let points: Point[];

  if (head.endsWith("_line")) {
    const start = pointAt(node, "start");
    const end = pointAt(node, "end");
    if (!start || !end) return null;
    type = "line";
    points = [apply(start), apply(end)];
  } else if (head.endsWith("_arc")) {
    const start = pointAt(node, "start");
    const middle = pointAt(node, "mid");
    const end = pointAt(node, "end");
    if (!start || !middle || !end) return null;
    type = "arc";
    points = arcPoints(start, middle, end).map(apply);
  } else if (head.endsWith("_circle")) {
    const center = pointAt(node, "center");
    const end = pointAt(node, "end");
    if (!center || !end) return null;
    type = "circle";
    points = circlePoints(center, end).map(apply);
  } else if (head.endsWith("_rect")) {
    const start = pointAt(node, "start");
    const end = pointAt(node, "end");
    if (!start || !end) return null;
    type = "rect";
    points = [
      apply(start),
      apply([end[0], start[1]]),
      apply(end),
      apply([start[0], end[1]]),
      apply(start),
    ];
  } else if (head.endsWith("_poly")) {
    type = "poly";
    points = pointsAt(node).map(apply);
    if (points.length > 2) points.push(points[0]);
  } else {
    return null;
  }
  return { id, type, points, layer, width, ref,
    filled: ["yes", "solid"].includes(stringAt(child(node, "fill"), 1).toLowerCase()) };
}

function closeEnough(a: Point, b: Point): boolean {
  return Math.hypot(a[0] - b[0], a[1] - b[1]) <= EPSILON;
}

function polygonArea(points: Point[]): number {
  let area = 0;
  for (let index = 0; index < points.length - 1; index += 1) {
    area += points[index][0] * points[index + 1][1] - points[index + 1][0] * points[index][1];
  }
  return area / 2;
}

function buildOutlineLoops(drawings: ParsedDrawing[], layerName = "Edge.Cuts"): Point[][] {
  const complete: Point[][] = [];
  const open: Point[][] = [];
  drawings.filter((drawing) => drawing.layer === layerName).forEach((drawing) => {
    const points = drawing.points;
    if (points.length > 2 && closeEnough(points[0], points[points.length - 1])) complete.push(points);
    else if (points.length > 1) open.push([...points]);
  });

  while (open.length) {
    const path = open.shift()!;
    let extended = true;
    while (extended && !closeEnough(path[0], path[path.length - 1])) {
      extended = false;
      for (let index = 0; index < open.length; index += 1) {
        const candidate = open[index];
        if (closeEnough(path[path.length - 1], candidate[0])) {
          path.push(...candidate.slice(1));
        } else if (closeEnough(path[path.length - 1], candidate[candidate.length - 1])) {
          path.push(...candidate.slice(0, -1).reverse());
        } else if (closeEnough(path[0], candidate[candidate.length - 1])) {
          path.unshift(...candidate.slice(0, -1));
        } else if (closeEnough(path[0], candidate[0])) {
          path.unshift(...candidate.slice(1).reverse());
        } else {
          continue;
        }
        open.splice(index, 1);
        extended = true;
        break;
      }
    }
    if (path.length > 2 && closeEnough(path[0], path[path.length - 1])) {
      path[path.length - 1] = path[0];
      complete.push(path);
    }
  }
  return complete.sort((a, b) => Math.abs(polygonArea(b)) - Math.abs(polygonArea(a)));
}

function regionKindForLayer(layer: ParsedLayerDefinition): ParsedBoardRegion["kind"] | "bend" | null {
  const label = `${layer.name} ${layer.userName ?? ""}`.trim().toLowerCase();
  if (/rigid[ ._-]*flex/.test(label)) return null;
  if (/(^|[ ._-])bend(?:[ ._-]|\d|$)/.test(label)) return "bend";
  if (/(^|[ ._-])stiffener(?:[ ._-]|\d|$)/.test(label)) return "stiffener";
  if (/(^|[ ._-])transition(?:[ ._-]|\d|$)/.test(label)) return "transition";
  if (/(^|[ ._-])flex(?:ible)?(?:[ ._-]*(?:region|outline|area))?(?:[ ._-]|\d|$)/.test(label)) return "flex";
  if (/(^|[ ._-])rigid(?:[ ._-]*(?:region|outline|area))?(?:[ ._-]|\d|$)/.test(label)) return "rigid";
  return null;
}

function annotationNumber(label: string, key: "r" | "radius" | "angle" | "a"): number | undefined {
  const expression = key === "r" || key === "radius"
    ? /(?:^|[ _.-])(?:r|radius)\s*=?\s*(-?\d+(?:\.\d+)?)\s*(?:mm)?(?:$|[ _.-])/i
    : /(?:^|[ _.-])(?:a|angle)\s*=?\s*(-?\d+(?:\.\d+)?)\s*(?:deg)?(?:$|[ _.-])/i;
  const value = Number(label.match(expression)?.[1]);
  return Number.isFinite(value) ? value : undefined;
}

function boundsOf(points: Point[]): { minX: number; minY: number; maxX: number; maxY: number } {
  if (!points.length) return { minX: 0, minY: 0, maxX: 100, maxY: 70 };
  const xExtent = numericExtent(points.map(point => point[0]));
  const yExtent = numericExtent(points.map(point => point[1]));
  return { minX: xExtent.minimum, minY: yExtent.minimum, maxX: xExtent.maximum, maxY: yExtent.maximum };
}

export function parseKicadBoard(source: string): ParsedBoard {
  const root = parseSExpression(tokenize(source));
  if (root[0] !== "kicad_pcb") throw new Error("The selected file is not a KiCad PCB document.");

  const tracks: ParsedTrack[] = [];
  const vias: ParsedVia[] = [];
  const pads: ParsedPad[] = [];
  const components: ParsedComponent[] = [];
  const zones: ParsedZone[] = [];
  const drawings: ParsedDrawing[] = [];
  const layers = new Set<string>();
  const layerDefinitions: ParsedLayerDefinition[] = [];
  const stackup: ParsedStackupLayer[] = [];
  const nets: Record<string, string> = {};

  for (const item of root) {
    if (isNode(item) && item[0] === "net") nets[stringAt(item, 1)] = stringAt(item, 2);
  }

  const netName = (node: Node) => {
    const net = child(node, "net");
    const idOrName = stringAt(net, 1);
    const explicit = stringAt(net, 2) || stringAt(child(node, "net_name"), 1);
    const name = explicit || nets[idOrName] || (/^\d+$/.test(idOrName) ? "" : idOrName);
    if (name) nets[idOrName || name] = name;
    return name || undefined;
  };

  for (const item of root) {
    if (!isNode(item) || !item.length) continue;
    const head = stringAt(item, 0);
    if (head === "layers") {
      item.slice(1).filter(isNode).forEach((layer) => {
        const name = stringAt(layer, 1);
        if (name && !name.includes("*")) {
          layerDefinitions.push({
            id: numberAt(layer, 0, layerDefinitions.length),
            name,
            kind: stringAt(layer, 2) || "user",
            userName: stringAt(layer, 3) || undefined,
          });
        }
        if (name.endsWith(".Cu") && !name.includes("*")) layers.add(name);
      });
    } else if (head === "setup") {
      const stackupNode = child(item, "stackup");
      children(stackupNode ?? [], "layer").forEach((stackLayer) => {
        const name = stringAt(stackLayer, 1);
        if (!name) return;
        const thicknessNode = child(stackLayer, "thickness");
        const epsilonNode = child(stackLayer, "epsilon_r");
        const lossNode = child(stackLayer, "loss_tangent");
        stackup.push({
          name,
          type: stringAt(child(stackLayer, "type"), 1, "unknown"),
          color: stringAt(child(stackLayer, "color"), 1) || undefined,
          thickness: thicknessNode ? numberAt(thicknessNode, 1) : undefined,
          material: stringAt(child(stackLayer, "material"), 1) || undefined,
          epsilonR: epsilonNode ? numberAt(epsilonNode, 1) : undefined,
          lossTangent: lossNode ? numberAt(lossNode, 1) : undefined,
        });
        if (name.endsWith(".Cu")) layers.add(name);
      });
    } else if (head === "segment" || head === "arc") {
      const width = numberAt(child(item, "width"), 1, 0.25);
      const layer = layerOf(item);
      const net = netName(item);
      const baseId = nodeId(item, `track-${tracks.length + 1}`);
      const route = head === "arc"
        ? arcPoints(pointAt(item, "start") ?? [0, 0], pointAt(item, "mid") ?? [0, 0], pointAt(item, "end") ?? [0, 0])
        : [pointAt(item, "start"), pointAt(item, "end")].filter(Boolean) as Point[];
      for (let index = 0; index < route.length - 1; index += 1) {
        tracks.push({ id: route.length > 2 ? `${baseId}:${index}` : baseId, start: route[index], end: route[index + 1], width, layer, net });
      }
      layers.add(layer);
    } else if (head === "via") {
      const at = pointAt(item, "at");
      if (!at) continue;
      const viaLayers = child(item, "layers")?.slice(1).filter((value): value is string => typeof value === "string") ?? ["F.Cu", "B.Cu"];
      vias.push({
        id: nodeId(item, `via-${vias.length + 1}`),
        at,
        size: numberAt(child(item, "size"), 1, 0.8),
        drill: numberAt(child(item, "drill"), 1, 0.4),
        layers: viaLayers,
        net: netName(item),
      });
    } else if (head === "zone") {
      const defaultLayer = layerOf(item);
      const polygonNodes = children(item, "filled_polygon");
      // KiCad also stores placement/keepout regions as zone outlines. They
      // carry no copper and must not enter the thermal copper inventory.
      if (!polygonNodes.length && (child(item, "placement") || child(item, "keepout"))) continue;
      const selectedPolygons = polygonNodes.length ? polygonNodes : children(item, "polygon");
      selectedPolygons.forEach((polygon, index) => {
        const points = pointsAt(polygon);
        if (points.length < 3) return;
        const layer = layerOf(polygon, defaultLayer);
        zones.push({ id: `${nodeId(item, `zone-${zones.length + 1}`)}:${index}`, points, layer, net: netName(item),
          source_kind: polygonNodes.length ? "filled_zone" : "zone_outline_unfilled",
          filled_copper_state: polygonNodes.length ? "source_filled" : "unfilled",
          source_fill_provenance_complete: polygonNodes.length > 0,
          source_fill_representation: polygonNodes.length ? "flat_polygon_path" : undefined });
        layers.add(layer);
      });
    } else if (head.startsWith("gr_")) {
      const drawing = drawingFromNode(item, nodeId(item, `drawing-${drawings.length + 1}`));
      if (drawing) drawings.push(drawing);
    } else if (head === "footprint" || head === "module") {
      const origin = pointAt(item, "at") ?? [0, 0];
      const footprintAt = child(item, "at");
      const rotation = numberAt(footprintAt, 3);
      const layer = layerOf(item);
      const mirrored = layer.startsWith("B.");
      const transform = (point: Point) => transformPoint(point, origin, rotation, mirrored);
      const reference = propertyOf(item, "Reference")
        || children(item, "fp_text").find((text) => stringAt(text, 1) === "reference")?.[2] as string
        || `REF${components.length + 1}`;
      const value = propertyOf(item, "Value")
        || children(item, "fp_text").find((text) => stringAt(text, 1) === "value")?.[2] as string
        || "";
      const componentPads: ParsedPad[] = [];
      const localPadPoints: Point[] = [];
      const bodyPoints: Point[] = [];
      const courtyardPoints: Point[] = [];

      children(item, "pad").forEach((padNode, index) => {
        const localAt = pointAt(padNode, "at") ?? [0, 0];
        localPadPoints.push(localAt);
        const size = child(padNode, "size");
        const rawLayers = child(padNode, "layers")?.slice(1).filter((entry): entry is string => typeof entry === "string") ?? [layer];
        const primaryLayer = rawLayers.includes("F.Cu") || rawLayers.includes("*.Cu")
          ? (mirrored ? "B.Cu" : "F.Cu")
          : rawLayers.find((entry) => entry.endsWith(".Cu")) ?? layer;
        const drillNode = child(padNode, "drill");
        const ovalDrill = stringAt(drillNode, 1) === "oval";
        const drill = ovalDrill ? numberAt(drillNode, 2) : numberAt(drillNode, 1);
        const drillHeight = ovalDrill ? numberAt(drillNode, 3, drill) : drill;
        const padKind = stringAt(padNode, 2);
        const width = numberAt(size, 1, 1);
        const height = numberAt(size, 2, 1);
        const pad: ParsedPad = {
          id: nodeId(padNode, `pad-${reference}-${stringAt(padNode, 1, String(index + 1))}`),
          name: stringAt(padNode, 1, String(index + 1)),
          at: transform(localAt),
          width,
          height,
          size: [width, height],
          // KiCad stores the pad position in footprint-local coordinates, but
          // serializes the pad angle in board coordinates.
          rotation: numberAt(child(padNode, "at"), 3),
          shape: stringAt(padNode, 3, "rect"),
          drill,
          drill_size: [drill, drillHeight],
          drill_shape: ovalDrill ? "oval" : "circle",
          type: padKind,
          pad_kind: padKind,
          plated: padKind !== "np_thru_hole",
          roundrect_rratio: numberAt(child(padNode, "roundrect_rratio"), 1, 0),
          layers: rawLayers,
          layer: primaryLayer,
          net: netName(padNode),
          ref: reference,
        };
        pads.push(pad);
        componentPads.push(pad);
        rawLayers.filter((entry) => entry.endsWith(".Cu") && !entry.includes("*")).forEach((entry) => layers.add(entry));
      });

      for (const graphicType of ["fp_line", "fp_arc", "fp_circle", "fp_rect", "fp_poly"]) {
        children(item, graphicType).forEach((graphic, index) => {
          const localDrawing = drawingFromNode(graphic, `${reference}:${graphicType}:${index}:local`, undefined, reference);
          if (localDrawing?.layer.endsWith(".Fab")) bodyPoints.push(...localDrawing.points);
          if (localDrawing?.layer.endsWith(".CrtYd")) courtyardPoints.push(...localDrawing.points);
          const drawing = drawingFromNode(graphic, `${reference}:${graphicType}:${index}`, transform, reference);
          if (drawing) drawings.push(drawing);
        });
      }

      const padBounds = boundsOf(localPadPoints);
      const width = localPadPoints.length ? Math.max(padBounds.maxX - padBounds.minX + 2.5, 2.5) : 5;
      const height = localPadPoints.length ? Math.max(padBounds.maxY - padBounds.minY + 2.5, 2.5) : 5;
      const modelNode = child(item, "model");
      components.push({
        id: nodeId(item, `component-${reference}`),
        ref: reference,
        value,
        library: stringAt(item, 1),
        at: origin,
        width,
        height,
        rotation,
        layer,
        model: Boolean(modelNode),
        modelPath: stringAt(modelNode, 1),
        modelPaths: children(item, "model").map(model => stringAt(model, 1)).filter(Boolean),
        modelOffset: xyzAt(modelNode, "offset", [0, 0, 0]),
        modelScale: xyzAt(modelNode, "scale", [1, 1, 1]),
        modelRotation: xyzAt(modelNode, "rotate", [0, 0, 0]),
        bodyBounds: bodyPoints.length ? boundsOf(bodyPoints) : undefined,
        courtyardBounds: courtyardPoints.length ? boundsOf(courtyardPoints) : undefined,
      });
      layers.add(layer === "B.Cu" ? "B.Cu" : "F.Cu");
    }
  }

  const outlineLoops = buildOutlineLoops(drawings);
  const geometryPoints = outlineLoops[0]
    ?? tracks.flatMap((track) => [track.start, track.end]).concat(pads.map((pad) => pad.at));
  const bounds = boundsOf(geometryPoints);
  const knownLayerNames = new Set(layerDefinitions.map((layer) => layer.name));
  let nextSyntheticLayerId = Math.max(-1, ...layerDefinitions.map(layer => layer.id)) + 1;
  [
    ...tracks.map((track) => track.layer),
    ...pads.flatMap((pad) => pad.layers),
    ...zones.map((zone) => zone.layer),
    ...drawings.map((drawing) => drawing.layer),
  ].forEach((name) => {
    if (!name || name.includes("*") || knownLayerNames.has(name)) return;
    knownLayerNames.add(name);
    layerDefinitions.push({ id: nextSyntheticLayerId++, name, kind: name.endsWith(".Cu") ? "signal" : "user" });
  });
  const copperLayers = orderedCopperLayerNames(layerDefinitions, layers, stackup.map(layer => layer.name));

  const explicitRegions: ParsedBoardRegion[] = [];
  const bendLines: ParsedBendLine[] = [];
  layerDefinitions.forEach((definition) => {
    const kind = regionKindForLayer(definition);
    if (!kind) return;
    const label = definition.userName || definition.name;
    if (kind === "bend") {
      drawings.filter(drawing => drawing.layer === definition.name && drawing.points.length >= 2).forEach((drawing, index) => {
        bendLines.push({
          id: `bend:${drawing.id}`,
          name: `${label} ${index + 1}`,
          points: drawing.points,
          sourceLayer: definition.name,
          radiusMm: annotationNumber(label, "radius"),
          angleDeg: annotationNumber(label, "angle"),
        });
      });
      return;
    }
    buildOutlineLoops(drawings, definition.name).forEach((outline, index) => {
      explicitRegions.push({
        id: `region:${definition.id}:${index}`,
        name: `${label}${index ? ` ${index + 1}` : ""}`,
        kind,
        outline,
        sourceLayer: definition.name,
        source: "kicad-user-layer",
      });
    });
  });
  const outerOutline = outlineLoops[0] ?? [];
  const boardArea = Math.abs(polygonArea(outerOutline));
  const flexArea = explicitRegions.filter(region => region.kind === "flex").reduce((sum, region) => sum + Math.abs(polygonArea(region.outline)), 0);
  const hasFlex = flexArea > 0;
  const hasRigid = explicitRegions.some(region => region.kind === "rigid");
  const technology: ParsedBoard["technology"] = hasFlex
    ? !hasRigid && boardArea > 0 && flexArea >= boardArea * 0.92 ? "flex" : "rigid-flex"
    : "rigid";
  const regions = [...explicitRegions];
  if (outerOutline.length && technology !== "flex" && !regions.some(region => region.kind === "rigid" && Math.abs(polygonArea(region.outline)) >= boardArea * 0.92)) {
    regions.unshift({
      id: "region:implicit-rigid-board",
      name: "Rigid board",
      kind: "rigid",
      outline: outerOutline,
      sourceLayer: "Edge.Cuts",
      source: "implicit-board-outline",
    });
  }

  return {
    width: Math.max(bounds.maxX - bounds.minX, 1),
    height: Math.max(bounds.maxY - bounds.minY, 1),
    bounds,
    outlineLoops,
    tracks,
    vias,
    pads,
    components,
    zones,
    drawings,
    layers: copperLayers,
    layerDefinitions,
    stackup,
    nets,
    technology,
    regions,
    bendLines,
  };
}
import { numericExtent } from "./numericRange";
