// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import type { ParsedBoard } from "./boardParser";
import type { AssemblyDesigns } from "./mcadAssembly";
import { parseDesignSourceOffThread } from "./boardImport";
import { materializeVisualBundle } from "./boardVisualBundles";
import { cancelLocalWorkerCleanup, runNativeProjectWorker } from "./workerBridge";
import { projectAssemblyCanonicalBoard } from "./assemblyCanonicalBoard";
import { restoreAssemblyBoardVisual } from "./assemblyBoardVisualRestoration";

type ReadyPayload = {
  contract: "spike/assembly-visual-ready/v1";
  manifest_payload_sha256: string;
  source: { design_id: string; source_digest: string; source_file: string; snapshot: unknown; quality?: { component_count?: number } };
  bundles: Record<string, unknown>;
  stage_errors?: Record<string, string>;
  stage_diagnostics?: Record<string, { code?: string }>;
  skipped_stages?: string[];
};
type CachedVisual = { board: ParsedBoard; missingReferences: string[]; stageErrors: Record<string, string>; modelCoverageMessage: string | null; dispose: () => void };
type CacheEntry = {
  promise: Promise<CachedVisual>; consumers: number; lastUsed: number; settled: boolean;
  cancelled: boolean; operationId: string | null; cancelTimer: ReturnType<typeof setTimeout> | null;
};

const visualCache = new Map<string, CacheEntry>();
const MAX_CACHED_VISUALS = 30;

