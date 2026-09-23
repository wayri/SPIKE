import { Fragment, useState, type ReactNode } from "react";
import "./TerminalTable.css";

export type TerminalTableRow = {
  id: string; name: string; x: string; y: string; layer: string;
  value: string; contactResistance: string; packageResistance: string;
};

/** One authoritative terminal record per row; expensive pad/waveform editors are lazy. */
export default function TerminalTable<T extends TerminalTableRow>({
  rows, label, layers, valueLabel, transient = false, readOnlyValue,
  onChange, onRemove, renderDetails,
}: {
  rows: T[]; label: string; layers: string[]; valueLabel: string;
  transient?: boolean; readOnlyValue?: (item: T, index: number) => string;
  onChange: (id: string, patch: Partial<TerminalTableRow>) => void;
  onRemove: (id: string) => void; renderDetails: (item: T, index: number) => ReactNode;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const field = (item: T, key: keyof Omit<TerminalTableRow, "id" | "layer">, title: string) =>
    <input aria-label={`${label}: ${item.name} ${title}`} value={item[key]}
      onChange={event => onChange(item.id, { [key]: event.target.value })} />;
  return <div className="terminal-table-scroll" role="region" aria-label={label} tabIndex={0}>
    <table className="terminal-table">
      <caption>{label} · {rows.length} {rows.length === 1 ? "terminal" : "terminals"}</caption>
      <thead><tr><th scope="col">Name</th><th scope="col">X (mm)</th><th scope="col">Y (mm)</th>
        <th scope="col">Connection</th><th scope="col">{transient ? "Waveform" : valueLabel}</th>
        <th scope="col">Contact R (Ω)</th><th scope="col">Package R (Ω)</th><th scope="col">Actions</th></tr></thead>
      <tbody>{rows.map((item, index) => <Fragment key={item.id}>
        <tr><td>{field(item, "name", "name")}</td><td>{field(item, "x", "X (mm)")}</td>
          <td>{field(item, "y", "Y (mm)")}</td>
          <td><select aria-label={`${label}: ${item.name} connection`} value={item.layer || "auto"}
            onChange={event => onChange(item.id, { layer: event.target.value })}>
            <option value="auto">Auto — connected copper</option>
            {layers.map(layer => <option key={layer} value={layer}>{layer} only</option>)}
          </select></td>
          <td>{readOnlyValue ? <span>{readOnlyValue(item, index)}</span> : transient
            ? <button type="button" onClick={() => setExpanded(item.id)}>Edit waveform</button>
            : field(item, "value", valueLabel)}</td>
          <td>{field(item, "contactResistance", "contact resistance")}</td>
          <td>{field(item, "packageResistance", "package resistance")}</td>
          <td><div className="terminal-table-actions"><button type="button" aria-expanded={expanded === item.id}
            aria-label={`Edit pads and details for ${item.name}`} onClick={() => setExpanded(expanded === item.id ? null : item.id)}>
            {expanded === item.id ? "Close details" : "Pads / details"}</button>
            <button type="button" aria-label={`Remove ${item.name}`} onClick={() => onRemove(item.id)}>×</button></div></td>
        </tr>
        {expanded === item.id && <tr className="terminal-table-detail"><td colSpan={8}>{renderDetails(item, index)}</td></tr>}
      </Fragment>)}</tbody>
    </table>
    {!rows.length && <p className="terminal-table-empty">No terminals. Add one below or use the board selection.</p>}
  </div>;
}
