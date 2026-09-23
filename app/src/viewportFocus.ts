export type FocusBounds2D = { minX: number; minY: number; maxX: number; maxY: number };
export type FocusViewBox = { x: number; y: number; width: number; height: number };

const finite = (value: number) => Number.isFinite(value);

/** Returns a finite ordered bound, or null rather than allowing camera NaNs. */
export function finiteFocusBounds(bounds: FocusBounds2D | null | undefined): FocusBounds2D | null {
  if (!bounds || ![bounds.minX, bounds.minY, bounds.maxX, bounds.maxY].every(finite)) return null;
  return {
    minX: Math.min(bounds.minX, bounds.maxX), minY: Math.min(bounds.minY, bounds.maxY),
    maxX: Math.max(bounds.minX, bounds.maxX), maxY: Math.max(bounds.minY, bounds.maxY),
  };
}

/** Centers an object selection and gives it a bounded, readable 2-D working zoom. */
export function focusViewBox(
  selection: FocusBounds2D | null | undefined,
  fallbackPoint: [number, number] | null | undefined,
  board: FocusBounds2D,
  aspect: number,
): FocusViewBox | null {
  const boardBounds = finiteFocusBounds(board);
  const selected = finiteFocusBounds(selection);
  const point = fallbackPoint && finite(fallbackPoint[0]) && finite(fallbackPoint[1]) ? fallbackPoint : null;
  if (!boardBounds || (!selected && !point)) return null;
  const centerX = selected ? (selected.minX + selected.maxX) / 2 : point![0];
  const centerY = selected ? (selected.minY + selected.maxY) / 2 : point![1];
  const boardWidth = Math.max(boardBounds.maxX - boardBounds.minX, Number.EPSILON);
  const boardHeight = Math.max(boardBounds.maxY - boardBounds.minY, Number.EPSILON);
  const selectedWidth = selected ? selected.maxX - selected.minX : 0;
  const selectedHeight = selected ? selected.maxY - selected.minY : 0;
  const safeAspect = finite(aspect) && aspect > 0 ? aspect : boardWidth / boardHeight;
  const desiredWidth = Math.min(
    Math.max(boardWidth * 0.06, selectedWidth * 2.8, selectedHeight * safeAspect * 2.8),
    boardWidth * 4,
  );
  const width = Math.max(desiredWidth, Number.EPSILON);
  const height = width / safeAspect;
  return { x: centerX - width / 2, y: centerY - height / 2, width, height };
}