function operationId() {
  return globalThis.crypto?.randomUUID?.() ?? `assembly-visual-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function sourceDigest(design: Record<string, unknown>) {
  const source = design.source;
  return source && typeof source === "object" && !Array.isArray(source)
    ? String((source as Record<string, unknown>).source_digest ?? "").toLowerCase()
    : "";
}

function pruneVisualCache() {
  if (visualCache.size <= MAX_CACHED_VISUALS) return;
  const candidates = [...visualCache.entries()].filter(([, entry]) => entry.settled && entry.consumers === 0)
    .sort((left, right) => left[1].lastUsed - right[1].lastUsed);
  while (visualCache.size > MAX_CACHED_VISUALS && candidates.length) {
    const [key, entry] = candidates.shift()!;
    visualCache.delete(key);
    void entry.promise.then(value => value.dispose(), () => undefined);
  }
}

async function requestReady(entry: CacheEntry, path: string, manifestDigest: string, designId: string, componentOverrides: Record<string, string>) {
  const deadline = Date.now() + 180_000;
  while (!entry.cancelled) {
    const id = operationId();
    entry.operationId = id;
    const response = await runNativeProjectWorker({ id, method: "prepare_assembly_design_visual_bundle", params: {
      project_path: path, expected_manifest_payload_sha256: manifestDigest, design_id: designId, stage: "ready", component_model_overrides: componentOverrides,
    } });
    entry.operationId = null;
    if (response.ok) return response.result as ReadyPayload;
    const error = response.error ?? "Assembly visual preparation failed";
    const busy = response.type === "WorkerBusyError" || /WORKER_BUSY|worker\s+(?:is\s+)?busy/i.test(error);
    if (!busy || Date.now() >= deadline) throw new Error(error);
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  throw new Error("Assembly visual preparation cancelled");
}

function acquireVisual(path: string, manifestDigest: string, designId: string, expectedSourceDigest: string, componentOverrides: Record<string, string>) {
  const key = `${path}\u0000${manifestDigest}\u0000${designId}\u0000${expectedSourceDigest}\u0000${JSON.stringify(Object.entries(componentOverrides).sort(([a], [b]) => a.localeCompare(b)))}`;
  let entry = visualCache.get(key);
  if (!entry) {
    entry = { promise: Promise.resolve(null as unknown as CachedVisual), consumers: 0, lastUsed: Date.now(),
      settled: false, cancelled: false, operationId: null, cancelTimer: null };
    const created = entry;
    created.promise = (async () => {
      const payload = await requestReady(created, path, manifestDigest, designId, componentOverrides);
      if (payload.contract !== "spike/assembly-visual-ready/v1" || payload.manifest_payload_sha256 !== manifestDigest
        || payload.source?.design_id !== designId || payload.source?.source_digest !== expectedSourceDigest) {
        throw new Error("Assembly visual response does not match the opened manifest and retained source identity.");
      }
      let board = await parseDesignSourceOffThread(payload.source.source_file || "assembly.spike-design.json",
        JSON.stringify(payload.source.snapshot), "spike-normalized");
      const disposers: Array<() => void> = [];
      const missing = new Set<string>();
      const repairMessages = new Set<string>();
      try {
        for (const stage of ["layout", "board", "components"]) {
          if (!(stage in payload.bundles)) continue;
          const raw = payload.bundles[stage] as { quality?: { visual_source_repairs?: Array<{ message?: unknown }> } };
          for (const repair of raw?.quality?.visual_source_repairs ?? []) {
            if (typeof repair.message === "string") repairMessages.add(repair.message.slice(0, 2000));
          }
          const bundle = await materializeVisualBundle(board, payload.bundles[stage]);
          disposers.push(bundle.dispose); board = bundle.board;
          bundle.missingReferences.forEach(reference => missing.add(reference));
        }
        const stageErrors = Object.fromEntries(Object.entries(payload.stage_errors ?? {}).map(([stage, message]) => {
          const code = payload.stage_diagnostics?.[stage]?.code;
          return [stage, code === "SPIKE-BE-VIEW-E-0001" ? `[${code}] ${message}` : message];
        }));
        return { board, missingReferences: [...missing], stageErrors,
          modelCoverageMessage: [...repairMessages, ...(payload.skipped_stages?.includes("components") ? [`No source 3D model assignments (${payload.source.quality?.component_count ?? board.components.length} footprints); component placeholders remain`] : [])].join("; ") || null,
          dispose: () => disposers.forEach(dispose => dispose()) };
      } catch (error) {
        disposers.forEach(dispose => dispose());
        throw error;
      }
    })().finally(() => { created.settled = true; created.lastUsed = Date.now(); pruneVisualCache(); });
    created.promise.catch(() => { if (visualCache.get(key) === created) visualCache.delete(key); });
    visualCache.set(key, created);
  }
  entry.consumers += 1; entry.lastUsed = Date.now();
  if (entry.cancelTimer) { clearTimeout(entry.cancelTimer); entry.cancelTimer = null; }
  const release = () => {
    entry!.consumers = Math.max(0, entry!.consumers - 1); entry!.lastUsed = Date.now();
    if (entry!.consumers === 0 && !entry!.settled) entry!.cancelTimer = setTimeout(() => {
      if (entry!.consumers || entry!.settled) return;
      entry!.cancelled = true;
      if (visualCache.get(key) === entry) visualCache.delete(key);
      if (entry!.operationId) void cancelLocalWorkerCleanup(entry!.operationId);
    }, 0);
  };
  return { promise: entry.promise, release };
}

/** Export once per retained source identity, then share verified GLB/SVG assets across occurrences and rerenders. */
export function useAssemblyBoardVisuals(retained: AssemblyDesigns | null, active: ParsedBoard | null,
  path: string | null, manifestDigest: string | null, whenActiveReady?: () => Promise<ParsedBoard | null>, componentOverridesByDesign?: Record<string, Record<string, string>>, signal?: AbortSignal) {
  const [prepared, setPrepared] = useState<Record<string, ParsedBoard>>({});
  const [diagnostics, setDiagnostics] = useState<Record<string, string>>({});
  const total = retained?.designs.filter(design => design.design_id !== retained.active_design_id).length ?? 0;
  const [progress, setProgress] = useState<{ owner: AssemblyDesigns | null; completed: number; pending: boolean }>({ owner: null, completed: 0, pending: false });
  const fallback = useMemo(() => {
    const boards: Record<string, ParsedBoard> = {}, errors: Record<string, string> = {};
    for (const design of retained?.designs ?? []) {
      try { boards[design.design_id] = projectAssemblyCanonicalBoard(design); }
      catch (cause) { errors[design.design_id] = `Retained geometry unavailable: ${cause instanceof Error ? cause.message : String(cause)}`; }
    }
    return { boards, errors };
  }, [retained]);
  useEffect(() => {
    let cancelled = false;
    const releases: Array<() => void> = [];
    const releaseAll = () => releases.splice(0).forEach(release => release());
    const abort = () => {
      cancelled = true; releaseAll();
      setProgress({ owner: retained, completed: 0, pending: false });
      if (retained) setDiagnostics(rows => ({ ...rows, [retained.active_design_id]: "Visual preparation cancelled; retained source geometry remains available." }));
    };
    setPrepared({}); setDiagnostics({});
    setProgress({ owner: retained, completed: 0, pending: Boolean(retained && path && manifestDigest && total) });
    if (signal?.aborted) { abort(); return; }
    if (!retained || !path || !manifestDigest || retained.designs.length < 1) return;
    signal?.addEventListener("abort", abort, { once: true });
    void (async () => {
      await whenActiveReady?.();
      let completed = 0;
      for (const design of retained.designs) {
        if (cancelled) return;
        if (design.design_id === retained.active_design_id) continue;
        const digest = sourceDigest(design);
        if (!/^[0-9a-f]{64}$/.test(digest)) {
          setDiagnostics(rows => ({ ...rows, [design.design_id]: "Retained board source identity is missing or malformed." }));
          setProgress({ owner: retained, completed: ++completed, pending: completed < total });
          continue;
        }
        const acquired = acquireVisual(path, manifestDigest, design.design_id, digest, componentOverridesByDesign?.[design.design_id] ?? {});
        releases.push(acquired.release);
        try {
          const result = await acquired.promise;
          if (cancelled) return;
          setPrepared(rows => ({ ...rows, [design.design_id]: result.board }));
          setDiagnostics(rows => {
            const next = { ...rows };
            const failures = Object.entries(result.stageErrors).map(([stage, message]) => `${stage}: ${message}`);
            if (result.modelCoverageMessage) failures.push(result.modelCoverageMessage);
            if (failures.length) next[design.design_id] = failures.join("; ");
            else if (result.missingReferences.length) next[design.design_id] = `${result.missingReferences.length} unresolved component model references`;
            else delete next[design.design_id];
            return next;
          });
        } catch (cause) {
          if (!cancelled) setDiagnostics(rows => ({ ...rows, [design.design_id]: cause instanceof Error ? cause.message : String(cause) }));
        }
        if (!cancelled) setProgress({ owner: retained, completed: ++completed, pending: completed < total });
      }
    })().catch(cause => {
      if (cancelled) return;
      setDiagnostics(rows => ({ ...rows, [retained.active_design_id]: `Visual preparation failed: ${cause instanceof Error ? cause.message : String(cause)}` }));
      setProgress({ owner: retained, completed: total, pending: false });
    });
    return () => { cancelled = true; signal?.removeEventListener("abort", abort); releaseAll(); };
  }, [retained, path, manifestDigest, whenActiveReady, componentOverridesByDesign, signal]);
  const boards = useMemo(() => {
    const restored = { ...fallback.boards, ...prepared };
    if (retained && active) {
      const retainedBoard = fallback.boards[retained.active_design_id];
      const preparedBoard = prepared[retained.active_design_id];
      const canonical = retainedBoard && preparedBoard
        ? restoreAssemblyBoardVisual(retainedBoard, preparedBoard) : preparedBoard ?? retainedBoard;
      restored[retained.active_design_id] = canonical ? restoreAssemblyBoardVisual(canonical, active) : active;
    }
    return restored;
  }, [fallback, prepared, retained, active]);
  return { boards, diagnostics: { ...fallback.errors, ...diagnostics }, total,
    completed: progress.owner === retained ? progress.completed : 0,
    pending: progress.owner === retained ? progress.pending : Boolean(retained && path && manifestDigest && total) };
}
