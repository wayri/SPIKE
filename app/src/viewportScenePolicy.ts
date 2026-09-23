export type ViewportSceneKind =
  | "substrate"
  | "region"
  | "mask"
  | "copper-zone"
  | "copper-track"
  | "copper-pad"
  | "via-face"
  | "via-barrel"
  | "drawing"
  | "component"
  | "picking"
  | "result"
  | "selection";

/** Resolve independent board/component roots once; parent visibility must not
 * undo a component toggle or a successful component load. */
export function boardSceneVisibility(options: {
  is3D: boolean; boardReady: boolean; componentsReady: boolean; split: boolean;
  layerFiltered: boolean; exploded: boolean; isolated: boolean;
  analysisOnly: boolean; resultsOnly: boolean;
  showModels: boolean; categoryFiltered: boolean; resultModelsVisible: boolean;
  missingModels: boolean;
}) {
  const o = options;
  const modelsRequested = o.is3D && o.showModels && o.resultModelsVisible && !o.resultsOnly;
  // Legacy single-file scenes cannot independently hide their component meshes.
  const legacyFiltered = !o.split && (!o.showModels || o.categoryFiltered || !o.resultModelsVisible);
  const importedBoard = o.is3D && o.boardReady && !o.resultsOnly && !o.analysisOnly
    && !o.isolated && !o.layerFiltered && !o.exploded && !legacyFiltered;
  const importedComponents = modelsRequested && o.split && o.componentsReady
    && (!o.isolated || o.analysisOnly);
  const proceduralComponents = modelsRequested && (!o.isolated || o.analysisOnly)
    && (o.missingModels || (!importedComponents && !(importedBoard && !o.split)));
  return {
    importedBoard, importedComponents, proceduralComponents,
    importedRoot: importedBoard || importedComponents,
    proceduralRoot: !o.resultsOnly && (!importedBoard || proceduralComponents),
  };
}

export type SceneBoundsMetrics = {
  radius: number;
  cameraDistance: number;
  cameraToBoundsCenter?: number;
};

export type ViewportRenderProfile = {
  fullPixelRatio: number;
  interactionPixelRatio: number;
  shadowMapSize: number;
  dynamicShadowUpdates: boolean;
  targetFps: number;
  largeScene: boolean;
};

type ResultOverlayState = {
  visible?: boolean;
  mode?: string;
} | null | undefined;

const safeIdentityPart = (value: string | undefined) => encodeURIComponent(value?.trim() || "global");

export function viewportSceneIdentity(
  kind: ViewportSceneKind,
  layer: string | undefined,
  sourceId: string,
) {
  return `spike:${kind}:${safeIdentityPart(layer)}:${safeIdentityPart(sourceId)}`;
}

export function viewportRenderOrder(
  kind: ViewportSceneKind,
  layer: string | undefined,
  copperLayers: readonly string[],
) {
  const copperIndex = Math.max(copperLayers.indexOf(layer ?? ""), 0);
  switch (kind) {
    case "substrate": return 0;
    case "region": return 4;
    case "mask": return layer?.startsWith("B.") ? 8 : 9;
    case "copper-zone": return 32 + copperIndex * 4;
    case "copper-track": return 33 + copperIndex * 4;
    case "copper-pad": return 34 + copperIndex * 4;
    case "via-face": return 35 + copperIndex * 4;
    case "via-barrel": return 168 + copperIndex;
    case "drawing": return 220;
    case "component": return 260;
    case "picking": return 500;
    case "result": return 600;
    case "selection": return 700;
  }
}

export function layerObjectVisible(
  layer: string | undefined,
  isComponentModel: boolean,
  visibleLayers: Readonly<Record<string, boolean>>,
) {
  if (isComponentModel) return true;
  if (!layer || layer === "through") return true;
  return visibleLayers[layer] !== false;
}

export function viaSpanVisible(
  startLayer: string | undefined,
  endLayer: string | undefined,
  copperLayers: readonly string[],
  visibleLayers: Readonly<Record<string, boolean>>,
) {
  if (!startLayer && !endLayer) return true;
  const start = copperLayers.indexOf(startLayer ?? "");
  const end = copperLayers.indexOf(endLayer ?? "");
  if (start < 0 || end < 0) {
    return layerObjectVisible(startLayer, false, visibleLayers)
      || layerObjectVisible(endLayer, false, visibleLayers);
  }
  const lower = Math.min(start, end);
  const upper = Math.max(start, end);
  return copperLayers.slice(lower, upper + 1).some(layer => visibleLayers[layer] !== false);
}

export function solverResultOverlayActive(
  result: unknown,
  visualization: ResultOverlayState,
) {
  return Boolean(result && visualization?.visible && visualization.mode
    && visualization.mode !== "geometry" && visualization.mode !== "impedance");
}

