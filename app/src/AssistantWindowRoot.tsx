// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import AssistantChatPanel from "./AssistantChatPanel";
import { connectAssistantWindow, minimizeAssistantWindow, destroyAssistantWindow, onAssistantCloseRequested } from "./assistantWindow";
import type { AssistantMessage } from "./assistantConversation";
import "./AssistantChatPanel.css";
type Connection = Awaited<ReturnType<typeof connectAssistantWindow>>;
type Chat = { id: string; title: string; messages: AssistantMessage[] };
const newChat = (): Chat => ({ id: crypto.randomUUID(), title: "New chat", messages: [] });
export default function AssistantWindowRoot() {
  const [connection, setConnection] = useState<Connection>();
  const [error, setError] = useState("");
  const [chats, setChats] = useState<Chat[]>(() => [newChat()]);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [closing, setClosing] = useState(false);
  const [handoff, setHandoff] = useState<string | null>(null);
  const dialog = useRef<HTMLElement>(null);
  const requestClose = () => { setHandoff(null); setClosing(true); };
  const histories = useRef(new Map<string, AssistantMessage[]>());
  const current = chats.find(chat => chat.id === selected) ?? chats[0];
  useEffect(() => {
    let disposed = false, disconnect: (() => void) | undefined, stopClose: (() => void) | undefined;
    void connectAssistantWindow().then(async bridge => {
      if (disposed) { bridge.dispose(); return; }
      disconnect = bridge.dispose; setConnection(bridge);
      const stop = await onAssistantCloseRequested(requestClose);
      if (disposed) stop(); else stopClose = stop;
    }).catch(reason => { if (!disposed) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { disposed = true; disconnect?.(); stopClose?.(); };
  }, []);
  useEffect(() => {
    if (!closing && handoff === null) return;
    const target = dialog.current;
    if (!target) return;
    const previous = document.activeElement as HTMLElement | null;
    const background = Array.from(document.querySelectorAll<HTMLElement>(".assistant-window__toolbar, .assistant-window__chat"));
    background.forEach(node => { node.inert = true; });
    const controls = () => Array.from(target.querySelectorAll<HTMLElement>("button:not([disabled]), textarea, input:not([disabled]), select:not([disabled])"));
    controls()[0]?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setClosing(false); setHandoff(null); }
      if (event.key !== "Tab") return;
      const items = controls(); if (!items.length) return;
      const index = items.indexOf(document.activeElement as HTMLElement);
      if (event.shiftKey && index <= 0) { event.preventDefault(); items[items.length - 1]?.focus(); }
      else if (!event.shiftKey && (index < 0 || index === items.length - 1)) { event.preventDefault(); items[0].focus(); }
    };
    target.addEventListener("keydown", keydown);
    return () => { background.forEach(node => { node.inert = false; }); target.removeEventListener("keydown", keydown); previous?.focus(); };
  }, [closing, handoff]);
  const exportHandoff = async () => {
    try {
      const transcript = histories.current.get(current.id) ?? current.messages;
      setHandoff(JSON.stringify({ format: "spike-assistant-handoff-v1", instructions: "Use SPIKE CLI or MCP for complex workflows. Inspect actual capabilities; model text is not solver validation. All edits and runs require the configured action policy.", conversation: transcript.filter(row => row.role !== "tool"), projectContext: null, interfaces: ["spike --help", "spike assistant-tools", "spike headless --help", "docs/HEADLESS_AUTOMATION.md", "docs/LOCAL_LLM_MCP.md"] }, null, 2));
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  return <main className="assistant-window">
    <nav className="assistant-window__toolbar" aria-label="Chat manager">
      <label>Chat<select value={current.id} disabled={busy} onChange={event => { setSelected(event.target.value); setBusy(false); }}>
        {chats.map((chat, index) => <option key={chat.id} value={chat.id}>{index + 1}. {chat.title}</option>)}
      </select></label>
      <button type="button" disabled={busy || chats.length >= 32} onClick={() => { const chat = newChat(); setChats(rows => [...rows, chat]); setSelected(chat.id); }}>New chat</button>
      <button type="button" disabled={busy} onClick={() => void exportHandoff()}>External LLM handoff</button>
      <button type="button" title="Minimize to the Windows taskbar; retain chats and active request" onClick={() => void minimizeAssistantWindow()}>Minimize</button>
    </nav>
    <p className="assistant-window__notice">Chats stay in this window's memory. Closing discards them. Provider or sharing changes clear the selected chat. Copy a handoff before closing; review its contents before sharing.</p>
    {error && <p role="alert">{error}</p>}
    {!connection && !error && <p role="status">Connecting to the SPIKE workspace...</p>}
    {connection && chats.map(chat => <div key={chat.id} className="assistant-window__chat" hidden={chat.id !== current.id}>
      <AssistantChatPanel {...connection} idPrefix={chat.id} initialMessages={chat.messages}
        nativeWindow={"__TAURI_INTERNALS__" in window}
        onMessages={messages => { histories.current.set(chat.id, messages); const first = messages.find(row => row.role === "user")?.content; if (first && chat.title === "New chat") setChats(rows => rows.map(row => row.id === chat.id ? { ...row, title: first.slice(0, 60) } : row)); }}
        onBusy={value => { if (chat.id === current.id) setBusy(value); }} onClose={requestClose} />
    </div>)}
    {closing && <section ref={dialog} className="assistant-window__dialog" role="dialog" aria-modal="true" aria-label="Close assistant chats">
      <h2>Close assistant chats?</h2><p>This discards all chats and cancels this window's model requests. Previously started analysis jobs remain in SPIKE.</p>
      <button type="button" className="spike-control--danger" onClick={() => void destroyAssistantWindow()}>Discard chats and close</button>
      <button type="button" onClick={() => setClosing(false)}>Keep open</button>
    </section>}
    {handoff !== null && <section ref={dialog} className="assistant-window__dialog" role="dialog" aria-modal="true" aria-label="External LLM handoff">
      <h2>External LLM handoff</h2><p>The transcript may contain project information. Inspect it, then select and copy it to your external assistant. Project context is excluded. Connect external tools through SPIKE's CLI or MCP.</p>
      <textarea readOnly rows={16} value={handoff} aria-label="Handoff transcript" onFocus={event => event.target.select()} />
      <button type="button" onClick={() => setHandoff(null)}>Done</button>
    </section>}
  </main>;
}
