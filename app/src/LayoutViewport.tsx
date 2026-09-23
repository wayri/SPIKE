import { memo, useEffect, useMemo, useRef, useState } from "react";
import { ParsedBoard, Point } from "./boardParser";
import type { AnalysisTerminalMarker, BoardObject, HoverProbeTarget, SelectionFilter, ViewportContextRequest, ViewportHoverTarget } from "./BoardViewport";
import type { ResultViewMode, ResultVisualization, ScalarSample, SolverResultBundle } from "./analysisResults";
import { layerCssColor } from "./layerPalette";
import { thermalVolume, ThermalScenarioView, ThermalSceneVisibility } from "./thermalScene";
import { numericExtent, numericMaximum } from "./numericRange";
import { resolveBoardCopperLayers } from "./copperLayerSelection";
import { solverResultOverlayActive } from "./viewportScenePolicy";
import { meshCellFaceVertices } from "./meshTopology";
import { spatiallyThinSamples, viewportResultField } from "./viewportResultFields";
import { pointOnResultConductor, resultDatumFitsConductor, resultFaceTriangleIndices } from "./resultGeometryMask";
import { buildScalarSvgBatches } from "./resultSvgBatches";
import { smoothDisplaySamples } from "./resultSurfaceInterpolation";
import { resultDatumLayers, resultLayerIsVisible, resultLayerWithVisibleData } from "./resultLayerSelection";
import type { Viewport2DState, ViewportRestoreCommand } from "./workspaceState";
import { buildBoundsSpatialIndex, pointBoundsCandidates, type BoundsSpatialIndex, type SpatialBounds } from "./viewportSpatialIndex";
import { finiteFocusBounds, focusViewBox, type FocusBounds2D } from "./viewportFocus";

import { copperNetLabels } from "./viewportPerformance";

type ViewBox = { x: number; y: number; width: number; height: number };
type NativeLayerGeometry = { zones: string; tracks: { width: number; path: string }[]; pads: string; vias: string; drawings: { width: number; path: string }[] };
type LayoutPickFeature =
  | { kind: "component"; index: number }
  | { kind: "pad"; index: number }
  | { kind: "via"; index: number }
  | { kind: "track"; index: number }
  | { kind: "zone"; index: number };

type LayoutFeatureLabel = { id: string; text: string; title: string; kind: string; x: number; y: number; angle: number; fontSize: number };

/** Screen-space budget shared by pad numbers, pin nets, tracks and zones. */
function layoutFeatureAnnotations(
  board: ParsedBoard,
  view: { minX: number; minY: number; maxX: number; maxY: number; unitsPerPixel: number },
  visibleLayers: Record<string, boolean>, activeLayer: string, isolatedNet: string | null,
  showNetNames: boolean, copperLabels: ReturnType<typeof copperNetLabels>,
) {
  const labels: LayoutFeatureLabel[] = [], pinOne: Point[] = [];
  const unit = view.unitsPerPixel;
  if (!(unit > 0) || !Number.isFinite(unit)) return { labels, pinOne };
  const occupied = new Map<string, { x: number; y: number; w: number; h: number }[]>();
  const cell = unit * 48;
  const add = (label: LayoutFeatureLabel) => {
    if (labels.length >= 600) return;
    const width = label.fontSize * (label.text.length * 0.65 + 1), height = label.fontSize * 1.2;
    const angle = label.angle * Math.PI / 180;
    const w = Math.abs(Math.cos(angle)) * width + Math.abs(Math.sin(angle)) * height;
    const h = Math.abs(Math.sin(angle)) * width + Math.abs(Math.cos(angle)) * height;
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
    for (const key of keys) { const entries = occupied.get(key); if (entries) entries.push(box); else occupied.set(key, [box]); }
    labels.push(label);
  };
  // Linear scan, early viewport rejection, then constant-sized collision buckets.
  // All visible pin-one markers are batched into one path, independent of text budget.
  for (const pad of board.pads) {
    const [x, y] = pad.at;
    if (x < view.minX || y < view.minY || x > view.maxX || y > view.maxY || isolatedNet && pad.net !== isolatedNet) continue;
    if (!resolveBoardCopperLayers(board.layers, pad.layers).some(layer => visibleLayers[layer] !== false && (activeLayer === "All" || layer === activeLayer))) continue;
    if (pad.ref && /^(?:0*1|A0*1)$/i.test(pad.name.trim())) pinOne.push(pad.at);
    if (!pad.name || labels.length >= 600) continue;
    const long = Math.max(pad.width, pad.height), short = Math.min(pad.width, pad.height);
    const fontFor = (text: string) => Math.min(unit * 11, short * 0.72, long / (text.length * 0.65 + 1));
    let text = pad.name;
    const combined = `${pad.name} \u00b7 ${pad.net ?? ""}`;
    if (showNetNames && pad.net && pad.net.length <= 160 && fontFor(combined) >= unit * 8) text = combined;
    const fontSize = fontFor(text);
    if (fontSize < unit * 7) continue;
    let angle = pad.rotation + (pad.height > pad.width ? 90 : 0);
    angle = ((angle + 90) % 180 + 180) % 180 - 90;
    add({ id: pad.id, kind: "pad", text, title: `${pad.ref ?? ""}.${pad.name}${pad.net ? `: ${pad.net}` : ""}`, x, y, angle, fontSize });
  }
  for (const label of copperLabels) add({ ...label, text: label.net, title: label.net });
  return { labels, pinOne };
}

function scalarSamplesForMode(result: SolverResultBundle | null | undefined, mode: ResultViewMode): ScalarSample[] {
  if (!result) return [];
  if (mode === "voltage") return result.scalar_fields.voltage_v;
  if (mode === "voltage_drop") return result.scalar_fields.voltage_drop_v;
  if (mode === "current") return result.scalar_fields.current_a;
  if (mode === "current_density") return result.scalar_fields.current_density_a_mm2;
  if (mode === "power_loss") return result.scalar_fields.power_loss_w;
  if (mode === "via_stress") return result.scalar_fields.via_current_density_a_mm2;
  if (mode === "impedance") return result.scalar_fields.operating_point_impedance_ohm;
  if (mode === "electric_field") return result.vector_fields.electric_field;
  if (mode === "magnetic_field") return result.vector_fields.magnetic_field;
  return [];
}
type Props = {
  board: ParsedBoard;
  visibleLayers: Record<string, boolean>;
  layerOpacity: Record<string, number>;
  showVias?: boolean;
  showNetNames?: boolean;
  selectedId: string | null;
  selectedPosition?: Point;
  selectedNet?: string | null;
  hoverPreview?: ViewportHoverTarget | null;
  isolatedNet?: string | null;
  analysisResult?: SolverResultBundle | null;
  resultVisualization?: ResultVisualization;
  analysisNets?: string[];
  probes?: BoardObject[];
  showProbes?: boolean;
  hoverProbeEnabled?: boolean;
  onHoverProbe?: (target: HoverProbeTarget | null) => void;
  terminalMarkers?: AnalysisTerminalMarker[];
  thermalScenario?: ThermalScenarioView | null;
  thermalVisibility?: ThermalSceneVisibility;
  translucentScene?: boolean;
  showAxes?: boolean;
  cameraCommand: string;
  viewportRestore?: ViewportRestoreCommand | null;
  onViewChange?: (view: Viewport2DState) => void;
  selectionBlink?: boolean;
  selectionFilter: SelectionFilter;
  onSelect: (object: BoardObject) => void;
  onContextMenu?: (request: ViewportContextRequest) => void;
};

const baseLayerOpacity: Record<string, number> = {
  "F.Cu": 1,
  "In1.Cu": 1,
  "In2.Cu": 1,
  "B.Cu": 1,
  "F.SilkS": 0.94,
  "B.SilkS": 0.45,
};

function distanceToSegment(point: Point, start: Point, end: Point) {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const lengthSquared = dx * dx + dy * dy;
  if (!lengthSquared) return Math.hypot(point[0] - start[0], point[1] - start[1]);
  const t = Math.max(0, Math.min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / lengthSquared));
  return Math.hypot(point[0] - (start[0] + t * dx), point[1] - (start[1] + t * dy));
}

function distanceToRotatedRect(point: Point, center: Point, width: number, height: number, rotationDeg: number) {
  const angle = -rotationDeg * Math.PI / 180;
  const dx = point[0] - center[0];
  const dy = point[1] - center[1];
  const localX = dx * Math.cos(angle) - dy * Math.sin(angle);
  const localY = dx * Math.sin(angle) + dy * Math.cos(angle);
  const outsideX = Math.max(Math.abs(localX) - width / 2, 0);
  const outsideY = Math.max(Math.abs(localY) - height / 2, 0);
  return Math.hypot(outsideX, outsideY);
}

function pointInPolygon(point: Point, polygon: Point[]) {
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index++) {
    const currentPoint = polygon[index];
    const previousPoint = polygon[previous];
    const denominator = previousPoint[1] - currentPoint[1] || Number.EPSILON;
    const intersects = (currentPoint[1] > point[1]) !== (previousPoint[1] > point[1])
      && point[0] < (previousPoint[0] - currentPoint[0]) * (point[1] - currentPoint[1]) / denominator + currentPoint[0];
    if (intersects) inside = !inside;
  }
  return inside;
}

function trackCoveredByZones(track: ParsedBoard["tracks"][number], zones: ParsedBoard["zones"]): boolean {
  const matchingZones = zones.filter(zone => zone.layer === track.layer && zone.net === track.net);
  if (!matchingZones.length) return false;
  // Sampling avoids exposing route outlines that are already part of a same-net pour,
  // while retaining any segment that crosses a void or leaves the copper zone.
  const coverage = Array.from({ length: 9 }, (_, index) => index / 8).filter(t => {
    const point: Point = [
      track.start[0] + (track.end[0] - track.start[0]) * t,
      track.start[1] + (track.end[1] - track.start[1]) * t,
    ];
    return matchingZones.some(zone => pointInPolygon(point, zone.points));
  }).length;
  // KiCad commonly retains route segments under a same-net filled zone. Drawing
  // those segments again produces long bars that are not visible copper edges.
  return coverage >= 5;
}

