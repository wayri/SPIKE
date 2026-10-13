// SPDX-License-Identifier: Apache-2.0
// Browser-only fixture. No project or solver data is loaded or saved.
import { useState } from "react";
import { createRoot } from "react-dom/client";
import TerminalTable, { type TerminalTableRow } from "../../src/TerminalTable";
import DataTable, { type DataTableTheme } from "../../src/DataTable";
import TableIdentityInput from "../../src/TableIdentityInput";
import "../../src/styles.css";

function Fixture() {
  const [width, setWidth] = useState(1100);
  const [theme, setTheme] = useState<DataTableTheme>("professional-dark");
  const [rows, setRows] = useState<TerminalTableRow[]>(() => Array.from({ length: 205 }, (_, i) => ({
    id: `source-${i}`, name: `Source ${i}`, x: String(i), y: "10", layer: "auto", value: "3.3", contactResistance: "0.01", packageResistance: "0",
  })));
  const [value, setValue] = useState("12");
  const [identities, setIdentities] = useState(["source-A", "source-B"]);
  return <main data-table-theme={theme} style={{ height: "100vh", overflow: "auto", padding: 24, display: "block", background: "var(--spike-table-surface)", color: "var(--spike-table-text)", colorScheme: "var(--spike-table-scheme)" }}>
    <h1 style={{ fontSize: 20 }}>SPIKE table interaction fixture</h1>
    <p>Development sample data only. Test narrow panels, keyboard entry, search, details and pagination.</p>
    <label>Panel width <select aria-label="Fixture panel width" value={width} style={{ background: "var(--spike-table-surface)", color: "var(--spike-table-text)", colorScheme: "var(--spike-table-scheme)" }} onChange={e => setWidth(Number(e.target.value))}>
      <option value={420}>420 px</option><option value={920}>920 px</option><option value={1100}>1100 px</option>
    </select></label>
    <label style={{ marginLeft: 16 }}>Table theme <select aria-label="Fixture table theme" value={theme} style={{ background: "var(--spike-table-surface)", color: "var(--spike-table-text)", colorScheme: "var(--spike-table-scheme)" }} onChange={event => setTheme(event.target.value as DataTableTheme)}>
      <option value="professional-dark">Professional dark</option><option value="light">Light</option><option value="high-contrast">High contrast</option><option value="system">Follow system</option>
    </select></label>
    <div style={{ width, maxWidth: "100%", marginTop: 16, display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 16 }}>
      <DataTable label="Identifier edits"><thead><tr><th>ID</th><th>Committed value</th></tr></thead>
        <tbody>{identities.map((id, index) => <tr key={id}><td><TableIdentityInput aria-label={`Identity ${index + 1}`} value={id}
          onCommit={next => setIdentities(current => current.map((item, i) => i === index ? next : item))}
          validate={next => !next.trim() ? "ID cannot be blank." : next !== id && identities.includes(next) ? "ID already exists." : ""} /></td><td>{id}</td></tr>)}</tbody>
      </DataTable>
      <TerminalTable rows={rows} label="Voltage sources" layers={["F.Cu", "B.Cu"]} valueLabel="Voltage (V)"
        onChange={(id, patch) => setRows(current => current.map(row => row.id === id ? { ...row, ...patch } : row))}
        onRemove={id => setRows(current => current.filter(row => row.id !== id))}
        renderDetails={row => <label>Details for {row.name}<textarea aria-label={`Notes for ${row.id}`} defaultValue="Multiline notes retain Enter." /></label>} />
      <div style={{ minWidth: 0 }}><DataTable label="Validation and keyboard cases">
        <thead><tr><th>Name</th><th>Value</th><th>Choice</th><th>Notes</th><th>Action</th></tr></thead>
        <tbody><tr><th scope="row"><input aria-label="Case A name" defaultValue="First" /></th><td><input aria-label="Case A value" type="number" value={value} onChange={e => setValue(e.target.value)} aria-invalid={Number(value) < 0} /></td>
          <td><select aria-label="Case A choice" defaultValue="one"><option value="one">First choice</option><option value="two">Second choice</option></select></td>
          <td><textarea aria-label="Case A notes" defaultValue="Line one" /></td><td><button disabled>Unavailable</button></td></tr>
          <tr><th scope="row"><input aria-label="Case B name" defaultValue="Second" /></th><td><input aria-label="Case B value" disabled value="7" /></td><td><input aria-label="Case B choice" readOnly value="Read only" /></td><td><textarea aria-label="Case B notes" /></td><td>Skipped by navigation</td></tr>
          <tr><th scope="row"><input aria-label="Case C name" defaultValue="Third" /></th><td><input aria-label="Case C value" type="number" defaultValue="9" /></td><td><input aria-label="Case C choice" defaultValue="Editable" /></td><td><textarea aria-label="Case C notes" /></td><td><button>Available</button></td></tr>
        </tbody></DataTable></div>
    </div>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
