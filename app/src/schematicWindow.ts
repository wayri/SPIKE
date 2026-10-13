// SPDX-License-Identifier: Apache-2.0
import { awaitNativeWindowCreated } from "./detachedToolWindows";

import type { SchematicSnapshot, SchematicAction } from "./kicadSchematicModel";
export type { SchematicSnapshot, SchematicAction } from "./kicadSchematicModel";

const LABEL = "spike-schematic-viewer";
const SNAPSHOT_EVENT = "spike-schematic-viewer-snapshot";
const ACTION_EVENT = "spike-schematic-viewer-action";
const CHANNEL_PREFIX = "spike-schematic-viewer-v1";
type Envelope = { token: string; snapshot?: SchematicSnapshot; action?: SchematicAction };
type Session = {
  token: string;
  snapshot: SchematicSnapshot;
  handle: (action: SchematicAction) => void | Promise<void>;
  stop: () => void;
  child?: Window;
  channel?: BroadcastChannel;
  leases: Set<string>;
};

let session: Session | null = null;
let operation: Promise<void> = Promise.resolve();
const native = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
const validAction = (value: unknown): value is SchematicAction =>
  Boolean(value && typeof value === "object" && ["ready", "import", "bind", "cancel", "select", "close", "closed"].includes((value as SchematicAction).type));

function randomToken(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(24)), byte => byte.toString(16).padStart(2, "0")).join("");
}

function serialize<T>(work: () => Promise<T>): Promise<T> {
  const next = operation.then(work, work);
  operation = next.then(() => undefined, () => undefined);
  return next;
}

function owns(current: Session, lease: string): boolean {
  return session === current && current.leases.has(lease);
}

function schematicUrl(token: string): string {
  const url = new URL(window.location.href);
  url.search = "";
  url.hash = "";
  url.searchParams.set("spikeSchematic", "1");
  url.searchParams.set("schematicToken", token);
  return `${url.pathname}${url.search}`;
}

async function publishSnapshot(current: Session): Promise<void> {
  const envelope: Envelope = { token: current.token, snapshot: current.snapshot };
  current.channel?.postMessage({ event: SNAPSHOT_EVENT, envelope });
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

/** Brings the current schematic viewer forward without replacing its session. */
export async function focusSchematicWindow(): Promise<boolean> {
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

export async function openSchematicWindow(
  snapshot: SchematicSnapshot,
  handle: Session["handle"],
): Promise<{ mode: "native" | "browser"; created: boolean; lease: string }> {
  const lease = randomToken();
  return serialize(async () => {
    if (session) {
      const existing = session;
      existing.snapshot = snapshot;
      existing.handle = handle;
      existing.leases.add(lease);
      if (await focusSchematicWindow() && owns(existing, lease)) {
        await publishSnapshot(existing);
        return { mode: native() ? "native" : "browser", created: false, lease };
      }
      existing.leases.delete(lease);
      if (session === existing) dispose(existing);
    }
    const current: Session = { token: randomToken(), snapshot, handle, stop: () => {}, leases: new Set([lease]) };
    session = current;
    let nativeChild: { destroy: () => Promise<void> } | undefined;
    try {
      current.channel = new BroadcastChannel(`${CHANNEL_PREFIX}:${current.token}`);
      current.channel.addEventListener("message", event => {
        if (event.data?.event === ACTION_EVENT) void receive(event.data.envelope);
      });
      if (native()) {
        const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
        if (!owns(current, lease)) throw new Error("Schematic viewer session was replaced during startup.");
        const stale = await WebviewWindow.getByLabel(LABEL);
        if (!owns(current, lease)) throw new Error("Schematic viewer session was replaced during startup.");
        await stale?.destroy();
        if (!owns(current, lease)) throw new Error("Schematic viewer session was replaced during startup.");
        const child = new WebviewWindow(LABEL, {
          url: schematicUrl(current.token),
          title: `SPIKE | Schematic viewer | ${snapshot.document?.source.file_name ?? "No schematic"}`,
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
        nativeChild = child;
        await child.once("tauri://destroyed", () => {
          if (session === current) {
            dispose(current);
            void current.handle({ type: "closed" });
          }
        });
        if (!owns(current, lease)) { await child.destroy(); throw new Error("Schematic viewer session was replaced during startup."); }
        await awaitNativeWindowCreated(child);
        if (!owns(current, lease)) { await child.destroy(); throw new Error("Schematic viewer session was replaced during startup."); }
        await publishSnapshot(current);
        return { mode: "native", created: true, lease };
      }
      current.child = window.open(
        schematicUrl(current.token),
        `${LABEL}-${current.token}`,
        "popup=yes,width=1180,height=820,resizable=yes,scrollbars=yes",
      ) ?? undefined;
      if (!current.child) throw new Error("Allow local SPIKE popup windows, then retry the schematic viewer.");
      return { mode: "browser", created: true, lease };
    } catch (error) {
      if (session === current) dispose(current);
      await nativeChild?.destroy().catch(() => {});
      throw error;
    }
  });
}

export async function updateSchematicWindow(snapshot: SchematicSnapshot): Promise<void> {
  if (!session) return;
  session.snapshot = snapshot;
  await publishSnapshot(session);
}

export async function closeSchematicWindow(lease?: string): Promise<void> {
  return serialize(async () => {
    const current = session;
    if (!current) return;
    if (lease) {
      if (!current.leases.delete(lease) || current.leases.size) return;
    }
    dispose(current);
    if (native()) {
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
      await (await WebviewWindow.getByLabel(LABEL))?.destroy();
    } else current.child?.close();
  });
}

export function isSchematicLocation(search = window.location.search): boolean {
  const params = new URLSearchParams(search);
  return params.get("spikeSchematic") === "1" && /^[a-f0-9]{48}$/.test(params.get("schematicToken") ?? "");
}

export async function connectSchematicChild(onSnapshot: (snapshot: SchematicSnapshot) => void): Promise<{
  act: (action: SchematicAction) => Promise<void>;
  stop: () => void;
}> {
  const token = new URLSearchParams(window.location.search).get("schematicToken");
  if (!token || !/^[a-f0-9]{48}$/.test(token)) throw new Error("Invalid schematic viewer session. Reopen it from SPIKE.");
  let stopped = false;
  let channel: BroadcastChannel | undefined;
  let unlisten: (() => void) | undefined;
  const receiveSnapshot = (envelope: Envelope) => {
    if (!stopped && envelope?.token === token && envelope.snapshot) onSnapshot(envelope.snapshot);
  };
  channel = new BroadcastChannel(`${CHANNEL_PREFIX}:${token}`);
  channel.addEventListener("message", event => {
    if (event.data?.event === SNAPSHOT_EVENT) receiveSnapshot(event.data.envelope);
  });
  const act = async (action: SchematicAction) => {
    if (stopped) return;
    const envelope: Envelope = { token, action };
    channel?.postMessage({ event: ACTION_EVENT, envelope });
  };
  await act({ type: "ready" });
  return { act, stop: () => { stopped = true; unlisten?.(); channel?.close(); } };
}
