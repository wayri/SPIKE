// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
export type SiChartPoint = Readonly<{ x: number; y: number }>;
export type SiChartSeries = Readonly<{
  id: string;
  label: string;
  points: readonly SiChartPoint[];
}>;

export type SiChannelCharts = Readonly<{
  portOrder: readonly string[];
  sMagnitudeDb: readonly SiChartSeries[];
  sPhaseDeg: readonly SiChartSeries[];
  reflectionMagnitude: readonly SiChartSeries[];
  vswr: readonly SiChartSeries[];
  tdrReflection: SiChartSeries;
  tdrImpedanceOhm: SiChartSeries;
  tdtNormalizedStep: SiChartSeries;
  nextDb: SiChartSeries | null;
  fextDb: SiChartSeries | null;
  crosstalkLinear: readonly SiChartSeries[];
  crosstalkVoltage: readonly SiChartSeries[];
  loadedCrosstalkDb: readonly SiChartSeries[];
  loadedCrosstalkLinear: readonly SiChartSeries[];
  crosstalkTimeStatus: string;
  impedanceReal: readonly SiChartSeries[];
  impedanceImag: readonly SiChartSeries[];
  impedanceMagnitude: readonly SiChartSeries[];
  impedanceCandidates: readonly Readonly<{ port: string; kind: string; frequencyHz: number | null; bracketHz: readonly number[] }>[];
  impedanceTermination: string;
  impedanceCandidateTruncated: boolean;
  eye: readonly SiChartSeries[];
  eyeSamplesPerUi: number | null;
  pam4EyeHeights: readonly SiChartSeries[];
  pam4BerProxies: readonly SiChartSeries[];
  productionQualified: false;
  complianceStatus: string;
  mixedModeMetrics: Readonly<Record<string, number>>;
}>;

export type ProjectedSiSeries = Readonly<{
  id: string;
  label: string;
  points: string;
  source: readonly SiChartPoint[];
}>;

const object = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};

const objects = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value)
    ? value.filter(item => item !== null && typeof item === "object" && !Array.isArray(item)) as Record<string, unknown>[]
    : [];

const finite = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

const finiteArray = (value: unknown): number[] => Array.isArray(value)
  ? value.map(finite).filter((item): item is number => item !== null)
  : [];

const pointSeries = (
  id: string,
  label: string,
  raw: unknown,
  xKey: string,
  yKey: string,
): SiChartSeries => ({
  id,
  label,
  points: objects(raw).flatMap(item => {
    const x = finite(item[xKey]);
    const y = finite(item[yKey]);
    return x === null || y === null ? [] : [{ x, y }];
  }),
});

const emptySeries = (id: string, label: string): SiChartSeries => ({ id, label, points: [] });

/** Preserve the worker's per-port reflection and finite/infinite VSWR decisions. */
export function reflectionMetrics(network: Record<string, unknown>): { reflectionMagnitude: SiChartSeries[]; vswr: SiChartSeries[] } {
  const reflectionMagnitude: SiChartSeries[] = [];
  const vswr: SiChartSeries[] = [];
  for (const port of objects(object(network.reflection_vswr).ports)) {
    const index = finite(port.port);
    if (index === null || !Number.isInteger(index) || index < 0) continue;
    const name = `S${index + 1}${index + 1}`;
    const reflection = pointSeries(`${name}-reflection`, `${name} |rho|`, port.trace, "frequency_hz", "reflection_magnitude");
    if (reflection.points.length) reflectionMagnitude.push(reflection);
    // The worker owns status classification; nulls split finite display runs.
    let segment: SiChartPoint[] = [];
    let segmentNumber = 0;
    const flush = () => {
      if (segment.length) vswr.push({ id: `${name}-vswr-${segmentNumber++}`, label: `${name} VSWR`, points: segment });
      segment = [];
    };
    for (const row of objects(port.trace)) {
      const frequency = finite(row.frequency_hz);
      const value = finite(row.vswr);
      if (frequency === null || row.vswr_status !== "finite" || value === null || value < 1) { flush(); continue; }
      segment.push({ x: frequency, y: value });
    }
    flush();
  }
  return { reflectionMagnitude, vswr };
}

