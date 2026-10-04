// SPDX-License-Identifier: Apache-2.0
import { BookOpen, Bug, ChevronDown, ChevronUp, Code2, FilePlus2, Files, FolderOpen, History, Library, Maximize2, Minimize2, Pause, Play, Plus, Save, SaveAll, Square, StepBack, StepForward, X } from "./icons";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { extensionAnalysisResult } from "./extensionAnalysisResult";
import { cancelLocalWorker, cancelLocalWorkerCleanup, isDesktopShell, openNativeTextFile, runLocalWorker, saveNativeTextFile, selectNativeImportFile } from "./workerBridge";
import PythonCodeEditor from "./PythonCodeEditor";
import PythonRunStatus from "./PythonRunStatus";
import PythonDebugPanel from "./PythonDebugPanel";
import PythonFileExplorer from "./PythonFileExplorer";
import PythonTemplateLibrary from "./PythonTemplateLibrary";
import PythonWorkspaceHelp from "./PythonWorkspaceHelp";
import PythonRecoveryPanel from "./PythonRecoveryPanel";
import PythonNetBrowser from "./PythonNetBrowser";
import { admittedPythonUiActions, pythonContextKey, pythonWorkspaceContext, type PythonUiAction, type PythonWorkspaceContext } from "./pythonWorkspaceContext";
import { PYTHON_STARTER, PYTHON_TEMPLATES, type PythonTemplate } from "./pythonWorkspaceTemplates";
import { debugFinished, newPythonDocument, persistPythonWorkspace, PYTHON_TAB_LIMIT, pythonAbsolutePath, pythonRelativePath, pythonCodeFits, pythonCodeHash, pythonDirty, pythonFileName, pythonParent, pythonPathKey, remapPythonBreakpoints, restorePythonWorkspace, savedPythonDocument, togglePythonBreakpoint, type PythonDebugSnapshot, type PythonDocument, type PythonScriptResult, type PythonWorkspaceSession } from "./pythonWorkspaceModel";
import { boundFloatingRect, initialFloatingRect, type FloatingRect } from "./pythonFloatingWindow";
import { emergeGeometryPreview } from "./emergeGeometryPreview";
import { admitDataViews } from "./scriptDataViews";
import { physicalGeometry } from "./scriptResultViewportModel";
import "./pythonWorkspace.css";
import "./PythonCodeEditor.css";

const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);
type Closing = { kind: "tab"; id: string } | { kind: "workspace" };
export type PythonInitialScript = { id: string; name: string; code: string };

