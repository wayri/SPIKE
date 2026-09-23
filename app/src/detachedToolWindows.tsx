// SPDX-License-Identifier: MIT

import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import {
  isToolWindowKind,
  decodeDetachedRowId,
  normalizeDetachedToolAction,
  normalizeDetachedToolSnapshot,
  type DetachedToolAction,
  type DetachedToolControl,
  type DetachedToolSnapshot,
  type ToolWindowKind,
} from "./detachedToolWindowModel";
import "./detachedToolWindows.css";

export type { DetachedToolAction, DetachedToolControl, DetachedToolSnapshot, ToolWindowKind } from "./detachedToolWindowModel";

const SNAPSHOT_EVENT = "spike-tool-snapshot";
const ACTION_EVENT = "spike-tool-action";
const CHANNEL_NAME = "spike-detached-tools-v1";
const labels: Record<ToolWindowKind, string> = { results: "spike-tool-results", probes: "spike-tool-probes", "trace-plots": "spike-tool-trace-plots" };
const TraceResultsWorkbench = lazy(() => import("./TraceResultsWorkbench"));
const windows = new Map<ToolWindowKind, Window>();
const snapshots = new Map<ToolWindowKind, DetachedToolSnapshot>();
const handlers = new Map<ToolWindowKind, (action: DetachedToolAction) => void>();
const browserChannels = new Map<ToolWindowKind, BroadcastChannel>();
const sessionTokens = new Map<ToolWindowKind, string>();
let nativeActionUnlisten: (() => void) | null = null;

