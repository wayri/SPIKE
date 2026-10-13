// SPDX-License-Identifier: Apache-2.0
import { MOUSE } from "three";
/** OrbitControls inverts ROTATE/PAN for modifiers. Shift must always resolve to pan. */
export function viewportMouseButtons(mode: "orbit" | "pan", view: "2D" | "3D", modifiers: { shiftKey: boolean; ctrlKey?: boolean; metaKey?: boolean }) {
  const modifiedPan = modifiers.shiftKey || (view === "2D" && Boolean(modifiers.ctrlKey || modifiers.metaKey));
  return {
    LEFT: modifiedPan ? MOUSE.ROTATE : view === "2D" || mode === "pan" ? MOUSE.PAN : MOUSE.ROTATE,
    MIDDLE: modifiedPan ? MOUSE.ROTATE : MOUSE.PAN,
    RIGHT: modifiedPan ? MOUSE.ROTATE : MOUSE.PAN,
  };
}