export default function PythonWorkspace({ design, results, workspace, initialScript, onUiAction, onClose, onStatus, onAttachDataset, onShowViewport }: {
  design: Record<string, unknown> | null; results: unknown;
  workspace?: PythonWorkspaceContext; initialScript?: PythonInitialScript | null; onUiAction?: (action: PythonUiAction) => void;
  onClose: () => void; onStatus: (message: string) => void; onAttachDataset?: (name: string, payload: unknown) => string;
  onShowViewport?: (result: unknown, label: string, keepEditorOpen?: boolean) => void;
}) {
  const context = useMemo(() => workspace ?? pythonWorkspaceContext(design), [workspace, design]);
  const contextKey = useMemo(() => pythonContextKey(context), [context]);
  const uiContext = useRef({ context, contextKey, onUiAction }); uiContext.current = { context, contextKey, onUiAction };
  const runContextKey = useRef("");
  const actionsApplied = useRef(false);
  const [insertion, setInsertion] = useState<{ text: string; revision: number }>();
  const [session, setSession] = useState(() => restorePythonWorkspace(PYTHON_STARTER));
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const [pane, setPane] = useState<"files" | "templates" | "help" | "backups" | "nets">("files");
  const [paneVisible, setPaneVisible] = useState(true);
  const [execution, setExecution] = useState<"idle" | "run" | "debug">("idle");
  const [runStartedAt, setRunStartedAt] = useState(0);
  const [runDocumentId, setRunDocumentId] = useState<string | null>(null);
  const [timeoutSeconds, setTimeoutSeconds] = useState(120);
  const [interpreter, setInterpreter] = useState(() => { try { return localStorage.getItem("spike-python-interpreter") || ""; } catch { return ""; } });
  const [stopping, setStopping] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({});
  const [backup, setBackup] = useState<{ ok: boolean; pending?: boolean; timestamp?: number; error?: string }>({ ok: true, pending: true });
  const [outputVisible, setOutputVisible] = useState(true);
  const [floating, setFloating] = useState(false);
  const [floatingRect, setFloatingRect] = useState<FloatingRect>(() => initialFloatingRect(window.innerWidth, window.innerHeight));
  const floatingDrag = useRef<{ kind: "move" | "resize"; rect: FloatingRect; x: number; y: number } | null>(null);
  const [inspectorVisible, setInspectorVisible] = useState(true);
  const tabStrip = useRef<HTMLDivElement>(null);
  const saveInFlight = useRef(false);
  const [outputs, setOutputs] = useState<Record<string, PythonScriptResult>>({});
  const [debug, setDebug] = useState<PythonDebugSnapshot | null>(null);
  const [debugBusy, setDebugBusy] = useState(false);
  const [closing, setClosing] = useState<Closing | null>(null);
  const [message, setMessage] = useState("Choose a file or template. Click a line number to add a breakpoint.");
  const [cursor, setCursor] = useState({ line: 1, column: 1 });
  const [focusLine, setFocusLine] = useState<{ line: number; revision: number }>();
  const fileInput = useRef<HTMLInputElement>(null);
  const activeRun = useRef<string | null>(null);
  const debugSession = useRef<string | null>(null);
  const lastPause = useRef("");
  const debugRevision = useRef(-1);
  const debugCommandActive = useRef(false);
  const pendingDebugSequence = useRef(0);
  const mounted = useRef(true);
  const openedInitialScript = useRef<string | null>(null);
  const desktop = isDesktopShell();
  useEffect(() => {
    const resize = () => setFloatingRect(rect => boundFloatingRect(rect, window.innerWidth, window.innerHeight));
    window.addEventListener("resize", resize); return () => window.removeEventListener("resize", resize);
  }, []);
  const beginFloatingGesture = (event: PointerEvent<HTMLElement>, kind: "move" | "resize") => {
    if (!floating || event.button !== 0 || kind === "move" && Boolean((event.target as HTMLElement).closest("button,input,select,a"))) return;
    event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
    floatingDrag.current = { kind, rect: floatingRect, x: event.clientX, y: event.clientY };
  };
  const moveFloatingGesture = (event: PointerEvent<HTMLElement>) => {
    const drag = floatingDrag.current; if (!drag) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    setFloatingRect(boundFloatingRect(drag.kind === "move" ? { ...drag.rect, x: drag.rect.x + dx, y: drag.rect.y + dy } : { ...drag.rect, width: drag.rect.width + dx, height: drag.rect.height + dy }, window.innerWidth, window.innerHeight));
  };
  const endFloatingGesture = (event: PointerEvent<HTMLElement>) => {
    floatingDrag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const active = session.documents.find(document => document.id === session.activeId);
  const running = execution !== "idle";
  const locked = running && runDocumentId === active?.id;
  const output = active ? outputs[active.id] : undefined;
  const admittedOutputViews = admitDataViews(output?.views);
  const canShowOutput = output?.status === "completed" && output.return_code === 0 && admittedOutputViews.length > 0;
  const debugSourceMatches = Boolean(active && debug?.filename && (active.path ? pythonPathKey(active.path) === pythonPathKey(debug.filename) : pythonFileName(debug.filename) === active.name));
  const activeDebug = debugSourceMatches ? debug : null;
  const commit = (change: (current: PythonWorkspaceSession) => PythonWorkspaceSession) => {
    const next = change(sessionRef.current); sessionRef.current = next; setSession(next);
  };
  const updateDocument = (id: string, change: (document: PythonDocument) => PythonDocument) => commit(current => ({ ...current, documents: current.documents.map(document => document.id === id ? change(document) : document) }));
  const selectRoot = (root: string) => commit(current => ({ ...current, root, roots: [root, ...(current.roots ?? []).filter(item => pythonPathKey(item) !== pythonPathKey(root))].slice(0, 8) }));
  const saveState = (document: PythonDocument) => savingId === document.id ? "Saving…" : saveErrors[document.id] ? "Save failed" : pythonDirty(document) ? "Unsaved" : document.path ? "Saved" : "Draft";
  const activate = (id: string) => { commit(current => ({ ...current, activeId: id })); setCursor({ line: 1, column: 1 }); setFocusLine(undefined); };
  const addDocument = (document: PythonDocument) => {
    if (sessionRef.current.documents.length >= PYTHON_TAB_LIMIT) { setMessage(`Close a tab before opening another. The workspace allows ${PYTHON_TAB_LIMIT} tabs.`); return; }
    if (!pythonCodeFits(document.code)) { setMessage("This file exceeds the 512 KB script limit."); return; }
    commit(current => ({ ...current, documents: [...current.documents, document], activeId: document.id }));
    setFocusLine(current => ({ line: 1, revision: (current?.revision ?? 0) + 1 })); setCursor({ line: 1, column: 1 });
  };
  useEffect(() => {
    if (!initialScript || openedInitialScript.current === initialScript.id) return;
    openedInitialScript.current = initialScript.id;
    const name = initialScript.name.toLowerCase().endsWith(".py") ? initialScript.name : `${initialScript.name}.py`;
    if (!pythonCodeFits(initialScript.code)) { setMessage("This script exceeds the 512 KB script limit."); return; }
    if (sessionRef.current.documents.length >= PYTHON_TAB_LIMIT) { setMessage(`Close a tab before opening another. The workspace allows ${PYTHON_TAB_LIMIT} tabs.`); return; }
    const document = { ...newPythonDocument(initialScript.code, name), savedCode: "" };
    addDocument(document);
    setMessage(`${name} opened as an unsaved script. Review the source and choose Run.`);
  }, [initialScript]);
  useEffect(() => {
    setBackup(current => ({ ...current, pending: true }));
    const timer = window.setTimeout(() => setBackup(persistPythonWorkspace(session)), 750);
    return () => window.clearTimeout(timer);
  }, [session]);
  useEffect(() => { tabStrip.current?.querySelector<HTMLButtonElement>('[aria-selected="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" }); }, [session.activeId]);
  useEffect(() => {
    const flush = () => persistPythonWorkspace(sessionRef.current);
    window.addEventListener("pagehide", flush);
    return () => window.removeEventListener("pagehide", flush);
  }, []);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (activeRun.current) void cancelLocalWorkerCleanup(activeRun.current);
      if (debugSession.current) void runLocalWorker({ method: "python_debug_command", params: { session_id: debugSession.current, command: "stop" } });
      persistPythonWorkspace(sessionRef.current);
    };
  }, []);
  const publish = (result: PythonScriptResult) => {
    if (result.status !== "completed") return;
    if (!actionsApplied.current && Array.isArray(result.ui_actions) && result.ui_actions.length) {
      actionsApplied.current = true;
      try {
        if (runContextKey.current !== uiContext.current.contextKey) throw new Error("Board context changed during execution. Rerun the script to apply its interface actions.");
        const actions = admittedPythonUiActions(result.ui_actions, uiContext.current.context);
        if (!uiContext.current.onUiAction) throw new Error("Interface actions are unavailable in this window.");
        for (const action of actions) uiContext.current.onUiAction(action);
      } catch (error) { setMessage(`Interface actions: ${errorText(error)}`); }
    }
    if (!result.published_result) return;
    const provenance = (result.published_result as Record<string, unknown>)?.provenance as Record<string, unknown> | undefined;
    const published = extensionAnalysisResult("analyses", "spike/v1", { analysis_result: result.published_result, input_design_sha256: provenance?.design_digest_sha256 });
    if (published) window.dispatchEvent(new CustomEvent("spike-analysis-result", { detail: published }));
    else setMessage("Script finished, but its published result could not be displayed.");
  };
  const applyDebug = (snapshot: PythonDebugSnapshot, documentId: string) => {
    if (typeof snapshot.revision === "number" && snapshot.revision < debugRevision.current) return;
    if (typeof snapshot.revision === "number") debugRevision.current = snapshot.revision;
    if (pendingDebugSequence.current && (snapshot.command_ack ?? 0) >= pendingDebugSequence.current || debugFinished(snapshot.status)) { pendingDebugSequence.current = 0; setDebugBusy(false); }
    setDebug(snapshot); setOutputs(current => ({ ...current, [documentId]: snapshot }));
    if (snapshot.status === "paused") {
      const location = `${snapshot.filename}:${snapshot.line}:${snapshot.revision}`;
      setMessage(`Paused at ${pythonFileName(snapshot.filename ?? "script.py")}:${snapshot.line ?? "—"}. ${snapshot.reason ?? ""}`);
      const document = sessionRef.current.documents.find(item => item.id === sessionRef.current.activeId);
      const sourceMatches = document && snapshot.filename && (document.path ? pythonPathKey(document.path) === pythonPathKey(snapshot.filename) : pythonFileName(snapshot.filename) === document.name);
      if (location !== lastPause.current && sourceMatches && snapshot.line) setFocusLine(current => ({ line: snapshot.line!, revision: (current?.revision ?? 0) + 1 }));
      lastPause.current = location;
    }
    if (debugFinished(snapshot.status)) {
      debugSession.current = null; setExecution("idle"); setStopping(false);
      setMessage(`Debug session ${snapshot.status}${snapshot.stderr ? ": see standard error below." : "."}`);
      if (snapshot.status === "completed") publish(snapshot);
    }
  };
  useEffect(() => {
    if (execution !== "debug" || !runDocumentId) return;
    let cancelled = false, timer: number;
    const poll = async () => {
      const id = debugSession.current;
      if (!id || cancelled) return;
      try {
        const response = await runLocalWorker({ method: "python_debug_status", params: { session_id: id } });
        if (cancelled || id !== debugSession.current) return;
        if (!response.ok) throw new Error(response.error ?? "Debugger status failed.");
        const snapshot = response.result as unknown as PythonDebugSnapshot;
        if (snapshot?.contract !== "spike/python-debug/v1") throw new Error("Invalid debugger status response.");
        applyDebug(snapshot, runDocumentId);
        if (debugFinished(snapshot.status)) return;
      } catch (caught) { if (!cancelled) setMessage(`Debugger status: ${errorText(caught)}. Stop remains available.`); }
      if (!cancelled) timer = window.setTimeout(() => void poll(), 700);
    };
    timer = window.setTimeout(() => void poll(), 350);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [execution, runDocumentId]);
  const openPath = async (path: string, root: string) => {
    const fullPath = pythonAbsolutePath(root, path);
    const existing = sessionRef.current.documents.find(document => document.path && pythonPathKey(document.path) === pythonPathKey(fullPath));
    if (existing) { activate(existing.id); return true; }
    if (!desktop) { const document = sessionRef.current.documents.find(item => item.name === path); if (document) activate(document.id); return Boolean(document); }
    try {
      const response = await runLocalWorker({ method: "python_workspace_files", params: { action: "read", root, path: pythonRelativePath(root, path) } });
      if (!response.ok) throw new Error(response.error ?? "Could not open the file.");
      const result = response.result!;
      if (typeof result.contents !== "string" || typeof result.path !== "string" || typeof result.sha256 !== "string") throw new Error("The worker returned an invalid script file.");
      const absolute = pythonAbsolutePath(root, result.path);
      addDocument({ ...newPythonDocument(result.contents, pythonFileName(result.path)), path: absolute, root, sha256: result.sha256 });
      setMessage(`Opened ${absolute}`);
      return true;
    } catch (caught) { setMessage(`Open failed: ${errorText(caught)}`); return false; }
  };
  const open = async () => {
    if (!desktop) { fileInput.current?.click(); return; }
    try {
      const file = await openNativeTextFile("script");
      if (!file) return;
      const existing = sessionRef.current.documents.find(document => document.path && pythonPathKey(document.path) === pythonPathKey(file.path));
      if (existing) { activate(existing.id); return; }
      if (!pythonCodeFits(file.contents)) throw new Error("This file exceeds the 512 KB script limit.");
      const root = pythonParent(file.path);
      addDocument({ ...newPythonDocument(file.contents, file.fileName), path: file.path, root, sha256: await pythonCodeHash(file.contents) });
      selectRoot(root); setMessage(`Opened ${file.path}`);
    } catch (caught) { setMessage(`Open failed: ${errorText(caught)}`); }
  };
  const openFolder = async () => {
    try { const folder = await selectNativeImportFile("script", true); if (folder) { selectRoot(folder.path); setPane("files"); setPaneVisible(true); } }
    catch (caught) { setMessage(`Open folder failed: ${errorText(caught)}`); }
  };
  const saveDocument = async (documentId: string, saveAs = false): Promise<boolean> => {
    const document = sessionRef.current.documents.find(item => item.id === documentId);
    if (!document || saveInFlight.current) return false;
    const snapshot = { ...document };
    saveInFlight.current = true; setSaving(true); setSavingId(documentId);
    try {
      let path = snapshot.path, root = snapshot.root, sha256: string | undefined;
      if (desktop) {
        if (saveAs || !path) {
          path = await saveNativeTextFile(snapshot.name.endsWith(".py") ? snapshot.name : `${snapshot.name}.py`, snapshot.code, "script") ?? undefined;
          if (!path) return false;
          root = pythonParent(path); sha256 = await pythonCodeHash(snapshot.code);
        } else {
          const saveRoot = root ?? pythonParent(path);
          const response = await runLocalWorker({ method: "python_workspace_files", params: { action: "write", root: saveRoot, path: pythonRelativePath(saveRoot, path), contents: snapshot.code, expected_sha256: snapshot.sha256 } });
          if (!response.ok) throw new Error(response.error ?? "Could not save the file.");
          sha256 = response.result?.sha256 as string | undefined;
          if (!sha256) throw new Error("Save returned no file digest.");
        }
      } else {
        const name = snapshot.name.endsWith(".py") ? snapshot.name : `${snapshot.name}.py`;
        const url = URL.createObjectURL(new Blob([snapshot.code], { type: "text/x-python;charset=utf-8" }));
        const link = documentCreateLink(url, name); link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        setMessage(`Download requested for ${name}. The draft remains unsaved until saved to a file.`);
        return false;
      }
      updateDocument(documentId, current => savedPythonDocument(current, { code: snapshot.code, path, root, sha256 }));
      setSaveErrors(current => { const next = { ...current }; delete next[documentId]; return next; });
      setMessage(`Saved ${path}`);
      return sessionRef.current.documents.find(item => item.id === documentId)?.code === snapshot.code;
    } catch (caught) { setSaveErrors(current => ({ ...current, [documentId]: errorText(caught) })); setMessage(`Save failed: ${errorText(caught)} Use Save as to preserve your edits separately.`); return false; }
    finally { saveInFlight.current = false; setSaving(false); setSavingId(null); }
  };
  const saveAll = async () => { for (const document of sessionRef.current.documents.filter(pythonDirty)) if (!await saveDocument(document.id)) return; };
  const createTemplate = (template: PythonTemplate) => { addDocument({ ...newPythonDocument(template.code, `${template.id}.py`), savedCode: "" }); setMessage(`${template.title}: ${template.requirements.length ? `review ${template.requirements.join(", ")}.` : "ready to inspect or run."}`); };
  const newFile = () => {
    let index = sessionRef.current.documents.length + 1;
    while (sessionRef.current.documents.some(document => document.name === `untitled-${index}.py`)) index++;
    addDocument(newPythonDocument("", `untitled-${index}.py`));
  };
  const removeTab = (id: string) => {
    persistPythonWorkspace(sessionRef.current);
    commit(current => {
      const index = current.documents.findIndex(document => document.id === id);
      const documents = current.documents.filter(document => document.id !== id);
      return { ...current, documents, activeId: current.activeId === id ? documents[Math.min(index, documents.length - 1)]?.id ?? "" : current.activeId };
    }); setClosing(null);
  };
  const requestClose = (id?: string) => {
    if (saveInFlight.current && (!id || id === savingId)) { setMessage("Wait for the file save to finish before closing."); return; }
    if (running && (!id || id === runDocumentId)) { setMessage("Stop the script before closing its tab or workspace."); return; }
    const dirty = id ? sessionRef.current.documents.some(document => document.id === id && pythonDirty(document)) : sessionRef.current.documents.some(pythonDirty);
    if (dirty) setClosing(id ? { kind: "tab", id } : { kind: "workspace" });
    else if (id) removeTab(id);
    else { onStatus(message); onClose(); }
  };
  const finishClose = async (save: boolean) => {
    if (!closing) return;
    const target = closing;
    if (save) {
      const documents = sessionRef.current.documents.filter(document => pythonDirty(document) && (target.kind === "workspace" || target.id === document.id));
      for (const document of documents) if (!await saveDocument(document.id)) return;
    }
    if (target.kind === "tab") removeTab(target.id);
    else {
      persistPythonWorkspace(sessionRef.current);
      if (!save) commit(current => ({ ...current, documents: current.documents.map(document => ({ ...document, code: document.savedCode })) }));
      persistPythonWorkspace(sessionRef.current); onClose();
    }
  };
  const run = async (debugging = false, geometryOnly = false) => {
    const document = sessionRef.current.documents.find(item => item.id === sessionRef.current.activeId);
    if (!desktop || activeRun.current || debugSession.current || execution !== "idle" || !document?.code.trim()) return;
    if (debugging && interpreter.trim()) { setMessage("Debugging with a selected external interpreter is not supported. Clear Interpreter to use the worker default debugger."); return; }
    const preparedCode = geometryOnly ? emergeGeometryPreview(document.code) : document.code;
    if (!preparedCode) { setMessage("Model preview is available only for a bundled EMerge example script with retained geometry resources."); return; }
    const id = crypto.randomUUID(); activeRun.current = id;
    runContextKey.current = contextKey; actionsApplied.current = false;
    setOutputVisible(true); setInspectorVisible(true); setRunDocumentId(document.id); setExecution("run"); setRunStartedAt(performance.now()); setDebug(null); setStopping(false); lastPause.current = ""; debugRevision.current = -1; pendingDebugSequence.current = 0;
    setOutputs(current => ({ ...current, [document.id]: { status: "running" } })); setMessage(debugging ? "Starting debugger…" : geometryOnly ? "Loading bundled EMerge model geometry…" : "Running Python script…");
    try {
      const response = await runLocalWorker({ id, method: debugging ? "start_python_debug" : "run_python_script", params: { code: preparedCode, filename: document.path ?? document.name, working_directory: document.path ? pythonParent(document.path) : sessionRef.current.root, breakpoints: document.breakpoints, design, results, workspace: context, timeout_seconds: timeoutSeconds, ...(!debugging && interpreter.trim() ? { python_executable: interpreter.trim() } : {}) } });
      if (!mounted.current) return;
      if (!response.ok) throw new Error(response.error ?? "Python execution failed.");
      if (debugging) {
        const snapshot = response.result as unknown as PythonDebugSnapshot;
        if (snapshot?.contract !== "spike/python-debug/v1" || !snapshot.session_id) throw new Error("The worker returned an invalid debug session.");
        debugSession.current = snapshot.session_id; applyDebug(snapshot, document.id);
        if (!debugFinished(snapshot.status)) setExecution("debug");
      } else {
        const result = response.result as PythonScriptResult | undefined;
        if (result?.contract !== "spike/python-script-result/v1") throw new Error("The worker returned no Python script result.");
        setOutputs(current => ({ ...current, [document.id]: result }));
        const admittedViews = admitDataViews(result.views);
        if (result.status === "completed" && result.return_code === 0 && admittedViews.some(view => physicalGeometry(view)) && onShowViewport) {
          setFloating(true); onShowViewport(result, `${document.name} · ${geometryOnly ? "model preview" : "physical model"}`, true);
        }
        setMessage(result.status === "completed" ? `Script completed${typeof result.duration_ms === "number" ? ` in ${(result.duration_ms / 1000).toFixed(2)} s` : ""}.` : "Script failed: see standard error below."); publish(result);
      }
    } catch (caught) { setMessage(`Execution failed: ${errorText(caught)}`); setOutputs(current => ({ ...current, [document.id]: { status: "failed", stderr: errorText(caught) } })); setExecution("idle"); }
    finally { activeRun.current = null; if (!debugging) { setExecution("idle"); setStopping(false); } }
  };
  const debugCommand = async (command: string, breakpoints?: number[]) => {
    const id = debugSession.current;
    if (!id || command !== "stop" && (debugCommandActive.current || pendingDebugSequence.current > 0)) return;
    debugCommandActive.current = true;
    setDebugBusy(true);
    try {
      const response = await runLocalWorker({ method: "python_debug_command", params: { session_id: id, command, breakpoints } });
      if (!response.ok) throw new Error(response.error ?? "Debug command failed.");
      const snapshot = response.result as unknown as PythonDebugSnapshot;
      if (snapshot.command_pending) pendingDebugSequence.current = snapshot.command_sequence ?? snapshot.command_pending;
      if (snapshot?.contract === "spike/python-debug/v1" && runDocumentId) applyDebug(snapshot, runDocumentId);
    } catch (caught) { setMessage(`Debugger: ${errorText(caught)}`); }
    finally { debugCommandActive.current = false; setDebugBusy(pendingDebugSequence.current > 0); }
  };
  const stop = async () => {
    if (stopping) return;
    setStopping(true);
    if (debugSession.current) { await debugCommand("stop"); setStopping(false); }
    else if (activeRun.current) {
      const accepted = await cancelLocalWorker(activeRun.current);
      setMessage(accepted ? "Stop requested; waiting for worker shutdown." : "The worker did not accept Stop. Try again."); if (!accepted) setStopping(false);
    }
  };
  const breakpoint = (line: number) => {
    if (!active || locked && (debugCommandActive.current || pendingDebugSequence.current > 0)) return;
    const points = togglePythonBreakpoint(active.breakpoints, line, active.code.split("\n").length);
    updateDocument(active.id, document => ({ ...document, breakpoints: points }));
    if (locked && debugSession.current) void debugCommand("breakpoints", points);
  };
  const clearBreakpoints = () => {
    if (!active || locked && (debugCommandActive.current || pendingDebugSequence.current > 0)) return;
    updateDocument(active.id, document => ({ ...document, breakpoints: [] }));
    if (locked && debugSession.current) void debugCommand("breakpoints", []);
  };
  const shortcut = (event: KeyboardEvent) => {
    // Keep project-level window shortcuts away from editor and dialog input.
    event.stopPropagation();
    if (closing) return;
    const control = event.ctrlKey || event.metaKey;
    if (control && ["s", "o", "n", "w"].includes(event.key.toLowerCase())) {
      event.preventDefault();
      if (event.key.toLowerCase() === "s" && active && !saving) void saveDocument(active.id, event.shiftKey);
      if (event.key.toLowerCase() === "o") void open();
      if (event.key.toLowerCase() === "n") newFile();
      if (event.key.toLowerCase() === "w" && active) requestClose(active.id);
    } else if (control && event.key === "Enter") { event.preventDefault(); void run(); }
    else if (["F5", "F9", "F10", "F11"].includes(event.key)) {
      event.preventDefault();
      if (event.key === "F9") breakpoint(cursor.line);
      if (event.key === "F5") void (debugSession.current ? debugCommand("continue") : run(true));
      if (event.key === "F10" && debug?.status === "paused") void debugCommand("step_over");
      if (event.key === "F11" && debug?.status === "paused") void debugCommand(event.shiftKey ? "step_out" : "step_into");
    }
  };
  const gotoLine = async (line: number, filename?: string) => {
    if (filename && active && !(active.path ? pythonPathKey(active.path) === pythonPathKey(filename) : pythonFileName(filename) === active.name)) {
      const runDocument = sessionRef.current.documents.find(document => document.id === runDocumentId);
      if (!runDocument?.root || !await openPath(filename, runDocument.root)) { setMessage(`Stack frame ${filename}:${line}. Open its folder from Files to inspect its source.`); return; }
    }
    setFocusLine(current => ({ line, revision: (current?.revision ?? 0) + 1 }));
  };
  const paused = debug?.status === "paused" && execution === "debug";
  return <div className={`modal-shade python-workspace-shade ${floating ? "python-floating-shade" : ""}`}><section style={floating ? { left: floatingRect.x, top: floatingRect.y, width: floatingRect.width, height: floatingRect.height } : undefined} className={`python-workspace ${floating ? "python-floating" : ""} ${running ? "is-running" : ""}`} role="dialog" aria-modal={!floating} aria-label="Python workspace" onKeyDown={shortcut}>
    <header onPointerDown={event => beginFloatingGesture(event, "move")} onPointerMove={moveFloatingGesture} onPointerUp={endFloatingGesture} onPointerCancel={endFloatingGesture} title={floating ? "Drag this title bar to move the Python panel" : undefined}><div><Code2 size={20} /><span><b>PYTHON WORKSPACE</b><small>Files, analysis scripts and local debugging</small></span></div><div className="python-window-actions"><button type="button" className="canvas-icon" onClick={() => setFloating(value => !value)} aria-label={floating ? "Center Python window" : "Float Python window"} title={floating ? "Restore centered workspace" : "Float Python while using the viewport"}>{floating ? <Maximize2 size={16} /> : <Minimize2 size={16} />}</button><button type="button" className="canvas-icon" onClick={() => requestClose()} disabled={running} aria-label="Close Python workspace"><X size={16} /></button></div></header>
    <div className="python-workspace-toolbar" aria-label="Python file and execution controls">
      <button type="button" onClick={newFile} title="New script (Ctrl+N)"><FilePlus2 size={14} /> New</button><button type="button" onClick={() => void open()} title="Open script (Ctrl+O)"><FolderOpen size={14} /> Open</button>
      <button type="button" onClick={() => active && void saveDocument(active.id)} disabled={!active || saving} title="Save current file (Ctrl+S)"><Save size={14} /> Save</button><button type="button" onClick={() => active && void saveDocument(active.id, true)} disabled={!active || saving} title="Save to another file (Ctrl+Shift+S)">Save as</button><button type="button" onClick={() => void saveAll()} disabled={saving || !session.documents.some(pythonDirty)} title="Save all changed files"><SaveAll size={14} /> Save all</button>
      <button type="button" onClick={() => void run(false, true)} disabled={!desktop || running || !active || !onShowViewport || !emergeGeometryPreview(active.code)} title="Load physical geometry from a retained bundled EMerge example without solving"><Code2 size={14} /> Load model</button>
      <span className="python-toolbar-spacer" />
      <label className="python-runtime-label" title="Absolute path to a local Python interpreter. Leave empty to use the worker default."><span>Interpreter</span><input aria-label="Python interpreter path" placeholder="Worker default" value={interpreter} disabled={running} onChange={event => { setInterpreter(event.target.value); try { localStorage.setItem("spike-python-interpreter", event.target.value); } catch { /* Workspace recovery reports unavailable local storage elsewhere. */ } }} /></label>
      <label className="python-workspace-timeout">Limit <input aria-label="Python time limit in seconds" type="number" min={1} max={600} value={timeoutSeconds} disabled={running} onChange={event => setTimeoutSeconds(Math.max(1, Math.min(600, Number(event.target.value) || 1)))} /> s</label>
      <button type="button" className="python-run-button" onClick={() => void run()} disabled={!desktop || running || !active?.code.trim()} title="Run active script (Ctrl+Enter)"><Play size={14} /> Run</button><button type="button" onClick={() => void (paused ? debugCommand("continue") : run(true))} disabled={!desktop || debugBusy || !paused && (!active?.code.trim() || running || Boolean(interpreter.trim()))} title={paused ? "Continue (F5)" : interpreter.trim() ? "Debugging with a selected external interpreter is not supported; clear Interpreter to use the worker default." : "Debug active script (F5)"}><Bug size={14} />{paused ? "Continue" : running ? "Debug unavailable" : "Debug"}</button>
      {running && <button type="button" onClick={() => void stop()} disabled={stopping} title="Stop execution"><Square size={14} />{stopping ? "Stopping…" : "Stop"}</button>}
    </div>
    {running && <PythonRunStatus startedAt={runStartedAt} name={session.documents.find(document => document.id === runDocumentId)?.name ?? active?.name ?? "Python script"} stopping={stopping} timeoutSeconds={timeoutSeconds} />}
    <input ref={fileInput} type="file" accept=".py,text/x-python,text/plain" multiple className="hidden-input" aria-label="Open Python scripts" onChange={event => { for (const file of Array.from(event.target.files ?? [])) void file.text().then(code => addDocument(newPythonDocument(code, file.name))).catch(caught => setMessage(`Open failed: ${errorText(caught)}`)); event.target.value = ""; }} />
    <div className="python-workspace-body">
      <nav className="python-activity-bar" aria-label="Python workspace panels">{([{ id: "files", label: "Files", icon: Files }, { id: "templates", label: "Templates", icon: Library }, { id: "nets", label: "Nets", icon: Files }, { id: "backups", label: "Backups", icon: History }, { id: "help", label: "Help", icon: BookOpen }] as const).map(item => <button type="button" key={item.id} aria-label={item.label} title={`${item.label} · Click again to hide`} aria-pressed={pane === item.id && paneVisible} onClick={() => { if (pane === item.id) setPaneVisible(current => !current); else { setPane(item.id); setPaneVisible(true); } }}><item.icon size={17} /><small>{item.label}</small></button>)}</nav>
      {paneVisible && <aside className="python-workspace-sidebar">{pane === "files" ? <PythonFileExplorer root={session.root} roots={session.roots} activeId={active?.id} onActivate={activate} documents={session.documents} activePath={active?.path} desktop={desktop} onRoot={selectRoot} onOpenFolder={() => void openFolder()} onOpenFile={(path, root) => void openPath(path, root)} /> : pane === "templates" ? <PythonTemplateLibrary onCreate={createTemplate} /> : pane === "nets" ? <PythonNetBrowser workspace={context} disabled={!active || locked} onInsert={text => setInsertion(current => ({ text, revision: (current?.revision ?? 0) + 1 }))} onAction={onUiAction} /> : pane === "backups" ? <PythonRecoveryPanel revision={backup.timestamp ?? 0} disabled={session.documents.length >= PYTHON_TAB_LIMIT} onRestore={document => { addDocument(document); setMessage(`Recovered ${document.name} into a separate unsaved tab.`); }} /> : <PythonWorkspaceHelp onTemplate={id => { const template = PYTHON_TEMPLATES.find(item => item.id === id); if (template) createTemplate(template); }} />}</aside>}
      <main className="python-workspace-center">
        <div className="python-tab-bar"><div ref={tabStrip} className="python-document-tabs" role="tablist" aria-label="Open Python files">{session.documents.map(document => <div key={document.id} className={active?.id === document.id ? "active" : ""}><button type="button" role="tab" tabIndex={active?.id === document.id ? 0 : -1} aria-label={`${document.name} · ${saveState(document)}`} aria-selected={active?.id === document.id} onClick={() => activate(document.id)} onKeyDown={event => { if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return; event.preventDefault(); const index = session.documents.indexOf(document); const next = event.key === "Home" ? 0 : event.key === "End" ? session.documents.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + session.documents.length) % session.documents.length; activate(session.documents[next].id); tabStrip.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus(); }} title={document.path ?? document.name}><FilePlus2 size={12} /><span>{document.name}</span>{pythonDirty(document) && <span className="python-tab-dirty" aria-label="Unsaved changes">●</span>}<small className={`python-save-state ${saveErrors[document.id] ? "failed" : pythonDirty(document) ? "dirty" : ""}`}>{saveState(document)}</small>{runDocumentId === document.id && running && <span>▶</span>}</button><button type="button" aria-label={`Close ${document.name}`} disabled={savingId === document.id || running && runDocumentId === document.id} onClick={() => requestClose(document.id)}><X size={12} /></button></div>)}</div><button type="button" className="python-add-tab" aria-label="Add Python tab" title="New script (Ctrl+N)" disabled={session.documents.length >= PYTHON_TAB_LIMIT} onClick={newFile}><Plus size={16} /></button></div>
        <div className="python-editor-context"><span title={active?.path}>{active?.path ?? active?.name ?? "No file open"}</span>{active && <strong className={`python-save-state ${saveErrors[active.id] ? "failed" : pythonDirty(active) ? "dirty" : ""}`} title={saveErrors[active.id]}>{saveState(active)}</strong>}<small>{design ? "Design attached" : "No design"} · {results ? "Results attached" : "No result"}{locked ? " · execution snapshot locked" : ""}</small>{debug && <button type="button" aria-pressed={inspectorVisible} onClick={() => setInspectorVisible(current => !current)}>Inspector</button>}</div>
        {execution === "debug" && <div className="python-debug-toolbar"><span>{debug?.status ?? "starting"}{debug?.line ? ` · line ${debug.line}` : ""}</span><button type="button" onClick={() => void debugCommand("pause")} disabled={debugBusy || debug?.status !== "running"}><Pause size={13} /> Pause</button><button type="button" onClick={() => void debugCommand("step_over")} disabled={debugBusy || !paused} title="Step over (F10)"><StepForward size={13} /> Over</button><button type="button" onClick={() => void debugCommand("step_into")} disabled={debugBusy || !paused} title="Step into (F11)">Into</button><button type="button" onClick={() => void debugCommand("step_out")} disabled={debugBusy || !paused} title="Step out (Shift+F11)"><StepBack size={13} /> Out</button></div>}
        <div className="python-editor-area">{active ? <PythonCodeEditor key={active.id} documentKey={active.id} workspace={context} insertion={insertion} onInserted={() => setInsertion(undefined)} code={active.code} breakpoints={active.breakpoints} executionLine={activeDebug?.status === "paused" ? activeDebug.line : undefined} locked={locked} focusLine={focusLine} onChange={code => { if (pythonCodeFits(code)) updateDocument(active.id, document => ({ ...document, code, breakpoints: remapPythonBreakpoints(document.code, code, document.breakpoints) })); else setMessage("Script exceeds the 512 KB editor limit."); }} onBreakpoint={breakpoint} onCursor={(line, column) => setCursor({ line, column })} onShortcut={() => undefined} /> : <div className="python-empty-editor"><Code2 size={36} /><h3>Open a script or start from a template</h3><button type="button" onClick={newFile}>New Python file</button><button type="button" onClick={() => { setPane("templates"); setPaneVisible(true); }}>Browse templates</button></div>}
          {debug && inspectorVisible && <PythonDebugPanel snapshot={debug} breakpoints={active?.breakpoints ?? []} onLine={(line, filename) => void gotoLine(line, filename)} onRemove={breakpoint} onClear={clearBreakpoints} />}
        </div>
        <div className={`python-workspace-output ${outputVisible ? "" : "collapsed"}`}><div className="python-output-heading"><button type="button" aria-label={outputVisible ? "Collapse output" : "Expand output"} aria-expanded={outputVisible} onClick={() => setOutputVisible(current => !current)}>{outputVisible ? <ChevronDown size={12} /> : <ChevronUp size={12} />}<b>OUTPUT</b></button><span>{output ? `${output.status ?? "unknown"}${output.return_code !== undefined ? ` · exit ${output.return_code}` : ""}` : "print() and exceptions appear here"}</span><button type="button" disabled={!onShowViewport || !canShowOutput} title="Show admitted script data in the main viewport" onClick={() => { if (onShowViewport && canShowOutput && output) onShowViewport(output, active?.name ?? "Python result", floating); }}>Show in viewport</button><button type="button" disabled={!onAttachDataset || !output?.published_result} title="Attach the published analysis result to a project study" onClick={() => { try { if (onAttachDataset && output?.published_result) setMessage(onAttachDataset(active?.name ?? "Python result", output.published_result)); } catch (error) { setMessage(errorText(error)); } }}>Attach to study</button><button type="button" disabled={locked} onClick={() => active && setOutputs(current => { const next = { ...current }; delete next[active.id]; return next; })}>Clear</button></div>{outputVisible && <div className="python-output-body">{output?.runtime && <small className="python-runtime-result">Python {output.runtime.python_version ?? "unknown"} · {output.runtime.executable}{output.runtime.emerge_version ? ` · EMerge ${output.runtime.emerge_version}` : ""}{output.runtime.optycal_version ? ` · Optycal ${output.runtime.optycal_version}` : ""}</small>}<pre aria-label="Python standard output">{output?.stdout || "No standard output yet."}</pre>{output?.stderr && <pre className="python-workspace-stderr" aria-label="Python standard error">{output.stderr}</pre>}</div>}</div>
      </main>
    </div>
    <footer><span role="status" title={message}>{message}</span><button type="button" className={`python-backup-status ${backup.ok ? "" : "failed"}`} title={backup.error ?? "Local recovery snapshots; Save writes your file."} onClick={() => { setPane("backups"); setPaneVisible(true); }}>{backup.ok ? backup.pending ? "Backing up…" : `Backed up${backup.timestamp ? ` ${new Date(backup.timestamp).toLocaleTimeString()}` : ""}` : "Backup unavailable"}</button><small>Ln {cursor.line}, Col {cursor.column} · Python{!desktop ? " · desktop required to run" : ""}</small><button type="button" onClick={() => requestClose()} disabled={running}>Close</button></footer>
    {!backup.ok && <p className="python-backup-error" role="alert">{backup.error ?? "Automatic recovery is unavailable. Save scripts to files."}</p>}
    {closing && <div className="python-close-shade"><section role="alertdialog" aria-modal="true" aria-label="Unsaved Python changes"><h3>Save your Python changes?</h3><p>{closing.kind === "tab" ? session.documents.find(document => document.id === closing.id)?.name : `${session.documents.filter(pythonDirty).length} changed files`} {closing.kind === "tab" ? "has" : "have"} unsaved edits.</p><div><button type="button" onClick={() => void finishClose(true)} disabled={saving}>Save and close</button><button type="button" onClick={() => void finishClose(false)} disabled={saving}>Discard edits</button><button type="button" onClick={() => setClosing(null)} disabled={saving} autoFocus>Cancel</button></div></section></div>}
    {floating && <button type="button" className="python-resize-handle" aria-label="Resize Python window" title="Drag to resize; arrow keys resize by 20 px" onPointerDown={event => beginFloatingGesture(event, "resize")} onPointerMove={moveFloatingGesture} onPointerUp={endFloatingGesture} onPointerCancel={endFloatingGesture} onKeyDown={event => { const changes: Record<string, [number, number]> = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] }; const change = changes[event.key]; if (change) { event.preventDefault(); setFloatingRect(rect => boundFloatingRect({ ...rect, width: rect.width + change[0], height: rect.height + change[1] }, window.innerWidth, window.innerHeight)); } }}>◢</button>}
  </section></div>;
}

function documentCreateLink(url: string, name: string): HTMLAnchorElement {
  const link = document.createElement("a"); link.href = url; link.download = name; return link;
}
