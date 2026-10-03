// SPDX-License-Identifier: Apache-2.0
// Normalize legacy title strings for the installed Plotly API, on an owned clone.
export function preparePlotLayout(layout: Record<string, unknown>, palette: { text: string; line: string; grid: string; surface?: string } = { text: "#cbd5e1", line: "#8397a6", grid: "#334155" }): Record<string, unknown> {
  const output = structuredClone(layout);
  const title = (item: Record<string, unknown>) => {
    if (typeof item.title === "string") item.title = { text: item.title };
  };
  const axis = (value: unknown) => {
    if (!value || typeof value !== "object") return;
    const item = value as Record<string, unknown>;
    title(item); item.automargin ??= true;
    item.showline ??= true; item.linewidth ??= 1.5; item.linecolor ??= palette.line;
    item.ticks ??= "outside"; item.ticklen ??= 5; item.tickwidth ??= 1;
    item.tickcolor ??= palette.line; item.gridcolor ??= palette.grid;
    if (palette.surface) { item.gridcolor = palette.grid; item.zerolinecolor = palette.line; }
    item.exponentformat ??= "SI"; item.separatethousands ??= true;
    item.tickfont = { size: 11, color: palette.text, ...(item.tickfont as object ?? {}) };
    if (item.title && typeof item.title === "object") {
      const label = item.title as Record<string, unknown>;
      label.standoff ??= 10; label.font = { size: 12, color: palette.text, ...(label.font as object ?? {}) };
    }
  };
  title(output);
  output.legend = { orientation: "h", x: 0, y: 1.04, yanchor: "bottom", maxheight: .2, ...(output.legend as object ?? {}) };
  if (palette.surface) {
    output.paper_bgcolor = palette.surface; output.plot_bgcolor = palette.surface;
    output.font = { ...(output.font as object ?? {}), color: palette.text };
  }
  for (const [key, value] of Object.entries(output)) {
    if (/^[xy]axis\d*$/.test(key)) axis(value);
    if (/^scene\d*$/.test(key) && value && typeof value === "object") {
      for (const coordinate of ["xaxis", "yaxis", "zaxis"]) axis((value as Record<string, unknown>)[coordinate]);
    }
  }
  return output;
}
