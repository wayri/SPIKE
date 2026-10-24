// SPDX-License-Identifier: Apache-2.0
/** Resolve occurrence ownership, never a net name or a shared design identity. */
export function viewportLayerTarget(context: {
  assembly: boolean;
  availableBoardIds: readonly string[];
  selectedBoardIds: readonly string[];
  selectedObject: { occurrenceId?: string; assemblyPartId?: string } | null;
  activeBoardAvailable: boolean;
  harnessSelected: boolean;
}): string | null {
  if (context.harnessSelected || context.selectedObject?.assemblyPartId || context.selectedBoardIds.length > 1) return null;
  if (!context.assembly) return context.activeBoardAvailable ? "active-board" : null;
  const occurrence = context.selectedObject?.occurrenceId;
  if (occurrence) return context.availableBoardIds.includes(occurrence) ? occurrence : null;
  // An unbound object in an assembly must not inherit an unrelated old board focus.
  if (context.selectedObject) return null;
  const selected = context.selectedBoardIds[0];
  return selected && context.availableBoardIds.includes(selected) ? selected : null;
}
