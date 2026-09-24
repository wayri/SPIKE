export const ERROR_CONTRACT = "spike/error/v1" as const;

export type ErrorOrigin = "FE" | "BE";
export type ErrorClassification = "I" | "W" | "P" | "E" | "C" | "S";
export type SpikeErrorEnvelope = {
  contract: typeof ERROR_CONTRACT;
  code: string;
  origin: ErrorOrigin;
  domain: string;
  classification: ErrorClassification;
  sequence: number;
  title: string;
  message: string;
  detail?: string;
  recoverable: boolean;
  retryable: boolean;
  user_action: string;
  docs_anchor: string;
  timestamp_utc: string;
  operation_id?: string;
  cause_code?: string;
  context: Record<string, unknown>;
};

type FrontendCode =
  | "SPIKE-FE-APP-E-0001"
  | "SPIKE-FE-APP-C-9999"
  | "SPIKE-FE-IPC-E-0001"
  | "SPIKE-FE-IPC-E-0002"
  | "SPIKE-FE-VIEW-P-0001"
  | "SPIKE-FE-PROJECT-E-0001"
  | "SPIKE-FE-SPICE-E-0001";

const frontendCatalog: Record<FrontendCode, { title: string; action: string; recoverable: boolean; retryable: boolean }> = {
  "SPIKE-FE-APP-E-0001": { title: "Frontend operation failed", action: "Review the operation details, correct the input, and retry.", recoverable: true, retryable: true },
  "SPIKE-FE-APP-C-9999": { title: "Unexpected frontend failure", action: "Preserve the diagnostic record and restart SPIKE.", recoverable: false, retryable: false },
  "SPIKE-FE-IPC-E-0001": { title: "Worker unavailable", action: "Restart the worker or application, then retry.", recoverable: true, retryable: true },
  "SPIKE-FE-IPC-E-0002": { title: "Malformed worker response", action: "Preserve diagnostics and verify frontend/backend versions.", recoverable: false, retryable: false },
  "SPIKE-FE-VIEW-P-0001": { title: "Viewport performance degraded", action: "Reduce visible detail or select a lower rendering quality preset.", recoverable: true, retryable: true },
  "SPIKE-FE-PROJECT-E-0001": { title: "Project open failed", action: "Check the project path and package integrity, then retry.", recoverable: true, retryable: true },
  "SPIKE-FE-SPICE-E-0001": { title: "SPICE assistant input invalid", action: "Correct the highlighted model, pin, or analysis fields and validate again.", recoverable: true, retryable: true },
};

const codePattern = /^SPIKE-(FE|BE)-([A-Z]+)-(I|W|P|E|C|S)-([0-9]{4})$/;

export function isSpikeErrorEnvelope(value: unknown): value is SpikeErrorEnvelope {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<SpikeErrorEnvelope>;
  return candidate.contract === ERROR_CONTRACT
    && typeof candidate.code === "string"
    && codePattern.test(candidate.code)
    && typeof candidate.message === "string"
    && typeof candidate.classification === "string";
}

export function frontendError(
  code: FrontendCode,
  message: string,
  operationId?: string,
  context: Record<string, unknown> = {},
): SpikeErrorEnvelope {
  const match = code.match(codePattern);
  const metadata = frontendCatalog[code];
  if (!match || !metadata) throw new Error(`Unregistered frontend error code: ${code}`);
  return {
    contract: ERROR_CONTRACT,
    code,
    origin: "FE",
    domain: match[2],
    classification: match[3] as ErrorClassification,
    sequence: Number(match[4]),
    title: metadata.title,
    message: message.slice(0, 512),
    recoverable: metadata.recoverable,
    retryable: metadata.retryable,
    user_action: metadata.action,
    docs_anchor: `help:error-codes#${code.toLowerCase()}`,
    timestamp_utc: new Date().toISOString(),
    operation_id: operationId,
    context,
  };
}

export function diagnosticMessage(error: SpikeErrorEnvelope | undefined, fallback: string): string {
  return error ? `[${error.code}] ${error.message}` : fallback;
}
