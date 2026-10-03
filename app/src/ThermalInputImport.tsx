import { useState } from "react";
import DataTable from "./DataTable";
import type { ParsedBoard } from "./boardParser";
import { componentThermalElements, type ThermalElement } from "./thermalAssembly";
import { mapThermalRecords, parseThermalDelimited, suggestThermalMapping, thermalRowsFromOdb, type ThermalImportMapping, type ThermalImportResult, type ThermalImportRow } from "./thermalBomParsing";

type Props = { board: ParsedBoard | null; elements: ThermalElement[]; onElements: (rows: ThermalElement[]) => void };
const labels: Record<keyof ThermalImportMapping, string> = {
  reference: "Part reference", power_w: "Dissipation (W)", theta_top_c_per_w: "Top path (K/W)", theta_bottom_c_per_w: "Bottom path (K/W)",
};

export default function ThermalInputImport({ board, elements, onElements }: Props) {
  const [fileName, setFileName] = useState("");
  const [headers, setHeaders] = useState<string[]>([]);
  const [records, setRecords] = useState<Record<string, string>[]>([]);
  const [mapping, setMapping] = useState<ThermalImportMapping>({ reference: "", power_w: "", theta_top_c_per_w: "", theta_bottom_c_per_w: "" });
  const [message, setMessage] = useState("Choose a BOM CSV/TSV, or read named ODB++ component properties.");
  const [odbResult, setOdbResult] = useState<ThermalImportResult | null>(null);
  const preview = odbResult ?? (records.length ? mapThermalRecords(records, mapping, board) : null);

  const loadFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      if (file.size > 5_000_000) throw new Error("BOM file exceeds the 5 MB import limit.");
      const parsed = parseThermalDelimited(await file.text());
      setFileName(file.name); setHeaders(parsed.headers); setRecords(parsed.records);
      setMapping(suggestThermalMapping(parsed.headers)); setOdbResult(null);
      setMessage(`${parsed.records.length} BOM rows loaded. Check the column mapping and preview before applying.`);
    } catch (error) {
      setFileName(""); setHeaders([]); setRecords([]); setOdbResult(null);
      setMessage(error instanceof Error ? error.message : "BOM could not be parsed.");
    }
  };

  const readOdb = () => {
    const result = thermalRowsFromOdb(board);
    setFileName("ODB++ component properties"); setHeaders([]); setRecords([]); setOdbResult(result);
    setMessage(result.rows.length ? `${result.rows.length} ODB++ parts have named thermal properties.` : result.issues[0] ?? "No thermal properties found.");
  };

  const applyRows = (rows: ThermalImportRow[]) => {
    if (!board || !rows.length) return;
    const imported = new Map(rows.map(row => [row.reference.toUpperCase(), row]));
    const known = new Map(elements.map(row => [row.reference.toUpperCase(), row]));
    const missing = componentThermalElements(board).filter(row => imported.has(row.reference.toUpperCase()) && !known.has(row.reference.toUpperCase()));
    const merged = [...elements, ...missing].map(element => {
      const row = imported.get(element.reference.toUpperCase());
      return row ? { ...element, power_w: row.power_w, theta_top_c_per_w: row.theta_top_c_per_w, theta_bottom_c_per_w: row.theta_bottom_c_per_w } : element;
    });
    onElements(merged);
    setMessage(`Applied W and top/bottom K/W to ${rows.length} board parts. Review the part table before running.`);
  };

  return <div className="wizard-section thermal-import-section">
    <label>IMPORT PART THERMAL INPUTS</label>
    <p className="thermal-table-note">Match a BOM reference to dissipation in W and complete top/bottom thermal paths to ambient in K/W (or °C/W). Junction-to-case values alone are insufficient. Existing CAD geometry is unchanged.</p>
    <div className="thermal-import-actions">
      <label className="secondary-btn thermal-file-button">Choose BOM CSV/TSV<input type="file" accept=".csv,.tsv,.txt,text/csv,text/tab-separated-values" onChange={event => void loadFile(event.target.files?.[0])} /></label>
      <button className="secondary-btn" disabled={!board} onClick={readOdb}>Read ODB++ properties</button>
      <span>{fileName || "No file selected"}</span>
    </div>
    {headers.length > 0 && <div className="thermal-import-mapping">{(Object.keys(labels) as (keyof ThermalImportMapping)[]).map(field => <label key={field}>{labels[field]}<select value={mapping[field]} onChange={event => setMapping(current => ({ ...current, [field]: event.target.value }))}><option value="">Choose column</option>{headers.map(header => <option key={header} value={header}>{header}</option>)}</select></label>)}</div>}
    <p className="thermal-import-message" role="status">{message}</p>
    {preview && <>
      <div className="thermal-import-summary">{preview.rows.length} matched parts · {preview.issues.length} skipped or flagged rows</div>
      {preview.rows.length > 0 && <div className="thermal-import-preview"><DataTable label="Thermal import preview"><thead><tr><th>Reference</th><th>W</th><th>Top K/W</th><th>Bottom K/W</th></tr></thead><tbody>{preview.rows.slice(0, 12).map(row => <tr key={row.reference}><td>{row.reference}</td><td>{row.power_w}</td><td>{row.theta_top_c_per_w}</td><td>{row.theta_bottom_c_per_w}</td></tr>)}</tbody></DataTable>{preview.rows.length > 12 && <small>Showing first 12 of {preview.rows.length} matched parts.</small>}</div>}
      {preview.issues.length > 0 && <details className="thermal-import-issues"><summary>Review {preview.issues.length} import issues</summary>{preview.issues.slice(0, 40).map((issue, index) => <p key={index}>{issue}</p>)}{preview.issues.length > 40 && <p>Only the first 40 issues are shown.</p>}</details>}
      <button className="secondary-btn" disabled={!preview.rows.length || preview.rows.length > 256} onClick={() => applyRows(preview.rows)}>Apply matched values</button>
      {preview.rows.length > 256 && <p className="thermal-import-message">The SPIKE thermal run supports at most 256 parts per solve.</p>}
    </>}
  </div>;
}
