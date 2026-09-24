import { normalizeSolverResult, type SolverResultBundle } from "./analysisResults";

/** The worker admits and design-binds this route before the UI receives it. */
export function extensionAnalysisResult(
  point: string,
  outputContract: string | undefined,
  data: unknown,
): SolverResultBundle | null {
  if (point !== "analyses" || outputContract !== "spike/v1" || !data || typeof data !== "object") return null;
  const envelope = data as Record<string, unknown>;
  const raw = envelope.analysis_result;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const result = raw as Record<string, unknown>;
  const provenance = result.provenance;
  if (result.contract !== "spike/v1" || typeof result.analysis_id !== "string" || !result.analysis_id
    || !provenance || typeof provenance !== "object" || Array.isArray(provenance)
    || typeof (provenance as Record<string, unknown>).design_id !== "string"
    || typeof (provenance as Record<string, unknown>).design_digest_sha256 !== "string"
    || (provenance as Record<string, unknown>).design_digest_sha256 !== envelope.input_design_sha256) return null;
  const bundle = normalizeSolverResult(raw);
  if (!bundle) return null;
  // The general UI normalizer derives voltage drop from source and node voltage
  // for older internal DC payloads. An external engine must publish that field.
  const fields = result.fields as Record<string, unknown> | undefined;
  const visualization = fields?.visualization as Record<string, unknown> | undefined;
  const scalars = visualization?.scalar_fields as Record<string, unknown> | undefined;
  if (!Array.isArray((result.scalar_fields as Record<string, unknown> | undefined)?.voltage_drop_v)
    && !Array.isArray(scalars?.voltage_drop_v)) bundle.scalar_fields.voltage_drop_v = [];
  return bundle;
}
