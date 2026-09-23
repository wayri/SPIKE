import type { SolverResultBundle } from "./analysisResults";
import { absoluteMaximum, numericMaximum, numericMinimum } from "./numericRange";

export type CopperFusingSettings = {
  ambientTemperatureC: number;
  faultDurationS: number;
};

export type FieldExtrema = {
  key: string;
  label: string;
  unit: string;
  count: number;
  minimum: number;
  mean: number;
  percentile95: number;
  maximum: number;
};

export type StressedVia = {
  elementId: string;
  net: string;
  layer: string;
  currentDensityAMm2: number;
  designLimitUtilization: number | null;
  fusingUtilization: number | null;
  status: "fusing" | "limit" | "watch" | "ok";
};

export type ResultEngineeringAnalytics = {
  fields: FieldExtrema[];
  probeSummary: {
    total: number;
    mapped: number;
    minimumVoltageV: number | null;
    maximumVoltageV: number | null;
    maximumDropV: number | null;
    maximumCurrentA: number | null;
    maximumCurrentDensityAMm2: number | null;
  };
  fusing: {
    modelStatus: "approximate" | "invalid_input";
    ambientTemperatureC: number;
    faultDurationS: number;
    currentDensityThresholdAMm2: number | null;
    maximumUtilization: number | null;
  };
  stressedVias: StressedVia[];
};

export const DEFAULT_COPPER_FUSING_SETTINGS: CopperFusingSettings = {
  ambientTemperatureC: 25,
  faultDurationS: 1,
};

const FIELD_DEFINITIONS: Record<string, { label: string; unit: string }> = {
  voltage_v: { label: "Absolute voltage", unit: "V" },
  voltage_drop_v: { label: "Voltage drop", unit: "V" },
  current_a: { label: "Current", unit: "A" },
  operating_point_impedance_ohm: { label: "Operating-point V/I", unit: "ohm" },
  current_density_a_mm2: { label: "Current density", unit: "A/mm2" },
  power_loss_w: { label: "Copper power loss", unit: "W" },
  via_current_density_a_mm2: { label: "Via current density", unit: "A/mm2" },
};

const finiteValues = (values: Array<number | undefined>) => values.filter((value): value is number => Number.isFinite(value));

const percentile = (sorted: number[], ratio: number) => {
  if (!sorted.length) return 0;
  const position = (sorted.length - 1) * ratio;
  const lower = Math.floor(position);
  const fraction = position - lower;
  return sorted[lower + 1] === undefined
    ? sorted[lower]
    : sorted[lower] + fraction * (sorted[lower + 1] - sorted[lower]);
};

export function resultFieldExtrema(result: SolverResultBundle | null): FieldExtrema[] {
  if (!result) return [];
  return Object.entries(result.scalar_fields).flatMap(([key, samples]) => {
    const values = samples.map(sample => sample.value).filter(Number.isFinite).sort((left, right) => left - right);
    if (!values.length) return [];
    const definition = FIELD_DEFINITIONS[key] ?? { label: key.replace(/_/g, " "), unit: "" };
    return [{
      key,
      label: definition.label,
      unit: definition.unit,
      count: values.length,
      minimum: values[0],
      mean: values.reduce((sum, value) => sum + value, 0) / values.length,
      percentile95: percentile(values, 0.95),
      maximum: values[values.length - 1],
    }];
  });
}

/**
 * Short-duration adiabatic copper fusing screen using Onderdonk's equation.
 * This is not a continuous-current, PCB temperature-rise, or thermal qualification model.
 */
export function copperFusingCurrentDensityAMm2(settings: CopperFusingSettings): number | null {
  const ambient = Number(settings.ambientTemperatureC);
  const duration = Number(settings.faultDurationS);
  const copperMeltingTemperatureC = 1084.62;
  if (!Number.isFinite(ambient) || !Number.isFinite(duration) || ambient <= -233 || ambient >= copperMeltingTemperatureC || duration <= 0) return null;
  const circularMilsPerMm2 = 1 / (Math.PI / 4 * 0.0254 * 0.0254);
  const temperatureTerm = Math.log10((copperMeltingTemperatureC - ambient) / (233 + ambient) + 1);
  if (!Number.isFinite(temperatureTerm) || temperatureTerm <= 0) return null;
  return circularMilsPerMm2 * Math.sqrt(temperatureTerm / (34 * duration));
}

