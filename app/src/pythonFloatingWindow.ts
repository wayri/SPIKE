// SPDX-License-Identifier: Apache-2.0
export type FloatingRect = { x: number; y: number; width: number; height: number };
export function boundFloatingRect(rect: FloatingRect, viewportWidth: number, viewportHeight: number): FloatingRect {
  const availableWidth = Math.max(1, viewportWidth - 16), availableHeight = Math.max(1, viewportHeight - 16);
  const width = Math.min(availableWidth, Math.max(Math.min(680, availableWidth), rect.width));
  const height = Math.min(availableHeight, Math.max(Math.min(440, availableHeight), rect.height));
  return { width, height, x: Math.max(8, Math.min(viewportWidth - width - 8, rect.x)), y: Math.max(8, Math.min(viewportHeight - height - 8, rect.y)) };
}
export function initialFloatingRect(width: number, height: number): FloatingRect {
  return boundFloatingRect({ x: 32, y: 72, width: Math.min(1080, width - 64), height: Math.min(740, height - 104) }, width, height);
}
