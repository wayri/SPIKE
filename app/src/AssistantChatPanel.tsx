// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { cancelLocalWorker, runLocalWorker } from "./workerBridge";
import { assistantToolCatalog, toolCapabilityStates } from "./assistantSkills";
import {
  CLOUD_PROVIDERS,
  contextPreview,
  runAssistantConversation,
  type AssistantMessage,
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

  const chooseProvider = (next: AssistantProvider) => {
    if (busy || setupBusy) return;
    const choice = PROVIDERS.find(item => item.id === next)!;
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
    setError("");
    try {
      const result = workerResult(await runWorker({ id, method: "assistant_models", params: { provider, ...(endpoint.trim() ? { endpoint: endpoint.trim() } : {}) } }));
      if (!alive.current || setupGeneration.current !== ticket) return;
      const next = Array.isArray(result.models) ? result.models.filter((item): item is string => typeof item === "string") : [];
      setModels(next);
      if (!model && next[0]) setModel(next[0]);
      setStatus(next.length ? `Found ${next.length} model${next.length === 1 ? "" : "s"}.` : "No models were reported; enter a model manually.");
    } catch (reason) { if (alive.current && setupGeneration.current === ticket) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally {
      if (setupGeneration.current === ticket) setupOperation.current = null;
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
    setDraft("");
    setError("");
    setStatus(nextStatus);
  };

  const send = async () => {
    const text = draft.trim();
    if (!text || busy) return;
    if (CLOUD_PROVIDERS.has(provider) && !allowCloud) { setError("Allow sending this conversation to the selected cloud provider first."); return; }
    const requestMessages = [...messages, { role: "user" as const, content: text }];
    const requestGeneration = ++generation.current;
    const controller = new AbortController();
    aborter.current = controller;
    setMessages(requestMessages);
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
        onEvidence: item => { if (alive.current && generation.current === requestGeneration) setEvidence(current => [...current, item]); },
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

  return <aside className="assistant-chat" aria-label="SPIKE Assistant">
    <header className="assistant-chat__header">
      <div><h2>SPIKE Assistant</h2><p>Simple questions and reviewed actions; use external LLM handoff for complex workflows.</p></div>
      {!nativeWindow && <button type="button" className="spike-control--icon" aria-label="Close SPIKE Assistant" title="Close" onClick={close}>X</button>}
    </header>

    <section className="assistant-chat__setup" aria-label="Assistant provider settings">
      <label>Provider<select value={provider} disabled={busy || setupBusy} onChange={event => chooseProvider(event.target.value as AssistantProvider)}>
        {PROVIDERS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select></label>
      {!selected.cloud && <label>Local endpoint<input value={endpoint} disabled={busy || setupBusy} onChange={event => setEndpoint(event.target.value)} /></label>}
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
      <p className="assistant-chat__disclosure">{shareContext
        ? preview.error || `Selected context: ${preview.sections} sections, ${preview.items} items, ${formatBytes(preview.bytes)}. ${preview.labels.join(", ") || "No named sections"}.`
        : "Project context is not selected. SPIKE tools stay unavailable."}</p>
      <details><summary>Available SPIKE skills ({assistantToolCatalog.length})</summary><ul>
        {(assistantToolCatalog as readonly CatalogPresentation[]).map(tool => <li key={tool.name}><strong>{tool.name}</strong> - {tool.description}{toolCapabilityStates?.[tool.name] ? ` (${String(toolCapabilityStates[tool.name])})` : ""}</li>)}
      </ul></details>
    </section>

    <div className="assistant-chat__feedback"><div className="assistant-chat__status" role="status">{status}</div>
      {error && <div className="assistant-chat__error" role="alert">{error} Review provider settings and retry.</div>}</div>
    <section className="assistant-chat__messages" aria-label="Conversation" aria-live="polite">
      {messages.length === 0 && <p className="assistant-chat__empty">Ask about the loaded design, or enable project context to use listed SPIKE skills.</p>}
      {messages.filter(message => message.role !== "tool").map((message, index) => <article key={`${message.role}-${index}`} className={`assistant-chat__message assistant-chat__message--${message.role}`}>
        <strong>{message.role === "user" ? "You" : "Assistant"}</strong><p>{message.content || "Requested SPIKE action."}</p>
      </article>)}
      {evidence.map((item, index) => <details key={`${item.toolCall.id}-${index}`} className={`assistant-chat__evidence assistant-chat__evidence--${item.state}`} open>
        <summary>{item.toolCall.name}: {item.state}</summary><pre>{item.detail}</pre>
      </details>)}
    </section>

    {review && <section className="assistant-chat__review" role="dialog" aria-modal="true" aria-labelledby={`${idPrefix}-review-title`}>
      <h3 id={`${idPrefix}-review-title`}>Review proposed {review.effect}</h3>
      <p>{review.description}</p><p>Project revision: <code>{review.revision}</code></p><pre>{JSON.stringify(review.arguments, null, 2)}</pre>{review.context && <details open><summary>Exact prepared case and preflight evidence</summary><pre>{JSON.stringify(review.context, null, 2)}</pre></details>}
      <div><button type="button" className="spike-control--primary" onClick={() => decideReview(true)}>Apply once</button><button type="button" onClick={() => decideReview(false)}>Reject</button></div>
    </section>}

    <footer className="assistant-chat__composer">
      <label htmlFor={`${idPrefix}-draft`}>Message</label>
      <textarea id={`${idPrefix}-draft`} rows={3} value={draft} disabled={busy || setupBusy} placeholder="Ask the SPIKE Assistant" onChange={event => setDraft(event.target.value)} onKeyDown={event => {
        if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); }
      }} />
      <div><button type="button" className="spike-control--primary" disabled={busy || setupBusy || !draft.trim() || !model.trim() || (shareContext && !!preview.error)} onClick={() => void send()}>Send</button>
        {busy && <button type="button" className="spike-control--danger" onClick={() => void stop()}>Cancel</button>}</div>
      <button type="button" className="spike-control--compact" disabled={setupBusy || (!busy && messages.length === 0 && evidence.length === 0 && !draft)} onClick={() => void clearConversation()}>Clear conversation</button>
    </footer>
  </aside>;
}
