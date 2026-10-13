// SPDX-License-Identifier: Apache-2.0
import { awaitNativeWindowCreated } from "./detachedToolWindows";
import { runLocalWorker, cancelLocalWorker } from "./workerBridge";
import { assistantToolCatalog, validateAssistantToolCall } from "./assistantSkills";
export const ASSISTANT_WINDOW = "spike-assistant";
const REQUEST = "spike-assistant-request", RESPONSE = "spike-assistant-response";
type Snapshot = { context: Record<string, unknown>; revision: string; projectIdentity: string };
type Request = { token: string; id: string; kind: "context" | "command" | "worker" | "cancel"; revision?: string; command?: string; args?: Record<string, unknown>; request?: Record<string, unknown>; operation?: string };
type Reply = { token: string; id: string; result?: unknown; error?: string; snapshot: Snapshot };
type Owner = { getContext: () => Record<string, unknown>; getRevision: () => string; getProjectIdentity: () => string; onCommand: (command: string, args: Record<string, unknown>) => Promise<unknown> };
let owner: Owner | undefined, token = "", stop: (() => void) | undefined;
const operations = new Set<string>();
const methods = new Set(["assistant_models", "assistant_provider_status", "assistant_set_credential", "assistant_delete_credential", "assistant_turn"]);
export function isAssistantWindow(search = window.location.search) { return new URLSearchParams(search).has("spikeAssistant"); }
export function bindAssistantWindow(next: Owner) { owner = next; }
let opening: Promise<void> | undefined;
export async function openAssistantWindow(next: Owner, onClosed: () => void) {
  owner = next;
  if (opening) return opening;
  opening = createAssistantWindow(next, onClosed).finally(() => { opening = undefined; });
  return opening;
}
async function createAssistantWindow(next: Owner, onClosed: () => void) {
  owner = next;
  const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  const existing = await WebviewWindow.getByLabel(ASSISTANT_WINDOW);
  if (existing && token) { await existing.unminimize(); await existing.show(); await existing.setFocus(); return; }
  await existing?.destroy(); stop?.();
  token = Array.from(crypto.getRandomValues(new Uint8Array(24)), x => x.toString(16).padStart(2, "0")).join("");
  const session = token;
  const { listen, emitTo } = await import("@tauri-apps/api/event");
  stop = await listen<Request>(REQUEST, async event => {
    const request = event.payload;
    if (!owner || request?.token !== session || token !== session || typeof request.id !== "string" || request.id.length > 80) return;
    let result: unknown, error: string | undefined;
    try {
      if (JSON.stringify(request).length > 2 * 1024 * 1024) throw new Error("Assistant request exceeds the transport budget.");
      if (request.kind === "context") result = null;
      else if (request.kind === "cancel") {
        if (!request.operation || !operations.has(request.operation)) throw new Error("Unknown assistant operation.");
        result = await cancelLocalWorker(request.operation);
      } else if (request.kind === "worker") {
        const job = request.request;
        if (!job || typeof job.method !== "string" || !methods.has(job.method) || typeof job.id !== "string" || job.id.length > 100 || !job.id.startsWith("assistant-")) throw new Error("Unsupported assistant worker request.");
        if (operations.has(job.id)) throw new Error("Duplicate assistant operation.");
        operations.add(job.id);
        try { result = await runLocalWorker(job); } finally { operations.delete(job.id); }
      } else if (request.kind === "command") {
        if (request.revision !== owner.getRevision()) throw new Error("Project changed. Refresh context and request a new proposal.");
        const entry = assistantToolCatalog.find(tool => tool.command === request.command);
        if (request.command === "assistant_review_context") {
          if (typeof request.args?.caseId !== "string") throw new Error("Missing prepared case identity.");
        } else {
          if (!entry) throw new Error("Unsupported assistant action.");
          validateAssistantToolCall(entry.name, request.args ?? {});
        }
        result = await owner.onCommand(request.command!, request.args ?? {});
      } else throw new Error("Unsupported assistant request.");
    } catch (reason) { error = reason instanceof Error ? reason.message : String(reason); }
    if (token !== session || !owner) return;
    await emitTo(ASSISTANT_WINDOW, RESPONSE, { token: session, id: request.id, result, error, snapshot: { context: owner.getContext(), revision: owner.getRevision(), projectIdentity: owner.getProjectIdentity() } } satisfies Reply);
  }, { target: { kind: "WebviewWindow", label: "main" } });
  const url = new URL(window.location.href); url.search = ""; url.hash = "";
  url.searchParams.set("spikeAssistant", "1"); url.searchParams.set("assistantToken", token);
  const child = new WebviewWindow(ASSISTANT_WINDOW, { url: `${url.pathname}${url.search}`, title: "SPIKE | Assistant chats", width: 1000, height: 800, minWidth: 560, minHeight: 500, resizable: true, decorations: true, skipTaskbar: false, dragDropEnabled: false });
  const dispose = () => {
    if (token !== session) return;
    token = ""; stop?.(); stop = undefined;
    for (const id of operations) void cancelLocalWorker(id).catch(() => {});
    operations.clear(); onClosed();
  };
  await child.once("tauri://destroyed", dispose);
  try { await awaitNativeWindowCreated(child); } catch (error) { dispose(); throw error; }
}
export async function connectAssistantWindow() {
  const token = new URLSearchParams(window.location.search).get("assistantToken");
  if (!token || !/^[a-f0-9]{48}$/.test(token)) throw new Error("Reopen the assistant from the SPIKE workspace.");
  let snapshot: Snapshot = { context: {}, revision: "starting", projectIdentity: "" }, closed = false;
  let projectIdentity = "", projectChanged = false;
  const pending = new Map<string, { resolve: (value: unknown) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>();
  const { listen, emitTo } = await import("@tauri-apps/api/event");
  const stop = await listen<Reply>(RESPONSE, event => {
    const reply = event.payload;
    if (reply?.token !== token) return;
    const task = pending.get(reply.id); if (!task) return;
    pending.delete(reply.id); clearTimeout(task.timer); snapshot = reply.snapshot;
    if (projectIdentity && snapshot.projectIdentity !== projectIdentity) projectChanged = true;
    projectIdentity ||= snapshot.projectIdentity;
    if (projectChanged) { task.reject(new Error("Project switched. Close and reopen assistant chats before continuing.")); return; }
    reply.error ? task.reject(new Error(reply.error)) : task.resolve(reply.result);
  }, { target: { kind: "WebviewWindow", label: ASSISTANT_WINDOW } });
  const request = async (data: Omit<Request, "token" | "id">): Promise<unknown> => {
    if (projectChanged) throw new Error("Project switched. Close and reopen assistant chats before continuing.");
    if (closed) throw new Error("Assistant disconnected. Reopen it from SPIKE.");
    const id = crypto.randomUUID();
    const promise = new Promise<unknown>((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(id); reject(new Error("SPIKE did not respond. Return to the workspace and retry.")); }, 150000);
      pending.set(id, { resolve, reject, timer });
    });
    try { await emitTo("main", REQUEST, { ...data, token, id, revision: snapshot.revision }); }
    catch (error) { const task = pending.get(id); if (task) { clearTimeout(task.timer); pending.delete(id); task.reject(error instanceof Error ? error : new Error(String(error))); } }
    return promise;
  };
  await request({ kind: "context" });
  return {
    getContext: () => snapshot.context, getRevision: () => snapshot.revision,
    prepareContext: async () => { await request({ kind: "context" }); },
    onCommand: (command: string, args: Record<string, unknown>) => request({ kind: "command", command, args }),
    runWorker: (job: Record<string, unknown>) => request({ kind: "worker", request: job }) as ReturnType<typeof runLocalWorker>,
    cancelWorker: (operation?: string) => operation ? request({ kind: "cancel", operation }) as ReturnType<typeof cancelLocalWorker> : Promise.resolve(false),
    dispose: () => { closed = true; stop(); for (const task of pending.values()) { clearTimeout(task.timer); task.reject(new Error("Assistant closed.")); } pending.clear(); },
  };
}

export async function minimizeAssistantWindow() {
  const { getCurrentWebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  await getCurrentWebviewWindow().minimize();
}
export async function destroyAssistantWindow() {
  const { getCurrentWebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  await getCurrentWebviewWindow().destroy();
}
export async function onAssistantCloseRequested(handler: () => void) {
  const { getCurrentWebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  return getCurrentWebviewWindow().onCloseRequested(event => { event.preventDefault(); handler(); });
}

/** Called only after the owning workspace's close/save/discard decision. */
export async function closeOwnedAssistantWindow() {
  const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  await (await WebviewWindow.getByLabel(ASSISTANT_WINDOW))?.destroy();
}
