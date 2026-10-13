// SPDX-License-Identifier: Apache-2.0
export type ThermalFrame = { time_s: number; node_temperatures_k: number[] };
export function thermalFrames(result: any): ThermalFrame[] {
  const frames = result?.field_result?.frames;
  if (!Array.isArray(frames) || frames.length > 1001) return [];
  let previous = -1, total = 0, count: number | undefined;
  for (const frame of frames) {
    if (!Number.isFinite(frame?.time_s) || frame.time_s < 0 || frame.time_s <= previous || !Array.isArray(frame.node_temperatures_k) ||
      frame.node_temperatures_k.some((v: unknown) => typeof v !== "number" || !Number.isFinite(v) || v < 0)) return [];
    count ??= frame.node_temperatures_k.length;
    total += frame.node_temperatures_k.length;
    if (!count || frame.node_temperatures_k.length !== count || total > 200000) return [];
    previous = frame.time_s;
  }
  return frames;
}
export function thermalPlaybackIndex(frames: ThermalFrame[], time: number): number {
  let left = 0, right = frames.length - 1;
  while (left < right) { const mid = Math.ceil((left + right) / 2); if (frames[mid].time_s <= time) left = mid; else right = mid - 1; }
  return left;
}
