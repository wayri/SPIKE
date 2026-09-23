// SPDX-License-Identifier: MIT
import type { SourceLoadReview } from "./sourceLoadReview";

export function sourceLoadReportHtml(
  review: SourceLoadReview | null,
  modelStatus: string | undefined,
  fmt: (value: number | null, digits?: number) => string,
  html: (value: unknown) => string,
): string {
  if (!review) return "";
  const rows = review.paths.map(path =>
    `<tr><td>${html(path.sourceId)}</td><td>${html(path.loadId)}</td><td>${html(path.supplyNet)}</td><td>${fmt(path.sourceVoltageV, 8)}</td><td>${fmt(path.loadVoltageV, 8)}</td><td>${fmt(path.supplyDropV * 1000, 7)}</td><td>${path.returnNet ? `${fmt((path.loopDropV ?? 0) * 1000, 7)} / ${html(path.returnNet)}` : "No explicit return"}</td><td>${fmt(path.loadCurrentA, 7)}</td><td>${html(path.limitState)}</td></tr>`).join("");
  return `<section id="source-load"><h2>Source-to-load terminal paths</h2><p>Terminal geometry: ${html(review.status)}. Overall model: ${html(modelStatus)}. Voltage reference: ${html(review.voltageReference)}. Source current balance: ${review.sourceCurrentBalanceA === null ? "not returned" : `${fmt(review.sourceCurrentBalanceA, 8)} A`}.</p><table class="data-table"><thead><tr><th>Source</th><th>Load</th><th>Supply net</th><th>Source V</th><th>Load V</th><th>Supply drop mV</th><th>Loop drop mV / return</th><th>Load A</th><th>Limit screen</th></tr></thead><tbody>${rows}</tbody></table><p>Signed terminal values come from solved boundary nodes. A below-limit screen is not mesh or measured-board qualification.</p></section>`;
}
