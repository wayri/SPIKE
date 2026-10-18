// SPDX-License-Identifier: Apache-2.0
import { awaitNativeWindowCreated } from "./detachedToolWindows";
import {
  MAX_WORKSPACE_VIEWS, actionMatchesWorkspaceView, validWorkspaceViewAction, validWorkspaceViewSnapshot,
  validWorkspaceViewViewportData, type WorkspaceViewAction, type WorkspaceViewSnapshot, type WorkspaceViewViewportData,
} from "./workspaceViewModel";

const SNAPSHOT = "spike-workspace-view-snapshot", ACTION = "spike-workspace-view-action", RESPONSE = "spike-workspace-view-response";
const VIEWPORT_REQUEST = "spike-workspace-view-viewport-request", VIEWPORT_RESPONSE = "spike-workspace-view-viewport-response";
type Envelope = { token: string; viewId: string; projectSession?: string; revision?: string; viewportRevision?: string; requestId?: string; action?: WorkspaceViewAction; snapshot?: WorkspaceViewSnapshot; viewport?: WorkspaceViewViewportData; result?: unknown; error?: string };
type Session = { token: string; snapshot: WorkspaceViewSnapshot; viewport?: WorkspaceViewViewportData; handle: (action: WorkspaceViewAction) => unknown | Promise<unknown>; stop: () => void; child?: Window; nativeChild?: { destroy: () => Promise<void> }; channel?: BroadcastChannel };
const sessions = new Map<string, Session>();
const native = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
const token = () => Array.from(crypto.getRandomValues(new Uint8Array(24)), byte => byte.toString(16).padStart(2, "0")).join("");
const safeId = (value: string) => value.toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/-+/g, "-").slice(0, 28) || "view";
const shortHash = (value: string) => { let hash = 2166136261; for (let i = 0; i < value.length; i++) { hash ^= value.charCodeAt(i); hash = Math.imul(hash, 16777619); } return (hash >>> 0).toString(36); };
export const workspaceViewWindowLabel = (viewId: string) => `spike-assembly-view-${safeId(viewId)}-${shortHash(viewId)}`;

function urlFor(viewId: string, sessionToken: string): string {
  const url = new URL(window.location.href); url.search = ""; url.hash = "";
  url.searchParams.set("spikeWorkspaceView", viewId); url.searchParams.set("workspaceViewToken", sessionToken);
  return `${url.pathname}${url.search}`;
}
export function workspaceViewIdFromLocation(search = window.location.search): string | null {
  const value = new URLSearchParams(search).get("spikeWorkspaceView");
  return value && value.length <= 128 ? value : null;
}
async function send(viewId: string, event: string, envelope: Envelope) {
  if (native()) { const { emitTo } = await import("@tauri-apps/api/event"); await emitTo(workspaceViewWindowLabel(viewId), event, envelope); }
  else sessions.get(viewId)?.channel?.postMessage({ event, envelope });
}
async function publish(viewId: string) {
  const session = sessions.get(viewId); if (session) await send(viewId, SNAPSHOT, { token: session.token, viewId, snapshot: session.snapshot });
}
async function receive(envelope: Envelope) {
  const session = sessions.get(envelope?.viewId); const action = envelope?.action;
  if (!session || envelope.token !== session.token || !validWorkspaceViewAction(action)) return;
  if (action.type === "ready") { await publish(envelope.viewId); return; }
  try {
    if (!session.snapshot.valid && !["closed", "redock", "focus-owner", "status", "lease"].includes(action.type)) throw new Error(session.snapshot.invalidReason ?? "This scoped view no longer exists in the active project.");
    if (!["closed", "redock", "focus-owner", "status", "lease"].includes(action.type)
      && (envelope.projectSession !== session.snapshot.projectSession || envelope.revision !== session.snapshot.revision)) throw new Error("The project view changed. Review the refreshed view and retry.");
    if (!actionMatchesWorkspaceView(action, session.snapshot.descriptor.scope)) throw new Error("The action does not belong to this fixed view scope.");
    let result: unknown;
    if (action.type === "focus-owner") {
      if (native()) {
        const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
        const owner = await WebviewWindow.getByLabel("main");
        if (!owner) throw new Error("The owning SPIKE window is unavailable.");
        await owner.unminimize(); await owner.show(); await owner.setFocus();
      } else window.focus?.();
      result = true;
    } else result = await session.handle(action);
    if (envelope.requestId) await send(envelope.viewId, RESPONSE, { token: session.token, viewId: envelope.viewId, requestId: envelope.requestId, result });
  } catch (error) {
    if (envelope.requestId) await send(envelope.viewId, RESPONSE, { token: session.token, viewId: envelope.viewId, requestId: envelope.requestId, error: error instanceof Error ? error.message : String(error) });
  }
}
async function receiveViewport(envelope: Envelope) {
  const session = sessions.get(envelope?.viewId);
  if (!session || envelope.token !== session.token || !envelope.requestId) return;
  const viewport = session.viewport;
  const error = !session.snapshot.valid ? session.snapshot.invalidReason ?? "This scoped view no longer exists in the active project." : !viewport ? "Scoped renderer inputs are not ready." : envelope.projectSession !== session.snapshot.projectSession
    ? "The owning project changed. Reopen this view." : envelope.viewportRevision !== viewport.revision || session.snapshot.viewportRevision !== viewport.revision
      ? "The scoped renderer inputs changed. Request the refreshed revision." : undefined;
  await send(envelope.viewId, VIEWPORT_RESPONSE, { token: session.token, viewId: envelope.viewId, requestId: envelope.requestId, ...(error ? { error } : { viewport }) });
}