export function selectionPulseFactor(
  nowMs: number,
  reducedMotion: boolean,
  resultOverlayActive: boolean,
  selectionBlink = true,
) {
  if (!selectionBlink || reducedMotion || resultOverlayActive) return 1;
  return 0.24 + 0.76 * (0.5 + 0.5 * Math.sin(nowMs * 0.0022 - Math.PI / 2));
}

/**
 * Select conservative perspective planes from the geometry currently visible
 * to the camera. The near plane deliberately remains small enough to avoid
 * clipping probes, components, and thermal/EMI fixtures when the user orbits
 * close to the board, while the far plane still has a bounded relationship to
 * the visible scene rather than a fixed, low precision global value.
 */
export function adaptivePerspectiveClip({ radius, cameraDistance, cameraToBoundsCenter }: SceneBoundsMetrics) {
  const safeRadius = Math.max(radius, 0.25);
  const safeDistance = Math.max(cameraDistance, safeRadius * 0.1, 0.01);
  const sceneDistance = Math.max(cameraToBoundsCenter ?? safeDistance, 0.01);
  // Auxiliary thermal/EMI volumes can be orders of magnitude larger than the
  // board. Do not let their size push the near plane through a close board
  // inspection; logarithmic depth handles the resulting broader range.
  const near = Math.max(0.005, Math.min(safeDistance / 2400, safeRadius / 1600, 0.25));
  const far = Math.max(
    near + 250,
    sceneDistance + safeRadius * 6,
    safeDistance * 4,
    safeRadius * 24,
  );
  return { near, far };
}

/**
 * OrbitControls needs a generous, scene-relative dolly range. A fixed board-
 * sized ceiling makes enclosure, chamber, and multi-board scenes feel as if
 * they are trapped inside an invisible box.
 */
export function adaptiveMaximumCameraDistance(radius: number) {
  return Math.max(10_000, Math.max(radius, 1) * 160);
}

/**
 * Keep high-density boards responsive without changing scene semantics. The
 * profile only adjusts presentation cost: pixel ratio, shadow resolution, and
 * frame cadence. Geometry, picking, and solver-result data remain unchanged.
 */
export function viewportRenderProfile(objectCount: number, devicePixelRatio: number): ViewportRenderProfile {
  const largeScene = objectCount >= 12_000;
  const ultraDenseScene = objectCount >= 250_000;
  const fullPixelRatio = Math.min(Math.max(devicePixelRatio, 0.75), largeScene ? 1 : 1.25);
  return {
    fullPixelRatio,
    interactionPixelRatio: Math.min(fullPixelRatio, largeScene ? 0.7 : 0.85),
    shadowMapSize: largeScene ? 512 : 1024,
    dynamicShadowUpdates: !largeScene,
    // The old 24/30 FPS hard cap made capable systems look underutilized and
    // guaranteed visibly sluggish camera motion even when frame time was low.
    // Ultra-dense scenes retain a conservative ceiling while ordinary and
    // large boards can use the available GPU headroom.
    targetFps: ultraDenseScene ? 30 : largeScene ? 45 : 60,
    largeScene,
  };
}

// The procedural mask is only a context layer; it has no pad openings. Keeping
// it faint prevents that approximation from visually replacing copper below it.
export const PROCEDURAL_SOLDERMASK_OPACITY = 0.22;

export type SubstrateZBounds = { bottom: number; top: number; depth: number };

/** Keep the display-only substrate between the outer copper centres. */
export function substrateZBounds(
  topCopperZ: number | undefined,
  bottomCopperZ: number | undefined,
  boardThickness: number,
  clearance: number,
): SubstrateZBounds {
  const thickness = Math.max(Math.abs(boardThickness), 1e-6);
  const gap = Math.max(clearance, 1e-6);
  const copper = [topCopperZ, bottomCopperZ].filter((value): value is number => Number.isFinite(value));
  if (copper.length >= 2 && Math.abs(copper[0] - copper[1]) > gap * 2) {
    const bottom = Math.min(copper[0], copper[1]) + gap;
    const top = Math.max(copper[0], copper[1]) - gap;
    return { bottom, top, depth: top - bottom };
  }
  if (copper.length) {
    const layer = copper[0];
    // A single copper plane has no pair to enclose. Put the visual substrate
    // on the larger available side and stop before the conductor centre.
    const nominalBottom = -thickness / 2;
    const nominalTop = thickness / 2;
    const below = Math.max(layer - gap - nominalBottom, 0);
    const above = Math.max(nominalTop - layer - gap, 0);
    if (below >= above && below > 0) {
      const bottom = nominalBottom;
      const top = layer - gap;
      return { bottom, top, depth: top - bottom };
    }
    if (above > 0) {
      const bottom = layer + gap;
      const top = nominalTop;
      return { bottom, top, depth: top - bottom };
    }
  }
  return { bottom: -thickness / 2, top: thickness / 2, depth: thickness };
}
