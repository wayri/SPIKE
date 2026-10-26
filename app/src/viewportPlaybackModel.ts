// SPDX-License-Identifier: Apache-2.0
import { createPlaybackTimeline } from "./transientPlayback";
import type { SolverResultBundle, ResultVisualization } from "./analysisResults";
import type { FieldVolumeData, FieldViewOptions } from "./fieldVolumeModel";
import { traceFieldGrid } from "./fieldStreamTracing";

export function hasPlayableFlow(data: FieldVolumeData, options: FieldViewOptions): boolean {
  if (!["streamlines", "streamtubes"].includes(options.mode) || !data.quantities.some(q => q.unit === "m/s")) return false;
  return data.frames.some((frame, index) => {
    if (!frame.vectors?.some(v => Math.hypot(...v) > 0)) return false;
    if (frame.streamlines?.some(path => path.points.some((p, i) => i > 0 && p.some((v, axis) => v !== path.points[i - 1][axis])))) return true;
    return options.mode === "streamtubes" && traceFieldGrid(data, { ...options, frame: index }).length > 0;
  });
}

/** Presentation duration only: microsecond electrical and minute thermal runs
 * both start with a readable eight-second replay. Solver timestamps stay intact. */
export function reviewPlaybackSpeed(times: readonly number[]): number {
  try { const t = createPlaybackTimeline(times).timesS; return (t[t.length - 1] - t[0]) / 8; }
  catch { return 1; }
}
export function transientBoardMode(result: SolverResultBundle): ResultVisualization["mode"] | null {
  if (result.status !== "completed" || result.time_series.frames.length < 2) return null;
  const fields = result.scalar_fields;
  const candidates = [["voltage_drop", "voltage_drop_v"], ["voltage", "voltage_v"], ["current", "current_a"], ["power_loss", "power_loss_w"]] as const;
  return candidates.find(([, key]) => result.time_series.frames.some(frame => frame.scalar_fields?.[key]?.length || (fields[key]?.length && frame.scalar_values?.[key]?.length)))?.[0] ?? null;
}
