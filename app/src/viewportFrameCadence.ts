// SPDX-License-Identifier: Apache-2.0

/** Camera gestures must follow display refresh, rather than a second FPS cap.
 * A 16.67 ms cap on a 16.6 ms RAF stream otherwise drops every second frame.
 * Only stationary views use the low-power cadence.
 */
export function viewportFrameDue(nowMs: number, lastRenderMs: number, moving: boolean, idleFps = 5): boolean {
  return moving || nowMs - lastRenderMs >= 1000 / Math.max(1, idleFps);
}

/** Match the nominal 60 Hz damping decay on slower/faster displays. */
export function viewportDampingFactor(nominalFactor: number, deltaSeconds: number): number {
  const elapsed = Math.max(0, Math.min(deltaSeconds, 0.1));
  return 1 - Math.pow(1 - nominalFactor, elapsed * 60);
}