/** Split at masked poles, including invalid samples omitted by worker decimation. */
function impedanceSegments(port: Record<string, unknown>, key: string): SiChartSeries[] {
  const number = finite(port.port);
  if (number === null || !Number.isInteger(number) || number < 0) return [];
  const invalid = objects(port.invalid_samples).flatMap(row => {
    const frequency = finite(row.frequency_hz);
    return frequency === null ? [] : [frequency];
  }).sort((a, b) => a - b);
  const segments: SiChartSeries[] = [];
  let points: SiChartPoint[] = [];
  let previous = -Infinity;
  let invalidIndex = 0;
  const flush = () => {
    if (points.length) segments.push({ id: `z-${number}-${key}-${segments.length}`, label: `Port ${number + 1}`, points });
    points = [];
  };
  for (const row of objects(port.trace)) {
    const x = finite(row.frequency_hz);
    const y = finite(row[key]);
    if (x === null || y === null || row.status !== "finite") { flush(); continue; }
    let crossedGap = false;
    while (invalidIndex < invalid.length && invalid[invalidIndex] <= x) {
      if (invalid[invalidIndex] > previous) crossedGap = true;
      invalidIndex += 1;
    }
    if (crossedGap || row.gap_before === true || x <= previous) flush();
    points.push({ x, y });
    previous = x;
  }
  flush();
  return segments;
}

/**
 * Converts the worker's SI result into display-only series without sorting,
 * reversing, transposing, or changing port meaning. The worker owns the
 * chronological/frequency ordering and the UI must preserve it exactly.
 */
