// SPDX-License-Identifier: MIT

import type { SolverResultBundle } from "./analysisResults";

export type ReportDomain = "pi" | "si" | "thermal" | "emi";

export const domainLabels: Record<ReportDomain, string> = {
  pi: "Power Integrity",
  si: "Signal Integrity",
  thermal: "Thermal",
  emi: "Electromagnetic Interference",
};

export function reportDomain(result: SolverResultBundle | null, analysisMode: string): ReportDomain {
  const classifier = `${result?.mode ?? ""} ${analysisMode}`.toLowerCase();
  if (/\bemi\b|electromagnetic.?interference|openems|far.?field|near.?field/.test(classifier)) return "emi";
  if (/thermal|heat|electro.?thermal|conjugate/.test(classifier)) return "thermal";
  if (/\bsi\b|signal.?integrity|s.?parameter|tdr|tdt|eye|channel|serdes|ddr|lvds|crosstalk/.test(classifier)) return "si";
  return "pi";
}
