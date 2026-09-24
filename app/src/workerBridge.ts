import { invoke } from "@tauri-apps/api/core";
import { diagnosticMessage, frontendError, isSpikeErrorEnvelope } from "./errorCatalog";
import type { SpikeErrorEnvelope } from "./errorCatalog";

export type WorkerResponse = {
  ok: boolean;
  id?: string;
  result?: Record<string, unknown>;
  error?: string;
  error_code?: string;
  error_detail?: SpikeErrorEnvelope;
  type?: string;
  meta?: Record<string, unknown>;
};
export type NativeTextFile = { path: string; fileName: string; contents: string };
export type NativeSelectedFile = { path: string; fileName: string };
export type PackageSignatureEnvelope = {
  contract: string;
  algorithm: string;
  key_id: string;
  signed_payload_sha256: string;
  signature_base64url: string;
};
export type NativePackageTrust = {
  verified: boolean;
  keyId: string;
  algorithm: string;
  signedPayloadSha256: string;
};

export type WorkerActivity = {
  operationId: string;
  method: string;
  heavy: boolean;
  phase: "started" | "cancelling" | "cancelled" | "completed" | "failed" | "rejected";
  durationMs?: number;
  message?: string;
  errorCode?: string;
};

const HEAVY_METHODS = new Set([
  "export_mcad_session",
  "preview_mcad_feedback",
  "apply_mcad_feedback",
  "benchmarks",
  "bind_multiboard_coupled_reduced_network",
  "export_step",
  "execute_thermal_field_job",
  "extract_mcad_package_shape_in_project",
  "generate_mcad_selector_preview_in_project",
  "import_into_assembly_project",
  "mesh_convergence",
  "plan_assembly_harnesses",
  "prepare_openems_case",
  "prepare_sparselizard_case",
  "prepare_3d_scene",
  "prepare_thermal_case",
  "prepare_visual_bundle",
  "plan_thermal_field_job",
  "read_project_model_artifacts",
  "read_project_state_artifact",
  "read_project_visual_bundle",
  "read_project_package_shape_selector_previews",
  "tessellate_mcad_part_in_project",
  "preview_mesh",
  "run_analysis",
  "run_converter_study",
  "run_field_circuit_cosimulation",
  "run_multiboard_si_independent_batch",
  "run_pi_path_native_mna",
  "run_harness_pi",
  "generate_tetrahedral_mesh",
  "run_openems_case",
  "run_preflighted_analysis",
  "run_si_uniform_channel",
  "run_si_workflow",
  "run_si_protocol_test_suite",
  "run_spice_workspace_native_mna",
  "run_owned_spice_workspace",
  "run_python_script",
  "run_sparselizard_case",
  "run_thermal_case",
]);

export function isHeavyWorkerMethod(method: string): boolean {
  return HEAVY_METHODS.has(method);
}

let activeHeavyOperation: { id: string; method: string } | null = null;
// A native cancellation request only acknowledges that shutdown has begun. Keep
// that intent locally until the matching run promise settles so a late worker
// response cannot overwrite the prompt cancelled state or expose partial data.
const cancelledOperations = new Map<string, number>();
let cancellationSequence = 0;