export function normalizeSiChannelResult(value: unknown): SiChannelCharts {
  const result = object(value);
  if (result.contract !== "spike/si-channel-result/v1") {
    throw new Error("Expected a spike/si-channel-result/v1 result.");
  }
  if (result.status !== "completed") throw new Error("The SI channel result is not completed.");
  if (result.production_qualified !== false) {
    throw new Error("The bounded geometry-derived SI result must remain explicitly non-production-qualified.");
  }

  const network = object(result.network);
  const impedance = object(network.impedance_response);
  const impedancePorts = impedance.contract === "spike/si-driving-point-impedance/v1" && impedance.status === "completed"
    ? objects(impedance.ports) : [];
  const impedanceReal = impedancePorts.flatMap(port => impedanceSegments(port, "real_ohm"));
  const impedanceImag = impedancePorts.flatMap(port => impedanceSegments(port, "imag_ohm"));
  const impedanceMagnitude = impedancePorts.flatMap(port => impedanceSegments(port, "magnitude_ohm"));
  const impedanceCandidates = impedancePorts.flatMap(port => objects(port.sampled_candidates).slice(0, 128).flatMap(candidate => {
    const number = finite(port.port);
    if (number === null || !Number.isInteger(number) || number < 0 || typeof candidate.kind !== "string") return [];
    return [{ port: `Port ${number + 1}`, kind: candidate.kind, frequencyHz: finite(candidate.frequency_hz), bracketHz: finiteArray(candidate.bracket_hz) }];
  }));
  const traces = object(network.traces);
  const traceNames = Object.keys(traces).filter(name => /^S\d+\d+$/.test(name));
  const sMagnitudeDb = traceNames.map(name =>
    pointSeries(`${name}-magnitude-db`, name, traces[name], "frequency_hz", "magnitude_db"),
  );
  const sPhaseDeg = traceNames.map(name =>
    pointSeries(`${name}-phase-deg`, name, traces[name], "frequency_hz", "phase_deg"),
  );
  const { reflectionMagnitude, vswr } = reflectionMetrics(network);

  const time = object(result.time_domain);
  const tdrReflection = pointSeries("tdr-reflection", "Reflection coefficient", time.tdr, "time_s", "reflection");
  const tdrImpedanceOhm = pointSeries("tdr-impedance", "Impedance", time.tdr, "time_s", "impedance_ohm");
  const tdtNormalizedStep = pointSeries("tdt-step", "Normalized transmitted step", time.tdt, "time_s", "normalized_step");

  const crosstalk = object(result.crosstalk);
  const next = object(crosstalk.next);
  const fext = object(crosstalk.fext);
  const mapping = object(crosstalk.mapping);
  const nextLabel = typeof mapping.next === "string" ? `NEXT · ${mapping.next}` : "NEXT · worker mapping unavailable";
  const fextLabel = typeof mapping.fext === "string" ? `FEXT · ${mapping.fext}` : "FEXT · worker mapping unavailable";
  const nextDb = crosstalk.contract === "spike/si-crosstalk-result/v1"
    ? pointSeries("next-db", nextLabel, next.trace, "frequency_hz", "transfer_db")
    : null;
  const fextDb = crosstalk.contract === "spike/si-crosstalk-result/v1"
    ? pointSeries("fext-db", fextLabel, fext.trace, "frequency_hz", "transfer_db")
    : null;
  const crosstalkLinear = nextDb ? [
    pointSeries("next-linear", nextLabel, next.trace, "frequency_hz", "magnitude"),
    pointSeries("fext-linear", fextLabel, fext.trace, "frequency_hz", "magnitude"),
  ] : [];
  // Voltage is never inferred from power-wave S magnitude by the UI.
  const crosstalkVoltage: SiChartSeries[] = [];
  const loadedCrosstalkDb: SiChartSeries[] = [];
  const loadedCrosstalkLinear: SiChartSeries[] = [];
  const loaded = object(crosstalk.loaded);
  const loadedTime = object(loaded.time_domain);
  if (loaded.contract === "spike/si-loaded-crosstalk-result/v1" && loaded.status === "completed") {
    const response = object(loaded.frequency_response);
    const ports = object(loaded.port_map);
    const portLabel = (key: string) => {
      const number = finite(ports[key]);
      return number !== null && Number.isInteger(number) && number >= 0 ? `port ${number + 1} (${key})` : key;
    };
    for (const [kind, destination] of [["next", "victim_near"], ["fext", "victim_far"]]) {
      const label = `${kind.toUpperCase()} · ${portLabel("aggressor_near")} → ${portLabel(destination)}`;
      const trace = object(response[kind]).trace;
      loadedCrosstalkDb.push(pointSeries(`loaded-${kind}-db`, label, trace, "frequency_hz", "transfer_db"));
      loadedCrosstalkLinear.push(pointSeries(`loaded-${kind}-linear`, label, trace, "frequency_hz", "magnitude"));
    }
    const times = loadedTime.time_s;
    if (loadedTime.status === "completed" && Array.isArray(times) && times.every(item => finite(item) !== null)) {
      for (const [key, label] of [["source_v", "Thevenin source"], ["next_v", "NEXT victim voltage"], ["fext_v", "FEXT victim voltage"]]) {
        const values = loadedTime[key];
        if (Array.isArray(values) && values.length === times.length && values.every(item => finite(item) !== null)) {
          crosstalkVoltage.push({ id: key, label, points: times.map((time, index) => ({ x: time as number, y: values[index] as number })) });
        }
      }
    }
  }

  const eyeResult = object(result.eye);
  const eye = objects(eyeResult.traces).flatMap((trace, traceIndex) => {
    const values = Array.isArray(trace.values)
      ? trace.values.map(finite).filter((sample): sample is number => sample !== null)
      : [];
    if (values.length < 2) return [];
    const sourceBit = finite(trace.source_bit_index);
    return [{
      id: `eye-${sourceBit ?? traceIndex}`,
      label: `Bit ${sourceBit ?? traceIndex}`,
      // Each worker trace spans two unit intervals. Sample zero stays on the
      // left and the final sample stays on the right.
      points: values.map((sample, index) => ({ x: 2 * index / (values.length - 1), y: sample })),
    }];
  });
  const pam4 = object(eyeResult.pam4);
  const pam4Bathtub = objects(pam4.bathtub);
  const pam4EyeHeights = [0, 1, 2].map(index => ({
    id: `pam4-eye-${index + 1}`,
    label: `PAM4 eye ${index + 1}`,
    points: pam4Bathtub.flatMap(sample => {
      const phase = finite(sample.phase_ui);
      const values = finiteArray(sample.eye_heights_normalized);
      return phase === null || values[index] === undefined ? [] : [{ x: phase, y: values[index] }];
    }),
  })).filter(series => series.points.length > 0);
  const pam4BerProxies = [0, 1, 2].map(index => ({
    id: `pam4-ber-${index + 1}`,
    label: `PAM4 BER proxy ${index + 1}`,
    points: pam4Bathtub.flatMap(sample => {
      const phase = finite(sample.phase_ui);
      const values = finiteArray(sample.ber_proxies);
      return phase === null || values[index] === undefined ? [] : [{ x: phase, y: values[index] }];
    }),
  })).filter(series => series.points.length > 0);

  const rawPortOrder = Array.isArray(network.port_order) ? network.port_order : [];
  const portOrder = rawPortOrder.filter((port): port is string => typeof port === "string");
  const samplesPerUi = finite(eyeResult.samples_per_ui);
  // A future mixed-mode extractor may retain scalar metrics here.  Do not
  // synthesize mode conversion from single-ended S parameters in the UI.
  const differential = object(result.differential);
  const mixedModeSource = Object.keys(object(result.mixed_mode)).length
    ? object(result.mixed_mode)
    : object(differential.transform);
  const mixedModeMetrics = Object.fromEntries(Object.entries(mixedModeSource)
    .flatMap(([key, sample]) => {
      const number = finite(sample);
      return number === null ? [] : [[key, number]];
    }));
  return {
    portOrder,
    sMagnitudeDb,
    sPhaseDeg,
    reflectionMagnitude,
    vswr,
    tdrReflection,
    tdrImpedanceOhm,
    tdtNormalizedStep,
    nextDb,
    fextDb,
    crosstalkLinear,
    crosstalkVoltage,
    loadedCrosstalkDb,
    loadedCrosstalkLinear,
    crosstalkTimeStatus: typeof loadedTime.status === "string" ? loadedTime.status : "not_requested",
    impedanceReal,
    impedanceImag,
    impedanceMagnitude,
    impedanceCandidates,
    impedanceTermination: typeof impedance.termination_mode === "string" ? impedance.termination_mode : "not_available",
    impedanceCandidateTruncated: impedancePorts.some(port => port.candidate_output_truncated === true),
    eye,
    eyeSamplesPerUi: samplesPerUi,
    pam4EyeHeights,
    pam4BerProxies,
    productionQualified: false,
    complianceStatus: typeof result.compliance_status === "string" ? result.compliance_status : "not_evaluated",
    mixedModeMetrics,
  };
}