function isNative(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

type ToolEnvelope<T> = { token: string; payload: T };

function randomToken(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  return Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
}

function tokenFor(kind: ToolWindowKind): string {
  const token = sessionTokens.get(kind) ?? randomToken();
  sessionTokens.set(kind, token);
  return token;
}

function cleanupSession(kind: ToolWindowKind, expectedToken?: string): void {
  if (expectedToken && sessionTokens.get(kind) !== expectedToken) return;
  windows.delete(kind);
  snapshots.delete(kind);
  handlers.delete(kind);
  browserChannels.get(kind)?.close();
  browserChannels.delete(kind);
  sessionTokens.delete(kind);
}

function queryUrl(kind: ToolWindowKind, token: string): string {
  const url = new URL(window.location.href);
  url.search = "";
  url.hash = "";
  url.searchParams.set("spikeTool", kind);
  url.searchParams.set("spikeToolToken", token);
  return `${url.pathname}${url.search}`;
}

function dispatchAction(value: unknown): void {
  if (!value || typeof value !== "object") return;
  const envelope = value as Partial<ToolEnvelope<unknown>>;
  const candidate = envelope.payload as { kind?: unknown } | undefined;
  if (!candidate || !isToolWindowKind(candidate.kind) || envelope.token !== sessionTokens.get(candidate.kind)) return;
  const action = normalizeDetachedToolAction(candidate, candidate.kind);
  if (!action) return;
  if (action.rowId) {
    if (!snapshots.get(action.kind)?.rows.some(row => row.id === action.rowId)) return;
    const decoded = decodeDetachedRowId(action.rowId);
    if (decoded === null) return;
    action.rowId = decoded;
  }
  if (action.type === "ready") { void publishSnapshot(action.kind); handlers.get(action.kind)?.(action); return; }
  const handler = handlers.get(action.kind);
  handler?.(action);
  if (action.type === "closed") cleanupSession(action.kind, envelope.token);
}

type NativeCreationHandle = {
  once<T>(event: string, handler: (event: { payload: T }) => void): Promise<() => void>;
};

/** Resolves on the native created event and rejects with the native error payload. */
export async function awaitNativeWindowCreated(child: NativeCreationHandle): Promise<void> {
  let resolveCreated!: () => void;
  let rejectCreated!: (reason: Error) => void;
  const outcome = new Promise<void>((resolve, reject) => { resolveCreated = resolve; rejectCreated = reject; });
  const [stopCreated, stopError, stopDestroyed] = await Promise.all([
    child.once("tauri://created", () => resolveCreated()),
    child.once<unknown>("tauri://error", event => {
      let detail = "unknown native error";
      if (typeof event.payload === "string") detail = event.payload;
      else if (event.payload instanceof Error) detail = event.payload.message;
      else try { detail = JSON.stringify(event.payload ?? detail); } catch { /* Keep the safe fallback. */ }
      rejectCreated(new Error(`Detached tool window creation failed: ${detail}`));
    }),
    child.once("tauri://destroyed", () => rejectCreated(new Error("Detached tool window was destroyed before creation completed"))),
  ]);
  try { await outcome; }
  finally { stopCreated(); stopError(); stopDestroyed(); }
}

function ensureBrowserChannel(kind: ToolWindowKind): BroadcastChannel {
  let channel = browserChannels.get(kind);
  if (!channel) {
    channel = new BroadcastChannel(`${CHANNEL_NAME}:${tokenFor(kind)}`);
    channel.addEventListener("message", event => {
      if (event.data?.channel === "action") dispatchAction(event.data.envelope);
    });
    browserChannels.set(kind, channel);
  }
  return channel;
}

async function ensureNativeActionListener(): Promise<void> {
  if (nativeActionUnlisten) return;
  const { listen } = await import("@tauri-apps/api/event");
  nativeActionUnlisten = await listen(ACTION_EVENT, event => dispatchAction(event.payload));
}

async function publishSnapshot(kind: ToolWindowKind): Promise<void> {
  const snapshot = snapshots.get(kind);
  if (!snapshot) return;
  if (isNative()) {
    const { emitTo } = await import("@tauri-apps/api/event");
    await emitTo(labels[kind], SNAPSHOT_EVENT, { token: tokenFor(kind), payload: snapshot } satisfies ToolEnvelope<DetachedToolSnapshot>);
  } else {
    ensureBrowserChannel(kind).postMessage({ channel: "snapshot", envelope: { token: tokenFor(kind), payload: snapshot } });
  }
}

export async function openDetachedToolWindow(
  kind: ToolWindowKind,
  snapshot: DetachedToolSnapshot,
  onAction: (action: DetachedToolAction) => void,
): Promise<{ mode: "native" | "browser"; created: boolean }> {
  const hadSession = sessionTokens.has(kind);
  snapshots.set(kind, normalizeDetachedToolSnapshot({ ...snapshot, kind }));
  handlers.set(kind, onAction);
  const token = tokenFor(kind);
  if (isNative()) {
    try {
      await ensureNativeActionListener();
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
      let current = await WebviewWindow.getByLabel(labels[kind]);
      if (current && !hadSession) {
        await current.close();
        current = null;
      }
      if (current) {
        await current.show();
        await current.setFocus();
        await publishSnapshot(kind);
        return { mode: "native", created: false };
      }
      const child = new WebviewWindow(labels[kind], {
        url: queryUrl(kind, token), title: `SPIKE | ${snapshot.title}`, width: kind === "probes" ? 1120 : 980,
        height: 680, minWidth: 520, minHeight: 360, resizable: true, decorations: true,
        backgroundColor: "#101820", dragDropEnabled: false,
      });
      const stopDestroyed = await child.once("tauri://destroyed", () => {
        dispatchAction({ token, payload: { kind, type: "closed" } });
      });
      try {
        await awaitNativeWindowCreated(child);
        await publishSnapshot(kind);
        return { mode: "native", created: true };
      } catch (error) {
        stopDestroyed();
        try { await child.close(); } catch { /* Creation errors can leave no closable native handle. */ }
        throw error;
      }
    } catch (error) {
      cleanupSession(kind, token);
      throw error;
    }
  }
  ensureBrowserChannel(kind);
  const existing = windows.get(kind);
  if (existing && !existing.closed) {
    existing.focus();
    await publishSnapshot(kind);
    return { mode: "browser", created: false };
  }
  const child = window.open(queryUrl(kind, token), `${labels[kind]}-${token}`, `popup=yes,width=${kind === "probes" ? 1120 : 980},height=680,resizable=yes,scrollbars=yes`);
  if (!child) {
    cleanupSession(kind, token);
    throw new Error("The browser blocked the detached tool window. Allow popups for this local SPIKE origin and retry.");
  }
  windows.set(kind, child);
  return { mode: "browser", created: true };
}

export async function updateDetachedToolWindow(kind: ToolWindowKind, snapshot: DetachedToolSnapshot): Promise<void> {
  snapshots.set(kind, normalizeDetachedToolSnapshot({ ...snapshot, kind }));
  await publishSnapshot(kind);
}

export async function closeDetachedToolWindow(kind: ToolWindowKind): Promise<void> {
  const token = sessionTokens.get(kind);
  try {
    if (isNative()) {
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
      await (await WebviewWindow.getByLabel(labels[kind]))?.close();
    } else windows.get(kind)?.close();
  } finally { cleanupSession(kind, token); }
}

export async function closeAllDetachedToolWindows(): Promise<void> {
  await Promise.all((["results", "probes", "trace-plots"] as const).map(closeDetachedToolWindow));
  nativeActionUnlisten?.();
  nativeActionUnlisten = null;
  browserChannels.forEach(channel => channel.close());
  browserChannels.clear();
  sessionTokens.clear();
}

export function detachedToolKindFromLocation(search = window.location.search): ToolWindowKind | null {
  const value = new URLSearchParams(search).get("spikeTool");
  return isToolWindowKind(value) ? value : null;
}

async function emitChildAction(action: DetachedToolAction): Promise<void> {
  const token = new URLSearchParams(window.location.search).get("spikeToolToken");
  if (!token || !/^[a-f0-9]{48}$/.test(token)) return;
  const envelope: ToolEnvelope<DetachedToolAction> = { token, payload: action };
  if (isNative()) {
    const { emitTo } = await import("@tauri-apps/api/event");
    await emitTo("main", ACTION_EVENT, envelope);
  } else {
    const channel = new BroadcastChannel(`${CHANNEL_NAME}:${token}`);
    channel.postMessage({ channel: "action", envelope });
    channel.close();
  }
}

function ToolControl({ control, emit }: { control: DetachedToolControl; emit: (value: string | boolean) => void }) {
  if (control.kind === "button") return <button className="detached-tool-button" disabled={control.disabled} title={control.title} onClick={() => emit(true)}>{control.label}</button>;
  if (control.kind === "toggle") return <label className="detached-tool-control detached-tool-toggle" title={control.title}><input type="checkbox" checked={Boolean(control.value)} disabled={control.disabled} onChange={event => emit(event.target.checked)} /><span>{control.label}</span></label>;
  if (control.kind === "select") return <label className="detached-tool-control" title={control.title}><span>{control.label}</span><select value={String(control.value ?? "")} disabled={control.disabled} onChange={event => emit(event.target.value)}>{control.options?.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
  return <label className="detached-tool-control" title={control.title}><span>{control.label}</span><input type="text" value={String(control.value ?? "")} disabled={control.disabled} onChange={event => emit(event.target.value)} /></label>;
}

function EditableCell({ value, commit }: { value: string | number | null; commit: (value: string) => void }) {
  const [draft, setDraft] = useState(String(value ?? ""));
  useEffect(() => setDraft(String(value ?? "")), [value]);
  return <input className="detached-tool-cell-input" aria-label="Editable table value" type="text" value={draft} onChange={event => setDraft(event.target.value)} onBlur={() => { if (draft !== String(value ?? "")) commit(draft); }} onKeyDown={event => { if (event.key === "Enter") event.currentTarget.blur(); }} />;
}

export function DetachedToolContent({ snapshot, kind, onAction }: {
  snapshot: DetachedToolSnapshot | null;
  kind: ToolWindowKind;
  onAction: (action: Omit<DetachedToolAction, "kind">) => void;
}) {
  if (kind === "trace-plots") return <main className="detached-tool-root" data-detached-tool={kind}>
    <header className="detached-tool-header"><div><span className="detached-tool-eyebrow">SPIKE ENGINEERING RESULTS</span><h1>{snapshot?.title ?? "Trace graphs"}</h1><p>{snapshot?.trace?.notice ?? "Waiting for the workspace state..."}</p></div><button className="detached-tool-button detached-tool-button-primary" onClick={() => onAction({ type: "redock" })}>Return to workspace</button></header>
    <section className="detached-tool-trace">{snapshot?.trace ? <Suspense fallback={<p className="detached-tool-empty">Loading trace graphs...</p>}><TraceResultsWorkbench result={snapshot.trace.result} domain={snapshot.trace.domain} /></Suspense> : <p className="detached-tool-empty">Waiting for the workspace state...</p>}</section>
  </main>;
  const hasActions = Boolean(snapshot?.rowActions?.length || snapshot?.rows.some(row => row.actions?.length));
  return <main className="detached-tool-root" data-detached-tool={kind}>
    <header className="detached-tool-header"><div><span className="detached-tool-eyebrow">{kind === "results" ? "SPIKE ANALYSIS RESULTS" : "SPIKE MEASUREMENT TABLE"}</span><h1>{snapshot?.title ?? (kind === "results" ? "Results" : "Probe table")}</h1>{snapshot?.status && <p>{snapshot.status}</p>}</div><button className="detached-tool-button detached-tool-button-primary" onClick={() => onAction({ type: "redock" })}>Return to workspace</button></header>
    {snapshot?.controls?.length ? <section className="detached-tool-toolbar" aria-label={`${snapshot.title} controls`}>{snapshot.controls.map(control => <ToolControl key={control.id} control={control} emit={value => onAction({ type: "control-change", controlId: control.id, value })} />)}</section> : null}
    {!snapshot ? <p className="detached-tool-empty">Waiting for the workspace state...</p> : snapshot.rows.length === 0 ? <p className="detached-tool-empty">{snapshot.emptyMessage}</p> : <div className="detached-tool-table-scroll"><table className="detached-tool-table">
      <thead><tr>{snapshot.columns.map((column, index) => <th key={`${column}-${index}`}>{column}</th>)}{hasActions ? <th>Actions</th> : null}</tr></thead>
      <tbody>{snapshot.rows.map(row => { const actions = row.actions ?? snapshot.rowActions ?? []; return <tr key={row.id} title={row.title}>{row.cells.map((cell, index) => <td key={index}>{row.editActions?.[index] ? <EditableCell value={cell} commit={value => onAction({ type: "row-action", rowId: row.id, actionId: row.editActions![index], value })} /> : cell ?? "-"}</td>)}{hasActions ? <td className="detached-tool-row-actions">{actions.map(action => <button className={`detached-tool-button detached-tool-button-small${action.destructive ? " destructive" : ""}`} key={action.id} onClick={() => onAction({ type: "row-action", rowId: row.id, actionId: action.id })}>{action.label}</button>)}</td> : null}</tr>; })}</tbody>
    </table></div>}
  </main>;
}

export function DetachedToolWindowRoot({ kind }: { kind: ToolWindowKind }) {
  const [snapshot, setSnapshot] = useState<DetachedToolSnapshot | null>(null);
  const label = useMemo(() => labels[kind], [kind]);
  const token = useMemo(() => new URLSearchParams(window.location.search).get("spikeToolToken"), []);
  useEffect(() => {
    let disposed = false;
    let unlisten: (() => void) | undefined;
    let channel: BroadcastChannel | undefined;
    const receive = (value: unknown) => {
      const envelope = value as Partial<ToolEnvelope<DetachedToolSnapshot>>;
      if (!token || envelope.token !== token) return;
      const candidate = envelope.payload;
      if (!disposed && candidate?.kind === kind) setSnapshot(normalizeDetachedToolSnapshot(candidate));
    };
    void (async () => {
      if (isNative()) {
        const { listen } = await import("@tauri-apps/api/event");
        const stop = await listen(SNAPSHOT_EVENT, event => receive(event.payload), { target: { kind: "WebviewWindow", label } });
        if (disposed) stop();
        else unlisten = stop;
      } else {
        if (!token) return;
        channel = new BroadcastChannel(`${CHANNEL_NAME}:${token}`);
        channel.addEventListener("message", event => { if (event.data?.channel === "snapshot") receive(event.data.envelope); });
      }
      await emitChildAction({ kind, type: "ready" });
    })();
    const beforeUnload = () => { void emitChildAction({ kind, type: "closed" }); };
    window.addEventListener("beforeunload", beforeUnload);
    return () => { disposed = true; unlisten?.(); channel?.close(); window.removeEventListener("beforeunload", beforeUnload); };
  }, [kind, label, token]);
  const act = (action: Omit<DetachedToolAction, "kind">) => { void emitChildAction({ kind, ...action }); };
  useEffect(() => {
    document.title = `SPIKE | ${snapshot?.title ?? (kind === "results" ? "Results" : kind === "probes" ? "Probe results" : "Trace graphs")}`;
  }, [kind, snapshot?.title]);
  return <DetachedToolContent snapshot={snapshot} kind={kind} onAction={act} />;
}
