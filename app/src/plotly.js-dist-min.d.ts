// SPDX-License-Identifier: MIT
declare module "plotly.js-dist-min" {
  const Plotly: { react(target: HTMLElement, data: Record<string, unknown>[], layout: Record<string, unknown>, config?: Record<string, unknown>): Promise<void>; purge(target: HTMLElement): void; Plots: { resize(target: HTMLElement): void } };
  export default Plotly;
}
