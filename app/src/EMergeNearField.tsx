// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import DataTable from "./DataTable";
import PlotlyChart from "./PlotlyChart";
import { downloadEMergeText } from "./emergeSampleExport";

import { admitEMergeFieldPlanes } from "./emergeNearFieldSamples";

export function EMergeNearField({ value }: { value: unknown }) {
  const planes = admitEMergeFieldPlanes(value);
  const [frequency, setFrequency] = useState(0), [kind, setKind] = useState<"e_v_m" | "h_a_m">("e_v_m"), [sample, setSample] = useState(0);
  if (!planes.length) return null;
  const plane = planes[Math.min(frequency, planes.length - 1)], [ny, nx] = plane.grid_shape;
  const field = plane[kind], selected = Math.min(sample, field.length - 1);
  const magnitude = (i: number) => plane.valid[i] ? Math.hypot(...field[i]!.flat()) : null;
  const z = Array.from({ length: ny }, (_, row) => Array.from({ length: nx }, (_, col) => magnitude(row * nx + col)));
  const exportCsv = () => {
    const rows = ["frequency_hz,x_mm,y_mm,z_mm,valid,Ex_real,Ex_imag,Ey_real,Ey_imag,Ez_real,Ez_imag,Hx_real,Hx_imag,Hy_real,Hy_imag,Hz_real,Hz_imag"];
    planes.forEach(plane => plane.coordinates_mm.forEach((point, i) => rows.push([plane.frequency_hz, ...point, plane.valid[i], ...(plane.e_v_m[i]?.flat() ?? Array(6).fill("")), ...(plane.h_a_m[i]?.flat() ?? Array(6).fill(""))].join(","))));
    downloadEMergeText("emerge-nearfield.csv", rows.join("\n") + "\n");
  };
  return <section><div className="extension-output-title"><b>Complex near-field plane</b><select aria-label="Near-field frequency" value={frequency} onChange={event => setFrequency(Number(event.target.value))}>{planes.map((plane, i) => <option value={i} key={plane.frequency_hz}>{plane.frequency_hz} Hz</option>)}</select><select aria-label="Near-field quantity" value={kind} onChange={event => setKind(event.target.value as typeof kind)}><option value="e_v_m">Electric field (V/m)</option><option value="h_a_m">Magnetic field (A/m)</option></select></div><PlotlyChart revision={`field-${frequency}-${kind}`} data={[{ type: "heatmap", x: plane.coordinates_mm.slice(0, nx).map(point => point[0]), y: Array.from({ length: ny }, (_, row) => plane.coordinates_mm[row * nx][1]), z, connectgaps: false, colorscale: "Viridis", colorbar: { title: kind === "e_v_m" ? "V/m" : "A/m" } }]} layout={{ paper_bgcolor: "#101c23", plot_bgcolor: "#101c23", font: { color: "#c8d8dd" }, margin: { t: 25, l: 55, r: 65, b: 50 }, xaxis: { title: "X (mm)" }, yaxis: { title: "Y (mm)", scaleanchor: "x" } }} /><small>Complex vector magnitude from solved FEM field samples at explicit coordinates. Invalid samples are blank. No field interpolation is added in SPIKE. Amplitudes use solver modal excitation coefficients; input-power calibration is required for absolute field interpretation.</small><label>Probe grid sample<select aria-label="Near-field grid probe" value={selected} onChange={event => setSample(Number(event.target.value))}>{plane.coordinates_mm.map((point, i) => <option key={i} value={i}>{i}: ({point.map(n => n.toPrecision(5)).join(", ")}) mm{plane.valid[i] ? "" : " · invalid"}</option>)}</select></label>{plane.valid[selected] ? <DataTable label="EMerge near-field sample components"><thead><tr><th>Component</th><th>Real</th><th>Imaginary</th></tr></thead><tbody>{field[selected]!.map((pair, i) => <tr key={i}><td>{["X", "Y", "Z"][i]}</td><td>{pair[0].toPrecision(6)}</td><td>{pair[1].toPrecision(6)}</td></tr>)}</tbody></DataTable> : <p>Sample outside the valid FEM field domain.</p>}<button className="secondary-btn" onClick={exportCsv}>Export complex field CSV</button></section>;
}
