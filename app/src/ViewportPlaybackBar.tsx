// SPDX-License-Identifier: Apache-2.0
import { Play, Pause, RotateCcw } from "./icons";
import type { useViewportPlayback } from "./useViewportPlayback";
import "./buttonStandard.css";
import "./ViewportPlaybackBar.css";
export default function ViewportPlaybackBar({ playback: p }: { playback: ReturnType<typeof useViewportPlayback> }) {
  if (!p.current) return null;
  return <section className="viewport-playback" aria-label="Viewport result playback" data-frame={p.frame} data-playing={p.playing}>
    <label>Result<select aria-label="Playback result" value={p.selected} onChange={e => p.select(e.target.value)}>{p.sources.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select></label>
    <button type="button" className="spike-control--primary" aria-label={p.playing ? "Pause viewport results" : "Play viewport results"} onClick={() => p.toggle()}>{p.playing ? <Pause size={15}/> : <Play size={15}/>} {p.playing ? "Pause" : "Play"}</button>
    <button type="button" aria-label="Restart viewport results" onClick={() => p.seek(0)}><RotateCcw size={14}/></button>
    {p.timeline && <><input aria-label="Viewport result time" type="range" min="0" max={p.current.times.length - 1} value={p.frame} onChange={e => p.seek(Number(e.target.value))}/><output>{p.current.times[p.frame]?.toPrecision(5)} s · {p.frame + 1}/{p.current.times.length}</output>
      <label>Speed<select aria-label="Viewport playback speed" value={p.rate} onChange={e => p.setRate(Number(e.target.value))}>{[.25,.5,1,2,4].map(n => <option key={n} value={n}>{n}× review</option>)}</select></label><label><input type="checkbox" checked={p.loop} onChange={e => p.setLoop(e.target.checked)}/>Loop</label></>}
    <small>{p.timeline ? `Saved solver frames · ${p.speed.toPrecision(3)} simulated s / playback s` : "Flow motion on a frozen field"}{p.current.flow && " · moving markers show direction, not particle timing"}</small>
  </section>;
}
