// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { Settings2, X, Paperclip, Trash2 } from "lucide-react";
import AssistantMessageContent from "./AssistantMessageContent";
import { ASSISTANT_ATTACHMENT_ACCEPT, checkAttachmentBudget, readAssistantAttachment } from "./assistantAttachments";
import { cancelLocalWorker, runLocalWorker } from "./workerBridge";
import { assistantToolCatalog, toolCapabilityStates } from "./assistantSkills";
import {
  CLOUD_PROVIDERS,
  contextPreview,
  runAssistantConversation,
  type AssistantMessage,
  type AssistantAttachment,
  type AssistantProvider,
  type ConversationEvidence,
  type ToolReview,
} from "./assistantConversation";
import "./AssistantChatPanel.css";

type CatalogPresentation = { name: string; description: string };

export type AssistantChatPanelProps = {
  onClose: () => void;
  onCommand: (command: string, args: Record<string, unknown>) => Promise<unknown>;
  getContext: () => Record<string, unknown>;
  getRevision: () => string;
  runWorker?: typeof runLocalWorker;
  cancelWorker?: typeof cancelLocalWorker;
  prepareContext?: () => Promise<void>;
  initialMessages?: AssistantMessage[];
  onMessages?: (messages: AssistantMessage[]) => void;
  onBusy?: (busy: boolean) => void;
  idPrefix?: string;
  nativeWindow?: boolean;
};

type ProviderChoice = { id: AssistantProvider; label: string; endpoint?: string; cloud: boolean; credential: boolean };
const PROVIDERS: ProviderChoice[] = [
  { id: "openai", label: "OpenAI (ChatGPT models)", cloud: true, credential: true },
  { id: "anthropic", label: "Anthropic Claude", cloud: true, credential: true },
  { id: "lmstudio", label: "LM Studio", endpoint: "http://127.0.0.1:1234", cloud: false, credential: false },
  { id: "ollama", label: "Ollama", endpoint: "http://127.0.0.1:11434", cloud: false, credential: false },
];

function workerResult(response: unknown): Record<string, unknown> {
  if (!response || typeof response !== "object") throw new Error("The assistant worker returned no response.");
  const envelope = response as Record<string, unknown>;
  if (envelope.ok !== true) throw new Error(typeof envelope.error === "string" ? envelope.error : "The assistant worker request failed.");
  return envelope.result && typeof envelope.result === "object" ? envelope.result as Record<string, unknown> : {};
}