/** Display floor only: retained source data and CSV remain unmodified. */
export function floorSiDb(series: readonly SiChartSeries[], floor = -160): readonly SiChartSeries[] {
  if (!Number.isFinite(floor) || floor >= 0) throw new Error("The dB display floor must be finite and negative.");
  return series.map(item => ({ ...item, points: item.points.map(point => ({ ...point, y: Math.max(floor, point.y) })) }));
}

/** Long-form original retained samples, with spreadsheet-formula-safe labels. */
export function buildSiCrosstalkCsv(value: unknown): string {
  const charts = normalizeSiChannelResult(value);
  const quote = (text: string) => `"${(/^[=+@\-\t\r]/.test(text) ? "'" + text : text).replace(/"/g, '""')}"`;
  const rows = ["series,label,x_unit,y_unit,x,y"];
  const add = (series: readonly SiChartSeries[], xUnit: string, yUnit: string) => {
    for (const item of series) for (const point of item.points) {
      rows.push([quote(item.id), quote(item.label), xUnit, yUnit, String(point.x), String(point.y)].join(","));
    }
  };
  add([charts.nextDb, charts.fextDb].filter((item): item is SiChartSeries => item !== null), "Hz", "dB");
  add(charts.crosstalkLinear, "Hz", "power_wave_ratio");
  add(charts.loadedCrosstalkDb, "Hz", "dB_V_per_source_V");
  add(charts.loadedCrosstalkLinear, "Hz", "V_per_source_V");
  add(charts.crosstalkVoltage, "s", "V");
  return rows.join("\r\n") + "\r\n";
}

