export type TransientWaveformKind = "constant" | "step" | "pulse" | "piecewise_linear";

export type TransientWaveformDefinition = {
  kind: TransientWaveformKind;
  highValue: string | number;
  initialValue?: string | number;
  delayS?: string | number;
  riseS?: string | number;
  widthS?: string | number;
  fallS?: string | number;
  periodS?: string | number;
  points?: string;
};

const SPICE_SCALES: Record<string, number> = {
  "": 1,
  f: 1e-15,
  p: 1e-12,
  n: 1e-9,
  u: 1e-6,
  m: 1e-3,
  k: 1e3,
  meg: 1e6,
  g: 1e9,
  t: 1e12,
};

/** Parse a scalar using SPICE engineering suffixes. `m` is milli; mega is `meg`. */
export function parseSpiceNumber(value: string | number, label = "value"): number {
  if (typeof value === "number") {
    if (Number.isFinite(value)) return value;
    throw new Error(`${label} must be finite.`);
  }
  const normalized = value.trim().replace(/[\u00b5\u03bc]/g, "u");
  if (!normalized) throw new Error(`${label} is required.`);
  const match = normalized.match(/^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\s*(meg|[fpnumkgt]?)(?:(?:s|sec|v|a|ohm|hz|f|h|w|r|\u03a9))?$/i);
  if (!match) throw new Error(`${label} must be numeric; engineering suffixes such as ns, us, ms, k, and meg are accepted.`);
  const scale = SPICE_SCALES[match[2].toLowerCase()];
  const result = Number(match[1]) * scale;
  if (!Number.isFinite(result)) throw new Error(`${label} is outside the supported numeric range.`);
  return result;
}

export function tryParseSpiceNumber(value: string | number, fallback = 0): number {
  try { return parseSpiceNumber(value); } catch { return fallback; }
}

export function formatEngineering(value: number, unit = ""): string {
  if (!Number.isFinite(value)) return `--${unit}`;
  if (value === 0) return `0${unit}`;
  const magnitude = Math.abs(value);
  const scales: [number, string][] = [
    [1e9, "G"], [1e6, "meg"], [1e3, "k"], [1, ""], [1e-3, "m"],
    [1e-6, "u"], [1e-9, "n"], [1e-12, "p"], [1e-15, "f"],
  ];
  const [scale, suffix] = scales.find(([candidate]) => magnitude >= candidate) ?? scales[scales.length - 1];
  return `${Number((value / scale).toPrecision(4))}${suffix}${unit}`;
}

export function parsePwlPoints(value: string): [number, number][] {
  const points = value.replace(/;/g, ",").split(",").map(token => token.trim()).filter(Boolean).map((token, index) => {
    const separator = token.indexOf(":");
    if (separator < 0) throw new Error(`PWL point ${index + 1} must use time:value syntax.`);
    return [
      parseSpiceNumber(token.slice(0, separator), `PWL time ${index + 1}`),
      parseSpiceNumber(token.slice(separator + 1), `PWL value ${index + 1}`),
    ] as [number, number];
  }).sort((left, right) => left[0] - right[0]);
  if (points.length < 2) throw new Error("PWL requires at least two time:value points.");
  if (points.some((point, index) => index > 0 && point[0] <= points[index - 1][0])) throw new Error("PWL times must be strictly increasing.");
  return points;
}

export function validateWaveform(definition: TransientWaveformDefinition): string[] {
  const issues: string[] = [];
  try {
    parseSpiceNumber(definition.highValue, "Final/high value");
    if (definition.kind !== "constant") parseSpiceNumber(definition.initialValue ?? 0, "Initial/low value");
    if (definition.kind === "piecewise_linear") parsePwlPoints(definition.points ?? "");
    if (definition.kind === "step" || definition.kind === "pulse") {
      const delay = parseSpiceNumber(definition.delayS ?? 0, "Delay");
      const rise = parseSpiceNumber(definition.riseS ?? 0, "Rise time");
      if (delay < 0 || rise < 0) issues.push("Delay and rise time cannot be negative.");
      if (definition.kind === "pulse") {
        const width = parseSpiceNumber(definition.widthS ?? 0, "On time");
        const fall = parseSpiceNumber(definition.fallS ?? 0, "Fall time");
        const period = parseSpiceNumber(definition.periodS ?? 0, "Period");
        if (width < 0 || fall < 0 || period <= 0) issues.push("Pulse on-time and fall time cannot be negative; period must be positive.");
        if (period < rise + width + fall) issues.push("Pulse period must contain rise, on-time, and fall intervals.");
      }
    }
  } catch (error) { issues.push(error instanceof Error ? error.message : "Invalid waveform."); }
  return issues;
}

export function waveformValue(definition: TransientWaveformDefinition, timeS: number): number {
  const high = parseSpiceNumber(definition.highValue, "Final/high value");
  if (definition.kind === "constant") return high;
  if (definition.kind === "piecewise_linear") {
    const points = parsePwlPoints(definition.points ?? "");
    if (timeS <= points[0][0]) return points[0][1];
    if (timeS >= points[points.length - 1][0]) return points[points.length - 1][1];
    const rightIndex = points.findIndex(point => point[0] >= timeS);
    const left = points[rightIndex - 1];
    const right = points[rightIndex];
    return left[1] + (right[1] - left[1]) * (timeS - left[0]) / (right[0] - left[0]);
  }
  const low = parseSpiceNumber(definition.initialValue ?? 0, "Initial/low value");
  const delay = Math.max(0, parseSpiceNumber(definition.delayS ?? 0, "Delay"));
  const rise = Math.max(0, parseSpiceNumber(definition.riseS ?? 0, "Rise time"));
  if (timeS < delay) return low;
  if (definition.kind === "step") {
    if (rise > 0 && timeS < delay + rise) return low + (high - low) * (timeS - delay) / rise;
    return high;
  }
  const width = Math.max(0, parseSpiceNumber(definition.widthS ?? 0, "On time"));
  const fall = Math.max(0, parseSpiceNumber(definition.fallS ?? 0, "Fall time"));
  const period = parseSpiceNumber(definition.periodS ?? 0, "Period");
  if (period <= 0 || period < rise + width + fall) throw new Error("Pulse period must contain rise, on-time, and fall intervals.");
  const phase = (timeS - delay) % period;
  if (rise > 0 && phase < rise) return low + (high - low) * phase / rise;
  if (phase < rise + width) return high;
  if (fall > 0 && phase < rise + width + fall) return high + (low - high) * (phase - rise - width) / fall;
  return low;
}

export function sampleWaveform(definition: TransientWaveformDefinition, stopTimeS: number, count = 96): { timeS: number; value: number }[] {
  const stop = Math.max(stopTimeS, 1e-15);
  return Array.from({ length: Math.max(2, count) }, (_, index) => {
    const timeS = stop * index / Math.max(1, count - 1);
    return { timeS, value: waveformValue(definition, timeS) };
  });
}
