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

/** Phase-preserving frame budget: early RAF timestamps must not halve FPS. */
export class ViewportFrameClock {
  private deadline = 0;
  private frequency = 0;
  due(nowMs: number, moving: boolean, maximumFps = 120): boolean {
    const fps = moving ? Math.max(1, Math.min(240, Number.isFinite(maximumFps) ? maximumFps : 120)) : 5;
    const interval = 1000 / fps;
    if(this.frequency !== fps){this.frequency=fps;this.deadline=nowMs;}
    if(nowMs + .5 < this.deadline)return false;
    this.deadline = nowMs - this.deadline > interval * 2 ? nowMs + interval : this.deadline + interval;
    return true;
  }
}
