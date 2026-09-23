import type { ScalarSample } from "./analysisResults";

export type ViewportResultField = {
  key: string;
  label: string;
  unit: string;
};

export const viewportResultField = (mode: string): ViewportResultField => {
  switch (mode) {
    case "voltage": return { key: "voltage_v", label: "Absolute voltage", unit: "V" };
    case "voltage_drop": return { key: "voltage_drop_v", label: "Voltage drop", unit: "V" };
    case "current": return { key: "current_a", label: "Current", unit: "A" };
    case "current_density": return { key: "current_density_a_mm2", label: "Current density", unit: "A/mm2" };
    case "power_loss": return { key: "power_loss_w", label: "Copper power loss", unit: "W" };
    case "via_stress": return { key: "via_current_density_a_mm2", label: "Via current density", unit: "A/mm2" };
    case "impedance": return { key: "operating_point_impedance_ohm", label: "PI impedance |V/I|", unit: "ohm" };
    default: return { key: mode, label: mode, unit: "" };
  }
};

const sameText = (left: string | undefined, right: string | undefined) => !left || !right || left === right;

/**
 * PI impedance is a local ratio only where the solver published co-located
 * voltage and current samples. This deliberately does not interpolate across
 * nets, layers, or unmatched elements because that would fabricate a field.
 */
export function piImpedanceSamples(voltageSamples: ScalarSample[], currentSamples: ScalarSample[]): ScalarSample[] {
  if (!voltageSamples.length || !currentSamples.length) return [];
  const indexed = new Map<string, ScalarSample[]>();
  currentSamples.forEach(sample => {
    if (!Number.isFinite(sample.value) || Math.abs(sample.value) < 1e-18) return;
    const key = `${sample.x_mm.toFixed(6)}:${sample.y_mm.toFixed(6)}`;
    indexed.set(key, [...(indexed.get(key) ?? []), sample]);
  });
  return voltageSamples.flatMap(voltage => {
    if (!Number.isFinite(voltage.value)) return [];
    const key = `${voltage.x_mm.toFixed(6)}:${voltage.y_mm.toFixed(6)}`;
    const current = (indexed.get(key) ?? []).find(candidate =>
      sameText(candidate.net, voltage.net)
      && sameText(candidate.layer, voltage.layer)
      && sameText(candidate.element_id, voltage.element_id),
    );
    if (!current) return [];
    return [{ ...voltage, value: Math.abs(voltage.value / current.value), kind: "pi_v_over_i" }];
  });
}

export function formatViewportAxisTick(valueMm: number): string {
  const magnitude = Math.abs(valueMm);
  if (magnitude >= 100 || Number.isInteger(valueMm)) return `${valueMm.toFixed(0)} mm`;
  if (magnitude >= 10) return `${valueMm.toFixed(1)} mm`;
  return `${valueMm.toFixed(2)} mm`;
}

export function formatViewportResultTick(value: number, unit: string): string {
  const magnitude = Math.abs(value);
  const rendered = magnitude > 0 && (magnitude < 1e-4 || magnitude >= 1e5)
    ? value.toExponential(3)
    : value.toFixed(magnitude >= 100 ? 1 : magnitude >= 1 ? 3 : 5);
  return unit ? `${rendered} ${unit}` : rendered;
}

type SpatialSample = {
  x_mm: number;
  y_mm: number;
  layer?: string;
  net?: string;
  value?: number;
  magnitude?: number;
};

const sampleStrength = (sample: SpatialSample) => Math.abs(Number(sample.magnitude ?? sample.value ?? 0));

const numericRange = (values: number[]) => values.reduce(
  (range, value) => ({ minimum: Math.min(range.minimum, value), maximum: Math.max(range.maximum, value) }),
  { minimum: Number.POSITIVE_INFINITY, maximum: Number.NEGATIVE_INFINITY },
);

/**
 * Reduces dense solver output without exposing its row/element ordering in the
 * viewport. One strongest sample is retained per physical layer/net/grid bin.
 */
export function spatiallyThinSamples<T extends SpatialSample>(samples: T[], limit: number): T[] {
  const maximum = Math.max(1, Math.floor(limit));
  if (samples.length <= maximum) return samples;
  const finite = samples.filter(sample => Number.isFinite(sample.x_mm) && Number.isFinite(sample.y_mm));
  if (finite.length <= maximum) return finite;
  const xs = finite.map(sample => sample.x_mm);
  const ys = finite.map(sample => sample.y_mm);
  const xRange = numericRange(xs);
  const yRange = numericRange(ys);
  const width = xRange.maximum - xRange.minimum;
  const height = yRange.maximum - yRange.minimum;
  const minimumX = xRange.minimum;
  const minimumY = yRange.minimum;
  let binSize = Math.max(Math.sqrt(Math.max(width * height, 1e-6) / maximum), 1e-5);
  let retained = finite;
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const bins = new Map<string, T>();
    finite.forEach(sample => {
      const key = [
        sample.layer ?? "",
        sample.net ?? "",
        Math.floor((sample.x_mm - minimumX) / binSize),
        Math.floor((sample.y_mm - minimumY) / binSize),
      ].join("\u0000");
      const current = bins.get(key);
      if (!current || sampleStrength(sample) > sampleStrength(current)) bins.set(key, sample);
    });
    retained = [...bins.values()];
    if (retained.length <= maximum) break;
    binSize *= Math.max(1.15, Math.sqrt(retained.length / maximum) * 1.04);
  }
  if (retained.length <= maximum) return retained;
  const step = retained.length / maximum;
  return Array.from({ length: maximum }, (_, index) => retained[Math.floor(index * step)]);
}
