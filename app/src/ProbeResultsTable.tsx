// SPDX-License-Identifier: Apache-2.0
import type { BoardObject } from "./BoardViewport";
import DataTable from "./DataTable";
import type { SolverResultBundle } from "./analysisResults";
import { buildProbeRows, evaluateProbeFormulas, probeResultsCsv, type ProbeFormulaRow, type ProbeQuantity, type ProbeReferenceValues } from "./probeCalculations";
import "./ProbeResultsTable.css";

export type ProbeResultsTableProps = {
  probes: readonly BoardObject[];
  result: SolverResultBundle | null;
  calculatedRows: readonly ProbeFormulaRow[];
  onCalculatedRowsChange: (rows: ProbeFormulaRow[]) => void;
  onRemoveProbe: (id: string) => void;
  onRenameProbe?: (id: string, name: string) => void;
  onExportCsv?: (csv: string) => void;
  probeReferenceIds?: Readonly<Record<string, string>>;
};

const shown = (item?: ProbeQuantity) => item ? `${item.value.toPrecision(5)} ${item.unit === "1" ? "" : item.unit}`.trim() : "-";

export default function ProbeResultsTable({ probes, result, calculatedRows, onCalculatedRowsChange, onRemoveProbe, onRenameProbe, onExportCsv, probeReferenceIds = {} }: ProbeResultsTableProps) {
  const rows = buildProbeRows(probes, result, probeReferenceIds);
  const references: ProbeReferenceValues = Object.fromEntries(rows.map(row => [row.id, row.values]));
  const calculations = evaluateProbeFormulas(calculatedRows, references);
  const updateFormula = (id: string, patch: Partial<ProbeFormulaRow>) => onCalculatedRowsChange(calculatedRows.map(row => row.id === id ? { ...row, ...patch } : row));
  const exportCsv = () => {
    const csv = probeResultsCsv(rows, calculations);
    if (onExportCsv) { onExportCsv(csv); return; }
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    link.download = "spike-probe-results.csv"; link.click(); URL.revokeObjectURL(link.href);
  };
  const nextId = () => { let index = calculatedRows.length + 1; while (calculatedRows.some(row => row.id === `C${index}`)) index++; return `C${index}`; };
  return <section className="probe-table" aria-labelledby="probe-table-title">
    <header><div><h3 id="probe-table-title">Probe results</h3><p>Use stable IDs such as <code>{rows[0]?.id ?? "P1"}.voltage</code> in formulas.</p></div>
      <div className="probe-table-actions"><button type="button" onClick={() => { const id = nextId(); onCalculatedRowsChange([...calculatedRows, { id, name: `Calculation ${id}`, formula: "" }]); }}>Add formula</button>
        <button type="button" onClick={exportCsv} disabled={!rows.length && !calculatedRows.length}>Export CSV</button></div></header>
    <div className="probe-table-scroll" role="region" aria-label="Probe measurements and calculated rows" tabIndex={0}>
      <DataTable label="Probe results"><caption>{probes.length} measurement point{probes.length === 1 ? "" : "s"}; {calculatedRows.length} calculated row{calculatedRows.length === 1 ? "" : "s"}</caption>
        <thead><tr><th scope="col">ID / name</th><th scope="col">Status</th><th scope="col">Net / layer</th><th scope="col">Voltage</th><th scope="col">Drop</th><th scope="col">Current</th><th scope="col">Power</th><th scope="col">Density</th><th scope="col">Local Z / R</th><th scope="col">Actions</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.sourceId} title={row.message}>
          <th scope="row"><code>{row.id}</code>{onRenameProbe ? <input aria-label={`Name for probe ${row.id}`} value={row.name} onChange={event => onRenameProbe(row.sourceId, event.target.value)} /> : <span>{row.name}</span>}<small>{row.kind}</small></th>
          <td><span className={`probe-status probe-status-${row.status.replace(/[^a-z0-9]/gi, "-").toLowerCase()}`}>{row.status}</span>{row.message && <small>{row.message}</small>}</td>
          <td>{row.net ?? "No net"}<small>{row.layer ?? "through"}</small></td><td>{shown(row.values.voltage)}</td><td>{shown(row.values.drop)}</td><td>{shown(row.values.current)}</td><td>{shown(row.values.power)}</td><td>{shown(row.values.density)}</td><td>{shown(row.values.impedance)}</td>
          <td><button type="button" aria-label={`Remove probe ${row.name}`} onClick={() => onRemoveProbe(row.sourceId)}>Delete</button></td></tr>)}
          {calculations.map(row => <tr key={`formula:${row.id}`} className={row.error ? "probe-formula-error" : "probe-formula-row"}>
            <th scope="row"><code>{row.id}</code><input aria-label={`Name for calculated row ${row.id}`} value={row.name} onChange={event => updateFormula(row.id, { name: event.target.value })} /><small>calculated</small></th>
            <td colSpan={2}><label>Formula<input aria-label={`Formula for ${row.id}`} value={row.formula} placeholder="P1.voltage / P1.current" onChange={event => updateFormula(row.id, { formula: event.target.value })} aria-invalid={Boolean(row.error)} aria-describedby={`formula-status-${row.id}`} /></label><small id={`formula-status-${row.id}`} role={row.error ? "alert" : undefined}>{row.error ?? "Calculated from displayed solver values"}</small></td>
            <td colSpan={6} className="probe-formula-value">{row.result ? shown(row.result) : "-"}</td>
            <td><button type="button" aria-label={`Delete calculated row ${row.name}`} onClick={() => onCalculatedRowsChange(calculatedRows.filter(item => item.id !== row.id))}>Delete</button></td></tr>)}
        </tbody></DataTable>
      {!rows.length && !calculatedRows.length && <p className="probe-table-empty">No probes placed. Place a probe on a conductor to begin.</p>}
    </div>
  </section>;
}
