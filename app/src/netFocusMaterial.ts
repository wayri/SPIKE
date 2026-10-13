// SPDX-License-Identifier: Apache-2.0
import type { Color, Material } from "three";
/** Preserve original material colors; focus is display state, never geometry. */
export function applyNetFocusColor(material: Material, active: boolean) {
  const color = (material as Material & { color?: Color }).color;
  if (!color) return;
  if (active) { material.userData.netFocusOriginalColor ??= color.getHex(); color.setHex(0x667076); }
  else if (material.userData.netFocusOriginalColor !== undefined) color.setHex(material.userData.netFocusOriginalColor);
}
