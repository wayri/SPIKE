// SPDX-License-Identifier: Apache-2.0
import { nextAssemblySectionPlane, type AssemblySection, type AssemblySectionPlane } from "./mcadAssembly";

export const MECHANICAL_SECTION_PRESETS = [
  { label: "XY", normal: [0, 0, 1] },
  { label: "XZ", normal: [0, 1, 0] },
  { label: "YZ", normal: [1, 0, 0] },
  { label: "45 XY", normal: [Math.SQRT1_2, Math.SQRT1_2, 0] },
  { label: "45 XZ", normal: [Math.SQRT1_2, 0, Math.SQRT1_2] },
  { label: "45 YZ", normal: [0, Math.SQRT1_2, Math.SQRT1_2] },
] as const;

/** Assembly coordinates: azimuth from +X toward +Y; elevation from XY toward +Z. */
export function sectionNormalFromAngles(azimuthDeg: number, elevationDeg: number): readonly [number, number, number] {
  if (!Number.isFinite(azimuthDeg) || !Number.isFinite(elevationDeg) || Math.abs(elevationDeg) > 90)
    throw new RangeError("Enter finite angles with elevation between -90 and 90 degrees.");
  const azimuth = (azimuthDeg % 360) * Math.PI / 180;
  const elevation = elevationDeg * Math.PI / 180;
  const clean = (n: number) => Math.abs(n) < 1e-15 ? 0 : n;
  return [clean(Math.cos(elevation) * Math.cos(azimuth)), clean(Math.cos(elevation) * Math.sin(azimuth)), clean(Math.sin(elevation))];
}

export function sectionAnglesFromNormal(normal: readonly [number, number, number]): { azimuth: number; elevation: number } {
  const length = Math.hypot(...normal);
  if (!normal.every(Number.isFinite) || !Number.isFinite(length) || length <= 1e-12) return { azimuth: 0, elevation: 0 };
  return { azimuth: Math.atan2(normal[1], normal[0]) * 180 / Math.PI, elevation: Math.asin(Math.max(-1, Math.min(1, normal[2] / length))) * 180 / Math.PI };
}

export function primaryMechanicalSectionPlane(section: AssemblySection): AssemblySectionPlane {
  if (section.mode === "planes" && section.planes.length) return section.planes[0];
  return { ...(section.planes[0] ?? nextAssemblySectionPlane(section)), enabled: true, flipped: false, normal: section.axis === "x" ? [1, 0, 0] : section.axis === "y" ? [0, 1, 0] : [0, 0, 1], offsetMm: section.offsetMm };
}

/** Editing the first cut retains all other planes and box settings for the advanced manager. */
export function updateMechanicalSectionPlane(section: AssemblySection, patch: Partial<AssemblySectionPlane>): AssemblySection {
  const plane = { ...primaryMechanicalSectionPlane(section), ...patch };
  const planes = [plane, ...section.planes.slice(1)];
  // Legacy axis sections have no plane flip field; all quick edits use the existing plane collection contract.
  return { ...section, mode: "planes", planes };
}


/** Moves the applied first plane through an assembly-space point in mm. */
export function mechanicalSectionThroughPoint(section: AssemblySection, point: readonly [number, number, number]): AssemblySection | null {
  const plane = primaryMechanicalSectionPlane(section);
  const length = Math.hypot(...plane.normal);
  if (!point.every(Number.isFinite) || !plane.normal.every(Number.isFinite) || !Number.isFinite(length) || length <= 1e-12) return null;
  const offsetMm = plane.normal.reduce((sum, value, index) => sum + value / length * point[index], 0);
  if (!Number.isFinite(offsetMm)) return null;
  return { ...updateMechanicalSectionPlane(section, { offsetMm, enabled: true }), enabled: true };
}
