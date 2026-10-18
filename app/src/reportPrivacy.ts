// SPDX-License-Identifier: Apache-2.0
import { APP_VERSION, RELEASE_CHANNEL } from "./appVersion";

export const REPORT_REDACTION_VERSION = "spike-report-redaction/1";
const ERROR_CLASSES = new Set(["Error", "TypeError", "RangeError", "ReferenceError", "SyntaxError", "URIError", "EvalError", "AggregateError"]);
const ERROR_CODES = new Set(["ENOENT", "EACCES", "EPERM", "ENOMEM", "ECONNREFUSED", "ETIMEDOUT", "ERR_OUT_OF_MEMORY"]);

/** Best-effort free-text scrubber. Arbitrary human names/project labels still require review. */
export function redactReportText(value: string): string {
  return value.slice(0, 12000)
    .replace(/\b(?:https?|file|ftp|ssh|wss?):\/\/[^\s<>]+/gi, "[URL removed]")
    .replace(/(?:[A-Z]:[\\/]|\\\\)[^\r\n<>"|]+/gi, "[path removed]")
    .replace(/(?:~\/|\/(?:Users|home|tmp|var|mnt|Volumes|opt|private|workspace|workspaces)\/)[^\r\n<>"|]+/gi, "[path removed]")
    .replace(/(^|[\s(=:])\/[^\s<>"')]+/g, "$1[path removed]")
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[email removed]")
    .replace(/\b(?:bearer\s+)[A-Za-z0-9._~+/=-]+/gi, "[credential removed]")
    .replace(/\b(?:password|passwd|secret|token|api[_-]?key|authorization|username|user|account|project|board|net)\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi, "[private field removed]")
    .replace(/\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b/g, "[credential removed]")
    .replace(/(?:[^\s<>"']+[\\/])+[^\s<>"']+/g, "[path removed]")
    .replace(/\b[^\s<>"']+\.(?:kicad_pcb|kicad_sch|kicad_pro|spike|step|stp|iges|igs|csv|json|xlsx|py|tsx?|jsx?|log|zip)\b/gi, "[filename removed]")
    .replace(/"[^"\r\n]*"|'[^'\r\n]*'/g, "[quoted text removed]")
    .replace(/\b\d{4}-\d{2}-\d{2}T[0-9:.]+Z?\b/g, "[timestamp removed]");
}

export type DiagnosticReport = {
  contract: "spike/support-report/v1";
  redaction_version: string;
  app_version: string;
  release_channel: string;
  kind: "interface-crash" | "user-report";
  report_id: string;
  error_class: string;
  error_code: string;
  message: string;
  frames: string[];
  component_depth: number;
  notes: string;
};

/** Non-cryptographic grouping key over ONLY public diagnostic fields; never hashes raw messages. */
function fingerprint(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index++) hash = Math.imul(hash ^ value.charCodeAt(index), 16777619);
  return `SPIKE-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

export function createDiagnosticReport(error?: Error | null, componentStack = ""): DiagnosticReport {
  // Keep bounded line/column positions only. Never export function names, filenames,
  // raw message, URL, browser fingerprint, wall clock time, or component labels.
  const frames = (error?.stack ?? "").slice(0, 24000).split("\n").slice(1, 21)
    .map(line => /:(\d{1,7}):(\d{1,7})\)?\s*$/.exec(line))
    .filter((match): match is RegExpExecArray => match !== null)
    .map(match => `[source location removed]:${match[1]}:${match[2]}`);
  const errorClass = error && ERROR_CLASSES.has(error.name) ? error.name : "Error";
  const candidateCode = error ? (error as Error & { code?: unknown }).code : undefined;
  const errorCode = typeof candidateCode === "string" && ERROR_CODES.has(candidateCode) ? candidateCode : "";
  const kind = error ? "interface-crash" : "user-report";
  return {
    contract: "spike/support-report/v1", redaction_version: REPORT_REDACTION_VERSION,
    app_version: APP_VERSION, release_channel: RELEASE_CHANNEL, kind,
    report_id: fingerprint(JSON.stringify([APP_VERSION, kind, errorClass, errorCode, frames])),
    error_class: error ? errorClass : "", error_code: errorCode,
    message: error ? "Error message omitted to protect project and personal information." : "User report",
    frames, component_depth: Math.min(50, componentStack.slice(0, 24000).split("\n").filter(line => line.trim()).length), notes: "",
  };
}

export function reportWithNotes(report: DiagnosticReport, notes: string): DiagnosticReport {
  return { ...report, notes: redactReportText(notes) };
}

export function formatDiagnosticReport(report: DiagnosticReport, format: "json" | "markdown"): string {
  if (format === "json") return JSON.stringify(report, null, 2);
  // A fenced JSON document keeps the same schema/fields in both share formats.
  const safeJson = JSON.stringify(report, null, 2).replace(/`/g, "\\u0060");
  return `# SPIKE support report ${report.report_id}\n\nReview before sharing. Automatic redaction cannot recognize every private detail.\n\n\`\`\`json\n${safeJson}\n\`\`\`\n`;
}
