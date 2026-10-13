// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import InteractivePlot from "./InteractivePlot";
import { solverRecord } from "./solverExtensionModel";
export function NativeSolverFieldPreview({ previews }: { previews: unknown[] }) {
  const [fieldIndex, setFieldIndex] = useState(0), [arrayIndex, setArrayIndex] = useState(0), [component, setComponent] = useState(0), [probe, setProbe] = useState(0);
  const field = solverRecord(previews[fieldIndex] ?? previews[0]);
  const arrays = Array.isArray(field.arrays) ? field.arrays.map(solverRecord) : [];
  const array = arrays[arrayIndex] ?? arrays[0];
  const points = Array.isArray(field.points) ? field.points as unknown[][] : [];
  const values = Array.isArray(array?.values) ? array.values as unknown[][] : [];
  const components = Number(array?.components ?? 1);
  const sample = points.flatMap((point, index) => {
    const row = values[index];
    if (!Array.isArray(point) || point.length !== 3 || !point.every(value => typeof value === "number" && Number.isFinite(value)) || !Array.isArray(row) || row.length !== components || !row.every(value => typeof value === "number" && Number.isFinite(value))) return [];
    const numbers = row as number[];
    return [{ point: point as number[], value: component === -1 ? Math.hypot(...numbers) : numbers[Math.min(component, components - 1)], index }];
  });
  const active = sample.find(item => item.index === probe) ?? sample[0];
  const unit = array?.units == null ? "Units not declared by worker" : String(array.units);
  if (!previews.length) return null;
  return <section aria-label="PALACE native field samples"><h4>Native mesh field samples</h4><div className="solver-fields"><label>Field artifact<select value={fieldIndex < previews.length ? fieldIndex : 0} onChange={event => { setFieldIndex(Number(event.target.value)); setArrayIndex(0); setComponent(0); setProbe(0); }}>{previews.map((item, index) => <option key={index} value={index}>{String(solverRecord(item).name ?? `Field ${index + 1}`)}</option>)}</select></label>{array && <><label>Native point array<select value={arrayIndex < arrays.length ? arrayIndex : 0} onChange={event => { setArrayIndex(Number(event.target.value)); setComponent(0); }}>{arrays.map((item, index) => <option key={index} value={index}>{String(item.name)}</option>)}</select></label><label>Displayed component<select value={component} onChange={event => setComponent(Number(event.target.value))}>{Array.from({ length: components }, (_, index) => <option key={index} value={index}>Component {index + 1}</option>)}{components > 1 && <option value={-1}>Vector magnitude (displayed norm)</option>}</select></label></>}</div>
    <p role="status">{String(field.status ?? "Unavailable")} - {sample.length} finite displayed samples from {String(field.source_point_count ?? points.length)} native points{field.sampled === true ? " (sampled)" : ""}.</p><small>Coordinates retain mesh units; one mesh unit equals {String(field.coordinate_units_m ?? "unspecified")} m. {unit}. Point samples have no interpolation or inferred surface geometry.</small>
    {!!sample.length && <><div className="solver-plot"><InteractivePlot title={`PALACE native samples: ${String(array?.name)}`} revision={`${field.name}:${array?.name}:${component}:${sample.length}`} data={[{ type: "scatter3d", mode: "markers", x: sample.map(item => item.point[0]), y: sample.map(item => item.point[1]), z: sample.map(item => item.point[2]), customdata: sample.map(item => item.index), marker: { size: 3, color: sample.map(item => item.value), colorscale: "Viridis", showscale: true, colorbar: { title: String(array?.units ?? "native value") } }, text: sample.map(item => `${String(array?.name)}: ${item.value}`) }]} layout={{ scene: { xaxis: { title: "X (mesh units)" }, yaxis: { title: "Y (mesh units)" }, zaxis: { title: "Z (mesh units)" }, aspectmode: "data" }, margin: { l: 0, r: 30, t: 20, b: 0 } }} onPointClick={point => setProbe(Number(point.customdata))} /></div><label>Probe retained node<select value={active?.index ?? 0} onChange={event => setProbe(Number(event.target.value))}>{sample.map(item => <option key={item.index} value={item.index}>Node {item.index}: {item.point.join(", ")}</option>)}</select></label>{active && <dl className="solver-status"><dt>Position (mesh units)</dt><dd>{active.point.join(", ")}</dd><dt>{String(array?.name)} {component === -1 ? "displayed norm" : `component ${component + 1}`}</dt><dd>{active.value.toPrecision(8)} {array?.units == null ? "(units unspecified)" : String(array.units)}</dd></dl>}</>}
    {!!sample.length && <details><summary>Native point sample table</summary><div className="solver-scroll"><table><caption>First {Math.min(40, sample.length)} finite displayed native samples</caption><thead><tr><th scope="col">Retained node</th><th scope="col">X (mesh units)</th><th scope="col">Y (mesh units)</th><th scope="col">Z (mesh units)</th><th scope="col">{String(array?.name)} {component === -1 ? "displayed norm" : `component ${component + 1}`}</th></tr></thead><tbody>{sample.slice(0, 40).map(item => <tr key={item.index}><td>{item.index}</td>{item.point.map((value, index) => <td key={index}>{value.toPrecision(8)}</td>)}<td>{item.value.toPrecision(8)}</td></tr>)}</tbody></table></div></details>}
  </section>;
}