/** Retained impedance records preserve null masks instead of substituting zeros. */
export function buildSiImpedanceCsv(value: unknown): string {
  normalizeSiChannelResult(value);
  const response = object(object(object(value).network).impedance_response);
  const rows = ["port,frequency_hz,status,real_ohm,imag_ohm,magnitude_ohm,gap_before"];
  if (response.contract !== "spike/si-driving-point-impedance/v1" || response.status !== "completed") return rows[0] + "\r\n";
  for (const port of objects(response.ports)) {
    const index = finite(port.port);
    if (index === null || !Number.isInteger(index) || index < 0) continue;
    for (const row of objects(port.trace)) {
      const frequency = finite(row.frequency_hz);
      if (frequency === null) continue;
      const status = ["finite", "open_or_pole", "ill_conditioned_termination", "numerically_unresolved"].includes(String(row.status)) ? String(row.status) : "invalid";
      rows.push([index + 1, frequency, status,
        ...["real_ohm", "imag_ohm", "magnitude_ohm"].map(key => status === "finite" ? finite(row[key]) ?? "" : ""),
        row.gap_before === true].join(","));
    }
  }
  return rows.join("\r\n") + "\r\n";
}

/** Keep endpoints and global extrema, then fill uniformly in source order. */
export function boundSiSeries(points: readonly SiChartPoint[], limit = 1200): readonly SiChartPoint[] {
  if (!Number.isInteger(limit) || limit < 4) throw new Error("SI chart point limit must be an integer of at least four.");
  if (points.length <= limit) return points.slice();
  const selected = new Set<number>([0, points.length - 1]);
  let minimum = 0;
  let maximum = 0;
  for (let index = 1; index < points.length; index += 1) {
    if (points[index].y < points[minimum].y) minimum = index;
    if (points[index].y > points[maximum].y) maximum = index;
  }
  selected.add(minimum);
  selected.add(maximum);
  const slots = limit - selected.size;
  for (let slot = 1; slot <= slots; slot += 1) {
    selected.add(Math.round(slot * (points.length - 1) / (slots + 1)));
  }
  // Duplicate uniform samples can only reduce the output count. Never add
  // points out of order merely to hit the limit exactly.
  return [...selected].sort((left, right) => left - right).slice(0, limit).map(index => points[index]);
}

export function projectSiSeries(
  series: readonly SiChartSeries[],
  width = 760,
  height = 260,
  padding = 26,
  pointLimit = 1200,
): readonly ProjectedSiSeries[] {
  const bounded = series.map(item => ({ ...item, points: boundSiSeries(item.points, pointLimit) }));
  const all = bounded.flatMap(item => item.points);
  if (!all.length) return bounded.map(item => ({ ...item, points: "", source: item.points }));
  let xMinimum = all[0].x;
  let xMaximum = all[0].x;
  let yMinimum = all[0].y;
  let yMaximum = all[0].y;
  for (let index = 1; index < all.length; index += 1) {
    const point = all[index];
    if (point.x < xMinimum) xMinimum = point.x;
    if (point.x > xMaximum) xMaximum = point.x;
    if (point.y < yMinimum) yMinimum = point.y;
    if (point.y > yMaximum) yMaximum = point.y;
  }
  const xSpan = Math.max(xMaximum - xMinimum, Number.EPSILON);
  const ySpan = Math.max(yMaximum - yMinimum, Number.EPSILON);
  const innerWidth = Math.max(1, width - 2 * padding);
  const innerHeight = Math.max(1, height - 2 * padding);
  return bounded.map(item => ({
    id: item.id,
    label: item.label,
    source: item.points,
    points: item.points.map(point => {
      const x = padding + (point.x - xMinimum) / xSpan * innerWidth;
      // SVG y grows down. Subtracting from yMaximum keeps larger engineering
      // values visually higher without mutating or mirroring source samples.
      const y = padding + (yMaximum - point.y) / ySpan * innerHeight;
      return `${x.toFixed(3)},${y.toFixed(3)}`;
    }).join(" "),
  }));
}

const escapeHtml = (value: unknown) => String(value).replace(/[&<>"']/g, character => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
}[character] ?? character));

const palette = ["#67e8f9", "#fbbf24", "#a78bfa", "#4ade80", "#fb7185", "#60a5fa", "#f472b6", "#c4b5fd"];

