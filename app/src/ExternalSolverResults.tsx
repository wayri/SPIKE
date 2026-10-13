// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import InteractivePlot from "./InteractivePlot";
import { NativeSolverFieldPreview } from "./NativeSolverFieldPreview";
import { solverRecord, solverResultData, solverTables } from "./solverExtensionModel";
export function ExternalSolverResults({ result, engine }: { result: unknown; engine: string }) {
  const [selected, select] = useState(0), [xColumn, setXColumn] = useState(0), [yColumn, setYColumn] = useState(1);
  const data = solverResultData(result), tables = solverTables(result);
  const table = tables[selected] ?? tables[0];
  const xi = Math.min(xColumn, (table?.columns.length ?? 1) - 1), yi = Math.min(yColumn, (table?.columns.length ?? 1) - 1);
  const diagnostics = Array.isArray(data.diagnostics) ? data.diagnostics : Array.isArray(data.issues) ? data.issues : [];
  const artifacts = Array.isArray(data.artifacts) ? data.artifacts : [];
  if (!Object.keys(data).length) return <p role="status">No {engine} result yet. Prepare and validate the case before running.</p>;
  const axis = (index: number) => table ? `${table.columns[index].name}${table.columns[index].unit ? ` (${table.columns[index].unit})` : ""}` : "";
  return <section aria-label={`${engine} results`}>
    <h4>Worker result</h4>
    <dl className="solver-status"><dt>Status</dt><dd>{String(data.status ?? "Returned")}</dd><dt>Solved</dt><dd>{data.solved === true ? "Solver returned a solved result" : "No solved result returned"}</dd><dt>Qualification</dt><dd>{String(data.model_status ?? "Unvalidated")} / {data.production_qualified === true ? "Production qualification reported by worker" : "Not production qualified"}</dd>{(data.case_id ?? solverRecord(data.case).job_id) != null && <><dt>Case</dt><dd>{String(data.case_id ?? solverRecord(data.case).job_id)}</dd></>}{Boolean(data.runtime) && <><dt>Runtime</dt><dd>{solverRecord(data.runtime).available === true ? "Available" : "Unavailable or not checked"} {String(solverRecord(data.runtime).executable ?? solverRecord(data.runtime).path ?? "")}</dd></>}</dl>
    {!!diagnostics.length && <ul className="solver-diagnostics">{diagnostics.map((value, i) => { const d = solverRecord(value); return <li key={i}><strong>{String(d.severity ?? "info")} {String(d.code ?? "")}</strong>: {String(d.message ?? value)}</li>; })}</ul>}
    {table && <><div className="solver-fields"><label>Result dataset<select value={selected < tables.length ? selected : 0} onChange={event => { select(Number(event.target.value)); setXColumn(0); setYColumn(1); }}>{tables.map((item, i) => <option key={i} value={i}>{item.name} ({item.rows.length} rows)</option>)}</select></label>{(["X", "Y"] as const).map((name, i) => <label key={name}>{name} axis<select value={i ? yi : xi} onChange={event => (i ? setYColumn : setXColumn)(Number(event.target.value))}>{table.columns.map((column, index) => <option key={index} value={index}>{column.name} {column.unit && `(${column.unit})`}</option>)}</select></label>)}</div>
      {!!table.rows.length && <div className="solver-plot"><InteractivePlot title={`${engine}: ${table.name}`} revision={`${data.case_id ?? ""}:${table.name}:${xi}:${yi}:${table.rows.length}`} data={[{ type: "scatter", mode: "lines", name: axis(yi), x: table.rows.map(row => row[xi]), y: table.rows.map(row => row[yi]) }]} layout={{ xaxis: { title: axis(xi) }, yaxis: { title: axis(yi) }, margin: { l: 65, r: 20, t: 30, b: 55 } }} /></div>}
      <div className="solver-scroll"><table><caption>{table.name}: first {Math.min(200, table.rows.length)} returned finite rows</caption><thead><tr>{table.columns.map((column, i) => <th key={i} scope="col">{column.name} {column.unit && `(${column.unit})`}</th>)}</tr></thead><tbody>{table.rows.slice(0, 200).map((row, i) => <tr key={i}>{row.map((value, j) => <td key={j}>{value.toPrecision(7)}</td>)}</tr>)}</tbody></table></div></>}
    {Array.isArray(data.field_previews) && <NativeSolverFieldPreview previews={data.field_previews} />}
    {!!artifacts.length && <details open><summary>Retained artifacts ({artifacts.length})</summary><div className="solver-scroll"><table><thead><tr><th scope="col">Name</th><th scope="col">Bytes</th><th scope="col">SHA-256</th></tr></thead><tbody>{artifacts.map((value, i) => { const a = solverRecord(value); return <tr key={i}><td>{String(a.name ?? a.file_name ?? "Artifact")}</td><td>{String(a.bytes ?? "")}</td><td>{String(a.sha256 ?? "")}</td></tr>; })}</tbody></table></div><small>Artifacts remain in the worker case. Inspect the case to refresh its retained outputs.</small></details>}
    <details><summary>Result provenance and raw worker payload</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>
  </section>;
}
