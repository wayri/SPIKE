// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { adjustPiLoadFromWheel, createPiQuickTuneScheduler, type PiQuickTuneSetup, type PiQuickTuneTerminal } from "./piQuickTune";
import type { ViewportNetTuneHandler } from "./viewportNetTune";
import { Play, RotateCcw, SlidersHorizontal } from "./icons";

type Props<T extends PiQuickTuneSetup<PiQuickTuneTerminal>> = {
  setup: T; scope: string; occurrenceId: string; available: boolean; busy: boolean;
  onChange: (setup: T) => void; onRun: (setup: T, scope: string) => Promise<void>;
  onHandler: (handler: ViewportNetTuneHandler | undefined) => void;
  onStatus: (message: string) => void;
};
/** UI owns edits; the existing validated PI transaction owns all solver work. */
export default function PiQuickTuneBar<T extends PiQuickTuneSetup<PiQuickTuneTerminal>>(props: Props<T>) {
  const [enabled, setEnabled] = useState(false);
  const [autoRun, setAutoRun] = useState(true);
  const [sink, setSink] = useState("");
  const [message, setMessage] = useState("Shift + wheel: 0.1 A · Shift + Alt: 0.01 A");
  const [undo, setUndo] = useState<{ before: T; after: T; scope: string } | null>(null);
  const latest = useRef(props); latest.current = props;
  const scheduled = useRef<T | null>(null);
  const scheduler = useRef<ReturnType<typeof createPiQuickTuneScheduler<{ setup: T; scope: string }>> | null>(null);
  useEffect(() => {
    const owned = createPiQuickTuneScheduler<{ setup: T; scope: string }>({
      run: async job => {
        const current = latest.current;
        if (!current.available || current.busy || current.scope !== job.scope || current.setup !== job.setup) return;
        scheduled.current = null;
        await current.onRun(job.setup, job.scope);
      },
      onError: error => latest.current.onStatus(error instanceof Error ? error.message : "Viewport PI rerun failed."),
    });
    scheduler.current = owned;
    return () => { owned.dispose(); scheduler.current = null; };
  }, []);
  useEffect(() => {
    scheduler.current?.invalidate(); scheduled.current = null; setUndo(null); setSink("");
  }, [props.scope]);
  useEffect(() => {
    if (scheduled.current && scheduled.current !== props.setup) { scheduler.current?.invalidate(); scheduled.current = null; }
  }, [props.setup]);
  useEffect(() => {
    if (!enabled || !props.available) { props.onHandler(undefined); scheduler.current?.invalidate(); return; }
    props.onHandler(event => {
      const current = latest.current;
      if (!current.available) return false;
      // Reserve Shift-wheel while armed: an invalid edit must not zoom instead.
      if (current.busy || scheduler.current?.isBusy()) { current.onStatus("Wait for the active analysis before adjusting a PI sink."); return true; }
      try {
        const adjustment = adjustPiLoadFromWheel(current.setup, { ...event, occurrenceId: event.occurrenceId ?? current.occurrenceId, terminalId: event.terminalId ?? (sink || undefined) }, current.occurrenceId);
        const next = adjustment.setup;
        setUndo(previous => previous?.scope === current.scope && previous.after === current.setup ? { ...previous, after: next } : { before: current.setup, after: next, scope: current.scope });
        scheduled.current = next;
        // Keep consecutive wheel events coherent before the next React render.
        latest.current = { ...current, setup: next };
        current.onChange(next);
        setMessage(`${event.net}: ${adjustment.currentA.toFixed(2)} A · previous overlay hidden${autoRun ? " · rerun after 0.5 s" : " · press Run"}`);
        if (autoRun) scheduler.current?.schedule({ setup: next, scope: current.scope });
      } catch (error) { current.onStatus(error instanceof Error ? error.message : "PI sink adjustment blocked."); }
      return true;
    });
    return () => props.onHandler(undefined);
  }, [enabled, props.available, props.occurrenceId, sink, autoRun, props.onHandler]);
  const loadIds = props.setup.loads.map(load => load.id.trim());
  const validIds = loadIds.every(Boolean) && new Set(loadIds).size === loadIds.length;
  const run = () => { scheduler.current?.invalidate(); void props.onRun(props.setup, props.scope).catch(error => props.onStatus(String(error))); };
  return <div className="pi-quick-tune-bar" role="toolbar" aria-label="Viewport PI load tuning" style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 5, padding: "4px 8px", fontSize: 11 }}>
    <button type="button" disabled={!props.available || props.busy || !validIds} aria-pressed={enabled} title="Arm Shift-wheel editing on the tested power net; requires an assigned PI source and sink" onClick={() => setEnabled(value => !value)}><SlidersHorizontal size={13}/> Tune PI</button>
    {!validIds && <span role="status">PI sink IDs must be nonblank and unique. Repair them in PI setup.</span>}
    {enabled && validIds && <><select aria-label="Sink adjusted by Shift-wheel" disabled={props.busy} value={sink} onChange={event => setSink(event.target.value)}><option value="">Hovered sink / unique net sink</option>{props.setup.loads.map(load => <option key={load.id} value={load.id}>{load.id} · {load.value} A</option>)}</select>
      <button type="button" disabled={props.busy} aria-pressed={autoRun} title="Rerun validated DC PI after scrolling stops" onClick={() => { scheduler.current?.invalidate(); setAutoRun(value => !value); }}>Auto run</button>
      <button type="button" disabled={props.busy} title="Run the current PI setup through preflight and resource admission" onClick={run}><Play size={13}/> Run</button>
      <button type="button" disabled={props.busy || !undo || undo.after !== props.setup || undo.scope !== props.scope} title="Restore current before the wheel burst; does not restore a stale result" onClick={() => { if (!undo) return; scheduler.current?.invalidate(); scheduled.current = null; props.onChange(undo.before); setUndo(null); setMessage("Current restored; run PI to refresh the overlay."); }}><RotateCcw size={13}/> Undo</button>
      <span role="status">{message}</span></>}
  </div>;
}