function LayoutViewport({ board, visibleLayers, layerOpacity, showVias = true, showNetNames = false, selectedId, selectedPosition, selectedNet = null, hoverPreview = null, isolatedNet = null, analysisResult = null, resultVisualization, analysisNets = [], probes = [], showProbes = true, hoverProbeEnabled = false, onHoverProbe, terminalMarkers = [], thermalScenario = null, thermalVisibility = { volume: true, heatSources: true, airflow: true, hardware: true }, translucentScene = false, showAxes = true, cameraCommand, viewportRestore = null, onViewChange, selectionBlink = true, selectionFilter, onSelect, onContextMenu }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef({ x: 0, y: 0, moved: false });
  const draggingRef = useRef(false);
  const dragPanFrameRef = useRef(0);
  const dragPanDeltaRef = useRef({ x: 0, y: 0, width: 1, height: 1 });
  const lastHoverProbeRef = useRef(0);
  const sourceViewBox = board.layoutViewBox ?? [0, 0, board.width, board.height];
  const initialView = useMemo<ViewBox>(() => ({
    x: sourceViewBox[0],
    y: sourceViewBox[1],
    width: sourceViewBox[2],
    height: sourceViewBox[3],
  }), [sourceViewBox.join(":")]);
  const [view, setView] = useState(initialView);
  const [pixelSize, setPixelSize] = useState({ width: 1000, height: 700 });
  useEffect(() => {
    const element = svgRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0 && entry.contentRect.height > 0)
        setPixelSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const [dragging, setDragging] = useState(false);
  const availableCopperLayers = useMemo(() => [...board.layers], [board]);
  const drawableLayers = useMemo(() => [...new Set([...board.layerDefinitions.map(layer => layer.name), ...board.layers, ...board.drawings.map(drawing => drawing.layer)])], [board]);
  const anyLayerVisible = drawableLayers.some(layer => visibleLayers[layer] !== false);
  const viasOnlyActive = showVias && !anyLayerVisible;
  const [failedLayerUrls, setFailedLayerUrls] = useState<Set<string>>(() => new Set());
  const plottedLayerAvailable = (layer: string) => {
    const url = board.layoutLayerUrls?.[layer];
    return Boolean(url && !failedLayerUrls.has(url) && (showVias || !availableCopperLayers.includes(layer)));
  };
  const copperLayerColors = useMemo(
    () => Object.fromEntries(availableCopperLayers.map((layer, index) => [layer, layerCssColor(layer, index)])),
    [availableCopperLayers],
  );
  const [activeCopperLayer, setActiveCopperLayer] = useState("All");
  const [layerPickerExpanded, setLayerPickerExpanded] = useState(false);
  const selectionPulseClass = !selectionBlink || solverResultOverlayActive(analysisResult, resultVisualization)
    ? undefined
    : "viewport-selection-pulse";
  const resultsOnlyScene = resultVisualization?.sceneMode === "results_only";
  const layersContainCopper = (entries: string[], target: string) => {
    const resolved = resolveBoardCopperLayers(availableCopperLayers, entries);
    return target === "All" || target === "Overview" ? resolved.length > 0 : resolved.includes(target);
  };
  const viaCopperLayers = (entries: string[]) => {
    const indices = resolveBoardCopperLayers(availableCopperLayers, entries).map(layer => availableCopperLayers.indexOf(layer));
    const extent = numericExtent(indices);
    return extent.count ? availableCopperLayers.slice(extent.minimum, extent.maximum + 1) : [];
  };
  const activeLayerMatches = (layer: string, layers?: string[]) => (layers ? resolveBoardCopperLayers(availableCopperLayers, layers) : [layer])
    .some(candidate => visibleLayers[candidate] !== false && (activeCopperLayer === "All" || activeCopperLayer === "Overview" || candidate === activeCopperLayer));

  const zoomAt = (clientX: number, clientY: number, rect: DOMRect, zoomIn: boolean) => {
    setView(current => {
      const scale = Math.min(rect.width / current.width, rect.height / current.height);
      const offsetX = (rect.width - current.width * scale) / 2;
      const offsetY = (rect.height - current.height * scale) / 2;
      const cursorX = current.x + (clientX - rect.left - offsetX) / scale;
      const cursorY = current.y + (clientY - rect.top - offsetY) / scale;
      const factor = zoomIn ? 0.82 : 1.22;
      const width = Math.max(Math.max(0.05, sourceViewBox[2] * 0.0005), Math.min(sourceViewBox[2] * 4, current.width * factor));
      const height = width * sourceViewBox[3] / sourceViewBox[2];
      const ratioX = (cursorX - current.x) / current.width;
      const ratioY = (cursorY - current.y) / current.height;
      return { x: cursorX - ratioX * width, y: cursorY - ratioY * height, width, height };
    });
  };
  const beginPan = (event: React.PointerEvent<SVGSVGElement | HTMLDivElement>) => {
    if (event.button === 2) return;
    event.preventDefault();
    event.stopPropagation();
    dragRef.current = { x: event.clientX, y: event.clientY, moved: false };
    draggingRef.current = true;
    setDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const continuePan = (event: React.PointerEvent<SVGSVGElement | HTMLDivElement>) => {
    if (!draggingRef.current) return;
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const dx = event.clientX - dragRef.current.x;
    const dy = event.clientY - dragRef.current.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) dragRef.current.moved = true;
    dragRef.current.x = event.clientX;
    dragRef.current.y = event.clientY;
    dragPanDeltaRef.current.x += dx;
    dragPanDeltaRef.current.y += dy;
    dragPanDeltaRef.current.width = Math.max(rect.width, 1);
    dragPanDeltaRef.current.height = Math.max(rect.height, 1);
    if (!dragPanFrameRef.current) dragPanFrameRef.current = requestAnimationFrame(() => {
      dragPanFrameRef.current = 0;
      const delta = dragPanDeltaRef.current;
      dragPanDeltaRef.current = { x: 0, y: 0, width: delta.width, height: delta.height };
      setView(current => {
        const unitsPerPixel = Math.max(current.width / delta.width, current.height / delta.height);
        return { ...current, x: current.x - delta.x * unitsPerPixel, y: current.y - delta.y * unitsPerPixel };
      });
    });
  };
  const endPan = (event: React.PointerEvent<SVGSVGElement | HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    draggingRef.current = false;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    return dragRef.current.moved;
  };

  useEffect(() => setView(initialView), [initialView]);
  useEffect(() => {
    const restored = viewportRestore?.twoD;
    if (!restored) return;
    setView({ x: restored.x, y: restored.y, width: restored.width, height: restored.height });
  }, [viewportRestore?.token, initialView]);
  useEffect(() => {
    onViewChange?.({ contract: "spike/layout-view/v1", ...view });
  }, [view, onViewChange]);
  useEffect(() => () => cancelAnimationFrame(dragPanFrameRef.current), []);
  useEffect(() => {
    if (!cameraCommand) return;
    if (cameraCommand.startsWith("fit")) {
      setView(initialView);
      return;
    }
    if (cameraCommand.startsWith("pan-")) {
      setView(current => {
        const xStep = current.width * 0.08;
        const yStep = current.height * 0.08;
        return {
          ...current,
          x: current.x + (cameraCommand.startsWith("pan-left") ? -xStep : cameraCommand.startsWith("pan-right") ? xStep : 0),
          y: current.y + (cameraCommand.startsWith("pan-up") ? -yStep : cameraCommand.startsWith("pan-down") ? yStep : 0),
        };
      });
      return;
    }
    if (!cameraCommand.startsWith("zoom-")) return;
    setView(current => {
      const factor = cameraCommand.startsWith("zoom-in") ? 0.8 : 1.25;
      const width = Math.max(Math.max(0.05, sourceViewBox[2] * 0.0005), Math.min(sourceViewBox[2] * 4, current.width * factor));
      const height = width * sourceViewBox[3] / sourceViewBox[2];
      return {
        x: current.x + (current.width - width) / 2,
        y: current.y + (current.height - height) / 2,
        width,
        height,
      };
    });
  }, [cameraCommand, initialView]);

  const marginX = (sourceViewBox[2] - board.width) / 2;
  const marginY = (sourceViewBox[3] - board.height) / 2;
  const toLayout = (point: Point): Point => [
    sourceViewBox[0] + marginX + point[0] - board.bounds.minX,
    sourceViewBox[1] + marginY + point[1] - board.bounds.minY,
  ];
  const toBoard = (point: Point): Point => [
    board.bounds.minX + point[0] - sourceViewBox[0] - marginX,
    board.bounds.minY + point[1] - sourceViewBox[1] - marginY,
  ];
  const layoutPickIndex = useMemo<BoundsSpatialIndex<LayoutPickFeature>>(() => {
    const project = (point: Point): Point => [
      sourceViewBox[0] + marginX + point[0] - board.bounds.minX,
      sourceViewBox[1] + marginY + point[1] - board.bounds.minY,
    ];
    const records: SpatialBounds<LayoutPickFeature>[] = [];
    board.components.forEach((component, index) => {
      const center = project(component.at);
      const radius = Math.hypot(component.width, component.height) / 2;
      records.push({ value: { kind: "component", index }, minX: center[0] - radius, maxX: center[0] + radius, minY: center[1] - radius, maxY: center[1] + radius, minZ: 0, maxZ: 0 });
    });
    board.pads.forEach((pad, index) => {
      const center = project(pad.at);
      const radius = Math.hypot(pad.width, pad.height) / 2;
      records.push({ value: { kind: "pad", index }, minX: center[0] - radius, maxX: center[0] + radius, minY: center[1] - radius, maxY: center[1] + radius, minZ: 0, maxZ: 0 });
    });
    board.vias.forEach((via, index) => {
      const center = project(via.at);
      const radius = via.size / 2;
      records.push({ value: { kind: "via", index }, minX: center[0] - radius, maxX: center[0] + radius, minY: center[1] - radius, maxY: center[1] + radius, minZ: 0, maxZ: 0 });
    });
    board.tracks.forEach((track, index) => {
      const start = project(track.start);
      const end = project(track.end);
      const radius = track.width / 2;
      records.push({ value: { kind: "track", index }, minX: Math.min(start[0], end[0]) - radius, maxX: Math.max(start[0], end[0]) + radius, minY: Math.min(start[1], end[1]) - radius, maxY: Math.max(start[1], end[1]) + radius, minZ: 0, maxZ: 0 });
    });
    board.zones.forEach((zone, index) => {
      if (!zone.points.length) return;
      let minX = Infinity; let maxX = -Infinity; let minY = Infinity; let maxY = -Infinity;
      for (const point of zone.points) {
        const projected = project(point);
        minX = Math.min(minX, projected[0]); maxX = Math.max(maxX, projected[0]);
        minY = Math.min(minY, projected[1]); maxY = Math.max(maxY, projected[1]);
      }
      records.push({ value: { kind: "zone", index }, minX, maxX, minY, maxY, minZ: 0, maxZ: 0 });
    });
    return buildBoundsSpatialIndex(records);
  }, [board, sourceViewBox.join(":"), marginX, marginY]);
  const nativeLayerGeometry = useMemo<Record<string, NativeLayerGeometry>>(() => {
    const project = (point: Point): Point => [
      sourceViewBox[0] + marginX + point[0] - board.bounds.minX,
      sourceViewBox[1] + marginY + point[1] - board.bounds.minY,
    ];
    const ellipsePath = (center: Point, radiusX: number, radiusY: number) => {
      const [x, y] = center;
      return `M${x - radiusX},${y}a${radiusX},${radiusY} 0 1,0 ${radiusX * 2},0a${radiusX},${radiusY} 0 1,0 ${-radiusX * 2},0Z`;
    };
    const rotatePoint = (point: Point, center: Point, degrees: number): Point => {
      const radians = degrees * Math.PI / 180;
      const dx = point[0] - center[0];
      const dy = point[1] - center[1];
      return [center[0] + dx * Math.cos(radians) - dy * Math.sin(radians), center[1] + dx * Math.sin(radians) + dy * Math.cos(radians)];
    };
    return Object.fromEntries(drawableLayers.map(layer => {
      const zones = board.zones.filter(item => item.layer === layer && item.points.length >= 3).map(item =>
        [item.points, ...(item.holes ?? [])].map(ring => `${ring.map((point, index) => { const [x, y] = project(point); return `${index ? "L" : "M"}${x},${y}`; }).join(" ")}Z`).join(" "),
      ).join(" ");
      const trackGroups = new Map<string, { width: number; paths: string[] }>();
      board.tracks.filter(item => item.layer === layer).forEach(track => {
        const widthKey = track.width.toFixed(4);
        const group = trackGroups.get(widthKey) ?? { width: track.width, paths: [] };
        const start = project(track.start);
        const end = project(track.end);
        group.paths.push(`M${start[0]},${start[1]}L${end[0]},${end[1]}`);
        trackGroups.set(widthKey, group);
      });
      const pads = board.pads.filter(item => availableCopperLayers.includes(layer) ? layersContainCopper(item.layers, layer)
        : item.layers.includes(layer) || /^[FB]\./.test(layer) && item.layers.includes(`*.${layer.slice(2)}`)).map(pad => {
        const center = project(pad.at);
        let path = "";
        if (pad.customPolygon && pad.customPolygon.length >= 3) {
          const perimeter = pad.customPolygon.map(([x, y]) => rotatePoint([center[0] + x, center[1] + y], center, pad.rotation));
          path = `${perimeter.map((point, index) => `${index ? "L" : "M"}${point[0]},${point[1]}`).join(" ")}Z`;
        } else if (pad.shape === "circle" || pad.shape === "oval" || pad.shape === "ellipse") {
          const perimeter = Array.from({ length: 20 }, (_, index): Point => {
            const angle = index / 20 * Math.PI * 2;
            return rotatePoint([
              center[0] + Math.cos(angle) * pad.width / 2,
              center[1] + Math.sin(angle) * pad.height / 2,
            ], center, pad.rotation);
          });
          path = `${perimeter.map((point, index) => `${index ? "L" : "M"}${point[0]},${point[1]}`).join(" ")}Z`;
        } else {
          const corners = ([
            [center[0] - pad.width / 2, center[1] - pad.height / 2],
            [center[0] + pad.width / 2, center[1] - pad.height / 2],
            [center[0] + pad.width / 2, center[1] + pad.height / 2],
            [center[0] - pad.width / 2, center[1] + pad.height / 2],
          ] as Point[]).map(point => rotatePoint(point, center, pad.rotation));
          path = `${corners.map((point, index) => `${index ? "L" : "M"}${point[0]},${point[1]}`).join(" ")}Z`;
        }
        return pad.drill > 0 ? `${path}${ellipsePath(center, pad.drill / 2, pad.drill / 2)}` : path;
      }).join(" ");
      const vias = availableCopperLayers.includes(layer) ? board.vias.filter(item => viaCopperLayers(item.layers).includes(layer)).map(via => {
        const center = project(via.at);
        return `${ellipsePath(center, via.size / 2, via.size / 2)}${ellipsePath(center, via.drill / 2, via.drill / 2)}`;
      }).join(" ") : "";
      const drawings = board.drawings.filter(item => item.layer === layer && item.points.length > 1).map(item => ({
        width: Math.max(item.width, 0.01),
        path: item.points.map((point, index) => { const [x, y] = project(point); return `${index ? "L" : "M"}${x},${y}`; }).join(" "),
      }));
      return [layer, {
        zones,
        tracks: [...trackGroups.values()].map(group => ({ width: group.width, path: group.paths.join(" ") })),
        pads,
        vias,
        drawings,
      }];
    }));
  }, [board, drawableLayers.join(":"), sourceViewBox.join(":"), marginX, marginY]);
  const clientToLayout = (clientX: number, clientY: number, rect: DOMRect): Point => {
    const scale = Math.min(rect.width / Math.max(view.width, 1), rect.height / Math.max(view.height, 1));
    const renderedWidth = view.width * scale;
    const renderedHeight = view.height * scale;
    const offsetX = (rect.width - renderedWidth) / 2;
    const offsetY = (rect.height - renderedHeight) / 2;
    return [
      view.x + (clientX - rect.left - offsetX) / Math.max(scale, Number.EPSILON),
      view.y + (clientY - rect.top - offsetY) / Math.max(scale, Number.EPSILON),
    ];
  };
  const pointerInLayout = (event: React.PointerEvent<SVGSVGElement>): Point => {
    const matrix = event.currentTarget.getScreenCTM();
    if (matrix) {
      const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
      return [point.x, point.y];
    }
    return clientToLayout(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect());
  };
  const objectAt = (layoutPoint: Point, ignoreSelectionFilter = false) => {
    const point = layoutPoint;
    const activeFilter: SelectionFilter = ignoreSelectionFilter ? "all" : selectionFilter;
    const rect = svgRef.current?.getBoundingClientRect();
    const unitsPerPixel = rect
      ? Math.max(view.width / Math.max(rect.width, 1), view.height / Math.max(rect.height, 1))
      : view.width / 1000;
    const threshold = Math.max(unitsPerPixel * 6, 0.035);
    const candidates: { distance: number; priority: number; object: BoardObject }[] = [];
    const broadPhase = pointBoundsCandidates(layoutPickIndex, point[0], point[1], threshold);
    for (const feature of broadPhase.values) {
      if (feature.kind === "component") {
        if (activeFilter === "net" || isolatedNet) continue;
        const component = board.components[feature.index];
        candidates.push({
          distance: distanceToRotatedRect(point, toLayout(component.at), component.width, component.height, component.rotation),
          priority: 1,
          object: { id: component.id, type: "component", name: component.value ? `${component.ref} ${component.value}` : component.ref, ref: component.ref, layer: component.layer, model: true, position: component.at },
        });
        continue;
      }
      if (activeFilter === "part") continue;
      if (feature.kind === "pad") {
        const pad = board.pads[feature.index];
        if (!activeLayerMatches(pad.layer, pad.layers) || (isolatedNet && pad.net !== isolatedNet)) continue;
        candidates.push({
          distance: distanceToRotatedRect(point, toLayout(pad.at), pad.width, pad.height, pad.rotation),
          priority: 5,
          object: { id: pad.id, type: "pad", name: `${pad.ref ?? ""}.${pad.name}`.replace(/^\./, ""), ref: pad.ref, net: pad.net, layer: pad.layer, position: pad.at },
        });
      } else if (feature.kind === "via") {
        const via = board.vias[feature.index];
        if (!showVias || !viasOnlyActive && !activeLayerMatches("through", viaCopperLayers(via.layers)) || (isolatedNet && via.net !== isolatedNet)) continue;
        const center = toLayout(via.at);
        candidates.push({
          distance: Math.max(0, Math.hypot(point[0] - center[0], point[1] - center[1]) - via.size / 2),
          priority: 6,
          object: { id: via.id, type: "via", name: via.net || via.id, net: via.net, layer: "through", position: via.at },
        });
      } else if (feature.kind === "track") {
        const track = board.tracks[feature.index];
        if (!activeLayerMatches(track.layer) || (isolatedNet && track.net !== isolatedNet)) continue;
        candidates.push({
          distance: Math.max(0, distanceToSegment(point, toLayout(track.start), toLayout(track.end)) - track.width / 2),
          priority: 4,
          object: { id: track.id, type: "trace", name: track.net || track.id, net: track.net, layer: track.layer, position: [(track.start[0] + track.end[0]) / 2, (track.start[1] + track.end[1]) / 2] },
        });
      } else {
        const zone = board.zones[feature.index];
        if (!activeLayerMatches(zone.layer) || (isolatedNet && zone.net !== isolatedNet)) continue;
        const points = zone.points.map(toLayout);
        let distance = pointInPolygon(point, points) ? 0 : Number.POSITIVE_INFINITY;
        if (distance !== 0) for (let index = 0; index < points.length; index += 1) {
          distance = Math.min(distance, distanceToSegment(point, points[index], points[(index + 1) % points.length]));
        }
        candidates.push({
          distance,
          priority: 2,
          object: { id: zone.id, type: "zone", name: zone.net || zone.id, net: zone.net, layer: zone.layer, position: zone.points.length ? [zone.points.reduce((sum, value) => sum + value[0], 0) / zone.points.length, zone.points.reduce((sum, value) => sum + value[1], 0) / zone.points.length] : undefined },
        });
      }
    }
    if (svgRef.current) svgRef.current.dataset.pickBroadphase = `inspected=${broadPhase.inspected};total=${layoutPickIndex.all.length};candidates=${broadPhase.values.length}`;
    const hit = candidates
      .filter(candidate => candidate.distance <= threshold)
      .sort((a, b) => a.distance - b.distance || b.priority - a.priority)[0];
    return hit ? { ...hit.object, position: toBoard(point) } : null;
  };
  const selectAt = (layoutPoint: Point) => {
    const object = objectAt(layoutPoint);
    if (object) onSelect(object);
    return object;
  };
  const updateHoverProbe = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!hoverProbeEnabled || event.buttons !== 0) {
      onHoverProbe?.(null);
      return;
    }
    const now = performance.now();
    if (now - lastHoverProbeRef.current < 30) return;
    lastHoverProbeRef.current = now;
    const layoutPoint = pointerInLayout(event);
    const object = objectAt(layoutPoint, true);
    onHoverProbe?.({ clientX: event.clientX, clientY: event.clientY, position: toBoard(layoutPoint), object });
  };

  useEffect(() => {
    if (!hoverProbeEnabled) onHoverProbe?.(null);
    return () => onHoverProbe?.(null);
  }, [hoverProbeEnabled, onHoverProbe]);

  const selectedPoint = useMemo(() => {
    if (selectedPosition) return toLayout(selectedPosition);
    if (!selectedId) return null;
    const component = board.components.find(item => item.id === selectedId);
    if (component) return toLayout(component.at);
    const pad = board.pads.find(item => item.id === selectedId);
    if (pad) return toLayout(pad.at);
    const via = board.vias.find(item => item.id === selectedId);
    if (via) return toLayout(via.at);
    const track = board.tracks.find(item => item.id === selectedId);
    if (track) return toLayout([(track.start[0] + track.end[0]) / 2, (track.start[1] + track.end[1]) / 2]);
    const zone = board.zones.find(item => item.id === selectedId);
    if (!zone?.points.length) return null;
    return toLayout([
      zone.points.reduce((sum, point) => sum + point[0], 0) / zone.points.length,
      zone.points.reduce((sum, point) => sum + point[1], 0) / zone.points.length,
    ]);
  }, [board, selectedId, selectedPosition, initialView]);
  const selectedFocusBounds = useMemo<FocusBounds2D | null>(() => {
    if (!selectedId) return null;
    const component = board.components.find(item => item.id === selectedId);
    if (component) {
      const point = toLayout(component.at);
      return finiteFocusBounds({ minX: point[0] - component.width / 2, minY: point[1] - component.height / 2, maxX: point[0] + component.width / 2, maxY: point[1] + component.height / 2 });
    }
    const pad = board.pads.find(item => item.id === selectedId);
    if (pad) {
      const point = toLayout(pad.at);
      return finiteFocusBounds({ minX: point[0] - pad.width / 2, minY: point[1] - pad.height / 2, maxX: point[0] + pad.width / 2, maxY: point[1] + pad.height / 2 });
    }
    const via = board.vias.find(item => item.id === selectedId);
    if (via) {
      const point = toLayout(via.at);
      return finiteFocusBounds({ minX: point[0] - via.size / 2, minY: point[1] - via.size / 2, maxX: point[0] + via.size / 2, maxY: point[1] + via.size / 2 });
    }
    const track = board.tracks.find(item => item.id === selectedId);
    if (track) {
      const start = toLayout(track.start); const end = toLayout(track.end); const pad = track.width / 2;
      return finiteFocusBounds({ minX: Math.min(start[0], end[0]) - pad, minY: Math.min(start[1], end[1]) - pad, maxX: Math.max(start[0], end[0]) + pad, maxY: Math.max(start[1], end[1]) + pad });
    }
    const zone = board.zones.find(item => item.id === selectedId);
    if (!zone?.points.length) return null;
    const bounds = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
    for (const sourcePoint of zone.points) {
      const point = toLayout(sourcePoint);
      bounds.minX = Math.min(bounds.minX, point[0]); bounds.minY = Math.min(bounds.minY, point[1]);
      bounds.maxX = Math.max(bounds.maxX, point[0]); bounds.maxY = Math.max(bounds.maxY, point[1]);
    }
    return finiteFocusBounds(bounds);
  }, [board, selectedId, sourceViewBox.join(":")]);
  const lastSelectionFocusCommand = useRef("");
  useEffect(() => {
    if (!cameraCommand.startsWith("focus-selection") || lastSelectionFocusCommand.current === cameraCommand) return;
    lastSelectionFocusCommand.current = cameraCommand;
    const focused = focusViewBox(
      selectedFocusBounds,
      selectedPosition ? toLayout(selectedPosition) : selectedPoint,
      { minX: sourceViewBox[0], minY: sourceViewBox[1], maxX: sourceViewBox[0] + sourceViewBox[2], maxY: sourceViewBox[1] + sourceViewBox[3] },
      sourceViewBox[2] / Math.max(sourceViewBox[3], Number.EPSILON),
    );
    if (focused) setView(focused);
  }, [cameraCommand, selectedFocusBounds, selectedPoint, selectedPosition, sourceViewBox.join(":")]);
  const selectedComponent = selectedId ? board.components.find(item => item.id === selectedId) : undefined;

  const projectionKey = `${sourceViewBox.join(":")}|${marginX}|${marginY}`;
  const boardPath = useMemo(() => board.outlineLoops.map(loop => loop.map((point, index) => {
    const [x, y] = toLayout(point);
    return `${index ? "L" : "M"}${x},${y}`;
  }).join(" ") + " Z").join(" "), [board, projectionKey]);
  const highlightedNet = isolatedNet ?? selectedNet;
  const resultFieldActive = solverResultOverlayActive(analysisResult, resultVisualization);
  const netSets = useMemo(() => ({
    tracks: highlightedNet ? board.tracks.filter(item => item.net === highlightedNet && visibleLayers[item.layer] !== false) : [],
    zones: highlightedNet ? board.zones.filter(item => item.net === highlightedNet && visibleLayers[item.layer] !== false) : [],
    vias: highlightedNet ? board.vias.filter(item => item.net === highlightedNet && showVias && (viasOnlyActive || viaCopperLayers(item.layers).some(layer => visibleLayers[layer] !== false))) : [],
    pads: highlightedNet ? board.pads.filter(item => item.net === highlightedNet && resolveBoardCopperLayers(availableCopperLayers, item.layers).some(layer => visibleLayers[layer] !== false)) : [],
  }), [board, highlightedNet, visibleLayers, showVias, viasOnlyActive]);
  const netTracks = netSets.tracks;
  const netZones = netSets.zones;
  const netVias = netSets.vias;
  const netPads = netSets.pads;
  const previewNet = hoverPreview?.kind === "net" ? hoverPreview.net : undefined;
  const previewSets = useMemo(() => ({
    tracks: previewNet ? board.tracks.filter(item => item.net === previewNet && visibleLayers[item.layer] !== false) : [],
    zones: previewNet ? board.zones.filter(item => item.net === previewNet && visibleLayers[item.layer] !== false) : [],
    pads: previewNet ? board.pads.filter(item => item.net === previewNet && resolveBoardCopperLayers(availableCopperLayers, item.layers).some(layer => visibleLayers[layer] !== false)) : [],
    vias: previewNet ? board.vias.filter(item => item.net === previewNet && showVias && (viasOnlyActive || viaCopperLayers(item.layers).some(layer => visibleLayers[layer] !== false))) : [],
  }), [board, previewNet, visibleLayers, showVias, viasOnlyActive]);
  const previewTracks = previewSets.tracks;
  const previewZones = previewSets.zones;
  const previewPads = previewSets.pads;
  const previewVias = previewSets.vias;
  const previewComponent = hoverPreview?.kind === "object" && hoverPreview.ref
    ? board.components.find(item => item.id === hoverPreview.id || item.ref === hoverPreview.ref) : undefined;
  const previewObjectPad = hoverPreview?.kind === "object" && hoverPreview.type === "pad" ? board.pads.find(item => item.id === hoverPreview.id) : undefined;
  const previewObjectVia = hoverPreview?.kind === "object" && hoverPreview.type === "via" ? board.vias.find(item => item.id === hoverPreview.id) : undefined;
  const previewObjectTrack = hoverPreview?.kind === "object" && hoverPreview.type === "trace" ? board.tracks.find(item => item.id === hoverPreview.id) : undefined;
  const netColor = isolatedNet ? "#5be6d7" : "#55e5d5";
  const netFocusActive = Boolean(highlightedNet && !isolatedNet && !resultFieldActive);
  const layerMatches = (layer: string) => activeCopperLayer === "All" || layer === activeCopperLayer;
  const displayedNets = useMemo(() => {
    const zones = netZones.filter(item => activeCopperLayer === "All" || item.layer === activeCopperLayer);
    const tracks = netTracks.filter(item =>
      (activeCopperLayer === "All" || item.layer === activeCopperLayer)
      && (item.id === selectedId || !trackCoveredByZones(item, zones)),
    );
    const pads = netPads.filter(item => layersContainCopper(item.layers, activeCopperLayer));
    const vias = netVias.filter(item => layersContainCopper(viaCopperLayers(item.layers), activeCopperLayer));
    const zonePathValue = zones.map(zone => zone.points.map((point, index) => {
      const [x, y] = toLayout(point);
      return `${index ? "L" : "M"}${x},${y}`;
    }).join(" ") + " Z").join(" ");
    return { zones, tracks, pads, vias, zonePathValue };
  }, [netSets, activeCopperLayer, selectedId, projectionKey]);
  const displayedNetZones = displayedNets.zones;
  const displayedNetTracks = displayedNets.tracks;
  const displayedNetPads = displayedNets.pads;
  const displayedNetVias = showVias ? displayedNets.vias : [];
  const selectedZoneActive = displayedNetZones.some(zone => zone.id === selectedId);
  const selectedZone = netZones.some(zone => zone.id === selectedId);
  const zonePath = (zones: ParsedBoard["zones"]) => zones.map(zone => zone.points.map((point, index) => {
    const [x, y] = toLayout(point);
    return `${index ? "L" : "M"}${x},${y}`;
  }).join(" ") + " Z").join(" ");
  const renderNativeLayer = (layer: string, key: string, opacity = 1) => {
    const geometry = nativeLayerGeometry[layer];
    if (!geometry) return null;
    const color = copperLayerColors[layer] ?? layerCssColor(layer);
    return <g key={key} opacity={opacity} pointerEvents="none" aria-label={`${layer} native vector geometry`}>
      {geometry.zones && <path d={geometry.zones} fill={color} fillOpacity="0.54" fillRule="evenodd" />}
      {geometry.tracks.map((track, index) => <path key={`${key}-track-${index}`} d={track.path} fill="none" stroke={color} strokeWidth={track.width} strokeLinecap="round" strokeLinejoin="round" />)}
      {geometry.pads && <path d={geometry.pads} fill={color} fillRule="evenodd" />}
      {showVias && geometry.vias && <path d={geometry.vias} fill={color} fillRule="evenodd" />}
      {geometry.drawings.map((drawing, index) => <path key={`${key}-drawing-${index}`} d={drawing.path} fill="none" stroke={color} strokeWidth={drawing.width} strokeLinecap="round" strokeLinejoin="round" />)}
    </g>;
  };
  const resultModeKey = resultVisualization?.mode ?? "geometry";
  const analysisNetsKey = analysisNets.join("\u0001");
  const visibleLayersKey = Object.keys(visibleLayers).length + ":" + Object.entries(visibleLayers).filter(([, value]) => value === false).map(([key]) => key).sort().join(",");
  useEffect(() => {
    // The layer manager is authoritative. A previous local F.Cu focus must not
    // silently suppress a newly enabled inner or bottom layer.
    setActiveCopperLayer("All");
  }, [availableCopperLayers.join(":"), visibleLayersKey]);
  const resultAnalysisOnly = Boolean(resultVisualization?.analysisOnly);
  const rawResultSamples = scalarSamplesForMode(analysisResult, resultModeKey);
  useEffect(() => {
    if (!resultVisualization?.visible || resultModeKey === "geometry" || resultModeKey === "mesh") return;
    const selectedLayer = resultLayerWithVisibleData(
      rawResultSamples,
      activeCopperLayer,
      board.layers,
      resultVisualization.visibleResultLayers,
      visibleLayers,
    );
    if (selectedLayer !== activeCopperLayer) setActiveCopperLayer(selectedLayer);
  }, [analysisResult, resultModeKey, resultVisualization?.visible, resultVisualization?.visibleResultLayers.join("\u0001"), activeCopperLayer, board.layers.join("\u0001"), visibleLayersKey]);
  const fieldPipeline = useMemo(() => {
    const rawSamples = rawResultSamples;
    const filtered = rawSamples.filter(sample => {
      const inside = sample.x_mm >= board.bounds.minX && sample.x_mm <= board.bounds.maxX
        && sample.y_mm >= board.bounds.minY && sample.y_mm <= board.bounds.maxY;
      const activeNet = !sample.net || !resultAnalysisOnly || !analysisNets.length || analysisNets.includes(sample.net);
      const layerVisible = resultLayerIsVisible(sample.layer, resultVisualization?.visibleResultLayers ?? [], board.layers, visibleLayers);
      const layerMatchesTarget = (() => {
        const layers = resultDatumLayers(sample.layer, board.layers);
        return !layers.length || activeCopperLayer === "All" || activeCopperLayer === "Overview" || layers.includes(activeCopperLayer);
      })();
      return inside && resultDatumFitsConductor(board, sample)
        && layerVisible && layerMatchesTarget && activeNet && (!isolatedNet || !sample.net || sample.net === isolatedNet);
    });
    const exact = filtered.filter(sample => (sample.vertices_mm?.length ?? 0) >= 3
      && resultFaceTriangleIndices(sample.vertices_mm!).length > 0);
    const retainedExact = spatiallyThinSamples(exact, 40000);
    const exactSamples = new Set(retainedExact);
    const samples = [
      ...retainedExact,
      // Degenerate or self-intersecting faces still carry a valid, admitted
      // solver sample. Render them as bounded centre glyphs instead of making
      // them silently disappear from the 2D result surface.
      ...spatiallyThinSamples(filtered.filter(sample => !exactSamples.has(sample)), 6000)
        .map(sample => ({ ...sample, vertices_mm: undefined })),
    ];
    const values = filtered.map(sample => sample.value);
    const extent = numericExtent(values, 0, 1);
    const savedRanges = analysisResult?.summary.visualization_ranges as Record<string, { minimum?: number; maximum?: number }> | undefined;
    const fieldKey = viewportResultField(resultModeKey).key;
    const savedMinimum = Number(savedRanges?.[fieldKey]?.minimum);
    const savedMaximum = Number(savedRanges?.[fieldKey]?.maximum);
    const cellSize = Math.max(0.08, Math.min(1.8, Math.sqrt(Math.max(board.width * board.height / Math.max(samples.length, 1), 0.0025)) * 1.08));
    return {
      samples,
      minimum: Number.isFinite(savedMinimum) ? savedMinimum : extent.minimum,
      maximum: Number.isFinite(savedMaximum) ? savedMaximum : extent.maximum,
      cellSize,
    };
  }, [analysisResult, board, resultAnalysisOnly, analysisNetsKey, activeCopperLayer, isolatedNet, visibleLayersKey, resultVisualization, resultModeKey]);
  const resultSamples = fieldPipeline.samples;
  const resultMinimum = fieldPipeline.minimum;
  const resultMaximum = fieldPipeline.maximum;
  const resultCellSize = fieldPipeline.cellSize;
  const resultColor = (value: number) => {
    const ratio = resultMaximum > resultMinimum ? (value - resultMinimum) / (resultMaximum - resultMinimum) : 0.5;
    return `hsl(${(1 - ratio) * 220} 92% 56%)`;
  };
  const vectorPipeline = useMemo(() => {
    const rawVectors = resultModeKey === "electric_field"
      ? analysisResult?.vector_fields.electric_field ?? []
      : resultModeKey === "magnetic_field"
        ? analysisResult?.vector_fields.magnetic_field ?? []
        : resultModeKey === "current" || resultModeKey === "current_density"
          ? analysisResult?.vector_fields.current_density ?? []
          : [];
    const filtered = rawVectors.filter(sample => {
      const inside = sample.x_mm >= board.bounds.minX && sample.x_mm <= board.bounds.maxX
        && sample.y_mm >= board.bounds.minY && sample.y_mm <= board.bounds.maxY;
      const activeNet = !sample.net || !resultAnalysisOnly || !analysisNets.length || analysisNets.includes(sample.net);
      const layerVisible = resultLayerIsVisible(sample.layer, resultVisualization?.visibleResultLayers ?? [], board.layers, visibleLayers);
      const layerMatchesTarget = (() => {
        const layers = resultDatumLayers(sample.layer, board.layers);
        return !layers.length || activeCopperLayer === "All" || activeCopperLayer === "Overview" || layers.includes(activeCopperLayer);
      })();
      return inside && pointOnResultConductor(board, [sample.x_mm, sample.y_mm], sample.net, sample.layer)
        && layerVisible && layerMatchesTarget && activeNet && (!isolatedNet || !sample.net || sample.net === isolatedNet);
    });
    const vectors = spatiallyThinSamples(filtered, 240);
    const vectorMaximum = Math.max(numericMaximum(vectors.map(sample => sample.magnitude), 0), Number.EPSILON);
    return { vectors, vectorMaximum };
  }, [analysisResult, board, resultAnalysisOnly, analysisNetsKey, activeCopperLayer, isolatedNet, visibleLayersKey, resultVisualization, resultModeKey]);
  const resultVectors = vectorPipeline.vectors;
  const resultVectorMaximum = vectorPipeline.vectorMaximum;
  const sampleLayers = (layer?: string) => resultDatumLayers(layer, board.layers);
  const sampleLayerVisible = (layer?: string) => {
    const selectedLayers = resultVisualization?.visibleResultLayers ?? [];
    return resultLayerIsVisible(layer, selectedLayers, board.layers, visibleLayers);
  };
  const sampleMatchesLayer = (layer: string | undefined, target: string) => {
    const layers = sampleLayers(layer);
    return !layers.length || target === "All" || target === "Overview" || layers.includes(target);
  };
  const probeLabelLayout = useMemo(() => {
    const entries = probes.filter(probe => probe.position && activeCopperLayer !== "Overview" && (!probe.layer || activeCopperLayer === "All" || probe.layer === "through" || probe.layer === activeCopperLayer));
    const occupied: { x: number; y: number; width: number; height: number }[] = [];
    return entries.map((probe, index) => {
      const point = toLayout(probe.position!);
      const solved = analysisResult?.probes.find(item => item.id === probe.id || probe.id.endsWith(item.id));
      const kind = probe.probeKind ?? "universal";
      const metric = solved?.status === "mapped"
        ? kind === "current" ? `${solved.peak_adjacent_current_a?.toPrecision(4) ?? "-"} A`
          : kind === "power" ? `${solved.adjacent_power_loss_w?.toPrecision(4) ?? "-"} W`
            : kind === "impedance" ? `${solved.local_series_resistance_ohm?.toPrecision(4) ?? "-"} ohm`
              : `${solved.voltage_v?.toPrecision(4) ?? "-"} V`
        : "not solved";
      const label = `P${index + 1} ${metric}`;
      const size = Math.max(view.width * 0.0072, 0.62);
      const width = Math.max(size * 4.2, label.length * size * 0.56);
      const height = size * 1.45;
      const offsets = [[1.5, -2.45], [1.5, 1.15], [-1.5 - width / size, -2.45], [-1.5 - width / size, 1.15], [1.5, -4.2], [1.5, 2.9]];
      let rect = { x: point[0] + size * offsets[0][0], y: point[1] + size * offsets[0][1], width, height };
      for (const [dx, dy] of offsets) {
        const candidate = { x: point[0] + size * dx, y: point[1] + size * dy, width, height };
        if (!occupied.some(existing => candidate.x < existing.x + existing.width && candidate.x + candidate.width > existing.x && candidate.y < existing.y + existing.height && candidate.y + candidate.height > existing.y)) {
          rect = candidate;
          break;
        }
      }
      occupied.push(rect);
      return { probe, index, point, solved, label, size, ...rect };
    });
  }, [probes, activeCopperLayer, analysisResult, view.x, view.y, view.width, view.height, projectionKey]);
  const thermalBounds = thermalScenario ? thermalVolume(thermalScenario) : null;
  const boardCenter = toLayout([
    (board.bounds.minX + board.bounds.maxX) / 2,
    (board.bounds.minY + board.bounds.maxY) / 2,
  ]);
  const thermalToLayout = (point: [number, number, number]): Point => thermalBounds ? [
    boardCenter[0] + point[0] - thermalBounds.x / 2,
    boardCenter[1] + point[1] - thermalBounds.y / 2,
  ] : boardCenter;
  const axisTicks = Array.from({ length: 6 }, (_, index) => index / 5);

  const featureAnnotations = useMemo(() => {
    if (resultsOnlyScene || activeCopperLayer === "Overview") return { labels: [], pinOne: [] };
    const visible = (item: { layer: string; net?: string }) => visibleLayers[item.layer] !== false
      && (activeCopperLayer === "All" || item.layer === activeCopperLayer) && (!isolatedNet || item.net === isolatedNet);
    const min = toBoard([view.x, view.y]), max = toBoard([view.x + view.width, view.y + view.height]);
    const bounds = { minX: min[0], minY: min[1], maxX: max[0], maxY: max[1],
      unitsPerPixel: Math.max(view.width / pixelSize.width, view.height / pixelSize.height) };
    const copper = showNetNames ? copperNetLabels(board.tracks.filter(visible), board.zones.filter(visible), bounds) : [];
    return layoutFeatureAnnotations(board, bounds, visibleLayers, activeCopperLayer, isolatedNet, showNetNames, copper);
  }, [board, showNetNames, resultsOnlyScene, activeCopperLayer, visibleLayers, isolatedNet, view, pixelSize, projectionKey]);

  const pinOnePath = useMemo(() => {
    const radius = Math.max(view.width / pixelSize.width, view.height / pixelSize.height) * 3;
    return featureAnnotations.pinOne.map(point => {
      const [x, y] = toLayout(point);
      return `M${x - radius},${y}a${radius},${radius} 0 1,0 ${radius * 2},0a${radius},${radius} 0 1,0 ${-radius * 2},0`;
    }).join(" ");
  }, [featureAnnotations, view, pixelSize, projectionKey]);

  const compositeCopper = activeCopperLayer === "All" && availableCopperLayers.filter(layer => visibleLayers[layer] !== false).length > 1;
  const nativeLayersOverlay = useMemo(() => (!resultsOnlyScene && !isolatedNet && activeCopperLayer !== "Overview"
    ? drawableLayers
      .filter(layer => !plottedLayerAvailable(layer)
        && visibleLayers[layer] !== false
        && (!availableCopperLayers.includes(layer) || activeCopperLayer === "All" || activeCopperLayer === layer))
      .map(layer => renderNativeLayer(
        layer,
        `native-${layer}`,
        (layerOpacity[layer] ?? 1)
          * (compositeCopper ? 0.42 : 0.9)
          * (netFocusActive ? 0.28 : 1)
          * (resultVisualization?.sceneMode === "analysis_only" ? 0.04
            : resultVisualization && ((resultVisualization.mode !== "geometry" && resultVisualization.mode !== "impedance") || translucentScene || resultVisualization.sceneMode === "translucent") ? resultVisualization.boardOpacity : 1),
      ))
    : null), [resultsOnlyScene, isolatedNet, activeCopperLayer, drawableLayers, board, visibleLayers, layerOpacity, netFocusActive, translucentScene, resultVisualization, nativeLayerGeometry, copperLayerColors, projectionKey, failedLayerUrls, showVias, compositeCopper]);

  const netHighlightOverlay = useMemo(() => {
    if (resultsOnlyScene || activeCopperLayer === "Overview" || !highlightedNet || resultFieldActive) return null;
    return <g className={selectionPulseClass} pointerEvents="none">
      {displayedNetZones.length > 0 && <path
        key={`highlight-zones-${highlightedNet}-${activeCopperLayer}`}
        d={displayedNets.zonePathValue}
        fill={selectedZoneActive ? "#ffc04f" : netColor}
        fillOpacity={isolatedNet ? 0.28 : selectedZoneActive ? 0.42 : 0.055}
        fillRule="nonzero"
        stroke="none"
      />}
      {displayedNetTracks.map(track => {
        const start = toLayout(track.start);
        const end = toLayout(track.end);
        const exactSelection = track.id === selectedId;
        const color = exactSelection ? "#ffc04f" : netColor;
        return <g key={`highlight-${track.id}`}>
          {netFocusActive && <line x1={start[0]} y1={start[1]} x2={end[0]} y2={end[1]} stroke="#061116" strokeOpacity="0.92" strokeWidth={Math.max(track.width + (exactSelection ? 0.68 : 0.42), exactSelection ? 0.88 : 0.62)} strokeLinecap="round" />}
          <line x1={start[0]} y1={start[1]} x2={end[0]} y2={end[1]} stroke={color} strokeWidth={Math.max(track.width + (exactSelection ? 0.14 : 0), netFocusActive ? 0.24 : 0.16)} strokeLinecap="round" />
        </g>;
      })}
      {displayedNetPads.map(pad => {
        const point = toLayout(pad.at);
        const exactSelection = pad.id === selectedId;
        return <rect key={`highlight-${pad.id}`} x={point[0] - pad.width / 2} y={point[1] - pad.height / 2} width={pad.width} height={pad.height} rx={Math.min(pad.width, pad.height) * 0.16} fill={exactSelection ? "#ffc04f" : netColor} fillOpacity={netFocusActive ? "0.9" : "0.76"} stroke="#061116" strokeWidth={exactSelection ? "0.46" : "0.26"} paintOrder="stroke fill" transform={`rotate(${pad.rotation} ${point[0]} ${point[1]})`} />;
      })}
      {displayedNetVias.map(via => {
        const point = toLayout(via.at);
        const exactSelection = via.id === selectedId;
        return <g key={`highlight-${via.id}`}>
          {netFocusActive && <circle cx={point[0]} cy={point[1]} r={via.size / 2 + 0.24} fill="#061116" />}
          <circle cx={point[0]} cy={point[1]} r={via.size / 2} fill={exactSelection ? "#ffc04f" : netColor} />
          <circle cx={point[0]} cy={point[1]} r={via.drill / 2} fill="#0b141a" />
        </g>;
      })}
    </g>;
  }, [resultsOnlyScene, activeCopperLayer, highlightedNet, resultFieldActive, selectionPulseClass, displayedNets, displayedNetZones, displayedNetTracks, displayedNetPads, displayedNetVias, selectedZoneActive, netColor, isolatedNet, selectedId, netFocusActive, projectionKey]);

  const meshCellsOverlay = useMemo(() => {
    if (activeCopperLayer === "Overview" || resultModeKey !== "mesh") return null;
    return analysisResult?.mesh.map(cell => {
      const centroid = cell.vertices_mm.reduce((sum, vertex) => [sum[0] + vertex[0], sum[1] + vertex[1]] as Point, [0, 0] as Point);
      const count = Math.max(cell.vertices_mm.length, 1);
      if (centroid[0] / count < board.bounds.minX || centroid[0] / count > board.bounds.maxX || centroid[1] / count < board.bounds.minY || centroid[1] / count > board.bounds.maxY) return null;
      if (cell.layer && visibleLayers[cell.layer] === false || cell.layer && activeCopperLayer !== "All" && cell.layer !== activeCopperLayer) return null;
      if (resultAnalysisOnly && cell.net && analysisNets.length && !analysisNets.includes(cell.net)) return null;
      const face = meshCellFaceVertices(cell);
      if (!resultDatumFitsConductor(board, { x_mm: centroid[0] / count, y_mm: centroid[1] / count, net: cell.net, layer: cell.layer, vertices_mm: face as [number, number, number][] })) return null;
      const points = face.map(vertex => toLayout([vertex[0], vertex[1]])).map(point => point.join(",")).join(" ");
      return <polygon key={`mesh-${cell.id}`} points={points} fill="none" stroke="#55d8d0" strokeWidth="0.11" vectorEffect="non-scaling-stroke" opacity="0.8" />;
    });
  }, [activeCopperLayer, resultModeKey, analysisResult, board, visibleLayers, resultAnalysisOnly, analysisNetsKey, projectionKey]);

  const displayResultSamples = useMemo(() => resultVisualization?.fieldStyle === "smooth"
    ? smoothDisplaySamples(resultSamples, resultFaceTriangleIndices) : resultSamples,
    [resultSamples, resultVisualization?.fieldStyle]);
  const resultSvgBatches = useMemo(() => buildScalarSvgBatches(displayResultSamples, {
    minimum: resultMinimum,
    maximum: resultMaximum,
    cellSize: resultCellSize,
    colorBuckets: resultVisualization?.fieldStyle === "smooth" ? 128 : 48,
    smooth: false,
    project: point => toLayout(point),
  }), [displayResultSamples, resultMinimum, resultMaximum, resultCellSize, resultVisualization?.fieldStyle, projectionKey]);
  const resultFieldOverlay = useMemo(() => <g className={`result-field-overlay style-${resultVisualization?.fieldStyle ?? "cells"}`} pointerEvents="none" shapeRendering="crispEdges">
    {resultSvgBatches.map(batch => <path key={`result-bucket-${batch.bucket}`} d={batch.path} fill={batch.color}
      fillOpacity="1" stroke="none"
      data-sample-count={batch.sampleCount} />)}
  </g>, [resultSvgBatches, resultVisualization?.fieldStyle]);

  const resultVectorsOverlay = useMemo(() => (!resultVisualization?.showVectors ? null : resultVectors.map((sample, index) => {
    const point = toLayout([sample.x_mm, sample.y_mm]);
    const magnitude = Math.max(sample.magnitude, Number.EPSILON);
    const vectorLength = resultCellSize * (1.1 + 2.4 * magnitude / resultVectorMaximum) * resultVisualization.vectorScale;
    const norm = Math.hypot(sample.vector[0], sample.vector[1]) || 1;
    return <line key={`result-vector-${sample.element_id ?? index}`} x1={point[0]} y1={point[1]} x2={point[0] + sample.vector[0] / norm * vectorLength} y2={point[1] + sample.vector[1] / norm * vectorLength} stroke="#f7d15e" strokeWidth={Math.max(view.width * 0.00045, 0.055)} markerEnd="url(#result-vector-arrow)" vectorEffect="non-scaling-stroke" opacity="0.9" pointerEvents="none" />;
  })), [resultVisualization?.showVectors, resultVisualization?.vectorScale, resultVectors, resultVectorMaximum, resultCellSize, view.width, projectionKey]);

  return <div className={`layout-viewport ${dragging ? "dragging" : ""} ${isolatedNet ? "net-isolated" : ""} ${netFocusActive ? "net-focused" : ""} ${activeCopperLayer === "Overview" ? "overview-active" : ""}`} data-highlighted-net={highlightedNet ?? ""}>
    <svg
      ref={svgRef}
      viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`}
      preserveAspectRatio="xMidYMid meet"
      onDoubleClick={() => setView(initialView)}
      onWheel={event => {
        event.preventDefault();
        zoomAt(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect(), event.deltaY < 0);
      }}
      onPointerDown={beginPan}
      onPointerMove={event => {
        continuePan(event);
        updateHoverProbe(event);
      }}
      onPointerUp={event => {
        if (!endPan(event)) selectAt(pointerInLayout(event));
      }}
      onPointerCancel={event => endPan(event)}
      onPointerLeave={() => onHoverProbe?.(null)}
      onContextMenu={event => {
        event.preventDefault();
        event.stopPropagation();
        const point = clientToLayout(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect());
        const object = selectAt(point);
        onContextMenu?.({ clientX: event.clientX, clientY: event.clientY, object });
      }}
    >
      <defs>
        <pattern id="layout-grid-small" width="1" height="1" patternUnits="userSpaceOnUse">
          <path d="M 1 0 L 0 0 0 1" fill="none" stroke="#243640" strokeWidth="0.035" />
        </pattern>
        <pattern id="layout-grid-large" width="10" height="10" patternUnits="userSpaceOnUse">
          <rect width="10" height="10" fill="url(#layout-grid-small)" />
          <path d="M 10 0 L 0 0 0 10" fill="none" stroke="#344a54" strokeWidth="0.07" />
        </pattern>
        <marker id="thermal-flow-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L7,3.5 L0,7 Z" fill="#82f2ff" />
        </marker>
        <marker id="result-vector-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L6,3 L0,6 Z" fill="#f7d15e" />
        </marker>
      </defs>
      <rect x={sourceViewBox[0] - sourceViewBox[2] * 4} y={sourceViewBox[1] - sourceViewBox[3] * 4} width={sourceViewBox[2] * 9} height={sourceViewBox[3] * 9} fill="#0b141a" />
      {showAxes && <rect x={sourceViewBox[0]} y={sourceViewBox[1]} width={sourceViewBox[2]} height={sourceViewBox[3]} fill="url(#layout-grid-large)" />}
      {showAxes && <g className="layout-measurement-axes" pointerEvents="none">
        <line x1={sourceViewBox[0]} y1={sourceViewBox[1]} x2={sourceViewBox[0] + sourceViewBox[2]} y2={sourceViewBox[1]} />
        <line x1={sourceViewBox[0]} y1={sourceViewBox[1]} x2={sourceViewBox[0]} y2={sourceViewBox[1] + sourceViewBox[3]} />
        {axisTicks.map(ratio => <g key={`x-${ratio}`}>
          <line x1={sourceViewBox[0] + sourceViewBox[2] * ratio} y1={sourceViewBox[1]} x2={sourceViewBox[0] + sourceViewBox[2] * ratio} y2={sourceViewBox[1] + view.height * 0.008} />
          <text x={sourceViewBox[0] + sourceViewBox[2] * ratio} y={sourceViewBox[1] + view.height * 0.026}>{(sourceViewBox[0] + sourceViewBox[2] * ratio).toFixed(1)} mm</text>
        </g>)}
        {axisTicks.map(ratio => <g key={`y-${ratio}`}>
          <line x1={sourceViewBox[0]} y1={sourceViewBox[1] + sourceViewBox[3] * ratio} x2={sourceViewBox[0] + view.width * 0.008} y2={sourceViewBox[1] + sourceViewBox[3] * ratio} />
          <text className="y-label" x={sourceViewBox[0] + view.width * 0.011} y={sourceViewBox[1] + sourceViewBox[3] * ratio}>{(sourceViewBox[1] + sourceViewBox[3] * ratio).toFixed(1)} mm</text>
        </g>)}
      </g>}
      {!resultsOnlyScene && anyLayerVisible && boardPath && <path d={boardPath} fill={isolatedNet || resultVisualization?.sceneMode === "analysis_only" ? "#0b1317" : "#111c22"} stroke={visibleLayers["Edge.Cuts"] === false ? "none" : "#6e8b91"} strokeWidth="0.18" fillRule="evenodd" />}
      {Object.entries(board.layoutLayerUrls ?? {}).map(([layer, url]) => {
        const isCopper = availableCopperLayers.includes(layer);
        const copperVisible = activeCopperLayer === "All" || layer === activeCopperLayer;
        if (!plottedLayerAvailable(layer) || resultsOnlyScene || isolatedNet || activeCopperLayer === "Overview" || visibleLayers[layer] === false || isCopper && !copperVisible) return null;
        const compositeOpacity = compositeCopper && isCopper ? 0.44 : 1;
        return <image
        key={layer}
        href={url}
        onError={() => setFailedLayerUrls(current => new Set(current).add(url))}
        x={sourceViewBox[0]}
        y={sourceViewBox[1]}
        width={sourceViewBox[2]}
        height={sourceViewBox[3]}
        opacity={(selectedZoneActive && isCopper
          ? (layerOpacity[layer] ?? 1) * (baseLayerOpacity[layer] ?? 0.7) * compositeOpacity * 0.24
          : (layerOpacity[layer] ?? 1) * (baseLayerOpacity[layer] ?? 0.7) * compositeOpacity * (netFocusActive ? 0.34 : 1))
          * (resultVisualization?.sceneMode === "analysis_only" ? 0.04
            : resultVisualization && ((resultVisualization.mode !== "geometry" && resultVisualization.mode !== "impedance") || translucentScene || resultVisualization.sceneMode === "translucent") ? resultVisualization.boardOpacity : 1)}
        style={{
          mixBlendMode: compositeCopper && isCopper ? "screen" : "normal",
          filter: resultVisualization?.sceneMode === "analysis_only"
            ? "grayscale(1) brightness(.36) contrast(.72)"
            : netFocusActive ? "grayscale(.82) saturate(.28) brightness(.7) contrast(.82)" : undefined,
        }}
      />;
      })}
      {nativeLayersOverlay}
      <g aria-label="Pad numbers and copper net names" pointerEvents="none" fill="#f3f8fa" stroke="#101820" strokeWidth={Math.max(view.width / pixelSize.width, view.height / pixelSize.height) * 1.8} paintOrder="stroke" fontFamily="monospace" textAnchor="middle" dominantBaseline="central">
        {featureAnnotations.labels.map(label => {
          const [x, y] = toLayout([label.x, label.y]);
          return <text key={`${label.kind}:${label.id}`} data-net-label={label.kind} x={x} y={y} fontSize={label.fontSize} transform={`rotate(${label.angle} ${x} ${y})`}><title>{label.title}</title>{label.text}</text>;
        })}
      </g>
      {pinOnePath && <path aria-label="Pin 1 and A1 markers" data-pin-one-count={featureAnnotations.pinOne.length} d={pinOnePath} fill="none" stroke="#ffdc74" strokeWidth={1.5} vectorEffect="non-scaling-stroke" pointerEvents="none" />}

      {!resultsOnlyScene && viasOnlyActive && <g aria-label="Vias only" pointerEvents="none">{availableCopperLayers.map(layer =>
        <path key={layer} d={nativeLayerGeometry[layer]?.vias ?? ""} fill="#c79c50" fillRule="evenodd" />)}</g>}
      {netHighlightOverlay}
      {hoverPreview && <g className="viewport-hover-preview" aria-label={`Preview ${hoverPreview.label}`}>
        {previewZones.filter(zone => activeCopperLayer === "All" || activeCopperLayer === "Overview" || zone.layer === activeCopperLayer).map(zone => <path key={`preview-zone-${zone.id}`} d={zonePath([zone])} fill="#ff38c7" fillOpacity="0.28" stroke="#ff8ee3" strokeWidth="0.28" fillRule="nonzero" />)}
        {previewTracks.filter(track => activeCopperLayer === "All" || activeCopperLayer === "Overview" || track.layer === activeCopperLayer).map(track => { const start = toLayout(track.start); const end = toLayout(track.end); return <line key={`preview-track-${track.id}`} x1={start[0]} y1={start[1]} x2={end[0]} y2={end[1]} stroke="#ff38c7" strokeWidth={Math.max(track.width + 0.38, 0.62)} strokeLinecap="round" />; })}
        {previewPads.filter(pad => layersContainCopper(pad.layers, activeCopperLayer)).map(pad => { const point = toLayout(pad.at); return <rect key={`preview-pad-${pad.id}`} x={point[0] - pad.width / 2} y={point[1] - pad.height / 2} width={pad.width} height={pad.height} rx={Math.min(pad.width, pad.height) * 0.16} fill="#ff38c7" stroke="#ffe2f8" strokeWidth="0.3" transform={`rotate(${pad.rotation} ${point[0]} ${point[1]})`} />; })}
        {showVias && previewVias.map(via => { const point = toLayout(via.at); return <g key={`preview-via-${via.id}`}><circle cx={point[0]} cy={point[1]} r={via.size / 2 + 0.22} fill="#ff38c7" /><circle cx={point[0]} cy={point[1]} r={via.drill / 2} fill="#0b141a" /></g>; })}
        {previewComponent && (() => { const point = toLayout(previewComponent.at); return <rect x={point[0] - previewComponent.width / 2} y={point[1] - previewComponent.height / 2} width={previewComponent.width} height={previewComponent.height} rx="0.35" fill="#ff38c7" fillOpacity="0.2" stroke="#ff38c7" strokeWidth="0.65" transform={`rotate(${previewComponent.rotation} ${point[0]} ${point[1]})`} />; })()}
        {previewObjectPad && (() => { const point = toLayout(previewObjectPad.at); return <rect x={point[0] - previewObjectPad.width / 2} y={point[1] - previewObjectPad.height / 2} width={previewObjectPad.width} height={previewObjectPad.height} rx={Math.min(previewObjectPad.width, previewObjectPad.height) * 0.16} fill="#ff38c7" stroke="#fff" strokeWidth="0.35" transform={`rotate(${previewObjectPad.rotation} ${point[0]} ${point[1]})`} />; })()}
        {previewObjectVia && (() => { const point = toLayout(previewObjectVia.at); return <circle cx={point[0]} cy={point[1]} r={previewObjectVia.size / 2 + 0.3} fill="#ff38c7" stroke="#fff" strokeWidth="0.3" />; })()}
        {previewObjectTrack && (() => { const start = toLayout(previewObjectTrack.start); const end = toLayout(previewObjectTrack.end); return <line x1={start[0]} y1={start[1]} x2={end[0]} y2={end[1]} stroke="#ff38c7" strokeWidth={Math.max(previewObjectTrack.width + 0.45, 0.7)} strokeLinecap="round" />; })()}
      </g>}
      {selectedComponent && activeCopperLayer !== "Overview" && (() => {
        const point = toLayout(selectedComponent.at);
        return <rect
          className={selectionPulseClass}
          pointerEvents="none"
          x={point[0] - selectedComponent.width / 2}
          y={point[1] - selectedComponent.height / 2}
          width={selectedComponent.width}
          height={selectedComponent.height}
          rx="0.35"
          fill="#ffb638"
          fillOpacity="0.12"
          stroke="#ffb638"
          strokeWidth="0.42"
          vectorEffect="non-scaling-stroke"
          transform={`rotate(${selectedComponent.rotation} ${point[0]} ${point[1]})`}
        />;
      })()}
      {selectedPoint && activeCopperLayer !== "Overview" && <g className={selectionPulseClass} pointerEvents="none">
        <circle cx={selectedPoint[0]} cy={selectedPoint[1]} r={Math.max(view.width * 0.012, 0.8)} fill="none" stroke="#ffb638" strokeWidth={Math.max(view.width * 0.0015, 0.12)} vectorEffect="non-scaling-stroke" />
        <circle cx={selectedPoint[0]} cy={selectedPoint[1]} r={Math.max(view.width * 0.003, 0.2)} fill="#ffb638" />
      </g>}
      {activeCopperLayer !== "Overview" && terminalMarkers.filter(terminal => {
        if (isolatedNet && terminal.net !== isolatedNet) return false;
        const layers = terminal.layer && terminal.layer !== "auto" ? [terminal.layer] : terminal.layers;
        return activeCopperLayer === "All" || !layers.length || layersContainCopper(layers, activeCopperLayer);
      }).map((terminal, index) => {
        const point = toLayout(terminal.position);
        const color = terminal.role === "source" ? "#63d69a"
          : terminal.role === "load" ? "#ffb84b"
            : terminal.role === "source_return" ? "#62a9ee" : "#b28cff";
        const label = terminal.role === "source" ? `S${index + 1}`
          : terminal.role === "load" ? `L${index + 1}`
            : terminal.role === "source_return" ? "SR" : "LR";
        const radius = Math.max(view.width * 0.0065, 0.44);
        const tooltip = `${terminal.name}\n${terminal.net}\n${terminal.value} ${terminal.role.includes("source") ? "V" : "A"}\n${terminal.position[0].toFixed(4)}, ${terminal.position[1].toFixed(4)} mm\n${terminal.layers.join(" / ") || terminal.layer || "connected conductor"}`;
        return <g key={`analysis-terminal-${terminal.id}`} className="analysis-terminal-marker">
          <title>{tooltip}</title>
          <circle cx={point[0]} cy={point[1]} r={radius * 1.45} fill="#071116" fillOpacity="0.9" stroke={color} strokeWidth="0.2" vectorEffect="non-scaling-stroke" />
          <circle cx={point[0]} cy={point[1]} r={radius * 0.48} fill={color} />
          <text x={point[0] + radius * 1.75} y={point[1] - radius * 1.3} fill={color} fontSize={Math.max(view.width * 0.008, 0.68)} fontWeight="700" pointerEvents="none">{label}</text>
        </g>;
      })}
      {showProbes && activeCopperLayer !== "Overview" && analysisResult?.probes.filter(probe => probe.status === "mapped" && probe.position_mm
        && (!isolatedNet || probe.net === isolatedNet)
        && resultLayerIsVisible(probe.layer, resultVisualization?.visibleResultLayers ?? [], board.layers, visibleLayers)
        && (activeCopperLayer === "All" || !probe.layer || resultDatumLayers(probe.layer, board.layers).includes(activeCopperLayer))).map(probe => {
        const point = toLayout(probe.position_mm!);
        const tooltip = `${probe.name ?? probe.id}\n${probe.voltage_v?.toFixed(6)} V\n${(Number(probe.voltage_drop_v) * 1000).toFixed(3)} mV drop\n${probe.peak_adjacent_current_a?.toFixed(4)} A`;
        return <g key={`probe-${probe.id}`} className="solved-probe">
          <circle cx={point[0]} cy={point[1]} r={Math.max(view.width * 0.006, 0.42)} fill="#081318" stroke="#ffbf47" strokeWidth="0.16" vectorEffect="non-scaling-stroke"><title>{tooltip}</title></circle>
          <circle cx={point[0]} cy={point[1]} r={Math.max(view.width * 0.0018, 0.12)} fill="#ffbf47" pointerEvents="none" />
        </g>;
      })}
      {meshCellsOverlay}
      {resultFieldOverlay}
      {resultVectorsOverlay}
      {thermalScenario && thermalBounds && activeCopperLayer !== "Overview" && <g className="thermal-scene-overlay" pointerEvents="none">
        {thermalVisibility.volume && <g>
          <rect
            x={boardCenter[0] - thermalBounds.x / 2}
            y={boardCenter[1] - thermalBounds.y / 2}
            width={thermalBounds.x}
            height={thermalBounds.y}
            fill={thermalScenario.medium === "potting" ? "#4fc2c2" : "#3da6d8"}
            fillOpacity={thermalScenario.medium === "potting" ? 0.12 : 0.035}
            stroke="#63c9ef"
            strokeWidth="0.2"
            strokeDasharray="1.2 0.7"
            vectorEffect="non-scaling-stroke"
          ><title>{`Thermal bounding volume ${thermalBounds.x} x ${thermalBounds.y} x ${thermalBounds.z} mm`}</title></rect>
          <text x={boardCenter[0] - thermalBounds.x / 2 + 1.2} y={boardCenter[1] - thermalBounds.y / 2 + 2.5} fill="#7ddcff" fontSize={Math.max(view.width * 0.007, 0.6)}>THERMAL DOMAIN · {thermalBounds.z} mm HIGH</text>
        </g>}
        {thermalVisibility.heatSources && (thermalScenario.heat_sources ?? []).map((source, index) => {
          const dimensions = source.dimensions_mm;
          const width = Math.max(Number(dimensions?.x) || board.width * 0.82, 1);
          const height = Math.max(Number(dimensions?.y) || board.height * 0.82, 1);
          const center = thermalToLayout(source.position ?? [thermalBounds.x / 2, thermalBounds.y / 2, 0]);
          return <g key={`thermal-source-${source.id ?? index}`}>
            <rect x={center[0] - width / 2} y={center[1] - height / 2} width={width} height={height} rx="1" fill="#ff6238" fillOpacity="0.2" stroke="#ffad4d" strokeWidth="0.22" vectorEffect="non-scaling-stroke"><title>{`${source.id ?? "Heat source"}: ${Number(source.power_w) || 0} W`}</title></rect>
            <text x={center[0] - width / 2 + 1} y={center[1] + 0.5} fill="#ffd18a" fontSize={Math.max(view.width * 0.0065, 0.55)}>{`${source.id ?? "HEAT"} · ${Number(source.power_w) || 0} W`}</text>
          </g>;
        })}
        {thermalVisibility.airflow && (thermalScenario.flow_channels ?? []).map((channel, index) => {
          const points = (channel.path ?? []).map(thermalToLayout);
          if (points.length < 2) return null;
          return <polyline key={`thermal-flow-${channel.id ?? index}`} points={points.map(point => point.join(",")).join(" ")} fill="none" stroke="#64e7f4" strokeOpacity="0.8" strokeWidth={Math.max(Number(channel.width_mm) * 0.08 || 0.8, 0.55)} strokeLinecap="round" strokeLinejoin="round" markerEnd="url(#thermal-flow-arrow)" vectorEffect="non-scaling-stroke"><title>{`${channel.id ?? "Flow channel"}: ${Number(channel.flow_rate_m3_s) || 0} m3/s`}</title></polyline>;
        })}
        {thermalVisibility.hardware && (thermalScenario.fans ?? []).filter(fan => fan.enabled !== false).map((fan, index) => {
          const center = thermalToLayout(fan.position ?? [thermalBounds.x * 0.1, thermalBounds.y / 2, thermalBounds.z / 2]);
          const direction = fan.direction ?? [1, 0, 0];
          const length = Math.max((Number(fan.diameter_mm) || 20) * 0.7, 8);
          return <g key={`thermal-fan-${fan.id ?? index}`}>
            <circle cx={center[0]} cy={center[1]} r={Math.max((Number(fan.diameter_mm) || 20) / 2, 3)} fill="#55d89d" fillOpacity="0.16" stroke="#6cf2b2" strokeWidth="0.22" vectorEffect="non-scaling-stroke"><title>{`${fan.name ?? fan.id ?? "Fan"}: ${Number(fan.diameter_mm) || 0} mm, ${Number(fan.flow_rate_m3_s) || 0} m3/s, ${Number(fan.static_pressure_pa) || 0} Pa, ${Number(fan.rpm) || 0} RPM`}</title></circle>
            <line x1={center[0]} y1={center[1]} x2={center[0] + direction[0] * length} y2={center[1] + direction[1] * length} stroke="#80f5bb" strokeWidth="0.3" markerEnd="url(#thermal-flow-arrow)" vectorEffect="non-scaling-stroke" />
          </g>;
        })}
        {thermalVisibility.hardware && (thermalScenario.virtual_heatsinks ?? []).filter(heatsink => heatsink.enabled !== false).map((heatsink, index) => {
          const dimensions = heatsink.dimensions_mm ?? {};
          const width = Math.max(Number(dimensions.x) || 40, 2);
          const height = Math.max(Number(dimensions.y) || 40, 2);
          const center = thermalToLayout(heatsink.position ?? [thermalBounds.x / 2, thermalBounds.y / 2, 0]);
          return <g key={`thermal-heatsink-${heatsink.id ?? index}`}>
            <rect x={center[0] - width / 2} y={center[1] - height / 2} width={width} height={height} fill="#b9ccd3" fillOpacity="0.15" stroke="#d4e2e7" strokeWidth="0.2" vectorEffect="non-scaling-stroke"><title>{`${heatsink.name ?? heatsink.id ?? "Heatsink"}: ${width} x ${height} x ${Number(dimensions.z) || 15} mm, target ${heatsink.target}`}</title></rect>
            {Array.from({ length: Math.min(Math.max(Number(heatsink.fin_count) || 0, 0), 40) }, (_, fin) => <line key={fin} x1={center[0] - width / 2 + width * (fin + 1) / ((Number(heatsink.fin_count) || 0) + 1)} y1={center[1] - height / 2} x2={center[0] - width / 2 + width * (fin + 1) / ((Number(heatsink.fin_count) || 0) + 1)} y2={center[1] + height / 2} stroke="#d4e2e7" strokeOpacity="0.7" strokeWidth="0.12" vectorEffect="non-scaling-stroke" />)}
          </g>;
        })}
        {thermalVisibility.hardware && (thermalScenario.thermal_links ?? []).filter(link => link.enabled !== false).map(link => {
          const from = thermalScenario.thermal_elements?.find(element => element.id === link.from_id);
          const to = thermalScenario.thermal_elements?.find(element => element.id === link.to_id);
          if (!from?.position || !to?.position) return null;
          const start = thermalToLayout(from.position);
          const end = thermalToLayout(to.position);
          return <line key={`thermal-link-${link.id}`} x1={start[0]} y1={start[1]} x2={end[0]} y2={end[1]} stroke="#ffd166" strokeWidth="0.28" strokeDasharray="1 0.5" markerEnd="url(#thermal-flow-arrow)" vectorEffect="non-scaling-stroke"><title>{`${from.reference ?? from.id} to ${to.reference ?? to.id}: ${Number(link.resistance_c_per_w) || 0} C/W`}</title></line>;
        })}
      </g>}
      <g className="probe-overlay-top" pointerEvents="none">
        {showProbes && probeLabelLayout.map(({ probe, point, solved, label, size, x, y, width, height }) => {
          const detail = solved?.status === "mapped" ? `${solved.voltage_v?.toFixed(6) ?? "-"} V | ${solved.peak_adjacent_current_a?.toFixed(5) ?? "-"} A | ${solved.adjacent_power_loss_w?.toFixed(6) ?? "-"} W | ${solved.local_series_resistance_ohm?.toPrecision(5) ?? "-"} ohm | ${solved.peak_adjacent_current_density_a_mm2?.toFixed(3) ?? "-"} A/mm2` : "Awaiting analysis";
          return <g key={`top-probe-${probe.id}`}>
            <title>{`${probe.name}\n${detail}`}</title>
            <circle cx={point[0]} cy={point[1]} r={Math.max(view.width * 0.0075, 0.52)} fill="#071116" stroke="#ffd166" strokeWidth="0.18" vectorEffect="non-scaling-stroke" />
            <path d={`M ${point[0]} ${point[1]} L ${x} ${y + height / 2}`} stroke="#ffd166" strokeWidth="0.13" vectorEffect="non-scaling-stroke" />
            <rect x={x} y={y} width={width} height={height} rx={size * 0.16} fill="#09171d" stroke="#d9a744" strokeWidth="0.11" vectorEffect="non-scaling-stroke" />
            <text x={x + size * 0.42} y={y + size} fill="#ffe09c" fontSize={size}>{label}</text>
          </g>;
        })}
      </g>
    </svg>
    {activeCopperLayer === "Overview" && <div className="layout-overview">
      {availableCopperLayers.map(layer => {
        const layerZones = netZones.filter(item => item.layer === layer);
        const layerTracks = netTracks.filter(item => item.layer === layer && (item.id === selectedId || !trackCoveredByZones(item, layerZones)));
        const layerPads = netPads.filter(item => layersContainCopper(item.layers, layer));
        const layerVias = netVias.filter(item => layersContainCopper(item.layers, layer));
        const featureCount = layerZones.length + layerTracks.length + layerPads.length + layerVias.length;
        const overviewResultSamples = displayResultSamples.filter(sample => sampleMatchesLayer(sample.layer, layer));
        const overviewResultVectors = resultVectors.filter(sample => sampleMatchesLayer(sample.layer, layer));
        const overviewId = layer.replace(/[^a-z0-9_-]/gi, "-");
        return <button key={layer} onClick={() => setActiveCopperLayer(layer)} title={`${layer}: drag to pan, wheel to zoom, double-click to fit`}>
          <span>{layer}</span>
          <div
            className="layout-overview-canvas"
            onWheel={event => {
              event.preventDefault();
              event.stopPropagation();
              zoomAt(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect(), event.deltaY < 0);
            }}
            onPointerDown={beginPan}
            onPointerMove={continuePan}
            onPointerUp={event => {
              const moved = endPan(event);
              if (!moved) setActiveCopperLayer(layer);
            }}
            onPointerCancel={event => endPan(event)}
            onDoubleClick={event => {
              event.preventDefault();
              event.stopPropagation();
              setView(initialView);
            }}
            onContextMenu={event => event.preventDefault()}
          >
            <svg viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`} preserveAspectRatio="xMidYMid meet" aria-label={`${layer} copper overview`}>
              <defs>
                <marker id={`overview-result-arrow-${overviewId}`} markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L6,3 L0,6 Z" fill="#f7d15e" /></marker>
              </defs>
              {!resultsOnlyScene && visibleLayers[layer] !== false && (plottedLayerAvailable(layer) ? <image
                href={board.layoutLayerUrls?.[layer]}
                onError={() => setFailedLayerUrls(current => new Set(current).add(board.layoutLayerUrls![layer]))}
                x={sourceViewBox[0]}
                y={sourceViewBox[1]}
                width={sourceViewBox[2]}
                height={sourceViewBox[3]}
                opacity={highlightedNet && !resultFieldActive ? selectedZone && layerZones.length ? 0.22 : 0.34 : 1}
                style={{
                  filter: highlightedNet && !resultFieldActive ? "grayscale(.9) saturate(.2) brightness(.66) contrast(.8)" : undefined,
                }}
              /> : renderNativeLayer(layer, `overview-native-${layer}`, highlightedNet && !resultFieldActive ? selectedZone && layerZones.length ? 0.22 : 0.34 : 0.9))}
              {!resultsOnlyScene && highlightedNet && !resultFieldActive && <g className={selectionPulseClass} pointerEvents="none">
              {layerZones.length > 0 && <path d={zonePath(layerZones)} fill={selectedZone ? "#ffc04f" : netColor} fillOpacity={selectedZone ? 0.5 : 0.16} fillRule="nonzero" stroke="none" />}
              {layerTracks.map(track => {
                const start = toLayout(track.start);
                const end = toLayout(track.end);
                return <line key={track.id} x1={start[0]} y1={start[1]} x2={end[0]} y2={end[1]} stroke={track.id === selectedId ? "#ffc04f" : netColor} strokeWidth={Math.max(track.width, 0.28)} strokeLinecap="round" />;
              })}
              {layerPads.map(pad => {
                const point = toLayout(pad.at);
                return <rect key={pad.id} x={point[0] - pad.width / 2} y={point[1] - pad.height / 2} width={pad.width} height={pad.height} rx={Math.min(pad.width, pad.height) * 0.16} fill={pad.id === selectedId ? "#ffc04f" : netColor} transform={`rotate(${pad.rotation} ${point[0]} ${point[1]})`} />;
              })}
              {showVias && layerVias.map(via => {
                const point = toLayout(via.at);
                return <g key={via.id}><circle cx={point[0]} cy={point[1]} r={via.size / 2} fill={via.id === selectedId ? "#ffc04f" : netColor} /><circle cx={point[0]} cy={point[1]} r={via.drill / 2} fill="#0b141a" /></g>;
              })}
              </g>}
              <g pointerEvents="none" shapeRendering="crispEdges">
                {buildScalarSvgBatches(overviewResultSamples, { minimum: resultMinimum, maximum: resultMaximum,
                  cellSize: resultCellSize, colorBuckets: 128, smooth: false, project: point => toLayout(point) }).map(batch =>
                  <path key={`overview-result-${layer}-${batch.bucket}`} d={batch.path} fill={batch.color} stroke="none" />)}
              </g>
              {resultVisualization?.showVectors && overviewResultVectors.map((sample, index) => {
                const point = toLayout([sample.x_mm, sample.y_mm]);
                const vectorLength = resultCellSize * (1.1 + 2.4 * Math.max(sample.magnitude, Number.EPSILON) / resultVectorMaximum) * resultVisualization.vectorScale;
                const norm = Math.hypot(sample.vector[0], sample.vector[1]) || 1;
                return <line key={`overview-vector-${layer}-${sample.element_id ?? index}`} x1={point[0]} y1={point[1]} x2={point[0] + sample.vector[0] / norm * vectorLength} y2={point[1] + sample.vector[1] / norm * vectorLength} stroke="#f7d15e" strokeWidth={Math.max(view.width * 0.00045, 0.055)} markerEnd={`url(#overview-result-arrow-${overviewId})`} vectorEffect="non-scaling-stroke" opacity="0.9" pointerEvents="none" />;
              })}
              {showProbes && probes.filter(probe => probe.position && (!probe.layer || probe.layer === "through" || probe.layer === layer)).map(probe => {
                const point = toLayout(probe.position!);
                return <g key={`overview-probe-${layer}-${probe.id}`} pointerEvents="none"><circle cx={point[0]} cy={point[1]} r={Math.max(view.width * 0.004, 0.28)} fill="#071116" stroke="#ffd166" strokeWidth="0.14" vectorEffect="non-scaling-stroke" /><circle cx={point[0]} cy={point[1]} r={Math.max(view.width * 0.0013, 0.09)} fill="#ffd166" /></g>;
              })}
            </svg>
          </div>
          {(highlightedNet || overviewResultSamples.length > 0) && <small>{overviewResultSamples.length > 0 ? `${overviewResultSamples.length} result samples` : `${featureCount} selected features`}</small>}
        </button>;
      })}
    </div>}
    <div
      className={`layout-layer-tabs ${layerPickerExpanded ? "expanded" : "collapsed"}`}
      aria-label="Active layout layer"
      aria-expanded={layerPickerExpanded}
      onMouseEnter={() => setLayerPickerExpanded(true)}
      onMouseLeave={() => setLayerPickerExpanded(false)}
      onFocusCapture={() => setLayerPickerExpanded(true)}
      onBlurCapture={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setLayerPickerExpanded(false);
      }}
    >
      {availableCopperLayers.map(layer => <button
        key={layer}
        className={activeCopperLayer === layer ? "selected" : ""}
        onClick={() => { setActiveCopperLayer(layer); setLayerPickerExpanded(false); }}
        style={{ "--layer-color": copperLayerColors[layer] } as React.CSSProperties}
        title={`Show ${layer}`}
      >
        <i aria-hidden="true" />
        <span>{layer}</span>
      </button>)}
      <button className={`aggregate ${activeCopperLayer === "All" ? "selected" : ""}`} onClick={() => { setActiveCopperLayer("All"); setLayerPickerExpanded(false); }}><i aria-hidden="true" /><span>All</span></button>
      <button className={`overview ${activeCopperLayer === "Overview" ? "selected" : ""}`} onClick={() => { setActiveCopperLayer("Overview"); setLayerPickerExpanded(false); }}><i aria-hidden="true" /><span>Overview</span></button>
    </div>
    <div className="layout-scale">VECTOR LAYOUT · {Math.round(sourceViewBox[2] / view.width * 100)}%</div>
  </div>;
}

export default memo(LayoutViewport);
