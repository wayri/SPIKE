/**
 * Resolve KiCad copper selectors to the board's physical copper stack.
 *
 * These selectors are not copper layers in their own right. `*.Cu` spans the
 * full stack, while `F&B.Cu` names only the outer copper layers. Keeping the
 * expansion here prevents inventory consumers from counting a selector as an
 * additional physical layer.
 */
export function resolveBoardCopperLayers(
  boardLayers: readonly string[],
  declaredLayers: readonly string[],
): string[] {
  const physicalCopper = [...new Set(boardLayers.filter(layer => layer && !layer.includes("*") && layer !== "F&B.Cu"))];
  if (declaredLayers.includes("*.Cu")) return physicalCopper;
  if (declaredLayers.includes("F&B.Cu")) return physicalCopper.filter((_, index) => index === 0 || index === physicalCopper.length - 1);
  const physicalSet = new Set(physicalCopper);
  return [...new Set(declaredLayers.filter(layer => physicalSet.has(layer)))];
}

/** Keep the 2D copper tab aligned with visibility changes in the layer manager. */
export function visibleLayoutCopperLayer(current: string, layers: readonly string[], visible: Readonly<Record<string, boolean>>): string {
  if (current === "All" || current === "Overview" || layers.includes(current) && visible[current] !== false) return current;
  return layers.find(layer => visible[layer] !== false) ?? current;
}
