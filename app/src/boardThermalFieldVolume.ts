// SPDX-License-Identifier: Apache-2.0
import { boardThermalViewportGrid, boardThermalAxisEdges } from "./boardThermalViewport";
import { admitFieldVolume, type FieldVolumeData, type FieldPoint } from "./fieldVolumeModel";

/** Repackage returned layer cells, preserving XY, layer order, temperatures and
 * timestamps. Z uses the existing viewport's board-midplane convention. */
export function boardThermalFieldVolume(raw: unknown): FieldVolumeData | null {
  const grid = boardThermalViewportGrid(raw);
  if (!grid) return null;
  const result = raw as { layer_grids?: { thickness_mm: number; temperatures_c: number[] }[]; transient?: { time_s: number; layer_temperatures_c: number[][] }[] };
  const layers = result.layer_grids, frames = result.transient;
  if (!layers?.length || !frames || frames.length < 2 || !layers.every(l => Number.isFinite(l.thickness_mm) && l.thickness_mm > 0)) return null;
  const [nx, ny] = grid.shape, xe = boardThermalAxisEdges(grid, 0), ye = boardThermalAxisEdges(grid, 1);
  const centers: FieldPoint[] = [], sizes: FieldPoint[] = [];
  let z = layers.reduce((sum, l) => sum + l.thickness_mm, 0) / 2;
  for (const layer of layers) {
    for (let y = 0; y < ny; y++) for (let x = 0; x < nx; x++) {
      centers.push([(xe[x] + xe[x + 1]) / 2, (ye[y] + ye[y + 1]) / 2, z - layer.thickness_mm / 2]);
      sizes.push([xe[x + 1] - xe[x], ye[y + 1] - ye[y], layer.thickness_mm]);
    }
    z -= layer.thickness_mm;
  }
  if (!frames.every(f => Array.isArray(f.layer_temperatures_c) && f.layer_temperatures_c.length === layers.length && f.layer_temperatures_c.every(a => Array.isArray(a) && a.length === nx * ny))) return null;
  try { return admitFieldVolume({ contract: "spike/field-volume-view/v1", id: "board-thermal-transient", label: "Board temperature transient", lengthUnit: "mm",
    geometryNote: "Saved approximate layered-board temperatures. Source XY and top-to-bottom layer order retained; Z centered on the board midplane. No component-body or airflow temperatures inferred.",
    cells: { centers, sizes }, quantities: [{ id: "temperature_c", label: "Board temperature", unit: "°C" }],
    frames: frames.map(f => ({ timeS: f.time_s, scalars: { temperature_c: f.layer_temperatures_c.flat() } })) }); }
  catch { return null; }
}
