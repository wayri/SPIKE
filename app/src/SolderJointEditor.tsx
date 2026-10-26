// SPDX-License-Identifier: Apache-2.0
import type { BondRecord } from "./BondManager";
import SectionHelpButton from "./SectionHelpButton";
import { DEFAULT_SOLDER_JOINT_VISUAL, normalizeSolderJointVisual, type SolderJointVisual } from "./solderJointModel";
import "./buttonStandard.css";
import "./SolderJointEditor.css";

type Props = {
  bond: BondRecord | null;
  onChange: (visual: SolderJointVisual | undefined) => void;
};

const styles: Array<{ value: SolderJointVisual["style"]; label: string }> = [
  { value: "smd-fillet", label: "SMD fillet" },
  { value: "through-hole", label: "Through-hole" },
  { value: "terminal", label: "Terminal" },
];

function finiteInRange(value: string, minimum: number, maximum: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(maximum, Math.max(minimum, parsed)) : minimum;
}

export default function SolderJointEditor({ bond, onChange }: Props) {
  const visual = normalizeSolderJointVisual(bond?.solderVisual) ?? null;
  const patch = (next: Partial<SolderJointVisual>) => visual && onChange({ ...visual, ...next });
  const identity = bond ? [bond.reference, bond.pad].filter(Boolean).join(" / ") || bond.id : "No connection selected";

  return <section className="solder-joint-editor" aria-labelledby="solder-joint-editor-title">
    <header>
      <div><h3 id="solder-joint-editor-title">Solder presentation</h3><small title={identity}>{identity}</small>{bond?.boardInstanceId && <output className="solder-joint-occurrence" title={`Board occurrence ${bond.boardInstanceId}`}>Occurrence: {bond.boardInstanceId}</output>}</div>
      <SectionHelpButton topic="doc:docs/SOLDER_CONNECTIONS.md" label="Solder connections" />
    </header>
    <p>Optional display geometry only. It does not infer weld quality or change electrical or thermal values.</p>
    {!bond ? <div className="solder-joint-editor-empty" role="status">Select a connection row to edit its solder geometry.</div> : <div className="solder-joint-editor-controls">
      {!visual ? <button type="button" className="spike-control--primary" onClick={() => onChange(DEFAULT_SOLDER_JOINT_VISUAL)}>Enable solder visual</button> : <>
        <label className="solder-joint-visible"><input type="checkbox" checked={visual.visible} onChange={event => patch({ visible: event.target.checked })} />Show in viewport</label>
        <label>Style<select aria-label="Solder joint style" value={visual.style} onChange={event => patch({ style: event.target.value as SolderJointVisual["style"] })}>{styles.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        <label>Height (mm)<input aria-label="Solder joint height in millimeters" type="number" min="0.01" max="20" step="0.01" value={visual.heightMm} onChange={event => patch({ heightMm: finiteInRange(event.target.value, 0.01, 20) })} /></label>
        <label>Spread (mm)<input aria-label="Solder joint spread in millimeters" type="number" min="0" max="20" step="0.01" value={visual.spreadMm} onChange={event => patch({ spreadMm: finiteInRange(event.target.value, 0, 20) })} /></label>
        <label>Opacity<input aria-label="Solder joint opacity" type="number" min="0.05" max="1" step="0.05" value={visual.opacity} onChange={event => patch({ opacity: finiteInRange(event.target.value, 0.05, 1) })} /></label>
        <button type="button" className="spike-control--compact" onClick={() => onChange(undefined)}>Remove visual</button>
      </>}
    </div>}
  </section>;
}
