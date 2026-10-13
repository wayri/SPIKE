// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import HarnessDocumentEditor from "./HarnessDocumentEditor";
import { ASSEMBLY_CONDUCTORS_KEY, assemblyHarnessDocument, retainAssemblyHarnessDocument, type AssemblyHarnessRow } from "./assemblyHarnessConductors";

export default function AssemblyHarnessWiring({ rows, onChange }: { rows: AssemblyHarnessRow[]; onChange: (row: AssemblyHarnessRow) => void }) {
  const [selected, setSelected] = useState(rows[0]?.id ?? "");
  const [error, setError] = useState("");
  useEffect(() => { if (!rows.some(row => row.id === selected)) setSelected(rows[0]?.id ?? ""); }, [rows, selected]);
  const row = rows.find(item => item.id === selected);
  const resolved = useMemo(() => {
    try { return { document: row ? assemblyHarnessDocument(row) : null, error: "" }; }
    catch (reason) { return { document: null, error: reason instanceof Error ? reason.message : String(reason) }; }
  }, [row]);
  if (!rows.length) return null;
  return <details className="assembly-harness-wiring"><summary>Wire diagram, pairs and harness analysis</summary>
    <label>Assembly harness<select value={selected} onChange={event => { setSelected(event.target.value); setError(""); }}>
      {rows.map(item => <option key={item.id} value={item.id}>{item.name || item.id} · {Object.keys(item.pin_map ?? {}).length} conductors</option>)}
    </select></label>
    <p>Each conductor follows an explicit saved pin pair. Edit endpoints and conductor count in the pin-map table. Save boards and links to retain wiring changes and update the assembly viewport. Harness analysis excludes board copper unless a separate coupled study includes it.</p>
    {(error || resolved.error) && <p role="alert">{error || resolved.error}</p>}
    {resolved.error && row?.extensions?.[ASSEMBLY_CONDUCTORS_KEY] && <button className="spike-control--danger" onClick={() => {
      const extensions = { ...row.extensions }; delete extensions[ASSEMBLY_CONDUCTORS_KEY]; onChange({ ...row, extensions }); setError("");
    }}>Clear saved conductor metadata from draft</button>}
    {resolved.document && row && <HarnessDocumentEditor key={row.id} value={resolved.document} onChange={next => {
      try { onChange(retainAssemblyHarnessDocument(row, next)); setError(""); }
      catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    }} />}
  </details>;
}
