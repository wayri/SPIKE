// SPDX-License-Identifier: Apache-2.0
import type * as THREE from "three";

export type MechanicalVisual = { visible: boolean; opacity: number };

export function mechanicalPartPresentation(sourceVisible: boolean, sourceOpacity: number, override: MechanicalVisual | undefined, isolated: boolean) {
  const requestedOpacity = override?.opacity ?? sourceOpacity;
  return {
    visible: (override?.visible ?? sourceVisible) && isolated,
    opacity: Number.isFinite(requestedOpacity) ? Math.max(0, Math.min(1, requestedOpacity)) : 1,
  };
}

type AssemblyMaterialState = {
  spikeAssemblyBaseOpacity?: number;
  spikeAssemblyBaseTransparent?: boolean;
  spikeAssemblyBaseDepthWrite?: boolean;
};

export function applyAssemblyMaterialOpacity(material: THREE.Material, partOpacity: number) {
  const state = material.userData as AssemblyMaterialState;
  state.spikeAssemblyBaseOpacity ??= material.opacity;
  state.spikeAssemblyBaseTransparent ??= material.transparent;
  state.spikeAssemblyBaseDepthWrite ??= material.depthWrite;
  const opacity = Number.isFinite(partOpacity) ? Math.max(0, Math.min(1, partOpacity)) : 1;
  const nextOpacity = (state.spikeAssemblyBaseOpacity ?? 1) * opacity;
  const nextTransparent = Boolean(state.spikeAssemblyBaseTransparent) || opacity < 0.999;
  const nextDepthWrite = state.spikeAssemblyBaseDepthWrite !== false && opacity >= 0.999;
  const changed = material.opacity !== nextOpacity || material.transparent !== nextTransparent || material.depthWrite !== nextDepthWrite;
  material.opacity = nextOpacity;
  material.transparent = nextTransparent;
  material.depthWrite = nextDepthWrite;
  if (changed) material.needsUpdate = true;
}

export function applyAssemblyMaterialClipping(material: THREE.Material, clippingPlanes: THREE.Plane[], clipShadows: boolean) {
  const currentPlanes = material.clippingPlanes ?? [];
  const unchanged = currentPlanes.length === clippingPlanes.length
    && currentPlanes.every((plane, index) => plane.normal.equals(clippingPlanes[index].normal) && plane.constant === clippingPlanes[index].constant)
    && material.clipShadows === clipShadows;
  if (unchanged) return;
  material.clippingPlanes = clippingPlanes;
  material.clipShadows = clipShadows;
  material.needsUpdate = true;
}
