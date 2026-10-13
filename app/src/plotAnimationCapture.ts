// SPDX-License-Identifier: Apache-2.0
import { throwIfCancelled } from "./transientPlayback";

type PlotlyGraph = HTMLDivElement & {
  once?: (event: string, callback: () => void) => void;
  removeListener?: (event: string, callback: () => void) => void;
};

const graphIn = (root: HTMLElement | null): PlotlyGraph | null => root?.querySelector<PlotlyGraph>(".trace-plot-canvas") ?? null;

function bounded<T>(task: Promise<T>, signal: AbortSignal | undefined, label: string, timeoutMs = 10_000): Promise<T> {
  throwIfCancelled(signal);
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    const finish = (value: T | undefined, error?: Error) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      signal?.removeEventListener("abort", aborted);
      if (error) reject(error); else resolve(value as T);
    };
    const aborted = () => finish(undefined, new DOMException("Animation export cancelled.", "AbortError"));
    const timer = window.setTimeout(() => finish(undefined, new Error(`${label} exceeded the ${(timeoutMs / 1000).toFixed(0)} second capture limit.`)), timeoutMs);
    signal?.addEventListener("abort", aborted, { once: true });
    task.then(value => finish(value), error => finish(undefined, error instanceof Error ? error : new Error(String(error))));
  });
}

/** Wait for the dedicated Plotly surface to finish the frame requested by React state. */
export function waitForPlotlyRender(root: HTMLElement | null, signal?: AbortSignal, timeoutMs = 10_000): Promise<void> {
  throwIfCancelled(signal);
  const graph = graphIn(root);
  if (!graph) return Promise.reject(new Error("The thermal volume plot is not available for animation capture."));
  if (typeof graph.once !== "function") {
    return new Promise<void>((resolve, reject) => {
      let first = 0, second = 0;
      let settled = false;
      const finish = (error?: Error) => {
        if (settled) return;
        settled = true;
        cancelAnimationFrame(first); cancelAnimationFrame(second); window.clearTimeout(timer);
        signal?.removeEventListener("abort", aborted);
        if (error) reject(error); else resolve();
      };
      const aborted = () => finish(new DOMException("Animation export cancelled.", "AbortError"));
      const timer = window.setTimeout(() => finish(new Error(`Thermal plot did not paint within the ${(timeoutMs / 1000).toFixed(0)} second capture limit.`)), timeoutMs);
      signal?.addEventListener("abort", aborted, { once: true });
      first = requestAnimationFrame(() => { second = requestAnimationFrame(() => finish()); });
    });
  }
  return new Promise<void>((resolve, reject) => {
    let settled = false;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      graph.removeListener?.("plotly_afterplot", rendered);
      signal?.removeEventListener("abort", aborted);
      if (error) reject(error); else resolve();
    };
    const rendered = () => finish();
    const aborted = () => finish(new DOMException("Animation export cancelled.", "AbortError"));
    const timer = window.setTimeout(() => finish(new Error(`Thermal plot did not finish rendering within the ${(timeoutMs / 1000).toFixed(0)} second capture limit.`)), timeoutMs);
    signal?.addEventListener("abort", aborted, { once: true });
    graph.once!("plotly_afterplot", rendered);
  });
}

/** Capture only the plot inside root; other viewport or workspace canvases are ignored. */
export async function capturePlotlySurface(root: HTMLElement | null, width = 800, height = 500, signal?: AbortSignal): Promise<ImageData> {
  throwIfCancelled(signal);
  const graph = graphIn(root);
  if (!graph) throw new Error("The thermal volume plot is not available for animation capture.");
  const plotly = (await import("plotly.js-dist-min")).default;
  throwIfCancelled(signal);
  const url = await bounded(plotly.toImage(graph, { format: "png", width, height }), signal, "Thermal plot image rendering");
  throwIfCancelled(signal);
  const image = new Image();
  image.src = url;
  await bounded(image.decode(), signal, "Thermal plot image decoding");
  throwIfCancelled(signal);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("2D thermal animation capture is unavailable.");
  context.drawImage(image, 0, 0, width, height);
  return context.getImageData(0, 0, width, height);
}
