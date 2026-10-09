// SPDX-License-Identifier: Apache-2.0
import type { Intersection, Plane } from "three";

/** Match Three.js clipping: negative signed plane distance is discarded.
 * Test the hit point, not an object's centre, so partially cut meshes remain pickable.
 */
export function sectionHitVisible(hit: Pick<Intersection, "point">, planes: readonly Plane[], epsilon = 1e-7): boolean {
  return planes.every(plane => plane.distanceToPoint(hit.point) >= -epsilon);
}
