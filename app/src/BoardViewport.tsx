import { memo, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { snapshotEmiDut } from "./emiChamber";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { ViewHelper } from "three/examples/jsm/helpers/ViewHelper.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRMLLoader } from "three/examples/jsm/loaders/VRMLLoader.js";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { ParsedBoard, ParsedComponent, ParsedPad, Point } from "./boardParser";
import { resolveBoardCopperLayers } from "./copperLayerSelection";
import { buildContourGrid } from "./contourField";
import { sharedVertexValues, resultSampleForHit, resultHitOccluded } from "./resultSurfaceInterpolation";
import LayoutViewport from "./LayoutViewport";
import type { Viewport2DState, Viewport3DCameraState, ViewportRestoreCommand } from "./workspaceState";
import type { MeshCell, ResultVisualization, ScalarSample, SolverResultBundle } from "./analysisResults";
import { layerCssColor, layerThreeColor } from "./layerPalette";
import { thermalVolume, ThermalScenarioView, ThermalSceneVisibility } from "./thermalScene";
import { numericExtent, numericMaximum } from "./numericRange";
import { meshCellEdgeIndexes, meshCellFaceVertices } from "./meshTopology";
import { pointOnResultConductor, resultDatumFitsConductor, resultFaceTriangleIndices } from "./resultGeometryMask";
import { resultDatumLayers, resultLayerIsVisible, selectedDatumLayers } from "./resultLayerSelection";
import { thermalScenePointMm } from "./thermalCoordinates";
import { normalizeThermalFieldResult, thermalFieldColor, thermalFieldExtent, thinThermalFieldSamples, type ThermalFieldName } from "./thermalResultFields";
import { boardSceneFormat, loadScenesBounded, loadSceneWithRetry, sceneLoadErrorMessage } from "./modelSceneLoader";
import { disposeScene, SceneResourceCache } from "./sceneResourceCache";
import { trackCapsuleDimensions } from "./trackGeometry";
import { buildAssemblySectionClippingPlanes, DEFAULT_ASSEMBLY_SECTION } from "./mcadAssembly";
import type { AssemblyPartViewportLoadState, AssemblySceneModel, AssemblySection, AssemblySelectorPreviewModel } from "./mcadAssembly";
import type { VirtualBoardVisual, VirtualHarnessVisual } from "./harnessVisualization";
import type { TopologyReference } from "./assemblyPackageShapes";
import { formatViewportAxisTick, formatViewportResultTick, piImpedanceSamples, spatiallyThinSamples, viewportResultField } from "./viewportResultFields";
import {
  adaptiveMaximumCameraDistance,
  adaptivePerspectiveClip,
  layerObjectVisible,
  PROCEDURAL_SOLDERMASK_OPACITY,
  substrateZBounds,
  selectionPulseFactor,
  solverResultOverlayActive,
  viaSpanVisible,
  viewportRenderProfile,
  viewportRenderOrder,
  viewportSceneIdentity,
  type ViewportSceneKind,
  boardSceneVisibility,
} from "./viewportScenePolicy";
import { KeyedResourcePool, partitionComponentProxies, takeWithinCostBudget, throughHoleComponentRefs } from "./viewportPerformance";
import { buildProceduralComponentInstances, updateProceduralComponentInstances, type PlaceholderInstance } from "./proceduralComponentInstances";
import { deriveComponentPlaceholder } from "./componentPlaceholder";
import {
  buildBoundsSpatialIndex, nearbyPointCandidates, nearestPointSample, pointSpatialIndex,
  rayBoundsCandidates, type BoundsSpatialIndex, type SpatialBounds,
} from "./viewportSpatialIndex";

export type BoardObject = {
  id: string;
  type: "component" | "trace" | "zone" | "via" | "pad" | "terminal";
  name: string;
  ref?: string;
  net?: string;
  layer?: string;
  model?: boolean;
  mount?: "smd" | "tht";
  position?: [number, number];
  layers?: string[];
  probeKind?: "universal" | "voltage" | "current" | "power" | "impedance";
};

function assemblySectionClippingPlanes(
  section: AssemblySection,
  transform: { centerX: number; centerY: number; scale: number },
): THREE.Plane[] {
  return buildAssemblySectionClippingPlanes(section, transform).map(({ normal, point }) =>
    new THREE.Plane().setFromNormalAndCoplanarPoint(new THREE.Vector3(...normal), new THREE.Vector3(...point)));
}

export type AnalysisTerminalMarker = {
  id: string;
  name: string;
  role: "source" | "load" | "source_return" | "load_return";
  position: Point;
  net: string;
  layer?: string;
  layers: string[];
  value: string;
  anchorType?: string;
};

export type RenderTelemetry = {
  fps: number;
  frameTimeMs: number;
  drawCalls: number;
  triangles: number;
  geometries: number;
  textures: number;
  pixelRatio: number;
};

export type ModelLoadStatus = {
  board: "none" | "loading" | "ready" | "failed";
  components: "none" | "loading" | "ready" | "failed";
  assembly: "none" | "loading" | "ready" | "failed";
  missingCount: number;
  missingRefs: string[];
  metrics: string;
  error?: string;
};

export type SelectionFilter = "all" | "part" | "net";
export type ViewportContextRequest = {
  clientX: number;
  clientY: number;
  object: BoardObject | null;
  focusPoint?: [number, number, number];
};
export type HoverProbeTarget = {
  clientX: number;
  clientY: number;
  position: Point;
  object: BoardObject | null;
  worldPosition?: [number, number, number];
  resultSample?: ScalarSample;
  resultField?: { label: string; unit: string };
};
export type ViewportHoverTarget = {
  kind: "net" | "object";
  id?: string;
  type?: BoardObject["type"];
  net?: string;
  ref?: string;
  layer?: string;
  position?: Point;
  label: string;
};
export const previewViewportTarget = (target: ViewportHoverTarget | null) => {
  window.dispatchEvent(new CustomEvent("spike-viewport-hover-preview", { detail: target }));
};

type ViewMode = "2D" | "3D";
type Props = {
  onEmiScene?: (scene: THREE.Group) => void;
  viewMode: ViewMode;
  visibleLayers: Record<string, boolean>;
  layerOpacity: Record<string, number>;
  layerSeparation: number;
  showVias: boolean;
  showNetNames?: boolean;
  showModels: boolean;
  showSmdModels: boolean;
  showThtModels: boolean;
  assemblyModels?: AssemblySceneModel[];
  assemblySelectorPreviews?: AssemblySelectorPreviewModel[];
  virtualBoards?: VirtualBoardVisual[];
  selectedBoardInstanceId?: string | null;
  onBoardInstanceSelect?: (board: VirtualBoardVisual) => void;
  virtualHarnesses?: VirtualHarnessVisual[];
  selectedHarnessId?: string | null;
  onHarnessSelect?: (harness: VirtualHarnessVisual) => void;
  topologySelectorActive?: boolean;
  selectedTopologyId?: string | null;
  onTopologySelect?: (reference: TopologyReference) => void;
  isolatedAssemblyPartId?: string | null;
  assemblySection?: AssemblySection;
  navigationMode: "orbit" | "pan";
  navigationInertia: boolean;
  showAxes?: boolean;
  selectionBlink?: boolean;
  cameraCommand: string;
  viewportRestore?: ViewportRestoreCommand | null;
  selectionFilter: SelectionFilter;
  selectedId: string | null;
  selectedPosition?: Point;
  selectedNet?: string | null;
  isolatedNet?: string | null;
  analysisResult?: SolverResultBundle | null;
  resultVisualization?: ResultVisualization;
  analysisNets?: string[];
  probes?: BoardObject[];
  showProbes?: boolean;
  hoverProbeEnabled?: boolean;
  hoverProbeKind?: NonNullable<BoardObject["probeKind"]>;
  terminalMarkers?: AnalysisTerminalMarker[];
  thermalScenario?: ThermalScenarioView | null;
  thermalVisibility?: ThermalSceneVisibility;
  board?: ParsedBoard | null;
  onSelect: (object: BoardObject) => void;
  onHoverProbe?: (target: HoverProbeTarget | null) => void;
  onContextMenu?: (request: ViewportContextRequest) => void;
  onOrbitCenter?: (position: [number, number, number]) => void;
  onCamera: (camera: Viewport3DCameraState) => void;
  onLayoutView?: (view: Viewport2DState) => void;
  onTelemetry?: (telemetry: RenderTelemetry) => void;
  onModelStatus?: (status: ModelLoadStatus) => void;
  onAssemblyPartViewportStatus?: (states: Record<string, AssemblyPartViewportLoadState>) => void;
};

type HoverProbeMeasurement = {
  voltage?: number;
  drop?: number;
  current?: number;
  density?: number;
  power?: number;
  resistance?: number;
  inductance?: number | null;
  capacitance?: number | null;
  impedance?: number;
  impedanceSource?: "v_over_i" | "network";
  impedanceFrequency?: number;
  resolution: Partial<Record<"voltage" | "drop" | "current" | "density" | "power", number>>;
  sampleDistanceMm?: number;
};

type LocalScalar = { value: number; resolution?: number; distanceMm: number };

function localScalar(samples: ScalarSample[], target: HoverProbeTarget): LocalScalar | undefined {
  if (!samples.length) return undefined;
  const object = target.object;
  if (object?.type === "component" && !object.net) return undefined;
  const index = pointSpatialIndex(samples);
  const nearby = nearbyPointCandidates(samples, target.position[0], target.position[1]);
  const hasElementIds = Boolean(object?.id && nearby.some(sample => sample.element_id === object.id));
  const hasNetMetadata = nearby.some(sample => Boolean(sample.net));
  const hasLayerMetadata = nearby.some(sample => Boolean(sample.layer));
  const contextual = nearby.filter(sample => {
    if (hasElementIds && sample.element_id !== object?.id) return false;
    if (!hasElementIds && object?.net && hasNetMetadata && sample.net !== object.net) return false;
    if (object?.layer && object.layer !== "through" && hasLayerMetadata
      && sample.layer !== object.layer && sample.layer !== "through") return false;
    return Number.isFinite(sample.value);
  }).map(sample => ({
    sample,
    distance: Math.hypot(sample.x_mm - target.position[0], sample.y_mm - target.position[1]),
  })).sort((left, right) => left.distance - right.distance);
  const nearest = contextual[0];
  const maximumDistance = Math.max(0.12, index.cellSize * (object?.type === "zone" ? 4 : 2.6));
  if (!nearest || nearest.distance > maximumDistance) return undefined;
  if (nearest.distance < 1e-7) return { value: nearest.sample.value, distanceMm: 0 };
  const interpolationRadius = Math.max(index.cellSize * 1.8, nearest.distance * 2.25);
  const local = contextual.filter(candidate => candidate.distance <= interpolationRadius).slice(0, 6);
  let weightedValue = 0; let totalWeight = 0;
  local.forEach(candidate => {
    const weight = 1 / Math.max(candidate.distance * candidate.distance, 1e-12);
    weightedValue += candidate.sample.value * weight; totalWeight += weight;
  });
  const values = [...new Set(local.map(candidate => candidate.sample.value))].sort((a, b) => a - b);
  let resolution: number | undefined;
  for (let indexValue = 1; indexValue < values.length; indexValue += 1) {
    const difference = Math.abs(values[indexValue] - values[indexValue - 1]);
    if (difference > 0 && (resolution === undefined || difference < resolution)) resolution = difference;
  }
  return { value: totalWeight ? weightedValue / totalWeight : nearest.sample.value, resolution, distanceMm: nearest.distance };
}

function measureHoverProbe(result: SolverResultBundle | null | undefined, target: HoverProbeTarget, impedanceFrequencyHz?: number | null): HoverProbeMeasurement {
  if (!result) return { resolution: {} };
  const voltageSample = localScalar(result.scalar_fields.voltage_v, target);
  const dropSample = localScalar(result.scalar_fields.voltage_drop_v, target);
  const currentSample = localScalar(result.scalar_fields.current_a, target);
  const densitySample = localScalar(result.scalar_fields.current_density_a_mm2, target);
  const powerSample = localScalar(result.scalar_fields.power_loss_w, target);
  const operatingImpedanceSample = localScalar(result.scalar_fields.operating_point_impedance_ohm, target);
  const voltage = voltageSample?.value;
  const drop = dropSample?.value;
  const current = currentSample?.value;
  const density = densitySample?.value;
  const solvedPower = powerSample?.value;
  const net = target.object?.net;
  const parasitic = net ? result.parasitics.find(entry => entry.net === net) : undefined;
  const impedancePoint = parasitic?.impedance?.length
    ? [...parasitic.impedance].sort((left, right) => Math.abs(left.frequency_hz - (impedanceFrequencyHz ?? left.frequency_hz)) - Math.abs(right.frequency_hz - (impedanceFrequencyHz ?? right.frequency_hz)))[0]
    : undefined;
  const mappedCandidate = result.probes.filter(probe => probe.status === "mapped" && probe.position_mm
    && (!net || probe.net === net)).map(probe => ({ probe, distance: Math.hypot(probe.position_mm![0] - target.position[0], probe.position_mm![1] - target.position[1]) }))
    .sort((left, right) => left.distance - right.distance)[0];
  const mappedProbe = mappedCandidate && (mappedCandidate.probe.id === target.object?.id || mappedCandidate.distance <= 0.5)
    ? mappedCandidate.probe : undefined;
  const legacyLocalImpedance = voltage !== undefined && current !== undefined && Math.abs(current) > 1e-18
    ? Math.abs(voltage / current)
    : undefined;
  const localImpedance = operatingImpedanceSample?.value ?? legacyLocalImpedance;
  return {
    voltage: voltage ?? mappedProbe?.voltage_v,
    drop: drop ?? mappedProbe?.voltage_drop_v,
    current: current ?? mappedProbe?.peak_adjacent_current_a,
    density: density ?? mappedProbe?.peak_adjacent_current_density_a_mm2,
    power: solvedPower ?? mappedProbe?.adjacent_power_loss_w ?? (voltage !== undefined && current !== undefined ? voltage * current : undefined),
    resistance: mappedProbe?.local_series_resistance_ohm ?? parasitic?.resistance_ohm,
    inductance: parasitic?.inductance_h,
    capacitance: parasitic?.capacitance_f,
    impedance: localImpedance ?? impedancePoint?.magnitude_ohm,
    impedanceSource: localImpedance !== undefined ? "v_over_i" : impedancePoint ? "network" : undefined,
    impedanceFrequency: impedancePoint?.frequency_hz,
    resolution: {
      voltage: voltageSample?.resolution,
      drop: dropSample?.resolution,
      current: currentSample?.resolution,
      density: densitySample?.resolution,
      power: powerSample?.resolution,
    },
    sampleDistanceMm: [voltageSample, dropSample, currentSample, densitySample, powerSample]
      .filter((sample): sample is LocalScalar => Boolean(sample))
      .reduce<number | undefined>((closest, sample) => closest === undefined ? sample.distanceMm : Math.min(closest, sample.distanceMm), undefined),
  };
}

function viewportScalarSamples(result: SolverResultBundle, mode: string): ScalarSample[] {
  if (mode === "voltage") return result.scalar_fields.voltage_v;
  if (mode === "voltage_drop") return result.scalar_fields.voltage_drop_v;
  if (mode === "current") return result.scalar_fields.current_a;
  if (mode === "current_density") return result.scalar_fields.current_density_a_mm2;
  if (mode === "power_loss") return result.scalar_fields.power_loss_w;
  if (mode === "via_stress") return result.scalar_fields.via_current_density_a_mm2;
  if (mode === "impedance") {
    return result.scalar_fields.operating_point_impedance_ohm.length
      ? result.scalar_fields.operating_point_impedance_ohm
      : piImpedanceSamples(result.scalar_fields.voltage_v, result.scalar_fields.current_a);
  }
  return [];
}

function engineeringValue(value: number | null | undefined, unit: string, scale = 1, resolution?: number) {
  if (value === undefined || value === null || !Number.isFinite(value)) return null;
  const scaled = value * scale;
  const magnitude = Math.abs(scaled);
  const scaledResolution = resolution === undefined ? undefined : Math.abs(resolution * scale);
  if ((magnitude > 0 && magnitude < 1e-7) || magnitude >= 1e9) return `${scaled.toExponential(5)} ${unit}`;
  const decimals = scaledResolution && Number.isFinite(scaledResolution) && scaledResolution > 0
    ? Math.max(0, Math.min(9, Math.ceil(-Math.log10(scaledResolution)) + 1))
    : magnitude >= 100 ? 3 : magnitude >= 1 ? 5 : 7;
  return `${scaled.toFixed(decimals)} ${unit}`;
}

const defaultLayerVisible = (name: string) =>
  name.endsWith(".Cu") || name.endsWith(".Mask") || name.endsWith(".SilkS") || name === "Edge.Cuts";

function material(color: number, options: { metalness?: number; roughness?: number; opacity?: number; emissive?: number } = {}) {
  const opacity = options.opacity ?? 1;
  return new THREE.MeshStandardMaterial({
    color,
    metalness: options.metalness ?? 0.15,
    roughness: options.roughness ?? 0.62,
    emissive: options.emissive ?? 0,
    transparent: opacity < 1,
    opacity,
    depthWrite: opacity >= 0.999,
    polygonOffset: opacity < 1,
    polygonOffsetFactor: opacity < 1 ? -2 : 0,
    polygonOffsetUnits: opacity < 1 ? -4 : 0,
    side: THREE.DoubleSide,
  });
}

function identifySceneObject(
  object: THREE.Object3D,
  kind: ViewportSceneKind,
  layer: string | undefined,
  sourceId: string,
  copperLayers: readonly string[],
) {
  const identity = viewportSceneIdentity(kind, layer, sourceId);
  const renderOrder = viewportRenderOrder(kind, layer, copperLayers);
  object.name = identity;
  object.renderOrder = renderOrder;
  object.userData = {
    ...object.userData,
    spikeSceneIdentity: identity,
    spikeRenderOrder: renderOrder,
  };
  if (object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.LineSegments) {
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    materials.forEach((entry, index) => {
      const materialIdentity = `${identity}:material:${index}`;
      entry.name = materialIdentity;
      entry.userData = {
        ...entry.userData,
        spikeMaterialIdentity: materialIdentity,
        spikeLayer: layer ?? null,
      };
    });
  }
  return object;
}

const clearGroup = disposeScene;
const gltfSceneCache = new SceneResourceCache(async url => (await new GLTFLoader().loadAsync(url)).scene);
const cloneCachedGltfScene = (url: string) => gltfSceneCache.clone(url);

function batchProceduralGeometry(root: THREE.Group, copperLayers: readonly string[]) {
  type Batch = {
    objects: THREE.Mesh[];
    geometries: THREE.BufferGeometry[];
    material: THREE.Material;
    layer?: string;
    kind: ViewportSceneKind;
    data: Record<string, unknown>;
  };
  root.updateMatrixWorld(true);
  const batches = new Map<string, Batch>();
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh) || Array.isArray(object.material)) return;
    const data = object.userData as Partial<BoardObject> & {
      viaFaceLayer?: string; viaBarrel?: boolean; viaStartLayer?: string; viaEndLayer?: string;
      pickingProxy?: boolean; model?: boolean;
    };
    if (data.pickingProxy || data.model || !["trace", "zone", "pad", "via"].includes(data.type ?? "")) return;
    const layer = data.viaFaceLayer ?? data.layer;
    const kind: ViewportSceneKind = data.type === "trace" ? "copper-track"
      : data.type === "zone" ? "copper-zone"
        : data.type === "pad" ? "copper-pad"
          : data.viaBarrel ? "via-barrel" : "via-face";
    const material = object.material as THREE.Material;
    const standard = material instanceof THREE.MeshStandardMaterial ? material : null;
    const attributes = Object.entries(object.geometry.attributes as Record<string, THREE.BufferAttribute | THREE.InterleavedBufferAttribute>)
      .map(([name, attribute]) => `${name}:${attribute.itemSize}:${attribute.normalized ? 1 : 0}`)
      .sort().join(",");
    const key = [kind, layer ?? "", data.viaStartLayer ?? "", data.viaEndLayer ?? "",
      object.geometry.index ? "indexed" : "plain", attributes, material.type,
      standard?.color.getHexString() ?? "", standard?.metalness ?? "", standard?.roughness ?? "",
      material.opacity, material.transparent, material.depthWrite].join("|");
    const batch: Batch = batches.get(key) ?? {
      objects: [], geometries: [], material: material.clone(), layer, kind,
      data: {
        layer, via: data.type === "via", viaFaceLayer: data.viaFaceLayer,
        viaBarrel: data.viaBarrel, viaStartLayer: data.viaStartLayer, viaEndLayer: data.viaEndLayer,
        batchedDisplay: true,
      },
    };
    const geometry = object.geometry.clone();
    geometry.applyMatrix4(object.matrixWorld);
    batch.objects.push(object);
    batch.geometries.push(geometry);
    batches.set(key, batch);
  });
  let sourceMeshes = 0;
  let displayMeshes = 0;
  const retiredMaterials = new Set<THREE.Material>();
  batches.forEach((batch, batchIndex) => {
    const merged = mergeGeometries(batch.geometries, false);
    if (!merged) {
      batch.geometries.forEach(geometry => geometry.dispose());
      batch.material.dispose();
      return;
    }
    const mesh = new THREE.Mesh(merged, batch.material);
    mesh.userData = batch.data;
    identifySceneObject(mesh, batch.kind, batch.layer, `procedural-batch-${batchIndex + 1}`, copperLayers);
    root.add(mesh);
    displayMeshes += 1;
    sourceMeshes += batch.objects.length;
    batch.objects.forEach(object => {
      object.removeFromParent();
      if (!object.geometry.userData.spikePickingOwner) object.geometry.dispose();
      retiredMaterials.add(object.material as THREE.Material);
    });
    batch.geometries.forEach(geometry => geometry.dispose());
  });
  retiredMaterials.forEach(entry => entry.dispose());
  root.children.filter(child => child instanceof THREE.Group && child.userData.via && !child.children.length)
    .forEach(child => child.removeFromParent());
  return { sourceMeshes, displayMeshes };
}

function rowMajorMatrix(values: number[]): THREE.Matrix4 {
  return new THREE.Matrix4().set(
    values[0], values[1], values[2], values[3],
    values[4], values[5], values[6], values[7],
    values[8], values[9], values[10], values[11],
    values[12], values[13], values[14], values[15],
  );
}

function matrixToRowMajor(matrix: THREE.Matrix4): number[] {
  const value = matrix.elements;
  return [
    value[0], value[4], value[8], value[12],
    value[1], value[5], value[9], value[13],
    value[2], value[6], value[10], value[14],
    value[3], value[7], value[11], value[15],
  ];
}

type BoardSurfaceKind = "copper" | "silkscreen" | "soldermask" | "substrate" | "unknown";

function classifyBoardSurface(material: THREE.MeshStandardMaterial, semanticName: string): BoardSurfaceKind {
  const semantic = `${semanticName} ${material.name}`.toLowerCase();
  if (semantic.includes("copper")) return "copper";
  if (semantic.includes("silkscreen")) return "silkscreen";
  if (semantic.includes("soldermask")) return "soldermask";
  if (semantic.includes("pcb") || semantic.includes("substrate")) return "substrate";

  const { r, g, b } = material.color;
  if (material.metalness >= 0.75) return "copper";
  if (r >= 0.75 && g >= 0.75 && b >= 0.75 && material.opacity <= 0.95) return "silkscreen";
  if (material.opacity <= 0.93 && g > r * 1.45 && g > b * 1.18) return "soldermask";
  if (material.opacity >= 0.94 && material.roughness >= 0.7) return "substrate";
  return "unknown";
}

function consolidateStaticModel(
  source: THREE.Object3D,
  shadows: { cast: boolean; receive: boolean },
): { model: THREE.Group; sourceMeshes: number; displayMeshes: number } {
  source.updateMatrixWorld(true);
  const model = new THREE.Group();
  const repeated = new Map<string, THREE.Mesh[]>();
  const instancedSources = new Set<THREE.Mesh>();
  source.traverse(object => {
    if (!(object instanceof THREE.Mesh) || object instanceof THREE.SkinnedMesh
      || object instanceof THREE.InstancedMesh || Array.isArray(object.material)
      || object.material.transparent || object.morphTargetInfluences?.length
      || object.matrixWorld.determinant() <= 0) return;
    const key = `${object.geometry.uuid}|${object.material.uuid}|${object.renderOrder}|${object.userData.componentMount ?? ""}|${object.userData.componentSide ?? ""}`;
    const group = repeated.get(key);
    if (group) group.push(object); else repeated.set(key, [object]);
  });
  const instanceGeometries = new Map<THREE.BufferGeometry, THREE.BufferGeometry>();
  for (const objects of repeated.values()) {
    if (objects.length < 4) continue;
    const first = objects[0];
    let geometry = instanceGeometries.get(first.geometry);
    if (!geometry) { geometry = first.geometry.clone(); instanceGeometries.set(first.geometry, geometry); }
    // Bounded instance buffers preserve culling granularity on very large boards.
    for (let start = 0; start < objects.length; start += 2048) {
      const count = Math.min(2048, objects.length - start);
      const mesh = new THREE.InstancedMesh(geometry, first.material, count);
      for (let index = 0; index < count; index += 1) {
        const object = objects[start + index];
        mesh.setMatrixAt(index, object.matrixWorld);
        instancedSources.add(object);
      }
      mesh.instanceMatrix.needsUpdate = true;
      mesh.computeBoundingBox();
      mesh.computeBoundingSphere();
      mesh.castShadow = shadows.cast;
      mesh.receiveShadow = shadows.receive;
      mesh.name = `${first.name}:instances:${start}`;
      mesh.renderOrder = first.renderOrder;
      mesh.userData = { ...first.userData, spikeSceneIdentity: mesh.name, spikeRenderOrder: mesh.renderOrder };
      model.add(mesh);
    }
  }
  const batches = new Map<string, {
    material: THREE.Material;
    geometries: THREE.BufferGeometry[];
    identity: string;
    renderOrder: number;
    userData: Record<string, unknown>;
  }>();
  const passthrough: THREE.Mesh[] = [];
  let sourceMeshes = 0;

  source.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return;
    sourceMeshes += 1;
    if (instancedSources.has(object)) return;
    const geometry = object.geometry.clone();
    geometry.applyMatrix4(object.matrixWorld);
    const requiresSorting = (entry: THREE.Material) => entry.transparent
      && !(entry instanceof THREE.MeshStandardMaterial && entry.alphaHash);
    const transparent = Array.isArray(object.material)
      ? object.material.some(requiresSorting)
      : requiresSorting(object.material);
    if (Array.isArray(object.material) || transparent) {
      const mesh = new THREE.Mesh(geometry, object.material);
      mesh.castShadow = shadows.cast;
      mesh.receiveShadow = shadows.receive;
      mesh.name = object.name;
      mesh.userData = { ...object.userData };
      mesh.renderOrder = object.renderOrder;
      passthrough.push(mesh);
      return;
    }
    const attributes = Object.entries(geometry.attributes as Record<string, THREE.BufferAttribute | THREE.InterleavedBufferAttribute>)
      .map(([name, attribute]) => `${name}:${attribute.itemSize}:${attribute.normalized ? 1 : 0}`)
      .sort()
      .join(",");
    const key = `${object.material.uuid}|${geometry.index ? "indexed" : "plain"}|${attributes}|${object.userData.componentMount ?? ""}|${object.userData.componentSide ?? ""}`;
    const batch: {
      material: THREE.Material;
      geometries: THREE.BufferGeometry[];
      identity: string;
      renderOrder: number;
      userData: Record<string, unknown>;
    } = batches.get(key) ?? {
      material: object.material,
      geometries: [] as THREE.BufferGeometry[],
      identity: object.name,
      renderOrder: object.renderOrder,
      userData: { ...object.userData },
    };
    batch.geometries.push(geometry);
    batches.set(key, batch);
  });

  batches.forEach(({ material: batchMaterial, geometries, identity, renderOrder, userData }) => {
    const merged = mergeGeometries(geometries, false);
    if (merged) {
      const mesh = new THREE.Mesh(merged, batchMaterial);
      mesh.castShadow = shadows.cast;
      mesh.receiveShadow = shadows.receive;
      mesh.name = identity;
      mesh.userData = { ...userData, spikeSceneIdentity: identity, spikeRenderOrder: renderOrder };
      mesh.renderOrder = renderOrder;
      model.add(mesh);
      geometries.forEach((geometry) => geometry.dispose());
    } else {
      geometries.forEach((geometry, index) => {
        const mesh = new THREE.Mesh(geometry, batchMaterial);
        mesh.castShadow = shadows.cast;
        mesh.receiveShadow = shadows.receive;
        mesh.name = `${identity}:part:${index}`;
        mesh.userData = { ...userData, spikeSceneIdentity: mesh.name, spikeRenderOrder: renderOrder };
        mesh.renderOrder = renderOrder;
        model.add(mesh);
      });
    }
  });
  passthrough.forEach((mesh) => model.add(mesh));

  const retiredGeometries = new Set<THREE.BufferGeometry>();
  source.traverse(object => { if (object instanceof THREE.Mesh) retiredGeometries.add(object.geometry); });
  retiredGeometries.forEach(geometry => geometry.dispose());
  return { model, sourceMeshes, displayMeshes: model.children.length };
}

