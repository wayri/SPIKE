/* SPDX-License-Identifier: Apache-2.0 */
import { useEffect, useMemo, useRef, useState } from "react";
import { cancelLocalWorker, runLocalWorker } from "./workerBridge";
import { defaultParallelWorkspace, retainParallelRun, type ParallelWorkspace, type ParallelWorkspaceRun } from "./parallelWorkspace";
import "./ParallelWorkerPanel.css";

export type ParallelPoolCatalog = {
  contract: "spike/parallel-pool-catalog/v1";
  cpu_budget: number;
  methods: string[];
  allowed_methods?: string[];
  limits?: Record<string, unknown>;
  acceleration?: { runtime?: Record<string, unknown>; backends?: Array<Record<string, unknown>> };
  limitations?: string[];
};

export type ParallelBatchJob = { id: string; method: string; params: Record<string, unknown> };
export type ParallelBatchRequest = {
  contract: "spike/parallel-batch/v1";
  jobs: ParallelBatchJob[];
  concurrency: number;
  threads_per_job: number;
  timeout_s: number;
};

type BatchJobResult = {
  id: string;
  method?: string;
  status?: string;
  ok?: boolean;
  error?: unknown;
  result?: unknown;
  duration_s?: number;
};

type ParallelBatchResult = {
  contract: "spike/parallel-batch-result/v1";
  status?: string;
  outcomes: BatchJobResult[];
};

const FORBIDDEN_INPUT_KEY = /(?:^|_)(?:api_?key|authorization|credential|host|hostname|network|password|secret|ssh|token|url)(?:$|_)/i;

