// SPDX-License-Identifier: Apache-2.0
import './ResultValueScale.css';
export type ResultValueScaleProps = { label: string; unit: string; minimum: number; maximum: number; gradient?: string; scope?: string };
export default function ResultValueScale({label, unit, minimum, maximum, gradient, scope}: ResultValueScaleProps) {
  if (!Number.isFinite(minimum) || !Number.isFinite(maximum) || maximum < minimum) return null;
  const format = (n: number) => n === 0 ? '0' : Math.abs(n) < .001 || Math.abs(n) >= 1e5 ? n.toExponential(3) : Number(n.toPrecision(5)).toString();
  const ticks = minimum === maximum ? [minimum] : [minimum, minimum + (maximum-minimum)/2, maximum];
  return <section className="result-value-scale" aria-label={`${label} value scale`} data-scale-minimum={minimum} data-scale-maximum={maximum}>
    <header><strong>{label}</strong>{unit && <span>{unit}</span>}</header>
    {gradient && <div className="result-value-scale__bar" style={{background:gradient}} aria-hidden="true"/>}
    <div className="result-value-scale__ticks">{ticks.map((n,i)=><span key={i}>{format(n)}{unit ? ` ${unit}` : ''}</span>)}</div>
    {scope && <small>{scope}</small>}
  </section>;
}