export function siPlotExtent(series: readonly SiChartSeries[]): { xMin: number; xMax: number; yMin: number; yMax: number } | null {
  const points = series.flatMap(item => item.points).filter(point => Number.isFinite(point.x) && Number.isFinite(point.y));
  if (!points.length) return null;
  const extent = { xMin: points[0].x, xMax: points[0].x, yMin: points[0].y, yMax: points[0].y };
  for (const point of points) {
    extent.xMin = Math.min(extent.xMin, point.x); extent.xMax = Math.max(extent.xMax, point.x);
    extent.yMin = Math.min(extent.yMin, point.y); extent.yMax = Math.max(extent.yMax, point.y);
  }
  return extent;
}

export function siTickLabel(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  return Math.abs(value) >= 1e4 || Math.abs(value) < 1e-3 ? value.toExponential(2) : Number(value.toPrecision(4)).toString();
}

function svgChart(title: string, xLabel: string, yLabel: string, series: readonly SiChartSeries[]): string {
  const visible = series.filter(item => item.points.length > 0);
  if (!visible.length) return `<section><h2>${escapeHtml(title)}</h2><p class="empty">No retained samples.</p></section>`;
  const projected = projectSiSeries(visible);
  const extent = siPlotExtent(visible)!;
  const ticks = [0, .5, 1].map(fraction => {
    const x = 26 + 708 * fraction;
    const y = 234 - 208 * fraction;
    const xValue = extent.xMin + (extent.xMax - extent.xMin) * fraction;
    const yValue = extent.yMin + (extent.yMax - extent.yMin) * fraction;
    const xTick = extent.xMin === extent.xMax && fraction !== 0 ? "" : `<line class="axis" x1="${x}" y1="234" x2="${x}" y2="238"/><text style="text-anchor:${fraction === 0 ? "start" : fraction === 1 ? "end" : "middle"}" x="${x}" y="247">${siTickLabel(xValue)}</text>`;
    const yTick = extent.yMin === extent.yMax && fraction !== 1 ? "" : `<text style="text-anchor:start" x="30" y="${y + 11}">${siTickLabel(yValue)}</text>`;
    return xTick + yTick;
  }).join("");
  const lines = projected.map((item, index) =>
    item.source.length === 1 ? `<circle cx="${item.points.split(",")[0]}" cy="${item.points.split(",")[1]}" r="2.5" fill="${palette[index % palette.length]}"/>` : `<polyline data-series="${escapeHtml(item.id)}" points="${item.points}" stroke="${palette[index % palette.length]}"/>`,
  ).join("");
  const legend = projected.map((item, index) =>
    `<span><i style="background:${palette[index % palette.length]}"></i>${escapeHtml(item.label)}</span>`,
  ).join("");
  return `<section><h2>${escapeHtml(title)}</h2><div class="legend">${legend}</div><svg viewBox="0 0 760 270" role="img" aria-label="${escapeHtml(title)}"><line class="axis" x1="26" y1="234" x2="734" y2="234"/><line class="axis" x1="26" y1="26" x2="26" y2="234"/>${lines}${ticks}<text x="380" y="266">${escapeHtml(xLabel)}</text><text x="8" y="130">${escapeHtml(yLabel)}</text></svg></section>`;
}

/**
 * Builds a bounded, offline, SVG-only report. It contains no canvas transform,
 * CSS reflection, or runtime plotting dependency, so exported coordinates use
 * the same left-to-right and low-to-high conventions as the normalized data.
 */
