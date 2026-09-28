// SPDX-License-Identifier: Apache-2.0
import { numericMaximum, numericMinimum } from "./numericRange";

const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const finite = (value: unknown): number | null => value === null || value === undefined || value === "" || !Number.isFinite(Number(value)) ? null : Number(value);
const number = (source: Record<string, unknown>, ...keys: string[]) => {
  for (const key of keys) { const value = finite(source[key]); if (value !== null) return value; }
  return null;
};
const html = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]!);
const fmt = (value: unknown, digits = 5) => {
  const n = finite(value);
  if (n === null) return "-";
  if (n === 0) return "0";
  return Math.abs(n) >= 10000 || Math.abs(n) < 0.001 ? n.toExponential(Math.max(2, digits - 2)) : n.toLocaleString("en-US", { maximumFractionDigits: digits });
};

export function buildThermalReportSection(rawScenario: unknown) {
  const scenario = record(rawScenario);
  const component = record(scenario.component_result);
  const field = record(scenario.field_result);
  const result = component.contract === "spike/thermal-result/v1" ? component : field;
  const ready = result.status === "completed";
  const summary = record(result.summary);
  const nodes = component.status === "completed" && Array.isArray(component.nodes) ? component.nodes.map(record) : [];
  const fields = nodes.length ? {} : record(field.fields);
  const temperatures = (Array.isArray(fields.temperature_c) ? fields.temperature_c : []).map(item => finite(record(item).value)).filter((value): value is number => value !== null);
  const maximumK = number(summary, "max_temperature_k", "maximum_temperature_k");
  const minimumK = number(summary, "min_temperature_k", "minimum_temperature_k");
  const peakC = number(summary, "max_temperature_c", "peak_temperature_c", "maximum_temperature_c") ?? (temperatures.length ? numericMaximum(temperatures) : maximumK === null ? null : maximumK - 273.15);
  const nodeTemperatures = nodes.map(node => number(node, "temperature_c")).filter((value): value is number => value !== null);
  const minimumC = number(summary, "min_temperature_c", "minimum_temperature_c") ?? (nodeTemperatures.length ? numericMinimum(nodeTemperatures) : temperatures.length ? numericMinimum(temperatures) : minimumK === null ? null : minimumK - 273.15);
  const ambientC = number(result, "ambient_temperature_c") ?? number(scenario, "ambient_temperature_c");
  const riseC = number(summary, "max_temperature_rise_c", "peak_temperature_rise_c", "temperature_rise_c") ?? (peakC !== null && ambientC !== null ? peakC - ambientC : null);
  const dissipatedW = number(summary, "total_dissipation_w", "total_power_w", "heat_source_power_w");
  const modelStatus = String(result.model_status ?? "not_qualified");
  const fluxCount = Array.isArray(fields.heat_flux_w_m2) ? fields.heat_flux_w_m2.length : 0;
  const gradientCount = Array.isArray(fields.temperature_gradient_c_per_mm) ? fields.temperature_gradient_c_per_mm.length : 0;
  const nodeRows = nodes.map(node => `<tr><td>${html(node.component_ref ?? node.id)}</td><td>${fmt(number(node, "power_w"), 6)}</td><td>${fmt(number(node, "temperature_c"), 6)}</td><td>${fmt(number(node, "steady_temperature_c"), 6)}</td><td>${fmt(number(node, "heat_flow_top_w"), 6)}</td><td>${fmt(number(node, "heat_flow_bottom_w"), 6)}</td></tr>`).join("");
  const surfaces = component.status === "completed" && Array.isArray(component.surfaces) ? component.surfaces.map(record) : [];
  const surfaceRows = surfaces.slice(0, 500).map(surface => `<tr><td>${html(surface.object_ref)}</td><td>${html(surface.surface)}</td><td>${html(surface.kind)}</td><td>${html(surface.target_ref ?? "environment")}</td><td>${fmt(number(surface, "heat_flow_w"), 7)}</td></tr>`).join("");
  const omittedSurfaces = Math.max(0, surfaces.length - 500);
  const statusClass = /failed|blocked|unsupported/i.test(modelStatus) ? "fail" : /^(validated|qualified)$/i.test(modelStatus) ? "pass" : "warn";
  const sectionHtml = `<section id="thermal-results"><h2>Thermal Analysis Result</h2><p>${html(result.status ?? "not run")} · ${html(result.mode ?? scenario.mode ?? "")} · ${html(modelStatus)}</p><table class="summary-table"><tr><th>Peak / minimum temperature</th><td>${peakC === null ? "Not returned" : `${fmt(peakC, 6)} C`} / ${minimumC === null ? "Not returned" : `${fmt(minimumC, 6)} C`}</td><th>Peak temperature rise</th><td>${riseC === null ? "Not returned" : `${fmt(riseC, 6)} C`}</td></tr><tr><th>Applied heat-source power</th><td>${dissipatedW === null ? "Not returned" : `${fmt(dissipatedW, 7)} W`}</td><th>Ambient reference</th><td>${ambientC === null ? "Not returned" : `${fmt(ambientC, 6)} C`}</td></tr><tr><th>Retained field preview</th><td>${temperatures.length.toLocaleString("en-US")} temperature / ${fluxCount.toLocaleString("en-US")} heat-flux / ${gradientCount.toLocaleString("en-US")} gradient samples</td><th>Field qualification</th><td><span class="severity ${statusClass}">${html(modelStatus)}</span></td></tr></table>${nodeRows ? `<h3>Component temperatures and heat paths</h3><table class="data-table"><thead><tr><th>Reference</th><th>Power W</th><th>Final C</th><th>Steady C</th><th>Top heat W</th><th>Bottom heat W</th></tr></thead><tbody>${nodeRows}</tbody></table><p>Top and bottom heat flows are steady-state branch values. The component result is an approximate lumped RC model; it does not produce a spatial PCB temperature field.</p>` : ""}${surfaceRows ? `<h3>Object and surface heat flows</h3><table class="data-table"><thead><tr><th>Object</th><th>Surface</th><th>Mechanism</th><th>Target</th><th>Steady flow W</th></tr></thead><tbody>${surfaceRows}</tbody></table><p>Positive flow leaves the named object; negative flow enters it. Each object remains one temperature node.${omittedSurfaces ? ` ${omittedSurfaces} more boundary rows remain in the saved result.` : ""}</p>` : ""}<div class="analytics-note"><b>Thermal validity boundary</b><p>Use this report for the solver-returned thermal scope only. A complete field claim requires a qualified solver adapter, geometry and contact evidence, material/coating data, boundary-condition evidence, mesh convergence, and workflow validation. Missing fields are deliberately shown as “Not returned”; no thermal field is inferred from electrical loss alone. Responsive reports retain bounded preview samples; full fields remain in their digest-bound solver artifact or prepared case.</p></div></section>`;
  const numericalNote = `<p>${ready ? "Component or field thermal results are shown in the Thermal Analysis Result section above." : "No completed thermal result is attached."} Spatial fields are reported only when a field solver returned them.</p>`;
  return { result, summary, ready, sectionHtml, numericalNote };
}