export function buildResultEngineeringAnalytics(
  result: SolverResultBundle | null,
  designDensityLimitAMm2: number | null,
  settings: CopperFusingSettings,
): ResultEngineeringAnalytics {
  const fusingThreshold = copperFusingCurrentDensityAMm2(settings);
  const limit = designDensityLimitAMm2 !== null && Number.isFinite(designDensityLimitAMm2) && designDensityLimitAMm2 > 0
    ? designDensityLimitAMm2
    : null;
  const probeVoltages = finiteValues(result?.probes.map(probe => probe.voltage_v) ?? []);
  const probeDrops = finiteValues(result?.probes.map(probe => probe.voltage_drop_v) ?? []);
  const probeCurrents = finiteValues(result?.probes.map(probe => probe.peak_adjacent_current_a) ?? []);
  const probeDensities = finiteValues(result?.probes.map(probe => probe.peak_adjacent_current_density_a_mm2) ?? []);
  const viaByElement = new Map<string, StressedVia>();
  (result?.scalar_fields.via_current_density_a_mm2 ?? []).forEach((sample, index) => {
    if (!Number.isFinite(sample.value)) return;
    const elementId = sample.element_id || `via-sample-${index + 1}`;
    const density = Math.abs(sample.value);
    const designUtilization = limit === null ? null : density / limit;
    const fusingUtilization = fusingThreshold === null ? null : density / fusingThreshold;
    const status: StressedVia["status"] = fusingUtilization !== null && fusingUtilization >= 1 ? "fusing"
      : designUtilization !== null && designUtilization >= 1 ? "limit"
        : (designUtilization !== null && designUtilization >= 0.8) || (fusingUtilization !== null && fusingUtilization >= 0.5) ? "watch"
          : "ok";
    const candidate: StressedVia = {
      elementId,
      net: sample.net ?? "-",
      layer: sample.layer ?? "through",
      currentDensityAMm2: density,
      designLimitUtilization: designUtilization,
      fusingUtilization,
      status,
    };
    const previous = viaByElement.get(elementId);
    if (!previous || density > previous.currentDensityAMm2) viaByElement.set(elementId, candidate);
  });
  const stressedVias = [...viaByElement.values()].sort((left, right) => right.currentDensityAMm2 - left.currentDensityAMm2);
  const densityValues = finiteValues(result?.scalar_fields.current_density_a_mm2.map(sample => Math.abs(sample.value)) ?? []);
  const viaDensityValues = stressedVias.map(via => via.currentDensityAMm2);
  const maximumDensity = [...densityValues, ...viaDensityValues].reduce<number | null>((maximum, value) => maximum === null ? value : Math.max(maximum, value), null);
  return {
    fields: resultFieldExtrema(result),
    probeSummary: {
      total: result?.probes.length ?? 0,
      mapped: result?.probes.filter(probe => probe.status === "mapped").length ?? 0,
      minimumVoltageV: probeVoltages.length ? numericMinimum(probeVoltages) : null,
      maximumVoltageV: probeVoltages.length ? numericMaximum(probeVoltages) : null,
      maximumDropV: probeDrops.length ? absoluteMaximum(probeDrops) : null,
      maximumCurrentA: probeCurrents.length ? absoluteMaximum(probeCurrents) : null,
      maximumCurrentDensityAMm2: probeDensities.length ? absoluteMaximum(probeDensities) : null,
    },
    fusing: {
      modelStatus: fusingThreshold === null ? "invalid_input" : "approximate",
      ambientTemperatureC: settings.ambientTemperatureC,
      faultDurationS: settings.faultDurationS,
      currentDensityThresholdAMm2: fusingThreshold,
      maximumUtilization: fusingThreshold !== null && maximumDensity !== null ? maximumDensity / fusingThreshold : null,
    },
    stressedVias,
  };
}
