// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import type { ParsedBoard } from "./boardParser";
import { allocatePiPinLoads, eligibleComponentSupplyPads, type PiComponentLoadSelection, type PiPinLoadPolicy } from "./piPinLoads";
import { parseSpiceNumber } from "./transientWaveform";
import "./buttonStandard.css";
import "./PiComponentLoadPanel.css";

export type PiComponentLoadPanelProps = {
  board: ParsedBoard | null;
  net: string;
  initialRef?: string;
  initialTotalCurrentA?: number;
  fixedRef?: boolean;
  onApply: (selection: PiComponentLoadSelection) => void;
  onDraftChange?: () => void;
  busy?: boolean;
};
type Draft = { total: string; policy: PiPinLoadPolicy; pins: Record<string, { enabled: boolean; weight: string }> };
const emptyDraft = (): Draft => ({ total: "", policy: "equal", pins: {} });

export function PiComponentLoadPanel({ board, net, initialRef, initialTotalCurrentA, fixedRef = false, onApply, onDraftChange, busy = false }: PiComponentLoadPanelProps) {
  const candidates = useMemo(() => board ? board.components.map(component => ({
    component, pads: eligibleComponentSupplyPads(board, component.ref, net),
  })).filter(item => item.pads.length).sort((a, b) => Number(b.pads.length > 1) - Number(a.pads.length > 1)
    || a.component.ref.localeCompare(b.component.ref, undefined, { numeric: true })) : [], [board, net]);
  const [chosenRef, setChosenRef] = useState(initialRef ?? "");
  const selectedRef = fixedRef ? initialRef ?? "" : candidates.some(item => item.component.ref === chosenRef) ? chosenRef
    : candidates.find(item => item.component.ref === initialRef)?.component.ref ?? candidates[0]?.component.ref ?? "";
  // Keep edits when users explore another component or rail. A replacement board gets its own draft map.
  const [draftsByBoard] = useState(() => new WeakMap<ParsedBoard, Record<string, Draft>>());
  const [, redraw] = useState(0);
  const contextKey = JSON.stringify([net, selectedRef]);
  const drafts = board ? draftsByBoard.get(board) ?? {} : {};
  if (board && !draftsByBoard.has(board)) draftsByBoard.set(board, drafts);
  const draft = drafts[contextKey] ?? { ...emptyDraft(), total: initialTotalCurrentA === undefined ? "" : String(initialTotalCurrentA) };
  const update = (change: Partial<Draft>) => {
    if (!board) return;
    onDraftChange?.();
    drafts[contextKey] = { ...draft, ...change };
    redraw(value => value + 1);
  };
  const pads = candidates.find(item => item.component.ref === selectedRef)?.pads ?? [];
  const pinDraft = (id: string) => draft.pins[id] ?? { enabled: true, weight: "1" };
  const updatePin = (id: string, change: Partial<{ enabled: boolean; weight: string }>) => update({
    pins: { ...draft.pins, [id]: { ...pinDraft(id), ...change } },
  });
  let selection: PiComponentLoadSelection | undefined;
  let error = "";
  try {
    if (board && net && pads.length) {
      const totalCurrentA = parseSpiceNumber(draft.total, "Total component current");
      selection = { componentRef: selectedRef, totalCurrentA, policy: draft.policy,
        pins: allocatePiPinLoads(totalCurrentA, pads.filter(pad => pinDraft(pad.id).enabled).map(pad => ({
          padId: pad.id, weight: draft.policy === "weights" ? parseSpiceNumber(pinDraft(pad.id).weight, `Pad ${pad.name} weight`) : 1,
        })), draft.policy) };
    }
  } catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
  const unavailable = !board ? "Load a board to identify component supply pads."
    : !net ? "Select a PI rail to identify its component pads."
    : !candidates.length ? "No component copper pads were found on the selected rail."
    : !pads.length ? "The selected component has no copper pads on this rail." : "";
  return <section className="pi-component-load" aria-label="Component supply pin loads">
    <h4>Component supply pin loads</h4>
    <p>PCB connectivity identifies candidate pads on the selected rail. It cannot infer IC pin functions or internal current distribution. Equal sharing is an editable input assumption; confirm supply pins and total current from the component data.</p>
    {unavailable ? <p role="status">{unavailable}</p> : <>
      <fieldset disabled={busy}>
        <div className="pi-component-load__fields">
          <label>Component<select disabled={fixedRef} value={selectedRef} onChange={event => {onDraftChange?.();setChosenRef(event.target.value);}}>
            {candidates.map(({ component, pads: eligible }) => <option key={component.id} value={component.ref}>{component.ref} · {component.value} · {eligible.length} rail pads</option>)}
          </select></label>
          <label>Total current (A)<input type="text" inputMode="decimal" placeholder="Enter current, e.g. 250m" value={draft.total} onChange={event => update({ total: event.target.value })} /></label>
          <label>Pin allocation<select value={draft.policy} onChange={event => update({ policy: event.target.value as PiPinLoadPolicy })}>
            <option value="equal">Equal share</option><option value="weights">Custom weights</option>
          </select></label>
        </div>
        <div className="pi-component-load__table"><table><thead><tr><th scope="col">Use</th><th scope="col">Supply pad</th><th scope="col">Weight</th><th scope="col">Current (A)</th></tr></thead>
          <tbody>{pads.map(pad => <tr key={pad.id}>
            <td><input type="checkbox" aria-label={`Use ${selectedRef} pad ${pad.name} (${pad.id})`} checked={pinDraft(pad.id).enabled} onChange={event => updatePin(pad.id, { enabled: event.target.checked })} /></td>
            <td title={pad.id}>{pad.name || "Unnamed"}<small>{pad.id}</small></td>
            <td><input type="text" inputMode="decimal" aria-label={`Weight for pad ${pad.name} (${pad.id})`} disabled={draft.policy === "equal" || !pinDraft(pad.id).enabled} value={draft.policy === "equal" ? "1" : pinDraft(pad.id).weight} onChange={event => updatePin(pad.id, { weight: event.target.value })} /></td>
            <td>{!pinDraft(pad.id).enabled ? "Excluded" : selection?.pins.find(pin => pin.padId === pad.id)?.currentA.toPrecision(6) ?? "—"}</td>
          </tr>)}</tbody></table></div>
      </fieldset>
      {error && <p className="pi-component-load__error" role={draft.total ? "alert" : "status"}>{error}</p>}
      <button type="button" className="spike-control--primary" disabled={busy || !selection} onClick={() => { if (selection) onApply(selection); }}>Apply component pin loads</button>
    </>}
  </section>;
}