function prepareImportedScene(scene: THREE.Object3D, kind: "board" | "components") {
  const clonedMaterials = new Map<string, THREE.Material>();
  let materialIndex = 0;
  let meshIndex = 0;
  const independentMaterial = (source: THREE.Material) => {
    const existing = clonedMaterials.get(source.uuid);
    if (existing) return existing;
    const clone = source.clone();
    const identity = viewportSceneIdentity(
      kind === "components" ? "component" : "region",
      undefined,
      `${kind}-material-${materialIndex++}-${source.name || "unnamed"}`,
    );
    clone.name = `${identity}:material:0`;
    clone.userData = { ...clone.userData, spikeMaterialIdentity: clone.name };
    clonedMaterials.set(source.uuid, clone);
    source.dispose();
    return clone;
  };
  scene.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return;
    object.material = Array.isArray(object.material)
      ? object.material.map(independentMaterial)
      : independentMaterial(object.material);
    object.castShadow = kind === "components";
    object.receiveShadow = true;
    const semanticName = object.name.toLowerCase();
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    let sceneKind: ViewportSceneKind = kind === "components" ? "component" : "region";
    materials.forEach((entry) => {
      entry.side = THREE.DoubleSide;
      if (entry instanceof THREE.MeshStandardMaterial && kind === "board") {
        const surface = classifyBoardSurface(entry, semanticName);
        if (surface === "copper") {
          sceneKind = "copper-zone";
          entry.color.setHex(0xc48832);
          entry.metalness = 0.64;
          entry.roughness = 0.34;
          entry.opacity = 1;
          entry.transparent = false;
        } else if (surface === "silkscreen") {
          sceneKind = "drawing";
          entry.color.setHex(0xe8e5da);
          entry.metalness = 0;
          entry.roughness = 0.72;
          entry.opacity = 1;
          entry.transparent = false;
        } else if (surface === "soldermask") {
          sceneKind = "mask";
          entry.color.setHex(0x08623c);
          entry.metalness = 0;
          entry.roughness = 0.5;
          entry.opacity = 0.76;
          entry.transparent = true;
          entry.alphaHash = false;
          entry.alphaToCoverage = false;
          entry.depthWrite = false;
          entry.polygonOffset = true;
          entry.polygonOffsetFactor = -1;
          entry.polygonOffsetUnits = -2;
          object.receiveShadow = false;
        } else if (surface === "substrate") {
          sceneKind = "substrate";
          entry.color.setHex(0x15382d);
          entry.metalness = 0;
          entry.roughness = 0.82;
          entry.opacity = 1;
          entry.transparent = false;
        }
      } else if (entry instanceof THREE.MeshStandardMaterial && kind === "components") {
        entry.roughness = Math.max(entry.roughness, 0.34);
        entry.metalness = Math.min(entry.metalness, 0.72);
      }
      const alphaHashed = entry instanceof THREE.MeshStandardMaterial && entry.alphaHash;
      entry.depthWrite = alphaHashed || !entry.transparent && entry.opacity >= 0.999;
      if (!alphaHashed && (entry.transparent || entry.opacity < 0.999) && !entry.polygonOffset) {
        entry.polygonOffset = true;
        entry.polygonOffsetFactor = -2;
        entry.polygonOffsetUnits = -4;
      }
      if ("shininess" in entry && typeof entry.shininess === "number") entry.shininess = Math.min(entry.shininess, 80);
      entry.needsUpdate = true;
    });
    const identity = viewportSceneIdentity(sceneKind, undefined, `${kind}-mesh-${meshIndex++}-${object.name || "unnamed"}`);
    object.name = identity;
    object.userData = { ...object.userData, spikeSceneIdentity: identity };
    object.renderOrder = viewportRenderOrder(sceneKind, undefined, []);
  });
  return consolidateStaticModel(scene, {
    cast: kind === "components",
    receive: true,
  });
}

function pathFromPoints(points: THREE.Vector2[], closed = true): THREE.Shape {
  const shape = new THREE.Shape();
  if (!points.length) return shape;
  shape.moveTo(points[0].x, points[0].y);
  points.slice(1).forEach((point) => shape.lineTo(point.x, point.y));
  if (closed) shape.closePath();
  return shape;
}

function capsulePath(width: number, height: number): THREE.Shape {
  const horizontal = width >= height;
  const radius = Math.min(width, height) / 2;
  const shape = new THREE.Shape();
  if (horizontal) {
    const half = Math.max(width / 2 - radius, 0);
    shape.moveTo(-half, -radius);
    shape.lineTo(half, -radius);
    shape.absarc(half, 0, radius, -Math.PI / 2, Math.PI / 2, false);
    shape.lineTo(-half, radius);
    shape.absarc(-half, 0, radius, Math.PI / 2, Math.PI * 1.5, false);
  } else {
    const half = Math.max(height / 2 - radius, 0);
    shape.moveTo(-radius, -half);
    shape.absarc(0, -half, radius, Math.PI, 0, false);
    shape.lineTo(radius, half);
    shape.absarc(0, half, radius, 0, Math.PI, false);
  }
  shape.closePath();
  return shape;
}

function roundedRectanglePath(width: number, height: number, radius: number): THREE.Shape {
  const r = Math.min(radius, width / 2, height / 2);
  const shape = new THREE.Shape();
  shape.moveTo(-width / 2 + r, -height / 2);
  shape.lineTo(width / 2 - r, -height / 2);
  shape.quadraticCurveTo(width / 2, -height / 2, width / 2, -height / 2 + r);
  shape.lineTo(width / 2, height / 2 - r);
  shape.quadraticCurveTo(width / 2, height / 2, width / 2 - r, height / 2);
  shape.lineTo(-width / 2 + r, height / 2);
  shape.quadraticCurveTo(-width / 2, height / 2, -width / 2, height / 2 - r);
  shape.lineTo(-width / 2, -height / 2 + r);
  shape.quadraticCurveTo(-width / 2, -height / 2, -width / 2 + r, -height / 2);
  shape.closePath();
  return shape;
}

function padPath(pad: ParsedPad, scale: number): THREE.Shape {
  const width = Math.max(pad.width * scale, 1e-6);
  const height = Math.max(pad.height * scale, 1e-6);
  let shape: THREE.Shape;
  if (pad.customPolygon && pad.customPolygon.length >= 3) {
    shape = new THREE.Shape(pad.customPolygon.map(([x, y]) => new THREE.Vector2(x * scale, -y * scale)));
    shape.closePath();
  } else if (pad.shape === "circle" || pad.shape === "ellipse") {
    shape = new THREE.Shape();
    shape.absellipse(0, 0, width / 2, height / 2, 0, Math.PI * 2, false);
  } else if (pad.shape === "oval") {
    shape = capsulePath(width, height);
  } else if (pad.shape === "roundrect") {
    shape = roundedRectanglePath(width, height, Math.min(width, height) * 0.22);
  } else {
    shape = roundedRectanglePath(width, height, Math.min(width, height) * 0.06);
  }
  if (pad.drill > 0) {
    const hole = new THREE.Path();
    const radius = pad.drill * scale / 2;
    hole.absellipse(0, 0, radius, radius, 0, Math.PI * 2, false);
    shape.holes.push(hole);
  }
  return shape;
}

function componentAppearance(component: ParsedComponent): { color: number; inset: number } {
  const prefix = component.ref[0]?.toUpperCase();
  if (prefix === "C") return { color: 0xb8a77d, inset: 0.35 };
  if (prefix === "R") return { color: 0x30383b, inset: 0.35 };
  if (prefix === "L") return { color: 0x252d30, inset: 0.18 };
  if (prefix === "J" || prefix === "P") return { color: 0x273d43, inset: 0.12 };
  if (prefix === "D") return { color: 0x343b3d, inset: 0.28 };
  if (prefix === "Q") return { color: 0x252b2e, inset: 0.22 };
  return { color: 0x242b2f, inset: 0.2 };
}

function boardThicknessMm(board: ParsedBoard): number {
  const imported = board.stackup.reduce((total, layer) => total + Math.max(Number(layer.thickness) || 0, 0), 0);
  return imported >= 0.1 ? imported : 1.6;
}

function copperZ(layer: string, layers: string[], boardThickness = 1.82, stackup: ParsedBoard["stackup"] = []): number {
  const surface = boardThickness / 2;
  const importedThickness = stackup.reduce((total, entry) => total + Math.max(Number(entry.thickness) || 0, 0), 0);
  if (importedThickness >= 0.1) {
    const worldPerMm = boardThickness / importedThickness;
    let cursor = surface;
    for (const entry of stackup) {
      const thickness = Math.max(Number(entry.thickness) || 0, 0) * worldPerMm;
      const center = cursor - thickness / 2;
      if (entry.name === layer) return center;
      cursor -= thickness;
    }
  }
  if (layer === layers[0]) return surface;
  if (layer === layers[layers.length - 1]) return -surface;
  const internal = layers.slice(1, -1);
  const index = internal.indexOf(layer);
  if (index < 0) return surface;
  const inset = Math.min(boardThickness * 0.16, surface * 0.48);
  const upper = surface - inset;
  const lower = -surface + inset;
  return internal.length === 1 ? 0 : upper + (lower - upper) * index / Math.max(internal.length - 1, 1);
}

function thermalPoint(
  point: [number, number, number],
  volume: { x: number; y: number; z: number },
  scale: number,
  board: ParsedBoard,
  frame: "domain_local" | "board_local" | "board_absolute" = "domain_local",
) {
  const scenePoint = thermalScenePointMm(point, frame, volume, board);
  return new THREE.Vector3(scenePoint[0] * scale, scenePoint[1] * scale, scenePoint[2] * scale);
}

function thermalLine(points: THREE.Vector3[], color: number, opacity = 0.9) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity, depthTest: true }));
  line.renderOrder = 145;
  return line;
}

function thermalArrow(start: THREE.Vector3, direction: THREE.Vector3, length: number, color: number) {
  const normalized = direction.lengthSq() > 0 ? direction.clone().normalize() : new THREE.Vector3(1, 0, 0);
  const arrow = new THREE.ArrowHelper(normalized, start, Math.max(length, 2), color, Math.max(length * 0.24, 1.5), Math.max(length * 0.1, 0.8));
  arrow.traverse(object => {
    object.renderOrder = 148;
    if (object instanceof THREE.Mesh || object instanceof THREE.Line) object.material.depthTest = false;
  });
  return arrow;
}

function overlayLabel(text: string, color = "#9db7c2", scale = 1) {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (!context) return null;
  const fontSize = 28;
  context.font = `600 ${fontSize}px ui-monospace, monospace`;
  const width = Math.ceil(context.measureText(text).width) + 18;
  canvas.width = width;
  canvas.height = 42;
  context.font = `600 ${fontSize}px ui-monospace, monospace`;
  context.fillStyle = "rgba(7, 17, 22, 0.78)";
  context.fillRect(0, 0, width, canvas.height);
  context.strokeStyle = "rgba(102, 139, 151, 0.8)";
  context.strokeRect(0.5, 0.5, width - 1, canvas.height - 1);
  context.fillStyle = color;
  context.fillText(text, 9, 30);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false, depthWrite: false });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set((width / canvas.height) * scale, scale, 1);
  sprite.renderOrder = 410;
  return sprite;
}

function resultAxisTicks(minimumMm: number, maximumMm: number, desiredCount = 5) {
  const span = Math.max(maximumMm - minimumMm, 0.001);
  const roughStep = span / Math.max(desiredCount - 1, 1);
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const normalized = roughStep / magnitude;
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
  const first = Math.ceil(minimumMm / step) * step;
  const ticks: number[] = [];
  for (let value = first; value <= maximumMm + step * 0.001 && ticks.length < 7; value += step) ticks.push(value);
  return ticks;
}

