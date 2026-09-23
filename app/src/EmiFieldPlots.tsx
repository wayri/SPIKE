import { useMemo } from "react";
import type { EmiFarFieldResult } from "./EmiWorkbench";
import { emiSpectrum, fieldDbUvM } from "./emiFieldData";
import { numericMaximum, numericMinimum } from "./numericRange";

export function EmiFieldPlots({ field, frequencyIndex, onFrequency }: { field: EmiFarFieldResult; frequencyIndex: number; onFrequency: (index: number) => void }) {
  const rows = useMemo(() => emiSpectrum(field), [field]);
  const levels = rows.flatMap(row => row.db === null ? [] : [row.db]);
  const low = levels.length ? Math.floor(numericMinimum(levels) / 10) * 10 - 10 : 0;
  const high = levels.length ? Math.ceil(numericMaximum(levels) / 10) * 10 + 10 : 100;
  const minLog = Math.log10(rows[0].frequency), maxLog = Math.log10(rows[rows.length - 1].frequency);
  const x = (frequency: number) => 48 + (maxLog === minLog ? .5 : (Math.log10(frequency) - minLog) / (maxLog - minLog)) * 424;
  const y = (db: number) => 170 - (db - low) / (high - low) * 140;
  const nt = field.theta_deg.length, np = field.phi_deg.length;
  const peak = rows[frequencyIndex]?.db;
  const angular: React.ReactNode[] = [];
  // Bound SVG cells independently of solver sampling density.
  const ts = Math.max(1, Math.ceil(nt / 45)), ps = Math.max(1, Math.ceil(np / 90));
  for (let t = 0; t < nt; t += ts) for (let p = 0; p < np; p += ps) {
    const db = fieldDbUvM(field.e_field_v_m.magnitude[(frequencyIndex * nt + t) * np + p]);
    const relative = db === null || peak === null || peak === undefined ? 0 : Math.max(0, Math.min(1, (db - peak + 40) / 40));
    angular.push(<rect key={`${t}-${p}`} x={48 + p / np * 424} y={25 + t / nt * 140} width={Math.min(ps, np - p) / np * 424 + .2} height={Math.min(ts, nt - t) / nt * 140 + .2} fill={`hsl(${225 - relative * 195} 75% ${18 + relative * 40}%)`}><title>θ {field.theta_deg[t]}°, φ {field.phi_deg[p]}°: {db === null ? "zero field" : `${db.toFixed(2)} dBµV/m`}</title></rect>);
  }
  return <>
    <div className="emi-spectrum"><h3>Radiated field spectrum · {field.radius_m} m</h3>
      <svg viewBox="0 0 500 210" role="img" aria-label="Peak total electric field over sampled directions, logarithmic frequency axis">
        {[0, 1, 2, 3, 4].map(i => { const db = low + (high - low) * i / 4; return <g key={i}><line x1="48" x2="472" y1={y(db)} y2={y(db)} stroke="#2a414f" /><text x="42" y={y(db) + 3} textAnchor="end">{db.toFixed(0)}</text></g>; })}
        <text x="48" y="16">dBµV/m · angular peak, total E</text>
        <polyline points={rows.filter(r => r.db !== null).map(r => `${x(r.frequency)},${y(r.db!)}`).join(" ")} fill="none" stroke="#64dacf" strokeWidth="2" />
        {rows.map((row, i) => row.db === null ? null : <circle key={i} cx={x(row.frequency)} cy={y(row.db)} r={i === frequencyIndex ? 5 : 3} fill={i === frequencyIndex ? "#ffc673" : "#64dacf"} onClick={() => onFrequency(i)}><title>{(row.frequency / 1e6).toFixed(3)} MHz: {row.db.toFixed(2)} dBµV/m</title></circle>)}
        <text x="48" y="188">{(rows[0].frequency / 1e6).toFixed(2)} MHz</text><text x="472" y="188" textAnchor="end">{(rows[rows.length - 1].frequency / 1e6).toFixed(2)} MHz</text><text x="250" y="205" textAnchor="middle">Frequency (log scale)</text>
      </svg>
      <p className="emi-note">Computed total-field angular envelope at the result radius. No receiver detector, antenna factor or regulatory limit has been applied.</p>
      <table><thead><tr><th>MHz</th><th>dBµV/m</th><th>θ / φ peak</th></tr></thead><tbody>{rows.map((row, i) => <tr key={i}><td><button onClick={() => onFrequency(i)}>{(row.frequency / 1e6).toFixed(3)}</button></td><td>{row.db?.toFixed(2) ?? "Zero"}</td><td>{row.theta}° / {row.phi}°</td></tr>)}</tbody></table>
    </div>
    <div className="emi-angular-map"><h3>Angular field map · {(rows[frequencyIndex].frequency / 1e6).toFixed(3)} MHz</h3><svg viewBox="0 0 500 210" role="img" aria-label="Theta phi electric field map, 40 dB below peak to peak"><text x="48" y="15">θ ↓ / φ → · blue: ≤ peak − 40 dB · amber: peak</text>{angular}<text x="40" y="34" textAnchor="end">{field.theta_deg[0]}°</text><text x="40" y="165" textAnchor="end">{field.theta_deg[nt - 1]}°</text><text x="48" y="184">{field.phi_deg[0]}°</text><text x="472" y="184" textAnchor="end">{field.phi_deg[np - 1]}°</text><text x="250" y="205" textAnchor="middle">Hover cells for sampled field values</text></svg></div>
  </>;
}
