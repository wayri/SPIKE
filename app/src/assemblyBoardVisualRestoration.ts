// SPDX-License-Identifier: Apache-2.0
import type { ParsedBoard } from "./boardParser";

const retainedFeatureCount = (board: ParsedBoard) =>
  board.tracks.length + board.vias.length + board.pads.length + board.components.length + board.zones.length;

/** Keep progressively loaded visual assets without allowing an outline-only
 * active snapshot to hide the validated geometry retained in the assembly. */
export function restoreAssemblyBoardVisual(retained: ParsedBoard, active: ParsedBoard): ParsedBoard {
  if (retainedFeatureCount(retained) === 0 || retainedFeatureCount(active) > 0) return active;
  return {
    ...retained,
    fullModelUrl: active.fullModelUrl ?? retained.fullModelUrl,
    boardModelUrl: active.boardModelUrl ?? retained.boardModelUrl,
    boardModelIncludesCopper: active.boardModelIncludesCopper ?? retained.boardModelIncludesCopper,
    componentModelUrl: active.componentModelUrl ?? retained.componentModelUrl,
    layoutLayerUrls: active.layoutLayerUrls ?? retained.layoutLayerUrls,
    layoutViewBox: active.layoutViewBox ?? retained.layoutViewBox,
    modelManifestUrl: active.modelManifestUrl ?? retained.modelManifestUrl,
  };
}
