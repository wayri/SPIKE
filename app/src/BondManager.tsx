import { useMemo, useState } from "react";
import { CheckCircle2, Link2, Plus, Search, Trash2, WandSparkles, X } from "lucide-react";

export type BondStatus = "draft" | "ready" | "warning" | "invalid" | "disabled";

export type BondRecord = {
  id: string;
  componentId?: string;
  padId?: string;
  position?: [number, number];
  connectedLayers: string[];
  source?: "authoritative-pad" | "nearest-pad" | "manual";
  part: string;
  reference: string;
  pad: string;
  net: string;
  surface: string;
  searchDistanceMm: number;
  electricalResistanceOhm: number;
  currentLimitA: number;
  thermalConductivityWmK: number;
  contactAreaMm2: number;
  bondMaterial: string;
  status: BondStatus;
  enabled: boolean;
};

export type BondHoverTarget = {
  bondId: string;
  part: string;
  reference: string;
  pad: string;
  net: string;
  surface: string;
};

export type BondValidationResult = {
  bondId?: string;
  status: BondStatus;
  message: string;
};

export type BondManagerProps = {
  bonds: readonly BondRecord[];
  onBondsChange: (bonds: BondRecord[]) => void;
  onAutoConnect?: (searchDistanceMm: number) => void;
  onValidate?: () => void;
  onBondAdd?: (bond: BondRecord) => void;
  onBondChange?: (bond: BondRecord, previous: BondRecord) => void;
  onBondDelete?: (bond: BondRecord) => void;
  onHoverBond?: (bond: BondRecord | null) => void;
  onHoverTarget?: (target: BondHoverTarget | null) => void;
  onClose: () => void;
  validation?: readonly BondValidationResult[];
  title?: string;
};

export const DEFAULT_BOND_VALUES: Omit<BondRecord, "id"> = {
  connectedLayers: [],
  source: "manual",
  part: "",
  reference: "",
  pad: "",
  net: "",
  surface: "F.Cu",
  searchDistanceMm: 0.25,
  electricalResistanceOhm: 0.001,
  currentLimitA: 1,
  thermalConductivityWmK: 50,
  contactAreaMm2: 1,
  bondMaterial: "Solder",
  status: "draft",
  enabled: true,
};