export function buildSiChannelHtmlReport(value: unknown): string {
  const charts = normalizeSiChannelResult(value);
  const crosstalk = [charts.nextDb, charts.fextDb].filter((item): item is SiChartSeries => item !== null);
  const eye = charts.eye.slice(0, 96);
  const portOrder = charts.portOrder.length ? charts.portOrder.join(" → ") : "Worker-declared numeric port order";
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>SPIKE experimental SI channel report</title><style>
body{margin:0;padding:28px;background:#07111d;color:#e5eef8;font:14px system-ui,sans-serif}header,section{max-width:1120px;margin:0 auto 22px;padding:20px;background:#0d1b2a;border:1px solid #26394d;border-radius:10px}h1,h2{margin:0 0 10px}.warning{color:#fde68a}.meta{color:#9fb3c8}.legend{display:flex;gap:12px;flex-wrap:wrap;margin:8px 0}.legend span{display:flex;align-items:center;gap:5px;font-size:12px}.legend i{width:14px;height:3px}svg{display:block;width:100%;height:280px;background:#081522}.axis{stroke:#789;stroke-width:1}polyline{fill:none;stroke-width:1.5;vector-effect:non-scaling-stroke}text{fill:#9fb3c8;font-size:10px;text-anchor:middle}.empty{color:#9fb3c8}@media print{body{background:white;color:#111}header,section{break-inside:avoid;background:white;border-color:#bbb}svg{background:white}}
</style></head><body><header><h1>Geometry-derived SI channel</h1><p class="warning"><b>Experimental — not production/signoff qualified and not protocol-compliance evidence.</b></p><p class="meta">Ports: ${escapeHtml(portOrder)} · Compliance: ${escapeHtml(charts.complianceStatus)}</p></header>
${svgChart("S-parameter magnitude", "Frequency (Hz)", "dB", charts.sMagnitudeDb)}
${svgChart("S-parameter phase", "Frequency (Hz)", "deg", charts.sPhaseDeg)}
${svgChart("TDR impedance", "Time (s)", "ohm", [charts.tdrImpedanceOhm])}
${svgChart("TDR reflection", "Time (s)", "rho", [charts.tdrReflection])}
${svgChart("TDT transmitted step", "Time (s)", "normalized", [charts.tdtNormalizedStep])}
${svgChart("NEXT / FEXT (display floor −160 dB)", "Frequency (Hz)", "dB", floorSiDb(crosstalk))}
${svgChart("NEXT / FEXT linear magnitude", "Frequency (Hz)", "power-wave ratio", charts.crosstalkLinear)}
${svgChart("Loaded victim/source voltage transfer (floor −160 dB)", "Frequency (Hz)", "dB V/V", floorSiDb(charts.loadedCrosstalkDb))}
${svgChart("Loaded victim/source voltage transfer", "Frequency (Hz)", "V/V", charts.loadedCrosstalkLinear)}
${svgChart("Victim voltage", "Time (s)", "V", charts.crosstalkVoltage)}
${svgChart("Loaded driving-point resistance", "Frequency (Hz)", "ohm", charts.impedanceReal)}
${svgChart("Loaded driving-point reactance", "Frequency (Hz)", "ohm", charts.impedanceImag)}
${svgChart("Loaded driving-point impedance magnitude", "Frequency (Hz)", "ohm", charts.impedanceMagnitude)}
<section><h2>Sampled resonance candidates</h2><p>Other ports terminated: ${escapeHtml(charts.impedanceTermination)}. Selected driving-port load is excluded. Masked poles are gaps. Candidates are not fitted poles, Q estimates or qualified physical resonances.</p><ul>${charts.impedanceCandidates.map(candidate => `<li>${escapeHtml(candidate.port)}: ${escapeHtml(candidate.kind)}; ${escapeHtml(candidate.frequencyHz ?? "bracket only")} Hz; bracket ${escapeHtml(candidate.bracketHz.join(" – "))} Hz</li>`).join("")}</ul><p>${charts.impedanceCandidateTruncated ? "Candidate output was truncated by the worker." : "Finite frequency spacing can miss narrow resonances."}</p></section>
${svgChart("Normalized NRZ eye", "Unit interval", "normalized amplitude", eye)}
${svgChart("PAM4 eye height by sampling phase", "Unit interval", "normalized amplitude", charts.pam4EyeHeights)}
${svgChart("PAM4 BER proxies by sampling phase", "Unit interval", "BER proxy", charts.pam4BerProxies)}
<section><h2>Qualification boundary</h2><p>This report preserves the worker's retained sample order and declared port mapping. It does not add de-embedding, extrapolation, receiver/package models, jitter/noise statistics, protocol masks, or certification.</p></section></body></html>`;
}

export const EMPTY_SI_SERIES = emptySeries;
