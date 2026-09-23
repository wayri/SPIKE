import { Activity, Minus, Repeat2, Spline, Waves } from "lucide-react";
import {
  formatEngineering, sampleWaveform, TransientWaveformDefinition, TransientWaveformKind,
  tryParseSpiceNumber, validateWaveform,
} from "./transientWaveform";
import { numericExtent } from "./numericRange";

export type EditableTerminalWaveform = {
  profile: TransientWaveformKind;
  value: string;
  profileInitial: string;
  profileDelayS: string;
  profileRiseS: string;
  profileWidthS: string;
  profileFallS: string;
  profilePeriodS: string;
  profileData: string;
};

const waveformDefinition = (value: EditableTerminalWaveform): TransientWaveformDefinition => ({
  kind: value.profile,
  highValue: value.value,
  initialValue: value.profileInitial,
  delayS: value.profileDelayS,
  riseS: value.profileRiseS,
  widthS: value.profileWidthS,
  fallS: value.profileFallS,
  periodS: value.profilePeriodS,
  points: value.profileData,
});

function WaveformPlot({ value, stopTimeS, unit }: { value: EditableTerminalWaveform; stopTimeS: string; unit: string }) {
  const definition = waveformDefinition(value);
  const stop = Math.max(tryParseSpiceNumber(stopTimeS, 1e-3), 1e-15);
  const issues = validateWaveform(definition);
  let samples: { timeS: number; value: number }[] = [];
  if (!issues.length) samples = sampleWaveform(definition, stop);
  const values = samples.map(sample => sample.value);
  const extent = numericExtent(values, 0, 1);
  const min = extent.minimum;
  const max = extent.maximum;
  const span = Math.max(max - min, Math.abs(max) * .05, 1e-12);
  const path = samples.map((sample, index) => {
    const x = 8 + 224 * sample.timeS / stop;
    const y = 60 - 48 * (sample.value - min) / span;
    return `${index ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(" ");
  return <div className={`waveform-plot ${issues.length ? "invalid" : ""}`}>
    <svg viewBox="0 0 240 70" role="img" aria-label={`${value.profile} waveform preview`}>
      <path className="wave-grid" d="M8 12H232 M8 36H232 M8 60H232 M8 12V60 M120 12V60 M232 12V60" />
      {!issues.length && <path className="wave-line" d={path} />}
    </svg>
    <span className="wave-y-max">{issues.length ? "INVALID" : formatEngineering(max, unit)}</span>
    <span className="wave-y-min">{issues.length ? issues[0] : formatEngineering(min, unit)}</span>
    <span className="wave-time">0 <b>{formatEngineering(stop, "s")}</b></span>
  </div>;
}

const modes: { id: TransientWaveformKind; label: string; icon: typeof Activity }[] = [
  { id: "constant", label: "DC", icon: Minus },
  { id: "step", label: "Step", icon: Activity },
  { id: "pulse", label: "Pulse", icon: Waves },
  { id: "piecewise_linear", label: "PWL", icon: Spline },
];

export default function TransientWaveformEditor({ value, stopTimeS, quantity, onChange }: {
  value: EditableTerminalWaveform;
  stopTimeS: string;
  quantity: "voltage" | "current";
  onChange: (patch: Partial<EditableTerminalWaveform>) => void;
}) {
  const unit = quantity === "voltage" ? "V" : "A";
  const setPreset = (preset: "load_step" | "short_pulse" | "long_pulse") => {
    if (preset === "load_step") onChange({ profile: "step", profileInitial: "0", profileDelayS: "10us", profileRiseS: "100ns" });
    else if (preset === "short_pulse") onChange({ profile: "pulse", profileInitial: "0", profileDelayS: "10us", profileRiseS: "100ns", profileWidthS: "10us", profileFallS: "100ns", profilePeriodS: "25us" });
    else onChange({ profile: "pulse", profileInitial: "0", profileDelayS: "100us", profileRiseS: "1us", profileWidthS: "1ms", profileFallS: "1us", profilePeriodS: "2ms" });
  };
  return <div className="waveform-editor">
    <div className="waveform-editor-heading"><span>EXCITATION</span><code>{value.profile === "pulse" ? "PULSE(V1 V2 TD TR TF PW PER)" : value.profile === "step" ? "STEP(V1 V2 TD TR)" : value.profile === "piecewise_linear" ? "PWL(T1 V1 ...)" : "DC(V)"}</code></div>
    <div className="waveform-mode" role="tablist" aria-label="Terminal waveform type">{modes.map(mode => {
      const Icon = mode.icon;
      return <button type="button" role="tab" aria-selected={value.profile === mode.id} className={value.profile === mode.id ? "selected" : ""} key={mode.id} onClick={() => onChange({ profile: mode.id })}><Icon size={13} />{mode.label}</button>;
    })}</div>
    <div className="waveform-workspace">
      <WaveformPlot value={value} stopTimeS={stopTimeS} unit={unit} />
      <div className="waveform-fields">
        <label>{value.profile === "pulse" ? "High" : value.profile === "constant" ? "Value" : "Final"} ({unit})<input value={value.value} onChange={event => onChange({ value: event.target.value })} /></label>
        {value.profile !== "constant" && value.profile !== "piecewise_linear" && <label>Initial / low ({unit})<input value={value.profileInitial} onChange={event => onChange({ profileInitial: event.target.value })} /></label>}
        {(value.profile === "step" || value.profile === "pulse") && <><label>Delay TD<input value={value.profileDelayS} onChange={event => onChange({ profileDelayS: event.target.value })} placeholder="10us" /></label><label>Rise TR<input value={value.profileRiseS} onChange={event => onChange({ profileRiseS: event.target.value })} placeholder="100ns" /></label></>}
        {value.profile === "pulse" && <><label>On time PW<input value={value.profileWidthS} onChange={event => onChange({ profileWidthS: event.target.value })} placeholder="10us" /></label><label>Fall TF<input value={value.profileFallS} onChange={event => onChange({ profileFallS: event.target.value })} placeholder="100ns" /></label><label>Period PER<input value={value.profilePeriodS} onChange={event => onChange({ profilePeriodS: event.target.value })} placeholder="25us" /></label></>}
        {value.profile === "piecewise_linear" && <label className="pwl-points">Time:value points<input value={value.profileData} onChange={event => onChange({ profileData: event.target.value })} placeholder="0:0, 10us:0, 11us:2, 1ms:2" /></label>}
      </div>
    </div>
    <div className="waveform-presets"><span>Presets</span><button type="button" onClick={() => setPreset("load_step")}><Activity size={12} /> Load step</button><button type="button" onClick={() => setPreset("short_pulse")}><Waves size={12} /> Short pulse</button><button type="button" onClick={() => setPreset("long_pulse")}><Repeat2 size={12} /> Long pulse</button></div>
  </div>;
}
