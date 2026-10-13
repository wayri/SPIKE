// SPDX-License-Identifier: Apache-2.0
import { awaitNativeWindowCreated } from "./detachedToolWindows";

export type ReportPreviewSnapshot = { fileName: string; html: string };
export type ReportPreviewAction = { type: "ready" | "export" | "close" | "closed" };

const LABEL = "spike-report-preview";
const SNAPSHOT_EVENT = "spike-report-preview-snapshot";
const ACTION_EVENT = "spike-report-preview-action";
const CHANNEL_PREFIX = "spike-report-preview-v1";
type Envelope = { token: string; snapshot?: ReportPreviewSnapshot; action?: ReportPreviewAction };
type Session = {
  token: string;
  snapshot: ReportPreviewSnapshot;
  handle: (action: ReportPreviewAction) => void | Promise<void>;
  stop: () => void;
  child?: Window;
  channel?: BroadcastChannel;
};

let session: Session | null = null;
const native = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
const validAction = (value: unknown): value is ReportPreviewAction =>
  Boolean(value && typeof value === "object" && ["ready", "export", "close", "closed"].includes((value as ReportPreviewAction).type));

function randomToken(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(24)), byte => byte.toString(16).padStart(2, "0")).join("");
}

function reportUrl(token: string): string {
  const url = new URL(window.location.href);
  url.search = "";
  url.hash = "";
  url.searchParams.set("spikeReportPreview", "1");
  url.searchParams.set("reportToken", token);
  return `${url.pathname}${url.search}`;
}

async function publishSnapshot(current: Session): Promise<void> {
  const envelope: Envelope = { token: current.token, snapshot: current.snapshot };
  if (native()) {
    const { emitTo } = await import("@tauri-apps/api/event");
    await emitTo(LABEL, SNAPSHOT_EVENT, envelope);
  } else current.channel?.postMessage({ event: SNAPSHOT_EVENT, envelope });
}

async function receive(envelope: Envelope): Promise<void> {
  const current = session;
  if (!current || envelope?.token !== current.token || !validAction(envelope.action)) return;
  if (envelope.action.type === "ready") {
    await publishSnapshot(current);
    return;
  }
  if (envelope.action.type === "closed") dispose(current);
  await current.handle(envelope.action);
}

function dispose(expected?: Session): void {
  if (expected && session !== expected) return;
  session?.stop();
  session?.channel?.close();
  session = null;
}

/** Brings the current report preview forward without replacing its session. */
export async function focusReportPreviewWindow(): Promise<boolean> {
  const current = session;
  if (!current) return false;
  if (native()) {
    const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    const child = await WebviewWindow.getByLabel(LABEL);
    if (!child) return false;
    await child.unminimize();
    await child.show();
    await child.setFocus();
  } else {
    if (!current.child || current.child.closed) return false;
    current.child.focus();
  }
  return true;
}

export async function openReportPreviewWindow(
  snapshot: ReportPreviewSnapshot,
  handle: Session["handle"],
): Promise<{ mode: "native" | "browser"; created: boolean }> {
  if (session) {
    session.snapshot = snapshot;
    session.handle = handle;
    if (await focusReportPreviewWindow()) {
      await publishSnapshot(session);
      return { mode: native() ? "native" : "browser", created: false };
    }
    dispose(session);
  }
  const current: Session = { token: randomToken(), snapshot, handle, stop: () => {} };
  session = current;
  try {
    if (native()) {
      const { listen } = await import("@tauri-apps/api/event");
      current.stop = await listen<Envelope>(ACTION_EVENT, event => { void receive(event.payload); });
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
      const stale = await WebviewWindow.getByLabel(LABEL);
      await stale?.destroy();
      const child = new WebviewWindow(LABEL, {
        url: reportUrl(current.token),
        title: `SPIKE | Engineering report | ${snapshot.fileName}`,
        width: 1180,
        height: 820,
        minWidth: 620,
        minHeight: 420,
        resizable: true,
        decorations: true,
        skipTaskbar: false,
        backgroundColor: "#101820",
        dragDropEnabled: false,
      });
      await child.once("tauri://destroyed", () => {
        if (session === current) {
          dispose(current);
          void current.handle({ type: "closed" });
        }
      });
      await awaitNativeWindowCreated(child);
      await publishSnapshot(current);
      return { mode: "native", created: true };
    }
    current.channel = new BroadcastChannel(`${CHANNEL_PREFIX}:${current.token}`);
    current.channel.addEventListener("message", event => {
      if (event.data?.event === ACTION_EVENT) void receive(event.data.envelope);
    });
    current.child = window.open(
      reportUrl(current.token),
      `${LABEL}-${current.token}`,
      "popup=yes,width=1180,height=820,resizable=yes,scrollbars=yes",
    ) ?? undefined;
    if (!current.child) throw new Error("Allow local SPIKE popup windows, then retry the report preview.");
    return { mode: "browser", created: true };
  } catch (error) {
    dispose(current);
    throw error;
  }
}

export async function updateReportPreviewWindow(snapshot: ReportPreviewSnapshot): Promise<void> {
  if (!session) return;
  session.snapshot = snapshot;
  await publishSnapshot(session);
}

export async function closeReportPreviewWindow(): Promise<void> {
  const current = session;
  if (!current) return;
  dispose(current);
  if (native()) {
    const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    await (await WebviewWindow.getByLabel(LABEL))?.destroy();
  } else current.child?.close();
}

export function isReportPreviewLocation(search = window.location.search): boolean {
  const params = new URLSearchParams(search);
  return params.get("spikeReportPreview") === "1" && /^[a-f0-9]{48}$/.test(params.get("reportToken") ?? "");
}

export async function connectReportPreviewChild(onSnapshot: (snapshot: ReportPreviewSnapshot) => void): Promise<{
  act: (action: ReportPreviewAction) => Promise<void>;
  stop: () => void;
}> {
  const token = new URLSearchParams(window.location.search).get("reportToken");
  if (!token || !/^[a-f0-9]{48}$/.test(token)) throw new Error("Invalid report preview session. Reopen it from SPIKE.");
  let stopped = false;
  let channel: BroadcastChannel | undefined;
  let unlisten: (() => void) | undefined;
  const receiveSnapshot = (envelope: Envelope) => {
    if (!stopped && envelope?.token === token && envelope.snapshot) onSnapshot(envelope.snapshot);
  };
  if (native()) {
    const { listen } = await import("@tauri-apps/api/event");
    unlisten = await listen<Envelope>(SNAPSHOT_EVENT, event => receiveSnapshot(event.payload), { target: { kind: "WebviewWindow", label: LABEL } });
  } else {
    channel = new BroadcastChannel(`${CHANNEL_PREFIX}:${token}`);
    channel.addEventListener("message", event => {
      if (event.data?.event === SNAPSHOT_EVENT) receiveSnapshot(event.data.envelope);
    });
  }
  const act = async (action: ReportPreviewAction) => {
    if (stopped) return;
    const envelope: Envelope = { token, action };
    if (native()) {
      const { emitTo } = await import("@tauri-apps/api/event");
      await emitTo("main", ACTION_EVENT, envelope);
    } else channel?.postMessage({ event: ACTION_EVENT, envelope });
  };
  await act({ type: "ready" });
  return { act, stop: () => { stopped = true; unlisten?.(); channel?.close(); } };
}
