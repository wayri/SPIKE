// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";

export type BoardSurfaceKind = "copper" | "silkscreen" | "soldermask" | "substrate" | "unknown";
export function classifyBoardSurface(material: THREE.MeshStandardMaterial, name: string): BoardSurfaceKind {
  const retained = material.userData.spikeBoardSurfaceKind as BoardSurfaceKind | undefined;
  if (retained && ["copper", "silkscreen", "soldermask", "substrate"].includes(retained)) return retained;
  const semantic = `${name} ${material.userData.spikeSourceMaterialName ?? material.name}`.toLowerCase();
  if (semantic.includes("copper")) return "copper";
  if (semantic.includes("silkscreen")) return "silkscreen";
  if (semantic.includes("soldermask")) return "soldermask";
  if (semantic.includes("pcb") || semantic.includes("substrate")) return "substrate";
  const { r, g, b } = material.color;
  if (material.metalness >= .75) return "copper";
  if (r >= .75 && g >= .75 && b >= .75 && material.opacity <= .95) return "silkscreen";
  // KiCad exports colored masks without semantic material names. Their hue is
  // configurable (including blue/red), while silk is neutral and copper is
  // metallic. Preserve the exporter alpha/chroma evidence across mask colors.
  const brightest = Math.max(r, g, b), darkest = Math.min(r, g, b);
  if (material.opacity <= .93 && brightest - darkest > brightest * .25) return "soldermask";
  if (material.opacity >= .94 && material.roughness >= .7) return "substrate";
  return "unknown";
}

/** Identical material/depth policy for the main PCB and every assembly occurrence.
 * The opaque laminate occludes inner copper; the mask remains a surface coating.
 * Call only on occurrence-owned materials, never on shared cached sources.
 */
export function configureImportedMaterial(material: THREE.Material, kind: "board" | "components", name: string): BoardSurfaceKind {
  material.side = THREE.DoubleSide;
  material.depthTest = true;
  let surface: BoardSurfaceKind = "unknown";
  if (material instanceof THREE.MeshStandardMaterial) {
    if (kind === "board") {
      surface = classifyBoardSurface(material, name);
      if (surface !== "unknown") {
        material.userData.spikeBoardSurfaceKind = surface;
        material.alphaHash = false; material.alphaToCoverage = false;
        material.opacity = surface === "soldermask" ? .76 : 1;
        material.transparent = surface === "soldermask";
        material.color.setHex({ copper: 0xc48832, silkscreen: 0xe8e5da, soldermask: 0x08623c, substrate: 0x9b783f }[surface]);
        material.metalness = surface === "copper" ? .64 : 0;
        material.roughness = { copper: .34, silkscreen: .72, soldermask: .5, substrate: .82 }[surface];
        material.polygonOffset = surface === "soldermask";
        material.polygonOffsetFactor = surface === "soldermask" ? -1 : 0;
        material.polygonOffsetUnits = surface === "soldermask" ? -2 : 0;
      }
    } else {
      material.roughness = Math.max(material.roughness, .34);
      material.metalness = Math.min(material.metalness, .72);
    }
  }
  const alphaHashed = material instanceof THREE.MeshStandardMaterial && material.alphaHash;
  material.depthWrite = alphaHashed || !material.transparent && material.opacity >= .999;
  if (!alphaHashed && material.transparent && !material.polygonOffset) {
    material.polygonOffset = true; material.polygonOffsetFactor = -2; material.polygonOffsetUnits = -4;
  }
  if ("shininess" in material && typeof material.shininess === "number") material.shininess = Math.min(material.shininess, 80);
  material.needsUpdate = true;
  return surface;
}