function formatBytes(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KiB`;
}

export default function AssistantChatPanel({ onClose, onCommand, getContext, getRevision, runWorker = runLocalWorker, cancelWorker = cancelLocalWorker, prepareContext, initialMessages = [], onMessages, onBusy, idPrefix = "assistant", nativeWindow = false }: AssistantChatPanelProps) {
  const [provider, setProvider] = useState<AssistantProvider>("openai");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [attachments, setAttachments] = useState<AssistantAttachment[]>([]);
  const [attaching, setAttaching] = useState(false);
  const attachmentInput = useRef<HTMLInputElement>(null);
  const attachmentTicket = useRef(0);
  const settingsButton = useRef<HTMLButtonElement>(null);
  const selected = PROVIDERS.find(item => item.id === provider)!;
  const [endpoint, setEndpoint] = useState(selected.endpoint ?? "");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [credential, setCredential] = useState("");
  const [credentialConfigured, setCredentialConfigured] = useState(false);
  const [setupBusy, setSetupBusy] = useState(false);
  const [allowCloud, setAllowCloud] = useState(false);
  const [shareContext, setShareContext] = useState(false);
  const [messages, setMessages] = useState<AssistantMessage[]>(initialMessages);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Checking provider status...");
  const [error, setError] = useState("");
  const [evidence, setEvidence] = useState<ConversationEvidence[]>([]);
  const [review, setReview] = useState<ToolReview | null>(null);
  const reviewResolver = useRef<((accepted: boolean) => void) | null>(null);
  const operation = useRef<string | null>(null);
  const alive = useRef(true);
  const generation = useRef(0);
  const setupGeneration = useRef(0);
  const setupOperation = useRef<{ id: string; cancellable: boolean } | null>(null);
  const aborter = useRef<AbortController | null>(null);
  const transcript = useRef<HTMLElement | null>(null);
  const preview = useMemo(() => {
    try { return { ...contextPreview(getContext()), error: "" }; }
    catch (reason) { return { sections: 0, items: 0, bytes: 0, labels: [] as string[], error: reason instanceof Error ? reason.message : String(reason) }; }
  }, [getContext, getRevision, messages.length]);

  useEffect(() => { onMessages?.(messages); }, [messages, onMessages]);
  useEffect(() => { onBusy?.(busy || setupBusy); }, [busy, setupBusy, onBusy]);

  useEffect(() => { alive.current = true; return () => {
    alive.current = false;
    generation.current += 1;
    setupGeneration.current += 1;
    aborter.current?.abort();
    reviewResolver.current?.(false);
    if (operation.current) void cancelWorker(operation.current).catch(() => {});
    if (setupOperation.current?.cancellable) void cancelWorker(setupOperation.current.id).catch(() => {});
  }; }, []);

  useEffect(() => {
    let current = true;
    if (!selected.cloud) {
      void probeModels();
      const discovery = setupOperation.current;
      return () => {
        current = false;
        if (discovery && setupOperation.current?.id === discovery.id) {
          setupGeneration.current += 1;
          setupOperation.current = null;
          void cancelWorker(discovery.id).catch(() => {});
        }
      };
    }
    setStatus("Checking provider status...");
    setError("");
    void runWorker({ id: `assistant-status-${crypto.randomUUID()}`, method: "assistant_provider_status", params: { provider } }).then(response => {
      if (!current || !alive.current) return;
      const result = workerResult(response);
      setCredentialConfigured(result.credential_configured === true);
      setStatus(typeof result.status === "string" ? result.status
        : result.cloud === true
          ? result.credential_store_supported === false ? "The OS credential store is unavailable." : result.credential_configured === true ? "Cloud provider credential configured." : "Cloud provider credential required."
          : `Local provider configured at ${String(result.endpoint ?? selected.endpoint ?? "the loopback endpoint")}.`);
    }).catch(reason => {
      if (current && alive.current) { setStatus("Provider unavailable."); setError(reason instanceof Error ? reason.message : String(reason)); }
    });
    return () => { current = false; };
  }, [provider]);

  useEffect(() => {
    if (transcript.current) transcript.current.scrollTop = transcript.current.scrollHeight;
  }, [messages, evidence.length]);

  const chooseProvider = (next: AssistantProvider) => {
    if (busy || setupBusy) return;
    const choice = PROVIDERS.find(item => item.id === next)!;
    attachmentTicket.current += 1; setAttachments([]); setAttaching(false);
    setProvider(next);
    setEndpoint(choice.endpoint ?? "");
    setModel("");
    setModels([]);
    setCredential("");
    setAllowCloud(false);
    setShareContext(false);
    setMessages([]);
    setEvidence([]);
    setReview(null);
    reviewResolver.current?.(false);
    reviewResolver.current = null;
  };

  const probeModels = async () => {
    const ticket = ++setupGeneration.current;
    const id = `assistant-models-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    setupOperation.current = { id, cancellable: true };
    setSetupBusy(true);
    setStatus("Connecting to provider and discovering models...");
    setError("");
    try {
      const result = workerResult(await runWorker({ id, method: "assistant_models", params: { provider, ...(endpoint.trim() ? { endpoint: endpoint.trim() } : {}) } }));
      if (!alive.current || setupGeneration.current !== ticket) return;
      const next = Array.isArray(result.models) ? result.models.filter((item): item is string => typeof item === "string") : [];
      setModels(next);
      const preferred = typeof result.preferred_model === "string" && next.includes(result.preferred_model) ? result.preferred_model : next[0];
      if (!model && preferred) setModel(preferred);
      setStatus(next.length ? `Connected. Found ${next.length} model${next.length === 1 ? "" : "s"}; sending a message loads the selected model if needed.` : selected.cloud ? "No models were reported; enter a model manually." : "Server connected, but no models are available. Install or load a model in your local provider, then probe again.");
    } catch (reason) { if (alive.current && setupGeneration.current === ticket) { setStatus("Provider connection failed."); setError(reason instanceof Error ? reason.message : String(reason)); } }
    finally {
      if (setupGeneration.current === ticket) setupOperation.current = null;
      if (alive.current && setupGeneration.current === ticket) setSetupBusy(false);
    }
  };

  const chooseWorkFolder = async () => {
    const ticket = ++setupGeneration.current;
    const pendingDraft = draft, pendingAttachments = attachments;
    setSetupBusy(true); setError("");
    try {
      await prepareContext?.();
      const result = await onCommand("assistant_choose_work_folder", {}) as Record<string, unknown>;
      if (!alive.current || setupGeneration.current !== ticket) return;
      if (!result.cancelled) {
        await clearConversation(`Work folder selected: ${String(result.workFolderName ?? "folder")}. Enable project tools to inspect its files.`);
        if (alive.current && setupGeneration.current === ticket) { setDraft(pendingDraft); setAttachments(pendingAttachments); }
      }
    } catch (reason) {
      if (alive.current && setupGeneration.current === ticket) setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      if (alive.current && setupGeneration.current === ticket) setSetupBusy(false);
    }
  };

  const saveCredential = async () => {
    const key = credential;
    if (!key) return;
    const ticket = ++setupGeneration.current;
    const id = `assistant-credential-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    setupOperation.current = { id, cancellable: false };
    setSetupBusy(true);
    setError("");
    try {
      workerResult(await runWorker({ id, method: "assistant_set_credential", params: { provider, key } }));
      if (!alive.current || setupGeneration.current !== ticket) return;
      setCredential("");
      setCredentialConfigured(true);
      setStatus("API credential is configured in the local credential store.");
    } catch (reason) { if (alive.current && setupGeneration.current === ticket) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally {
      if (alive.current && setupGeneration.current === ticket) { setCredential(""); setSetupBusy(false); }
      if (setupGeneration.current === ticket) setupOperation.current = null;
    }
  };

  const deleteCredential = async () => {
    const ticket = ++setupGeneration.current;
    const id = `assistant-credential-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    setupOperation.current = { id, cancellable: false };
    setSetupBusy(true);
    setError("");
    try {
      workerResult(await runWorker({ id, method: "assistant_delete_credential", params: { provider } }));
      if (!alive.current || setupGeneration.current !== ticket) return;
      setCredentialConfigured(false);
      setStatus("API credential removed.");
    } catch (reason) { if (alive.current && setupGeneration.current === ticket) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally {
      if (setupGeneration.current === ticket) setupOperation.current = null;
      if (alive.current && setupGeneration.current === ticket) setSetupBusy(false);
    }
  };

  const decideReview = (accepted: boolean) => {
    const resolve = reviewResolver.current;
    reviewResolver.current = null;
    setReview(null);
    resolve?.(accepted);
  };

  const requestReview = (proposal: ToolReview) => new Promise<boolean>(resolve => {
    reviewResolver.current = resolve;
    setReview(proposal);
  });

  const stop = async () => {
    generation.current += 1;
    aborter.current?.abort();
    decideReview(false);
    const id = operation.current;
    operation.current = null;
    try { if (id) await cancelWorker(id); }
    catch (reason) { if (alive.current) setError(`Local request stopped; worker cancellation was not confirmed: ${reason instanceof Error ? reason.message : String(reason)}`); }
    finally { if (alive.current) { setBusy(false); setStatus("Assistant request cancelled."); } }
  };

  const clearConversation = async (nextStatus = "Conversation cleared.") => {
    if (busy || operation.current || reviewResolver.current) await stop();
    setMessages([]);
    setEvidence([]);
    setReview(null);
    attachmentTicket.current += 1; setAttachments([]); setAttaching(false);
    setDraft("");
    setError("");
    setStatus(nextStatus);
  };

  const attachFiles = async (files: File[]) => {
    if (!files.length || busy || setupBusy || attaching) return;
    const ticket = ++attachmentTicket.current;
    setAttaching(true); setError("");
    try {
      if (files.length + attachments.length > 8) throw new Error("Select up to 8 attachments.");
      const added = [] as AssistantAttachment[];
      // Read sequentially to bound temporary decoding memory; reject the whole batch on error.
      for (const file of files) added.push(await readAssistantAttachment(file));
      const next = [...attachments, ...added];
      checkAttachmentBudget([...messages.flatMap(message => message.attachments ?? []), ...next]);
      if (alive.current && attachmentTicket.current === ticket) setAttachments(next);
    } catch (reason) {
      if (alive.current && attachmentTicket.current === ticket) setError(reason instanceof Error ? reason.message : String(reason));
    } finally { if (alive.current && attachmentTicket.current === ticket) setAttaching(false); }
  };

  const send = async () => {
    const text = draft.trim();
    if ((!text && !attachments.length) || busy || attaching) return;
    if (CLOUD_PROVIDERS.has(provider) && !allowCloud) { setError("Allow sending this conversation to the selected cloud provider first."); return; }
    const requestMessages = [...messages, { role: "user" as const, content: text, ...(attachments.length ? { attachments } : {}) }];
    const requestGeneration = ++generation.current;
    const controller = new AbortController();
    aborter.current = controller;
    setMessages(requestMessages);
    setAttachments([]);
    setDraft("");
    setEvidence([]);
    setError("");
    setBusy(true);
    setStatus("Waiting for assistant...");
    try {
      await prepareContext?.();
      if (controller.signal.aborted) return;
      const completed = await runAssistantConversation({
        provider, model, endpoint, allowCloud, shareProjectContext: shareContext,
        messages: requestMessages, runWorker, onCommand, getContext, getRevision,
        review: async proposal => {
          const context = typeof proposal.arguments.caseId === "string" ? await onCommand("assistant_review_context", { caseId: proposal.arguments.caseId }) : undefined;
          if (!alive.current || controller.signal.aborted || generation.current !== requestGeneration) return false;
          return requestReview({ ...proposal, ...(context && typeof context === "object" ? { context: context as Record<string, unknown> } : {}) });
        }, signal: controller.signal,
        onOperation: id => { operation.current = id; },
        onEvidence: item => { if (alive.current && generation.current === requestGeneration) {
          setEvidence(current => [...current, item]);
          setStatus(`${item.toolCall.name}: ${item.state}. Waiting for the assistant to continue...`);
        } },
      });
      if (alive.current && generation.current === requestGeneration) { setMessages(completed); setStatus("Assistant response complete."); }
    } catch (reason) {
      if (alive.current && generation.current === requestGeneration && !controller.signal.aborted) setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      if (alive.current && generation.current === requestGeneration) setBusy(false);
    }
  };

  const close = () => {
    setupGeneration.current += 1;
    const setup = setupOperation.current;
    setupOperation.current = null;
    if (setup?.cancellable) void cancelWorker(setup.id).catch(() => {});
    void stop();
    onClose();
  };

  return <aside className="assistant-chat" aria-label="SPIKE Assistant" onKeyDown={event => {
    if (event.key === "Escape" && settingsOpen && !review) { event.preventDefault(); setSettingsOpen(false); settingsButton.current?.focus(); }
  }}>
    <header className="assistant-chat__header">
      <div className="assistant-chat__identity"><h2>SPIKE Assistant</h2><p title={model}>{selected.label} · {model || "Choose a model in settings"}{shareContext ? " · Project tools on" : ""}</p></div>
      <button ref={settingsButton} type="button" className="spike-control--icon" aria-label="Assistant settings" title="Provider, model and sharing" aria-expanded={settingsOpen} aria-controls={`${idPrefix}-settings`} onClick={() => setSettingsOpen(open => !open)}><Settings2 size={18} /></button>
      {!nativeWindow && <button type="button" className="spike-control--icon" aria-label="Close SPIKE Assistant" title="Close" onClick={close}><X size={18} /></button>}
    </header>

    <section id={`${idPrefix}-settings`} className="assistant-chat__setup" aria-label="Assistant provider settings" hidden={!settingsOpen}>
      <div className="assistant-chat__settings-heading"><strong>Connection & sharing</strong><button type="button" className="spike-control--icon" aria-label="Close assistant settings" onClick={() => { setSettingsOpen(false); settingsButton.current?.focus(); }}><X size={16} /></button></div>
      <label>Provider<select value={provider} disabled={busy || setupBusy} onChange={event => chooseProvider(event.target.value as AssistantProvider)}>
        {PROVIDERS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select></label>
      {!selected.cloud && <><label>Local endpoint<input value={endpoint} disabled={busy || setupBusy} onChange={event => {
        setEndpoint(event.target.value); setModels([]); setModel("");
        void clearConversation("Endpoint changed. Probe models to check this server.");
      }} /></label><p className="assistant-chat__disclosure">{provider === "ollama" ? "Start the installed Ollama service with: ollama serve" : "In LM Studio, load a model and start the local API server."} SPIKE connects to that service; it does not download models.</p></>}
      <div className="assistant-chat__model-row">
        <label>Model<input list={`${idPrefix}-models`} value={model} disabled={busy || setupBusy} placeholder="Enter or probe a model" onChange={event => setModel(event.target.value)} /></label>
        <datalist id={`${idPrefix}-models`}>{models.map(item => <option key={item} value={item} />)}</datalist>
        <button type="button" disabled={busy || setupBusy} onClick={() => void probeModels()}>Probe models</button>
      </div>
      {selected.credential && <div className="assistant-chat__credential">
        <label>API credential<input type="password" autoComplete="off" value={credential} disabled={busy || setupBusy} onChange={event => setCredential(event.target.value)} /></label>
        <button type="button" disabled={busy || setupBusy || !credential} onClick={() => void saveCredential()}>Save securely</button>
        {credentialConfigured && <button type="button" className="spike-control--danger" disabled={busy || setupBusy} onClick={() => void deleteCredential()}>Remove</button>}
        <span>{credentialConfigured ? "Credential configured" : "No credential configured"}</span>
      </div>}
      {selected.cloud && <label className="assistant-chat__check"><input type="checkbox" checked={allowCloud} disabled={busy || setupBusy} onChange={event => {
        setAllowCloud(event.target.checked); void clearConversation("Conversation cleared after cloud consent changed.");
      }} /> Allow sending this conversation to {selected.label}</label>}
      <label className="assistant-chat__check"><input type="checkbox" checked={shareContext} disabled={busy || setupBusy} onChange={event => {
        setShareContext(event.target.checked); void clearConversation("Conversation cleared after project sharing changed.");
      }} /> Share selected project context and enable SPIKE tools</label>
      <button type="button" disabled={busy || setupBusy} onClick={() => void chooseWorkFolder()}>Choose work folder</button>
      <p className="assistant-chat__disclosure">The work folder is shared across this project's chats. The task harness can inspect bounded text files and calculate CSV summaries there. Requested evidence is sent to the selected model when project tools are enabled. Python drafts open for review; chat never runs them.</p>
      <p className="assistant-chat__disclosure">{shareContext
        ? preview.error || `Selected context: ${preview.sections} sections, ${preview.items} items, ${formatBytes(preview.bytes)}. ${preview.labels.join(", ") || "No named sections"}.`
        : "Project context is not selected. SPIKE tools stay unavailable."}</p>
      <details><summary>Available SPIKE skills ({assistantToolCatalog.length})</summary><ul>
        {(assistantToolCatalog as readonly CatalogPresentation[]).map(tool => <li key={tool.name}><strong>{tool.name}</strong> - {tool.description}{toolCapabilityStates?.[tool.name] ? ` (${String(toolCapabilityStates[tool.name])})` : ""}</li>)}
      </ul></details>
    </section>

    <div className="assistant-chat__feedback"><div className="assistant-chat__status" role="status">{status}</div>
      {error && <div className="assistant-chat__error" role="alert">{error} Review provider settings and retry.</div>}</div>
    <section ref={transcript} className="assistant-chat__messages" aria-label="Conversation" aria-live="polite">
      {messages.length === 0 && <div className="assistant-chat__empty"><h3>What are we working on?</h3><p>Ask a question, paste a screenshot, or attach an image or text file.</p><p>Choose a model in <button type="button" className="spike-control--bare" onClick={() => setSettingsOpen(true)}>settings</button>. Enable project sharing there to inspect your design and propose reviewed actions.</p></div>}
      {messages.filter(message => message.role !== "tool").map((message, index) => <article key={`${message.role}-${index}`} className={`assistant-chat__message assistant-chat__message--${message.role}`}>
        <strong>{message.role === "user" ? "You" : "Assistant"}</strong><AssistantMessageContent message={message} />
      </article>)}
      {evidence.length > 0 && <details className="assistant-chat__activity"><summary>SPIKE activity · {evidence.length} action{evidence.length === 1 ? "" : "s"}{evidence.some(item => item.state !== "completed") ? " · Needs attention" : ""}</summary>{evidence.map((item, index) => <details key={`${item.toolCall.id}-${index}`} className={`assistant-chat__evidence assistant-chat__evidence--${item.state}`}>
        <summary>{item.toolCall.name}: {item.state}</summary><pre>{item.detail}</pre>
      </details>)}</details>}
    </section>

    {review && <section className="assistant-chat__review" role="dialog" aria-modal="true" aria-labelledby={`${idPrefix}-review-title`}>
      <h3 id={`${idPrefix}-review-title`}>Review proposed {review.effect}</h3>
      <p>{review.description}</p><p>Project revision: <code>{review.revision}</code></p>
      {review.name === "spike_python_draft" ? <><p>Unsaved draft: {String(review.arguments.title)}.py · Apply stages this source; it does not run it.</p><pre>{String(review.arguments.source)}</pre></> : <pre>{JSON.stringify(review.arguments, null, 2)}</pre>}
      {review.context && <details open><summary>Exact prepared case and preflight evidence</summary><pre>{JSON.stringify(review.context, null, 2)}</pre></details>}
      <div><button type="button" className="spike-control--primary" onClick={() => decideReview(true)}>Apply once</button><button type="button" onClick={() => decideReview(false)}>Reject</button></div>
    </section>}

    <footer className="assistant-chat__composer" onDragOver={event => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; } }} onDrop={event => { event.preventDefault(); void attachFiles(Array.from(event.dataTransfer.files)); }}>
      <input ref={attachmentInput} type="file" multiple hidden accept={ASSISTANT_ATTACHMENT_ACCEPT} aria-label="Attach images or text files" onChange={event => { void attachFiles(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
      {attachments.length > 0 && <div className="assistant-chat__pending" aria-label="Pending attachments">{attachments.map(item => <figure key={item.id}>
        {item.mimeType.startsWith("image/") && <img src={item.dataUrl} alt={item.name} />}
        <figcaption title={item.name}>{item.name}</figcaption><button type="button" className="spike-control--icon" aria-label={`Remove ${item.name}`} disabled={busy || attaching} onClick={() => setAttachments(items => items.filter(entry => entry.id !== item.id))}><X size={14} /></button>
      </figure>)}</div>}
      <label htmlFor={`${idPrefix}-draft`}>Message</label>
      {!draft.trim() && <div className="assistant-chat__task-shortcuts">
        {[
          ["Inspect files", "Use spike_work_files to list the selected work folder. Identify useful input files and ask which one to inspect if the target is unclear. Do not change files."],
          ["Analyze data", "Inspect my selected work folder and the relevant data file. Confirm the exact columns, units and requested calculation with me if missing. Use deterministic tools for calculations and report the source hash, actual results and limitations."],
          ["Draft Python", "Help me create a Python script from the available project/file evidence. Ask for my desired inputs and outputs if missing. Use actual SPIKE Python APIs where needed, include validation, and stage the source with spike_python_draft after review. Do not run or save it."],
        ].map(([label, prompt]) => <button key={label} type="button" className="spike-control--compact" disabled={busy || setupBusy || attaching} onClick={() => setDraft(prompt)}>{label}</button>)}
      </div>}
      <textarea id={`${idPrefix}-draft`} rows={3} value={draft} disabled={busy || setupBusy || attaching} placeholder="Message SPIKE · paste an image or drop files" onPaste={event => { const files = Array.from(event.clipboardData.files); if (files.length) { event.preventDefault(); void attachFiles(files); } }} onChange={event => setDraft(event.target.value)} onKeyDown={event => {
        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); }
      }} />
      <div className="assistant-chat__compose-actions"><button type="button" className="spike-control--icon" aria-label="Attach images or text" title="Attach PNG, JPEG, WebP or UTF-8 text" disabled={busy || setupBusy || attaching} onClick={() => attachmentInput.current?.click()}><Paperclip size={18} /></button><span className="assistant-chat__send-note">{attaching ? "Reading attachments…" : selected.cloud ? `Sends to ${selected.label}` : "Local model"}</span><button type="button" className="spike-control--primary" disabled={busy || setupBusy || attaching || (!draft.trim() && !attachments.length) || !model.trim() || (shareContext && !!preview.error)} onClick={() => void send()}>Send</button>
        {busy && <button type="button" className="spike-control--danger" onClick={() => void stop()}>Cancel</button>}
      <button type="button" className="spike-control--icon" aria-label="Clear conversation" title="Clear conversation" disabled={setupBusy || (!busy && messages.length === 0 && evidence.length === 0 && !draft && !attachments.length)} onClick={() => void clearConversation()}><Trash2 size={17} /></button></div>
    </footer>
  </aside>;
}
