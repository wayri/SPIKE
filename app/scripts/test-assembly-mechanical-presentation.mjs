// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { MeshStandardMaterial, Plane, Vector3 } from "three";
import { readFile } from "node:fs/promises";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { applyAssemblyMaterialClipping, applyAssemblyMaterialOpacity, mechanicalPartPresentation } = await importTestTypescript("assemblyMechanicalPresentation");

assert.deepEqual(mechanicalPartPresentation(false, .7, { visible: true, opacity: .25 }, true), { visible: true, opacity: .25 },
  "an explicit manager override can reveal a source-hidden part");
assert.deepEqual(mechanicalPartPresentation(true, .7, undefined, false), { visible: false, opacity: .7 },
  "part isolation remains a final visibility gate");
assert.deepEqual(mechanicalPartPresentation(true, .7, undefined, true), { visible: true, opacity: .7 },
  "removing an override restores source presentation");

const material = new MeshStandardMaterial({ opacity: .6, transparent: false, depthWrite: true });
applyAssemblyMaterialOpacity(material, .25);
assert.equal(material.opacity, .15, "manager opacity composes with the source material opacity");
assert.equal(material.transparent, true);
assert.equal(material.depthWrite, false);
const translucentVersion = material.version;
applyAssemblyMaterialOpacity(material, .25);
assert.equal(material.version, translucentVersion, "unchanged presentation does not invalidate the material shader");
applyAssemblyMaterialOpacity(material, 1);
assert.equal(material.opacity, .6, "clearing translucency restores the original material opacity");
assert.equal(material.transparent, false, "clearing translucency restores original transparency");
assert.equal(material.depthWrite, true, "clearing translucency restores original depth writing");
material.dispose();

const originallyTransparent = new MeshStandardMaterial({ opacity: .4, transparent: true, depthWrite: false });
applyAssemblyMaterialOpacity(originallyTransparent, .2);
applyAssemblyMaterialOpacity(originallyTransparent, 1);
assert.equal(originallyTransparent.opacity, .4);
assert.equal(originallyTransparent.transparent, true, "manager restoration preserves source transparency");
assert.equal(originallyTransparent.depthWrite, false, "manager restoration preserves source depth writing");
originallyTransparent.dispose();

const clipped = new MeshStandardMaterial();
const clippingPlanes = [new Plane(new Vector3(1, 0, 0), -4)];
applyAssemblyMaterialClipping(clipped, clippingPlanes, true);
assert.equal(clipped.clippingPlanes.length, 1, "an active arbitrary MCAD section reaches the actual material");
assert.equal(clipped.clippingPlanes[0].distanceToPoint(new Vector3(4, 2, 3)), 0, "material clipping preserves the section plane math");
assert.equal(clipped.clipShadows, true);
const clippedVersion = clipped.version;
applyAssemblyMaterialClipping(clipped, [clippingPlanes[0].clone()], true);
assert.equal(clipped.version, clippedVersion, "equivalent section planes do not invalidate unchanged materials");
clipped.dispose();

const viewportSource = await readFile(new URL("../src/BoardViewport.tsx", import.meta.url), "utf8");
assert.match(viewportSource, /\}, \[activeBoard, assemblyModels, onAssemblyPartViewportStatus\]\);/,
  "manager presentation changes must not restart the assembly model loading effect");
assert.match(viewportSource, /\}, \[assemblyModels, mechanicalVisuals, assemblySection, isolatedAssemblyPartId\]\);/,
  "manager presentation changes must update the retained assembly display effect");
assert.match(viewportSource, /\[assemblySection, assemblySelectorPreviews, mechanicalVisuals, isolatedAssemblyPartId/,
  "selector previews share manager visibility and opacity by stable part identity");

console.log("Assembly mechanical visibility, isolation, opacity, and material restoration passed");