const integer = (value: string, label: string, minimum: number, maximum: number) => {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${label} must be an integer from ${minimum} to ${maximum}.`);
  }
  return parsed;
};

function inspectInput(value: unknown, path = "params"): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => inspectInput(item, `${path}[${index}]`));
    return;
  }
  if (!value || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value)) {
    const separatedKey = key.replace(/([a-z0-9])([A-Z])/g, "$1_$2");
    if (FORBIDDEN_INPUT_KEY.test(separatedKey)) {
      throw new Error(`${path}.${key} is not accepted. Worker-pool jobs cannot carry network locations or credentials.`);
    }
    inspectInput(child, `${path}.${key}`);
  }
}

export function parseParallelJobs(source: string, allowedMethods: string[]): ParallelBatchJob[] {
  if (new TextEncoder().encode(source).length > 4 * 1024 * 1024) throw new Error("Jobs exceed the 4 MiB review limit.");
  let parsed: unknown;
  try { parsed = JSON.parse(source); }
  catch (caught) { throw new Error(`Jobs must be valid JSON: ${caught instanceof Error ? caught.message : String(caught)}`); }
  if (!Array.isArray(parsed) || parsed.length < 1 || parsed.length > 64) {
    throw new Error("Jobs must be a JSON array containing 1 to 64 independent jobs.");
  }
  const ids = new Set<string>();
  return parsed.map((candidate, index) => {
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) throw new Error(`Job ${index + 1} must be an object.`);
    const job = candidate as Record<string, unknown>;
    const extra = Object.keys(job).filter(key => !["id", "method", "params"].includes(key));
    if (extra.length) throw new Error(`Job ${index + 1} has unsupported fields: ${extra.join(", ")}.`);
    const id = typeof job.id === "string" ? job.id.trim() : "";
    const method = typeof job.method === "string" ? job.method.trim() : "";
    if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(id)) throw new Error(`Job ${index + 1} needs a portable id of at most 128 characters.`);
    if (ids.has(id)) throw new Error(`Job id ${id} is duplicated.`);
    ids.add(id);
    if (!allowedMethods.includes(method)) throw new Error(`Job ${id} method ${method || "(empty)"} is not in the detected pool allowlist.`);
    if (!job.params || typeof job.params !== "object" || Array.isArray(job.params)) throw new Error(`Job ${id} params must be a JSON object.`);
    inspectInput(job.params, `Job ${id} params`);
    return { id, method, params: job.params as Record<string, unknown> };
  });
}

export function buildParallelBatchRequest(
  jobsJson: string,
  allowedMethods: string[],
  concurrency: string,
  threadsPerJob: string,
  timeoutSeconds: string,
  cpuBudget?: number,
): ParallelBatchRequest {
  const jobs = parseParallelJobs(jobsJson, allowedMethods);
  const parsedConcurrency = integer(concurrency, "Concurrency", 1, Math.min(8, jobs.length));
  const parsedThreads = integer(threadsPerJob, "Threads per job", 1, 32);
  if (cpuBudget !== undefined && parsedConcurrency * parsedThreads > cpuBudget) {
    throw new Error(`The batch requests ${parsedConcurrency * parsedThreads} CPU threads, above the detected budget of ${cpuBudget}.`);
  }
  return {
    contract: "spike/parallel-batch/v1",
    jobs,
    concurrency: parsedConcurrency,
    threads_per_job: parsedThreads,
    timeout_s: integer(timeoutSeconds, "Timeout", 1, 180),
  };
}

const validCatalog = (value: unknown): value is ParallelPoolCatalog => {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ParallelPoolCatalog>;
  return candidate.contract === "spike/parallel-pool-catalog/v1"
    && Number.isInteger(candidate.cpu_budget) && Number(candidate.cpu_budget) > 0
    && Array.isArray(candidate.methods) && candidate.methods.every(method => typeof method === "string" && method.length > 0);
};

const validBatchResult = (value: unknown): value is ParallelBatchResult => {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ParallelBatchResult>;
  return candidate.contract === "spike/parallel-batch-result/v1"
    && Array.isArray(candidate.outcomes)
    && candidate.outcomes.every(job => job && typeof job === "object" && typeof job.id === "string");
};

const firstPositiveInteger = (source: Record<string, unknown> | undefined, keys: string[], fallback: number) => {
  if (!source) return fallback;
  for (const key of keys) {
    const value = Number(source[key]);
    if (Number.isInteger(value) && value > 0) return value;
  }
  return fallback;
};

const readable = (value: string) => value.replace(/_/g, " ");
const jobTone = (job: BatchJobResult) => job.ok === true || job.status === "completed" ? "ready" : job.status === "queued" || job.status === "running" || job.status === "cancelling" ? "active" : "failed";
const errorText = (value: unknown) => typeof value === "string" ? value : value && typeof value === "object" && "message" in value ? String(value.message) : value ? JSON.stringify(value) : "";

export default function ParallelWorkerPanel({ workspace, onWorkspaceChange }: {
  workspace?: ParallelWorkspace; onWorkspaceChange?: (next: ParallelWorkspace) => void;
} = {}) {
  const [localWorkspace, setLocalWorkspace] = useState(defaultParallelWorkspace);
  const saved = workspace ?? localWorkspace;
  const workspaceRef = useRef(saved);
  workspaceRef.current = saved;
  const updateWorkspace = (next: ParallelWorkspace) => {
    workspaceRef.current = next;
    if (onWorkspaceChange) onWorkspaceChange(next); else setLocalWorkspace(next);
  };
  const updateDraft = (key: keyof ParallelWorkspace["draft"], value: string) => {
    const current = workspaceRef.current;
    updateWorkspace({ ...current, draft: { ...current.draft, [key]: value } });
  };
  const jobsJson = saved.draft.jobs_json, concurrency = saved.draft.concurrency;
  const threadsPerJob = saved.draft.threads_per_job, timeoutSeconds = saved.draft.timeout_s;
  const setJobsJson = (value: string) => updateDraft("jobs_json", value);
  const setConcurrency = (value: string) => updateDraft("concurrency", value);
  const setThreadsPerJob = (value: string) => updateDraft("threads_per_job", value);
  const setTimeoutSeconds = (value: string) => updateDraft("timeout_s", value);
  const saveRun = (run: ParallelWorkspaceRun) => updateWorkspace(retainParallelRun(workspaceRef.current, run));
  const [catalog, setCatalog] = useState<ParallelPoolCatalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [busy, setBusy] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState<BatchJobResult[]>([]);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const operationId = useRef<string | null>(null);
  const catalogSequence = useRef(0);

  const loadCatalog = async () => {
    const sequence = ++catalogSequence.current;
    setLoadingCatalog(true); setCatalogError("");
    const response = await runLocalWorker({ method: "parallel_pool_catalog", params: {} });
    if (catalogSequence.current !== sequence) return;
    if (!response.ok || !validCatalog(response.result)) {
      setCatalog(null);
      setCatalogError(response.error ?? "The local worker returned an invalid parallel-pool catalog.");
      setLoadingCatalog(false);
      return;
    }
    const loaded = response.result;
    setCatalog(loaded);
    setLoadingCatalog(false);
  };

  useEffect(() => { void loadCatalog(); return () => {
    catalogSequence.current += 1;
    const id = operationId.current;
    operationId.current = null;
    if (id) void cancelLocalWorker(id);
  }; }, []);

  const draftError = useMemo(() => {
    if (!catalog) return "Load the local pool catalog before reviewing a batch.";
    try { buildParallelBatchRequest(jobsJson, catalog.methods, concurrency, threadsPerJob, timeoutSeconds, catalog.cpu_budget); return ""; }
    catch (caught) { return caught instanceof Error ? caught.message : String(caught); }
  }, [catalog, jobsJson, concurrency, threadsPerJob, timeoutSeconds]);

  const run = async () => {
    if (!catalog || operationId.current) return;
    let request: ParallelBatchRequest;
    try { request = buildParallelBatchRequest(jobsJson, catalog.methods, concurrency, threadsPerJob, timeoutSeconds, catalog.cpu_budget); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); return; }
    const id = globalThis.crypto?.randomUUID?.() ?? `parallel-batch-${Date.now()}`;
    operationId.current = id;
    saveRun({ id, request, result: null, status: "interrupted" });
    setBusy(true); setCancelling(false); setError("");
    setResults(request.jobs.map(job => ({ id: job.id, method: job.method, status: "queued" })));
    const response = await runLocalWorker({ id, method: "run_parallel_batch", params: { request } });
    if (operationId.current !== id) return;
    operationId.current = null; setBusy(false); setCancelling(false);
    if (!response.ok || !validBatchResult(response.result)) {
      saveRun({ id, request, result: null, status: response.type === "WorkerCancelledError" ? "cancelled" : "failed", error: response.error ?? "Invalid worker result." });
      setError(response.error ?? "The worker returned an invalid parallel-batch result.");
      setResults(current => current.map(job => ({ ...job, status: response.type === "WorkerCancelledError" ? "cancelled" : "failed", error: response.error })));
      return;
    }
    saveRun({ id, request, result: response.result as unknown as Record<string, unknown>, status: response.result.status === "cancelled" ? "cancelled" : response.result.status === "completed_with_errors" ? "completed_with_errors" : "completed" });
    setResults(response.result.outcomes);
  };

  const cancel = async () => {
    const id = operationId.current;
    if (!id || cancelling) return;
    setCancelling(true); setError("");
    setResults(current => current.map(job => job.status === "queued" || job.status === "running" ? { ...job, status: "cancelling" } : job));
    const accepted = await cancelLocalWorker(id);
    if (!accepted && operationId.current === id) {
      setCancelling(false);
      setError("The local worker did not accept the cancellation request. The batch may already have finished.");
    }
  };

  const accelerators = catalog?.acceleration?.backends ?? [];
  const cpuEntries = catalog ? Object.entries({ cpu_thread_budget: catalog.cpu_budget, ...(catalog.limits ?? {}) }).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value)) : [];

  return <section className="parallel-worker-panel" aria-labelledby="parallel-worker-heading">
    <header>
      <div><p>Local compute</p><h3 id="parallel-worker-heading">Worker pool</h3></div>
      <button type="button" className="spike-control--compact" disabled={loadingCatalog || busy} onClick={() => void loadCatalog()}>{loadingCatalog ? "Detecting…" : "Refresh pool"}</button>
    </header>
    <p className="parallel-worker-intro">Run independent allowlisted jobs concurrently on this computer. Each job receives its own method and parameters; this does not partition one solve across workers or a network cluster.</p>

    {catalogError && <div className="parallel-worker-error" role="alert"><b>Pool detection failed.</b><span>{catalogError}</span><button type="button" className="spike-control--compact" onClick={() => void loadCatalog()}>Retry detection</button></div>}
    {saved.runs.length > 0 && <div className="parallel-worker-history" aria-label="Saved parallel execution history">
      <h4>Saved batch results</h4><p>The most recent 32 batches are retained in this project. Opening a batch does not execute it. A run saved before completion is interrupted.</p>
      {[...saved.runs].reverse().map(run => <article key={run.id}>
        <button type="button" className="spike-control--compact" aria-expanded={expandedRunId === run.id} onClick={() => setExpandedRunId(current => current === run.id ? null : run.id)}>{run.id} · {readable(run.status)}</button>
        {expandedRunId === run.id && <div>
        {run.error && <p role="alert">{run.error}</p>}
        <button type="button" className="spike-control--compact" disabled={busy} onClick={() => {
          const request = run.request as unknown as ParallelBatchRequest;
          updateWorkspace({ ...workspaceRef.current, draft: { jobs_json: JSON.stringify(request.jobs, null, 2), concurrency: String(request.concurrency), threads_per_job: String(request.threads_per_job), timeout_s: String(request.timeout_s) } });
        }}>Load batch inputs</button>
        <details><summary>Original request</summary><pre>{JSON.stringify(run.request, null, 2)}</pre></details>
        {run.result ? <details open><summary>Saved results and execution provenance</summary><pre>{JSON.stringify(run.result, null, 2)}</pre></details> : <p>No completed result was retained for this run.</p>}
        </div>}
      </article>)}
    </div>}
    {catalog && <>
      <div className="parallel-worker-runtime" aria-label="Detected pool resources">
        <article><span>CPU budget</span><b>{catalog.cpu_budget} worker threads</b><small>{firstPositiveInteger(catalog.acceleration?.runtime, ["logical_cpus"], catalog.cpu_budget)} logical processors detected; the worker budget is authoritative.</small></article>
        <article><span>Allowed methods</span><b>{catalog.methods.length}</b><small title={catalog.methods.join(", ")}>{catalog.methods.map(readable).join(", ") || "None detected"}</small></article>
        <article><span>Accelerators</span><b>{accelerators.length ? "Detected states" : "CPU only"}</b><small>{accelerators.length ? accelerators.map(item => `${String(item.name ?? item.id ?? "accelerator")}: ${readable(String(item.state ?? "unknown"))}`).join("; ") : "No supported accelerator reported."}</small></article>
      </div>
      {cpuEntries.length > 0 && <details className="parallel-worker-budget"><summary>CPU budget details</summary><dl>{cpuEntries.map(([key, value]) => <div key={key}><dt>{readable(key)}</dt><dd>{String(value)}</dd></div>)}</dl></details>}

      <div className="parallel-worker-editor">
        <label htmlFor="parallel-jobs-json"><span>Batch jobs JSON</span><small>Review every id, method, and params object before running.</small></label>
        <textarea id="parallel-jobs-json" spellCheck={false} value={jobsJson} disabled={busy} onChange={event => setJobsJson(event.target.value)} />
      </div>
      <div className="parallel-worker-knobs">
        <label><span>Concurrency</span><input aria-label="Concurrency" type="number" min="1" max={firstPositiveInteger(catalog.limits, ["max_concurrency"], 8)} step="1" value={concurrency} disabled={busy} onChange={event => setConcurrency(event.target.value)} /></label>
        <label><span>Threads per job</span><input aria-label="Threads per job" type="number" min="1" max={firstPositiveInteger(catalog.limits, ["max_threads_per_job"], 32)} step="1" value={threadsPerJob} disabled={busy} onChange={event => setThreadsPerJob(event.target.value)} /></label>
        <label><span>Timeout (seconds)</span><input aria-label="Timeout seconds" type="number" min="1" max={firstPositiveInteger(catalog.limits, ["max_timeout_s"], 180)} step="1" value={timeoutSeconds} disabled={busy} onChange={event => setTimeoutSeconds(event.target.value)} /></label>
      </div>
      <div className={`parallel-worker-review ${draftError ? "invalid" : "ready"}`} role="status">
        <b>{draftError ? "Input review required" : "Batch input reviewed"}</b><span>{draftError || "The batch uses only detected allowlisted methods and local resource controls."}</span>
      </div>
      <div className="parallel-worker-actions">
        <button type="button" className="spike-control--primary" disabled={busy || Boolean(draftError)} onClick={() => void run()}>{busy ? "Batch running…" : "Run reviewed batch"}</button>
        <button type="button" className="spike-control--compact" disabled={!busy || cancelling} onClick={() => void cancel()}>{cancelling ? "Cancelling…" : "Cancel batch"}</button>
        <span aria-live="polite">{busy ? `${results.length} jobs submitted to the local pool.` : results.length ? "Batch stopped or completed; per-job status is shown below." : "No batch has been run."}</span>
      </div>
      {error && <p className="parallel-worker-run-error" role="alert">{error} Review the job status and inputs, then retry.</p>}
      {results.length > 0 && <div className="parallel-worker-results" aria-label="Parallel job status">
        {results.map(job => <article key={job.id} className={jobTone(job)}><header><b title={job.id}>{job.id}</b><span>{readable(job.status ?? (job.ok ? "completed" : "failed"))}</span></header><small>{readable(job.method ?? "method not returned")}{typeof job.duration_s === "number" ? ` · ${job.duration_s.toFixed(3)} s` : ""}</small>{job.error !== undefined && <p>{errorText(job.error)}</p>}{job.result !== undefined && <details><summary>Returned result</summary><pre>{JSON.stringify(job.result, null, 2)}</pre></details>}</article>)}
      </div>}
      <aside className="parallel-worker-limits"><b>Execution boundary</b><ul><li>Only methods listed by the local catalog are dispatchable.</li><li>Jobs are independent; whole-solve network partitioning is unsupported.</li><li>NVIDIA acceleration is used only where an existing probed CuPy path reports support. AMD and Intel GPU execution are unsupported.</li><li>Network worker management is available through the documented CLI commands, with no hosts, credentials, or secret keys accepted here.</li></ul></aside>
    </>}
    {loadingCatalog && !catalog && <div className="parallel-worker-empty" role="status">Detecting the local CPU budget and allowed worker methods…</div>}
  </section>;
}
