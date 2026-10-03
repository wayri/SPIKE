// SPDX-License-Identifier: Apache-2.0
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import PlotlyChart from "../../src/PlotlyChart";
import { SiPlot } from "../../src/SiWorkflowPlots";
import "../../src/siWorkflow.css";
import "../../src/tableTheme.css";
const line = [{ type: "scatter", mode: "lines+markers", name: "Controller_board_with_a_long_name / voltage", x: [0, 1, 2, 3, 4, 5, 6], y: [1, 1.2, null, .9, 1.1, 1, 1.3], connectgaps: false }];
const cases: Record<string, { data: Record<string, unknown>[]; layout: Record<string, unknown> }> = {
  line: { data: line, layout: { xaxis: { title: "Time (ns)" }, yaxis: { title: "Voltage (V)" } } },
  log: { data: [{ type: "scatter", x: [1, 10, 100, 1000], y: [1, 2, 3, 2], name: "Log sweep" }], layout: { xaxis: { title: "Frequency (Hz)", type: "log" }, yaxis: { title: "Impedance (ohm)" } } },
  spatial: { data: [{ type: "scatter3d", mode: "lines+markers", name: "Spatial fixture", x: [0, 1, 2], y: [0, 2, 1], z: [0, 1, 2] }], layout: { scene: { xaxis: { title: "X (mm)" }, yaxis: { title: "Y (mm)" }, zaxis: { title: "Z (mm)" } } } },
  field: { data: [{ type: "heatmap", x: [0, 1, 2], y: [0, 1], z: [[1, null, 2], [3, 4, 5]] }], layout: { xaxis: { title: "X (mm)" }, yaxis: { title: "Y (mm)" } } },
  workflow: { data: line, layout: {} },
};
function Fixture() {
  const [kind, setKind] = useState("line"), [width, setWidth] = useState("900"), [theme, setTheme] = useState("professional-dark");
  useEffect(() => { document.documentElement.dataset.tableTheme = theme; }, [theme]);
  const figure = cases[kind];
  return <main data-table-theme={theme} style={{ minHeight: "120vh", padding: 16, font: "12px system-ui", color: "var(--spike-table-text)", background: "var(--spike-table-surface)" }}>
    <h1>SPIKE plot interactions</h1><p>Synthetic interface fixture, not solver output. Wheel scrolling should continue through the page.</p>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 14 }}>
      <label>Plot type <select value={kind} onChange={e => setKind(e.target.value)}><option value="line">Line with gap</option><option value="log">Logarithmic</option><option value="spatial">3D</option><option value="field">Field map</option><option value="workflow">SI workflow adapter</option></select></label>
      <label>Panel width <select value={width} onChange={e => setWidth(e.target.value)}><option>420</option><option>900</option><option>1200</option></select></label>
      <label>Theme <select value={theme} onChange={e => setTheme(e.target.value)}><option value="professional-dark">Dark</option><option value="light">Light</option><option value="high-contrast">High contrast</option></select></label>
    </div>
    <div style={{ width: `min(${width}px, 100%)`, minWidth: 0 }}>{kind === "workflow" ? <SiPlot title="Synthetic SI workflow adapter" curves={[{ name: line[0].name, points: line[0].x.map((x, index) => ({ x, y: line[0].y[index] ?? NaN })) }, { name: "Receiver_board / reference voltage", points: line[0].x.map((x, index) => ({ x, y: (line[0].y[index] ?? NaN) + .05 })) }]} xLabel="Time (ns)" yLabel="Voltage (V)"/> : <PlotlyChart title={`${kind} plot fixture`} data={figure.data} layout={{ ...figure.layout, paper_bgcolor: theme === "light" ? "#fff" : "#111f29", plot_bgcolor: theme === "light" ? "#fff" : "#111f29", font: { color: theme === "light" ? "#23384a" : "#dce7ee" }, margin: { t: 34, l: 64, r: 28, b: 48 } }} revision={kind}/>}</div>
    <p>Paste example: two tab-separated columns with headers Time (ns) and Voltage (V). Incompatible units and non-finite values are rejected.</p>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Fixture/>);
