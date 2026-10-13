// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const appRoot = resolve(import.meta.dirname, "..");
const source = readFileSync(resolve(appRoot, "src", "ParallelWorkerPanel.tsx"), "utf8");
const engineCenterSource = readFileSync(resolve(appRoot, "src", "ExternalEngineCenter.tsx"), "utf8");
assert.match(engineCenterSource, /import ParallelWorkerPanel from "\.\/ParallelWorkerPanel"/);
assert.match(engineCenterSource, /> Worker pool<\/button>/);
assert.match(engineCenterSource, /section === "pool" \? <ParallelWorkerPanel workspace=/);
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const nodeRequire = createRequire(import.meta.url);

function loadModule(reactDependency, bridge = {}) {
  const loaded = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => {
    if (name === "react") return reactDependency;
    if (name === "react/jsx-runtime") return nodeRequire("react/jsx-runtime");
    if (name === "./workerBridge") return {
      runLocalWorker: bridge.runLocalWorker ?? (async () => { throw new Error("unexpected worker request"); }),
      cancelLocalWorker: bridge.cancelLocalWorker ?? (async () => false),
    };
    if (name === "./parallelWorkspace") {
      const dependency = { exports: {} };
      const output = ts.transpileModule(readFileSync(resolve(appRoot, "src", "parallelWorkspace.ts"), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
      new Function("module", "exports", output)(dependency, dependency.exports);
      return dependency.exports;
    }
    if (name === "./ParallelWorkerPanel.css") return {};
    return nodeRequire(name);
  }, loaded, loaded.exports);
  return loaded.exports;
}

const api = loadModule(React);
const allowed = ["run_smps_converter", "run_internal_airflow"];
const jobs = api.parseParallelJobs(JSON.stringify([
  { id: "converter-a", method: "run_smps_converter", params: { request: { contract: "example/v1" } } },
  { id: "airflow-b", method: "run_internal_airflow", params: { request: { contract: "example/v1" } } },
]), allowed);
assert.equal(jobs.length, 2);
assert.equal(jobs[0].method, "run_smps_converter");
assert.equal(api.parseParallelJobs(JSON.stringify([{ id: "electrical-port", method: allowed[0], params: { request: { port_id: "positive" } } }]), allowed).length, 1);
assert.throws(() => api.parseParallelJobs(" ".repeat(4 * 1024 * 1024 + 1), allowed), /review limit/);
assert.throws(() => api.parseParallelJobs("{}", allowed), /JSON array/);
assert.throws(() => api.parseParallelJobs(JSON.stringify([{ id: "a", method: "run_unknown", params: {} }]), allowed), /allowlist/);
assert.throws(() => api.parseParallelJobs(JSON.stringify([{ id: "a", method: allowed[0], params: { api_key: "do-not-send" } }]), allowed), /cannot carry network locations or credentials/);
assert.throws(() => api.parseParallelJobs(JSON.stringify([{ id: "a", method: allowed[0], params: { accessToken: "do-not-send" } }]), allowed), /cannot carry network locations or credentials/);
assert.throws(() => api.parseParallelJobs(JSON.stringify([{ id: "not portable", method: allowed[0], params: {} }]), allowed), /portable id/);
assert.throws(() => api.parseParallelJobs(JSON.stringify([
  { id: "duplicate", method: allowed[0], params: {} }, { id: "duplicate", method: allowed[1], params: {} },
]), allowed), /duplicated/);
const request = api.buildParallelBatchRequest(JSON.stringify(jobs), allowed, "2", "3", "45", 8);
assert.deepEqual(request, { contract: "spike/parallel-batch/v1", jobs, concurrency: 2, threads_per_job: 3, timeout_s: 45 });
assert.throws(() => api.buildParallelBatchRequest(JSON.stringify(jobs), allowed, "2.5", "3", "45"), /Concurrency/);
assert.throws(() => api.buildParallelBatchRequest(JSON.stringify(jobs), allowed, "2", "5", "45", 8), /above the detected budget/);
assert.throws(() => api.buildParallelBatchRequest(JSON.stringify(jobs), allowed, "2", "1", "181", 8), /Timeout/);

const catalog = {
  contract: "spike/parallel-pool-catalog/v1",
  cpu_budget: 8,
  methods: allowed,
  limits: { max_concurrency: 8, max_threads_per_job: 8, max_timeout_s: 180, memory_limit: "unsupported_by_portable_process_pool" },
  acceleration: { runtime: { logical_cpus: 12, cpu_thread_budget: 8 }, backends: [
    { id: "cupy-cuda", name: "NVIDIA CuPy", state: "available" },
    { id: "petsc-mumps", name: "PETSc MUMPS", state: "unavailable" },
  ] },
};

const states = [], refs = [], effects = [], pending = [], cancellations = [];
let stateCursor = 0, refCursor = 0, effectCursor = 0;
const hookReact = {
  useEffect(effect) { const index = effectCursor++; if (!(index in effects)) effects[index] = effect; },
  useMemo(factory) { return factory(); },
  useRef(initial) { const index = refCursor++; if (!(index in refs)) refs[index] = { current: initial }; return refs[index]; },
  useState(initial) { const index = stateCursor++; if (!(index in states)) states[index] = typeof initial === "function" ? initial() : initial;
    return [states[index], value => { states[index] = typeof value === "function" ? value(states[index]) : value; }]; },
};
const interactiveApi = loadModule(hookReact, {
  runLocalWorker: value => new Promise(resolvePromise => pending.push({ value, resolve: resolvePromise })),
  cancelLocalWorker: async id => { cancellations.push(id); return true; },
});
const mount = () => { stateCursor = 0; refCursor = 0; effectCursor = 0; return interactiveApi.default(); };
function find(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (predicate(node)) return node;
  for (const child of [node.props?.children].flat(Infinity)) { const found = find(child, predicate); if (found) return found; }
  return null;
}
const button = label => find(mount(), node => node.type === "button" && node.props.children === label);
const flush = async () => { await new Promise(done => setImmediate(done)); await new Promise(done => setImmediate(done)); };

mount();
const unmount = effects[0]();
assert.deepEqual(pending[0].value, { method: "parallel_pool_catalog", params: {} }, "opening the tab reads only the local catalog");
assert.equal(pending.length, 1, "mounting must not execute a batch");
pending[0].resolve({ ok: true, result: catalog });
await flush();
let markup = renderToStaticMarkup(mount());
assert.match(markup, /Worker pool/);
assert.match(markup, /8 worker threads/);
assert.match(markup, /12 logical processors detected/);
assert.match(markup, /run smps converter/);
assert.match(markup, /NVIDIA CuPy: available/);
assert.match(markup, /whole-solve network partitioning is unsupported/);
assert.match(markup, /AMD and Intel GPU execution are unsupported/);
assert.match(markup, /no hosts, credentials, or secret keys accepted here/);
assert.match(markup, /Input review required/, "the empty example method requires explicit review");

const textarea = find(mount(), node => node.type === "textarea");
textarea.props.onChange({ target: { value: JSON.stringify(jobs, null, 2) } });
assert.match(renderToStaticMarkup(mount()), /Batch input reviewed/);
button("Run reviewed batch").props.onClick();
assert.equal(pending.length, 2);
assert.equal(pending[1].value.method, "run_parallel_batch");
assert.equal(pending[1].value.params.request.contract, "spike/parallel-batch/v1");
assert.equal(pending[1].value.params.request.concurrency, 1);
assert.equal(pending[1].value.params.request.threads_per_job, 1);
assert.deepEqual(pending[1].value.params.request.jobs, jobs);
assert.ok(pending[1].value.id, "the operation id is explicit so cancellation targets this batch");
assert.equal(button("Batch running…").props.disabled, true);
button("Cancel batch").props.onClick();
await flush();
assert.deepEqual(cancellations, [pending[1].value.id]);
assert.match(renderToStaticMarkup(mount()), /Cancelling/);

pending[1].resolve({ ok: false, type: "WorkerCancelledError", error: "Batch cancelled." });
await flush();
markup = renderToStaticMarkup(mount());
assert.match(markup, /cancelled/);
assert.match(markup, /Batch cancelled/);
assert.match(markup, /Review the job status and inputs, then retry/);

button("Run reviewed batch").props.onClick();
pending[2].resolve({ ok: true, result: {
  contract: "spike/parallel-batch-result/v1", status: "completed", outcomes: [
    { id: "converter-a", method: "run_smps_converter", status: "completed", ok: true, duration_s: 0.125, result: { status: "ok" } },
    { id: "airflow-b", method: "run_internal_airflow", status: "failed", ok: false, error: "fixture failure" },
  ],
} });
await flush();
markup = renderToStaticMarkup(mount());
assert.match(markup, /0.125 s/);
assert.match(markup, /fixture failure/);
assert.match(markup, /Returned result/);
assert.match(markup, /Saved batch results/, "prior failure remains in the portable history");
const retained = states.find(value => value?.contract === "spike/parallel-workspace/v1");
assert.equal(retained.runs.length, 2);
assert.equal(retained.runs[0].status, "cancelled");
assert.equal(retained.runs[1].result.contract, "spike/parallel-batch-result/v1");
assert.deepEqual(retained.runs[1].request.jobs, jobs);
const reopened = renderToStaticMarkup(React.createElement(api.default, { workspace: structuredClone(retained) }));
assert.match(reopened, /Saved batch results/);
assert.doesNotMatch(reopened, /fixture failure/, "large payloads are not formatted until the batch is opened");
const expand = find(mount(), node => node.type === "button" && node.props["aria-expanded"] === false && node.props.children?.[0] === retained.runs[1].id);
assert.ok(expand);
const beforeExpandRequests = pending.length;
expand.props.onClick();
assert.match(renderToStaticMarkup(mount()), /Saved results and execution provenance/);
assert.match(renderToStaticMarkup(mount()), /Load batch inputs/);
assert.equal(pending.length, beforeExpandRequests, "opening a retained result must not dispatch a worker job");
assert.doesNotMatch(reopened, /Batch running/);

button("Run reviewed batch").props.onClick();
const closingId = pending[3].value.id;
const beforeClose = JSON.stringify(states);
unmount();
await flush();
assert.equal(cancellations.at(-1), closingId, "closing the owner cancels its active batch");
pending[3].resolve({ ok: true, result: { contract: "spike/parallel-batch-result/v1", outcomes: [] } });
await flush();
assert.equal(JSON.stringify(states), beforeClose, "late callbacks cannot update a closed panel");

console.log("Parallel worker panel allowlist, input review, local catalog, resource controls, cancellation, per-job status and recovery tests passed.");
