// SPDX-License-Identifier: Apache-2.0
declare module "plotly.js-dist-min" {
  const Plotly: { react(target: HTMLElement, data: Record<string, unknown>[], layout: Record<string, unknown>, config?: Record<string, unknown>): Promise<void>;
    relayout(target: HTMLElement, changes: Record<string, unknown>): Promise<void>;
    toImage(target: HTMLElement, options: { format: "png"; width: number; height: number }): Promise<string>;
    purge(target: HTMLElement): void; Plots: { resize(target: HTMLElement): Promise<void> | void } };
  export default Plotly;
}
