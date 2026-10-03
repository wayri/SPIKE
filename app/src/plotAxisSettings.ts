// SPDX-License-Identifier: Apache-2.0
import type { PlotTrace } from "./plotClipboard";
export type AxisDraft = { scale: "linear" | "log"; auto: boolean; minimum: string; maximum: string };
export type AxisSettings = { x: AxisDraft; y: AxisDraft; grid: "off" | "major" | "minor"; crosshair: boolean };
export function buildPlotAxes(settings: AxisSettings, data: readonly PlotTrace[]): Record<string, Record<string, unknown>> {
  const output: Record<string, Record<string, unknown>> = {};
  for (const coordinate of ["x", "y"] as const) {
    const draft = settings[coordinate];
    if (draft.scale === "log" && data.some(trace => {
      const samples = trace[coordinate];
      return (Array.isArray(samples) || ArrayBuffer.isView(samples)) && Array.from(samples as ArrayLike<unknown>).some(value => typeof value === "number" && Number.isFinite(value) && value <= 0);
    })) throw new Error(`${coordinate.toUpperCase()} log scale requires positive coordinates. Non-positive samples will not be hidden silently.`);
    const axis: Record<string, unknown> = { type: draft.scale, autorange: draft.auto, showgrid: settings.grid !== "off",
      minor: { showgrid: settings.grid === "minor", ticks: settings.grid === "minor" ? "outside" : "", ticklen: 3 },
      showspikes: settings.crosshair, spikemode: "across", spikesnap: "cursor", spikethickness: 1, spikedash: "dot" };
    if (!draft.auto) {
      const minimum = Number(draft.minimum), maximum = Number(draft.maximum);
      if (!draft.minimum.trim() || !draft.maximum.trim() || !Number.isFinite(minimum) || !Number.isFinite(maximum) || minimum >= maximum) throw new Error(`${coordinate.toUpperCase()} bounds must be finite, with minimum smaller than maximum.`);
      if (draft.scale === "log" && minimum <= 0) throw new Error(`${coordinate.toUpperCase()} log bounds must be positive, in the displayed units.`);
      axis.range = draft.scale === "log" ? [Math.log10(minimum), Math.log10(maximum)] : [minimum, maximum];
    }
    output[`${coordinate}axis`] = axis;
  }
  return output;
}