export function createBondRecord(overrides: Partial<BondRecord> = {}): BondRecord {
  return {
    ...DEFAULT_BOND_VALUES,
    id: `bond-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    ...overrides,
  };
}

export function defaultBondRecord(overrides: Partial<BondRecord> = {}): BondRecord {
  return createBondRecord(overrides);
}

function numberOrZero(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

const statusOptions: BondStatus[] = ["draft", "ready", "warning", "invalid", "disabled"];

export default function BondManager({
  bonds,
  onBondsChange,
  onAutoConnect,
  onValidate,
  onBondAdd,
  onBondChange,
  onBondDelete,
  onHoverBond,
  onHoverTarget,
  onClose,
  validation = [],
  title = "Bond Manager",
}: BondManagerProps) {
  const [query, setQuery] = useState("");
  const [autoConnectDistance, setAutoConnectDistance] = useState(DEFAULT_BOND_VALUES.searchDistanceMm);
  const normalizedQuery = query.trim().toLowerCase();
  const visibleBonds = useMemo(() => bonds.filter(bond => !normalizedQuery || [
    bond.part, bond.reference, bond.pad, bond.net, bond.surface, bond.bondMaterial, bond.status,
  ].some(value => value.toLowerCase().includes(normalizedQuery))), [bonds, normalizedQuery]);

  const updateBond = (previous: BondRecord, patch: Partial<BondRecord>) => {
    const nextBond = { ...previous, ...patch };
    onBondsChange(bonds.map(bond => bond.id === previous.id ? nextBond : bond));
    onBondChange?.(nextBond, previous);
  };
  const addBond = () => {
    const bond = createBondRecord();
    onBondsChange([...bonds, bond]);
    onBondAdd?.(bond);
  };
  const deleteBond = (bond: BondRecord) => {
    onBondsChange(bonds.filter(item => item.id !== bond.id));
    onBondDelete?.(bond);
  };
  const preview = (bond: BondRecord | null) => {
    onHoverBond?.(bond);
    onHoverTarget?.(bond && {
      bondId: bond.id,
      part: bond.part,
      reference: bond.reference,
      pad: bond.pad,
      net: bond.net,
      surface: bond.surface,
    });
  };
  const validationFor = (bond: BondRecord) => validation.find(item => item.bondId === bond.id);

  return <div className="modal-shade bond-manager-shade" onPointerDown={event => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <section className="bond-manager" role="dialog" aria-modal="true" aria-label={title}>
      <header>
        <div><b>{title.toUpperCase()}</b><small>Component-to-pad and component-to-copper connection properties</small></div>
        <button onClick={onClose} title="Close Bond Manager" aria-label="Close Bond Manager"><X size={17} /></button>
      </header>

      <div className="bond-manager-toolbar">
        <label className="bond-manager-filter"><Search size={14} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Find part, pad, net, or material" autoFocus /></label>
        <span className="bond-manager-divider" />
        <label className="bond-manager-distance"><span>Search</span><input type="number" min="0.001" max="10" step="0.05" value={autoConnectDistance} onChange={event => setAutoConnectDistance(numberOrZero(event.target.value))} /><small>mm</small></label>
        <button onClick={() => onAutoConnect?.(autoConnectDistance)} disabled={!onAutoConnect || autoConnectDistance <= 0 || autoConnectDistance > 10} title="Connect imported footprint terminals to owned pads; use distance only when ownership is missing"><WandSparkles size={15} /> Auto-connect</button>
        <button onClick={onValidate} disabled={!onValidate} title="Validate bond geometry and physical properties"><CheckCircle2 size={15} /> Validate</button>
        <button onClick={addBond} title="Add an empty bond"><Plus size={15} /> Add bond</button>
      </div>

      <div className="bond-manager-body">
        <div className="bond-manager-table-wrap">
          <table className="bond-manager-table">
            <thead><tr><th>Use</th><th>Part</th><th>Reference</th><th>Pad</th><th>Net</th><th>Connected copper</th><th>Search distance (mm)</th><th>Electrical R (ohm)</th><th>Current limit (A)</th><th>Thermal k (W/mK)</th><th>Contact area (mm2)</th><th>Bond material</th><th>Status</th><th /></tr></thead>
            <tbody>{visibleBonds.map(bond => {
              const result = validationFor(bond);
              const status = bond.status;
              const displayStatus = result?.status ?? status;
              return <tr key={bond.id} className={`bond-manager-row ${displayStatus} ${bond.enabled ? "" : "disabled"}`} onMouseEnter={() => preview(bond)} onMouseLeave={() => preview(null)}>
                <td><input type="checkbox" checked={bond.enabled} onChange={event => updateBond(bond, { enabled: event.target.checked, status: event.target.checked && bond.status === "disabled" ? "draft" : event.target.checked ? bond.status : "disabled" })} aria-label={`Enable bond ${bond.reference || bond.id}`} /></td>
                <td><input value={bond.part} onChange={event => updateBond(bond, { part: event.target.value })} aria-label="Part" /></td>
                <td><input value={bond.reference} onChange={event => updateBond(bond, { reference: event.target.value })} aria-label="Reference" /></td>
                <td><input value={bond.pad} onChange={event => updateBond(bond, { pad: event.target.value })} aria-label="Pad" /></td>
                <td><input value={bond.net} onChange={event => updateBond(bond, { net: event.target.value })} aria-label="Net" /></td>
                <td><input value={bond.surface} onChange={event => { const surface = event.target.value; updateBond(bond, { surface, connectedLayers: surface.split("/").map(value => value.trim()).filter(Boolean) }); }} aria-label="Connected copper layers" title={bond.source === "authoritative-pad" ? "Imported from footprint pad ownership" : bond.source === "nearest-pad" ? "Inferred by bounded nearest-pad search" : "Manually defined"} /></td>
                <td><input type="number" min="0" step="any" value={bond.searchDistanceMm} onChange={event => updateBond(bond, { searchDistanceMm: numberOrZero(event.target.value) })} aria-label="Search distance in millimeters" /></td>
                <td><input type="number" min="0" step="any" value={bond.electricalResistanceOhm} onChange={event => updateBond(bond, { electricalResistanceOhm: numberOrZero(event.target.value) })} aria-label="Electrical resistance in ohms" /></td>
                <td><input type="number" min="0" step="any" value={bond.currentLimitA} onChange={event => updateBond(bond, { currentLimitA: numberOrZero(event.target.value) })} aria-label="Current limit in amperes" /></td>
                <td><input type="number" min="0" step="any" value={bond.thermalConductivityWmK} onChange={event => updateBond(bond, { thermalConductivityWmK: numberOrZero(event.target.value) })} aria-label="Thermal conductivity in watts per meter kelvin" /></td>
                <td><input type="number" min="0" step="any" value={bond.contactAreaMm2} onChange={event => updateBond(bond, { contactAreaMm2: numberOrZero(event.target.value) })} aria-label="Contact area in square millimeters" /></td>
                <td><input value={bond.bondMaterial} onChange={event => updateBond(bond, { bondMaterial: event.target.value })} aria-label="Bond material" /></td>
                <td><select value={status} onChange={event => updateBond(bond, { status: event.target.value as BondStatus })} aria-label="Bond status" title={result?.message}><option value={status}>{status}</option>{statusOptions.filter(option => option !== status).map(option => <option key={option} value={option}>{option}</option>)}</select></td>
                <td><button onClick={() => deleteBond(bond)} title={`Delete bond ${bond.reference || bond.id}`} aria-label={`Delete bond ${bond.reference || bond.id}`}><Trash2 size={14} /></button></td>
              </tr>;
            })}</tbody>
          </table>
          {!visibleBonds.length && <div className="bond-manager-empty"><Link2 size={24} /><b>{bonds.length ? "No bonds match this filter" : "No component bonds configured"}</b><span>{bonds.length ? "Change the filter to show the remaining bonds." : "Add a bond or auto-connect nearby component pads and copper."}</span></div>}
        </div>
        {!!validation.length && <div className="bond-manager-validation" aria-label="Bond validation results">{validation.map((result, index) => <div key={`${result.bondId ?? "all"}-${index}`} className={result.status}><b>{result.status}</b><span>{result.message}</span></div>)}</div>}
      </div>

      <footer><span>{bonds.filter(bond => bond.enabled).length} enabled / {bonds.length} total bonds</span><button className="secondary-btn" onClick={onClose}>Close</button></footer>
    </section>
  </div>;
}
