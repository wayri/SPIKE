// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useRef, useState } from "react";
import type { AxisSettings } from "./plotAxisSettings";
export default function PlotAxisEditor({ initial, labels, onApply, onClose }: { initial: AxisSettings; labels: { x: string; y: string }; onApply: (settings: AxisSettings) => string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const headingId = useId();
  const [settings, setSettings] = useState(initial), [error, setError] = useState("");
  useEffect(() => { const element = dialog.current; element?.showModal(); return () => element?.close(); }, []);
  return <dialog ref={dialog} className="spike-plot-axis-editor" aria-labelledby={headingId} onCancel={event => { event.preventDefault(); onClose(); }} onKeyDown={event => event.stopPropagation()}>
    <form onSubmit={event => { event.preventDefault(); const message = onApply(settings); if (message) setError(message); }}>
      <header><h3 id={headingId}>Plot axes</h3><button type="button" aria-label="Close plot axes" onClick={onClose}>×</button></header>
      <p>Bounds use the displayed units. Axis settings affect this view only.</p>
      <div className="spike-plot-axis-fields">{(["x", "y"] as const).map(coordinate => {
        const axis = settings[coordinate], prefix = coordinate.toUpperCase();
        const edit = (patch: Partial<typeof axis>) => setSettings(value => ({ ...value, [coordinate]: { ...value[coordinate], ...patch } }));
        return <fieldset key={coordinate}><legend>{prefix} · {labels[coordinate] || "Unlabeled coordinate"}</legend>
          <label>{prefix} scale<select value={axis.scale} onChange={event => edit({ scale: event.target.value as typeof axis.scale })}><option value="linear">Linear</option><option value="log">Logarithmic</option></select></label>
          <label className="spike-plot-axis-check"><input type="checkbox" checked={axis.auto} onChange={event => edit({ auto: event.target.checked })}/>Fit {prefix} automatically</label>
          <label>{prefix} minimum<input inputMode="decimal" disabled={axis.auto} value={axis.minimum} onChange={event => edit({ minimum: event.target.value })}/></label>
          <label>{prefix} maximum<input inputMode="decimal" disabled={axis.auto} value={axis.maximum} onChange={event => edit({ maximum: event.target.value })}/></label>
        </fieldset>;
      })}</div>
      <div className="spike-plot-axis-options"><label>Grid<select value={settings.grid} onChange={event => setSettings(value => ({ ...value, grid: event.target.value as AxisSettings["grid"] }))}><option value="off">Off</option><option value="major">Major ticks</option><option value="minor">Major + minor ticks</option></select></label>
        <label className="spike-plot-axis-check"><input type="checkbox" checked={settings.crosshair} onChange={event => setSettings(value => ({ ...value, crosshair: event.target.checked }))}/>Hover crosshair</label></div>
      {error && <p role="alert">{error}</p>}
      <footer><button type="submit">Apply axes</button><button type="button" onClick={onClose}>Cancel</button></footer>
    </form>
  </dialog>;
}
