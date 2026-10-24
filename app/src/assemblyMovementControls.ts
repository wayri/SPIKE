// SPDX-License-Identifier: Apache-2.0
import type { TransformControls } from "three/examples/jsm/controls/TransformControls.js";

/** One pointer owner for simultaneous translation arrows and rotation rings.
 * Uses the public TransformControls pointer API; no private picker internals.
 */
export function installAssemblyMovementControls(arrows: TransformControls, rings: TransformControls,
  canvas: HTMLElement, beforeGesture: () => void) {
  arrows.disconnect(); rings.disconnect();
  const previousTouchAction = canvas.style.touchAction;
  canvas.style.touchAction = "none";
  let owner: TransformControls | null = null;
  let pointerId: number | null = null;
  const pointer = (event: PointerEvent) => {
    const rect = canvas.getBoundingClientRect();
    return { x: (event.clientX - rect.left) / Math.max(rect.width, 1) * 2 - 1,
      y: -(event.clientY - rect.top) / Math.max(rect.height, 1) * 2 + 1, button: event.button } as PointerEvent;
  };
  const hover = (event: PointerEvent) => {
    const point = pointer(event);
    for (const control of [arrows, rings]) {
      if (control.enabled && control.object) control.pointerHover(point);
      else control.axis = null;
    }
    // An arrow wins at a crossing, keeping its smaller handle reachable.
    if (arrows.axis) rings.axis = null;
    return arrows.axis ? arrows : rings.axis ? rings : null;
  };
  const down = (event: PointerEvent) => {
    if (event.button !== 0 || owner) return;
    const chosen = hover(event);
    if (!chosen) return;
    beforeGesture();
    chosen.pointerHover(pointer(event));
    chosen.pointerDown(pointer(event));
    if (!chosen.dragging) return;
    owner = chosen; pointerId = event.pointerId;
    canvas.setPointerCapture(event.pointerId);
  };
  const move = (event: PointerEvent) => {
    if (owner) {
      if (event.pointerId === pointerId) owner.pointerMove(pointer(event));
    } else hover(event);
  };
  const release = () => {
    const captured = pointerId;
    owner = null; pointerId = null;
    if (captured !== null && canvas.hasPointerCapture(captured)) canvas.releasePointerCapture(captured);
  };
  const up = (event: PointerEvent) => {
    if (event.pointerId !== pointerId) return;
    owner?.pointerUp(pointer(event)); release();
  };
  const cancel = (event: PointerEvent) => {
    if (event.pointerId !== pointerId) return;
    beforeGesture(); release();
  };
  const capture = { capture: true };
  canvas.addEventListener("pointerdown", down, capture);
  canvas.addEventListener("pointermove", move, capture);
  canvas.addEventListener("pointerup", up, capture);
  canvas.addEventListener("pointercancel", cancel, capture);
  canvas.addEventListener("lostpointercapture", cancel, capture);
  return { dispose() {
    if (owner) beforeGesture(); release();
    canvas.removeEventListener("pointerdown", down, capture);
    canvas.removeEventListener("pointermove", move, capture);
    canvas.removeEventListener("pointerup", up, capture);
    canvas.removeEventListener("pointercancel", cancel, capture);
    canvas.removeEventListener("lostpointercapture", cancel, capture);
    canvas.style.touchAction = previousTouchAction;
  } };
}
