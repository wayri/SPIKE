// SPDX-License-Identifier: Apache-2.0
import type { ParsedBoard } from "./boardParser";
import type { VirtualBoardVisual } from "./harnessVisualization";
import { copperNetLabels } from "./viewportPerformance";
import { canonicalNetId, assemblyLayerIsRendered } from "./assemblyLayout2d";
export function assemblyNetLabels(board: ParsedBoard, visual: VirtualBoardVisual,
  visibility: Record<string, boolean>, opacity: Record<string, number>, unitsPerPixel: number, limit = 80) {
  const named = (net?: string) => net ? board.nets[net] ?? visual.netNamesById?.[net] ?? net : undefined;
  // Label planning uses a readable text footprint, not the physical copper width.
  const tracks = board.tracks.filter(row => assemblyLayerIsRendered(row.layer, visibility, opacity)).map(row => ({...row, net:named(row.net), width:Math.max(row.width,unitsPerPixel * 14)}));
  const zones = board.zones.filter(row => assemblyLayerIsRendered(row.layer, visibility, opacity)).map(row => ({...row, net:named(row.net)}));
  return copperNetLabels(tracks,zones,{...board.bounds,unitsPerPixel},limit).map(label => ({...label,
    occurrenceId:visual.id, canonicalNetId:canonicalNetId(board,visual.netIdsByName,label.net,visual.netNamesById)}));
}