function BoardViewport({ onEmiScene, viewMode, visibleLayers, layerOpacity, layerSeparation, showVias, showNetNames = false, showModels, showSmdModels, showThtModels, assemblyModels = [], assemblySelectorPreviews = [], virtualBoards = [], selectedBoardInstanceId = null, onBoardInstanceSelect, virtualHarnesses = [], selectedHarnessId = null, onHarnessSelect, topologySelectorActive = false, selectedTopologyId = null, onTopologySelect, isolatedAssemblyPartId = null, assemblySection = DEFAULT_ASSEMBLY_SECTION, navigationMode, navigationInertia, showAxes = true, selectionBlink = true, cameraCommand, viewportRestore = null, selectionFilter, selectedId, selectedPosition, selectedNet = null, isolatedNet = null, analysisResult = null, resultVisualization, analysisNets = [], probes = [], showProbes = true, hoverProbeEnabled = false, hoverProbeKind = "universal", terminalMarkers = [], thermalScenario = null, thermalVisibility = { volume: true, heatSources: true, airflow: true, hardware: true, field: true }, board, onSelect, onHoverProbe, onContextMenu, onOrbitCenter, onCamera, onLayoutView, onTelemetry, onModelStatus, onAssemblyPartViewportStatus }: Props) {
  const [incomingBoard, setIncomingBoard] = useState<ParsedBoard | null>(null);
  const [fullModelState, setFullModelState] = useState<"none" | "loading" | "ready" | "failed">("none");
  const [componentModelState, setComponentModelState] = useState<"none" | "loading" | "ready" | "failed">("none");
  const [assemblyModelState, setAssemblyModelState] = useState<"none" | "loading" | "ready" | "failed">("none");
  const [assemblyModelError, setAssemblyModelError] = useState("");
  const [modelMetrics, setModelMetrics] = useState("");
  const [modelError, setModelError] = useState("");
  const [modelRetryGeneration, setModelRetryGeneration] = useState(0);
  const [missingModelCount, setMissingModelCount] = useState(0);
  const [missingModelRefs, setMissingModelRefs] = useState<string[]>([]);
  const [hoverPreview, setHoverPreview] = useState<ViewportHoverTarget | null>(null);
  const [hoverProbeTarget, setHoverProbeTarget] = useState<HoverProbeTarget | null>(null);
  const activeBoard = board ?? incomingBoard;
  const splitSceneAvailable = Boolean(activeBoard?.componentModelUrl);
  const layerFilterActive = activeBoard?.boardModelIncludesCopper === false
    || Object.entries(visibleLayers).some(([name, visible]) => visible !== defaultLayerVisible(name))
    || Object.values(layerOpacity).some(opacity => opacity < 0.999)
    || layerSeparation > 0.001
    || !showVias;
  const resultSceneKey = resultVisualization ? [
    resultVisualization.visible, resultVisualization.mode, resultVisualization.analysisOnly,
    resultVisualization.boardOpacity, resultVisualization.translucentScene, resultVisualization.sceneMode,
    resultVisualization.showComponentModels,
  ].join("\u0000") : "none";
  const resultOverlayKey = resultVisualization ? [
    resultVisualization.mode, resultVisualization.analysisOnly, resultVisualization.plotStyle,
    resultVisualization.fieldStyle, resultVisualization.waveHeightScale, resultVisualization.showVectors,
    resultVisualization.vectorScale, resultVisualization.visibleResultLayers.join("\u0001"),
  ].join("\u0000") : "none";
  const analysisNetSet = useMemo(() => new Set(analysisNets), [analysisNets]);

  useEffect(() => {
    onModelStatus?.({
      board: fullModelState,
      components: componentModelState,
      assembly: assemblyModelState,
      missingCount: missingModelCount,
      missingRefs: missingModelRefs,
      metrics: modelMetrics,
      error: [modelError, assemblyModelError].filter(Boolean).join(" "),
    });
  }, [assemblyModelError, assemblyModelState, componentModelState, fullModelState, missingModelCount, missingModelRefs, modelMetrics, modelError, onModelStatus]);
  const hostRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene>();
  const rendererRef = useRef<THREE.WebGLRenderer>();
  const keyLightRef = useRef<THREE.DirectionalLight>();
  const perspectiveRef = useRef<THREE.PerspectiveCamera>();
  const orthographicRef = useRef<THREE.OrthographicCamera>();
  const activeCameraRef = useRef<THREE.Camera>();
  const controls3dRef = useRef<OrbitControls>();
  const controls2dRef = useRef<OrbitControls>();
  const boardGroupRef = useRef<THREE.Group>();
  const assemblyGroupRef = useRef<THREE.Group>();
  const virtualBoardGroupRef = useRef<THREE.Group>();
  const virtualBoardPickablesRef = useRef<THREE.Object3D[]>([]);
  const harnessGroupRef = useRef<THREE.Group>();
  const harnessPickablesRef = useRef<THREE.Object3D[]>([]);
  const selectorPreviewGroupRef = useRef<THREE.Group>();
  const selectorPreviewPickablesRef = useRef<THREE.Object3D[]>([]);
  const topologySelectorActiveRef = useRef(topologySelectorActive);
  const onTopologySelectRef = useRef(onTopologySelect);
  const onHarnessSelectRef = useRef(onHarnessSelect);
  const onBoardInstanceSelectRef = useRef(onBoardInstanceSelect);
  const assemblyGizmoRef = useRef<TransformControls>();
  const assemblyGizmoConfigRef = useRef({ partId: "", enabled: false, mode: "translate" as "translate" | "rotate", translationSnapMm: 1, rotationSnapDeg: 15 });
  const syncAssemblyGizmoRef = useRef<() => void>(() => {});
  const refreshAssemblyDisplayRef = useRef<() => void>(() => {});
  const pickablesRef = useRef<THREE.Object3D[]>([]);
  const pickablesRevisionRef = useRef(0);
  const pickablesIndexRef = useRef<{ revision: number; index: BoundsSpatialIndex<THREE.Object3D> }>();
  const resultSurfacePickablesRef = useRef<THREE.Object3D[]>([]);
  const objectMapRef = useRef(new Map<string, THREE.Object3D>());
  const selectionBoxRef = useRef<THREE.BoxHelper>();
  const hoverMaterialsRef = useRef<Set<THREE.Material>>(new Set());
  const selectionMaterialsRef = useRef<Set<THREE.Material>>(new Set());
  const proceduralGroupRef = useRef<THREE.Group>();
  const pickingGroupRef = useRef<THREE.Group>();
  const accurateGroupRef = useRef<THREE.Group>();
  const accurateBoardRef = useRef<THREE.Object3D>();
  const accurateComponentsRef = useRef<THREE.Object3D>();
  const resultGroupRef = useRef<THREE.Group>();
  const axisGroupRef = useRef<THREE.Group>();
  const hoverProbeGroupRef = useRef<THREE.Group>();
  const thermalGroupRef = useRef<THREE.Group>();
  const isolatedNetRef = useRef<string | null>(isolatedNet);
  const resultOverlayActiveRef = useRef(false);
  const selectionBlinkRef = useRef(selectionBlink);
  const viewHelperRef = useRef<ViewHelper>();
  const modelGenerationRef = useRef(0);
  const assemblyGenerationRef = useRef(0);
  const lastSceneBoardRef = useRef<ParsedBoard | null>(null);
  const boardSizeRef = useRef({ width: 200, height: 120 });
  const boardTransformRef = useRef({ centerX: 0, centerY: 0, scale: 1 });
  const interactionComplexityRef = useRef(0);
  const focusBoundsRef = useRef({
    center: new THREE.Vector3(0, 0, 4),
    size: new THREE.Vector3(200, 120, 12),
  });
  // Board fit intentionally excludes optional thermal and EMI scene fixtures.
  // Those may be much larger than the PCB, but still participate in clipping.
  const visibleBoundsRef = useRef({
    center: new THREE.Vector3(0, 0, 4),
    size: new THREE.Vector3(200, 120, 12),
  });
  const renderProfileRef = useRef(viewportRenderProfile(0, window.devicePixelRatio));
  const viewModeRef = useRef<ViewMode>(viewMode);
  const onEmiSceneRef = useRef(onEmiScene);
  const onSelectRef = useRef(onSelect);
  const onHoverProbeRef = useRef(onHoverProbe);
  const hoverProbeEnabledRef = useRef(hoverProbeEnabled);
  const onContextMenuRef = useRef(onContextMenu);
  const onOrbitCenterRef = useRef(onOrbitCenter);
  const selectionFilterRef = useRef<SelectionFilter>(selectionFilter);
  const onCameraRef = useRef(onCamera);
  const onTelemetryRef = useRef(onTelemetry);
  const fitRef = useRef<(mode: ViewMode) => void>(() => undefined);
  const refreshVisibleBoundsRef = useRef<() => void>(() => undefined);
  const fittedModesRef = useRef<Set<ViewMode>>(new Set());

  useEffect(() => { onEmiSceneRef.current = onEmiScene; if (onEmiScene) refreshVisibleBoundsRef.current(); }, [onEmiScene]);
  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);
  useEffect(() => { onTopologySelectRef.current = onTopologySelect; }, [onTopologySelect]);
  useEffect(() => { onHarnessSelectRef.current = onHarnessSelect; }, [onHarnessSelect]);
  useEffect(() => { onBoardInstanceSelectRef.current = onBoardInstanceSelect; }, [onBoardInstanceSelect]);
  useEffect(() => { topologySelectorActiveRef.current = topologySelectorActive; }, [topologySelectorActive]);
  useEffect(() => { onHoverProbeRef.current = onHoverProbe; }, [onHoverProbe]);
  useEffect(() => {
    hoverProbeEnabledRef.current = hoverProbeEnabled;
    if (!hoverProbeEnabled) setHoverProbeTarget(null);
  }, [hoverProbeEnabled]);
  useEffect(() => { onContextMenuRef.current = onContextMenu; }, [onContextMenu]);
  useEffect(() => { onOrbitCenterRef.current = onOrbitCenter; }, [onOrbitCenter]);
  useEffect(() => { selectionFilterRef.current = selectionFilter; }, [selectionFilter]);
  useEffect(() => { onCameraRef.current = onCamera; }, [onCamera]);
  useEffect(() => { onTelemetryRef.current = onTelemetry; }, [onTelemetry]);
  useEffect(() => { viewModeRef.current = viewMode; }, [viewMode]);
  useEffect(() => { isolatedNetRef.current = isolatedNet; }, [isolatedNet]);
  useEffect(() => {
    selectionBlinkRef.current = selectionBlink;
    if (hostRef.current) hostRef.current.dataset.selectionBlink = selectionBlink ? "enabled" : "disabled";
  }, [selectionBlink]);
  useEffect(() => {
    resultOverlayActiveRef.current = solverResultOverlayActive(analysisResult, resultVisualization);
    if (hostRef.current) {
      hostRef.current.dataset.selectionAnimation = resultOverlayActiveRef.current ? "suppressed-for-results" : "enabled";
    }
  }, [analysisResult, resultVisualization]);
  useEffect(() => {
    const boardComplexity = activeBoard
      ? activeBoard.tracks.length + activeBoard.vias.length + activeBoard.pads.length + activeBoard.zones.length + activeBoard.components.length
      : 0;
    const resultComplexity = analysisResult
      ? analysisResult.mesh.length
        + Object.values(analysisResult.scalar_fields).reduce((total, samples) => total + samples.length, 0)
        + Object.values(analysisResult.vector_fields).reduce((total, samples) => total + samples.length, 0)
        + analysisResult.component_bridges.length
      : 0;
    const assemblyComplexity = assemblyModels.length + virtualBoards.length
      + virtualHarnesses.reduce((total, harness) => total + harness.routeMm.length, 0)
      + assemblySelectorPreviews.reduce((total, preview) => total + preview.references.size, 0);
    const complexity = boardComplexity + resultComplexity + assemblyComplexity;
    interactionComplexityRef.current = complexity;
    const profile = viewportRenderProfile(complexity, window.devicePixelRatio);
    renderProfileRef.current = profile;
    const renderer = rendererRef.current;
    if (renderer) {
      renderer.setPixelRatio(profile.fullPixelRatio);
      renderer.shadowMap.autoUpdate = profile.dynamicShadowUpdates;
    }
    if (keyLightRef.current) {
      keyLightRef.current.shadow.mapSize.set(profile.shadowMapSize, profile.shadowMapSize);
      keyLightRef.current.shadow.needsUpdate = true;
    }
    if (hostRef.current) {
      hostRef.current.dataset.interactionLod = complexity > 12000 ? `large;objects=${complexity}` : `standard;objects=${complexity}`;
      hostRef.current.dataset.renderProfile = profile.largeScene ? "large-board" : "standard-board";
    }
  }, [activeBoard, analysisResult, assemblyModels, assemblySelectorPreviews, virtualBoards, virtualHarnesses]);
  useEffect(() => {
    const handler = (event: Event) => setHoverPreview((event as CustomEvent<ViewportHoverTarget | null>).detail ?? null);
    window.addEventListener("spike-viewport-hover-preview", handler);
    return () => window.removeEventListener("spike-viewport-hover-preview", handler);
  }, []);
  useEffect(() => {
    const handler = (event: Event) => setIncomingBoard((event as CustomEvent<ParsedBoard>).detail);
    window.addEventListener("spike-board-imported", handler);
    return () => window.removeEventListener("spike-board-imported", handler);
  }, []);
  useEffect(() => {
    const retry = () => setModelRetryGeneration(current => current + 1);
    window.addEventListener("spike-retry-model-scene", retry);
    return () => window.removeEventListener("spike-retry-model-scene", retry);
  }, []);
  useEffect(() => {
    let cancelled = false;
    setMissingModelCount(0);
    setMissingModelRefs([]);
    if (!activeBoard?.modelManifestUrl) return () => { cancelled = true; };
    fetch(activeBoard.modelManifestUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`Scene manifest request failed: ${response.status}`);
        return response.json();
      })
      .then((manifest: { quality?: { missing_model_count?: number; missing_references?: string[] } }) => {
        if (!cancelled) {
          setMissingModelCount(Math.max(0, Number(manifest.quality?.missing_model_count) || 0));
          setMissingModelRefs(
            Array.isArray(manifest.quality?.missing_references)
              ? manifest.quality.missing_references.filter(value => typeof value === "string")
              : [],
          );
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMissingModelCount(0);
          setMissingModelRefs([]);
        }
      });
    return () => { cancelled = true; };
  }, [activeBoard?.modelManifestUrl]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x171d21);
    // Engineering geometry must not disappear with camera distance. Depth
    // planes are derived from scene bounds below, so atmospheric fog would
    // only hide valid PCB, chamber, enclosure, or assembly content.
    scene.fog = null;
    host.dataset.distanceFade = "disabled";

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
      logarithmicDepthBuffer: true,
    });
    const initialProfile = renderProfileRef.current;
    const fullPixelRatio = initialProfile.fullPixelRatio;
    renderer.setPixelRatio(fullPixelRatio);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.NeutralToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.autoClear = false;
    renderer.info.autoReset = false;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.autoUpdate = initialProfile.dynamicShadowUpdates;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.localClippingEnabled = true;
    renderer.domElement.className = "three-canvas";
    host.appendChild(renderer.domElement);
    const captureWebglFrame = (event: Event) => {
      const request = event as CustomEvent<{ resolve?: (canvas: HTMLCanvasElement) => void }>;
      if (viewModeRef.current === "3D") {
        renderer.clear();
        renderer.render(scene, activeCameraRef.current!);
      }
      request.detail?.resolve?.(renderer.domElement);
    };
    window.addEventListener("spike-capture-webgl-frame", captureWebglFrame);

    const environment = new RoomEnvironment();
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(environment, 0.04).texture;
    scene.environmentIntensity = 0.82;
    environment.dispose();
    pmrem.dispose();

    const perspective = new THREE.PerspectiveCamera(38, 1, 0.05, 1000);
    perspective.up.set(0, 0, 1);
    const orthographic = new THREE.OrthographicCamera(-120, 120, 80, -80, 0.1, 1200);
    orthographic.position.set(0, 0, 500);
    activeCameraRef.current = viewModeRef.current === "2D" ? orthographic : perspective;

    const controls3d = new OrbitControls(perspective, renderer.domElement);
    controls3d.enableDamping = false;
    controls3d.dampingFactor = 0.075;
    controls3d.screenSpacePanning = true;
    controls3d.minDistance = 10;
    controls3d.maxDistance = adaptiveMaximumCameraDistance(visibleBoundsRef.current.size.length() / 2);
    controls3d.minPolarAngle = 0.001;
    controls3d.maxPolarAngle = Math.PI - 0.001;
    controls3d.rotateSpeed = 0.85;
    controls3d.panSpeed = 0.75;
    controls3d.zoomSpeed = 0.85;
    controls3d.zoomToCursor = true;
    controls3d.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
    controls3d.mouseButtons.MIDDLE = THREE.MOUSE.PAN;
    controls3d.mouseButtons.RIGHT = THREE.MOUSE.PAN;
    controls3d.touches.ONE = THREE.TOUCH.ROTATE;
    controls3d.touches.TWO = THREE.TOUCH.DOLLY_PAN;
    host.dataset.inputMap = "left=orbit;middle-click=orbit-center;middle-drag=pan;right=pan;wheel=zoom";
    let updateCameraLighting = () => undefined;
    const updatePerspectiveClipping = () => {
      const radius = Math.max(visibleBoundsRef.current.size.length() / 2, 4);
      const distance = perspective.position.distanceTo(controls3d.target);
      const cameraToBoundsCenter = perspective.position.distanceTo(visibleBoundsRef.current.center);
      const { near, far } = adaptivePerspectiveClip({ radius, cameraDistance: distance, cameraToBoundsCenter });
      if (Math.abs(perspective.near - near) > 0.01 || Math.abs(perspective.far - far) > 0.1) {
        perspective.near = near;
        perspective.far = far;
        perspective.updateProjectionMatrix();
      }
      host.dataset.depthPrecision = [
        "adaptive-logarithmic-z",
        `near=${near.toFixed(3)}`,
        `far=${far.toFixed(3)}`,
        `distance=${distance.toFixed(3)}`,
        `scene-distance=${cameraToBoundsCenter.toFixed(3)}`,
      ].join(";");
    };
    const refreshVisibleBounds = () => {
      if (onEmiSceneRef.current) {
        onEmiSceneRef.current(snapshotEmiDut([boardGroup, assemblyGroup, virtualBoardGroup, harnessGroup], boardTransformRef.current.scale));
      }
      const boardBounds = new THREE.Box3().setFromObject(boardGroup);
      const assemblyBounds = assemblyGroup.visible
        ? new THREE.Box3().setFromObject(assemblyGroup)
        : new THREE.Box3();
      const thermalBounds = new THREE.Box3().setFromObject(thermalGroup);
      const resultBounds = new THREE.Box3().setFromObject(resultGroup);
      if (!assemblyBounds.isEmpty()) boardBounds.union(assemblyBounds);
      if (!thermalBounds.isEmpty()) boardBounds.union(thermalBounds);
      if (!resultBounds.isEmpty()) boardBounds.union(resultBounds);
      if (!boardBounds.isEmpty()) {
        visibleBoundsRef.current = {
          center: boardBounds.getCenter(new THREE.Vector3()),
          size: boardBounds.getSize(new THREE.Vector3()),
        };
      } else {
        visibleBoundsRef.current = {
          center: focusBoundsRef.current.center.clone(),
          size: focusBoundsRef.current.size.clone(),
        };
      }
      const visibleRadius = Math.max(visibleBoundsRef.current.size.length() / 2, 4);
      controls3d.maxDistance = adaptiveMaximumCameraDistance(visibleRadius);
      const orthoSceneDistance = orthographic.position.distanceTo(visibleBoundsRef.current.center);
      orthographic.near = 0.01;
      orthographic.far = Math.max(2_000, orthoSceneDistance + visibleRadius * 8);
      orthographic.updateProjectionMatrix();
      const shadowSpan = Math.max(260, visibleRadius * 1.5);
      const shadowCamera = keyLightRef.current?.shadow.camera;
      if (shadowCamera instanceof THREE.OrthographicCamera) {
        shadowCamera.left = -shadowSpan;
        shadowCamera.right = shadowSpan;
        shadowCamera.top = shadowSpan;
        shadowCamera.bottom = -shadowSpan;
        shadowCamera.far = Math.max(500, visibleRadius * 12);
        shadowCamera.updateProjectionMatrix();
      }
      updateCameraLighting();
      updatePerspectiveClipping();
    };
    refreshVisibleBoundsRef.current = refreshVisibleBounds;
    const record3dCamera = () => {
      updatePerspectiveClipping();
      updateCameraLighting();
      host.dataset.liveCameraMetrics = [
        `position=${perspective.position.toArray().map((value) => value.toFixed(3)).join(",")}`,
        `target=${controls3d.target.toArray().map((value) => value.toFixed(3)).join(",")}`,
        `up=${perspective.up.toArray().map((value) => value.toFixed(0)).join(",")}`,
      ].join(";");
      onCameraRef.current({
        contract: "spike/viewport-camera/v1",
        position: perspective.position.toArray() as [number, number, number],
        target: controls3d.target.toArray() as [number, number, number],
        up: perspective.up.toArray() as [number, number, number],
      });
    };
    controls3d.addEventListener("change", record3dCamera);

    const controls2d = new OrbitControls(orthographic, renderer.domElement);
    controls2d.enableRotate = false;
    controls2d.enableDamping = false;
    controls2d.dampingFactor = 0.09;
    controls2d.screenSpacePanning = true;
    controls2d.panSpeed = 0.8;
    controls2d.zoomSpeed = 0.9;
    controls2d.zoomToCursor = true;
    controls2d.mouseButtons.LEFT = THREE.MOUSE.PAN;
    controls2d.mouseButtons.MIDDLE = THREE.MOUSE.PAN;
    controls2d.mouseButtons.RIGHT = THREE.MOUSE.PAN;
    controls2d.touches.ONE = THREE.TOUCH.PAN;
    controls2d.touches.TWO = THREE.TOUCH.DOLLY_PAN;
    const record2dCamera = () => {
      updateCameraLighting();
      host.dataset.liveCameraMetrics = [
        `position=${orthographic.position.toArray().map((value) => value.toFixed(3)).join(",")}`,
        `target=${controls2d.target.toArray().map((value) => value.toFixed(3)).join(",")}`,
        `up=${orthographic.up.toArray().map((value) => value.toFixed(0)).join(",")}`,
        `zoom=${orthographic.zoom.toFixed(3)}`,
      ].join(";");
    };
    controls2d.addEventListener("change", record2dCamera);

    let qualityRestoreTimer = 0;
    const scheduleFullQuality = (delay: number) => {
      window.clearTimeout(qualityRestoreTimer);
      qualityRestoreTimer = window.setTimeout(() => {
        const currentProfile = renderProfileRef.current;
        renderer.setPixelRatio(currentProfile.fullPixelRatio);
        renderer.shadowMap.autoUpdate = currentProfile.dynamicShadowUpdates;
        // A camera-relative key needs one fresh shadow map after each orbit,
        // even when large-scene profiles disable continuous shadow updates.
        renderer.shadowMap.needsUpdate = true;
        host.dataset.renderQuality = `full;dpr=${currentProfile.fullPixelRatio.toFixed(2)}`;
      }, delay);
    };
    const beginInteraction = () => {
      window.clearTimeout(qualityRestoreTimer);
      const profile = renderProfileRef.current;
      if (renderer.getPixelRatio() !== profile.interactionPixelRatio) renderer.setPixelRatio(profile.interactionPixelRatio);
      renderer.shadowMap.autoUpdate = false;
      host.dataset.renderQuality = `interactive;dpr=${profile.interactionPixelRatio.toFixed(2)}`;
      scheduleFullQuality(1200);
    };
    const endInteraction = () => scheduleFullQuality(120);
    controls3d.addEventListener("start", beginInteraction);
    controls3d.addEventListener("end", endInteraction);
    controls2d.addEventListener("start", beginInteraction);
    controls2d.addEventListener("end", endInteraction);
    host.dataset.renderQuality = `full;dpr=${fullPixelRatio.toFixed(2)}`;

    const hemisphere = new THREE.HemisphereLight(0xdce6e8, 0x506965, 0.9);
    scene.add(hemisphere);
    scene.add(new THREE.AmbientLight(0xb8c9cb, 0.34));
    const lightTarget = new THREE.Object3D();
    lightTarget.name = "camera-light-target";
    scene.add(lightTarget);
    const key = new THREE.DirectionalLight(0xfff6e8, 1.75);
    key.target = lightTarget;
    key.castShadow = true;
    key.shadow.mapSize.set(initialProfile.shadowMapSize, initialProfile.shadowMapSize);
    key.shadow.camera.left = -260;
    key.shadow.camera.right = 260;
    key.shadow.camera.top = 220;
    key.shadow.camera.bottom = -220;
    key.shadow.bias = -0.00025;
    key.shadow.normalBias = 0.035;
    scene.add(key);
    keyLightRef.current = key;
    const fill = new THREE.DirectionalLight(0xc7e1df, 0.82);
    fill.target = lightTarget;
    scene.add(fill);
    const lowerFill = new THREE.DirectionalLight(0x9bcfc9, 0.58);
    lowerFill.target = lightTarget;
    scene.add(lowerFill);
    const rim = new THREE.DirectionalLight(0xdbe8ec, 0.48);
    rim.target = lightTarget;
    scene.add(rim);
    let lastShadowRefresh = 0;
    const lastKeyPosition = new THREE.Vector3(Number.POSITIVE_INFINITY, 0, 0);
    updateCameraLighting = () => {
      const camera = activeCameraRef.current;
      if (!camera) return;
      camera.updateMatrixWorld();
      const target = viewModeRef.current === "3D" ? controls3d.target : controls2d.target;
      const cameraSide = camera.position.clone().sub(target);
      if (cameraSide.lengthSq() < 1e-8) cameraSide.set(0, 0, 1);
      cameraSide.normalize();
      const cameraRight = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).normalize();
      const cameraUp = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1).normalize();
      const sceneRadius = Math.max(visibleBoundsRef.current.size.length() / 2, 4);
      const rigDistance = Math.max(sceneRadius * 2.6, 120);

      lightTarget.position.copy(target);
      hemisphere.position.copy(cameraSide);
      key.position.copy(target)
        .addScaledVector(cameraSide, rigDistance * 1.45)
        .addScaledVector(cameraRight, rigDistance * 0.28)
        .addScaledVector(cameraUp, rigDistance * 0.3);
      fill.position.copy(target)
        .addScaledVector(cameraSide, rigDistance * 0.95)
        .addScaledVector(cameraRight, -rigDistance * 0.65)
        .addScaledVector(cameraUp, rigDistance * 0.08);
      lowerFill.position.copy(target)
        .addScaledVector(cameraSide, rigDistance * 0.82)
        .addScaledVector(cameraRight, rigDistance * 0.12)
        .addScaledVector(cameraUp, -rigDistance * 0.58);
      rim.position.copy(target)
        .addScaledVector(cameraSide, -rigDistance * 0.62)
        .addScaledVector(cameraRight, rigDistance * 0.42)
        .addScaledVector(cameraUp, rigDistance * 0.2);
      lightTarget.updateMatrixWorld();

      const now = performance.now();
      const shadowMoved = lastKeyPosition.distanceToSquared(key.position) > Math.max(sceneRadius * sceneRadius * 0.0025, 0.25);
      if (shadowMoved && now - lastShadowRefresh > 180) {
        key.shadow.needsUpdate = true;
        lastKeyPosition.copy(key.position);
        lastShadowRefresh = now;
      }
      host.dataset.lightingRig = [
        "camera-relative",
        `side=${cameraSide.toArray().map(value => value.toFixed(3)).join(",")}`,
        `target=${target.toArray().map(value => value.toFixed(3)).join(",")}`,
      ].join(";");
    };
    updateCameraLighting();

    const boardGroup = new THREE.Group();
    boardGroup.name = "native-board";
    scene.add(boardGroup);
    const assemblyGroup = new THREE.Group();
    assemblyGroup.name = "mcad-assembly";
    scene.add(assemblyGroup);
    const virtualBoardGroup = new THREE.Group();
    virtualBoardGroup.name = "virtual-board-instances";
    scene.add(virtualBoardGroup);
    const harnessGroup = new THREE.Group();
    harnessGroup.name = "virtual-harnesses";
    harnessGroup.renderOrder = 180;
    scene.add(harnessGroup);
    const selectorPreviewGroup = new THREE.Group();
    selectorPreviewGroup.name = "mcad-exact-selector-previews";
    scene.add(selectorPreviewGroup);
    const assemblyGizmo = new TransformControls(perspective, renderer.domElement);
    assemblyGizmo.space = "local";
    assemblyGizmo.size = 0.82;
    scene.add(assemblyGizmo.getHelper());
    assemblyGizmoRef.current = assemblyGizmo;
    const syncAssemblyGizmo = () => {
      const config = assemblyGizmoConfigRef.current;
      const target = config.enabled && viewModeRef.current === "3D"
        ? assemblyGroup.getObjectByProperty("name", `part:${config.partId}`)
        : undefined;
      if (!target) {
        assemblyGizmo.detach();
        return;
      }
      if (assemblyGizmo.object !== target) {
        target.matrix.decompose(target.position, target.quaternion, target.scale);
        target.matrixAutoUpdate = true;
        assemblyGizmo.attach(target);
      }
      assemblyGizmo.setMode(config.mode);
      assemblyGizmo.setTranslationSnap(config.translationSnapMm > 0 ? config.translationSnapMm : null);
      assemblyGizmo.setRotationSnap(config.rotationSnapDeg > 0 ? THREE.MathUtils.degToRad(config.rotationSnapDeg) : null);
    };
    syncAssemblyGizmoRef.current = syncAssemblyGizmo;
    const onAssemblyGizmoConfig = (event: Event) => {
      const detail = (event as CustomEvent<Partial<typeof assemblyGizmoConfigRef.current>>).detail;
      if (!detail || typeof detail !== "object") return;
      const mode = detail.mode === "rotate" ? "rotate" : "translate";
      const translationSnapMm = Number(detail.translationSnapMm);
      const rotationSnapDeg = Number(detail.rotationSnapDeg);
      assemblyGizmoConfigRef.current = {
        partId: typeof detail.partId === "string" ? detail.partId : "",
        enabled: detail.enabled === true,
        mode,
        translationSnapMm: Number.isFinite(translationSnapMm) && translationSnapMm >= 0 ? translationSnapMm : 1,
        rotationSnapDeg: Number.isFinite(rotationSnapDeg) && rotationSnapDeg >= 0 ? rotationSnapDeg : 15,
      };
      syncAssemblyGizmo();
    };
    const publishGizmoTransform = (kind: "preview" | "commit") => {
      const object = assemblyGizmo.object;
      const partId = assemblyGizmoConfigRef.current.partId;
      if (!object || !partId) return;
      object.updateMatrix();
      window.dispatchEvent(new CustomEvent(`spike-mcad-transform-${kind}`, {
        detail: { partId, assemblyTransform: matrixToRowMajor(object.matrix), mode: assemblyGizmo.mode },
      }));
    };
    const onGizmoMouseDown = () => { controls3d.enabled = false; };
    const onGizmoObjectChange = () => publishGizmoTransform("preview");
    const onGizmoMouseUp = () => {
      controls3d.enabled = true;
      publishGizmoTransform("commit");
    };
    assemblyGizmo.addEventListener("mouseDown", onGizmoMouseDown);
    assemblyGizmo.addEventListener("objectChange", onGizmoObjectChange);
    assemblyGizmo.addEventListener("mouseUp", onGizmoMouseUp);
    window.addEventListener("spike-mcad-gizmo-config", onAssemblyGizmoConfig);
    const resultGroup = new THREE.Group();
    resultGroup.name = "solver-result-overlay";
    scene.add(resultGroup);
    const thermalGroup = new THREE.Group();
    thermalGroup.name = "thermal-scene-overlay";
    scene.add(thermalGroup);
    const axisGroup = new THREE.Group();
    axisGroup.name = "measurement-axes";
    scene.add(axisGroup);
    const hoverProbeGroup = new THREE.Group();
    hoverProbeGroup.name = "hover-probe-overlay";
    hoverProbeGroup.renderOrder = 400;
    scene.add(hoverProbeGroup);
    const hoverLabel = document.createElement("div");
    hoverLabel.className = "viewport-hover-label";
    host.appendChild(hoverLabel);

    const selectionBox = new THREE.BoxHelper(new THREE.Object3D(), 0xffc14f);
    selectionBox.material.depthTest = false;
    selectionBox.material.transparent = true;
    selectionBox.material.opacity = 0.95;
    selectionBox.renderOrder = 200;
    selectionBox.visible = false;
    scene.add(selectionBox);
    const viewHelper = new ViewHelper(perspective, renderer.domElement);
    viewHelper.setLabels("X", "Y", "Z");
    viewHelper.setLabelStyle("12px sans-serif", "#dbe6e9", 14);

    const fit = (mode: ViewMode) => {
      const rect = host.getBoundingClientRect();
      const aspect = rect.width / Math.max(rect.height, 1);
      const boardWidth = boardSizeRef.current.width * 1.12;
      const boardHeight = boardSizeRef.current.height * 1.12;
      if (mode === "2D") {
        const halfHeight = Math.max(boardHeight / 2, boardWidth / Math.max(aspect, 0.1) / 2);
        orthographic.left = -halfHeight * aspect;
        orthographic.right = halfHeight * aspect;
        orthographic.top = halfHeight;
        orthographic.bottom = -halfHeight;
        orthographic.zoom = 1;
        orthographic.position.set(0, 0, 500);
        orthographic.up.set(0, 1, 0);
        controls2d.target.set(0, 0, 0);
        orthographic.lookAt(0, 0, 0);
        orthographic.updateProjectionMatrix();
        controls2d.update();
        record2dCamera();
      } else {
        const { center, size } = focusBoundsRef.current;
        const verticalFov = perspective.fov * Math.PI / 180;
        const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * Math.max(aspect, 0.1));
        const radius = Math.max(size.length() / 2, 1);
        const distance = Math.max(
          radius / Math.sin(verticalFov / 2),
          radius / Math.sin(horizontalFov / 2),
        ) * 1.08;
        const direction = new THREE.Vector3(0.72, -0.86, 0.72).normalize();
        perspective.position.copy(center).addScaledVector(direction, distance);
        perspective.up.set(0, 0, 1);
        controls3d.target.copy(center);
        perspective.lookAt(center);
        perspective.updateProjectionMatrix();
        controls3d.update();
        record3dCamera();
      }
      const camera = mode === "2D" ? orthographic : perspective;
      const target = mode === "2D" ? controls2d.target : controls3d.target;
      host.dataset.cameraMetrics = [
        mode,
        `position=${camera.position.toArray().map((value) => value.toFixed(2)).join(",")}`,
        `target=${target.toArray().map((value) => value.toFixed(2)).join(",")}`,
      ].join(";");
    };
    fitRef.current = fit;

    let viewportInitialized = false;
    const resize = () => {
      const rect = host.getBoundingClientRect();
      renderer.setSize(rect.width, rect.height, false);
      perspective.aspect = rect.width / Math.max(rect.height, 1);
      perspective.updateProjectionMatrix();
      if (!viewportInitialized) {
        viewportInitialized = true;
        fit(viewModeRef.current);
      } else {
        const halfHeight = (orthographic.top - orthographic.bottom) / 2;
        const aspect = rect.width / Math.max(rect.height, 1);
        orthographic.left = -halfHeight * aspect;
        orthographic.right = halfHeight * aspect;
        orthographic.updateProjectionMatrix();
      }
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const objectData = (object: THREE.Object3D | null): BoardObject | null => {
      let target = object;
      while (target && !target.userData.id) target = target.parent;
      return target?.userData.id ? target.userData as BoardObject : null;
    };
    const allowedByFilter = (data: BoardObject) => selectionFilterRef.current === "all"
      || selectionFilterRef.current === "part" && data.type === "component"
      || selectionFilterRef.current === "net" && Boolean(data.net) && data.type !== "component";
    const pickPriority = (candidate: { hit: THREE.Intersection; data: BoardObject }) =>
      Number(candidate.hit.object.userData.pickPriority ?? (candidate.data.type === "component" ? 1 : 0));
    const exactRaycastCandidates = () => {
      const source = pickablesRef.current;
      if (interactionComplexityRef.current <= 12_000 || source.length < 2_000) return source;
      let cached = pickablesIndexRef.current;
      if (!cached || cached.revision !== pickablesRevisionRef.current) {
        scene.updateMatrixWorld(true);
        const records: SpatialBounds<THREE.Object3D>[] = source.flatMap(object => {
          const bounds = new THREE.Box3().setFromObject(object);
          if (bounds.isEmpty()) return [];
          return [{
            value: object,
            minX: bounds.min.x, maxX: bounds.max.x,
            minY: bounds.min.y, maxY: bounds.max.y,
            minZ: bounds.min.z, maxZ: bounds.max.z,
          }];
        });
        cached = { revision: pickablesRevisionRef.current, index: buildBoundsSpatialIndex(records) };
        pickablesIndexRef.current = cached;
      }
      const query = rayBoundsCandidates(
        cached.index,
        raycaster.ray.origin.toArray() as [number, number, number],
        raycaster.ray.direction.toArray() as [number, number, number],
      );
      host.dataset.raycastBroadphase = [
        `input=${source.length}`, `candidates=${query.values.length}`,
        `cells=${query.cells}`, `global=${query.global}`,
      ].join(";");
      return query.values;
    };
    const hitAt = (event: PointerEvent | MouseEvent, respectSelectionFilter = true) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, activeCameraRef.current!);
      const intersections = raycaster.intersectObjects(exactRaycastCandidates(), true);
      const componentDepthTolerance = viewModeRef.current === "3D" && selectionFilterRef.current === "all" ? 1.5 : 0.01;
      let best: { hit: THREE.Intersection; data: BoardObject } | undefined;
      for (const hit of intersections) {
        const data = objectData(hit.object);
        if (!data || respectSelectionFilter && !allowedByFilter(data)
          || isolatedNetRef.current && data.net !== isolatedNetRef.current) continue;
        const candidate = { hit, data };
        if (!best) {
          best = candidate;
          continue;
        }
        const depthDelta = candidate.hit.distance - best.hit.distance;
        if (depthDelta < -componentDepthTolerance
          || Math.abs(depthDelta) <= componentDepthTolerance && pickPriority(candidate) > pickPriority(best)) best = candidate;
      }
      return best;
    };
    const selectorHitAt = (event: PointerEvent | MouseEvent) => {
      if (!topologySelectorActiveRef.current || viewModeRef.current !== "3D" || !selectorPreviewPickablesRef.current.length) return undefined;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.params.Line.threshold = 1.5;
      raycaster.setFromCamera(pointer, activeCameraRef.current!);
      return raycaster.intersectObjects(selectorPreviewPickablesRef.current, false)
        .filter(hit => visibleInScene(hit.object) && hit.object.userData.topologyReference)
        .sort((left, right) => {
          const leftKind = (left.object.userData.topologyReference as TopologyReference).topology_kind;
          const rightKind = (right.object.userData.topologyReference as TopologyReference).topology_kind;
          const priority = (kind: string) => kind === "axis" ? 3 : kind === "edge" ? 2 : 1;
          return Math.abs(left.distance - right.distance) > 0.5 ? left.distance - right.distance : priority(rightKind) - priority(leftKind);
        })[0];
    };
    const harnessHitAt = (event: PointerEvent | MouseEvent) => {
      if (viewModeRef.current !== "3D" || !harnessPickablesRef.current.length) return undefined;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.params.Line.threshold = 2.5;
      raycaster.setFromCamera(pointer, activeCameraRef.current!);
      return raycaster.intersectObjects(harnessPickablesRef.current, false)
        .find(hit => visibleInScene(hit.object) && hit.object.userData.virtualHarness);
    };
    const virtualBoardHitAt = (event: PointerEvent | MouseEvent) => {
      if (viewModeRef.current !== "3D" || !virtualBoardPickablesRef.current.length) return undefined;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, activeCameraRef.current!);
      return raycaster.intersectObjects(virtualBoardPickablesRef.current, false)
        .find(hit => visibleInScene(hit.object) && hit.object.userData.virtualBoard);
    };
    let resultCursorOccluded = false;
    const resultSurfaceHitAt = (event: PointerEvent | MouseEvent) => {
      resultCursorOccluded = false;
      if (!resultSurfacePickablesRef.current.length) return undefined;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, activeCameraRef.current!);
      const hit = raycaster.intersectObjects(resultSurfacePickablesRef.current, true)
        .find(candidate => visibleInScene(candidate.object));
      if (!hit) return undefined;
      // Cursor visibility must match the depth-buffer view, including board,
      // components and assembly parts. Transparent inspection remains pickable.
      const blockers = resultOcclusionCandidates();
      const occluded = raycaster.intersectObjects(blockers, false).some(blocker => {
        if (!visibleInScene(blocker.object) || blocker.object.userData.pickingProxy) return false;
        const mesh = blocker.object as THREE.Mesh;
        const material = Array.isArray(mesh.material)
          ? mesh.material[blocker.face?.materialIndex ?? 0] : mesh.material;
        return material?.visible && material.colorWrite && resultHitOccluded(
          hit.distance, blocker.distance, material.opacity, material.depthWrite);
      });
      resultCursorOccluded = Boolean(occluded);
      return occluded ? undefined : hit;
    };
    const visibleInScene = (object: THREE.Object3D) => {
      let current: THREE.Object3D | null = object;
      while (current) {
        if (!current.visible) return false;
        current = current.parent;
      }
      return true;
    };
    let occluderRevision = -1;
    let occluderIndex: BoundsSpatialIndex<THREE.Object3D> | undefined;
    const resultOcclusionCandidates = () => {
      if (!occluderIndex || occluderRevision !== pickablesRevisionRef.current) {
        scene.updateMatrixWorld(true);
        const records: SpatialBounds<THREE.Object3D>[] = [];
        for (const root of [boardGroup, accurateGroupRef.current, assemblyGroup, virtualBoardGroup]) root?.traverse(object => {
          if (!(object instanceof THREE.Mesh) || object.userData.pickingProxy) return;
          const bounds = new THREE.Box3().setFromObject(object);
          if (!bounds.isEmpty()) records.push({ value: object,
            minX: bounds.min.x, maxX: bounds.max.x, minY: bounds.min.y, maxY: bounds.max.y,
            minZ: bounds.min.z, maxZ: bounds.max.z });
        });
        occluderIndex = buildBoundsSpatialIndex(records);
        occluderRevision = pickablesRevisionRef.current;
      }
      return rayBoundsCandidates(occluderIndex, raycaster.ray.origin.toArray() as [number, number, number],
        raycaster.ray.direction.toArray() as [number, number, number]).values;
    };
    const scenePointAt = (event: PointerEvent | MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, activeCameraRef.current!);
      const surfaceHit = raycaster.intersectObject(boardGroup, true)
        .find(hit => visibleInScene(hit.object) && !hit.object.userData.pickingProxy);
      if (surfaceHit) return surfaceHit.point.clone();
      const target = viewModeRef.current === "3D" ? controls3d.target : controls2d.target;
      return raycaster.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 0, 1), -target.z), new THREE.Vector3()) ?? undefined;
    };
    const setOrbitCenter = (point: THREE.Vector3) => {
      if (viewModeRef.current !== "3D") return;
      controls3d.target.copy(point);
      perspective.lookAt(point);
      controls3d.update();
      viewHelper.center.copy(point);
      record3dCamera();
      const position = point.toArray() as [number, number, number];
      host.dataset.orbitCenter = position.map(value => value.toFixed(3)).join(",");
      onOrbitCenterRef.current?.(position);
    };
    let hoverFrame = 0;
    let hoverEvent: PointerEvent | null = null;
    let lastHoverCheck = 0;
    const updateHover = () => {
      hoverFrame = 0;
      const event = hoverEvent;
      hoverEvent = null;
      if (!event || event.buttons !== 0) return;
      const now = performance.now();
      const complexity = interactionComplexityRef.current;
      const hoverInterval = hoverProbeEnabledRef.current
        ? complexity > 12000 ? 90 : complexity > 4000 ? 55 : 30
        : complexity > 12000 ? 180 : complexity > 4000 ? 120 : 80;
      if (now - lastHoverCheck < hoverInterval) return;
      lastHoverCheck = now;
      // On very large designs, default pointer movement must not raycast tens
      // of thousands of objects. Click selection remains exact; enabling the
      // hover probe deliberately opts back into throttled continuous picking.
      const selectorHit = selectorHitAt(event);
      const hit = !hoverProbeEnabledRef.current && complexity > 12000
        ? undefined
        : hitAt(event, !hoverProbeEnabledRef.current);
      renderer.domElement.style.cursor = hoverProbeEnabledRef.current ? "crosshair" : selectorHit || hit ? "pointer" : viewModeRef.current === "2D" ? "grab" : "default";
      const data = hit?.data;
      if (hoverProbeEnabledRef.current) {
        const resultHit = resultSurfaceHitAt(event);
        const surfaceData = resultHit?.object.userData;
        const resultSamples = surfaceData?.contourSamples as ScalarSample[] | undefined;
        const transform = boardTransformRef.current;
        const pickedSample = resultHit && resultSamples
          ? resultSampleForHit(resultSamples, resultHit.faceIndex, surfaceData?.triangleSamples, resultHit.instanceId)
            ?? nearestPointSample(resultSamples, transform.centerX + resultHit.point.x / transform.scale,
              transform.centerY - resultHit.point.y / transform.scale).sample
          : undefined;
        // In results-only mode there may be no geometry pick proxy at all.
        // A rendered result face is itself the authoritative cursor target.
        if (resultHit && pickedSample) {
          const target: HoverProbeTarget = {
            clientX: event.clientX, clientY: event.clientY,
            position: [transform.centerX + resultHit.point.x / transform.scale,
              transform.centerY - resultHit.point.y / transform.scale],
            worldPosition: resultHit.point.toArray() as [number, number, number],
            resultSample: pickedSample,
            resultField: { label: surfaceData?.contourLabel ?? "Result", unit: surfaceData?.contourUnit ?? "" },
            object: { id: pickedSample.element_id ?? "result-sample", type: "zone",
              name: pickedSample.element_id ?? "Solver sample", net: pickedSample.net, layer: pickedSample.layer },
          };
          setHoverProbeTarget(target);
          onHoverProbeRef.current?.(target);
        } else if (hit && !resultHit && !resultCursorOccluded) {
          const transform = boardTransformRef.current;
          const target: HoverProbeTarget = {
            clientX: event.clientX,
            clientY: event.clientY,
            position: [
              transform.centerX + hit.hit.point.x / transform.scale,
              transform.centerY - hit.hit.point.y / transform.scale,
            ],
            object: data ?? null,
          };
          setHoverProbeTarget(target);
          onHoverProbeRef.current?.(target);
        } else {
          setHoverProbeTarget(null);
          onHoverProbeRef.current?.(null);
        }
        hoverLabel.classList.remove("visible");
        return;
      }
      if (data && (data as BoardObject & { analysisTerminal?: boolean }).analysisTerminal) {
        const rect = host.getBoundingClientRect();
        hoverLabel.textContent = (data as BoardObject & { hoverText?: string }).hoverText ?? data.name;
        hoverLabel.style.left = `${event.clientX - rect.left + 14}px`;
        hoverLabel.style.top = `${event.clientY - rect.top + 14}px`;
        hoverLabel.classList.add("visible");
      } else {
        const surfaceHit = resultSurfaceHitAt(event);
        const surfaceData = surfaceHit?.object.userData as {
          contourSamples?: ScalarSample[];
          contourLabel?: string;
          contourUnit?: string;
        } | undefined;
        if (surfaceHit && surfaceData?.contourSamples?.length) {
          const transform = boardTransformRef.current;
          const xMm = transform.centerX + surfaceHit.point.x / transform.scale;
          const yMm = transform.centerY - surfaceHit.point.y / transform.scale;
          const nearestQuery = nearestPointSample(surfaceData.contourSamples, xMm, yMm);
          const nearest = resultSampleForHit(surfaceData.contourSamples, surfaceHit.faceIndex,
            surfaceHit.object.userData.triangleSamples, surfaceHit.instanceId) ?? nearestQuery.sample;
          host.dataset.contourHoverQuery = [
            `samples=${surfaceData.contourSamples.length}`,
            `inspected=${nearestQuery.inspected}`,
            `rings=${nearestQuery.rings}`,
            `buckets=${nearestQuery.bucketCount}`,
          ].join(";");
          if (nearest) {
            const rect = host.getBoundingClientRect();
            const unit = surfaceData.contourUnit ? ` ${surfaceData.contourUnit}` : "";
            hoverLabel.textContent = `${surfaceData.contourLabel ?? "Result"}: ${nearest.value.toPrecision(7)}${unit} | ${nearest.x_mm.toFixed(3)}, ${nearest.y_mm.toFixed(3)} mm | ${nearest.layer ?? "solved layer"} | nearest solver sample`;
            hoverLabel.style.left = `${event.clientX - rect.left + 14}px`;
            hoverLabel.style.top = `${event.clientY - rect.top + 14}px`;
            hoverLabel.classList.add("visible");
          } else {
            hoverLabel.classList.remove("visible");
          }
        } else {
          hoverLabel.classList.remove("visible");
        }
      }
    };
    const onPointerMove = (event: PointerEvent) => {
      if (event.buttons !== 0) {
        renderer.domElement.style.cursor = "grabbing";
        hoverLabel.classList.remove("visible");
        setHoverProbeTarget(null);
        onHoverProbeRef.current?.(null);
        return;
      }
      hoverEvent = event;
      if (!hoverFrame) hoverFrame = requestAnimationFrame(updateHover);
    };
    const selectAt = (event: MouseEvent) => {
      const candidate = hitAt(event);
      if (!candidate) return null;
      const { hit, data } = candidate;
      const transform = boardTransformRef.current;
      const selectedObject = {
        ...data,
        position: [
          transform.centerX + hit.point.x / transform.scale,
          transform.centerY - hit.point.y / transform.scale,
        ] as Point,
      };
      onSelectRef.current(selectedObject);
      return selectedObject;
    };
    let pointerStart = { x: 0, y: 0, button: -1 };
    const onPointerDown = (event: PointerEvent) => {
      pointerStart = { x: event.clientX, y: event.clientY, button: event.button };
      renderer.domElement.style.cursor = "grabbing";
    };
    const onPointerUp = (event: PointerEvent) => {
      const movement = Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y);
      renderer.domElement.style.cursor = viewModeRef.current === "2D" ? "grab" : "default";
      if (viewModeRef.current === "3D" && event.button === 1 && pointerStart.button === 1 && movement <= 3) {
        const point = scenePointAt(event);
        if (point) setOrbitCenter(point);
        return;
      }
      if (event.button !== 0 || pointerStart.button !== 0 || movement > 3) return;
      if (assemblyGizmo.dragging) return;
      if (viewModeRef.current === "3D") {
        viewHelper.center.copy(controls3d.target);
        if (viewHelper.handleClick(event)) return;
      }
      const selectorHit = selectorHitAt(event);
      if (selectorHit) {
        onTopologySelectRef.current?.(selectorHit.object.userData.topologyReference as TopologyReference);
        return;
      }
      const harnessHit = harnessHitAt(event);
      if (harnessHit) {
        onHarnessSelectRef.current?.(harnessHit.object.userData.virtualHarness as VirtualHarnessVisual);
        return;
      }
      const virtualBoardHit = virtualBoardHitAt(event);
      if (virtualBoardHit) {
        onBoardInstanceSelectRef.current?.(virtualBoardHit.object.userData.virtualBoard as VirtualBoardVisual);
        return;
      }
      selectAt(event);
    };
    const onPointerCancel = () => {
      pointerStart = { x: 0, y: 0, button: -1 };
      renderer.domElement.style.cursor = viewModeRef.current === "2D" ? "grab" : "default";
      setHoverProbeTarget(null);
      onHoverProbeRef.current?.(null);
    };
    const onPointerLeave = () => {
      hoverLabel.classList.remove("visible");
      setHoverProbeTarget(null);
      onHoverProbeRef.current?.(null);
    };
    const onContextMenu = (event: MouseEvent) => {
      event.preventDefault();
      const movement = Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y);
      if (pointerStart.button === 2 && movement > 3) return;
      const focusPoint = viewModeRef.current === "3D" ? scenePointAt(event)?.toArray() as [number, number, number] | undefined : undefined;
      const object = selectAt(event);
      onContextMenuRef.current?.({ clientX: event.clientX, clientY: event.clientY, object, focusPoint });
    };
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointerup", onPointerUp);
    renderer.domElement.addEventListener("pointercancel", onPointerCancel);
    renderer.domElement.addEventListener("pointerleave", onPointerLeave);
    renderer.domElement.addEventListener("contextmenu", onContextMenu);

    sceneRef.current = scene;
    rendererRef.current = renderer;
    perspectiveRef.current = perspective;
    orthographicRef.current = orthographic;
    controls3dRef.current = controls3d;
    controls2dRef.current = controls2d;
    boardGroupRef.current = boardGroup;
    assemblyGroupRef.current = assemblyGroup;
    virtualBoardGroupRef.current = virtualBoardGroup;
    harnessGroupRef.current = harnessGroup;
    selectorPreviewGroupRef.current = selectorPreviewGroup;
    resultGroupRef.current = resultGroup;
    thermalGroupRef.current = thermalGroup;
    axisGroupRef.current = axisGroup;
    hoverProbeGroupRef.current = hoverProbeGroup;
    selectionBoxRef.current = selectionBox;
    viewHelperRef.current = viewHelper;
    resize();

    let frame = 0;
    const clock = new THREE.Clock();
    let telemetryStart = performance.now();
    let telemetryFrames = 0;
    let telemetryWorkMs = 0;
    let lastRender = 0;
    let interactionUntil = performance.now() + 300;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const markInteractive = () => { interactionUntil = performance.now() + 300; };
    controls3d.addEventListener("start", markInteractive);
    controls3d.addEventListener("change", markInteractive);
    controls2d.addEventListener("start", markInteractive);
    controls2d.addEventListener("change", markInteractive);
    renderer.domElement.addEventListener("wheel", markInteractive, { passive: true });
    const animate = () => {
      frame = requestAnimationFrame(animate);
      const now = performance.now();
      const animatedHighlight = hoverMaterialsRef.current.size > 0
        || (selectionMaterialsRef.current.size > 0 && selectionBlinkRef.current && !resultOverlayActiveRef.current);
      const activeFps = now < interactionUntil || animatedHighlight
        ? renderProfileRef.current.targetFps
        : Math.min(5, renderProfileRef.current.targetFps);
      if (document.hidden || now - lastRender < 1000 / activeFps) return;
      lastRender = now;
      const delta = clock.getDelta();
      const pulse = 0.28 + 0.72 * (0.5 + 0.5 * Math.sin(now * 0.012));
      hoverMaterialsRef.current.forEach(entry => {
        if (entry instanceof THREE.MeshBasicMaterial) entry.opacity = 0.94 * pulse;
        if (entry instanceof THREE.MeshStandardMaterial) entry.emissiveIntensity = 1.15 * pulse;
      });
      // Keep a persistent amber outline while making the fill/emissive pulse
      // broad enough to remain obvious against dense copper and dark models.
      const selectionPulse = selectionPulseFactor(now, reducedMotion, resultOverlayActiveRef.current, selectionBlinkRef.current);
      selectionMaterialsRef.current.forEach(entry => {
        if (entry instanceof THREE.MeshBasicMaterial) {
          const baseOpacity = Number(entry.userData.spikeSelectionBaseOpacity) || 0.62;
          entry.opacity = baseOpacity * selectionPulse;
        }
        if (entry instanceof THREE.MeshStandardMaterial) {
          const baseIntensity = Number(entry.userData.spikeSelectionBaseIntensity) || 1.45;
          entry.emissiveIntensity = baseIntensity * selectionPulse;
        }
      });
      if (selectionBox.visible) {
        (selectionBox.material as THREE.Material).opacity = 0.82 + 0.18 * selectionPulse;
      }
      controls3d.update();
      controls2d.update();
      const vectorLayoutActive = viewModeRef.current === "2D" && host.classList.contains("layout-active");
      if (!vectorLayoutActive) {
        renderer.info.reset();
        renderer.clear();
        renderer.render(scene, activeCameraRef.current!);
      }
      if (!vectorLayoutActive && viewModeRef.current === "3D") {
        viewHelper.center.copy(controls3d.target);
        if (viewHelper.animating) {
          viewHelper.update(delta);
          controls3d.update();
        }
        viewHelper.render(renderer);
      }
      telemetryFrames += 1;
      telemetryWorkMs += performance.now() - now;
      const elapsed = now - telemetryStart;
      if (elapsed >= 1000) {
        onTelemetryRef.current?.({
          fps: telemetryFrames * 1000 / elapsed,
          frameTimeMs: telemetryWorkMs / telemetryFrames,
          drawCalls: renderer.info.render.calls,
          triangles: renderer.info.render.triangles,
          geometries: renderer.info.memory.geometries,
          textures: renderer.info.memory.textures,
          pixelRatio: renderer.getPixelRatio(),
        });
        telemetryStart = now;
        telemetryFrames = 0;
        telemetryWorkMs = 0;
      }
    };
    animate();

    return () => {
      cancelAnimationFrame(frame);
      if (hoverFrame) cancelAnimationFrame(hoverFrame);
      window.clearTimeout(qualityRestoreTimer);
      observer.disconnect();
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("pointercancel", onPointerCancel);
      renderer.domElement.removeEventListener("pointerleave", onPointerLeave);
      renderer.domElement.removeEventListener("contextmenu", onContextMenu);
      renderer.domElement.removeEventListener("wheel", markInteractive);
      controls3d.removeEventListener("start", markInteractive);
      controls3d.removeEventListener("change", markInteractive);
      controls2d.removeEventListener("start", markInteractive);
      controls2d.removeEventListener("change", markInteractive);
      window.removeEventListener("spike-capture-webgl-frame", captureWebglFrame);
      window.removeEventListener("spike-mcad-gizmo-config", onAssemblyGizmoConfig);
      assemblyGizmo.removeEventListener("mouseDown", onGizmoMouseDown);
      assemblyGizmo.removeEventListener("objectChange", onGizmoObjectChange);
      assemblyGizmo.removeEventListener("mouseUp", onGizmoMouseUp);
      assemblyGizmo.detach();
      scene.remove(assemblyGizmo.getHelper());
      assemblyGizmo.dispose();
      controls3d.dispose();
      controls2d.dispose();
      viewHelper.dispose();
      clearGroup(boardGroup);
      clearGroup(assemblyGroup);
      clearGroup(virtualBoardGroup);
      virtualBoardPickablesRef.current = [];
      clearGroup(harnessGroup);
      harnessPickablesRef.current = [];
      clearGroup(resultGroup);
      clearGroup(thermalGroup);
      clearGroup(axisGroup);
      clearGroup(hoverProbeGroup);
      selectionBox.geometry.dispose();
      (selectionBox.material as THREE.Material).dispose();
      renderer.dispose();
      keyLightRef.current = undefined;
      assemblyGizmoRef.current = undefined;
      syncAssemblyGizmoRef.current = () => undefined;
      refreshVisibleBoundsRef.current = () => undefined;
      hoverLabel.remove();
      host.removeChild(renderer.domElement);
    };
  }, []);

  useEffect(() => {
    const controls = [controls3dRef.current, controls2dRef.current].filter((value): value is OrbitControls => Boolean(value));
    controls.forEach(control => {
      control.enableDamping = navigationInertia;
      if (!navigationInertia) control.update();
    });
    if (hostRef.current) hostRef.current.dataset.navigationInertia = navigationInertia ? "enabled" : "disabled";
  }, [navigationInertia]);

  useEffect(() => {
    const group = boardGroupRef.current;
    if (!group || !activeBoard) return;
    const retryingSameBoard = lastSceneBoardRef.current === activeBoard && modelRetryGeneration > 0;
    lastSceneBoardRef.current = activeBoard;
    clearGroup(group);
    const generation = ++modelGenerationRef.current;
    const proceduralGroup = new THREE.Group();
    proceduralGroup.name = "procedural-board";
    const pickingGroup = new THREE.Group();
    pickingGroup.name = "electrical-picking";
    const accurateGroup = new THREE.Group();
    accurateGroup.name = "kicad-authoritative-model";
    group.add(proceduralGroup, accurateGroup, pickingGroup);
    proceduralGroupRef.current = proceduralGroup;
    pickingGroupRef.current = pickingGroup;
    accurateGroupRef.current = accurateGroup;
    accurateBoardRef.current = undefined;
    accurateComponentsRef.current = undefined;
    setFullModelState(activeBoard.boardModelUrl || activeBoard.fullModelUrl ? "loading" : "none");
    setComponentModelState(activeBoard.componentModelUrl ? "loading" : "none");
    setModelMetrics("");
    setModelError("");
    pickablesRef.current = [];
    pickablesRevisionRef.current += 1;
    objectMapRef.current.clear();

    const centerX = (activeBoard.bounds.minX + activeBoard.bounds.maxX) / 2;
    const centerY = (activeBoard.bounds.minY + activeBoard.bounds.maxY) / 2;
    const scale = 210 / Math.max(activeBoard.width, activeBoard.height, 1);
    boardTransformRef.current = { centerX, centerY, scale };
    const world = (point: Point) => new THREE.Vector2((point[0] - centerX) * scale, (centerY - point[1]) * scale);
    const boardWidth = activeBoard.width * scale;
    const boardHeight = activeBoard.height * scale;
    const boardThickness = boardThicknessMm(activeBoard) * scale;
    const boardSurface = boardThickness / 2;
    const copperClearance = Math.max(0.004 * scale, 0.012);
    const throughHoleRefs = throughHoleComponentRefs(activeBoard.pads);
    const componentPads = new Map<string, ParsedPad[]>();
    activeBoard.pads.forEach((pad) => {
      if (!pad.ref) return;
      const grouped = componentPads.get(pad.ref);
      if (grouped) grouped.push(pad); else componentPads.set(pad.ref, [pad]);
    });
    const boardFeatureCount = activeBoard.tracks.length + activeBoard.zones.length + activeBoard.pads.length + activeBoard.vias.length;
    const proceduralLod = boardFeatureCount > 40_000;
    // Reduce curve tessellation on dense boards, never omit electrical objects.
    // Batching below keeps draw calls bounded while preserving every layer.
    const displayTracks = activeBoard.tracks;
    const displayPads = activeBoard.pads;
    const displayVias = activeBoard.vias;
    const displayComponents = activeBoard.components;
    const poolBatchMaterials = boardFeatureCount >= 1000;
    const displayMaterialPool = new KeyedResourcePool<THREE.MeshStandardMaterial>();
    const viaGeometryPool = new KeyedResourcePool<THREE.BufferGeometry>();
    const copperGeometryPool = new KeyedResourcePool<THREE.BufferGeometry>();
    const displayMaterial = (
      color: number,
      options: { metalness?: number; roughness?: number; opacity?: number; emissive?: number } = {},
    ) => {
      if (!poolBatchMaterials) return material(color, options);
      const key = [
        color, options.metalness ?? 0.15, options.roughness ?? 0.62,
        options.opacity ?? 1, options.emissive ?? 0,
      ].join("|");
      return displayMaterialPool.acquire(key, () => material(color, options));
    };
    boardSizeRef.current = { width: boardWidth, height: boardHeight };
    focusBoundsRef.current = {
      center: new THREE.Vector3(0, 0, boardSurface),
      size: new THREE.Vector3(boardWidth, boardHeight, Math.max(14, boardThickness + 8)),
    };
    // Before authoritative models finish loading, the procedural board remains
    // the fit target and the visible clipping target.
    visibleBoundsRef.current = {
      center: focusBoundsRef.current.center.clone(),
      size: focusBoundsRef.current.size.clone(),
    };
    const loops = activeBoard.outlineLoops.length
      ? activeBoard.outlineLoops
      : [[
        [activeBoard.bounds.minX, activeBoard.bounds.minY],
        [activeBoard.bounds.maxX, activeBoard.bounds.minY],
        [activeBoard.bounds.maxX, activeBoard.bounds.maxY],
        [activeBoard.bounds.minX, activeBoard.bounds.maxY],
        [activeBoard.bounds.minX, activeBoard.bounds.minY],
      ] as Point[]];
    const boardShape = pathFromPoints(loops[0].slice(0, -1).map(world));
    loops.slice(1).forEach((loop) => {
      const points = loop.slice(0, -1).map(world);
      if (points.length > 2) boardShape.holes.push(pathFromPoints(points));
    });

    // The substrate fills the space between conductors. Including the outer
    // copper/finish thickness or extruding a bevel beyond it hides enabled copper.
    const substrateBounds = substrateZBounds(
      activeBoard.layers.length ? copperZ(activeBoard.layers[0], activeBoard.layers, boardThickness, activeBoard.stackup) : undefined,
      activeBoard.layers.length > 1 ? copperZ(activeBoard.layers[activeBoard.layers.length - 1], activeBoard.layers, boardThickness, activeBoard.stackup) : undefined,
      boardThickness,
      copperClearance,
    );
    const substrate = new THREE.Mesh(
      new THREE.ExtrudeGeometry(boardShape, {
        depth: substrateBounds.depth,
        bevelEnabled: false,
        curveSegments: 10,
      }),
      material(0x184b40, { roughness: 0.48 }),
    );
    substrate.position.z = substrateBounds.bottom;
    substrate.receiveShadow = true;
    substrate.castShadow = true;
    substrate.userData.substrate = true;
    identifySceneObject(substrate, "substrate", undefined, "board-substrate", activeBoard.layers);
    proceduralGroup.add(substrate);
    const boardEdges = new THREE.LineSegments(
      new THREE.EdgesGeometry(substrate.geometry, 24),
      new THREE.LineBasicMaterial({ color: 0x4b756c, transparent: true, opacity: 0.75 }),
    );
    boardEdges.position.copy(substrate.position);
    boardEdges.userData.layer = "Edge.Cuts";
    identifySceneObject(boardEdges, "drawing", "Edge.Cuts", "board-outline", activeBoard.layers);
    proceduralGroup.add(boardEdges);

    activeBoard.regions?.filter(region => region.source !== "implicit-board-outline" && region.outline.length >= 3).forEach((region) => {
      const points = Math.hypot(region.outline[0][0] - region.outline[region.outline.length - 1][0], region.outline[0][1] - region.outline[region.outline.length - 1][1]) < 0.015
        ? region.outline.slice(0, -1)
        : region.outline;
      if (points.length < 3) return;
      const color = region.kind === "flex" ? 0xb4883c : region.kind === "stiffener" ? 0x617e91 : region.kind === "transition" ? 0x9a6942 : 0x3b6d62;
      const overlay = new THREE.Mesh(
        new THREE.ShapeGeometry(pathFromPoints(points.map(world)), 8),
        material(color, { roughness: 0.7, opacity: region.kind === "flex" ? 0.46 : 0.3 }),
      );
      overlay.position.z = boardSurface + copperClearance * 0.6;
      overlay.userData = { layer: region.sourceLayer, surface: true, rigidFlexRegion: true, regionKind: region.kind };
      identifySceneObject(overlay, "region", region.sourceLayer, region.id, activeBoard.layers);
      proceduralGroup.add(overlay);
    });
    activeBoard.bendLines?.forEach((bend) => {
      if (bend.points.length < 2) return;
      const geometry = new THREE.BufferGeometry().setFromPoints(bend.points.map(point => {
        const mapped = world(point);
        return new THREE.Vector3(mapped.x, mapped.y, boardSurface + copperClearance * 5);
      }));
      const line = new THREE.Line(geometry, new THREE.LineDashedMaterial({ color: 0xffb84d, dashSize: 1.8, gapSize: 0.9, transparent: true, opacity: 0.92, depthTest: false }));
      line.computeLineDistances();
      line.userData = { layer: bend.sourceLayer, surface: true, rigidFlexBend: true };
      identifySceneObject(line, "drawing", bend.sourceLayer, bend.id, activeBoard.layers);
      proceduralGroup.add(line);
    });

    for (const [layer, z] of [["B.Mask", -boardSurface - copperClearance * 2], ["F.Mask", boardSurface + copperClearance * 2]] as const) {
      const mask = new THREE.Mesh(
        new THREE.ShapeGeometry(boardShape, 10),
        material(0x145a46, { roughness: 0.58, opacity: PROCEDURAL_SOLDERMASK_OPACITY }),
      );
      mask.position.z = z;
      mask.userData.surface = true;
      mask.userData.layer = layer;
      identifySceneObject(mask, "mask", layer, `${layer}-surface`, activeBoard.layers);
      proceduralGroup.add(mask);
    }

    const register = (object: THREE.Object3D, data: BoardObject, pickPriority = 1) => {
      const sceneKind: ViewportSceneKind = data.type === "zone" ? "copper-zone"
        : data.type === "trace" ? "copper-track"
          : data.type === "pad" ? "copper-pad"
            : data.type === "component" ? "component" : "via-face";
      identifySceneObject(object, sceneKind, data.layer, data.id, activeBoard.layers);
      object.userData = { ...object.userData, ...data };
      objectMapRef.current.set(data.id, object);
      if (!(object instanceof THREE.Mesh) || data.type === "via") return;
      const pickMaterial = new THREE.MeshBasicMaterial({
        color: 0x39d6c8,
        transparent: true,
        opacity: 0,
        depthWrite: false,
        colorWrite: false,
        side: THREE.DoubleSide,
      });
      // The display mesh is retired after batching, so its original geometry
      // can become the exact picking proxy. Avoid cloning every track, pad,
      // and zone before batching; the batcher clones only the transformed
      // display buffer and leaves this geometry owned by the picking group.
      object.geometry.userData.spikePickingOwner = true;
      const pickable = new THREE.Mesh(object.geometry, pickMaterial);
      pickable.position.copy(object.position);
      pickable.rotation.copy(object.rotation);
      pickable.scale.copy(object.scale);
      pickable.userData = {
        ...data,
        pickPriority,
        basePositionZ: object.position.z,
        pickingProxy: true,
      };
      identifySceneObject(pickable, "picking", data.layer, `${data.id}-pick`, activeBoard.layers);
      pickingGroup.add(pickable);
      pickablesRef.current.push(pickable);
      objectMapRef.current.set(data.id, pickable);
    };

    activeBoard.zones.forEach((zone) => {
      if (zone.points.length < 3) return;
      const shape = pathFromPoints(zone.points.map(world));
      for (const hole of zone.holes ?? []) shape.holes.push(pathFromPoints(hole.map(world)));
      const mesh = new THREE.Mesh(
        new THREE.ShapeGeometry(shape, 4),
        displayMaterial(layerThreeColor(zone.layer, activeBoard.layers.indexOf(zone.layer)), { metalness: 0.38, roughness: 0.52, opacity: 0.86 }),
      );
      mesh.position.z = copperZ(zone.layer, activeBoard.layers, boardThickness, activeBoard.stackup);
      mesh.receiveShadow = true;
      register(mesh, { id: zone.id, type: "zone", name: zone.net || zone.id, layer: zone.layer, net: zone.net, position: zone.points.length ? [zone.points.reduce((sum, point) => sum + point[0], 0) / zone.points.length, zone.points.reduce((sum, point) => sum + point[1], 0) / zone.points.length] : undefined }, 1);
      proceduralGroup.add(mesh);
    });

    displayTracks.forEach((track) => {
      const start = world(track.start);
      const end = world(track.end);
      const length = start.distanceTo(end);
      const width = Math.max(track.width * scale, 1e-6);
      const capsule = trackCapsuleDimensions(length, width);
      const mesh = new THREE.Mesh(
        copperGeometryPool.acquire(
          `track:${capsule.shapeLength.toFixed(5)}:${capsule.width.toFixed(5)}`,
          () => new THREE.ShapeGeometry(capsulePath(capsule.shapeLength, capsule.width), proceduralLod ? 4 : 8),
        ),
        displayMaterial(layerThreeColor(track.layer, activeBoard.layers.indexOf(track.layer)), { metalness: 0.42, roughness: 0.48 }),
      );
      const surfaceDirection = track.layer === activeBoard.layers[activeBoard.layers.length - 1] ? -1 : 1;
      mesh.position.set((start.x + end.x) / 2, (start.y + end.y) / 2, copperZ(track.layer, activeBoard.layers, boardThickness, activeBoard.stackup) + copperClearance * surfaceDirection);
      mesh.rotation.z = Math.atan2(end.y - start.y, end.x - start.x);
      mesh.receiveShadow = true;
      const data: BoardObject = { id: track.id, type: "trace", name: track.net || track.id, layer: track.layer, net: track.net, position: [(track.start[0] + track.end[0]) / 2, (track.start[1] + track.end[1]) / 2] };
      register(mesh, data, 2);
      proceduralGroup.add(mesh);
    });

    displayPads.forEach((pad) => {
      const position = world(pad.at);
      const padLayers = [...resolveBoardCopperLayers(activeBoard.layers, pad.layers),
        ...["F.Paste", "B.Paste"].filter(layer => pad.layers.includes(layer) || pad.layers.includes("*.Paste"))];
      for (const layer of padLayers) {
        const mesh = new THREE.Mesh(
          copperGeometryPool.acquire(
            `pad:${pad.shape}:${pad.width.toFixed(5)}:${pad.height.toFixed(5)}:${pad.drill.toFixed(5)}:${scale.toFixed(7)}:${pad.customPolygon ? JSON.stringify(pad.customPolygon) : ""}`,
            () => new THREE.ShapeGeometry(padPath(pad, scale), proceduralLod ? 4 : 12),
          ),
          displayMaterial(new THREE.Color(layerCssColor(layer, activeBoard.layers.indexOf(layer))).getHex(), { metalness: 0.48, roughness: 0.43 }),
        );
        const surfaceDirection = layer.startsWith("B.") || layer === activeBoard.layers[activeBoard.layers.length - 1] ? -1 : 1;
        const surfaceZ = layer.endsWith(".Paste") ? surfaceDirection * (boardSurface + copperClearance * 3)
          : copperZ(layer, activeBoard.layers, boardThickness, activeBoard.stackup);
        mesh.position.set(position.x, position.y, surfaceZ + copperClearance * 2 * surfaceDirection);
        mesh.rotation.z = pad.rotation * Math.PI / 180;
        mesh.receiveShadow = true;
        const data: BoardObject = { id: pad.id, type: "pad", name: `${pad.ref ?? ""}.${pad.name}`.replace(/^\./, ""), ref: pad.ref, layer, net: pad.net, position: pad.at };
        register(mesh, data, 4);
        proceduralGroup.add(mesh);
      }
    });

    displayVias.forEach((via) => {
      const position = world(via.at);
      const viaGroup = new THREE.Group();
      const outerRadius = Math.max(via.size * scale / 2, 1e-6);
      const innerRadius = Math.min(Math.max(via.drill * scale / 2, 0), outerRadius);
      const data: BoardObject = { id: via.id, type: "via", name: via.net || via.id, layer: "through", net: via.net, position: via.at };
      const spanLayers = [...new Set(via.layers.filter(layer => activeBoard.layers.includes(layer)))]
        .sort((left, right) => activeBoard.layers.indexOf(left) - activeBoard.layers.indexOf(right));
      const startLayer = spanLayers[0] ?? "F.Cu";
      const endLayer = spanLayers[spanLayers.length - 1] ?? "B.Cu";
      const startZ = copperZ(startLayer, activeBoard.layers, boardThickness, activeBoard.stackup);
      const startLayerIndex = Math.max(activeBoard.layers.indexOf(startLayer), 0);
      const endLayerIndex = Math.max(activeBoard.layers.indexOf(endLayer), startLayerIndex);
      const connectedLayers = activeBoard.layers.slice(startLayerIndex, endLayerIndex + 1);
      const faceLayers = proceduralLod
        ? [...new Set([startLayer, endLayer])]
        : connectedLayers.length ? connectedLayers : [startLayer];
      for (const faceLayer of faceLayers) {
        const ring = new THREE.Mesh(
          viaGeometryPool.acquire(
            `ring:${innerRadius.toFixed(5)}:${outerRadius.toFixed(5)}`,
            () => new THREE.RingGeometry(innerRadius, outerRadius, 28),
          ),
          displayMaterial(0xa96f2f, { metalness: 0.62, roughness: 0.44 }),
        );
        ring.position.z = copperZ(faceLayer, activeBoard.layers, boardThickness, activeBoard.stackup);
        ring.userData = { ...data, viaFaceLayer: faceLayer, basePositionZ: ring.position.z };
        identifySceneObject(ring, "via-face", faceLayer, `${via.id}-${faceLayer}`, activeBoard.layers);
        viaGroup.add(ring);
      }
      const barrelSpans = proceduralLod
        ? [[startLayer, endLayer] as const]
        : connectedLayers.length > 1
        ? connectedLayers.slice(0, -1).map((layer, index) => [layer, connectedLayers[index + 1]] as const)
        : [[startLayer, endLayer] as const];
      barrelSpans.forEach(([segmentStartLayer, segmentEndLayer]) => {
        const segmentStartZ = copperZ(segmentStartLayer, activeBoard.layers, boardThickness, activeBoard.stackup);
        const segmentEndZ = copperZ(segmentEndLayer, activeBoard.layers, boardThickness, activeBoard.stackup);
        const barrelLength = Math.max(Math.abs(segmentStartZ - segmentEndZ), 0.04);
        const barrel = new THREE.Mesh(
          viaGeometryPool.acquire(
            `barrel:${innerRadius.toFixed(5)}:${barrelLength.toFixed(5)}`,
            () => new THREE.CylinderGeometry(innerRadius, innerRadius, barrelLength, 24, 1, true),
          ),
          displayMaterial(0x87592a, { metalness: 0.58, roughness: 0.48 }),
        );
        barrel.rotation.x = Math.PI / 2;
        barrel.position.z = (segmentStartZ + segmentEndZ) / 2;
        barrel.userData = {
          ...data,
          viaBarrel: true,
          viaStartLayer: segmentStartLayer,
          viaEndLayer: segmentEndLayer,
          basePositionZ: barrel.position.z,
          baseScaleY: barrel.scale.y,
        };
        identifySceneObject(barrel, "via-barrel", segmentStartLayer, `${via.id}-${segmentStartLayer}-${segmentEndLayer}`, activeBoard.layers);
        viaGroup.add(barrel);
      });
      viaGroup.position.set(position.x, position.y, 0);
      viaGroup.userData = { ...data, via: true };
      identifySceneObject(viaGroup, "via-barrel", "through", via.id, activeBoard.layers);
      proceduralGroup.add(viaGroup);
      objectMapRef.current.set(data.id, viaGroup);
      const viaPick = new THREE.Mesh(
        new THREE.CircleGeometry(outerRadius * 1.18, 20),
        new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false, side: THREE.DoubleSide }),
      );
      viaPick.position.set(position.x, position.y, startZ + copperClearance * 3);
      viaPick.userData = { ...data, pickPriority: 5, basePositionZ: viaPick.position.z, pickingProxy: true, viaPick: true, viaPickLayer: startLayer };
      identifySceneObject(viaPick, "picking", startLayer, `${via.id}-pick`, activeBoard.layers);
      pickingGroup.add(viaPick);
      pickablesRef.current.push(viaPick);
      objectMapRef.current.set(data.id, viaPick);
    });

    const drawingsByLayer = new Map<string, number[]>();
    activeBoard.drawings.filter((drawing) => drawing.layer !== "Edge.Cuts").forEach((drawing) => {
      const positions = drawingsByLayer.get(drawing.layer) ?? [];
      const bottom = drawing.layer.startsWith("B.");
      const z = bottom ? -boardSurface - copperClearance * 3 : drawing.layer.startsWith("F.") ? boardSurface + copperClearance * 3 : boardSurface + copperClearance * 4;
      for (let index = 0; index < drawing.points.length - 1; index += 1) {
        const start = world(drawing.points[index]);
        const end = world(drawing.points[index + 1]);
        positions.push(start.x, start.y, z);
        positions.push(end.x, end.y, z);
      }
      drawingsByLayer.set(drawing.layer, positions);
    });
    drawingsByLayer.forEach((positions, layer) => {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      const color = layer.endsWith("SilkS") ? 0xe8e2cf
        : layer.endsWith("Fab") ? 0x7196a6
          : layer.endsWith("CrtYd") ? 0xb269a7
            : layer === "Margin" ? 0xd4b958
              : 0x6f8f9c;
      const lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color, transparent: true, opacity: layer.endsWith("SilkS") ? 0.86 : 0.58 }));
      lines.userData.layer = layer;
      identifySceneObject(lines, "drawing", layer, `${layer}-drawings`, activeBoard.layers);
      proceduralGroup.add(lines);
    });

    const placeholderInstances: PlaceholderInstance[] = [];
    displayComponents.forEach((component) => {
      const mount: "smd" | "tht" = throughHoleRefs.has(component.ref) ? "tht" : "smd";
      const data: BoardObject = {
        id: component.id,
        type: "component",
        name: component.value ? `${component.ref} ${component.value}` : component.ref,
        ref: component.ref,
        layer: component.layer,
        model: true,
        mount,
      };
      const bottom = component.layer.startsWith("B.") || activeBoard.layers.length > 1 && component.layer === activeBoard.layers[activeBoard.layers.length - 1];
      const side: 1 | -1 = bottom ? -1 : 1;
      const appearance = componentAppearance(component);
      const dimensions = deriveComponentPlaceholder(component, componentPads.get(component.ref) ?? [], mount);
      const inset = dimensions.planarSource === "body" || dimensions.planarSource === "courtyard" ? 0 : appearance.inset;
      const width = Math.max(dimensions.widthMm * scale * (1 - inset), 1e-6);
      const height = Math.max(dimensions.depthMm * scale * (1 - inset), 1e-6);
      const bodyHeight = Math.max(dimensions.heightMm * scale, 1e-6);
      const localAngle = -component.rotation * Math.PI / 180;
      const offset = dimensions.centerOffsetMm;
      const center = world([
        component.at[0] + offset[0] * Math.cos(localAngle) - offset[1] * Math.sin(localAngle),
        component.at[1] + offset[0] * Math.sin(localAngle) + offset[1] * Math.cos(localAngle),
      ]);
      const bodyZ = bottom ? -boardSurface - bodyHeight / 2 : boardSurface + bodyHeight / 2;
      placeholderInstances.push({ id: component.id, ref: component.ref, layer: component.layer, mount, side, kind: "body", color: appearance.color,
        position: new THREE.Vector3(center.x, center.y, bodyZ), rotationZ: component.rotation * Math.PI / 180, scale: new THREE.Vector3(width, height, bodyHeight) });
      if (/^[CR]/i.test(component.ref)) {
        const capWidth = Math.max(width * 0.14, 1e-6);
        for (const capSide of [-1, 1]) {
          const offset = new THREE.Vector2(capSide * (width / 2 - capWidth / 2), 0).rotateAround(new THREE.Vector2(), component.rotation * Math.PI / 180);
          placeholderInstances.push({ id: component.id, ref: component.ref, layer: component.layer, mount, side, kind: "cap", color: 0xb7b8b4,
            position: new THREE.Vector3(center.x + offset.x, center.y + offset.y, bodyZ), rotationZ: component.rotation * Math.PI / 180, scale: new THREE.Vector3(capWidth, height * 1.02, bodyHeight * 0.72) });
        }
      } else if (/^[UQ]/i.test(component.ref)) {
        const offset = new THREE.Vector2(-width * 0.3, height * 0.3).rotateAround(new THREE.Vector2(), component.rotation * Math.PI / 180);
        const radius = Math.min(width, height) * 0.055;
        placeholderInstances.push({ id: component.id, ref: component.ref, layer: component.layer, mount, side, kind: "marker", color: 0xc7c4b8,
          position: new THREE.Vector3(center.x + offset.x, center.y + offset.y, bottom ? bodyZ - bodyHeight / 2 - 0.04 : bodyZ + bodyHeight / 2 + 0.04),
          rotationZ: component.rotation * Math.PI / 180, scale: new THREE.Vector3(radius, radius, 0.05 * scale) });
      }
      {
        const componentPick = new THREE.Mesh(
          new THREE.BoxGeometry(Math.max(dimensions.widthMm * scale, 1.2), Math.max(dimensions.depthMm * scale, 1.2), Math.max(bodyHeight, 3)),
          new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false }),
        );
        componentPick.position.set(center.x, center.y, 0);
        componentPick.position.z = (component.layer.startsWith("B.") || activeBoard.layers.length > 1 && component.layer === activeBoard.layers[activeBoard.layers.length - 1]) ? -boardSurface - 1 : boardSurface + 1;
        componentPick.rotation.z = component.rotation * Math.PI / 180;
        componentPick.userData = { ...data, pickPriority: 6, basePositionZ: componentPick.position.z, pickingProxy: true };
        identifySceneObject(componentPick, "picking", component.layer, `${component.id}-pick`, activeBoard.layers);
        pickingGroup.add(componentPick);
        pickablesRef.current.push(componentPick);
        objectMapRef.current.set(data.id, componentPick);
      }
    });
    const placeholderRoot = buildProceduralComponentInstances(placeholderInstances);
    placeholderRoot.name = "procedural-component-instances";
    proceduralGroup.add(placeholderRoot);
    pickablesRevisionRef.current += 1;
    if (hostRef.current) hostRef.current.dataset.proceduralLod = [
      `enabled=${proceduralLod}`,
      `tracks=${displayTracks.length}/${activeBoard.tracks.length}`,
      `pads=${displayPads.length}/${activeBoard.pads.length}`,
      `vias=${displayVias.length}/${activeBoard.vias.length}`,
      `components=${displayComponents.length}/${activeBoard.components.length}`,
      "scope=viewport-only",
    ].join(";");

    if (boardFeatureCount >= 1000) {
      const batches = batchProceduralGeometry(proceduralGroup, activeBoard.layers);
      if (hostRef.current) {
        hostRef.current.dataset.proceduralBatches =
          `source-meshes=${batches.sourceMeshes};display-meshes=${batches.displayMeshes}`;
        hostRef.current.dataset.proceduralMaterialPool =
          `requests=${displayMaterialPool.requests};unique=${displayMaterialPool.size}`;
        hostRef.current.dataset.proceduralViaGeometryPool =
          `requests=${viaGeometryPool.requests};unique=${viaGeometryPool.size}`;
        hostRef.current.dataset.proceduralCopperGeometryPool =
          `requests=${copperGeometryPool.requests};unique=${copperGeometryPool.size}`;
      }
    } else if (hostRef.current) {
      hostRef.current.dataset.proceduralBatches = "disabled-small-board";
      hostRef.current.dataset.proceduralMaterialPool = "disabled-small-board";
      hostRef.current.dataset.proceduralViaGeometryPool =
        `requests=${viaGeometryPool.requests};unique=${viaGeometryPool.size}`;
      hostRef.current.dataset.proceduralCopperGeometryPool =
        `requests=${copperGeometryPool.requests};unique=${copperGeometryPool.size}`;
    }

    const boardModelUrl = activeBoard.boardModelUrl ?? activeBoard.fullModelUrl;
    if (boardModelUrl || activeBoard.componentModelUrl) {
      const loadScene = (url: string) => loadSceneWithRetry<THREE.Object3D>(async () => {
        if (boardSceneFormat(url) === "gltf") {
          return (await new GLTFLoader().loadAsync(url)).scene;
        }
        return new VRMLLoader().loadAsync(url);
      });
      Promise.allSettled([
        boardModelUrl ? loadScene(boardModelUrl) : Promise.resolve(null),
        activeBoard.componentModelUrl ? loadScene(activeBoard.componentModelUrl) : Promise.resolve(null),
      ]).then(([boardResult, componentResult]) => {
        if (modelGenerationRef.current !== generation) {
          if (boardResult.status === "fulfilled" && boardResult.value) clearGroup(boardResult.value);
          if (componentResult.status === "fulfilled" && componentResult.value) clearGroup(componentResult.value);
          return;
        }
        if (boardResult.status === "rejected" && (componentResult.status === "rejected" || !componentResult.value)) {
          const error = sceneLoadErrorMessage(boardResult.reason);
          setFullModelState("failed");
          setComponentModelState(activeBoard.componentModelUrl ? "failed" : "none");
          setModelError(`Board scene: ${error}`);
          if (hostRef.current) {
            hostRef.current.dataset.modelLoad = `board=failed;components=${activeBoard.componentModelUrl ? "blocked" : "none"};error=${error}`;
          }
          return;
        }
        const boardAvailable = boardResult.status === "fulfilled" && Boolean(boardResult.value);
        const loadedBoard = boardResult.status === "fulfilled" && boardResult.value ? boardResult.value : new THREE.Group();
        const loadedComponents = componentResult.status === "fulfilled" ? componentResult.value : null;
        setComponentModelState(activeBoard.componentModelUrl
          ? componentResult.status === "fulfilled" ? "ready" : "failed"
          : "none");
        setModelError([
          boardResult.status === "rejected" ? `Board scene: ${sceneLoadErrorMessage(boardResult.reason)}` : "",
          componentResult.status === "rejected" ? `Component scene: ${sceneLoadErrorMessage(componentResult.reason)}` : "",
        ].filter(Boolean).join("; "));
        if (hostRef.current) {
          hostRef.current.dataset.modelLoad = [
            `board=${boardAvailable ? "ready" : boardModelUrl ? "failed" : "none"}`,
            `components=${activeBoard.componentModelUrl ? componentResult.status : "none"}`,
            componentResult.status === "rejected" ? `error=${String(componentResult.reason)}` : "",
          ].filter(Boolean).join(";");
        }
        const boardConsolidated = prepareImportedScene(loadedBoard, "board");
        const boardModel = boardConsolidated.model;
        boardModel.name = "authoritative-board";
        accurateBoardRef.current = boardModel;
        const importedComponentBounds = new Map<string, THREE.Box3>();
        if (loadedComponents) {
          loadedComponents.updateMatrixWorld(true);
          const componentObjectsByName = new Map<string, THREE.Object3D>();
          loadedComponents.traverse(object => {
            if (object.name && !componentObjectsByName.has(object.name)) componentObjectsByName.set(object.name, object);
          });
          activeBoard.components.forEach((component) => {
            const sourceObject = componentObjectsByName.get(component.ref);
            if (!sourceObject) return;
            sourceObject.traverse(object => {
              object.userData.componentMount = throughHoleRefs.has(component.ref) ? "tht" : "smd";
              object.userData.componentSide = (component.layer.startsWith("B.") || activeBoard.layers.length > 1 && component.layer === activeBoard.layers[activeBoard.layers.length - 1]) ? -1 : 1;
            });
            const bounds = new THREE.Box3().setFromObject(sourceObject);
            if (!bounds.isEmpty()) importedComponentBounds.set(component.id, bounds);
          });
        }
        const componentConsolidated = loadedComponents ? prepareImportedScene(loadedComponents, "components") : null;
        const componentModel = componentConsolidated?.model ?? null;
        if (componentModel) {
          componentModel.name = "authoritative-components";
          accurateComponentsRef.current = componentModel;
        }
        const assembly = new THREE.Group();
        assembly.name = "authoritative-assembly";
        assembly.add(boardModel);
        if (componentModel) assembly.add(componentModel);
        const rawBox = new THREE.Box3().setFromObject(boardModel);
        if (rawBox.isEmpty()) {
          // KiCad GLB uses metres, Y up, and the source board XY origin. A
          // failed/absent board export must not block an independent part scene.
          rawBox.set(new THREE.Vector3(activeBoard.bounds.minX / 1000, 0, -activeBoard.bounds.maxY / 1000),
            new THREE.Vector3(activeBoard.bounds.maxX / 1000, boardThicknessMm(activeBoard) / 1000, -activeBoard.bounds.minY / 1000));
        }
        const rawSize = rawBox.getSize(new THREE.Vector3());
        let sourcePlane = "XY";
        if (rawSize.y < rawSize.z && rawSize.y < rawSize.x) {
          assembly.rotation.x = Math.PI / 2;
          sourcePlane = "XZ";
        } else if (rawSize.x < rawSize.y && rawSize.x < rawSize.z) {
          assembly.rotation.y = -Math.PI / 2;
          sourcePlane = "YZ";
        }
        assembly.updateMatrixWorld(true);
        const orientedBox = new THREE.Box3().setFromObject(boardModel);
        const orientedSize = orientedBox.getSize(new THREE.Vector3());
        // KiCad GLB coordinates are metres in the source board coordinate system.
        // Map them through the same Edge.Cuts-derived transform as the electrical
        // pick geometry. Fitting the GLB's rendered bounds includes copper and
        // silkscreen overhangs and causes a visible selection offset.
        const targetScale = scale * 1000;
        if (sourcePlane === "XY") {
          assembly.scale.set(targetScale, -targetScale, targetScale);
        } else {
          assembly.scale.setScalar(targetScale);
        }
        if (sourcePlane === "XZ" || sourcePlane === "XY") {
          assembly.position.x = -centerX * scale;
          assembly.position.y = centerY * scale;
        }
        if (componentModel) {
          const bottomCount = activeBoard.components.filter((component) => (component.layer.startsWith("B.") || activeBoard.layers.length > 1 && component.layer === activeBoard.layers[activeBoard.layers.length - 1])).length;
          componentModel.userData.basePosition = componentModel.position.clone();
          componentModel.userData.sourcePlane = sourcePlane;
          componentModel.userData.targetScale = targetScale;
          componentModel.userData.componentSide = bottomCount > activeBoard.components.length / 2 ? -1 : 1;
        }
        assembly.updateMatrixWorld(true);
        const scaledBox = boardAvailable ? new THREE.Box3().setFromObject(boardModel) : rawBox.clone().applyMatrix4(assembly.matrixWorld);
        if (sourcePlane === "YZ") {
          const alignedCenter = scaledBox.getCenter(new THREE.Vector3());
          assembly.position.x -= alignedCenter.x;
          assembly.position.y -= alignedCenter.y;
        }
        assembly.position.z += -boardSurface - scaledBox.min.z;
        assembly.userData.authoritativeModel = true;
        accurateGroup.add(assembly);
        assembly.updateMatrixWorld(true);
        const componentsById = new Map(activeBoard.components.map(component => [component.id, component]));
        const replacementIds = new Set([...importedComponentBounds.keys()].filter(id => componentsById.has(id)));
        const replacementPicks = partitionComponentProxies(pickablesRef.current, replacementIds);
        replacementPicks.replaced.forEach(object => {
          pickingGroup.remove(object);
          if (object instanceof THREE.Mesh) {
            object.geometry.dispose();
            (object.material as THREE.Material).dispose();
          }
        });
        pickablesRef.current = replacementPicks.retained;
        importedComponentBounds.forEach((sourceBounds, componentId) => {
          const component = componentsById.get(componentId);
          if (!component) return;

          const worldBounds = sourceBounds.clone().applyMatrix4(assembly.matrixWorld);
          const size = worldBounds.getSize(new THREE.Vector3());
          const center = worldBounds.getCenter(new THREE.Vector3());
          const data: BoardObject = {
            id: component.id,
            type: "component",
            name: component.value ? `${component.ref} ${component.value}` : component.ref,
            ref: component.ref,
            layer: component.layer,
            model: true,
            mount: throughHoleRefs.has(component.ref) ? "tht" : "smd",
          };
          const proxy = new THREE.Mesh(
            new THREE.BoxGeometry(Math.max(size.x, 0.1), Math.max(size.y, 0.1), Math.max(size.z, 0.1)),
            new THREE.MeshBasicMaterial({
              color: 0x39d6c8,
              transparent: true,
              opacity: 0,
              depthWrite: false,
              colorWrite: false,
            }),
          );
          proxy.position.copy(center);
          proxy.userData = {
            ...data,
            pickPriority: 6,
            basePositionZ: center.z,
            pickingProxy: true,
            accurateComponentPick: true,
          };
          identifySceneObject(proxy, "picking", component.layer, `${component.id}-accurate-pick`, activeBoard.layers);
          pickingGroup.add(proxy);
          pickablesRef.current.push(proxy);
          objectMapRef.current.set(componentId, proxy);
        });
        pickablesRevisionRef.current += 1;
        const finalBox = new THREE.Box3().setFromObject(assembly);
        const finalSize = finalBox.getSize(new THREE.Vector3());
        const finalCenter = finalBox.getCenter(new THREE.Vector3());
        focusBoundsRef.current = {
          center: finalCenter.clone(),
          size: finalSize.clone(),
        };
        refreshVisibleBoundsRef.current();
        setModelMetrics([
          `raw=${rawSize.x.toFixed(2)},${rawSize.y.toFixed(2)},${rawSize.z.toFixed(2)}`,
          `plane=${sourcePlane}`,
          `scale=${targetScale.toFixed(5)}`,
          `final=${finalSize.x.toFixed(2)},${finalSize.y.toFixed(2)},${finalSize.z.toFixed(2)}`,
          `center=${finalCenter.x.toFixed(2)},${finalCenter.y.toFixed(2)},${finalCenter.z.toFixed(2)}`,
          `boardMeshes=${boardConsolidated.displayMeshes}/${boardConsolidated.sourceMeshes}`,
          `componentMeshes=${componentConsolidated?.displayMeshes ?? 0}/${componentConsolidated?.sourceMeshes ?? 0}`,
        ].join(";"));
        setFullModelState(boardAvailable ? "ready" : boardModelUrl ? "failed" : "none");
      }).catch((error: unknown) => {
        if (modelGenerationRef.current !== generation) return;
        setFullModelState("failed");
        const detail = sceneLoadErrorMessage(error);
        setModelError(`Scene preparation: ${detail}`);
        if (hostRef.current) hostRef.current.dataset.modelLoad = `board=failed;error=${detail}`;
      });
    }

    if (!retryingSameBoard) {
      fittedModesRef.current = new Set([viewModeRef.current]);
      fitRef.current(viewModeRef.current);
    }
    refreshVisibleBoundsRef.current();
  }, [activeBoard, modelRetryGeneration]);

  useEffect(() => {
    const group = assemblyGroupRef.current;
    if (!group) return;
    clearGroup(group);
    const generation = ++assemblyGenerationRef.current;
    if (!assemblyModels.length) {
      setAssemblyModelState("none");
      setAssemblyModelError("");
      if (hostRef.current) hostRef.current.dataset.assemblyModelLoad = "none";
      refreshVisibleBoundsRef.current();
      return;
    }

    const { centerX, centerY, scale } = boardTransformRef.current;
    const assemblyFrame = new THREE.Group();
    assemblyFrame.name = "assembly-frame-mm";
    // Canonical AssemblyIR is right-handed millimetres. The board viewport uses
    // its Edge.Cuts-derived world scale and an inverted screen Y axis.
    assemblyFrame.scale.set(scale, -scale, scale);
    assemblyFrame.position.set(-centerX * scale, centerY * scale, 0);
    group.add(assemblyFrame);
    group.visible = viewMode === "3D" && showModels;
    setAssemblyModelState("loading");
    setAssemblyModelError("");
    onAssemblyPartViewportStatus?.(Object.fromEntries(assemblyModels.map(instance => [instance.partId, "pending" as const])));
    if (hostRef.current) hostRef.current.dataset.assemblyModelLoad = `loading=${assemblyModels.length}`;

    loadScenesBounded(assemblyModels, async instance => {
      const loaded = await loadSceneWithRetry(() => cloneCachedGltfScene(instance.url));
      if (assemblyGenerationRef.current !== generation) { clearGroup(loaded); throw new Error("Scene load cancelled."); }
      const preparedMaterials = new Set<THREE.Material>();
      loaded.name = `${instance.name || instance.partId}-source-metres`;
      loaded.scale.setScalar(1000);
      loaded.traverse(object => {
        if (object instanceof THREE.Mesh) {
          object.castShadow = true;
          object.receiveShadow = true;
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          const cloned = materials.map(entry => {
            const material = entry;
            if (preparedMaterials.has(material)) return material;
            preparedMaterials.add(material);
            material.userData.spikeAssemblyBaseOpacity = entry.opacity;
            material.userData.spikeAssemblyBaseTransparent = entry.transparent;
            material.userData.spikeAssemblyBaseDepthWrite = entry.depthWrite;
            material.opacity = entry.opacity * instance.opacity;
            material.transparent = entry.transparent || instance.opacity < 0.999;
            material.depthWrite = entry.depthWrite && instance.opacity >= 0.999;
            return material;
          });
          object.material = Array.isArray(object.material) ? cloned : cloned[0];
        }
      });
      const modelFrame = new THREE.Group();
      modelFrame.name = `model:${instance.modelId}`;
      modelFrame.matrix.copy(rowMajorMatrix(instance.modelTransform));
      modelFrame.matrixAutoUpdate = false;
      modelFrame.add(loaded);
      const partFrame = new THREE.Group();
      partFrame.name = `part:${instance.partId}`;
      partFrame.userData = {
        spikeSceneIdentity: instance.partId,
        assemblyPartId: instance.partId,
        modelId: instance.modelId,
        modelType: instance.modelType,
        assemblyVisible: instance.visible,
      };
      partFrame.matrix.copy(rowMajorMatrix(instance.partTransform));
      partFrame.matrixAutoUpdate = false;
      partFrame.add(modelFrame);
      return partFrame;
    }, { cancelled: () => assemblyGenerationRef.current !== generation }).then(results => {
      if (assemblyGenerationRef.current !== generation) {
        results.forEach(result => {
          if (result.status === "fulfilled") clearGroup(result.value);
        });
        return;
      }
      let ready = 0;
      const failures: string[] = [];
      const partStates: Record<string, AssemblyPartViewportLoadState> = {};
      results.forEach((result, index) => {
        if (result.status === "fulfilled") {
          assemblyFrame.add(result.value);
          ready += 1;
          partStates[assemblyModels[index].partId] = "ready";
        } else {
          failures.push(`${assemblyModels[index]?.name ?? `part ${index + 1}`}: ${sceneLoadErrorMessage(result.reason)}`);
          partStates[assemblyModels[index].partId] = "failed";
        }
      });
      assemblyFrame.updateMatrixWorld(true);
      if (hostRef.current) {
        const cache = gltfSceneCache.stats;
        hostRef.current.dataset.assemblyResourceCache = `sources=${cache.entries};decoded-bytes=${cache.bytes};occurrences=${cache.users}`;
        hostRef.current.dataset.assemblyModelLoad = [
          `ready=${ready}`,
          `failed=${failures.length}`,
          failures.length ? `error=${failures.join(" | ").slice(0, 320)}` : "",
        ].filter(Boolean).join(";");
      }
      setAssemblyModelState(failures.length ? "failed" : "ready");
      setAssemblyModelError(failures.join(" | "));
      onAssemblyPartViewportStatus?.(partStates);
      refreshAssemblyDisplayRef.current();
      syncAssemblyGizmoRef.current();
    });

    return () => {
      assemblyGenerationRef.current += 1;
      clearGroup(group);
    };
  }, [activeBoard, assemblyModels, onAssemblyPartViewportStatus]);

  useEffect(() => {
    const group = virtualBoardGroupRef.current;
    if (!group) return;
    clearGroup(group);
    virtualBoardPickablesRef.current = [];
    const { centerX, centerY, scale } = boardTransformRef.current;
    const assemblyFrame = new THREE.Group();
    assemblyFrame.name = "virtual-board-frame-mm";
    assemblyFrame.scale.set(scale, -scale, scale);
    assemblyFrame.position.set(-centerX * scale, centerY * scale, 0);
    group.add(assemblyFrame);
    const transformPoint = (matrix: number[], point: readonly [number, number, number]) => new THREE.Vector3(
      matrix[0] * point[0] + matrix[1] * point[1] + matrix[2] * point[2] + matrix[3],
      matrix[4] * point[0] + matrix[5] * point[1] + matrix[6] * point[2] + matrix[7],
      matrix[8] * point[0] + matrix[9] * point[1] + matrix[10] * point[2] + matrix[11],
    );
    for (const boardVisual of virtualBoards) {
      if (boardVisual.active) continue;
      const halfWidth = boardVisual.widthMm / 2;
      const halfHeight = boardVisual.heightMm / 2;
      const [cx, cy, cz] = boardVisual.localCenterMm;
      const corners = [
        [cx - halfWidth, cy - halfHeight, cz], [cx + halfWidth, cy - halfHeight, cz],
        [cx + halfWidth, cy + halfHeight, cz], [cx - halfWidth, cy + halfHeight, cz],
      ].map(point => transformPoint(boardVisual.transform, point as [number, number, number]));
      const geometry = new THREE.BufferGeometry().setFromPoints(corners);
      geometry.setIndex([0, 1, 2, 0, 2, 3]);
      geometry.computeVertexNormals();
      const selected = boardVisual.id === selectedBoardInstanceId;
      const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({
        color: selected ? 0xffb638 : 0x4e91a2,
        transparent: true, opacity: selected ? 0.28 : 0.12,
        side: THREE.DoubleSide, depthWrite: false,
      }));
      mesh.name = `virtual-board:${boardVisual.id}`;
      mesh.renderOrder = selected ? 177 : 170;
      mesh.userData.virtualBoard = boardVisual;
      mesh.userData.virtualBoardId = boardVisual.id;
      assemblyFrame.add(mesh);
      virtualBoardPickablesRef.current.push(mesh);
      const edgePoints = [corners[0], corners[1], corners[1], corners[2], corners[2], corners[3], corners[3], corners[0]];
      const edge = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(edgePoints), new THREE.LineBasicMaterial({ color: selected ? 0xffb638 : 0x74c9d7, transparent: true, opacity: selected ? 1 : 0.65, depthTest: false }));
      edge.renderOrder = selected ? 178 : 171;
      assemblyFrame.add(edge);
    }
    group.visible = viewMode === "3D" && showModels;
    if (hostRef.current) hostRef.current.dataset.virtualBoardScene = `ready=${virtualBoardPickablesRef.current.length};selected=${selectedBoardInstanceId ?? ""}`;
    return () => {
      virtualBoardPickablesRef.current = [];
      clearGroup(group);
    };
  }, [activeBoard, selectedBoardInstanceId, showModels, viewMode, virtualBoards]);

  useEffect(() => {
    const group = harnessGroupRef.current;
    if (!group) return;
    clearGroup(group);
    harnessPickablesRef.current = [];
    if (!virtualHarnesses.length) {
      if (hostRef.current) hostRef.current.dataset.virtualHarnessScene = "ready=0";
      return;
    }
    const { centerX, centerY, scale } = boardTransformRef.current;
    const assemblyFrame = new THREE.Group();
    assemblyFrame.name = "virtual-harness-frame-mm";
    assemblyFrame.scale.set(scale, -scale, scale);
    assemblyFrame.position.set(-centerX * scale, centerY * scale, 0);
    group.add(assemblyFrame);
    for (const harness of virtualHarnesses) {
      const route = harness.routeMm.map(point => new THREE.Vector3(...point));
      if (route.length < 2) continue;
      const curve = new THREE.CatmullRomCurve3(route, false, "centripetal");
      const material = new THREE.LineBasicMaterial({
        color: 0x48c6db,
        transparent: true,
        opacity: 0.72,
        depthTest: false,
        depthWrite: false,
      });
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(harness.routedPolyline ? route : curve.getPoints(16)), material);
      line.name = `harness:${harness.id}`;
      line.renderOrder = 181;
      line.userData.virtualHarness = harness;
      line.userData.harnessId = harness.id;
      assemblyFrame.add(line);
      harnessPickablesRef.current.push(line);
    }
    group.visible = viewMode === "3D" && showModels;
    if (hostRef.current) hostRef.current.dataset.virtualHarnessScene = `ready=${harnessPickablesRef.current.length};selected=${selectedHarnessId ?? ""}`;
    return () => {
      harnessPickablesRef.current = [];
      clearGroup(group);
    };
  }, [activeBoard, showModels, viewMode, virtualHarnesses]);

  useEffect(() => {
    const group = harnessGroupRef.current;
    if (!group) return;
    group.visible = viewMode === "3D" && showModels;
    group.traverse(object => {
      if (!(object instanceof THREE.Line) || typeof object.userData.harnessId !== "string") return;
      const selected = object.userData.harnessId === selectedHarnessId;
      const material = object.material as THREE.LineBasicMaterial;
      material.color.setHex(selected ? 0xffb638 : 0x48c6db);
      material.opacity = selected ? 1 : 0.72;
      material.needsUpdate = true;
      object.renderOrder = selected ? 192 : 181;
    });
    if (hostRef.current) hostRef.current.dataset.virtualHarnessScene = `ready=${harnessPickablesRef.current.length};selected=${selectedHarnessId ?? ""}`;
  }, [selectedHarnessId, showModels, viewMode]);

  useEffect(() => {
    const group = selectorPreviewGroupRef.current;
    if (!group) return;
    clearGroup(group);
    selectorPreviewPickablesRef.current = [];
    if (!assemblySelectorPreviews.length) return;
    const { centerX, centerY, scale } = boardTransformRef.current;
    const assemblyFrame = new THREE.Group();
    assemblyFrame.name = "selector-preview-assembly-frame-mm";
    assemblyFrame.scale.set(scale, -scale, scale);
    assemblyFrame.position.set(-centerX * scale, centerY * scale, 0);
    group.add(assemblyFrame);
    let cancelled = false;
    void loadScenesBounded(assemblySelectorPreviews, async instance => {
      const loaded = await loadSceneWithRetry(() => cloneCachedGltfScene(instance.url));
      if (cancelled) { clearGroup(loaded); throw new Error("Scene load cancelled."); }
      try {
      loaded.name = `selector-preview:${instance.shapeId}:source-metres`;
      loaded.scale.setScalar(1000);
      const pickables: THREE.Object3D[] = [];
      loaded.traverse(object => {
        const topologyId = typeof object.userData?.topology_id === "string" ? object.userData.topology_id : "";
        if (!topologyId) return;
        const reference = instance.references.get(topologyId);
        if (!reference || object.userData?.topology_kind !== reference.topology_kind) {
          throw new Error(`Selector preview ${instance.shapeId} contains an unresolved topology node.`);
        }
        object.userData.topologyReference = reference;
        object.userData.assemblyPartId = instance.partId;
        object.renderOrder = reference.topology_kind === "face" ? 310 : 320;
        if (object instanceof THREE.Mesh) {
          const originals = Array.isArray(object.material) ? object.material : [object.material];
          originals.forEach(material => material.dispose());
          object.material = new THREE.MeshBasicMaterial({ color: 0x45d4b5, transparent: true, opacity: 0.12, depthWrite: false, side: THREE.DoubleSide });
          pickables.push(object);
        } else if (object instanceof THREE.Line) {
          const originals = Array.isArray(object.material) ? object.material : [object.material];
          originals.forEach(material => material.dispose());
          object.material = new THREE.LineBasicMaterial({ color: reference.topology_kind === "axis" ? 0xffc857 : 0x70d7ff, transparent: true, opacity: 0.72, depthTest: false });
          pickables.push(object);
        }
      });
      if (pickables.length !== instance.references.size) {
        clearGroup(loaded);
        throw new Error(`Selector preview ${instance.shapeId} omitted canonical topology nodes.`);
      }
      const modelFrame = new THREE.Group();
      modelFrame.matrix.copy(rowMajorMatrix(instance.modelTransform));
      modelFrame.matrixAutoUpdate = false;
      modelFrame.add(loaded);
      const partFrame = new THREE.Group();
      partFrame.name = `selector-part:${instance.partId}`;
      partFrame.userData = { assemblyPartId: instance.partId, assemblyVisible: instance.visible };
      partFrame.matrix.copy(rowMajorMatrix(instance.partTransform));
      partFrame.matrixAutoUpdate = false;
      partFrame.add(modelFrame);
      return { partFrame, pickables };
      } catch (error) { clearGroup(loaded); throw error; }
    }, { cancelled: () => cancelled }).then(settled => {
      const results = settled.flatMap(result => result.status === "fulfilled" ? [result.value] : []);
      if (cancelled) {
        results.forEach(result => clearGroup(result.partFrame));
        return;
      }
      const failed = settled.find(result => result.status === "rejected");
      if (failed?.status === "rejected") {
        results.forEach(result => clearGroup(result.partFrame));
        throw failed.reason;
      }
      results.forEach(result => assemblyFrame.add(result.partFrame));
      selectorPreviewPickablesRef.current = results.flatMap(result => result.pickables);
      assemblyFrame.updateMatrixWorld(true);
      if (hostRef.current) hostRef.current.dataset.selectorPreviewLoad = `ready=${results.length};selectors=${selectorPreviewPickablesRef.current.length}`;
    }).catch(error => {
      if (!cancelled) {
        selectorPreviewPickablesRef.current = [];
        clearGroup(group);
        if (hostRef.current) hostRef.current.dataset.selectorPreviewLoad = `failed;error=${sceneLoadErrorMessage(error).slice(0, 240)}`;
      }
    });
    return () => {
      cancelled = true;
      selectorPreviewPickablesRef.current = [];
      clearGroup(group);
    };
  }, [activeBoard, assemblySelectorPreviews]);

  useEffect(() => {
    const group = selectorPreviewGroupRef.current;
    if (!group) return;
    group.visible = viewMode === "3D" && showModels && topologySelectorActive;
    const clippingPlanes = assemblySectionClippingPlanes(assemblySection, boardTransformRef.current);
    group.traverse(object => {
      const reference = object.userData?.topologyReference as TopologyReference | undefined;
      const partId = typeof object.userData?.assemblyPartId === "string" ? object.userData.assemblyPartId : "";
      if (partId) object.visible = !isolatedAssemblyPartId || isolatedAssemblyPartId === partId;
      if (!reference) return;
      const selected = reference.topology_id === selectedTopologyId;
      if (object instanceof THREE.Mesh && object.material instanceof THREE.MeshBasicMaterial) {
        object.material.color.setHex(selected ? 0xff5f57 : 0x45d4b5);
        object.material.opacity = selected ? 0.58 : 0.12;
        object.material.clippingPlanes = clippingPlanes;
        object.material.needsUpdate = true;
      } else if (object instanceof THREE.Line && object.material instanceof THREE.LineBasicMaterial) {
        object.material.color.setHex(selected ? 0xff5f57 : reference.topology_kind === "axis" ? 0xffc857 : 0x70d7ff);
        object.material.opacity = selected ? 1 : 0.72;
        object.material.clippingPlanes = clippingPlanes;
        object.material.needsUpdate = true;
      }
    });
  }, [assemblySection, assemblySelectorPreviews, isolatedAssemblyPartId, selectedTopologyId, showModels, topologySelectorActive, viewMode]);

  useEffect(() => {
    const apply = () => {
      const group = assemblyGroupRef.current;
      if (!group) return;
      const clippingPlanes = assemblySectionClippingPlanes(assemblySection, boardTransformRef.current);
      group.traverse(object => {
        const partId = typeof object.userData?.assemblyPartId === "string" ? object.userData.assemblyPartId : "";
        if (partId) {
          object.visible = object.userData.assemblyVisible !== false
            && (!isolatedAssemblyPartId || isolatedAssemblyPartId === partId);
        }
        if (object instanceof THREE.Mesh) {
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach(material => {
            material.clippingPlanes = clippingPlanes;
            material.clipShadows = clippingPlanes.length > 0;
            material.needsUpdate = true;
          });
        }
      });
      refreshVisibleBoundsRef.current();
    };
    refreshAssemblyDisplayRef.current = apply;
    apply();
  }, [assemblyModels, assemblySection, isolatedAssemblyPartId]);

  useEffect(() => {
    if (assemblyGroupRef.current) assemblyGroupRef.current.visible = viewMode === "3D" && showModels;
    syncAssemblyGizmoRef.current();
    refreshVisibleBoundsRef.current();
  }, [showModels, viewMode]);

  useEffect(() => {
    const group = thermalGroupRef.current;
    if (!group) return;
    clearGroup(group);
    if (!activeBoard || !thermalScenario) {
      if (hostRef.current) hostRef.current.dataset.thermalScene = "none";
      refreshVisibleBoundsRef.current();
      return;
    }

    const volume = thermalVolume(thermalScenario);
    const scale = boardTransformRef.current.scale;
    const world = { x: volume.x * scale, y: volume.y * scale, z: volume.z * scale };
    const normalizedThermalField = normalizeThermalFieldResult(thermalScenario.field_result);
    const overlayMaterial = (color: number, opacity: number) => new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity,
      depthWrite: false,
      side: THREE.DoubleSide,
    });

    if (thermalVisibility.volume) {
      const boxGeometry = new THREE.BoxGeometry(world.x, world.y, world.z);
      const fillOpacity = thermalScenario.medium === "potting" ? 0.12 : thermalScenario.enclosure === "sealed" ? 0.045 : 0.018;
      const fill = new THREE.Mesh(boxGeometry, overlayMaterial(thermalScenario.medium === "potting" ? 0x58b9ba : 0x4aa9d8, fillOpacity));
      fill.position.z = world.z / 2;
      fill.renderOrder = 138;
      group.add(fill);
      const outline = new THREE.LineSegments(
        new THREE.EdgesGeometry(boxGeometry),
        new THREE.LineBasicMaterial({ color: 0x67c8ee, transparent: true, opacity: 0.86, depthTest: false }),
      );
      outline.position.copy(fill.position);
      outline.renderOrder = 149;
      group.add(outline);
    }

    if (thermalVisibility.heatSources) {
      (thermalScenario.heat_sources ?? []).forEach((source, index) => {
        const dimensions = source.dimensions_mm;
        const widthMm = Math.max(Number(dimensions?.x) || activeBoard.width * 0.82, 1);
        const depthMm = Math.max(Number(dimensions?.y) || activeBoard.height * 0.82, 1);
        const heightMm = Math.max(Number(dimensions?.z) || 1.2, 0.2);
        const heat = new THREE.Mesh(
          new THREE.BoxGeometry(widthMm * scale, depthMm * scale, heightMm * scale),
          overlayMaterial(0xff5d32, 0.3),
        );
        const position = source.position
          ? thermalPoint(source.position, volume, scale, activeBoard, source.coordinate_frame)
          : new THREE.Vector3(0, 0, 1.15 + heightMm * scale / 2 + index * 0.18);
        heat.position.copy(position);
        heat.renderOrder = 142;
        heat.userData.thermal = { type: "heat-source", id: source.id, power_w: source.power_w };
        group.add(heat);
        const ring = new THREE.LineSegments(
          new THREE.EdgesGeometry(heat.geometry),
          new THREE.LineBasicMaterial({ color: 0xffb04d, transparent: true, opacity: 0.95, depthTest: false }),
        );
        ring.position.copy(position);
        ring.renderOrder = 150;
        group.add(ring);
      });
    }

    if (thermalVisibility.airflow) {
      (thermalScenario.flow_channels ?? []).forEach(channel => {
        const points = (channel.path ?? []).map(point => thermalPoint(point, volume, scale, activeBoard));
        if (points.length < 2) return;
        const curve = new THREE.CatmullRomCurve3(points, false, "centripetal");
        const radius = Math.max(Math.min(Number(channel.width_mm) || 4, Number(channel.height_mm) || 4) * scale * 0.12, 0.55);
        const tube = new THREE.Mesh(
          new THREE.TubeGeometry(curve, Math.max(points.length * 8, 12), radius, 8, false),
          overlayMaterial(0x42d5e8, 0.22),
        );
        tube.renderOrder = 140;
        group.add(tube);
        group.add(thermalLine(points, 0x6eeeff, 0.98));
        points.slice(1).forEach((point, index) => {
          const start = points[index];
          const direction = point.clone().sub(start);
          group.add(thermalArrow(start.clone().lerp(point, 0.58), direction, Math.min(direction.length() * 0.28, 12), 0x8bf5ff));
        });
      });
    }

    if (thermalVisibility.hardware) {
      const elementPositions = new Map<string, THREE.Vector3>();
      (thermalScenario.thermal_elements ?? []).filter(element => element.enabled !== false).forEach((element, index) => {
        const dimensions = element.dimensions_mm ?? {};
        const width = Math.max(Number(dimensions.x) || 1, 0.2) * scale;
        const depth = Math.max(Number(dimensions.y) || 1, 0.2) * scale;
        const height = Math.max(Number(dimensions.z) || 1, 0.2) * scale;
        const position = thermalPoint(element.position ?? [volume.x / 2, volume.y / 2, 1 + index * 0.1], volume, scale, activeBoard, element.coordinate_frame);
        position.z += height / 2;
        elementPositions.set(element.id, position);
        const box = new THREE.Mesh(
          new THREE.BoxGeometry(width, depth, height),
          overlayMaterial(Number(element.power_w) > 0 ? 0xff7138 : element.kind === "mechanical" ? 0x8da4af : 0xc8d5da, Number(element.power_w) > 0 ? 0.16 : 0.08),
        );
        box.position.copy(position);
        box.renderOrder = 141;
        box.userData.thermal = { type: "thermal-element", id: element.id, reference: element.reference, power_w: element.power_w };
        group.add(box);
        const outline = new THREE.LineSegments(new THREE.EdgesGeometry(box.geometry), new THREE.LineBasicMaterial({ color: Number(element.power_w) > 0 ? 0xffa34e : 0xa8c4cf, transparent: true, opacity: 0.8, depthTest: false }));
        outline.position.copy(position);
        outline.renderOrder = 150;
        group.add(outline);
      });
      (thermalScenario.thermal_links ?? []).filter(link => link.enabled !== false).forEach(link => {
        const from = elementPositions.get(link.from_id);
        const to = elementPositions.get(link.to_id);
        if (!from || !to) return;
        const line = thermalLine([from, to], 0xffd166, 0.96);
        (line.material as THREE.LineBasicMaterial).depthTest = false;
        line.renderOrder = 152;
        line.userData.thermal = { type: "thermal-link", id: link.id, resistance_c_per_w: link.resistance_c_per_w };
        group.add(line);
        group.add(thermalArrow(from.clone().lerp(to, 0.42), to.clone().sub(from), Math.min(from.distanceTo(to) * 0.18, 5), 0xffd166));
      });
      (thermalScenario.fans ?? []).filter(fan => fan.enabled !== false).forEach(fan => {
        const position = thermalPoint(fan.position ?? [volume.x * 0.1, volume.y / 2, volume.z / 2], volume, scale, activeBoard);
        const direction = new THREE.Vector3(...(fan.direction ?? [1, 0, 0]));
        direction.set(direction.x, -direction.y, direction.z).normalize();
        const radius = Math.max((Number(fan.diameter_mm) || 20) * scale / 2, 3);
        const fanMesh = new THREE.Mesh(
          new THREE.CylinderGeometry(radius, radius, Math.max((Number(fan.depth_mm) || 25) * scale, 1.2), 32, 1, true),
          overlayMaterial(0x63d69a, 0.2),
        );
        fanMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction);
        fanMesh.position.copy(position);
        fanMesh.renderOrder = 143;
        fanMesh.userData.thermal = { type: "fan", id: fan.id, name: fan.name, flow_rate_m3_s: fan.flow_rate_m3_s, static_pressure_pa: fan.static_pressure_pa, rpm: fan.rpm };
        group.add(fanMesh);
        group.add(thermalArrow(position, direction, Math.max(radius * 1.5, 8), 0x68f2ac));
      });

      (thermalScenario.virtual_heatsinks ?? []).filter(heatsink => heatsink.enabled !== false).forEach((heatsink, index) => {
        const dimensions = heatsink.dimensions_mm ?? {};
        const width = Math.max(Number(dimensions.x) || 40, 2) * scale;
        const depth = Math.max(Number(dimensions.y) || 40, 2) * scale;
        const height = Math.max(Number(dimensions.z) || 15, 1) * scale;
        const position = heatsink.position
          ? thermalPoint(heatsink.position, volume, scale, activeBoard)
          : new THREE.Vector3(0, 0, 2 + height / 2 + index * 1.2);
        const sink = new THREE.Group();
        const base = new THREE.Mesh(new THREE.BoxGeometry(width, depth, Math.max(height * 0.16, 0.8)), overlayMaterial(0xb8c9d0, 0.48));
        base.position.z = -height / 2 + Math.max(height * 0.08, 0.4);
        sink.add(base);
        const finCount = Math.max(0, Math.min(40, Math.round(Number(heatsink.fin_count) || 0)));
        const finHeight = Math.min(Math.max((Number(heatsink.fin_height_mm) || Number(dimensions.z) * 0.8) * scale, 0.2), height * 0.92);
        const finThickness = Math.max((Number(heatsink.fin_thickness_mm) || 1) * scale, 0.12);
        for (let finIndex = 0; finIndex < finCount; finIndex += 1) {
          const fin = new THREE.Mesh(
            new THREE.BoxGeometry(Math.min(finThickness, width / Math.max(finCount, 1) * 0.9), depth, finHeight),
            overlayMaterial(0xc8d8de, 0.38),
          );
          fin.position.set(-width / 2 + width * (finIndex + 0.5) / finCount, 0, -height / 2 + Math.max(height * 0.16, 0.8) + finHeight / 2);
          sink.add(fin);
        }
        sink.position.copy(position);
        sink.renderOrder = 144;
        sink.userData.thermal = { type: "heatsink", id: heatsink.id, name: heatsink.name, target: heatsink.target, material: heatsink.material, interface_resistance_c_per_w: heatsink.interface_resistance_c_per_w };
        group.add(sink);
      });

      (thermalScenario.openings ?? []).forEach((opening, index) => {
        const x = opening.face === "-X" ? -world.x / 2 : world.x / 2;
        const z = world.z * (0.38 + index * 0.08);
        const size = Math.max(Math.min(world.y, world.z) * 0.16, 3);
        const points = [
          new THREE.Vector3(x, -size, z - size), new THREE.Vector3(x, size, z - size),
          new THREE.Vector3(x, size, z + size), new THREE.Vector3(x, -size, z + size),
          new THREE.Vector3(x, -size, z - size),
        ];
        group.add(thermalLine(points, 0xffcf66, 0.96));
      });
    }

    // Field samples use instancing, a hard LOD budget, and the coordinate
    // contract shared with fixtures.  No interpolation or inferred heat map.
    if (thermalVisibility.field !== false) {
      const preferred: ThermalFieldName | undefined = normalizedThermalField?.fields?.temperature_c?.length ? "temperature_c"
        : normalizedThermalField?.fields?.heat_flux_w_m2?.length ? "heat_flux_w_m2"
          : normalizedThermalField?.fields?.temperature_gradient_c_per_mm?.length ? "temperature_gradient_c_per_mm" : undefined;
      const sourceSamples = preferred ? normalizedThermalField?.fields?.[preferred] ?? [] : [];
      const samples = thinThermalFieldSamples(sourceSamples, 9000);
      if (samples.length) {
        const extent = thermalFieldExtent(sourceSamples);
        const geometry = new THREE.SphereGeometry(Math.max(scale * 0.42, 0.18), 6, 4);
        const material = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.78, depthWrite: false, vertexColors: true });
        const cloud = new THREE.InstancedMesh(geometry, material, samples.length);
        const matrix = new THREE.Matrix4(); const color = new THREE.Color();
        samples.forEach((sample, index) => {
          const point = thermalPoint(sample.position_mm, volume, scale, activeBoard, sample.coordinate_frame);
          matrix.makeTranslation(point.x, point.y, point.z); cloud.setMatrixAt(index, matrix);
          const rgb = thermalFieldColor(sample.value, extent.minimum, extent.maximum); color.setRGB(...rgb); cloud.setColorAt(index, color);
        });
        cloud.instanceMatrix.needsUpdate = true;
        if (cloud.instanceColor) cloud.instanceColor.needsUpdate = true;
        cloud.renderOrder = 147;
        cloud.userData.thermal = { type: "field", field: preferred, published_samples: sourceSamples.length, displayed_samples: samples.length, status: normalizedThermalField?.status, model_status: normalizedThermalField?.model_status };
        group.add(cloud);
      }
    }

    if (hostRef.current) {
      hostRef.current.dataset.thermalScene = [
        `volume=${thermalVisibility.volume ? 1 : 0}`,
        `sources=${thermalScenario.heat_sources?.length ?? 0}`,
        `channels=${thermalScenario.flow_channels?.length ?? 0}`,
        `fans=${thermalScenario.fans?.length ?? 0}`,
        `heatsinks=${thermalScenario.virtual_heatsinks?.length ?? 0}`,
        `elements=${thermalScenario.thermal_elements?.length ?? 0}`,
        `links=${thermalScenario.thermal_links?.length ?? 0}`,
        `field=${normalizedThermalField?.fields?.temperature_c?.length ?? normalizedThermalField?.fields?.heat_flux_w_m2?.length ?? normalizedThermalField?.fields?.temperature_gradient_c_per_mm?.length ?? 0}`,
        `field_status=${normalizedThermalField?.status ?? "no_published_field"}`,
      ].join(";");
    }
    // Thermal fixtures should extend the depth range but must never replace
    // the PCB as the target of Fit.
    refreshVisibleBoundsRef.current();
  }, [activeBoard, thermalScenario, thermalVisibility]);

  useEffect(() => {
    const group = axisGroupRef.current;
    if (!group) return;
    clearGroup(group);
    const resultsActive = Boolean(analysisResult && resultVisualization?.visible && resultVisualization.mode !== "geometry");
    group.visible = showAxes && viewMode === "3D";
    if (!group.visible || !activeBoard) return;
    const { scale, centerX, centerY } = boardTransformRef.current;
    const size = Math.max(activeBoard.width, activeBoard.height, 10) * scale * 1.35;
    const divisions = Math.max(10, Math.min(40, Math.ceil(size / Math.max(scale * 5, 1))));
    const grid = new THREE.GridHelper(size, divisions, 0x66808b, 0x30434b);
    grid.rotation.x = Math.PI / 2;
    grid.position.z = -boardThicknessMm(activeBoard) * scale / 2 - 0.65;
    const materials = Array.isArray(grid.material) ? grid.material : [grid.material];
    materials.forEach(material => {
      material.transparent = true;
      material.opacity = 0.52;
      material.depthWrite = false;
    });
    grid.renderOrder = -10;
    group.add(grid);
    const axes = new THREE.AxesHelper(Math.max(size * 0.16, 8));
    axes.position.set(-size / 2, -size / 2, grid.position.z + 0.04);
    axes.renderOrder = 140;
    group.add(axes);
    if (!resultsActive) return;
    const xTicks = resultAxisTicks(activeBoard.bounds.minX, activeBoard.bounds.maxX);
    const yTicks = resultAxisTicks(activeBoard.bounds.minY, activeBoard.bounds.maxY);
    const tickLength = Math.max(size * 0.012, 1.2);
    const axisZ = grid.position.z + 0.08;
    const xAxisY = (centerY - activeBoard.bounds.minY) * scale;
    const yAxisX = (activeBoard.bounds.minX - centerX) * scale;
    const tickMaterial = new THREE.LineBasicMaterial({ color: 0x9bb5bf, transparent: true, opacity: 0.9, depthTest: false, depthWrite: false });
    const addTick = (points: THREE.Vector3[], text: string, labelPosition: THREE.Vector3) => {
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), tickMaterial);
      line.renderOrder = 405;
      group.add(line);
      const label = overlayLabel(text, "#b9d0d7", Math.max(size * 0.018, 3.6));
      if (label) {
        label.position.copy(labelPosition);
        group.add(label);
      }
    };
    xTicks.forEach(value => {
      const x = (value - centerX) * scale;
      addTick(
        [new THREE.Vector3(x, xAxisY, axisZ), new THREE.Vector3(x, xAxisY - tickLength, axisZ)],
        formatViewportAxisTick(value),
        new THREE.Vector3(x, xAxisY - tickLength * 3.1, axisZ + 0.2),
      );
    });
    yTicks.forEach(value => {
      const y = (centerY - value) * scale;
      addTick(
        [new THREE.Vector3(yAxisX, y, axisZ), new THREE.Vector3(yAxisX - tickLength, y, axisZ)],
        formatViewportAxisTick(value),
        new THREE.Vector3(yAxisX - tickLength * 4.2, y, axisZ + 0.2),
      );
    });
    const xUnit = overlayLabel("X (mm)", "#ed6f6a", Math.max(size * 0.021, 4.2));
    if (xUnit) { xUnit.position.set((activeBoard.bounds.maxX - centerX) * scale, xAxisY - tickLength * 6.3, axisZ + 0.3); group.add(xUnit); }
    const yUnit = overlayLabel("Y (mm)", "#64d8a3", Math.max(size * 0.021, 4.2));
    if (yUnit) { yUnit.position.set(yAxisX - tickLength * 7.8, (centerY - activeBoard.bounds.maxY) * scale, axisZ + 0.3); group.add(yUnit); }
    const visualization = resultVisualization;
    const resultSamples = analysisResult && visualization ? viewportScalarSamples(analysisResult, visualization.mode) : [];
    if (resultSamples.length && visualization && visualization.plotStyle !== "flat") {
      const values = resultSamples.map(sample => sample.value).filter(Number.isFinite);
      const extent = numericExtent(values);
      const amplitude = THREE.MathUtils.clamp(
        Math.max(activeBoard.width, activeBoard.height) * scale * 0.11 * (visualization.waveHeightScale || 1),
        1.2,
        42,
      );
      const zX = yAxisX;
      const zY = xAxisY;
      const zLine = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(zX, zY, axisZ),
          new THREE.Vector3(zX, zY, axisZ + amplitude),
        ]),
        new THREE.LineBasicMaterial({ color: 0x63b8ff, depthTest: false, depthWrite: false }),
      );
      zLine.renderOrder = 406;
      group.add(zLine);
      const metadata = viewportResultField(visualization.mode);
      [0, 0.5, 1].forEach(ratio => {
        const value = extent.minimum + (extent.maximum - extent.minimum) * ratio;
        const z = axisZ + amplitude * ratio;
        addTick(
          [new THREE.Vector3(zX, zY, z), new THREE.Vector3(zX - tickLength, zY, z)],
          formatViewportResultTick(value, metadata.unit),
          new THREE.Vector3(zX - tickLength * 4.8, zY, z + 0.2),
        );
      });
      const zUnit = overlayLabel(metadata.label, "#79c7ff", Math.max(size * 0.019, 3.8));
      if (zUnit) {
        zUnit.position.set(zX - tickLength * 5.2, zY, axisZ + amplitude + tickLength * 1.8);
        group.add(zUnit);
      }
    }
  }, [activeBoard, analysisResult, resultVisualization, showAxes, viewMode]);

  useEffect(() => {
    const perspective = perspectiveRef.current;
    const orthographic = orthographicRef.current;
    const controls3d = controls3dRef.current;
    const controls2d = controls2dRef.current;
    if (!perspective || !orthographic || !controls3d || !controls2d) return;
    viewModeRef.current = viewMode;
    activeCameraRef.current = viewMode === "2D" ? orthographic : perspective;
    controls2d.enabled = viewMode === "2D";
    controls3d.enabled = viewMode === "3D";
    if (!fittedModesRef.current.has(viewMode)) {
      fitRef.current(viewMode);
      fittedModesRef.current.add(viewMode);
    }
  }, [viewMode, fullModelState]);

  useEffect(() => {
    const controls3d = controls3dRef.current;
    const host = hostRef.current;
    if (!controls3d || !host) return;
    controls3d.mouseButtons.LEFT = navigationMode === "pan" ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
    host.dataset.inputMap = navigationMode === "pan"
      ? "left=pan;middle=pan;right=pan;wheel=zoom"
      : "left=orbit;middle-click=orbit-center;middle-drag=pan;right=pan;wheel=zoom";
  }, [navigationMode]);

  useEffect(() => {
    const group = proceduralGroupRef.current;
    if (!group) return;
    const copperLayers = activeBoard?.layers ?? [];
    const viasOnlyActive = showVias
      && Object.keys(visibleLayers).length > 0
      && Object.values(visibleLayers).every(visible => !visible);
    const stackMidpoint = Math.max((copperLayers.length - 1) / 2, 0.5);
    const worldSpacing = layerSeparation * (210 / Math.max(activeBoard?.width ?? 210, activeBoard?.height ?? 210, 1));
    const offsetForLayer = (layer?: string) => {
      if (!layer || layer === "through") return 0;
      const copperIndex = copperLayers.indexOf(layer);
      if (copperIndex >= 0) return (stackMidpoint - copperIndex) * worldSpacing;
      if (layer.startsWith("F.")) return stackMidpoint * worldSpacing;
      if (layer.startsWith("B.")) return -stackMidpoint * worldSpacing;
      return 0;
    };
    const spatialResult = resultVisualization?.mode !== "geometry";
    const analysisView = Boolean(resultVisualization?.visible && (resultVisualization.translucentScene || resultVisualization.analysisOnly || spatialResult));
    const analysisOnlyScene = resultVisualization?.sceneMode === "analysis_only";
    const resultsOnlyScene = resultVisualization?.sceneMode === "results_only";
    const resultModelsVisible = resultVisualization?.showComponentModels !== false;
    const categoryFilterActive = !showSmdModels || !showThtModels;
    const presentation = boardSceneVisibility({
      is3D: viewMode === "3D", boardReady: fullModelState === "ready",
      componentsReady: componentModelState === "ready", split: splitSceneAvailable,
      layerFiltered: layerFilterActive, exploded: layerSeparation > 0.001,
      isolated: Boolean(isolatedNet), analysisOnly: analysisOnlyScene, resultsOnly: resultsOnlyScene,
      showModels, categoryFiltered: categoryFilterActive, resultModelsVisible,
      missingModels: missingModelRefs.length > 0,
    });
    const authoritativeAnalysisView = analysisView && presentation.importedBoard;
    const authoritativeView = !analysisView && presentation.importedBoard;
    group.visible = presentation.proceduralRoot;
    if (accurateGroupRef.current) accurateGroupRef.current.visible = presentation.importedRoot;
    if (accurateBoardRef.current) accurateBoardRef.current.visible = presentation.importedBoard;
    if (accurateComponentsRef.current) accurateComponentsRef.current.visible = presentation.importedComponents;
    if (hostRef.current) hostRef.current.dataset.groupVisibility = JSON.stringify(presentation);
    const authoritativeOpacity = authoritativeAnalysisView && resultVisualization?.sceneMode === "translucent"
      ? resultVisualization.boardOpacity
      : 1;
    accurateGroupRef.current?.traverse(object => {
      if (!(object instanceof THREE.Mesh)) return;
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.forEach(entry => {
        const settings = entry.userData as { spikeBaseOpacity?: number; spikeBaseTransparent?: boolean; spikeBaseDepthWrite?: boolean };
        settings.spikeBaseOpacity ??= entry.opacity;
        settings.spikeBaseTransparent ??= entry.transparent;
        settings.spikeBaseDepthWrite ??= entry.depthWrite;
        const wasTransparent = entry.transparent;
        entry.opacity = (settings.spikeBaseOpacity ?? 1) * authoritativeOpacity;
        entry.transparent = Boolean(settings.spikeBaseTransparent) || authoritativeOpacity < 0.999;
        entry.depthWrite = authoritativeOpacity >= 0.999 && settings.spikeBaseDepthWrite !== false;
        if (entry.transparent !== wasTransparent) entry.needsUpdate = true;
      });
    });
    const missingModelSet = new Set(missingModelRefs);
    const hoverMaterials = new Set<THREE.Material>();
    const selectionMaterials = new Set<THREE.Material>();
    const resultFieldActive = solverResultOverlayActive(analysisResult, resultVisualization);
    const proceduralModelsAllowed = !activeBoard?.componentModelUrl || componentModelState !== "ready";
    const placeholderRoot = group.getObjectByName("procedural-component-instances");
    if (placeholderRoot) updateProceduralComponentInstances(placeholderRoot, {
      showModels: presentation.proceduralComponents,
      showSmd: showSmdModels,
      showTht: showThtModels,
      allowAll: proceduralModelsAllowed,
      missingRefs: missingModelSet,
      selectedId,
      hoverId: hoverPreview?.id,
      hoverRef: hoverPreview?.ref,
      separationForLayer: layer => offsetForLayer(layer),
    });
    group.traverse((object) => {
      if (object === group) return;
      if (object === placeholderRoot) return;
      const data = object.userData as Partial<BoardObject> & {
        surface?: boolean;
        model?: boolean;
        mount?: "smd" | "tht";
        separationAnchor?: boolean;
        via?: boolean;
        viaFaceLayer?: string;
        viaBarrel?: boolean;
        viaStartLayer?: string;
        viaEndLayer?: string;
        substrate?: boolean;
        basePositionZ?: number;
        baseScaleY?: number;
        proceduralComponentBatch?: boolean;
      };
      if (data.proceduralComponentBatch) return;
      // A component's footprint layer controls placement, not model visibility.
      // Copper toggles must never hide SMD/THT models placed on that side.
      const visibilityLayer = data.viaFaceLayer ?? data.layer;
      const faceVisible = layerObjectVisible(visibilityLayer, Boolean(data.model), visibleLayers);
      const layerVisible = viasOnlyActive && data.via ? true : data.viaBarrel
        ? viaSpanVisible(data.viaStartLayer, data.viaEndLayer, copperLayers, visibleLayers)
        : faceVisible;
      const surfaceVisible = !data.surface || viewMode === "3D";
      const missingModelFallback = Boolean(data.model && data.ref && missingModelSet.has(data.ref));
      const categoryVisible = data.mount === "tht" ? showThtModels : data.mount === "smd" ? showSmdModels : true;
      const modelVisible = !data.model || showModels && resultModelsVisible && categoryVisible && viewMode === "3D" && (proceduralModelsAllowed || missingModelFallback);
      const authoritativeFallbackVisible = !authoritativeView || Boolean(data.model && presentation.proceduralComponents);
      const viaVisible = !data.via || showVias;
      const inspectingCopper = copperLayers.some(layer => visibleLayers[layer] === false) || layerSeparation > 0.001;
      const substrateVisible = !data.substrate || !viasOnlyActive && !inspectingCopper;
      const isolatedVisible = !isolatedNet || Boolean(data.net && data.net === isolatedNet);
      const analyzed = Boolean(data.net && analysisNetSet.has(data.net));
      const analysisVisible = analysisOnlyScene
        ? analyzed || Boolean(data.model && resultModelsVisible)
        : !resultVisualization?.analysisOnly || analyzed || Boolean(data.substrate || data.surface);
      object.visible = layerVisible && surfaceVisible && modelVisible && viaVisible && substrateVisible && isolatedVisible && analysisVisible && authoritativeFallbackVisible;
      if (data.layer && (!data.model || data.separationAnchor)) {
        data.basePositionZ ??= object.position.z;
        object.position.z = data.basePositionZ + offsetForLayer(data.layer);
      }
      if (data.viaFaceLayer) {
        data.basePositionZ ??= object.position.z;
        object.position.z = data.basePositionZ + offsetForLayer(data.viaFaceLayer);
      }
      if (data.viaBarrel && data.viaStartLayer && data.viaEndLayer) {
        data.baseScaleY ??= object.scale.y;
        data.basePositionZ ??= object.position.z;
        const segmentOffset = (offsetForLayer(data.viaStartLayer) + offsetForLayer(data.viaEndLayer)) / 2;
        object.position.z = data.basePositionZ + segmentOffset;
        object.scale.y = data.baseScaleY;
      }
      if (data.layer && !data.model && (object instanceof THREE.Mesh || object instanceof THREE.LineSegments)) {
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        materials.forEach((entry) => {
          const settings = entry.userData as { baseOpacity?: number; baseTransparent?: boolean; baseDepthWrite?: boolean };
          if (settings.baseOpacity === undefined) {
            settings.baseOpacity = entry.opacity;
            settings.baseTransparent = entry.transparent;
            settings.baseDepthWrite = entry.depthWrite;
          }
          const opacity = layerOpacity[data.layer!] ?? 1;
          const sceneOpacity = resultVisualization?.sceneMode === "translucent" ? resultVisualization.boardOpacity : 1;
          const analysisOpacity = sceneOpacity;
          const wasTransparent = entry.transparent;
          entry.opacity = (settings.baseOpacity ?? 1) * opacity * analysisOpacity;
          entry.transparent = Boolean(settings.baseTransparent) || opacity < 0.999 || analysisOpacity < 0.999;
          entry.depthWrite = opacity >= 0.999 && analysisOpacity >= 0.999 && settings.baseDepthWrite !== false;
          if (entry.transparent !== wasTransparent) entry.needsUpdate = true;
        });
      }
      if (object instanceof THREE.Mesh && data.id) {
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        materials.forEach((entry) => {
          if (entry instanceof THREE.MeshStandardMaterial) {
            const selected = data.id === selectedId;
            const previewed = Boolean(hoverPreview && (hoverPreview.kind === "net" ? data.net === hoverPreview.net : data.id === hoverPreview.id || Boolean(hoverPreview.ref && data.ref === hoverPreview.ref)));
            entry.emissive.set(previewed ? 0xff38c7 : selected ? 0xffa51f : 0x000000);
            entry.emissiveIntensity = previewed ? 1.15 : selected ? 1.45 : 0;
            if (previewed) hoverMaterials.add(entry);
            if (selected && !previewed) {
              entry.userData.spikeSelectionBaseIntensity = 1.45;
              selectionMaterials.add(entry);
            }
          }
        });
      }
    });
    const accurateComponents = accurateComponentsRef.current;
    if (accurateComponents) {
      const basePosition = accurateComponents.userData.basePosition as THREE.Vector3 | undefined;
      const sourcePlane = accurateComponents.userData.sourcePlane as string | undefined;
      const targetScale = Number(accurateComponents.userData.targetScale) || 1;
      if (basePosition) {
        accurateComponents.position.copy(basePosition);
      }
      accurateComponents.traverse(object => {
        if (!(object instanceof THREE.Mesh)) return;
        const mount = object.userData.componentMount;
        object.visible = mount === "smd" ? showSmdModels : mount === "tht" ? showThtModels : showSmdModels || showThtModels;
        object.userData.baseComponentPosition ??= object.position.clone();
        object.position.copy(object.userData.baseComponentPosition as THREE.Vector3);
        const localOffset = (Number(object.userData.componentSide) || 1) * stackMidpoint * worldSpacing / targetScale;
        if (sourcePlane === "XZ") object.position.y += localOffset;
        else if (sourcePlane === "YZ") object.position.x += localOffset;
        else object.position.z += localOffset;
      });
    }
    const pickingGroup = pickingGroupRef.current;
    pickingGroup?.traverse((object) => {
      if (!(object instanceof THREE.Mesh) || !object.userData.pickingProxy) return;
      const data = object.userData as Partial<BoardObject> & {
        basePositionZ?: number;
        viaPick?: boolean;
        viaPickLayer?: string;
      };
      const componentProxy = data.type === "component" || Boolean(data.model);
      const categoryVisible = data.mount === "tht" ? showThtModels : data.mount === "smd" ? showSmdModels : true;
      const layerVisible = componentProxy
        ? showModels && categoryVisible && viewMode === "3D"
        : viasOnlyActive && data.viaPick ? true : layerObjectVisible(data.viaPickLayer ?? data.layer, false, visibleLayers);
      const pickMaterial = object.material as THREE.MeshBasicMaterial;
      const exactSelected = data.id === selectedId;
      const netHighlighted = Boolean(data.net && (data.net === selectedNet || data.net === isolatedNet));
      const previewed = Boolean(hoverPreview && (hoverPreview.kind === "net" ? data.net === hoverPreview.net : data.id === hoverPreview.id || Boolean(hoverPreview.ref && data.ref === hoverPreview.ref)));
      const analysisHighlighted = Boolean(resultVisualization?.analysisOnly && data.net && analysisNetSet.has(data.net));
      const visualHighlighted = exactSelected || analysisHighlighted || !resultFieldActive && netHighlighted;
      const visualPreviewed = previewed && (!resultFieldActive || hoverPreview?.kind !== "net");
      // Raycaster explicitly tests these objects even when `visible` is false.
      // Keep dormant proxies out of the render list; this removes one draw call
      // per track/pad/via/component on large boards without changing picking.
      object.visible = layerVisible && (!isolatedNet || data.net === isolatedNet) && (visualHighlighted || visualPreviewed);
      object.position.z = (data.basePositionZ ?? object.position.z)
        + (data.viaPick && data.viaPickLayer ? offsetForLayer(data.viaPickLayer) : offsetForLayer(data.layer));
      pickMaterial.colorWrite = visualHighlighted || visualPreviewed;
      pickMaterial.opacity = visualPreviewed ? 0.94 : exactSelected ? 0.92 : visualHighlighted ? 0.74 : 0;
      pickMaterial.color.setHex(visualPreviewed ? 0xff38c7 : exactSelected ? 0xffb638 : 0x39d6c8);
      if (visualPreviewed) hoverMaterials.add(pickMaterial);
      if (visualHighlighted && !visualPreviewed) {
        pickMaterial.userData.spikeSelectionBaseOpacity = pickMaterial.opacity;
        selectionMaterials.add(pickMaterial);
      }
    });
    const selectionBox = selectionBoxRef.current;
    const selected = selectedId ? objectMapRef.current.get(selectedId) : undefined;
    if (selectionBox) {
      selectionBox.visible = Boolean(selected);
      if (selected) {
        selectionBox.setFromObject(selected);
      }
    }
    hoverMaterialsRef.current = hoverMaterials;
    selectionMaterialsRef.current = selectionMaterials;
  }, [activeBoard, visibleLayers, layerOpacity, layerSeparation, showVias, selectedId, selectedNet, isolatedNet, hoverPreview, showModels, showSmdModels, showThtModels, viewMode, fullModelState, componentModelState, layerFilterActive, splitSceneAvailable, resultSceneKey, analysisResult, analysisNets, missingModelRefs]);

  // Selection, hover, opacity, and visibility changes do not alter proxy
  // bounds. Invalidating the spatial index for those high-frequency updates
  // forced the next click to Box3-scan the entire board. Only exploded-layer
  // motion changes existing proxy bounds; board/model rebuilds increment the
  // revision at their construction sites.
  useEffect(() => {
    pickablesRevisionRef.current += 1;
  }, [layerSeparation]);

  useEffect(() => {
    const group = resultGroupRef.current;
    if (!group || !activeBoard) return;
    resultSurfacePickablesRef.current = [];
    pickablesRef.current = pickablesRef.current.filter(object => !object.userData.analysisTerminal);
    clearGroup(group);
    const { centerX, centerY, scale } = boardTransformRef.current;
    const copperLayers = activeBoard.layers;
    const stackMidpoint = Math.max((copperLayers.length - 1) / 2, 0.5);
    const worldSpacing = layerSeparation * scale;
    const boardThickness = boardThicknessMm(activeBoard) * scale;
    const explodedOffset = (layer?: string) => {
      if (!layer || layer === "through") return 0;
      const copperIndex = copperLayers.indexOf(layer);
      if (copperIndex >= 0) return (stackMidpoint - copperIndex) * worldSpacing;
      return 0;
    };
    const displayLayerZ = (layer?: string) => copperZ(layer ?? "F.Cu", copperLayers, boardThickness, activeBoard.stackup) + explodedOffset(layer);
    const selectedResultLayers = resultVisualization?.visibleResultLayers ?? [];
    const displayedDatumLayers = (layer?: string) => selectedDatumLayers(layer, selectedResultLayers, copperLayers)
      .filter(candidate => visibleLayers[candidate] !== false);
    const position = (sample: { x_mm: number; y_mm: number; z_mm?: number; layer?: string }) => {
      const displayLayers = displayedDatumLayers(sample.layer);
      const displayLayer = displayLayers[Math.floor((displayLayers.length - 1) / 2)];
      const layerZ = displayLayer ? displayLayerZ(displayLayer) + 0.32 : undefined;
      return new THREE.Vector3(
        (sample.x_mm - centerX) * scale,
        (centerY - sample.y_mm) * scale,
        layerZ ?? (sample.z_mm === undefined ? displayLayerZ(sample.layer) + 0.32 : sample.z_mm * scale),
      );
    };
    terminalMarkers.forEach((terminal, index) => {
      const layers = (terminal.layer && terminal.layer !== "auto" ? [terminal.layer] : terminal.layers)
        .filter(layer => copperLayers.includes(layer));
      const visibleMarkerLayers = (layers.length ? layers : ["F.Cu"]).filter(layer => visibleLayers[layer] !== false);
      if (!visibleMarkerLayers.length || isolatedNet && terminal.net !== isolatedNet) return;
      const color = terminal.role === "source" ? 0x63d69a
        : terminal.role === "load" ? 0xffb84b
          : terminal.role === "source_return" ? 0x62a9ee : 0xb28cff;
      const markerGroup = new THREE.Group();
      const points = visibleMarkerLayers.map(layer => position({ x_mm: terminal.position[0], y_mm: terminal.position[1], layer }));
      points.forEach(point => {
        const marker = new THREE.Mesh(
          new THREE.TorusGeometry(1.45, 0.34, 8, 20),
          new THREE.MeshBasicMaterial({ color, depthTest: false, transparent: true, opacity: 0.96 }),
        );
        marker.position.copy(point);
        marker.renderOrder = 130;
        markerGroup.add(marker);
      });
      if (points.length > 1) {
        const geometry = new THREE.BufferGeometry().setFromPoints([points[0], points[points.length - 1]]);
        const span = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color, depthTest: false, transparent: true, opacity: 0.72 }));
        span.renderOrder = 129;
        markerGroup.add(span);
      }
      const object: BoardObject = {
        id: `analysis-terminal:${terminal.id}`,
        type: "terminal",
        name: terminal.name,
        net: terminal.net,
        layer: terminal.layer === "auto" ? "through" : terminal.layer,
        layers: visibleMarkerLayers,
        position: terminal.position,
      };
      markerGroup.userData = {
        ...object,
        analysisTerminal: true,
        pickPriority: 30,
        hoverText: `${terminal.name} | ${terminal.net} | ${terminal.value} ${terminal.role.includes("source") ? "V" : "A"} | ${visibleMarkerLayers.join(" / ")} | ${terminal.position[0].toFixed(4)}, ${terminal.position[1].toFixed(4)} mm`,
      };
      markerGroup.children.forEach(child => { child.userData = markerGroup.userData; });
      group.add(markerGroup);
      pickablesRef.current.push(...markerGroup.children);
      markerGroup.name = `analysis-terminal-${index + 1}`;
    });
    pickablesRevisionRef.current += 1;
    if (showProbes) probes.filter(probe => probe.position).forEach(probe => {
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(1.05, 14, 10),
        new THREE.MeshBasicMaterial({ color: 0xffbf47, depthTest: false, depthWrite: false }),
      );
      marker.position.copy(position({ x_mm: probe.position![0], y_mm: probe.position![1], layer: probe.layer }));
      marker.renderOrder = 320;
      marker.userData = { probe: true, id: probe.id, name: probe.name, pickPriority: 40 };
      group.add(marker);
    });
    if (!analysisResult || !resultVisualization) return;
    const mode = resultVisualization.mode;
    if (showProbes) analysisResult.probes
      .filter(probe => probe.status === "mapped" && probe.position_mm && !probes.some(placed => placed.id === probe.id || placed.id.endsWith(probe.id)))
      .forEach(probe => {
        const marker = new THREE.Mesh(
          new THREE.SphereGeometry(1.05, 14, 10),
          new THREE.MeshBasicMaterial({ color: 0xffbf47, depthTest: false, depthWrite: false }),
        );
        marker.position.copy(position({ x_mm: probe.position_mm![0], y_mm: probe.position_mm![1], layer: probe.layer }));
        marker.renderOrder = 320;
        marker.userData = { probe: true, id: probe.id, name: probe.name, voltage_v: probe.voltage_v, voltage_drop_v: probe.voltage_drop_v, pickPriority: 40 };
        group.add(marker);
      });
    if (mode === "geometry") return;
    const rawScalarSamples = viewportScalarSamples(analysisResult, mode);
    const alignmentToleranceMm = Math.max(activeBoard.width, activeBoard.height) * 0.015 + 0.25;
    const sampleInBounds = (sample: { x_mm: number; y_mm: number }) =>
      sample.x_mm >= activeBoard.bounds.minX - alignmentToleranceMm
      && sample.x_mm <= activeBoard.bounds.maxX + alignmentToleranceMm
      && sample.y_mm >= activeBoard.bounds.minY - alignmentToleranceMm
      && sample.y_mm <= activeBoard.bounds.maxY + alignmentToleranceMm;
    const netIsVisible = (net?: string) => !net
      || (!isolatedNet || net === isolatedNet)
      && (!resultVisualization.analysisOnly || !analysisNetSet.size || analysisNetSet.has(net));
    const layerIsVisible = (layer?: string) => resultLayerIsVisible(
      layer,
      selectedResultLayers,
      copperLayers,
      visibleLayers,
    );
    const bridgeIsVisible = (bridge: SolverResultBundle["component_bridges"][number]) => {
      const bridgeNets = [bridge.from_net, bridge.to_net].filter((net): net is string => Boolean(net));
      const bridgeLayers = [bridge.from_layer, bridge.to_layer].filter((layer): layer is string => Boolean(layer));
      const netMatches = !isolatedNet || bridgeNets.includes(isolatedNet);
      const analysisMatches = !resultVisualization.analysisOnly || !analysisNetSet.size
        || bridgeNets.some(net => analysisNetSet.has(net));
      return netMatches && analysisMatches && (!bridgeLayers.length || bridgeLayers.some(layer => layerIsVisible(layer)));
    };
    const bridgePosition = (vertex: [number, number, number], layer?: string) => new THREE.Vector3(
      (vertex[0] - centerX) * scale,
      (centerY - vertex[1]) * scale,
      // Endpoint Z is solver-authored board-local millimetres. Keep it exact,
      // adding only the active exploded-layer displacement used by all layers.
      vertex[2] * scale + explodedOffset(layer) + 0.14,
    );
    const visibleBridges = analysisResult.component_bridges.filter(bridgeIsVisible);
    if (visibleBridges.length) {
      const bridgeSegments: number[] = [];
      visibleBridges.forEach(bridge => {
        const [start, end] = bridge.vertices_mm;
        const startPoint = bridgePosition(start, bridge.from_layer);
        const endPoint = bridgePosition(end, bridge.to_layer);
        bridgeSegments.push(startPoint.x, startPoint.y, startPoint.z, endPoint.x, endPoint.y, endPoint.z);
      });
      const bridgeGeometry = new THREE.BufferGeometry();
      bridgeGeometry.setAttribute("position", new THREE.Float32BufferAttribute(bridgeSegments, 3));
      const bridgeOverlay = new THREE.LineSegments(
        bridgeGeometry,
        new THREE.LineDashedMaterial({
          color: 0xffc14d,
          dashSize: Math.max(scale * 0.9, 0.35),
          gapSize: Math.max(scale * 0.45, 0.18),
          transparent: true,
          opacity: 0.98,
          depthTest: false,
          depthWrite: false,
        }),
      );
      bridgeOverlay.computeLineDistances();
      bridgeOverlay.name = "electrical-equivalent-component-bridges";
      bridgeOverlay.renderOrder = 128;
      bridgeOverlay.userData = {
        resultPrimitive: "electrical_equivalent_line",
        physicalGeometry: false,
        currentDensitySupported: false,
        bridgeCount: visibleBridges.length,
        bridges: visibleBridges.map(bridge => ({
          id: bridge.id,
          component_ref: bridge.component_ref,
          resistance_ohm: bridge.resistance_ohm,
          current_a: bridge.current_a,
          voltage_drop_v: bridge.voltage_drop_v,
          power_loss_w: bridge.power_loss_w,
        })),
      };
      group.add(bridgeOverlay);
    }
    const scalarSamples: ScalarSample[] = [];
    let outsideBoard = 0;
    let outsideConductor = 0;
    rawScalarSamples.forEach(sample => {
      if (!sampleInBounds(sample)) {
        outsideBoard += 1;
        return;
      }
      if (!resultDatumFitsConductor(activeBoard, sample)) {
        outsideConductor += 1;
        return;
      }
      if (netIsVisible(sample.net) && layerIsVisible(sample.layer)) scalarSamples.push(sample);
    });
    if (hostRef.current) hostRef.current.dataset.resultAlignment = [
      "transform=edge-cuts-v1",
      `scale=${scale.toPrecision(8)}`,
      `center=${centerX.toPrecision(8)},${centerY.toPrecision(8)}`,
      `samples=${scalarSamples.length}`,
      `outside=${outsideBoard}`,
      `off-conductor=${outsideConductor}`,
    ].join(";");
    if (scalarSamples.length) {
      const values = scalarSamples.map(sample => sample.value);
      const savedRanges = analysisResult.summary.visualization_ranges as Record<string, { minimum?: number; maximum?: number }> | undefined;
      const fieldKey = viewportResultField(mode).key;
      const extent = numericExtent(values);
      const minimum = Number.isFinite(savedRanges?.[fieldKey]?.minimum) ? Number(savedRanges?.[fieldKey]?.minimum) : extent.minimum;
      const maximum = Number.isFinite(savedRanges?.[fieldKey]?.maximum) ? Number(savedRanges?.[fieldKey]?.maximum) : extent.maximum;
      const triangleIndices = new Map<ScalarSample, number[]>();
      const trianglesFor = (sample: ScalarSample) => {
        const cached = triangleIndices.get(sample);
        if (cached) return cached;
        const triangles = resultFaceTriangleIndices(sample.vertices_mm!);
        triangleIndices.set(sample, triangles);
        return triangles;
      };
      const triangulatableSamples = scalarSamples.filter(sample => (sample.vertices_mm?.length ?? 0) >= 3
        && trianglesFor(sample).length > 0);
      const thinnedExactSamples = spatiallyThinSamples(
        triangulatableSamples,
        renderProfileRef.current.largeScene ? 40000 : 80000,
      );
      // Sample count alone is not a safe rendering budget: one solver datum
      // may carry a many-sided face. Bound the actual triangle work so dense
      // post-processing cannot monopolize the UI thread or upload an
      // unbounded vertex buffer. This is display LOD only; the result bundle
      // and reports retain the complete solver data.
      const exactBudget = takeWithinCostBudget(
        thinnedExactSamples,
        renderProfileRef.current.largeScene ? 60_000 : 120_000,
        sample => Math.max(1, trianglesFor(sample).length / 3),
      );
      const exactSamples = exactBudget.items;
      const renderedExactSet = new Set(exactSamples);
      if (hostRef.current) hostRef.current.dataset.resultSurfaceBudget = [
        `source=${triangulatableSamples.length}`,
        `thinned=${thinnedExactSamples.length}`,
        `rendered=${exactSamples.length}`,
        `triangles=${exactBudget.cost}`,
        `omitted=${exactBudget.omitted}`,
      ].join(";");
      const fallbackSamples = spatiallyThinSamples(
        // Preserve admitted samples with unusable face topology as truthful
        // centre markers instead of dropping them from both render paths.
        scalarSamples.filter(sample => !renderedExactSet.has(sample)),
        6000,
      );
      const estimatedCellMm = Math.sqrt(Math.max(activeBoard.width * activeBoard.height / Math.max(scalarSamples.length, 1), 0.0025));
      const cellSize = THREE.MathUtils.clamp(estimatedCellMm * scale * 1.08, 0.18, 3.2);
      const cellDepth = viewMode === "2D" ? 0.04 : THREE.MathUtils.clamp(cellSize * 0.16, 0.06, 0.42);
      const heightPlot = viewMode === "3D" && resultVisualization.plotStyle === "height";
      const contourPlot = viewMode === "3D" && resultVisualization.plotStyle === "contour";
      if (exactSamples.length) {
        const positions: number[] = [];
        const colors: number[] = [];
        const triangleSamples: number[] = [];
        const surfaceValues: number[] = [];
        const smoothValues = resultVisualization.fieldStyle === "smooth" || contourPlot
          ? sharedVertexValues(triangulatableSamples) : null;
        const amplitude = THREE.MathUtils.clamp(
          Math.max(activeBoard.width, activeBoard.height) * scale * 0.11 * resultVisualization.waveHeightScale,
          1.2,
          42,
        );
        exactSamples.forEach((sample, sampleIndex) => {
          const vertices = sample.vertices_mm!;
          const triangles = trianglesFor(sample);
          if (!triangles.length) return;
          const ratio = maximum > minimum ? THREE.MathUtils.clamp((sample.value - minimum) / (maximum - minimum), 0, 1) : 0.5;
          let minimumZ = Number.POSITIVE_INFINITY;
          let maximumZ = Number.NEGATIVE_INFINITY;
          for (const vertex of vertices) {
            minimumZ = Math.min(minimumZ, vertex[2]);
            maximumZ = Math.max(maximumZ, vertex[2]);
          }
          const span = resultDatumLayers(sample.layer, copperLayers);
          const selectedSpan = displayedDatumLayers(sample.layer);
          const baseZ = displayLayerZ(sample.layer);
          const selectedFirstZ = selectedSpan.length ? displayLayerZ(selectedSpan[0]) : baseZ;
          const selectedLastZ = selectedSpan.length ? displayLayerZ(selectedSpan[selectedSpan.length - 1]) : baseZ;
          const spanFirstZ = span.length ? displayLayerZ(span[0]) : baseZ;
          const spanLastZ = span.length ? displayLayerZ(span[span.length - 1]) : baseZ;
          const centerZ = (minimumZ + maximumZ) / 2;
          for (let index = 0; index < triangles.length; index += 3) {
            triangleSamples.push(sampleIndex);
            for (let corner = 0; corner < 3; corner += 1) {
              const vertexIndex = triangles[index + corner];
              const vertex = vertices[vertexIndex];
              const value = smoothValues?.get(sample)?.[vertexIndex] ?? sample.value;
              const vertexRatio = maximum > minimum ? THREE.MathUtils.clamp((value - minimum) / (maximum - minimum), 0, 1) : ratio;
              const color = new THREE.Color().setHSL((1 - vertexRatio) * 0.62, 0.92, 0.54);
              const outward = sample.layer === copperLayers[copperLayers.length - 1] && copperLayers.length > 1 ? -1 : 1;
              const plotHeight = outward * ((heightPlot || contourPlot ? vertexRatio * amplitude : 0) + 0.015);
              const zRatio = maximumZ > minimumZ ? (vertex[2] - minimumZ) / (maximumZ - minimumZ) : 0;
              const z = selectedResultLayers.length && selectedSpan.length
                ? selectedSpan.length === 1 ? selectedFirstZ : selectedFirstZ + (selectedLastZ - selectedFirstZ) * zRatio
                : span.length > 1 ? spanFirstZ + (spanLastZ - spanFirstZ) * zRatio
                  : baseZ + (vertex[2] - centerZ) * scale;
              positions.push(
                (vertex[0] - centerX) * scale,
                (centerY - vertex[1]) * scale,
                z + plotHeight,
              );
              colors.push(color.r, color.g, color.b);
              surfaceValues.push(value);
            }
          }
        });
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
        const surface = new THREE.Mesh(
          geometry,
          new THREE.MeshBasicMaterial({
            vertexColors: true,
            side: THREE.DoubleSide,
            transparent: false,
            opacity: 1,
            depthTest: true,
            depthWrite: true,
            polygonOffset: true,
            polygonOffsetFactor: -1,
          }),
        );
        surface.renderOrder = 115;
        const field = viewportResultField(mode);
        surface.userData = { contourSamples: exactSamples, triangleSamples,
          contourLabel: field.label, contourUnit: field.unit };
        group.add(surface);
        resultSurfacePickablesRef.current.push(surface);
        if (contourPlot && maximum > minimum) {
          const lines: number[] = [];
          for (let triangle = 0; triangle < surfaceValues.length; triangle += 3) {
            for (let band = 1; band <= 10; band++) {
              const level = minimum + (maximum - minimum) * band / 11;
              const crossings: number[][] = [];
              for (const [left, right] of [[0, 1], [1, 2], [2, 0]]) {
                const a = surfaceValues[triangle + left]; const b = surfaceValues[triangle + right];
                if ((a <= level && b > level) || (b <= level && a > level)) {
                  const ratio = (level - a) / (b - a);
                  crossings.push([0, 1, 2].map(axis => positions[(triangle + left) * 3 + axis]
                    + ratio * (positions[(triangle + right) * 3 + axis] - positions[(triangle + left) * 3 + axis])));
                }
              }
              const outward = exactSamples[triangleSamples[triangle / 3]]?.layer === "B.Cu" ? -1 : 1;
              if (crossings.length === 2) for (const point of crossings) lines.push(point[0], point[1], point[2] + outward * 0.004);
            }
          }
          if (lines.length) {
            const lineGeometry = new THREE.BufferGeometry();
            lineGeometry.setAttribute("position", new THREE.Float32BufferAttribute(lines, 3));
            const isolines = new THREE.LineSegments(lineGeometry,
              new THREE.LineBasicMaterial({ color: 0x133642, transparent: true, opacity: 0.7, depthTest: true, depthWrite: false }));
            isolines.renderOrder = 116;
            group.add(isolines);
          }
        }
      }
      const surfacedSamples = new Set<ScalarSample>();
      if ((contourPlot || resultVisualization.fieldStyle === "smooth") && fallbackSamples.length) {
        const fieldMetadata = viewportResultField(mode);
        const grouped = new Map<string, ScalarSample[]>();
        fallbackSamples.forEach(sample => {
          const key = `${sample.layer ?? "F.Cu"}\u0000${sample.net ?? ""}`;
          const samples = grouped.get(key) ?? [];
          samples.push(sample);
          grouped.set(key, samples);
        });
        const groups = [...grouped.entries()].sort((left, right) => right[1].length - left[1].length).slice(0, 24);
        const perGroupLimit = Math.max(360, Math.floor(15000 / Math.max(groups.length, 1)));
        const amplitude = THREE.MathUtils.clamp(
          Math.max(activeBoard.width, activeBoard.height) * scale * 0.11 * resultVisualization.waveHeightScale,
          1.2,
          42,
        );
        groups.forEach(([key, samples]) => {
          const contour = buildContourGrid(samples, { levels: 11, maximumGridVertices: perGroupLimit });
          if (!contour) return;
          const [rawLayer, rawNet] = key.split("\u0000");
          const surfaceLayer = rawLayer.split("->").find(layer => visibleLayers[layer] !== false) ?? rawLayer.split("->")[0] ?? "F.Cu";
          const outward = surfaceLayer === copperLayers[copperLayers.length - 1] && copperLayers.length > 1 ? -1 : 1;
          const baseZ = displayLayerZ(surfaceLayer) + outward * 0.015;
          const positions = new Float32Array(contour.vertices.length * 3);
          const colors = new Float32Array(contour.vertices.length * 3);
          contour.vertices.forEach((vertex, index) => {
            if (!vertex) return;
            const ratio = maximum > minimum ? THREE.MathUtils.clamp((vertex.value - minimum) / (maximum - minimum), 0, 1) : 0.5;
            positions[index * 3] = (vertex.xMm - centerX) * scale;
            positions[index * 3 + 1] = (centerY - vertex.yMm) * scale;
            positions[index * 3 + 2] = baseZ + (contourPlot ? outward * ratio * amplitude : 0);
            const color = new THREE.Color().setHSL((1 - ratio) * 0.62, 0.92, 0.54);
            colors[index * 3] = color.r;
            colors[index * 3 + 1] = color.g;
            colors[index * 3 + 2] = color.b;
          });
          const surfaceGeometry = new THREE.BufferGeometry();
          surfaceGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
          surfaceGeometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
          const supportedIndices: number[] = [];
          for (let index = 0; index < contour.indices.length; index += 3) {
            const triangle = contour.indices.slice(index, index + 3);
            const vertices = triangle.map(vertexIndex => contour.vertices[vertexIndex])
              .filter((vertex): vertex is NonNullable<typeof vertex> => vertex != null);
            if (vertices.length === 3 && resultDatumFitsConductor(activeBoard, {
              x_mm: vertices.reduce((sum, vertex) => sum + vertex.xMm, 0) / 3,
              y_mm: vertices.reduce((sum, vertex) => sum + vertex.yMm, 0) / 3,
              net: rawNet || undefined,
              layer: rawLayer,
              vertices_mm: vertices.map(vertex => [vertex.xMm, vertex.yMm, 0]),
            })) supportedIndices.push(...triangle);
          }
          if (!supportedIndices.length) return;
          samples.forEach(sample => surfacedSamples.add(sample));
          surfaceGeometry.setIndex(supportedIndices);
          surfaceGeometry.computeVertexNormals();
          const surface = new THREE.Mesh(
            surfaceGeometry,
            new THREE.MeshBasicMaterial({
              vertexColors: true,
              side: THREE.DoubleSide,
              transparent: false,
              opacity: 1,
              depthWrite: true,
              polygonOffset: true,
              polygonOffsetFactor: -1,
            }),
          );
          surface.renderOrder = 116;
          surface.userData = {
            contourSamples: contour.sourceSamples,
            contourLabel: fieldMetadata.label,
            contourUnit: fieldMetadata.unit,
          };
          group.add(surface);
          resultSurfacePickablesRef.current.push(surface);
          const supportedContours = contour.contours.filter(segment =>
            pointOnResultConductor(activeBoard, segment.start, rawNet || undefined, rawLayer)
            && pointOnResultConductor(activeBoard, segment.end, rawNet || undefined, rawLayer)
            && pointOnResultConductor(activeBoard, [
              (segment.start[0] + segment.end[0]) / 2,
              (segment.start[1] + segment.end[1]) / 2,
            ], rawNet || undefined, rawLayer));
          if (contourPlot && supportedContours.length) {
            const linePositions = new Float32Array(supportedContours.length * 6);
            supportedContours.forEach((segment, index) => {
              const ratio = maximum > minimum ? THREE.MathUtils.clamp((segment.level - minimum) / (maximum - minimum), 0, 1) : 0.5;
              const z = baseZ + (contourPlot ? outward * ratio * amplitude : 0) + 0.035;
              linePositions.set([
                (segment.start[0] - centerX) * scale,
                (centerY - segment.start[1]) * scale,
                z,
                (segment.end[0] - centerX) * scale,
                (centerY - segment.end[1]) * scale,
                z,
              ], index * 6);
            });
            const lineGeometry = new THREE.BufferGeometry();
            lineGeometry.setAttribute("position", new THREE.BufferAttribute(linePositions, 3));
            const lines = new THREE.LineSegments(
              lineGeometry,
              new THREE.LineBasicMaterial({ color: 0x132930, transparent: true, opacity: 0.76, depthWrite: false }),
            );
            lines.renderOrder = 117;
            group.add(lines);
          }
        });
      }
      const markerSamples = fallbackSamples.filter(sample => !surfacedSamples.has(sample));
      if (markerSamples.length) {
        const smoothField = resultVisualization.fieldStyle === "smooth" && !heightPlot;
        const geometry = smoothField
          ? new THREE.CircleGeometry(cellSize * 1.18, 20)
          : new THREE.BoxGeometry(cellSize, cellSize, 1);
        const markers = new THREE.InstancedMesh(
          geometry,
          new THREE.MeshBasicMaterial({
            transparent: false,
            opacity: 1,
            depthTest: true,
            depthWrite: true,
            blending: THREE.NormalBlending,
          }),
          markerSamples.length,
        );
        const matrix = new THREE.Matrix4();
        const orientation = new THREE.Quaternion();
        const objectScale = new THREE.Vector3(1, 1, 1);
        markerSamples.forEach((sample, index) => {
          const ratio = maximum > minimum ? (sample.value - minimum) / (maximum - minimum) : 0.5;
          const samplePosition = position(sample);
          const height = heightPlot
            ? cellDepth + ratio * cellSize * 6 * resultVisualization.waveHeightScale
            : cellDepth;
          samplePosition.z += smoothField ? 0.08 : height * 0.5 + 0.04;
          objectScale.set(1, 1, smoothField ? 1 : height);
          matrix.compose(samplePosition, orientation, objectScale);
          markers.setMatrixAt(index, matrix);
          markers.setColorAt(index, new THREE.Color().setHSL((1 - ratio) * 0.62, 0.92, 0.54));
        });
        markers.instanceMatrix.needsUpdate = true;
        if (markers.instanceColor) markers.instanceColor.needsUpdate = true;
        markers.renderOrder = 115;
        const field = viewportResultField(mode);
        markers.userData = { contourSamples: markerSamples,
          contourLabel: field.label, contourUnit: field.unit };
        group.add(markers);
        resultSurfacePickablesRef.current.push(markers);
      }
    }
    if (mode === "mesh") {
      const segments: number[] = [];
      const selectedMeshNet = isolatedNet
        ?? (selectedNet && analysisResult.mesh.some(cell => cell.net === selectedNet) ? selectedNet : null);
      analysisResult.mesh.filter(cell => {
        const face = meshCellFaceVertices(cell) as [number, number, number][];
        const center = face.reduce((sum, vertex) => [sum[0] + vertex[0], sum[1] + vertex[1]] as Point, [0, 0] as Point);
        const count = Math.max(face.length, 1);
        return cell.vertices_mm.length >= 3
          && cell.vertices_mm.every(vertex => vertex.length === 3 && vertex.every(Number.isFinite))
          && cell.vertices_mm.every(vertex => sampleInBounds({ x_mm: vertex[0], y_mm: vertex[1] }))
          && Boolean(cell.net)
          && (!selectedMeshNet || cell.net === selectedMeshNet)
          && netIsVisible(cell.net)
          && layerIsVisible(cell.layer)
          && resultDatumFitsConductor(activeBoard, { x_mm: center[0] / count, y_mm: center[1] / count, net: cell.net, layer: cell.layer, vertices_mm: face });
      }).forEach(cell => {
        const rawZ = cell.vertices_mm.map(vertex => vertex[2]);
        const zExtent = numericExtent(rawZ);
        const minimumZ = zExtent.minimum;
        const maximumZ = zExtent.maximum;
        const layerSpan = cell.layer?.split("->") ?? [];
        const vertices = cell.vertices_mm.map(vertex => {
          let z = displayLayerZ(cell.layer);
          if (layerSpan.length === 2) {
            const ratio = maximumZ > minimumZ ? (vertex[2] - minimumZ) / (maximumZ - minimumZ) : 0;
            z = displayLayerZ(layerSpan[0]) + (displayLayerZ(layerSpan[1]) - displayLayerZ(layerSpan[0])) * ratio;
          } else {
            const centerZ = (minimumZ + maximumZ) / 2;
            z += (vertex[2] - centerZ) * scale;
          }
          return new THREE.Vector3((vertex[0] - centerX) * scale, (centerY - vertex[1]) * scale, z + 0.08);
        });
        const edgeIndexes = meshCellEdgeIndexes(cell);
        if (!edgeIndexes.length) return;
        segments.push(...edgeIndexes.flatMap(([start, end]) => [
          vertices[start].x, vertices[start].y, vertices[start].z,
          vertices[end].x, vertices[end].y, vertices[end].z,
        ]));
      });
      if (segments.length) {
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.Float32BufferAttribute(segments, 3));
        const overlay = new THREE.LineSegments(
          geometry,
          new THREE.LineBasicMaterial({ color: 0x55d8d0, transparent: true, opacity: 0.76, depthWrite: false }),
        );
        overlay.renderOrder = 90;
        group.add(overlay);
      }
    }
    const field = mode === "electric_field"
      ? analysisResult.vector_fields.electric_field
      : mode === "magnetic_field" ? analysisResult.vector_fields.magnetic_field
        : mode === "current" || mode === "current_density" ? analysisResult.vector_fields.current_density : [];
    const visibleVectors = field.filter(sample => sampleInBounds(sample)
      && pointOnResultConductor(activeBoard, [sample.x_mm, sample.y_mm], sample.net, sample.layer)
      && netIsVisible(sample.net) && layerIsVisible(sample.layer));
    if (resultVisualization.showVectors && visibleVectors.length) {
      const maximum = Math.max(numericMaximum(visibleVectors.map(sample => sample.magnitude), 0), Number.EPSILON);
      const vectorLimit = renderProfileRef.current.largeScene ? 96 : 180;
      const renderedVectors = spatiallyThinSamples(visibleVectors.filter(sample => sample.magnitude >= maximum * 0.01), vectorLimit);
      const boardVectorScale = THREE.MathUtils.clamp(Math.max(activeBoard.width, activeBoard.height) * scale * 0.032, 0.8, 5.5);
      renderedVectors.forEach(sample => {
        const direction = new THREE.Vector3(sample.vector[0], -sample.vector[1], sample.vector[2]);
        if (!direction.lengthSq()) return;
        const normalizedMagnitude = THREE.MathUtils.clamp(sample.magnitude / maximum, 0, 1);
        const length = boardVectorScale * (0.35 + 0.65 * Math.sqrt(normalizedMagnitude)) * resultVisualization.vectorScale;
        group.add(new THREE.ArrowHelper(
          direction.normalize(),
          position(sample),
          length,
          mode === "electric_field" ? 0x42d9ff : 0xff68bd,
          Math.max(length * 0.2, 0.25),
          Math.max(length * 0.1, 0.12),
        ));
      });
    }
    // Result contours and transient peaks may rise well above the board. They
    // participate in depth clipping, but never in the board-centric fit box.
    refreshVisibleBoundsRef.current();
  }, [activeBoard, analysisResult, resultOverlayKey, probes, showProbes, terminalMarkers, visibleLayers, layerSeparation, isolatedNet, analysisNets, viewMode]);

  useEffect(() => {
    if (!cameraCommand) return;
    const mode = viewModeRef.current;
    const camera = mode === "2D" ? orthographicRef.current : perspectiveRef.current;
    const controls = mode === "2D" ? controls2dRef.current : controls3dRef.current;
    if (!camera || !controls) return;
    if (cameraCommand.startsWith("fit")) {
      fitRef.current(mode);
    } else if (cameraCommand.startsWith("focus-selection")) {
      const selectedObject = selectedId ? objectMapRef.current.get(selectedId) : undefined;
      const objectBounds = selectedObject ? new THREE.Box3().setFromObject(selectedObject) : null;
      const boundsAreFinite = objectBounds && [
        objectBounds.min.x, objectBounds.min.y, objectBounds.min.z,
        objectBounds.max.x, objectBounds.max.y, objectBounds.max.z,
      ].every(Number.isFinite) && !objectBounds.isEmpty();
      const transform = boardTransformRef.current;
      const fallback = selectedPosition && selectedPosition.every(Number.isFinite)
        ? new THREE.Vector3(
          (selectedPosition[0] - transform.centerX) * transform.scale,
          (transform.centerY - selectedPosition[1]) * transform.scale,
          focusBoundsRef.current.center.z,
        )
        : null;
      const objectPosition = selectedObject?.getWorldPosition(new THREE.Vector3());
      const target = boundsAreFinite
        ? objectBounds!.getCenter(new THREE.Vector3())
        : fallback ?? (objectPosition?.toArray().every(Number.isFinite) ? objectPosition : null);
      if (!target || !target.toArray().every(Number.isFinite)) return;
      const size = boundsAreFinite ? objectBounds!.getSize(new THREE.Vector3()) : new THREE.Vector3();
      const boardSpan = Math.max(boardSizeRef.current.width, boardSizeRef.current.height, 1);
      const selectionSpan = Math.max(size.x, size.y, size.z, boardSpan * 0.06);
      const direction = camera.position.clone().sub(controls.target);
      if (!direction.toArray().every(Number.isFinite) || direction.lengthSq() < Number.EPSILON) direction.set(0.72, -0.86, 0.72);
      direction.normalize();
      if (camera instanceof THREE.OrthographicCamera) {
        const aspect = Math.abs((camera.right - camera.left) / Math.max(camera.top - camera.bottom, Number.EPSILON));
        const desiredWidth = Math.max(selectionSpan * 2.8, boardSpan * 0.06);
        camera.zoom = THREE.MathUtils.clamp((camera.right - camera.left) / Math.max(desiredWidth, selectionSpan / Math.max(aspect, 0.1)), 0.1, 30);
        camera.position.add(target.clone().sub(controls.target));
        camera.updateProjectionMatrix();
      } else {
        const verticalFov = camera.fov * Math.PI / 180;
        const distance = Math.max(selectionSpan * 1.6 / Math.sin(verticalFov / 2), boardSpan * 0.08);
        camera.position.copy(target).addScaledVector(direction, distance);
      }
      controls.target.copy(target);
      viewHelperRef.current?.center.copy(target);
    } else if (cameraCommand.startsWith("orbit-target:") && camera instanceof THREE.PerspectiveCamera) {
      const coordinateText = cameraCommand.slice("orbit-target:".length).split(":", 1)[0];
      const coordinates = coordinateText.split(",").map(Number);
      if (coordinates.length === 3 && coordinates.every(Number.isFinite)) {
        const target = new THREE.Vector3(coordinates[0], coordinates[1], coordinates[2]);
        controls.target.copy(target);
        camera.lookAt(target);
        controls.update();
        viewHelperRef.current?.center.copy(target);
        if (hostRef.current) hostRef.current.dataset.orbitCenter = coordinates.map(value => value.toFixed(3)).join(",");
        onOrbitCenterRef.current?.(coordinates as [number, number, number]);
      }
    } else if (cameraCommand.startsWith("pan-")) {
      camera.updateMatrixWorld(true);
      const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
      const up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
      const span = camera instanceof THREE.OrthographicCamera
        ? (camera.top - camera.bottom) / Math.max(camera.zoom, 0.01)
        : 2 * camera.position.distanceTo(controls.target) * Math.tan(camera.fov * Math.PI / 360);
      const step = Math.max(span * 0.08, 0.25);
      const delta = new THREE.Vector3();
      if (cameraCommand.startsWith("pan-left")) delta.addScaledVector(right, -step);
      if (cameraCommand.startsWith("pan-right")) delta.addScaledVector(right, step);
      if (cameraCommand.startsWith("pan-up")) delta.addScaledVector(up, step);
      if (cameraCommand.startsWith("pan-down")) delta.addScaledVector(up, -step);
      camera.position.add(delta);
      controls.target.add(delta);
    } else if (cameraCommand.startsWith("zoom-in")) {
      if (camera instanceof THREE.OrthographicCamera) {
        camera.zoom = Math.min(camera.zoom * 1.25, 30);
        camera.updateProjectionMatrix();
      } else {
        camera.position.lerp(controls.target, 0.2);
      }
    } else if (cameraCommand.startsWith("zoom-out")) {
      if (camera instanceof THREE.OrthographicCamera) {
        camera.zoom = Math.max(camera.zoom / 1.25, 0.1);
        camera.updateProjectionMatrix();
      } else {
        camera.position.sub(controls.target).multiplyScalar(1.25).add(controls.target);
      }
    } else if ((cameraCommand.startsWith("orbit") || cameraCommand.startsWith("view-")) && camera instanceof THREE.PerspectiveCamera) {
      const distance = Math.max(camera.position.distanceTo(controls.target), Math.max(boardSizeRef.current.width, boardSizeRef.current.height) * 1.1);
      let direction = new THREE.Vector3(0.72, -0.86, 0.72);
      // The small Y component avoids OrbitControls' polar singularity while
      // remaining visually top/bottom aligned and preserving subsequent orbit.
      if (cameraCommand.startsWith("view-top")) direction = new THREE.Vector3(0, -0.025, 1);
      if (cameraCommand.startsWith("view-bottom")) direction = new THREE.Vector3(0, 0.025, -1);
      if (cameraCommand.startsWith("view-front")) direction = new THREE.Vector3(0, -1, 0);
      if (cameraCommand.startsWith("view-back")) direction = new THREE.Vector3(0, 1, 0);
      if (cameraCommand.startsWith("view-left")) direction = new THREE.Vector3(-1, 0, 0);
      if (cameraCommand.startsWith("view-right")) direction = new THREE.Vector3(1, 0, 0);
      camera.up.set(0, 0, 1);
      camera.position.copy(controls.target).addScaledVector(direction.normalize(), distance);
    }
    camera.lookAt(controls.target);
    controls.update();
  }, [cameraCommand]);

  useEffect(() => {
    const restored = viewportRestore?.threeD;
    const camera = perspectiveRef.current;
    const controls = controls3dRef.current;
    if (!restored || !camera || !controls) return;
    camera.position.fromArray(restored.position);
    camera.up.fromArray(restored.up);
    controls.target.fromArray(restored.target);
    camera.lookAt(controls.target);
    camera.updateProjectionMatrix();
    controls.update();
    viewHelperRef.current?.center.copy(controls.target);
  }, [viewportRestore?.token, activeBoard]);

  const hoverProbeMeasurement = hoverProbeTarget ? measureHoverProbe(analysisResult, hoverProbeTarget, resultVisualization?.impedanceFrequencyHz) : null;
  const hoverProbeRows: [string, string][] = [];
  if (hoverProbeTarget?.resultSample && hoverProbeTarget.resultField) {
    hoverProbeRows.push([hoverProbeTarget.resultField.label,
      `${hoverProbeTarget.resultSample.value.toPrecision(7)} ${hoverProbeTarget.resultField.unit}`]);
  }
  if (hoverProbeMeasurement) {
    const add = (label: string, value: string | null) => { if (value) hoverProbeRows.push([label, value]); };
    if (hoverProbeKind === "universal" || hoverProbeKind === "voltage") {
      add("V", engineeringValue(hoverProbeMeasurement.voltage, "V", 1, hoverProbeMeasurement.resolution.voltage));
      add("Drop", engineeringValue(hoverProbeMeasurement.drop, "mV", 1000, hoverProbeMeasurement.resolution.drop));
    }
    if (hoverProbeKind === "universal" || hoverProbeKind === "current") {
      add("I", engineeringValue(hoverProbeMeasurement.current, "A", 1, hoverProbeMeasurement.resolution.current));
      add("J", engineeringValue(hoverProbeMeasurement.density, "A/mm2", 1, hoverProbeMeasurement.resolution.density));
    }
    if (hoverProbeKind === "universal" || hoverProbeKind === "power") add("P", engineeringValue(hoverProbeMeasurement.power, "W", 1, hoverProbeMeasurement.resolution.power));
    if (hoverProbeKind === "universal" || hoverProbeKind === "impedance") {
      add(hoverProbeMeasurement.impedanceSource === "v_over_i" ? "Z |V/I|" : "Z", engineeringValue(hoverProbeMeasurement.impedance ?? hoverProbeMeasurement.resistance, "ohm"));
      add("L", engineeringValue(hoverProbeMeasurement.inductance, "nH", 1e9));
      add("C", engineeringValue(hoverProbeMeasurement.capacitance, "pF", 1e12));
    }
  }
  const hoverProbeOverlayText = [hoverProbeTarget?.object?.net ?? "Solved coordinate", ...hoverProbeRows.map(([label, value]) => `${label} ${value}`)].join(" | ");

  useEffect(() => {
    const group = hoverProbeGroupRef.current;
    if (!group) return;
    const resultsActive = Boolean(analysisResult && resultVisualization?.visible && resultVisualization.mode !== "geometry");
    if (!resultsActive || viewMode !== "3D" || !hoverProbeEnabled || !hoverProbeTarget || !activeBoard) {
      clearGroup(group);
      return;
    }
    const { centerX, centerY, scale } = boardTransformRef.current;
    const layer = hoverProbeTarget.object?.layer;
    const boardThickness = boardThicknessMm(activeBoard) * scale;
    const layers = activeBoard.layers;
    const layerZ = layer && layer !== "through"
      ? copperZ(layer, layers, boardThickness, activeBoard.stackup)
      : boardThickness / 2;
    const point = new THREE.Vector3(
      (hoverProbeTarget.position[0] - centerX) * scale,
      (centerY - hoverProbeTarget.position[1]) * scale,
      layerZ + Math.max(0.5, Math.max(activeBoard.width, activeBoard.height) * scale * 0.005),
    );
    if (hoverProbeTarget.worldPosition) point.fromArray(hoverProbeTarget.worldPosition);
    const radius = THREE.MathUtils.clamp(Math.max(activeBoard.width, activeBoard.height) * scale * 0.012, 1.5, 6);
    let reticle = group.getObjectByName("hover-probe-reticle-3d") as THREE.Mesh | undefined;
    if (!reticle || Number(reticle.userData.radius) !== radius) {
      clearGroup(group);
      reticle = new THREE.Mesh(
        new THREE.RingGeometry(radius * 0.66, radius, 28),
        new THREE.MeshBasicMaterial({ color: 0xffc34e, transparent: true, opacity: 0.96, side: THREE.DoubleSide, depthTest: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 }),
      );
      reticle.name = "hover-probe-reticle-3d";
      reticle.userData.radius = radius;
      reticle.renderOrder = 420;
      group.add(reticle);
      const stem = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3(0, 0, 1)]),
        new THREE.LineBasicMaterial({ color: 0xffd166, transparent: true, opacity: 0.95, depthTest: true, depthWrite: false }),
      );
      stem.name = "hover-probe-stem-3d";
      stem.renderOrder = 421;
      group.add(stem);
    }
    reticle.position.copy(point);
    const stem = group.getObjectByName("hover-probe-stem-3d") as THREE.Line | undefined;
    if (stem) {
      stem.position.copy(point);
      stem.scale.set(1, 1, radius * 4.4);
    }
    let label = group.getObjectByName("hover-probe-label-3d") as THREE.Sprite | undefined;
    if (label?.userData.text !== hoverProbeOverlayText) {
      if (label) {
        group.remove(label);
        label.material.map?.dispose();
        label.material.dispose();
      }
      label = overlayLabel(hoverProbeOverlayText, "#fff0c5", Math.max(radius * 1.35, 3.2)) ?? undefined;
      if (label) {
        label.material.depthTest = true;
        label.name = "hover-probe-label-3d";
        label.userData.text = hoverProbeOverlayText;
        group.add(label);
      }
    }
    label?.position.copy(point).add(new THREE.Vector3(radius * 1.2, radius * 0.8, radius * 4.8));
    group.visible = true;
  }, [activeBoard, analysisResult, hoverProbeEnabled, hoverProbeOverlayText, hoverProbeTarget, resultVisualization, viewMode]);

  return (
    <div ref={hostRef} className={`three-host ${viewMode === "2D" && activeBoard ? "layout-active" : ""}`} data-model-metrics={modelMetrics} data-hover-preview={hoverPreview?.label ?? ""}>
      {viewMode === "2D" && activeBoard && <LayoutViewport
        board={activeBoard}
        visibleLayers={visibleLayers}
        layerOpacity={layerOpacity}
        showVias={showVias}
        showNetNames={showNetNames}
        selectedId={selectedId}
        selectedPosition={selectedPosition}
        selectedNet={selectedNet}
        hoverPreview={hoverPreview}
        isolatedNet={isolatedNet}
        analysisResult={analysisResult}
        resultVisualization={resultVisualization}
        analysisNets={analysisNets}
        probes={probes}
        showProbes={showProbes}
        hoverProbeEnabled={hoverProbeEnabled}
        onHoverProbe={setHoverProbeTarget}
        terminalMarkers={terminalMarkers}
        thermalScenario={thermalScenario}
        thermalVisibility={thermalVisibility}
        translucentScene={Boolean(resultVisualization?.translucentScene || resultVisualization?.sceneMode === "translucent")}
        showAxes={showAxes}
        cameraCommand={cameraCommand}
        viewportRestore={viewportRestore}
        onViewChange={onLayoutView}
        selectionBlink={selectionBlink}
        selectionFilter={selectionFilter}
        onSelect={onSelect}
        onContextMenu={onContextMenu}
      />}
      {hoverProbeEnabled && hoverProbeTarget && <>
        <div className="hover-probe-reticle" style={{ left: hoverProbeTarget.clientX, top: hoverProbeTarget.clientY }} />
        <div
          className="hover-probe-banner"
          style={{
            left: Math.max(8, Math.min(hoverProbeTarget.clientX + 18, window.innerWidth - 312)),
            top: Math.max(8, Math.min(hoverProbeTarget.clientY + 18,
              window.innerHeight - 128 - hoverProbeRows.length * 26)),
          }}
        >
          <div><b>HOVER {hoverProbeKind.toUpperCase()}</b><span>LIVE</span></div>
          <strong>{hoverProbeTarget.object?.net ?? hoverProbeTarget.object?.name ?? "Board coordinate"}</strong>
          <small>{hoverProbeTarget.position[0].toFixed(3)}, {hoverProbeTarget.position[1].toFixed(3)} mm · {hoverProbeTarget.object?.layer ?? "nearest solved layer"}</small>
          {hoverProbeTarget.resultSample
            ? <small className="hover-probe-source">Solver sample · {hoverProbeTarget.resultSample.element_id ?? "sample"} · smooth colors are display interpolation</small>
            : hoverProbeMeasurement?.sampleDistanceMm !== undefined && <small className="hover-probe-source">Local solver interpolation · nearest sample {hoverProbeMeasurement.sampleDistanceMm.toFixed(3)} mm</small>}
          {hoverProbeRows.length
            ? <dl>{hoverProbeRows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
            : <p>No solved value at this location</p>}
        </div>
      </>}
      <div
        className={`view-quality ${fullModelState}${missingModelCount > 0 || componentModelState === "failed" ? " warning" : ""}`}
        title={componentModelState === "failed"
          ? "The board loaded, but the component scene could not be loaded. Available footprint placeholders remain visible."
          : missingModelCount > 0
            ? `${missingModelCount} component model references could not be resolved by KiCad. Missing parts use footprint placeholders.`
            : undefined}
      >
        {viewMode === "2D"
          ? activeBoard?.layoutLayerUrls ? "KICAD VECTOR LAYOUT" : "DESIGN GEOMETRY"
          : isolatedNet
            ? `ISOLATED NET · ${isolatedNet}`
          : layerFilterActive
            ? componentModelState === "ready" && showModels ? `LAYER VIEW · KICAD MODELS${missingModelCount ? ` · ${missingModelCount} GAPS` : ""}` : "LAYER VIEW · FOOTPRINT PLACEHOLDERS"
          : fullModelState === "ready"
            ? componentModelState === "failed"
              ? "KICAD BOARD | COMPONENT SCENE FAILED"
              : missingModelCount > 0 ? `KICAD MODEL | ${missingModelCount} GAPS` : "KICAD MODEL"
            : fullModelState === "loading"
              ? "LOADING KICAD MODEL"
              : fullModelState === "failed"
                ? "MODEL FALLBACK"
                : "FOOTPRINT PLACEHOLDERS"}
      </div>
    </div>
  );
}

export default memo(BoardViewport);
