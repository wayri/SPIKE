export type ThermalCoordinateFrame = "domain_local" | "board_local" | "board_absolute";

export type ThermalCoordinateBoard = {
  width: number;
  height: number;
  bounds: { minX: number; maxX: number; minY: number; maxY: number };
};

export type ThermalCoordinateVolume = { x: number; y: number; z: number };

/** Convert a thermal-contract coordinate into the board-centred scene frame, in millimetres. */
export function thermalScenePointMm(
  point: [number, number, number],
  frame: ThermalCoordinateFrame,
  volume: ThermalCoordinateVolume,
  board: ThermalCoordinateBoard,
): [number, number, number] {
  if (frame === "board_local") return [point[0] - board.width / 2, board.height / 2 - point[1], point[2]];
  if (frame === "board_absolute") {
    const centerX = (board.bounds.minX + board.bounds.maxX) / 2;
    const centerY = (board.bounds.minY + board.bounds.maxY) / 2;
    return [point[0] - centerX, centerY - point[1], point[2]];
  }
  return [point[0] - volume.x / 2, volume.y / 2 - point[1], point[2]];
}