function operationId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `spike-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  if (error && typeof error === "object" && "message" in error) return String(error.message);
  return "The local SPIKE worker failed without a diagnostic message.";
}

function publishWorkerActivity(activity: Omit<WorkerActivity, "heavy">): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent<WorkerActivity>("spike-worker-activity", {
      detail: { ...activity, heavy: isHeavyWorkerMethod(activity.method) },
    }));
  }
}

export function isDesktopShell(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

export async function getDesktopAppVersion(): Promise<string | null> {
  if (!isDesktopShell()) return null;
  const { getVersion } = await import("@tauri-apps/api/app");
  return getVersion();
}

export async function subscribeDesktopCloseRequested(
  onRequested: (preventDefault: () => void) => void,
): Promise<() => void> {
  if (!isDesktopShell()) return () => undefined;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  return getCurrentWindow().onCloseRequested(event => onRequested(() => event.preventDefault()));
}

export async function closeDesktopWindow(): Promise<void> {
  if (!isDesktopShell()) return;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  // Called only after the main workspace's save/discard close decision.
  // A second close request would re-enter the listener and hide permission
  // failures inside Tauri's asynchronous event callback.
  await getCurrentWindow().destroy();
}

export async function runLocalWorker(request: Record<string, unknown>): Promise<WorkerResponse> {
  const method = typeof request.method === "string" ? request.method : "unknown";
  const id = typeof request.id === "string" && request.id ? request.id : operationId();
  if (!isDesktopShell()) {
    const errorDetail = frontendError("SPIKE-FE-IPC-E-0001", "Local worker execution requires the SPIKE desktop shell. The browser preview supports configuration and visualization only.", id, { method });
    return { ok: false, id, error: diagnosticMessage(errorDetail, errorDetail.message), error_code: errorDetail.code, error_detail: errorDetail };
  }
  const heavy = isHeavyWorkerMethod(method);
  if (heavy && activeHeavyOperation) {
    const message = `${activeHeavyOperation.method} is already running. Wait for it to finish before starting ${method}.`;
    const errorDetail = frontendError("SPIKE-FE-APP-E-0001", message, id, { active_method: activeHeavyOperation.method, requested_method: method });
    publishWorkerActivity({ operationId: id, method, phase: "rejected", message, errorCode: errorDetail.code });
    return { ok: false, id, error: diagnosticMessage(errorDetail, message), error_code: errorDetail.code, error_detail: errorDetail, type: "WorkerBusyError" };
  }
  if (heavy) activeHeavyOperation = { id, method };
  const started = performance.now();
  publishWorkerActivity({ operationId: id, method, phase: "started" });
  try {
    const response = await invoke<WorkerResponse>("run_worker", { request: { ...request, id } });
    const durationMs = performance.now() - started;
    if (cancelledOperations.has(id)) {
      return cancelledWorkerResponse(id, method);
    }
    if (!response || typeof response.ok !== "boolean") {
      const message = "The local worker returned a malformed response.";
      const errorDetail = frontendError("SPIKE-FE-IPC-E-0002", message, id, { method });
      publishWorkerActivity({ operationId: id, method, phase: "failed", durationMs, message, errorCode: errorDetail.code });
      return { ok: false, id, error: diagnosticMessage(errorDetail, message), error_code: errorDetail.code, error_detail: errorDetail, type: "WorkerProtocolError" };
    }
    const errorDetail = isSpikeErrorEnvelope(response.error_detail) ? response.error_detail : undefined;
    publishWorkerActivity({
      operationId: id,
      method,
      phase: response.ok ? "completed" : "failed",
      durationMs,
      message: errorDetail ? diagnosticMessage(errorDetail, response.error ?? errorDetail.message) : response.error,
      errorCode: errorDetail?.code ?? response.error_code,
    });
    return { ...response, error_detail: errorDetail, id: response.id ?? id };
  } catch (error) {
    const durationMs = performance.now() - started;
    if (cancelledOperations.has(id)) {
      return cancelledWorkerResponse(id, method);
    }
    const message = errorMessage(error);
    const errorDetail = frontendError("SPIKE-FE-IPC-E-0001", message, id, { method, error_type: error instanceof Error ? error.name : "WorkerInvokeError" });
    publishWorkerActivity({ operationId: id, method, phase: "failed", durationMs, message, errorCode: errorDetail.code });
    return { ok: false, id, error: diagnosticMessage(errorDetail, message), error_code: errorDetail.code, error_detail: errorDetail, type: error instanceof Error ? error.name : "WorkerInvokeError" };
  } finally {
    if (activeHeavyOperation?.id === id) activeHeavyOperation = null;
    cancelledOperations.delete(id);
  }
}

function cancelledWorkerResponse(id: string, method: string): WorkerResponse {
  const message = `${method} was cancelled.`;
  publishWorkerActivity({
    operationId: id,
    method,
    phase: "cancelled",
    message,
    errorCode: "SPIKE-BE-SOLVER-E-0003",
  });
  return {
    ok: false,
    id,
    error: `[SPIKE-BE-SOLVER-E-0003] ${message}`,
    error_code: "SPIKE-BE-SOLVER-E-0003",
    type: "WorkerCancelledError",
  };
}

export async function runSiUniformChannel(
  design: Record<string, unknown>,
  request: Record<string, unknown>,
): Promise<WorkerResponse> {
  return runLocalWorker({
    method: "run_si_uniform_channel",
    params: { design, request },
  });
}

export async function runSiProtocolTestSuite(
  design: Record<string, unknown>,
  request: Record<string, unknown>,
): Promise<WorkerResponse> {
  return runLocalWorker({
    method: "run_si_protocol_test_suite",
    params: { design, request },
  });
}

export async function cancelLocalWorker(operationId?: string): Promise<boolean> {
  if (!isDesktopShell()) return false;
  const id = operationId ?? activeHeavyOperation?.id;
  if (!id) return false;
  const method = activeHeavyOperation?.id === id ? activeHeavyOperation.method : "worker_operation";
  publishWorkerActivity({ operationId: id, method, phase: "cancelling", message: `Cancelling ${method}.` });
  const cancellationToken = ++cancellationSequence;
  try {
    // Set this before invoking native code to close the race with a worker
    // response that settles while the cancellation command is in flight.
    cancelledOperations.set(id, cancellationToken);
    const cancelled = await invoke<boolean>("cancel_worker", { operationId: id });
    if (!cancelled && cancelledOperations.get(id) === cancellationToken) cancelledOperations.delete(id);
    publishWorkerActivity({
      operationId: id,
      method,
      phase: cancelled ? "cancelling" : "failed",
      message: cancelled ? `${method} cancellation accepted; waiting for worker shutdown.` : `No active worker operation matched ${id}.`,
      errorCode: cancelled ? "SPIKE-BE-SOLVER-E-0003" : "SPIKE-FE-APP-E-0001",
    });
    return cancelled;
  } catch (error) {
    // Do not erase a newer repeated Stop request when this invocation loses a
    // race or fails independently.
    if (cancelledOperations.get(id) === cancellationToken) cancelledOperations.delete(id);
    const message = errorMessage(error);
    publishWorkerActivity({ operationId: id, method, phase: "failed", message, errorCode: "SPIKE-FE-IPC-E-0001" });
    return false;
  }
}

// React effect teardown is best-effort lifecycle cleanup, not a user-visible
// cancellation action. A request can finish natively just before its promise
// continuation settles, so suppress the expected stale-operation response.
export async function cancelLocalWorkerCleanup(operationId: string): Promise<boolean> {
  if (!isDesktopShell() || !operationId) return false;
  try {
    return await invoke<boolean>("cancel_worker", { operationId });
  } catch {
    return false;
  }
}

export async function openNativeTextFile(kind: "board" | "project" | "report" | "result" | "netlist" | "license" | "script"): Promise<NativeTextFile | null> {
  if (!isDesktopShell()) return null;
  return invoke<NativeTextFile | null>("open_text_file", { kind });
}

export async function saveNativeTextFile(suggestedName: string, contents: string, kind: "project" | "report" | "step" | "netlist" | "result" | "license" | "script"): Promise<string | null> {
  if (!isDesktopShell()) return null;
  return invoke<string | null>("save_text_file", { suggestedName, contents, kind });
}

export type ExtensionArtifact = { file_name: string; media_type: string; encoding: "base64" | "utf-8"; data: string; sha256: string };

export async function saveExtensionArtifact(artifact: ExtensionArtifact): Promise<string | null> {
  if (!isDesktopShell()) throw new Error("Engineering artifact export requires the desktop app.");
  return invoke<string | null>("save_extension_artifact", { suggestedName: artifact.file_name, data: artifact.data, encoding: artifact.encoding, sha256: artifact.sha256 });
}

export async function writeApprovedTextFile(path: string, contents: string): Promise<string> {
  if (!isDesktopShell()) throw new Error("Approved-path writes require the SPIKE desktop shell.");
  return invoke<string>("write_approved_text_file", { path, contents });
}

export async function selectNativeProjectFile(): Promise<NativeSelectedFile | null> {
  if (!isDesktopShell()) return null;
  return invoke<NativeSelectedFile | null>("select_project_file");
}

export async function selectNativeImportFile(kind: "board" | "harness", directory = false): Promise<NativeSelectedFile | null> {
  if (!isDesktopShell()) return null;
  return invoke<NativeSelectedFile | null>("select_import_file", { kind, directory });
}

export async function takeStartupProject(): Promise<NativeSelectedFile | null> {
  if (!isDesktopShell()) return null;
  return invoke<NativeSelectedFile | null>("take_startup_project");
}

export async function selectNativeMcadFile(): Promise<NativeSelectedFile | null> {
  if (!isDesktopShell()) return null;
  return invoke<NativeSelectedFile | null>("select_mcad_file");
}

export async function selectNativeProjectSavePath(suggestedName: string): Promise<string | null> {
  if (!isDesktopShell()) return null;
  return invoke<string | null>("select_project_save_path", { suggestedName });
}

export async function runNativeProjectWorker(request: Record<string, unknown>): Promise<WorkerResponse> {
  if (!isDesktopShell()) {
    return { ok: false, error: "SPIKE v3 package I/O requires the desktop shell.", type: "DesktopRequiredError" };
  }
  const method = typeof request.method === "string" ? request.method : "unknown";
  const id = typeof request.id === "string" && request.id ? request.id : operationId();
  const heavy = isHeavyWorkerMethod(method);
  if (heavy && activeHeavyOperation) {
    const message = `${activeHeavyOperation.method} is already running. Wait for it to finish before starting ${method}.`;
    publishWorkerActivity({ operationId: id, method, phase: "rejected", message, errorCode: "SPIKE-FE-APP-E-0001" });
    return { ok: false, id, error: message, error_code: "SPIKE-FE-APP-E-0001", type: "WorkerBusyError" };
  }
  if (heavy) activeHeavyOperation = { id, method };
  const started = performance.now();
  publishWorkerActivity({ operationId: id, method, phase: "started" });
  try {
    const response = await invoke<WorkerResponse>("run_project_worker", { request: { ...request, id } });
    if (cancelledOperations.has(id)) return cancelledWorkerResponse(id, method);
    publishWorkerActivity({
      operationId: id,
      method,
      phase: response.ok ? "completed" : "failed",
      durationMs: performance.now() - started,
      message: response.error,
      errorCode: response.error_code,
    });
    return { ...response, id: response.id ?? id };
  } catch (error) {
    if (cancelledOperations.has(id)) return cancelledWorkerResponse(id, method);
    const message = errorMessage(error);
    publishWorkerActivity({ operationId: id, method, phase: "failed", durationMs: performance.now() - started, message, errorCode: "SPIKE-FE-IPC-E-0001" });
    return { ok: false, id, error: message, error_code: "SPIKE-FE-IPC-E-0001", type: error instanceof Error ? error.name : "WorkerInvokeError" };
  } finally {
    if (activeHeavyOperation?.id === id) activeHeavyOperation = null;
    cancelledOperations.delete(id);
  }
}

export async function verifyNativeProjectManifestSignature(
  signedPayloadBase64url: string,
  signature: PackageSignatureEnvelope,
): Promise<NativePackageTrust> {
  if (!isDesktopShell()) throw new Error("Package trust verification requires the SPIKE desktop shell.");
  return invoke<NativePackageTrust>("verify_project_manifest_signature", {
    signedPayloadBase64url,
    signature,
  });
}
