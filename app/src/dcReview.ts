import type { ScalarSample, SolverResultBundle } from "./analysisResults";
import { resultSolvedForPresentation } from "./resultAdmission";

export type DcLimitReview = {
  value: number | null;
  limit: number | null;
  state: "violated" | "within" | "unset" | "unavailable";
};

export type DcReview = {
  sourceVoltageV: number | null;
  lowestVoltage: ScalarSample | null;
  highestDrop: ScalarSample | null;
  highestDensity: ScalarSample | null;
  highestViaDensity: ScalarSample | null;
  drop: DcLimitReview;
  density: DcLimitReview;
};

const finite = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

const positiveLimit = (value: number | null): number | null =>
  value !== null && Number.isFinite(value) && value > 0 ? value : null;

const scoped = (samples: ScalarSample[], net: string | null, layers: string[]): ScalarSample[] =>
  samples.filter(sample => Number.isFinite(sample.value)
    && (!net || sample.net === net)
    && (!layers.length || layers.includes(sample.layer ?? "")));

const extreme = (samples: ScalarSample[], higher: boolean): ScalarSample | null =>
  samples.reduce<ScalarSample | null>((best, sample) =>
    !best || (higher ? sample.value > best.value : sample.value < best.value) ? sample : best, null);

const compare = (value: number | null, limit: number | null): DcLimitReview => ({
  value,
  limit,
  state: value === null ? "unavailable" : limit === null ? "unset" : value > limit ? "violated" : "within",
});

/** UI review of original DC samples. A sample extremum is not a load-terminal measurement. */
export function buildDcReview(
  result: SolverResultBundle | null,
  net: string | null,
  layers: string[],
  dropLimitMv: number | null,
  densityLimitAMm2: number | null,
): DcReview | null {
  if (!resultSolvedForPresentation(result) || result?.mode !== "dc") return null;
  const lowestVoltage = extreme(scoped(result.scalar_fields.voltage_v, net, layers), false);
  const highestDrop = extreme(scoped(result.scalar_fields.voltage_drop_v, net, layers), true);
  const highestDensity = extreme(scoped(result.scalar_fields.current_density_a_mm2, net, layers), true);
  const highestViaDensity = extreme(scoped(result.scalar_fields.via_current_density_a_mm2, net, layers), true);
  const sourceVoltageV = finite(result.summary.source_voltage_v);
  const dropLimit = positiveLimit(dropLimitMv);
  return {
    sourceVoltageV,
    lowestVoltage,
    highestDrop,
    highestDensity,
    highestViaDensity,
    drop: compare(highestDrop?.value ?? null, dropLimit === null ? null : dropLimit / 1000),
    density: compare(highestDensity?.value ?? null, positiveLimit(densityLimitAMm2)),
  };
}
