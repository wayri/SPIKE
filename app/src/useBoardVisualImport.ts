import { useCallback, useEffect, useRef, useState } from "react";
import type { ParsedBoard } from "./boardParser";
import { materializeVisualBundle, type VisualBundlePayload } from "./boardVisualBundles";
import { cancelLocalWorker, isDesktopShell, runLocalWorker, runNativeProjectWorker, selectNativeMcadFile, type WorkerResponse } from "./workerBridge";
import { IMPORT_STAGES, missingModelProblems, useNativeCopperForImport, type BoardImportProgress } from "./boardImportProgress";

type ImportContext = { board: ParsedBoard; fileName: string; source: string; path?: string | null; overrides: Record<string, string>; warnings: Map<string, string> };

export function useBoardVisualImport(apply: (board: ParsedBoard) => void, status: (message: string) => void) {
  const [progress, setProgress] = useState<BoardImportProgress | null>(null);
  const [open, setOpen] = useState(false);
  const generation = useRef(0);
  const disposers = useRef(new Map<string, () => void>());
  const activeId = useRef<string | null>(null);
  const context = useRef<ImportContext | null>(null);
  const pending = useRef<Promise<void> | null>(null);
  const callbacks = useRef({ apply, status });
  callbacks.current = { apply, status };
  const reset = useCallback(() => {
    generation.current++;
    if (activeId.current) void cancelLocalWorker(activeId.current);
    activeId.current = null;
    disposers.current.forEach(dispose => dispose());
    disposers.current.clear();
    context.current = null;
    setProgress(null); setOpen(false);
  }, []);
  useEffect(() => reset, [reset]);

  const begin = useCallback((fileName: string) => {
    setOpen(true);
    setProgress({ fileName, stage: "parsing", percent: 0, label: "Reading board geometry and layers", startedAt: Date.now(), busy: true, warnings: [], problems: [] });
  }, []);
  const finishBasic = useCallback(() => {
    setProgress(current => current ? { ...current, stage: "ready", percent: 100, busy: false, label: "Board imported" } : null);
    setOpen(false);
  }, []);
  const fail = useCallback((message: string) => {
    setProgress(current => current ? { ...current, busy: false, label: "Import needs attention", warnings: [message] } : null);
    setOpen(true);
  }, []);

  const executeRun = useCallback(async (input: ImportContext, componentsOnly = false) => {
    const token = ++generation.current;
    if (activeId.current) await cancelLocalWorker(activeId.current);
    if (generation.current !== token) return;
    context.current = input;
    setOpen(true);
    if (!componentsOnly) input.warnings.clear();
    let missingPaths: string[] = [];
    let missingRefs: string[] = [];
    const nativeCopper = useNativeCopperForImport(input.board, new TextEncoder().encode(input.source).length);
    setProgress({ fileName: input.fileName, stage: "layout", percent: 15, label: "Preparing visual import", startedAt: Date.now(), busy: true, warnings: [], problems: [] });
    for (const step of IMPORT_STAGES) {
      if (componentsOnly && step.stage !== "components") continue;
      if (generation.current !== token) return;
      input.warnings.delete(step.stage);
      setProgress(current => current ? { ...current, stage: step.stage, percent: step.start, label: step.label } : null);
      const execute = async (lightweight: boolean): Promise<WorkerResponse> => {
        const id = crypto.randomUUID();
        activeId.current = id;
        const params = {
          ...(input.path ? { board_path: input.path } : { source_board: input.source, source_file: input.fileName }),
          stage: step.stage, lightweight_board: lightweight, timeout_seconds: 600,
          max_artifact_bytes: 96 * 1024 * 1024, model_overrides: input.overrides,
        };
        try {
          return await (input.path ? runNativeProjectWorker : runLocalWorker)({ id, method: "prepare_visual_bundle", params });
        } catch (error) { return { ok: false, error: error instanceof Error ? error.message : String(error) }; }
        finally { if (activeId.current === id) activeId.current = null; }
      };
      let response = await execute(nativeCopper && step.stage === "board");
      if (generation.current !== token) return;
      if (!response.ok && step.stage === "board" && !nativeCopper) {
        setProgress(current => current ? { ...current, label: "Recovering with native copper geometry" } : null);
        response = await execute(true);
      }
      if (generation.current !== token) return;
      if (!response.ok || !response.result) {
        input.warnings.set(step.stage, `${step.label}: ${response.error ?? "No visual data returned"}`);
        continue; // Finished stages remain usable; a failed stage never discards them.
      }
      try {
        setProgress(current => current ? { ...current, label: `Verifying ${step.stage === "layout" ? "layer" : "3D"} data` } : null);
        const materialized = await materializeVisualBundle(input.board, response.result);
        if (generation.current !== token) { materialized.dispose(); return; }
        const previousDispose = disposers.current.get(step.stage);
        disposers.current.set(step.stage, materialized.dispose);
        input.board = materialized.board;
        callbacks.current.apply(input.board);
        previousDispose?.();
        if (step.stage === "components") {
          missingRefs = materialized.missingReferences;
          missingPaths = (response.result as unknown as VisualBundlePayload).quality?.unresolved_model_paths ?? [];
        }
        setProgress(current => current ? { ...current, percent: step.end } : null);
      } catch (error) {
        input.warnings.set(step.stage, `${step.label}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
    if (generation.current !== token) return;
    if (missingRefs.length && !missingPaths.length) {
      const failed = new Set(missingRefs);
      missingPaths = input.board.components.filter(component => failed.has(component.ref))
        .flatMap(component => component.modelPaths ?? (component.modelPath ? [component.modelPath] : []));
      if (!missingPaths.length) input.warnings.set("components", `KiCad could not convert models for ${missingRefs.join(", ")}.`);
    }
    const warnings = [...input.warnings.values()];
    const problems = missingModelProblems(input.board, missingPaths);
    const message = warnings.length || problems.length ? "Board imported with items to review" : "Board, layers and 3D parts imported";
    setProgress(current => current ? { ...current, stage: "ready", percent: 100, busy: false, label: message, warnings, problems } : null);
    callbacks.current.status(message);
    setOpen(Boolean(warnings.length || problems.length));
  }, []);

  const run = useCallback((input: ImportContext, componentsOnly = false) => {
    const task = executeRun(input, componentsOnly);
    pending.current = task;
    void task.finally(() => { if (pending.current === task) pending.current = null; });
    return task;
  }, [executeRun]);
  const whenReady = useCallback(async () => {
    while (pending.current) await pending.current;
    return context.current?.board ?? null;
  }, []);
  const prepare = useCallback(async (board: ParsedBoard, fileName: string, source: string, path?: string | null) => {
    if (!isDesktopShell() || !fileName.toLowerCase().endsWith(".kicad_pcb")) { finishBasic(); return; }
    await run({ board, fileName, source, path, overrides: {}, warnings: new Map() });
  }, [run, finishBasic]);
  const cancel = useCallback(async () => {
    const token = ++generation.current;
    const id = activeId.current;
    if (id) await cancelLocalWorker(id);
    if (generation.current !== token) return;
    activeId.current = null;
    setProgress(current => current ? { ...current, stage: "cancelled", busy: false, label: "Import stopped; completed geometry is retained" } : null);
  }, []);
  const locate = useCallback(async (source: string) => {
    const current = context.current;
    if (!current?.path) { fail("Reimport the original board through the desktop Import command to select local replacement models."); return; }
    let file;
    try { file = await selectNativeMcadFile(); }
    catch (error) { fail(error instanceof Error ? error.message : String(error)); return; }
    if (!file || context.current !== current) return;
    if (!/\.(step|stp|wrl|vrml)$/i.test(file.path)) { fail("Select a STEP or VRML component model."); return; }
    current.overrides[source] = file.path;
    await run(current, true);
  }, [run, fail]);
  const retry = useCallback(async () => { if (context.current) await run(context.current); }, [run]);
  return { progress, open, begin, finishBasic, fail, prepare, reset, cancel, locate, retry, whenReady, dismiss: () => setOpen(false), show: () => setOpen(true) };
}