export async function focusWorkspaceViewWindow(viewId: string): Promise<boolean> {
  const session = sessions.get(viewId); if (!session) return false;
  if (native()) { const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow"); const child = await WebviewWindow.getByLabel(workspaceViewWindowLabel(viewId)); if (!child) return false; await child.unminimize(); await child.show(); await child.setFocus(); }
  else { if (!session.child || session.child.closed) return false; session.child.focus(); }
  return true;
}
export async function updateWorkspaceViewWindow(viewId: string, snapshot: WorkspaceViewSnapshot, viewport?: WorkspaceViewViewportData) {
  const session = sessions.get(viewId); if (!session) return;
  if (!validWorkspaceViewSnapshot(snapshot) || snapshot.viewId !== viewId) throw new Error("Invalid scoped view snapshot.");
  session.snapshot = snapshot; if (viewport) session.viewport = viewport; await publish(viewId);
}
export async function openWorkspaceViewWindow(viewId: string, snapshot: WorkspaceViewSnapshot, handle: Session["handle"], viewport?: WorkspaceViewViewportData) {
  if (!validWorkspaceViewSnapshot(snapshot) || snapshot.viewId !== viewId || viewport && !validWorkspaceViewViewportData(viewport)) throw new Error("Invalid scoped view session data.");
  const existing = sessions.get(viewId);
  if (existing) {
    existing.handle = handle; if (viewport) existing.viewport = viewport;
    const focused = await focusWorkspaceViewWindow(viewId);
    if (sessions.get(viewId) !== existing) throw new Error("Scoped view opening was cancelled.");
    if (focused) { await updateWorkspaceViewWindow(viewId, snapshot, viewport); return; }
    existing.stop(); existing.channel?.close(); sessions.delete(viewId);
  }
  if (sessions.size >= MAX_WORKSPACE_VIEWS) throw new Error(`At most ${MAX_WORKSPACE_VIEWS} detached assembly views may be open.`);
  const session: Session = { token: token(), snapshot, viewport, handle, stop: () => {} }; sessions.set(viewId, session);
  let initializationCancelled = false; const initializationStops: Array<() => void> = [];
  session.stop = () => { initializationCancelled = true; initializationStops.splice(0).forEach(remove => remove()); };
  try {
    if (native()) {
      const { listen } = await import("@tauri-apps/api/event");
      if (initializationCancelled || sessions.get(viewId) !== session) throw new Error("Scoped view opening was cancelled.");
      const stopAction = await listen<Envelope>(ACTION, event => { if (event.payload?.viewId === viewId) void receive(event.payload); });
      if (initializationCancelled || sessions.get(viewId) !== session) { stopAction(); throw new Error("Scoped view opening was cancelled."); }
      initializationStops.push(stopAction);
      const stopViewport = await listen<Envelope>(VIEWPORT_REQUEST, event => { if (event.payload?.viewId === viewId) void receiveViewport(event.payload); });
      if (initializationCancelled || sessions.get(viewId) !== session) { stopViewport(); throw new Error("Scoped view opening was cancelled."); }
      initializationStops.push(stopViewport);
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow"); const label = workspaceViewWindowLabel(viewId);
      if (sessions.get(viewId) !== session) throw new Error("Scoped view opening was cancelled.");
      const previous = await WebviewWindow.getByLabel(label);
      if (sessions.get(viewId) !== session) throw new Error("Scoped view opening was cancelled.");
      await previous?.destroy();
      if (sessions.get(viewId) !== session) throw new Error("Scoped view opening was cancelled.");
      const child = new WebviewWindow(label, { url: urlFor(viewId, session.token), title: `SPIKE | ${snapshot.descriptor.title}`, width: 1120, height: 780, minWidth: 640, minHeight: 420, resizable: true, decorations: true, skipTaskbar: false, backgroundColor: "#101820", dragDropEnabled: false });
      session.nativeChild = child;
      await child.once("tauri://destroyed", () => { if (sessions.get(viewId) === session) { sessions.delete(viewId); session.stop(); void session.handle({ type: "closed" }); } });
      if (sessions.get(viewId) !== session) throw new Error("Scoped view opening was cancelled.");
      await awaitNativeWindowCreated(child);
      if (sessions.get(viewId) !== session) throw new Error("Scoped view opening was cancelled.");
    } else {
      session.channel = new BroadcastChannel(`spike-workspace-view:${session.token}`);
      session.channel.addEventListener("message", event => { if (event.data?.event === ACTION) void receive(event.data.envelope); if (event.data?.event === VIEWPORT_REQUEST) void receiveViewport(event.data.envelope); });
      session.child = window.open(urlFor(viewId, session.token), `${workspaceViewWindowLabel(viewId)}-${session.token}`, "popup=yes,width=1120,height=780,resizable=yes,scrollbars=yes") ?? undefined;
      if (!session.child) throw new Error("Allow local SPIKE popup windows, then retry.");
    }
    await publish(viewId);
  } catch (error) { if (sessions.get(viewId) === session) sessions.delete(viewId); session.stop(); session.channel?.close(); throw error; }
}
export async function closeWorkspaceViewWindow(viewId: string) {
  const session = sessions.get(viewId); if (!session) return; sessions.delete(viewId); session.stop(); session.channel?.close();
  if (native()) await session.nativeChild?.destroy(); else session.child?.close();
}
export async function closeAllWorkspaceViewWindows() { await Promise.all([...sessions.keys()].map(closeWorkspaceViewWindow)); }

export async function connectWorkspaceViewChild(viewId: string, callbacks: { onSnapshot: (snapshot: WorkspaceViewSnapshot) => void; onOwnerConnection?: (connected: boolean) => void }, options: { leaseIntervalMs?: number; leaseTimeoutMs?: number; requestTimeoutMs?: number } = {}) {
  const sessionToken = new URLSearchParams(window.location.search).get("workspaceViewToken");
  if (!sessionToken || !/^[a-f0-9]{48}$/.test(sessionToken) || !viewId || viewId.length > 128) throw new Error("Invalid scoped view session. Reopen it from SPIKE.");
  let snapshot: WorkspaceViewSnapshot | null = null, stopped = false, channel: BroadcastChannel | undefined;
  const pending = new Map<string, { resolve: (value: unknown) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>(); const stops: Array<() => void> = [];
  const received = (event: string, envelope: Envelope) => {
    if (stopped || envelope?.token !== sessionToken || envelope.viewId !== viewId) return;
    if (event === SNAPSHOT && validWorkspaceViewSnapshot(envelope.snapshot)) { snapshot = envelope.snapshot; callbacks.onSnapshot(snapshot); callbacks.onOwnerConnection?.(true); }
    if ((event === RESPONSE || event === VIEWPORT_RESPONSE) && envelope.requestId) { const request = pending.get(envelope.requestId); if (!request) return; clearTimeout(request.timer); pending.delete(envelope.requestId); envelope.error ? request.reject(new Error(envelope.error)) : event === VIEWPORT_RESPONSE && !validWorkspaceViewViewportData(envelope.viewport) ? request.reject(new Error("Workspace returned malformed scoped renderer inputs.")) : request.resolve(event === VIEWPORT_RESPONSE ? envelope.viewport : envelope.result); }
  };
  try {
    if (native()) { const { listen } = await import("@tauri-apps/api/event"); for (const event of [SNAPSHOT, RESPONSE, VIEWPORT_RESPONSE]) stops.push(await listen<Envelope>(event, message => received(event, message.payload), { target: { kind: "WebviewWindow", label: workspaceViewWindowLabel(viewId) } })); }
    else { channel = new BroadcastChannel(`spike-workspace-view:${sessionToken}`); channel.addEventListener("message", event => received(event.data?.event, event.data?.envelope)); }
  } catch (error) { stops.forEach(stop => stop()); channel?.close(); throw error; }
  const emit = async (event: string, envelope: Envelope) => { if (native()) { const { emitTo } = await import("@tauri-apps/api/event"); await emitTo("main", event, envelope); } else channel?.postMessage({ event, envelope }); };
  const request = async (event: string, action?: WorkspaceViewAction, viewportRevision?: string, timeout = options.requestTimeoutMs ?? 120000) => {
    if (stopped) throw new Error("Scoped view closed."); const requestId = crypto.randomUUID();
    const promise = new Promise<unknown>((resolve, reject) => { const timer = setTimeout(() => { pending.delete(requestId); reject(new Error("Workspace owner did not respond.")); }, timeout); pending.set(requestId, { resolve, reject, timer }); });
    try { await emit(event, { token: sessionToken, viewId, projectSession: snapshot?.projectSession, revision: snapshot?.revision, viewportRevision, requestId, action }); }
    catch (error) { const item = pending.get(requestId); if (item) { clearTimeout(item.timer); pending.delete(requestId); item.reject(error instanceof Error ? error : new Error(String(error))); } }
    return promise;
  };
  const act = async (action: WorkspaceViewAction) => {
    if (["ready", "closed"].includes(action.type)) { await emit(ACTION, { token: sessionToken, viewId, projectSession: snapshot?.projectSession, revision: snapshot?.revision, action }); return; }
    return request(ACTION, action);
  };
  const requestViewport = (viewportRevision: string) => request(VIEWPORT_REQUEST, undefined, viewportRevision) as Promise<WorkspaceViewViewportData>;
  const leaseInterval = Math.max(25, options.leaseIntervalMs ?? 5000), leaseTimeout = Math.max(20, options.leaseTimeoutMs ?? 12000);
  const lease = setInterval(() => { void request(ACTION, { type: "lease" }, undefined, leaseTimeout).then(() => callbacks.onOwnerConnection?.(true)).catch(() => callbacks.onOwnerConnection?.(false)); }, leaseInterval);
  const stop = () => { if (stopped) return; stopped = true; clearInterval(lease); stops.forEach(remove => remove()); channel?.close(); pending.forEach(item => { clearTimeout(item.timer); item.reject(new Error("Scoped view closed.")); }); pending.clear(); };
  try { await act({ type: "ready" }); }
  catch (error) { stop(); throw error; }
  return { act, requestViewport, stop };
}
