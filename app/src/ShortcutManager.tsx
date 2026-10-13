// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { defaultShortcuts, eventShortcutKey, fixedShortcuts, shortcutBindingIssue, shortcutGroups, shortcutLabels, type ShortcutAction, type ShortcutMap, type ShortcutPreset } from "./shortcutCatalog";
import "./buttonStandard.css";
import "./ShortcutManager.css";

export type ShortcutManagerProps = {
  shortcuts: ShortcutMap;
  onAssign: (action: ShortcutAction, key: string) => void;
  onReset: () => void;
  onPreset: (preset: ShortcutPreset) => void;
  onClose: () => void;
};

export default function ShortcutManager({ shortcuts, onAssign, onReset, onPreset, onClose }: ShortcutManagerProps) {
  const [query, setQuery] = useState("");
  const [capturing, setCapturing] = useState<ShortcutAction | null>(null);
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState<{ action: ShortcutAction; key: string; conflict: ShortcutAction } | null>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    search.current?.focus();
    return () => { if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
  }, []);
  const beginCapture = (action: ShortcutAction) => { setCapturing(action); setPending(null); setNotice(`Press the shortcut for ${shortcutLabels[action]}. Escape cancels; Delete clears.`); };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    // Do not let assignments reach workspace or viewport hotkeys.
    event.stopPropagation();
    if (capturing) {
      event.preventDefault();
      if (event.repeat || event.nativeEvent.isComposing) return;
      if (event.key === "Escape") { setCapturing(null); setNotice("Assignment cancelled."); return; }
      if (["Delete", "Backspace"].includes(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
        onAssign(capturing, ""); setCapturing(null); setNotice("Shortcut unassigned."); return;
      }
      const key = eventShortcutKey(event);
      if (!key) return;
      const issue = shortcutBindingIssue(key);
      if (issue) { setNotice(issue); return; }
      const conflict = (Object.keys(shortcuts) as ShortcutAction[]).find(action => action !== capturing && shortcuts[action] === key);
      if (conflict) {
        setPending({ action: capturing, key, conflict });
        setNotice(`${key} is assigned to ${shortcutLabels[conflict]}. Swap to give that action ${shortcuts[capturing] || "an unassigned shortcut"}.`);
        setCapturing(null);
      } else {
        onAssign(capturing, key); setCapturing(null); setNotice(`${shortcutLabels[capturing]} assigned to ${key}.`);
      }
      return;
    }
    if (event.key === "Escape") { event.preventDefault(); if (pending) { setPending(null); setNotice("Assignment cancelled."); } else onClose(); }
    if (event.key === "Tab") {
      const controls = [...(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, a[href]') ?? [])];
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  };
  const term = query.trim().toLowerCase();
  const matches = (label: string, key: string, group: string) => `${label} ${key} ${group}`.toLowerCase().includes(term);
  const unassigned = (Object.keys(shortcuts) as ShortcutAction[]).filter(action => !shortcuts[action]);
  return <div className="shortcut-manager-shade" onKeyDown={onKeyDown}>
    <div className="shortcut-manager" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="shortcut-manager-title" aria-describedby="shortcut-manager-help">
      <header><h2 id="shortcut-manager-title">Keyboard shortcuts</h2><button type="button" aria-label="Close shortcut manager" onClick={onClose}>Close</button></header>
      <p id="shortcut-manager-help">The KiCad preset follows PCB and 3D viewer actions where SPIKE supports them. SPIKE analysis and assembly actions use Ctrl+Shift shortcuts. Existing saved bindings are preserved.</p>
      <div className="shortcut-manager-tools">
        <label>Search actions<input ref={search} type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Action, group or shortcut" /></label>
        <button type="button" onClick={() => { onPreset("kicad"); setCapturing(null); setPending(null); setNotice("KiCad preset applied."); }}>KiCad preset</button>
        <button type="button" onClick={() => { onPreset("spike"); setCapturing(null); setPending(null); setNotice("Legacy SPIKE preset applied."); }}>SPIKE preset</button>
        <button type="button" onClick={() => { onReset(); setCapturing(null); setPending(null); setNotice("KiCad defaults restored."); }}>Reset defaults</button>
      </div>
      {unassigned.length > 0 && <p className="shortcut-manager-warning">{unassigned.length} unassigned action{unassigned.length === 1 ? "" : "s"}. Saved bindings take priority when new defaults collide. Assign a key or apply a preset to restore them.</p>}
      <div className="shortcut-manager-status" role="status" aria-live="polite">{notice || "Click a shortcut, then press a key with Ctrl, Shift or Alt. Delete clears an assignment."}
        {pending && <div><button type="button" onClick={() => { onAssign(pending.action, pending.key); setNotice(`Swapped shortcuts for ${shortcutLabels[pending.action]} and ${shortcutLabels[pending.conflict]}.`); setPending(null); }}>Swap bindings</button><button type="button" onClick={() => { setPending(null); setNotice("Assignment cancelled."); }}>Cancel assignment</button></div>}
      </div>
      <div className="shortcut-manager-list">
        {shortcutGroups.map(group => {
          const visible = group.actions.filter(action => matches(shortcutLabels[action], shortcuts[action], group.label));
          return visible.length ? <section key={group.label}><h3>{group.label}</h3>{visible.map(action => <div className="shortcut-manager-row" key={action}>
            <span>{shortcutLabels[action]}<small>Default: {defaultShortcuts[action]}</small></span>
            <button type="button" aria-label={`Assign ${shortcutLabels[action]}`} aria-pressed={capturing === action} onClick={() => beginCapture(action)}><kbd>{capturing === action ? "Press shortcut..." : shortcuts[action] || "Unassigned"}</kbd></button>
            <button type="button" aria-label={`Clear ${shortcutLabels[action]}`} disabled={!shortcuts[action]} onClick={() => { onAssign(action, ""); setCapturing(null); setPending(null); setNotice(`${shortcutLabels[action]} unassigned.`); }}>Clear</button>
          </div>)}</section> : null;
        })}
        <section><h3>Fixed application shortcuts</h3>{fixedShortcuts.filter(item => matches(item.label, item.key, "Fixed application shortcuts")).map(item => <div className="shortcut-manager-row shortcut-manager-fixed" key={item.key}><span>{item.label}</span><kbd>{item.key}</kbd></div>)}</section>
        {!shortcutGroups.some(group => group.actions.some(action => matches(shortcutLabels[action], shortcuts[action], group.label))) && !fixedShortcuts.some(item => matches(item.label, item.key, "Fixed application shortcuts")) && <p>No matching shortcuts.</p>}
      </div>
      <footer><span>Ctrl also accepts Command on macOS. Shortcuts apply when the viewport or workspace has focus.</span><a href="https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#actions-reference" target="_blank" rel="noreferrer">KiCad action reference</a></footer>
    </div>
  </div>;
}
