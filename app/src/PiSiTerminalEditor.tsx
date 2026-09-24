import { useId, useState, type ReactNode } from "react";
import { ChevronDown, Crosshair, MousePointer2, Plus, Trash2 } from "lucide-react";
import "./PiSiTerminalEditor.css";

export type PiSiTerminalRow = {
  id: string;
  name: string;
  x: string;
  y: string;
  layer: string;
  value: string;
  contactResistance: string;
  packageResistance: string;
};

export type PiSiTerminalEditorProps<T extends PiSiTerminalRow> = {
  rows: T[];
  label: string;
  layers: string[];
  valueLabel: string;
  transient?: boolean;
  readOnlyValue?: (item: T, index: number) => string;
  onChange: (id: string, patch: Partial<PiSiTerminalRow>) => void;
  onRemove: (id: string) => void;
  renderDetails: (item: T, index: number) => ReactNode;
  addLabel: string;
  pickLabel?: string;
  activePickLabel?: string;
  pickActive?: boolean;
  selectionAvailable?: boolean;
  selectionLabel?: string;
  emptyMessage?: string;
  onAdd: () => void;
  onTogglePick: () => void;
  onUseSelection: () => void;
};

/** Responsive PI/SI terminal cards. Record ownership and placement stay in the parent. */
export default function PiSiTerminalEditor<T extends PiSiTerminalRow>({
  rows, label, layers, valueLabel, transient = false, readOnlyValue,
  onChange, onRemove, renderDetails, addLabel, pickLabel = "Pick exact point",
  activePickLabel = "Click exact copper point", pickActive = false,
  selectionAvailable = false, selectionLabel = "Use current selection",
  emptyMessage = "No terminals. Add one below or use the board selection.",
  onAdd, onTogglePick, onUseSelection,
}: PiSiTerminalEditorProps<T>) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const controlId = useId().replace(/:/g, "");
  const edit = (item: T, key: keyof Omit<PiSiTerminalRow, "id" | "layer">, fieldLabel: string) =>
    <input aria-label={`${label}: ${item.name} ${fieldLabel}`} value={item[key]}
      onChange={event => onChange(item.id, { [key]: event.target.value })} />;
  const toggleDetails = (id: string) => setExpanded(current => current === id ? null : id);

  return <section className="pisi-terminal-editor" aria-label={label}>
    <header className="pisi-terminal-editor__summary">
      <h3>{label}</h3><span>{rows.length} {rows.length === 1 ? "terminal" : "terminals"}</span>
    </header>
    <div className="pisi-terminal-editor__cards">
      {rows.map((item, index) => {
        const detailsOpen = expanded === item.id;
        const detailsId = `${controlId}-terminal-details-${index}`;
        return <article className="pisi-terminal-editor__card" key={item.id}>
          <header className="pisi-terminal-editor__card-heading">
            <strong>{item.name || `Terminal ${index + 1}`}</strong>
            <div className="pisi-terminal-editor__row-actions">
              <button type="button" className="pisi-terminal-editor__details-button"
                aria-expanded={detailsOpen} aria-controls={detailsId}
                aria-label={`Edit pads and details for ${item.name}`} onClick={() => toggleDetails(item.id)}>
                Pads / details <ChevronDown size={14} aria-hidden="true" />
              </button>
              <button type="button" className="pisi-terminal-editor__remove-button"
                aria-label={`Remove ${item.name}`} title={`Remove ${item.name}`} onClick={() => onRemove(item.id)}>
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </div>
          </header>
          <div className="pisi-terminal-editor__grid">
            <label className="pisi-terminal-editor__field pisi-terminal-editor__field--name"><span>Name</span>{edit(item, "name", "name")}</label>
            <label className="pisi-terminal-editor__field"><span>X (mm)</span>{edit(item, "x", "X (mm)")}</label>
            <label className="pisi-terminal-editor__field"><span>Y (mm)</span>{edit(item, "y", "Y (mm)")}</label>
            <label className="pisi-terminal-editor__field pisi-terminal-editor__field--connection"><span>Connection</span>
              <select aria-label={`${label}: ${item.name} connection`} value={item.layer || "auto"}
                onChange={event => onChange(item.id, { layer: event.target.value })}>
                <option value="auto">Auto - connected copper</option>
                {layers.map(layer => <option key={layer} value={layer}>{layer} only</option>)}
              </select>
            </label>
            <div className="pisi-terminal-editor__field pisi-terminal-editor__field--value"><span>{transient ? "Waveform" : valueLabel}</span>
              {readOnlyValue
                ? <output aria-label={`${label}: ${item.name} ${valueLabel}`}>{readOnlyValue(item, index)}</output>
                : transient
                  ? <button type="button" onClick={() => setExpanded(item.id)}>Edit waveform</button>
                  : edit(item, "value", valueLabel)}
            </div>
            <label className="pisi-terminal-editor__field"><span>Contact R (ohm)</span>{edit(item, "contactResistance", "contact resistance")}</label>
            <label className="pisi-terminal-editor__field"><span>Package R (ohm)</span>{edit(item, "packageResistance", "package resistance")}</label>
          </div>
          {detailsOpen && <div className="pisi-terminal-editor__details" id={detailsId}>{renderDetails(item, index)}</div>}
        </article>;
      })}
    </div>
    {!rows.length && <p className="pisi-terminal-editor__empty">{emptyMessage}</p>}
    <footer className="pisi-terminal-editor__toolbar" aria-label={`${label} actions`}>
      <button type="button" onClick={onAdd}><Plus size={14} aria-hidden="true" /> {addLabel}</button>
      <button type="button" className={pickActive ? "selected" : ""} aria-pressed={pickActive} onClick={onTogglePick}>
        <Crosshair size={14} aria-hidden="true" /> {pickActive ? activePickLabel : pickLabel}
      </button>
      <button type="button" disabled={!selectionAvailable} onClick={onUseSelection}>
        <MousePointer2 size={14} aria-hidden="true" /> {selectionLabel}
      </button>
    </footer>
  </section>;
}
