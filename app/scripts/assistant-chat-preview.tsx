// SPDX-License-Identifier: Apache-2.0
import React from "react";
import { createRoot } from "react-dom/client";
import AssistantChatPanel from "../src/AssistantChatPanel";
import "../src/buttonStandard.css";
import "../src/tableTheme.css";

// Actual UI, synthetic conversation only. No inference or solver result claimed.
function Preview() {
  return <main style={{ height: "100vh", display: "flex", flexDirection: "column", background: "var(--spike-table-surface)", color: "var(--spike-table-text)" }}>
    <p style={{ margin: 0, padding: 8, font: "11px system-ui" }}>UI acceptance fixture · synthetic messages · no solver or model inference</p>
    <div className="assistant-window__chat">
      <AssistantChatPanel nativeWindow onClose={() => {}} getRevision={() => "fixture"} getContext={() => ({})} onCommand={async () => ({})}
        runWorker={async () => ({ ok: true, result: { credential_configured: false, cloud: true, credential_store_supported: true } }) as never}
        initialMessages={[
          { role: "user", content: "Help me compare the setup choices and inspect a screenshot." },
          { role: "assistant", content: "## Start with your question\n\nAttach a screenshot or text file with the paperclip, or paste an image into the composer.\n\n| Task | Where to look |\n| --- | --- |\n| Provider and model | Settings gear |\n| Project evidence | Sharing in settings |\n| Exact tool output | Collapsed activity |\n\n**Engineering results** remain linked to actual SPIKE evidence. Model text does not establish validation.\n\n```text\nInspect the selected board and list its saved studies.\n```" },
        ]} />
    </div><output id="acceptance" style={{ font: "10px system-ui" }}>Checking…</output>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Preview />);
setTimeout(() => {
  try {
    const settings = document.querySelector<HTMLElement>(".assistant-chat__setup")!;
    if (!settings.hidden) throw new Error("Settings must start collapsed");
    const chat = document.querySelector<HTMLElement>(".assistant-chat__messages")!;
    if (chat.getBoundingClientRect().height < innerHeight * .55) throw new Error("Conversation must own most of the window");
    if (!chat.querySelector("table") || !chat.querySelector("code")) throw new Error("Rich answer missing");
    const gear = document.querySelector<HTMLButtonElement>('[aria-label="Assistant settings"]')!;
    gear.click();
    setTimeout(() => {
      if (settings.hidden) { document.getElementById("acceptance")!.textContent = "FAIL: settings did not open"; return; }
      document.querySelector<HTMLButtonElement>('[aria-label="Close assistant settings"]')!.click();
      setTimeout(async () => {
        const composer = document.querySelector<HTMLElement>(".assistant-chat__composer")!.getBoundingClientRect();
        const source = atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==");
        const clipboard = new DataTransfer();
        clipboard.items.add(new File([Uint8Array.from(source, c => c.charCodeAt(0))], "pasted-screenshot.png", { type: "image/png" }));
        document.querySelector("textarea")!.dispatchEvent(new ClipboardEvent("paste", { clipboardData: clipboard, bubbles: true, cancelable: true }));
        await new Promise(resolve => setTimeout(resolve, 150));
        const remove = document.querySelector<HTMLButtonElement>('[aria-label="Remove pasted-screenshot.png"]');
        const pasted = !!remove && !!document.querySelector(".assistant-chat__pending img");
        remove?.click();
        await new Promise(resolve => setTimeout(resolve, 50));
        const overflow = chat.scrollWidth > chat.clientWidth + 1;
        document.getElementById("acceptance")!.textContent = settings.hidden && composer.bottom <= innerHeight && pasted && !overflow ? "PASS: chat dominant; rich output; settings; paste image preview/remove; no horizontal clipping" : "FAIL: settings, composer, paste or clipping";
      }, 50);
    }, 50);
  } catch (error) { document.getElementById("acceptance")!.textContent = `FAIL: ${String(error)}`; }
}, 250);
