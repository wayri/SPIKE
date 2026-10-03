// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import DataTable from "./DataTable";
import type { ParsedBoard } from "./boardParser";
import { numericExtent } from "./numericRange";
import { thermalFieldColor } from "./thermalResultFields";

type Node = { id: string; component_ref: string; steady_temperature_c: number; peak_transient_temperature_c?: number; peak_transient_time_s?: number; time_to_90pct_steady_s?: number | null; final_to_steady_gap_c?: number };
type Frame = { time_s: number; temperatures_c: Record<string, number> };

export default function ThermalTransientOverlay({ board, nodes, frames }: { board: ParsedBoard | null; nodes: Node[]; frames: Frame[] }) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing || frames.length < 2) return;
    const timer = window.setInterval(() => setIndex(current => current >= frames.length - 1 ? 0 : current + 1), 600);
    return () => window.clearInterval(timer);
  }, [playing, frames.length]);
  if (frames.length < 2) return null;
  const frame = frames[Math.min(index, frames.length - 1)];
  const allValues = frames.flatMap(sample => nodes.map(node => sample.temperatures_c[node.id]).filter(Number.isFinite));
  const { minimum, maximum } = numericExtent(allValues);
  const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
  const positions = new Map(board?.components.map(part => [part.ref, part.at]) ?? []);
  const bounds = board?.bounds;
  const margin = bounds ? Math.max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY) * 0.03 : 0;
  const radius = bounds ? Math.max(1, Math.min(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY) / 90) : 1;
  const hottest = nodes.reduce<{ ref: string; temperature: number } | null>((best, node) => {
    const temperature = frame.temperatures_c[node.id];
    return finite(temperature) && (!best || temperature > best.temperature) ? { ref: node.component_ref, temperature } : best;
  }, null);
  return <div className="wizard-section thermal-transient-overlay"><label>TRANSIENT PART OVERLAY · APPROXIMATE OBJECT TEMPERATURES</label>
    <p className="thermal-table-note">Markers are solved lumped object temperatures at imported part locations. Their color does not imply a continuous board temperature field. The board-layer animation below is a separate spatial model.</p>
    <div className="thermal-native-actions"><button type="button" onClick={() => setPlaying(value => !value)}>{playing ? "Pause" : "Play"}</button><input aria-label="Thermal part animation time frame" type="range" min="0" max={frames.length - 1} value={index} onChange={event => { setPlaying(false); setIndex(Number(event.target.value)); }} /><span>{frame.time_s.toFixed(2)} s · hottest {hottest ? `${hottest.ref} ${hottest.temperature.toFixed(2)} °C` : "—"}</span></div>
    {bounds && <svg role="img" aria-label="Board outline with transient component temperature markers" viewBox={`${bounds.minX - margin} ${bounds.minY - margin} ${bounds.maxX - bounds.minX + 2 * margin} ${bounds.maxY - bounds.minY + 2 * margin}`} preserveAspectRatio="xMidYMid meet" className="thermal-part-overlay-figure"><rect x={bounds.minX} y={bounds.minY} width={bounds.maxX - bounds.minX} height={bounds.maxY - bounds.minY} fill="#edf4fa" />{board?.outlineLoops.map((loop, loopIndex) => <polyline key={loopIndex} points={loop.map(point => `${point[0]},${point[1]}`).join(" ")} fill="none" stroke="#427498" strokeWidth={radius / 3} />)}{nodes.map(node => { const point = positions.get(node.component_ref); const value = frame.temperatures_c[node.id]; if (!point || !finite(value)) return null; const [r, g, b] = thermalFieldColor(value, minimum, maximum); return <g key={node.id}><circle cx={point[0]} cy={point[1]} r={radius * 2} fill={`rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`} opacity="0.3" /><circle cx={point[0]} cy={point[1]} r={radius} fill={`rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`} stroke="#173653" strokeWidth={radius / 5}><title>{`${node.component_ref}: ${value.toFixed(2)} °C at ${frame.time_s.toFixed(2)} s`}</title></circle></g>; })}</svg>}
    <div className="thermal-native-results"><DataTable label="Thermal transient component results"><thead><tr><th>Part</th><th>Current °C</th><th>Peak °C</th><th>Peak time s</th><th>90% of steady s</th><th>Final to steady °C</th></tr></thead><tbody>{nodes.map(node => <tr key={node.id}><td>{node.component_ref}</td><td>{finite(frame.temperatures_c[node.id]) ? frame.temperatures_c[node.id].toFixed(2) : "—"}</td><td>{finite(node.peak_transient_temperature_c) ? node.peak_transient_temperature_c.toFixed(2) : "—"}</td><td>{finite(node.peak_transient_time_s) ? node.peak_transient_time_s.toFixed(2) : "—"}</td><td>{finite(node.time_to_90pct_steady_s) ? node.time_to_90pct_steady_s.toFixed(2) : "not reached"}</td><td>{finite(node.final_to_steady_gap_c) ? node.final_to_steady_gap_c.toFixed(2) : "—"}</td></tr>)}</tbody></DataTable></div>
    <small>90% time is linearly interpolated between saved samples when the steady target is reached; it is not a fitted physical time constant.</small>
  </div>;
}
